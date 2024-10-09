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
	gh api -X PUT -H "Accept: application/vnd.github+json" \
		-H "X-GitHub-Api-Version: 2022-11-28" \
		/repos/mgedmin/check-manifest/branches/master/protection/required_status_checks/contexts \
		-f "contexts[]=check-manifest"                         \
		-f "contexts[]=check-python-versions"                  \
		-f "contexts[]=flake8"                                 \
		-f "contexts[]=isort"                                  \
		-f "contexts[]=mypy"                                   \
		-f "contexts[]=Python 3.7, bzr"                        \
		-f "contexts[]=Python 3.7, git"                        \
		-f "contexts[]=Python 3.7, hg"                         \
		-f "contexts[]=Python 3.7, svn"                        \
		-f "contexts[]=Python 3.8, bzr"                        \
		-f "contexts[]=Python 3.8, git"                        \
		-f "contexts[]=Python 3.8, hg"                         \
		-f "contexts[]=Python 3.8, svn"                        \
		-f "contexts[]=Python 3.9, bzr"                        \
		-f "contexts[]=Python 3.9, git"                        \
		-f "contexts[]=Python 3.9, hg"                         \
		-f "contexts[]=Python 3.9, svn"                        \
		-f "contexts[]=Python 3.10, bzr"                       \
		-f "contexts[]=Python 3.10, git"                       \
		-f "contexts[]=Python 3.10, hg"                        \
		-f "contexts[]=Python 3.10, svn"                       \
		-f "contexts[]=Python 3.11, bzr"                       \
		-f "contexts[]=Python 3.11, git"                       \
		-f "contexts[]=Python 3.11, hg"                        \
		-f "contexts[]=Python 3.11, svn"                       \
		-f "contexts[]=Python 3.12, bzr"                       \
		-f "contexts[]=Python 3.12, git"                       \
		-f "contexts[]=Python 3.12, hg"                        \
		-f "contexts[]=Python 3.12, svn"                       \
		-f "contexts[]=Python 3.13, bzr"                       \
		-f "contexts[]=Python 3.13, git"                       \
		-f "contexts[]=Python 3.13, hg"                        \
		-f "contexts[]=Python 3.13, svn"                       \
		-f "contexts[]=Python pypy3.10, bzr"                   \
		-f "contexts[]=Python pypy3.10, git"                   \
		-f "contexts[]=Python pypy3.10, hg"                    \
		-f "contexts[]=Python pypy3.10, svn"                   \
		-f "contexts[]=continuous-integration/appveyor/branch" \
		-f "contexts[]=continuous-integration/appveyor/pr"

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
