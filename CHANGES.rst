Changelog
=========


0.9 (unreleased)
----------------

* Add suggestion pattern for `.travis.yml`.

* When check-manifest -u (or -c) doesn't know how to write a rule matching a
  particular file, it now apologizes explicitly.


0.8 (2013-03-06)
----------------

* Entry point for zest.releaser_.  If you install both zest.releaser and
  check-manifest, you will be asked if you want to check your manifest during
  ``fullrelease``.

.. _zest.releaser: https://pypi.python.org/pypi/zest.releaser


0.7 (2013-03-05)
----------------

* First release available from the Python Package Index.

* Moved from https://gist.github.com/4277075
  to https://github.com/mgedmin/check-manifest

* Added README.rst, CHANGES.rst, setup.py, tox.ini (but no real tests yet),
  MANIFEST.in, and a Makefile.

* Fixed a bug in error reporting (when setup.py failed, the user would get
  `TypeError: descriptor '__init__' requires a 'exceptions.Exception' object
  but received a 'str'`).
