# Inmanta sphinx extensions

This project provides two sphinx extensions for generating Inmanta related documentation. Add these
extensions to the extensions list of conf.py to enable them.

## sphinxcontrib.inmanta.config

This extension loads all the defined configuration options in the Inmanta core and uses
the embedded documentation to generate a config reference.

It adds the show-options directive and a number of config objects to sphinx. Within the show-options directive, the
 namespaces should be specified that contain the Option() definitions. This can be done in two different ways. Either
 directly in the content of the show-options directive or indirectly via the namespace-files option. Both options don't
 have to be used simultaneously Use it like this to generate documentation:

```
.. show-options::
    :namespace-files: ./config-namespaces/*.conf

	inmanta.server.config
	inmanta.agent.config
```

The namespace-files option contains a comma-separated list of files. These files contain a list of namespaces. The * operator
 can be used to match on certain files in a directory. An example of such a file is show below:

```
inmanta.deploy
inmanta.export
inmanta.compiler.config
```


## sphinxcontrib.inmanta.dsl


This exention adds objects and directives to add documentation for Inmanta dsl objects such as
entities, relations, ...


## Inmanta doc gen

To generate inmanta docs for a module, use the following

```bash
python -m sphinxcontrib.inmanta.api --module_repo folder_with_modules --module module_name  --file autodoc.rst
```

To control what is added to the module, add the following to the `pyproject.toml` of the module
The `module_filter` is a list of regexes, only submodules of which the name match one of the regexes are included
```toml
[tool.inmanta-sphinx.docgen]
module_filter = ["^module_name"] # Only include main module, no submodules
```
