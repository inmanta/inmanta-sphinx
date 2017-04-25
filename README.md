Inmanta sphinx extensions
-------------------------

This project provides two sphinx extensions for generating Inmanta related documentation. Add these
extensions to the extensions list of conf.py to enable them.

sphinxcontrib.inmanta.config
============================

This extension loads all the defined configuration options in the Inmanta core and uses
the embedded documentation to generate a config reference.

It adds the show-options directive and a number of config objects to sphinx. Use it like this to
generate documentation:

```
.. show-options::

	inmanta.server.config
	inmanta.agent.config
```

sphinxcontrib.inmanta.dsl
=========================

This exention adds objects and directives to add documentation for Inmanta dsl objects such as
entities, relations, ...

