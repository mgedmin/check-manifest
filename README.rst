check-manifest
==============

|buildstatus|_ |appveyor|_ |coverage|_

Are you a Python developer?  Have you uploaded packages to the Python Package
Index?  Have you accidentally uploaded *broken* packages with some files
missing?  If so, check-manifest is for you.

Quick start
-----------

::

    $ pip install check-manifest

    $ cd ~/src/mygreatpackage
    $ check-manifest

You can ask the script to help you update your MANIFEST.in::

    $ check-manifest -u -v
    listing source files under version control: 6 files and directories
    building an sdist: check-manifest-0.7.tar.gz: 4 files and directories
    lists of files in version control and sdist do not match!
    missing from sdist:
      tests.py
      tox.ini
    suggested MANIFEST.in rules:
      include *.py
      include tox.ini
    updating MANIFEST.in

    $ cat MANIFEST.in
    include *.rst

    # added by check_manifest.py
    include *.py
    include tox.ini


Command-line reference
----------------------

::

    $ check-manifest --help
    usage: check-manifest [-h] [--version] [-v] [-c] [-u] [-p PYTHON]
                          [--ignore patterns]
                          [source_tree]

    Check a Python MANIFEST.in file for completeness

    positional arguments:
      source_tree           location for the source tree (default: .)

    optional arguments:
      -h, --help            show this help message and exit
      --version             show program's version number and exit
      -v, --verbose         more verbose output (default: False)
      -c, --create          create a MANIFEST.in if missing (default: False)
      -u, --update          append suggestions to MANIFEST.in (implies --create)
                            (default: False)
      -p PYTHON, --python PYTHON
                            use this Python interpreter for running setup.py sdist
                            (default: /home/mg/.venv/bin/python)
      --ignore patterns     ignore files/directories matching these comma-
                            separated patterns (default: None)
      --ignore-bad-ideas patterns
                            ignore bad idea files/directories matching these
                            comma-separated patterns (default: [])


Configuration
-------------

You can configure check-manifest to ignore certain file patterns using
a ``[tool.check-manifest]`` section in your ``pyproject.toml`` file or
a ``[check-manifest]`` section in either ``setup.cfg`` or
``tox.ini``. Examples::

    # pyproject.toml
    [tool.check-manifest]
    ignore = [".travis.yml"]

    # setup.cfg or tox.ini
    [check-manifest]
    ignore =
        .travis.yml

Note that lists are newline separated in the ``setup.cfg`` and
``tox.ini`` files.

The following options are recognized:

ignore
    A list of filename patterns that will be ignored by check-manifest.
    Use this if you want to keep files in your version control system
    that shouldn't be included in your source distributions.  The
    default ignore list is ::

        PKG-INFO
        *.egg-info
        *.egg-info/*
        setup.cfg
        .hgtags
        .hgsigs
        .hgignore
        .gitignore
        .bzrignore
        .gitattributes
        .github/*
        .travis.yml
        Jenkinsfile
        *.mo

ignore-default-rules
    If set to ``true``, your ``ignore`` patterns will replace the default
    ignore list instead of adding to it.

ignore-bad-ideas
    A list of filename patterns that will be ignored by
    check-manifest's generated files check.  Use this if you want to
    keep generated files in your version control system, even though
    it is generally a bad idea.


Version control integration
---------------------------

With `pre-commit <https://pre-commit.com>`_, check-manifest can be part of your
git-workflow. Add the following to your ``.pre-commit-config.yaml``.

.. code-block:: yaml

    repos:
    -   repo: https://github.com/mgedmin/check-manifest
        rev: "0.51"
        hooks:
        -   id: check-manifest

If you are running pre-commit without a network, you can utilize
``args: [--no-build-isolation]`` to prevent a ``pip install`` reaching out to
PyPI.  This makes ``python -m build`` ignore your ``build-system.requires``,
so you'll want to list them all in ``additional_dependencies``.

.. code-block:: yaml

    repos:
    -   repo: https://github.com/mgedmin/check-manifest
        rev: "0.51"
        hooks:
        -   id: check-manifest
            args: [--no-build-isolation]
            additional_dependencies: [setuptools, wheel, setuptools-scm]


.. |buildstatus| image:: https://github.com/mgedmin/check-manifest/actions/workflows/build.yml/badge.svg?branch=master
.. _buildstatus: https://github.com/mgedmin/check-manifest/actions

.. |appveyor| image:: https://ci.appveyor.com/api/projects/status/github/mgedmin/check-manifest?branch=master&svg=true
.. _appveyor: https://ci.appveyor.com/project/mgedmin/check-manifest

.. |coverage| image:: https://coveralls.io/repos/mgedmin/check-manifest/badge.svg?branch=master
.. _coverage: https://coveralls.io/r/mgedmin/check-manifest
