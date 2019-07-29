# Generating documentation for all modules in a project

## Setup

1. install dependencies

```bash
pip install inmanta-sphinx inmanta
```

2. setup a basic sphinx project in the main project folder

```bash
#docs folder
mkdir docs
cd docs
#sphinx project
sphinx-quickstart --sep
#folder for module documentation
mkdir source/modules
```

3. Adapt the project to load the inmanta extensions, in the file `conf.py`, modify extensions to contain `'sphinxcontrib.inmanta.dsl'`:

```python
extensions = [ 'sphinxcontrib.inmanta.dsl']
```

5. Adapt `index.rst` to include all generated modules documents into the TOC

```reStructuredText
.. toctree::
   :maxdepth: 2
   :glob:

   modules/*
```

6. put the following script in project root

```bash
#!/bin/bash

# script to generate documentation

for lib in libs/*
do
    if [ ! -e $lib/module.yml ]
    then
        # not a module
        continue
    fi

    # get remote repo
    pushd $lib
    origin=$(git remote -v | grep -E "origin.*\(fetch\)" | tr "[:blank:]" " "  | cut -d " " -f 2)
    popd

    # get name
    name=$(basename $lib)

    # make it
    python -m sphinxcontrib.inmanta.api --module_repo $(pwd)/libs --module $name --source-repo $origin --file docs/source/modules/$name.rst

done

cd docs
make html
```

7. execute it and enjoy
