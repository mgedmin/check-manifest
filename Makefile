.PHONY: all
all:
	@echo "Nothing to build.  Try 'make help' perhaps?"

##: Testing

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

##: Linting

.PHONY: lint
lint:                           ##: run all linters
	tox -p auto -e flake8,mypy,isort,check-manifest,check-python-versions

.PHONY: flake8
flake8:                         ##: check for style problems
	tox -e flake8

.PHONY: isort
isort:                          ##: check for incorrect import ordering
	tox -e isort

.PHONY: mypy
mypy:                           ##: check for type errors
	tox -e mypy

##: GitHub maintenance

.PHONY: update-github-branch-protection-rules

update-github-branch-protection-rules:  ##: update GitHub branch protection rules
	uv run --script .github/update_branch_protection_rules.py

##: Releasing

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
	    ! grep "rev: " README.rst | grep -qv "^$$rev_line$$" || { \
	        echo "README.rst doesn't specify $$rev_line"; \
	        echo "Please run make update-readme"; exit 1; }

.PHONY: update-readme
update-readme:
	sed -i -e 's/rev: ".*"/rev: "$(shell $(PYTHON) setup.py --version)"/' README.rst

FILE_WITH_VERSION = check_manifest.py
include release.mk
HELP_INDENT = "  "
