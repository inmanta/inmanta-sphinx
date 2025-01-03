# -*- coding: utf-8 -*-
from setuptools import setup

long_desc = '''
This contrib extension, sphinxcontrib.inmanta provides a Sphinx
domain for describing inmanta config and inmanta modules.
'''

requires = ['Sphinx>=1.5', 'click', "toml"]

setup(
    name='inmanta-sphinx',
    version='2.4.0',
    url='https://github.com/inmanta/inmanta-sphinx',
    license='ASL 2.0',
    author='Inmanta',
    author_email='code@inmanta.com',
    description='Inmanta domain for inmanta modules and config',
    long_description=long_desc,
    zip_safe=False,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Documentation',
        'Topic :: Utilities',
    ],
    platforms='any',
    packages=['sphinxcontrib.inmanta'],
    include_package_data=True,
    install_requires=requires,
    entry_points='''
        [console_scripts]
        sphinx-inmanta-api=sphinxcontrib.inmanta.api:generate_api_doc
        [pygments.lexers]
        inmanta = sphinxcontrib.inmanta.pygments_lexer:InmantaLexer
    ''',
)
