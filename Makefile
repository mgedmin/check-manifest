.PHONY: all
all:
	@echo "Nothing to build.  Try 'make test' perhaps?"

.PHONY: check test
test:
	tox -p auto
check:
	SKIP_NO_TESTS=1 tox

.PHONY: coverage
coverage:
	tox -e coverage

.PHONY: diff-cover
diff-cover: coverage
	coverage xml
	diff-cover coverage.xml

.PHONY: distcheck
distcheck: distcheck-self  # also release.mk will add other checks

FILE_WITH_VERSION = check_manifest.py
DISTCHECK_DIFF_OPTS = $(DISTCHECK_DIFF_DEFAULT_OPTS) -x .github
include release.mk

.PHONY: distcheck-self
distcheck-self:
	tox -e py3 --notest
	.tox/py3/bin/check-manifest
