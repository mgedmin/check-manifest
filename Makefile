PYTHON = python
FILE_WITH_VERSION = check_manifest.py
FILE_WITH_CHANGELOG = CHANGES.rst

.PHONY: all
all:
	@echo "Nothing to build.  Try 'make test' perhaps?"

.PHONY: check test
test:
	detox
check:
	SKIP_NO_TESTS=1 tox

.PHONY: coverage
coverage:
	tox -e coverage

.PHONY: distcheck
distcheck: distcheck-self  # also release.mk will add other checks

include release.mk

.PHONY: distcheck-self
distcheck-self:
	$(PYTHON) check_manifest.py
