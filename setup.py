#!/usr/bin/env python
import ast
import email.utils
import os
import re

from setuptools import setup


here = os.path.dirname(__file__)

with open(os.path.join(here, 'README.rst')) as readme:
    with open(os.path.join(here, 'CHANGES.rst')) as changelog:
        long_description = readme.read() + '\n\n' + changelog.read()

metadata = {}
with open(os.path.join(here, 'check_manifest.py')) as f:
    rx = re.compile('(__version__|__author__|__url__|__licence__) = (.*)')
    for line in f:
        m = rx.match(line)
        if m:
            metadata[m.group(1)] = ast.literal_eval(m.group(2))
version = metadata['__version__']
author, author_email = email.utils.parseaddr(metadata['__author__'])
url = metadata['__url__']
licence = metadata['__licence__']

setup(
    name='check-manifest',
    version=version,
    author=author,
    author_email=author_email,
    url=url,
    description='Check MANIFEST.in in a Python source package for completeness',
    long_description=long_description,
    keywords=['distutils', 'setuptools', 'packaging', 'manifest', 'checker',
              'linter'],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
    ],
    license=licence,

    py_modules=['check_manifest'],
    zip_safe=False,
    test_suite='tests.test_suite',
    python_requires=">=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*",
    install_requires=['toml'],
    extras_require={
        'test': ['mock'],
    },
    tests_require=['mock'],
    entry_points={
        'console_scripts': [
            'check-manifest = check_manifest:main',
        ],
        'zest.releaser.prereleaser.before': [
            'check-manifest = check_manifest:zest_releaser_check',
        ],
    },
)
