.PHONY: all
all:
	@echo "Nothing to build.  Try 'make test' perhaps?"

.PHONY: test
test:                           ##: run tests
	tox -p auto

.PHONY: check
check:                          ##: run tests without skipping any
# 'make check' is defined in release.mk and here's how you can override it
define check_recipe =
	SKIP_NO_TESTS=1 tox
endef

.PHONY: coverage
coverage:                       ##: measure test coverage
	tox -e coverage

.PHONY: diff-cover
diff-cover: coverage            ##: show untested code in this branch
	coverage xml
	diff-cover coverage.xml

.PHONY: distcheck
distcheck: distcheck-self  # also release.mk will add other checks

.PHONY: distcheck-self
distcheck-self:
	tox -e check-manifest

.PHONY: releasechecklist
releasechecklist: check-readme  # also release.mk will add other checks

.PHONY: check-readme
check-readme:
	@rev_line='        rev: "'"`$(PYTHON) setup.py --version`"'"' && \
	    grep -q "^$$rev_line$$" README.rst || { \
	        echo "README.rst doesn't specify $$rev_line"; \
	        echo "Please run make update-readme"; exit 1; }

.PHONY: update-readme
update-readme:
	sed -i -e 's/rev: ".*"/rev: "$(shell $(PYTHON) setup.py --version)"/' README.rst

FILE_WITH_VERSION = check_manifest.py
include release.mk
