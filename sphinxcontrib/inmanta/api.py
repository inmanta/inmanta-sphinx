"""
    Copyright 2017 Inmanta

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.

    Contact: code@inmanta.com
"""

import typing
from collections import defaultdict, OrderedDict
from typing import Optional, Union
from collections.abc import Sequence, Callable, Mapping
import os
import re
import shutil
import sys
import tempfile

import click
import toml

from inmanta import module, compiler, ast
from inmanta.agent import handler
from inmanta.ast.attribute import RelationAttribute
from inmanta.module import Project
from inmanta.plugins import PluginMeta, Plugin
from inmanta.resources import resource, Resource
from inmanta.agent.handler import ResourceHandler
from sphinx.util import docstrings


ATTRIBUTE_REGEX = re.compile(
    "(?::param|:attribute|:attr) (.*?)(?:(?=:param)|(?=:attribute)|(?=:attr)|\Z)", re.S
)
ATTRIBUTE_LINE_REGEX = re.compile("([^\s:]+)(:)?\s(.*?)\Z")
PARAM_REGEX = re.compile(":param|:attribute|:attr")
AUTODOC_FILE = "autodoc.rst"


def format_multiplicity(rel):
    low = rel.low
    high = rel.high

    if low == high:
        return low

    if high is None:
        high = "*"

    return str(low) + ":" + str(high)


def parse_docstring(docstring: str) -> dict[str, Union[dict[str, str], list[str]]]:
    """
    Parse a docstring and return its components. Inspired by
    https://github.com/openstack/rally/blob/master/rally/common/plugin/info.py#L31-L79

    :param str docstring: The string/comment to parse in docstring elements
    :returns: {
        "comment": ...,
        "attributes": ...,
    }
    """
    docstring = "\n".join(docstrings.prepare_docstring(docstring))
    comment = docstring
    attributes = {}
    match = PARAM_REGEX.search(docstring)
    if match:
        comment = docstring[: match.start()]

        # process params
        attr_lines = ATTRIBUTE_REGEX.findall(docstring)
        for line in attr_lines:
            line = re.sub("\s+", " ", line.strip())
            match = ATTRIBUTE_LINE_REGEX.search(line)
            if match is None:
                print("Comment empty: " + line, file=sys.stderr)
                continue

            items = match.groups()
            attributes[items[0]] = items[2]

    comment_lines = []
    for line in comment.split("\n"):
        line = line.rstrip()
        comment_lines.append(line)

    return {"comment": comment_lines, "attributes": attributes}


class DocModule(object):
    def doc_compile(
        self, module_dir: Optional[str], name: str, import_list: Sequence[str]
    ) -> list[str]:
        """
        Compile the documentation for a module and generate the API documentation,
        organized in sections e.g. Entities, Implementations, Resources, Handlers...

        :param module_dir: Absolute path to the directory where all v1 modules are stored. Must not be None if the module
            is a v1 module.
        :param name: The name of the module.
        :param import_list: A list of all namespaces that should be imported in order to load the full AST for this module.

        :returns: The generated documentation as a list of str.
        """
        old_curdir = os.getcwd()
        main_cf = "\n".join(["import " + i for i in import_list])
        try:
            project_dir = tempfile.mkdtemp()
            with open(os.path.join(project_dir, "main.cf"), "w+") as fd:
                fd.write(main_cf)

            module_path: str = module_dir if module_dir is not None else "[]"
            with open(os.path.join(project_dir, "project.yml"), "w+") as fd:
                fd.write(
                    """name: docgen
description: Project to generate docs
repo: %s
modulepath: %s
pip:
  use_system_config: true
"""
                    % (module_path, module_path)
                )

            os.chdir(project_dir)
            project = Project.get()
            if hasattr(project, "install_modules"):
                # This is required for Modules V2, which don't install on each compile
                project.install_modules()
            project.load()
            _, root_ns = compiler.get_types_and_scopes()

            module_ns = root_ns.get_child(name)

            doc_ns = [ns for ns in module_ns.children(recursive=True)]
            doc_ns.append(module_ns)

            modules = {}
            for ns in doc_ns:
                modules[ns.get_full_name()] = ns.defines_types

            lines = []

            types = defaultdict(OrderedDict)
            for module in sorted(modules.keys()):
                for type_name in sorted(modules[module].keys()):
                    type_obj = modules[module][type_name]
                    if isinstance(type_obj, ast.entity.Entity):
                        full_name = type_obj.get_full_name()
                        types["entity"][full_name] = type_obj

                    elif isinstance(type_obj, ast.entity.Implementation):
                        full_name = type_obj.get_full_name()
                        types["implementation"][full_name] = type_obj

                    elif isinstance(type_obj, ast.type.ConstraintType):
                        types["typedef"][type_name] = type_obj

                    elif isinstance(type(type_obj), PluginMeta):
                        types["plugin"][type_name] = type_obj

                    else:
                        print(type(type_obj))

            if len(types["typedef"]) > 0:
                lines.extend(self.emit_heading("Typedefs", "-"))
                for obj in types["typedef"].values():
                    lines.extend(self.emit_typedef(obj))
                lines.append("")

            if len(types["entity"]) > 0:
                lines.extend(self.emit_heading("Entities", "-"))
                for obj in types["entity"].values():
                    lines.extend(self.emit_entity(obj))

            if len(types["implementation"]) > 0:
                lines.extend(self.emit_heading("Implementations", "-"))
                for obj in types["implementation"].values():
                    lines.extend(self.emit_implementation(obj))

            if len(types["plugin"]) > 0:
                lines.extend(self.emit_heading("Plugins", "-"))
                for plugin in types["plugin"].values():
                    lines.extend(self.emit_plugin(plugin))

            res_list = sorted(
                [
                    res
                    for res in resource._resources.items()
                    if res[0][: len(name)] == name
                ],
                key=lambda x: x[0],
            )
            if len(res_list) > 0:
                lines.extend(self.emit_heading("Resources", "-"))
                for res, (cls, opt) in res_list:
                    lines.extend(self.emit_resource(res, cls, opt))

            h = []
            for entity, handlers in handler.Commander.get_handlers().items():
                for handler_name, cls in handlers.items():
                    if cls.__module__.startswith("inmanta_plugins." + name):
                        h.extend(self.emit_handler(entity, handler_name, cls))

            if len(h) > 0:
                lines.extend(self.emit_heading("Handlers", "-"))
                lines.extend(h)

            return lines
        finally:
            os.chdir(old_curdir)
            shutil.rmtree(project_dir)

        return []

    def emit_handler(
        self, entity: str, name: str, cls: typing.Type[ResourceHandler]
    ) -> list[str]:
        """
        Generate documentation for a handler.
        :param entity: The entity this handler applies to.
        :param name: The name of the handler being documented.
        :param cls: The type of the handler.

        :return: The documented handler as a list of str
        """
        mod = cls.__module__[len("inmanta_plugins.") :]
        lines = [".. py:class:: %s.%s" % (mod, cls.__name__), ""]
        if cls.__doc__ is not None:
            lines.extend(self.prep_docstring(cls.__doc__, 1))
            lines.append("")

        lines.append(" * Handler name ``%s``" % name)
        lines.append(" * Handler for entity :inmanta:Entity:`%s`" % entity)
        lines.append("")
        return lines

    def emit_resource(
        self, name: str, cls: Resource, opt: Mapping[str, str]
    ) -> list[str]:
        """
        Generate documentation for a resource.
        :param name: The name of the resource being documented.
        :param cls: The type of the resource.
        :param opt: Attributes of the resource.
        :return: The documented resource as a list of str
        """
        mod = cls.__module__[len("inmanta_plugins.") :]
        lines = [".. py:class:: %s.%s" % (mod, cls.__name__), ""]
        if cls.__doc__ is not None:
            lines.extend(self.prep_docstring(cls.__doc__, 1))
            lines.append("")

        lines.append(" * Resource for entity :inmanta:Entity:`%s`" % name)
        lines.append(" * Id attribute ``%s``" % opt["name"])
        lines.append(" * Agent name ``%s``" % opt["agent"])

        handlers = []
        for cls in handler.Commander.get_handlers()[name].values():
            mod = cls.__module__[len("inmanta_plugins.") :]
            handlers.append(":py:class:`%s.%s`" % (mod, cls.__name__))
        lines.append(" * Handlers " + ", ".join(handlers))
        lines.append("")
        return lines

    def emit_plugin(self, instance: Plugin) -> list[str]:
        """
        Generate documentation for a plugin.
        :param instance: The plugin being documented.
        :return: The documented plugin as a list of str
        """
        lines = [
            ".. py:function:: %s.%s" % (str(instance.ns), instance.get_signature()),
            "",
        ]
        if instance.__class__.__function__.__doc__ is not None:
            docstring = [
                "   " + x
                for x in docstrings.prepare_docstring(
                    instance.__class__.__function__.__doc__
                )
            ]
            lines.extend(docstring)
            lines.append("")
        return lines

    def emit_heading(self, heading: str, char: str) -> list[str]:
        """
        Emit a sphinx heading/section underlined by char.
        """
        return [heading, char * len(heading), ""]

    def prep_docstring(self, docstr, indent_level=0):
        return [
            ("   " * indent_level) + x for x in docstrings.prepare_docstring(docstr)
        ]

    def emit_attributes(
        self, entity: ast.entity.Entity, attributes: Mapping[str, str]
    ) -> list[str]:
        """
        Generate documentation for the attributes of an entity.
        :param entity: The entity whose attributes are being documented.
        :param attributes: Maps attributes names to their documentation.
        :return: The documented attributes as a list of str
        """
        all_attributes = [
            entity.get_attribute(name) for name in list(entity._attributes.keys())
        ]
        relations = [x for x in all_attributes if isinstance(x, RelationAttribute)]
        others = [x for x in all_attributes if not isinstance(x, RelationAttribute)]

        defaults = entity.get_default_values()
        lines = []

        for attr in others:
            name = attr.get_name()

            attr_line = "   .. inmanta:attribute:: {1} {2}.{0}".format(
                attr.get_name(), attr.get_type().type_string(), entity.get_full_name()
            )
            if attr.get_name() in defaults:
                attr_line += "=" + str(defaults[attr.get_name()])
            lines.append(attr_line)
            lines.append("")
            if name in attributes:
                lines.append("      " + attributes[name])

            lines.append("")

        for attr in relations:
            lines.append(
                "   .. inmanta:relation:: {} {}.{} [{}]".format(
                    attr.get_type(),
                    entity.get_full_name(),
                    attr.get_name(),
                    format_multiplicity(attr),
                )
            )
            if attr.comment is not None:
                lines.append("")
                lines.extend(self.prep_docstring(attr.comment, 2))

            lines.append("")
            if attr.end is not None:
                otherend = (
                    attr.end.get_entity().get_full_name() + "." + attr.end.get_name()
                )
                lines.append(
                    "      other end: :inmanta:relation:`{0} [{1}]<{0}>`".format(
                        otherend, format_multiplicity(attr.end)
                    )
                )
                lines.append("")

        if len(entity.implementations) > 0:
            lines.append(
                "   The following implementations are defined for this entity:"
            )
            lines.append("")
            for impl in entity.implementations:
                lines.append(
                    "      * :inmanta:implementation:`%s`" % impl.get_full_name()
                )

            lines.append("")

        if len(entity.implements) > 0:
            lines.append(
                "   The following implements statements select implementations for this entity:"
            )
            lines.append("")
            for impl in entity.implements:
                lines.append(
                    "      * "
                    + ", ".join(
                        [
                            ":inmanta:implementation:`%s`" % x.get_full_name()
                            for x in impl.implementations
                        ]
                    )
                )

                constraint_str = impl.constraint.pretty_print()
                if constraint_str != "True":
                    lines.append("        constraint ``%s``" % constraint_str)

            lines.append("")

        return lines

    def emit_implementation(self, impl: ast.entity.Implementation) -> list[str]:
        """
        Generate documentation for a single implementation.

        :param impl: The implementation being documented
        :return: The generated implementation documentation as a list of str.
        """
        lines = []
        lines.append(
            ".. inmanta:implementation:: {0}::{1}".format(
                impl.namespace.get_full_name(), impl.name
            )
        )
        if impl.comment is not None:
            lines.append("")
            lines.extend(self.prep_docstring(impl.comment, 2))
        lines.append("")

        return lines

    def emit_entity(self, entity: ast.entity.Entity) -> list[str]:
        """
        Generate documentation for a single entity.

        :param entity: The entity being documented
        :return: The generated entity documentation as a list of str.
        """
        lines = []
        lines.append(".. inmanta:entity:: " + entity.get_full_name())
        lines.append("")

        if len(entity.parent_entities) > 0:
            lines.append(
                "   Parents: %s"
                % ", ".join(
                    [
                        ":inmanta:entity:`%s`" % x.get_full_name()
                        for x in entity.parent_entities
                    ]
                )
            )
        lines.append("")

        attributes = {}
        if entity.comment:
            result = parse_docstring(entity.comment)
            lines.extend(["   " + x for x in result["comment"]])
            lines.append("")
            attributes = result["attributes"]

        lines.extend(self.emit_attributes(entity, attributes))
        lines.append("")

        return lines

    def emit_typedef(self, typedef: ast.type.ConstraintType) -> list[str]:
        """
        Generate documentation for a single typedef statement.

        :param typedef: The typedef being documented
        :return: The generated typedef documentation as a list of str.
        """
        lines = []
        lines.append(".. inmanta:typedef:: {0}".format(typedef.type_string()))
        lines.append("")
        lines.append("   * Base type ``{0}``".format(typedef.basetype.type_string()))
        lines.append(
            "   * Type constraint ``{0}``".format(typedef.expression.pretty_print())
        )
        lines.append("")
        return lines

    def emit_intro(self, module: module.Module) -> list[str]:
        """
        Generate the introduction to the module's documentation.

        :param module: The module being documented.
        :return: The generated module documentation introduction as a list of str.
        """
        lines = self.emit_heading("Module " + module.name, "=")

        if module.metadata.description is not None:
            lines.append(module.metadata.description)
            lines.append("")

        lines.append(" * License: " + module.metadata.license)
        lines.append(" * Version: " + str(module.version))

        if (
            hasattr(module.metadata, "compiler_version")
            and module.metadata.compiler_version is not None
        ):
            lines.append(
                " * This module requires compiler version %s or higher"
                % module.metadata.compiler_version
            )

        lines.append("")
        return lines

    def _get_modules(
        self, module_source_dir: Optional[str], module_name: str
    ) -> Optional[tuple[module.Module, list[str]]]:
        """
        Given a module name, returns the module object and a list of all submodule names.

        :param module_source_dir: Absolute path to the directory where all v1 modules are stored. Must not be None if module is a v1
            module.
        :param module_name: The name of the module to fetch.
        """

        def get_module() -> Optional[module.Module]:
            """
            Returns the module object.
            """
            if hasattr(module, "ModuleV2"):
                local_v2_source: module.ModuleV2Source = module.ModuleV2Source(urls=[])
                v2_mod: Optional[module.ModuleV2] = (
                    local_v2_source.get_installed_module(
                        project=None, module_name=module_name
                    )
                )
                if v2_mod is not None:
                    return v2_mod
                elif module_source_dir is None:
                    raise ValueError(
                        f"{module_name} was not found as a v2 module. Either install it as a v2 module or pass the directory"
                        " where v1 modules are located."
                    )
                else:
                    return module.Module.from_path(
                        os.path.join(module_source_dir, module_name)
                    )
            else:
                # legacy mode
                if module_source_dir is None:
                    raise ValueError(
                        "Please pass the directory where all modules modules are located."
                    )
                try:
                    return module.Module(
                        None, os.path.join(module_source_dir, module_name)
                    )
                except (module.InvalidModuleException, module.InvalidMetadata):
                    return None

        mod: Optional[module.Module] = get_module()
        return (mod, mod.get_all_submodules()) if mod is not None else None

    def get_module_filter(self, module_folder: Optional[str]) -> Callable[[str], bool]:
        """
        Produce a function to filter module names, based on the `tool.inmanta-sphinx.docgen.module_filter` config option

        As input, it gets the module folder. It read the `pyproject.toml` in the module and extract the filters.

        If no config is found, it defaults to including everything

        :param module_folder: the folder containing the module
        :return: a function that, given the fully qualified name of a module, will return True if the module has to be included.
        """

        if not module_folder:
            return lambda x: True

        pyproject = os.path.join(module_folder, "pyproject.toml")
        if not os.path.exists(pyproject):
            return lambda x: True

        pyproject_dict = toml.load(pyproject)
        filters = (
            pyproject_dict.get("tool", {})
            .get("inmanta-sphinx", {})
            .get("docgen", {})
            .get("module_filter", [])
        )
        if isinstance(filters, str):
            filters = [filters]

        parsed_filters = [re.compile(f) for f in filters]
        if not parsed_filters:
            return lambda x: True

        def filter_func(name):
            for filter in parsed_filters:
                if filter.match(name):
                    return True
            return False

        return filter_func

    def run(
        self, module_source_dir: str, module_name: str, extra_modules: Sequence[str]
    ) -> str:
        """
        Run the module doc generation.

        :param module_source_dir: Absolute path to the directory where the source of the module is.
        :param module_name: The name of the module to generate docs for.
        :param extra_modules: The names of any extra modules.

        :returns: The documentation for this module as a string.
        """
        mod_data: Optional[tuple[module.Module, list[str]]] = self._get_modules(
            module_source_dir, module_name
        )
        if mod_data is None:
            raise Exception(
                f"Could not find module {module_name} in {module_source_dir}."
            )
        mod, submodules = mod_data

        module_filter = self.get_module_filter(
            None
            if not module_source_dir
            else os.path.join(module_source_dir, module_name)
        )

        for name in extra_modules:
            extra_mod_data: Optional[tuple[module.Module, list[str]]] = (
                self._get_modules(module_source_dir, name)
            )
            if extra_mod_data is not None:
                submodules.extend(extra_mod_data[1])

        submodules = sorted([sm for sm in set(submodules) if module_filter(sm)])
        print("Selected sub-modules: " + ", ".join(submodules))

        lines = self.emit_intro(mod)
        lines.extend(self.doc_compile(module_source_dir, mod.name, submodules))
        lines = [line for line in lines if line is not None]
        return "\n".join(lines)


@click.command()
@click.option(
    "--module-sources",
    help=(
        "The path to the local directory where all module sources (v1 or v2) are stored."
    ),
)
@click.option(
    "--module-name", help="The module to generate api docs for", required=True
)
@click.option(
    "--extra-modules",
    "-m",
    help="Extra modules that should be loaded to render the docs",
    multiple=True,
)
@click.option(
    "--out-dir",
    "-d",
    help="Path to directory in which to put documentation.",
    required=True,
)
@click.option(
    "--autodoc-only",
    "-a",
    is_flag=True, show_default=True, default=False,
    help="Ignore the README.md file when building documentation for this module "
         "and generate documentation under <out_dir>/<module_name>.rst.",
    required=True,
)
def generate_module_doc(
    module_sources: str,
    module_name: str,
    extra_modules: Sequence[str],
    out_dir: str,
    autodoc_only: bool = False,
):
    """
    Generate API documentation for a module. This command expects the module source to live in a directory
    that has the module's name and that is in the <module_sources> directory.

    The output of this command depends on whether the module contains
    a README.md file or not:

    If the module contains a README.md file, a doc directory named <module_name> for this module is created in <out_dir>.
    This folder is then populated with relevant doc info for this module:
        - The README.md file
        - The changelog.md file (if present)
        - The docs folder (if present)

    In addition, if the README.md file references ``autodoc.rst``, then api documentation for this module will be
    generated and placed in a ``autodoc.rst`` file in the <module_name> directory

    If the module doesn't contain a README.md or if the `--autodoc-only` option is provided, then the
    api documentation for this module is generated and placed in a <module_name>.rst file in <out_dir>.
    """

    module_source_dir = os.path.abspath(os.path.join(module_sources, module_name))
    readme_file = os.path.join(module_source_dir, "README.md")

    # No README in module source -> generate autodoc in
    # <out_dir>/
    #     ├─ <module_name>.rst

    if not os.path.exists(readme_file) or autodoc_only:
        write_auto_doc(
            extra_modules=extra_modules,
            module_name=module_name,
            module_source_dir=module_sources,
            out_file=os.path.join(out_dir, module_name + ".rst"),
        )
        return

    # Module source contains a README -> populate:
    # <out_dir>/
    #     ├─ <module_name>/
    #              ├─ README.md
    #              ├─ CHANGELOG.md      (copy from module source if it exists)
    #              ├─ docs/             (copy from module source if it exists)
    #              ├─ autodoc.rst       (iff readme mentions "autodoc.rst")

    module_doc_dir = build_module_doc_directory(out_dir, module_source_dir, module_name)

    with open(readme_file, "r") as f:
        for line in f:
            if AUTODOC_FILE in line:
                write_auto_doc(
                    extra_modules=extra_modules,
                    module_name=module_name,
                    module_source_dir=module_sources,
                    out_file=os.path.join(
                        os.path.abspath(module_doc_dir), AUTODOC_FILE
                    ),
                )
                break


def build_module_doc_directory(out_dir: str, module_dir, module_name: str) -> str:
    """
    Create a documentation directory named <module_name> in <out_dir> directory and return the path to it.
    In addition, relevant documentation files/directories are copied to this directory from <module_dir> path.

    :param out_dir: Root dir in which to create the <module_name> directory.
    :param module_dir: Path to the module.
    :param module_name: Name of the module doc directory to create.
    :return: Path to the created directory.
    """
    module_doc_dir = os.path.abspath(os.path.join(out_dir, module_name))
    os.makedirs(module_doc_dir)
    src_to_dest_map = {
        os.path.join(module_dir, "README.md"): os.path.join(
            module_doc_dir, "README.md"
        ),
        os.path.join(module_dir, "CHANGELOG.md"): os.path.join(
            module_doc_dir, "CHANGELOG.md"
        ),
        os.path.join(module_dir, "docs"): os.path.join(module_doc_dir, "docs"),
    }
    for src, dest in src_to_dest_map.items():
        if not os.path.exists(src):
            continue
        if os.path.isdir(src):
            shutil.copytree(src, dest)
        else:
            shutil.copy(src, dest)

    return module_doc_dir


def write_auto_doc(
    extra_modules: Sequence[str],
    module_name: str,
    module_source_dir: Optional[str],
    out_file: str,
) -> None:
    """
    Wrapper around the ``DocModule.run()`` method to generate documentation for a module
    and write it to a file. This method expects the module source to live in a <module_name> subdirectory
    of the <module_source_dir> directory.

    :param extra_modules: Sequence of extra modules required to load the full AST for this module.
    :param module_name: Name of the module for which to generate documentation.
    :param module_source_dir: Directory containing module sources.
    :param out_file: Path to the file to write generated documentation to.
    :return: None
    """
    doc = DocModule()

    auto_doc = doc.run(
        module_source_dir=os.path.abspath(module_source_dir),
        module_name=module_name,
        extra_modules=extra_modules,
    )
    os.makedirs(os.path.dirname(out_file), exist_ok=True)

    with open(out_file, "w+") as fd:
        fd.write(auto_doc)


if __name__ == "__main__":
    generate_module_doc()
