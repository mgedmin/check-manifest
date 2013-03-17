check-manifest
==============

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

    $ check-manifest -u
    listing source files under version control: 6 files and directories
    building an sdist: check-manifest-0.7.tar.gz: 4 files and directories
    files in version control do not match the sdist!
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
    usage: check-manifest [-h] [-c] [-u] [source_tree]

    Check a Python MANIFEST.in file for completeness

    positional arguments:
      source_tree   location for the source tree (default: .)

    optional arguments:
      -h, --help    show this help message and exit
      -c, --create  create a MANIFEST.in if missing (default: False)
      -u, --update  append suggestions to MANIFEST.in (implies --create) (default:
                    False)


