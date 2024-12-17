# Shortcuts for various dev tasks. Based on makefile from pydantic
.DEFAULT_GOAL := all
isort = isort sphinxcontrib
black = black sphinxcontrib

.PHONY: install
install:
	pip install -U setuptools pip uv
	uv pip install -U -e . -r requirements.dev.txt

.PHONY: format
format:
	$(isort)
	$(black)

.PHONY: pep8
pep8:
	flake8 sphinxcontrib

.PHONY: mypy mypy-diff mypy-save
RUN_MYPY=MYPYPATH=. python -m mypy --soft-error-limit=-1 --html-report mypy -p sphinxcontrib.inmanta

mypy:
	$(RUN_MYPY)

# compare mypy output with baseline file, show newly introduced and resolved type errors
mypy-diff:
	$(RUN_MYPY) | mypy-baseline filter

# save mypy output to baseline file
mypy-save:
	$(RUN_MYPY) | mypy-baseline sync

.PHONY: all
all: pep8 mypy

.PHONY: clean
clean:
	rm -rf `find . -name __pycache__`
	rm -f `find . -type f -name '*.py[co]' `
	rm -f `find . -type f -name '*~' `
	rm -f `find . -type f -name '.*~' `
	rm -rf .cache
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf mypy
	rm -rf coverage
	rm -rf *.egg-info
	rm -f .coverage
	rm -f .coverage.*
	rm -rf build
	find -name .env | xargs rm -rf
	python setup.py clean
	make -C docs clean
