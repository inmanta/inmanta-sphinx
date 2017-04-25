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


# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

# based on oslo_config.sphinxext
# http://docs.openstack.org/developer/oslo.config/sphinxext.html

from collections import defaultdict
import os
import re
import shutil
import sys
import tempfile

from docutils import nodes
from docutils.parsers import rst
from docutils.statemachine import ViewList
from sphinx import addnodes
from sphinx.directives import ObjectDescription
from sphinx.domains import Domain
from sphinx.domains import ObjType
from sphinx.locale import l_
from sphinx.roles import XRefRole
from sphinx.util import docstrings
from sphinx.util.nodes import make_refnode
from sphinx.util.nodes import nested_parse_with_titles

from inmanta import module, compiler, ast
from inmanta.ast.attribute import RelationAttribute
from inmanta.module import Project
from inmanta.plugins import PluginMeta
from _collections import OrderedDict
from inmanta.resources import resource
from inmanta.agent import handler


def format_multiplicity(rel):
    low = rel.low
    high = rel.high

    if low == high:
        return low

    if high is None:
        high = "\*"

    return str(low) + ":" + str(high)


def get_first_statement(stmts):
    out = None
    line = float("inf")
    for stmt in stmts:
        if(stmt.line > 0 and stmt.line < line):
            out = stmt
            line = stmt.line
    return out


ATTRIBUTE_REGEX = re.compile("(?::param|:attribute|:attr) (.*?)(?:(?=:param)|(?=:attribute)|(?=:attr)|\Z)", re.S)
ATTRIBUTE_LINE_REGEX = re.compile("([^\s:]+)(:)?\s(.*?)\Z")
PARAM_REGEX = re.compile(":param|:attribute|:attr")


def parse_docstring(docstring):
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
        comment = docstring[:match.start()]

        # process params
        attr_lines = ATTRIBUTE_REGEX.findall(docstring)
        for line in attr_lines:
            line = re.sub("\s+", " ", line.strip())
            match = ATTRIBUTE_LINE_REGEX.search(line)
            if match is None:
                print("Unable to parse line: " + line, file=sys.stderr)

            items = match.groups()
            attributes[items[0]] = items[2]

    comment_lines = []
    for line in comment.split("\n"):
        line = line.strip()
        if len(line) > 0:
            comment_lines.append(line)

    return {"comment": comment_lines, "attributes": attributes}


def module_list(argument):
    if argument is None:
        return []
    return [x.strip() for x in argument.split(",")]


class ShowModule(rst.Directive):
    has_content = True

    option_spec = {
        'additional_modules': module_list,
    }

    def doc_compile(self, module_dir, name, import_list):
        curdir = os.getcwd()
        main_cf = "\n".join(["import " + i for i in import_list])
        try:
            project_dir = tempfile.mkdtemp()
            with open(os.path.join(project_dir, "main.cf"), "w+") as fd:
                fd.write(main_cf)

            with open(os.path.join(project_dir, "project.yml"), "w+") as fd:
                fd.write("""name: docgen
description: Project to generate docs
repo: %s
modulepath: %s
    """ % (module_dir, module_dir))

            project = Project(project_dir)
            project.use_virtual_env()
            Project.set(project)
            project.verify()
            project.load()
            _, root_ns = compiler.do_compile()

            doc_ns = [ns for ns in root_ns.children(recursive=True) if ns.get_full_name()[:len(name)] == name]

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

                    elif isinstance(type_obj, (ast.entity.Default, ast.type.ConstraintType)):
                        types["typedef"][type_name] = type_obj

                    elif isinstance(type(type_obj), PluginMeta):
                        types["plugin"][type_name] = type_obj

                    else:
                        print(type(type_obj))

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

            res_list = sorted([res for res in resource._resources.items() if res[0][:len(name)] == name], key=lambda x: x[0])
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
            os.chdir(curdir)
            shutil.rmtree(project_dir)

        return []

    def emit_handler(self, entity, name, cls):
        mod = cls.__module__[len("inmanta_plugins."):]
        lines = [".. py:class:: %s.%s" % (mod, cls.__name__), ""]
        if cls.__doc__ is not None:
            lines.extend(self.prep_docstring(cls.__doc__, 1))
            lines.append("")

        lines.append(" * Handler name ``%s``" % name)
        lines.append(" * Handler for entity :inmanta:Entity:`%s`" % entity)
        lines.append("")
        return lines

    def emit_resource(self, name, cls, opt):
        mod = cls.__module__[len("inmanta_plugins."):]
        lines = [".. py:class:: %s.%s" % (mod, cls.__name__), ""]
        if cls.__doc__ is not None:
            lines.extend(self.prep_docstring(cls.__doc__, 1))
            lines.append("")

        lines.append(" * Resource for entity :inmanta:Entity:`%s`" % name)
        lines.append(" * Id attribute ``%s``" % opt["name"])
        lines.append(" * Agent name ``%s``" % opt["agent"])

        handlers = []
        for cls in handler.Commander.get_handlers()[name].values():
            mod = cls.__module__[len("inmanta_plugins."):]
            handlers.append(":py:class:`%s.%s`" % (mod, cls.__name__))
        lines.append(" * Handlers " + ", ".join(handlers))
        lines.append("")
        return lines

    def emit_plugin(self, instance):
        lines = [".. py:function:: " + instance.get_signature(), ""]
        if instance.__class__.__function__.__doc__ is not None:
            docstring = ["   " + x for x in docstrings.prepare_docstring(instance.__class__.__function__.__doc__)]
            lines.extend(docstring)
            lines.append("")
        return lines

    def emit_heading(self, heading, char):
        """emit a sphinx heading/section  underlined by char """
        return [heading, char * len(heading), ""]

    def prep_docstring(self, docstr, indent_level=0):
        return [("   " * indent_level) + x for x in docstrings.prepare_docstring(docstr)]

    def emit_attributes(self, entity, attributes):
        all_attributes = [entity.get_attribute(name) for name in list(entity._attributes.keys())]
        relations = [x for x in all_attributes if isinstance(x, RelationAttribute)]
        others = [x for x in all_attributes if not isinstance(x, RelationAttribute)]

        defaults = entity.get_default_values()
        lines = []

        for attr in others:
            name = attr.get_name()

            attr_line = "   .. inmanta:attribute:: {1} {2}.{0}".format(attr.get_name(), attr.get_type().__str__(),
                                                                       entity.get_full_name())
            if attr.get_name() in defaults:
                attr_line += "=" + str(defaults[attr.get_name()])
            lines.append(attr_line)
            lines.append("")
            if name in attributes:
                lines.append("      " + attributes[name])

            lines.append("")

        for attr in relations:
            lines.append("   .. inmanta:relation:: {} {}.{} [{}]".format(attr.get_type(), entity.get_full_name(),
                                                                         attr.get_name(), format_multiplicity(attr)))
            if attr.comment is not None:
                lines.append("")
                lines.extend(self.prep_docstring(attr.comment, 2))

            lines.append("")
            if attr.end is not None:
                otherend = attr.end.get_entity().get_full_name() + "." + attr.end.get_name()
                lines.append("      other end: :inmanta:relation:`{0} [{1}]<{0}>`".format(otherend,
                                                                                          format_multiplicity(attr.end)))
                lines.append("")

        if len(entity.implementations) > 0:
            lines.append("   The following implementations are defined for this entity:")
            lines.append("")
            for impl in entity.implementations:
                lines.append("      * :inmanta:implementation:`%s`" % impl.get_full_name())

            lines.append("")

        if len(entity.implements) > 0:
            lines.append("   The following implements statements select implementations for this entity:")
            lines.append("")
            for impl in entity.implements:
                lines.append("      * " + ", ".join([":inmanta:implementation:`%s`" % x.get_full_name()
                                                     for x in impl.implementations]))

                constraint_str = impl.constraint.pretty_print()
                if constraint_str != "True":
                    lines.append("        constraint ``%s``" % constraint_str)

            lines.append("")

        return lines

    def emit_implementation(self, impl):
        lines = []
        lines.append(".. inmanta:implementation:: {0}::{1}".format(impl.namespace.get_full_name(), impl.name))
        if impl.comment is not None:
            lines.append("")
            lines.extend(self.prep_docstring(impl.comment, 2))
        lines.append("")

        return lines

    def emit_entity(self, entity):
        lines = []
        lines.append(".. inmanta:entity:: " + entity.get_full_name())
        lines.append("")

        if len(entity.parent_entities) > 0:
            lines.append("   Parents: %s" % ", ".join([":inmanta:entity:`%s`" % x.get_full_name()
                                                       for x in entity.parent_entities]))
        lines.append("")

        attributes = {}
        if(entity.comment):
            result = parse_docstring(entity.comment)
            lines.extend(["   " + x for x in result["comment"]])
            lines.append("")
            attributes = result["attributes"]

        lines.extend(self.emit_attributes(entity, attributes))
        lines.append("")

        # print("\n".join(lines))
        return lines

    def _get_modules(self, module_path):
        if os.path.exists(module_path) and module.Module.is_valid_module(module_path):
            mod = module.Module(None, module_path)
            return mod.get_all_submodules()
        return []

    def run(self):
        env = self.state.document.settings.env
        module_dir = env.config.inmanta_modules_dir

        args = []
        for arg in self.content:
            arg = arg.strip()
            if len(arg) > 0:
                args.append(arg)

        submodules = []
        name = args[0]
        module_path = os.path.join(module_dir, name)
        submodules.extend(self._get_modules(module_path))

        if "additional_modules" in self.options:
            for name in self.options["additional_modules"]:
                module_path = os.path.join(module_dir, name)
                submodules.extend(self._get_modules(module_path))

        lines = self.doc_compile(module_dir, args[0], submodules)

        result = ViewList()
        source_name = '<' + __name__ + '>'
        # print("\n".join(lines))
        for line in lines:
            result.append(line, source_name)

        node = nodes.section()
        node.document = self.state.document
        nested_parse_with_titles(self.state, result, node)

        return node.children



class InmantaXRefRole(XRefRole):
    pass


class InmantaObject(ObjectDescription):
    def add_target_and_index(self, name, sig, signode):
        targetname = self.objtype + '-' + name
        if targetname not in self.state.document.ids:
            signode['names'].append(targetname)
            signode['ids'].append(targetname)
            signode['first'] = (not self.names)
            self.state.document.note_explicit_target(signode)

            objects = self.env.domaindata['inmanta']['objects']
            key = (self.objtype, name)
            if key in objects:
                self.state_machine.reporter.warning('duplicate description of %s %s, ' % (self.objtype, name) +
                                                    'other instance in ' + self.env.doc2path(objects[key]), line=self.lineno)
            objects[key] = self.env.docname
        indextext = self.get_index_text(self.objtype, name)
        if indextext:
            self.indexnode['entries'].append(('single', indextext, targetname, '', None))

    def get_index_text(self, objectname, name):
        return name


class Entity(InmantaObject):
    def handle_signature(self, sig, signode):
        signode += addnodes.desc_annotation("entity", "entity ")
        signode += addnodes.desc_addname(sig, sig)
        return sig


class Attribute(InmantaObject):
    def handle_signature(self, sig, signode):
        signode += addnodes.desc_annotation("attribute", "attribute ")
        typ, name = sig.split(" ")
        default = None
        if "=" in name:
            name, default = name.split("=")

        signode += addnodes.desc_type(typ, typ + " ")

        show_name = name
        if "." in name:
            _, show_name = name.split(".")
        signode += addnodes.desc_addname(name, show_name)

        if default is not None:
            signode += addnodes.desc_type(default, "=" + default)

        return name


class Relation(InmantaObject):
    def handle_signature(self, sig, signode):
        signode += addnodes.desc_annotation("relation", "relation ")
        typ, name, mult = sig.split(" ")
        signode += addnodes.desc_type(typ, typ + " ")

        show_name = name
        if "." in name:
            _, show_name = name.split(".")
        signode += addnodes.desc_addname(name, show_name)

        signode += addnodes.desc_type(mult, " " + mult)
        return name


class Implementation(InmantaObject):
    def handle_signature(self, sig, signode):
        signode += addnodes.desc_annotation("implementation", "implementation ")
        signode += addnodes.desc_addname(sig, sig)
        return sig


class InmantaDomain(Domain):
    name = "inmanta"
    label = "inmanta"

    object_types = {
        'module': ObjType(l_('module'), 'mod', 'obj'),
        'entity': ObjType(l_('entity'), 'func', 'obj'),
        'attribute': ObjType(l_('attribute'), 'attr', 'obj'),
        'relation': ObjType(l_('relation'), 'attr', 'obj'),
        'implementation': ObjType(l_('implementation'), 'attr', 'obj'),
    }
    directives = {
        'module': Entity,
        'entity': Entity,
        'attribute': Attribute,
        'relation': Relation,
        'implementation': Implementation,
    }
    roles = {
        'entity': InmantaXRefRole(),
        'attribute': InmantaXRefRole(),
        'relation': InmantaXRefRole(),
        'implementation': InmantaXRefRole(),
    }
    initial_data = {
        'objects': {},  # fullname -> docname, objtype
    }

    def clear_doc(self, docname):
        for (typ, name), doc in list(self.data['objects'].items()):
            if doc == docname:
                del self.data['objects'][typ, name]

    def merge_domaindata(self, docnames, otherdata):
        # XXX check duplicates
        for (typ, name), doc in otherdata['objects'].items():
            if doc in docnames:
                self.data['objects'][typ, name] = doc

    def resolve_xref(self, env, fromdocname, builder, typ, target, node, contnode):
        objects = self.data['objects']
        for objtype in self.object_types.keys():
            if (objtype, target) in objects:
                return make_refnode(builder, fromdocname, objects[objtype, target], objtype + '-' + target,
                                    contnode, target + ' ' + objtype)

    def resolve_any_xref(self, env, fromdocname, builder, target,
                         node, contnode):
        objects = self.data['objects']
        results = []
        for objtype in self.object_types:
            if (objtype, target) in self.data['objects']:
                results.append(('inmanta:' + self.role_for_objtype(objtype),
                                make_refnode(builder, fromdocname, objects[objtype, target], objtype + '-' + target,
                                             contnode, target + ' ' + objtype)))
        return results

    def get_objects(self):
        for (typ, name), docname in self.data['objects'].items():
            yield name, name, typ, docname, typ + '-' + name, 1


def setup(app):
    app.add_config_value('inmanta_modules_dir', 'modules', rebuild=None)
    app.add_directive('inmanta-module', ShowModule)
    app.add_domain(InmantaDomain)
