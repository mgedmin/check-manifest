import codecs
import locale
import os
import posixpath
import shutil
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import unittest
import zipfile
from contextlib import closing
from functools import partial
from io import BytesIO, StringIO
from typing import Optional
from xml.etree import ElementTree as ET

import mock

from check_manifest import rmtree


CAN_SKIP_TESTS = os.getenv('SKIP_NO_TESTS', '') == ''


try:
    codecs.lookup('oem')
except LookupError:
    HAS_OEM_CODEC = False
else:
    # Python >= 3.6 on Windows
    HAS_OEM_CODEC = True


class MockUI:

    def __init__(self, verbosity=1):
        self.verbosity = verbosity
        self.warnings = []
        self.errors = []

    def info(self, message):
        pass

    def info_begin(self, message):
        pass

    def info_cont(self, message):
        pass

    def info_end(self, message):
        pass

    def warning(self, message):
        self.warnings.append(message)

    def error(self, message):
        self.errors.append(message)


class Tests(unittest.TestCase):

    def setUp(self):
        self.ui = MockUI()

    def make_temp_dir(self):
        tmpdir = tempfile.mkdtemp(prefix='test-', suffix='-check-manifest')
        self.addCleanup(rmtree, tmpdir)
        return tmpdir

    def create_file(self, filename, contents):
        with open(filename, 'w') as f:
            f.write(contents)

    def create_zip_file(self, filename, filenames):
        with closing(zipfile.ZipFile(filename, 'w')) as zf:
            for fn in filenames:
                zf.writestr(fn, '')

    def create_tar_file(self, filename, filenames):
        with closing(tarfile.TarFile(filename, 'w')) as tf:
            for fn in filenames:
                tf.addfile(tarfile.TarInfo(fn), BytesIO())

    def test_run_success(self):
        from check_manifest import run
        self.assertEqual(run(["true"]), "")

    def test_run_failure(self):
        from check_manifest import CommandFailed, run
        with self.assertRaises(CommandFailed) as cm:
            run(["false"])
        self.assertEqual(str(cm.exception),
                         "['false'] failed (status 1):\n")

    def test_run_no_such_program(self):
        from check_manifest import Failure, run
        with self.assertRaises(Failure) as cm:
            run(["there-is-really-no-such-program"])
        # Linux says "[Errno 2] No such file or directory"
        # Windows says "[Error 2] The system cannot find the file specified"
        # but on 3.x it's "[WinErr 2] The system cannot find the file specified"
        should_start_with = "could not run ['there-is-really-no-such-program']:"
        self.assertTrue(
            str(cm.exception).startswith(should_start_with),
            '\n%r does not start with\n%r' % (str(cm.exception),
                                              should_start_with))

    def test_mkdtemp_readonly_files(self):
        from check_manifest import mkdtemp
        with mkdtemp(hint='-test-readonly') as d:
            fn = os.path.join(d, 'file.txt')
            with open(fn, 'w'):
                pass
            os.chmod(fn, 0o444)  # readonly
        assert not os.path.exists(d)

    @unittest.skipIf(sys.platform == 'win32',
                     "No POSIX-like unreadable directories on Windows")
    def test_rmtree_unreadable_directories(self):
        d = self.make_temp_dir()
        sd = os.path.join(d, 'subdir')
        os.mkdir(sd)
        os.chmod(sd, 0)  # a bad mode for a directory, oops
        # The onerror API of shutil.rmtree doesn't let us recover from
        # os.listdir() failures.
        with self.assertRaises(OSError):
            rmtree(sd)
        os.chmod(sd, 0o755)  # so we can clean up

    def test_rmtree_readonly_directories(self):
        d = self.make_temp_dir()
        sd = os.path.join(d, 'subdir')
        fn = os.path.join(sd, 'file.txt')
        os.mkdir(sd)
        open(fn, 'w').close()
        os.chmod(sd, 0o444)  # a bad mode for a directory, oops
        rmtree(sd)
        assert not os.path.exists(sd)

    def test_rmtree_readonly_directories_and_files(self):
        d = self.make_temp_dir()
        sd = os.path.join(d, 'subdir')
        fn = os.path.join(sd, 'file.txt')
        os.mkdir(sd)
        open(fn, 'w').close()
        os.chmod(fn, 0o444)  # readonly
        os.chmod(sd, 0o444)  # a bad mode for a directory, oops
        rmtree(sd)
        assert not os.path.exists(sd)

    def test_copy_files(self):
        from check_manifest import copy_files
        actions = []
        n = os.path.normpath
        with mock.patch('os.path.isdir', lambda d: d in ('b', n('/dest/dir'))):
            with mock.patch('os.makedirs',
                            lambda d: actions.append('makedirs %s' % d)):
                with mock.patch('os.mkdir',
                                lambda d: actions.append('mkdir %s' % d)):
                    with mock.patch('shutil.copy2',
                                    lambda s, d: actions.append(f'cp {s} {d}')):
                        copy_files(['a', 'b', n('c/d/e')], n('/dest/dir'))
        self.assertEqual(
            actions,
            [
                'cp a %s' % n('/dest/dir/a'),
                'mkdir %s' % n('/dest/dir/b'),
                'makedirs %s' % n('/dest/dir/c/d'),
                'cp %s %s' % (n('c/d/e'), n('/dest/dir/c/d/e')),
            ])

    def test_get_one_file_in(self):
        from check_manifest import get_one_file_in
        with mock.patch('os.listdir', lambda dir: ['a']):
            self.assertEqual(get_one_file_in(os.path.normpath('/some/dir')),
                             os.path.normpath('/some/dir/a'))

    def test_get_one_file_in_empty_directory(self):
        from check_manifest import Failure, get_one_file_in
        with mock.patch('os.listdir', lambda dir: []):
            with self.assertRaises(Failure) as cm:
                get_one_file_in('/some/dir')
            self.assertEqual(str(cm.exception),
                             "No files found in /some/dir")

    def test_get_one_file_in_too_many(self):
        from check_manifest import Failure, get_one_file_in
        with mock.patch('os.listdir', lambda dir: ['b', 'a']):
            with self.assertRaises(Failure) as cm:
                get_one_file_in('/some/dir')
            self.assertEqual(str(cm.exception),
                             "More than one file exists in /some/dir:\na\nb")

    def test_unicodify(self):
        from check_manifest import unicodify
        nonascii = "\u00E9.txt"
        self.assertEqual(unicodify(nonascii), nonascii)
        self.assertEqual(
            unicodify(nonascii.encode(locale.getpreferredencoding())),
            nonascii)

    def test_get_archive_file_list_unrecognized_archive(self):
        from check_manifest import Failure, get_archive_file_list
        with self.assertRaises(Failure) as cm:
            get_archive_file_list('/path/to/archive.rar')
        self.assertEqual(str(cm.exception),
                         'Unrecognized archive type: archive.rar')

    def test_get_archive_file_list_zip(self):
        from check_manifest import get_archive_file_list
        filename = os.path.join(self.make_temp_dir(), 'archive.zip')
        self.create_zip_file(filename, ['a', 'b/c'])
        self.assertEqual(get_archive_file_list(filename),
                         ['a', 'b/c'])

    def test_get_archive_file_list_zip_nonascii(self):
        from check_manifest import get_archive_file_list
        filename = os.path.join(self.make_temp_dir(), 'archive.zip')
        nonascii = "\u00E9.txt"
        self.create_zip_file(filename, [nonascii])
        self.assertEqual(get_archive_file_list(filename),
                         [nonascii])

    def test_get_archive_file_list_tar(self):
        from check_manifest import get_archive_file_list
        filename = os.path.join(self.make_temp_dir(), 'archive.tar')
        self.create_tar_file(filename, ['a', 'b/c'])
        self.assertEqual(get_archive_file_list(filename),
                         ['a', 'b/c'])

    def test_get_archive_file_list_tar_nonascii(self):
        from check_manifest import get_archive_file_list
        filename = os.path.join(self.make_temp_dir(), 'archive.tar')
        nonascii = "\u00E9.txt"
        self.create_tar_file(filename, [nonascii])
        self.assertEqual(get_archive_file_list(filename),
                         [nonascii])

    def test_format_list(self):
        from check_manifest import format_list
        self.assertEqual(format_list([]), "")
        self.assertEqual(format_list(['a']), "  a")
        self.assertEqual(format_list(['a', 'b']), "  a\n  b")

    def test_format_missing(self):
        from check_manifest import format_missing
        self.assertEqual(
            format_missing(set(), set(), "1st", "2nd"),
            "")
        self.assertEqual(
            format_missing({"c"}, {"a"}, "1st", "2nd"),
            "missing from 1st:\n"
            "  c\n"
            "missing from 2nd:\n"
            "  a")

    def test_strip_toplevel_name_empty_list(self):
        from check_manifest import strip_toplevel_name
        self.assertEqual(strip_toplevel_name([]), [])

    def test_strip_toplevel_name_no_common_prefix(self):
        from check_manifest import Failure, strip_toplevel_name
        self.assertRaises(Failure, strip_toplevel_name, ["a/b", "c/d"])

    def test_detect_vcs_no_vcs(self):
        from check_manifest import Failure, detect_vcs
        ui = MockUI()
        with mock.patch('check_manifest.VCS.detect', staticmethod(lambda *a: False)):
            with mock.patch('check_manifest.Git.detect', staticmethod(lambda *a: False)):
                with self.assertRaises(Failure) as cm:
                    detect_vcs(ui)
                self.assertEqual(str(cm.exception),
                                 "Couldn't find version control data"
                                 " (git/hg/bzr/svn supported)")

    def test_normalize_names(self):
        from check_manifest import normalize_names
        j = os.path.join
        self.assertEqual(normalize_names(["a", j("b", ""), j("c", "d"),
                                          j("e", "f", ""),
                                          j("g", "h", "..", "i")]),
                         ["a", "b", "c/d", "e/f", "g/i"])

    def test_canonical_file_list(self):
        from check_manifest import canonical_file_list
        j = os.path.join
        self.assertEqual(
            canonical_file_list(['b', 'a', 'c', j('c', 'd'), j('e', 'f'),
                                 'g', j('g', 'h', 'i', 'j')]),
            ['a', 'b', 'c/d', 'e/f', 'g/h/i/j'])

    def test_file_matches(self):
        from check_manifest import file_matches
        patterns = ['setup.cfg', '*.egg-info', '*.egg-info/*']
        self.assertFalse(file_matches('setup.py', patterns))
        self.assertTrue(file_matches('setup.cfg', patterns))
        self.assertTrue(file_matches('src/zope.foo.egg-info', patterns))
        self.assertTrue(file_matches('src/zope.foo.egg-info/SOURCES.txt',
                                     patterns))

    def test_strip_sdist_extras(self):
        from check_manifest import (
            IgnoreList,
            canonical_file_list,
            strip_sdist_extras,
        )
        filelist = canonical_file_list([
            '.github',
            '.github/ISSUE_TEMPLATE',
            '.github/ISSUE_TEMPLATE/bug_report.md',
            '.gitignore',
            '.travis.yml',
            'setup.py',
            'setup.cfg',
            'README.txt',
            'src',
            'src/.gitignore',
            'src/zope',
            'src/zope/__init__.py',
            'src/zope/foo',
            'src/zope/foo/__init__.py',
            'src/zope/foo/language.po',
            'src/zope/foo/language.mo',
            'src/zope.foo.egg-info',
            'src/zope.foo.egg-info/SOURCES.txt',
        ])
        expected = canonical_file_list([
            'setup.py',
            'README.txt',
            'src',
            'src/zope',
            'src/zope/__init__.py',
            'src/zope/foo',
            'src/zope/foo/__init__.py',
            'src/zope/foo/language.po',
        ])
        ignore = IgnoreList.default()
        self.assertEqual(strip_sdist_extras(ignore, filelist), expected)

    def test_strip_sdist_extras_with_manifest(self):
        from check_manifest import (
            IgnoreList,
            _get_ignore_from_manifest_lines,
            canonical_file_list,
            strip_sdist_extras,
        )
        manifest_in = textwrap.dedent("""
            graft src
            exclude *.cfg
            global-exclude *.mo
            prune src/dump
            recursive-exclude src/zope *.sh
        """)
        filelist = canonical_file_list([
            '.github/ISSUE_TEMPLATE/bug_report.md',
            '.gitignore',
            'setup.py',
            'setup.cfg',
            'MANIFEST.in',
            'README.txt',
            'src',
            'src/helper.sh',
            'src/dump',
            'src/dump/__init__.py',
            'src/zope',
            'src/zope/__init__.py',
            'src/zope/zopehelper.sh',
            'src/zope/foo',
            'src/zope/foo/__init__.py',
            'src/zope/foo/language.po',
            'src/zope/foo/language.mo',
            'src/zope/foo/config.cfg',
            'src/zope/foo/foohelper.sh',
            'src/zope.foo.egg-info',
            'src/zope.foo.egg-info/SOURCES.txt',
        ])
        expected = canonical_file_list([
            'setup.py',
            'MANIFEST.in',
            'README.txt',
            'src',
            'src/helper.sh',
            'src/zope',
            'src/zope/__init__.py',
            'src/zope/foo',
            'src/zope/foo/__init__.py',
            'src/zope/foo/language.po',
            'src/zope/foo/config.cfg',
        ])
        ignore = IgnoreList.default()
        ignore += _get_ignore_from_manifest_lines(manifest_in.splitlines(), self.ui)
        result = strip_sdist_extras(ignore, filelist)
        self.assertEqual(result, expected)

    def test_find_bad_ideas(self):
        from check_manifest import find_bad_ideas
        filelist = [
            '.gitignore',
            'setup.py',
            'setup.cfg',
            'README.txt',
            'src',
            'src/zope',
            'src/zope/__init__.py',
            'src/zope/foo',
            'src/zope/foo/__init__.py',
            'src/zope/foo/language.po',
            'src/zope/foo/language.mo',
            'src/zope.foo.egg-info',
            'src/zope.foo.egg-info/SOURCES.txt',
        ]
        expected = [
            'src/zope/foo/language.mo',
            'src/zope.foo.egg-info',
        ]
        self.assertEqual(find_bad_ideas(filelist), expected)

    def test_find_suggestions(self):
        from check_manifest import find_suggestions
        self.assertEqual(find_suggestions(['buildout.cfg']),
                         (['include buildout.cfg'], []))
        self.assertEqual(find_suggestions(['unknown.file~']),
                         ([], ['unknown.file~']))
        self.assertEqual(find_suggestions(['README.txt', 'CHANGES.txt']),
                         (['include *.txt'], []))
        filelist = [
            'docs/index.rst',
            'docs/image.png',
            'docs/Makefile',
            'docs/unknown-file',
            'src/etc/blah/blah/Makefile',
        ]
        expected_rules = [
            'recursive-include docs *.png',
            'recursive-include docs *.rst',
            'recursive-include docs Makefile',
            'recursive-include src Makefile',
        ]
        expected_unknowns = ['docs/unknown-file']
        self.assertEqual(find_suggestions(filelist),
                         (expected_rules, expected_unknowns))

    def test_find_suggestions_generic_fallback_rules(self):
        from check_manifest import find_suggestions
        self.assertEqual(find_suggestions(['Changelog']),
                         (['include Changelog'], []))
        self.assertEqual(find_suggestions(['id-lang.map']),
                         (['include *.map'], []))
        self.assertEqual(find_suggestions(['src/id-lang.map']),
                         (['recursive-include src *.map'], []))

    def test_is_package(self):
        from check_manifest import is_package
        j = os.path.join
        exists = {j('a', 'setup.py'), j('c', 'pyproject.toml')}
        with mock.patch('os.path.exists', lambda fn: fn in exists):
            self.assertTrue(is_package('a'))
            self.assertFalse(is_package('b'))
            self.assertTrue(is_package('c'))

    def test_extract_version_from_filename(self):
        from check_manifest import extract_version_from_filename as e
        self.assertEqual(e('dist/foo_bar-1.2.3.dev4+g12345.zip'), '1.2.3.dev4+g12345')
        self.assertEqual(e('dist/foo_bar-1.2.3.dev4+g12345.tar.gz'), '1.2.3.dev4+g12345')
        self.assertEqual(e('dist/foo-bar-1.2.3.dev4+g12345.tar.gz'), '1.2.3.dev4+g12345')

    def test_get_ignore_from_manifest_lines(self):
        from check_manifest import IgnoreList, _get_ignore_from_manifest_lines
        parse = partial(_get_ignore_from_manifest_lines, ui=self.ui)
        self.assertEqual(parse([]),
                         IgnoreList())
        self.assertEqual(parse(['', ' ']),
                         IgnoreList())
        self.assertEqual(parse(['exclude *.cfg']),
                         IgnoreList().exclude('*.cfg'))
        self.assertEqual(parse(['exclude          *.cfg']),
                         IgnoreList().exclude('*.cfg'))
        self.assertEqual(parse(['\texclude\t*.cfg foo.*   bar.txt']),
                         IgnoreList().exclude('*.cfg', 'foo.*', 'bar.txt'))
        self.assertEqual(parse(['exclude some/directory/*.cfg']),
                         IgnoreList().exclude('some/directory/*.cfg'))
        self.assertEqual(parse(['include *.cfg']),
                         IgnoreList())
        self.assertEqual(parse(['global-exclude *.pyc']),
                         IgnoreList().global_exclude('*.pyc'))
        self.assertEqual(parse(['global-exclude *.pyc *.sh']),
                         IgnoreList().global_exclude('*.pyc', '*.sh'))
        self.assertEqual(parse(['recursive-exclude dir *.pyc']),
                         IgnoreList().recursive_exclude('dir', '*.pyc'))
        self.assertEqual(parse(['recursive-exclude dir *.pyc foo*.sh']),
                         IgnoreList().recursive_exclude('dir', '*.pyc', 'foo*.sh'))
        self.assertEqual(parse(['recursive-exclude dir nopattern.xml']),
                         IgnoreList().recursive_exclude('dir', 'nopattern.xml'))
        # We should not fail when a recursive-exclude line is wrong:
        self.assertEqual(parse(['recursive-exclude dirwithoutpattern']),
                         IgnoreList())
        self.assertEqual(parse(['prune dir']),
                         IgnoreList().prune('dir'))
        # And a mongo test case of everything at the end
        text = textwrap.dedent("""
            exclude *.02
            exclude *.03 04.*   bar.txt
            exclude          *.05
            exclude some/directory/*.cfg
            global-exclude *.10 *.11
            global-exclude *.12
            include *.20
            prune 30
            recursive-exclude    40      *.41
            recursive-exclude 42 *.43 44.*
        """).splitlines()
        self.assertEqual(
            parse(text),
            IgnoreList()
            .exclude('*.02', '*.03', '04.*', 'bar.txt', '*.05', 'some/directory/*.cfg')
            .global_exclude('*.10', '*.11', '*.12')
            .prune('30')
            .recursive_exclude('40', '*.41')
            .recursive_exclude('42', '*.43', '44.*')
        )

    def test_get_ignore_from_manifest_lines_warns(self):
        from check_manifest import IgnoreList, _get_ignore_from_manifest_lines
        parse = partial(_get_ignore_from_manifest_lines, ui=self.ui)
        text = textwrap.dedent("""
            graft a/
            recursive-include /b *.txt
        """).splitlines()
        self.assertEqual(parse(text), IgnoreList())
        self.assertEqual(self.ui.warnings, [
            'ERROR: Trailing slashes are not allowed in MANIFEST.in on Windows: a/',
            'ERROR: Leading slashes are not allowed in MANIFEST.in on Windows: /b',
        ])

    def test_get_ignore_from_manifest(self):
        from check_manifest import IgnoreList, _get_ignore_from_manifest
        filename = os.path.join(self.make_temp_dir(), 'MANIFEST.in')
        self.create_file(filename, textwrap.dedent('''
           exclude \\
              # yes, this is allowed!
              test.dat

           # https://github.com/mgedmin/check-manifest/issues/66
           # docs/ folder
        '''))
        ui = MockUI()
        self.assertEqual(_get_ignore_from_manifest(filename, ui),
                         IgnoreList().exclude('test.dat'))
        self.assertEqual(ui.warnings, [])

    def test_get_ignore_from_manifest_warnings(self):
        from check_manifest import IgnoreList, _get_ignore_from_manifest
        filename = os.path.join(self.make_temp_dir(), 'MANIFEST.in')
        self.create_file(filename, textwrap.dedent('''
           # this is bad: a file should not end with a backslash
           exclude test.dat \\
        '''))
        ui = MockUI()
        self.assertEqual(_get_ignore_from_manifest(filename, ui),
                         IgnoreList().exclude('test.dat'))
        self.assertEqual(ui.warnings, [
            "%s, line 2: continuation line immediately precedes end-of-file" % filename,
        ])

    def test_should_use_pep517_no_pyproject_toml(self):
        from check_manifest import cd, should_use_pep_517
        src_dir = self.make_temp_dir()
        with cd(src_dir):
            self.assertFalse(should_use_pep_517())

    def test_should_use_pep517_no_build_system(self):
        from check_manifest import cd, should_use_pep_517
        src_dir = self.make_temp_dir()
        filename = os.path.join(src_dir, 'pyproject.toml')
        self.create_file(filename, textwrap.dedent('''
            [tool.check-manifest]
        '''))
        with cd(src_dir):
            self.assertFalse(should_use_pep_517())

    def test_should_use_pep517_no_build_backend(self):
        from check_manifest import cd, should_use_pep_517
        src_dir = self.make_temp_dir()
        filename = os.path.join(src_dir, 'pyproject.toml')
        self.create_file(filename, textwrap.dedent('''
            [build-system]
            requires = [
                "setuptools >= 40.6.0",
                "wheel",
            ]
        '''))
        with cd(src_dir):
            self.assertFalse(should_use_pep_517())

    def test_should_use_pep517_yes_please(self):
        from check_manifest import cd, should_use_pep_517
        src_dir = self.make_temp_dir()
        filename = os.path.join(src_dir, 'pyproject.toml')
        self.create_file(filename, textwrap.dedent('''
            [build-system]
            requires = [
                "setuptools >= 40.6.0",
                "wheel",
            ]
            build-backend = "setuptools.build_meta"
        '''))
        with cd(src_dir):
            self.assertTrue(should_use_pep_517())

    def _test_build_sdist_pep517(self, build_isolation):
        from check_manifest import build_sdist, cd, get_one_file_in
        src_dir = self.make_temp_dir()
        filename = os.path.join(src_dir, 'pyproject.toml')
        self.create_file(filename, textwrap.dedent('''
            [build-system]
            requires = [
                "setuptools >= 40.6.0",
                "wheel",
            ]
            build-backend = "setuptools.build_meta"
        '''))
        out_dir = self.make_temp_dir()
        python = os.path.abspath(sys.executable)
        with cd(src_dir):
            build_sdist(out_dir, python=python, build_isolation=build_isolation)
        self.assertTrue(get_one_file_in(out_dir))

    def test_build_sdist_pep517_isolated(self):
        self._test_build_sdist_pep517(build_isolation=True)

    def test_build_sdist_pep517_no_isolation(self):
        self._test_build_sdist_pep517(build_isolation=False)


class TestConfiguration(unittest.TestCase):

    def setUp(self):
        self.oldpwd = os.getcwd()
        self.tmpdir = tempfile.mkdtemp(prefix='test-', suffix='-check-manifest')
        os.chdir(self.tmpdir)
        self.ui = MockUI()

    def tearDown(self):
        os.chdir(self.oldpwd)
        rmtree(self.tmpdir)

    def test_read_config_no_config(self):
        import check_manifest
        ignore, ignore_bad_ideas = check_manifest.read_config()
        self.assertEqual(ignore, check_manifest.IgnoreList.default())

    def test_read_setup_config_no_section(self):
        import check_manifest
        with open('setup.cfg', 'w') as f:
            f.write('[pep8]\nignore =\n')
        ignore, ignore_bad_ideas = check_manifest.read_config()
        self.assertEqual(ignore, check_manifest.IgnoreList.default())

    def test_read_pyproject_config_no_section(self):
        import check_manifest
        with open('pyproject.toml', 'w') as f:
            f.write('[tool.pep8]\nignore = []\n')
        ignore, ignore_bad_ideas = check_manifest.read_config()
        self.assertEqual(ignore, check_manifest.IgnoreList.default())

    def test_read_setup_config_no_option(self):
        import check_manifest
        with open('setup.cfg', 'w') as f:
            f.write('[check-manifest]\n')
        ignore, ignore_bad_ideas = check_manifest.read_config()
        self.assertEqual(ignore, check_manifest.IgnoreList.default())

    def test_read_pyproject_config_no_option(self):
        import check_manifest
        with open('pyproject.toml', 'w') as f:
            f.write('[tool.check-manifest]\n')
        ignore, ignore_bad_ideas = check_manifest.read_config()
        self.assertEqual(ignore, check_manifest.IgnoreList.default())

    def test_read_setup_config_extra_ignores(self):
        import check_manifest
        with open('setup.cfg', 'w') as f:
            f.write('[check-manifest]\nignore = foo\n  bar*\n')
        ignore, ignore_bad_ideas = check_manifest.read_config()
        expected = check_manifest.IgnoreList.default().global_exclude('foo', 'bar*')
        self.assertEqual(ignore, expected)

    def test_read_pyproject_config_extra_ignores(self):
        import check_manifest
        with open('pyproject.toml', 'w') as f:
            f.write('[tool.check-manifest]\nignore = ["foo", "bar*"]\n')
        ignore, ignore_bad_ideas = check_manifest.read_config()
        expected = check_manifest.IgnoreList.default().global_exclude('foo', 'bar*')
        self.assertEqual(ignore, expected)

    def test_read_setup_config_override_ignores(self):
        import check_manifest
        with open('setup.cfg', 'w') as f:
            f.write('[check-manifest]\nignore = foo\n\n  bar\n')
            f.write('ignore-default-rules = yes\n')
        ignore, ignore_bad_ideas = check_manifest.read_config()
        expected = check_manifest.IgnoreList().global_exclude('foo', 'bar')
        self.assertEqual(ignore, expected)

    def test_read_pyproject_config_override_ignores(self):
        import check_manifest
        with open('pyproject.toml', 'w') as f:
            f.write('[tool.check-manifest]\nignore = ["foo", "bar"]\n')
            f.write('ignore-default-rules = true\n')
        ignore, ignore_bad_ideas = check_manifest.read_config()
        expected = check_manifest.IgnoreList().global_exclude('foo', 'bar')
        self.assertEqual(ignore, expected)

    def test_read_setup_config_ignore_bad_ideas(self):
        import check_manifest
        with open('setup.cfg', 'w') as f:
            f.write('[check-manifest]\n'
                    'ignore-bad-ideas = \n'
                    '  foo\n'
                    '  bar*\n')
        ignore, ignore_bad_ideas = check_manifest.read_config()
        expected = check_manifest.IgnoreList().global_exclude('foo', 'bar*')
        self.assertEqual(ignore_bad_ideas, expected)

    def test_read_pyproject_config_ignore_bad_ideas(self):
        import check_manifest
        with open('pyproject.toml', 'w') as f:
            f.write('[tool.check-manifest]\n'
                    'ignore-bad-ideas = ["foo", "bar*"]\n')
        ignore, ignore_bad_ideas = check_manifest.read_config()
        expected = check_manifest.IgnoreList().global_exclude('foo', 'bar*')
        self.assertEqual(ignore_bad_ideas, expected)

    def test_read_manifest_no_manifest(self):
        import check_manifest
        ignore = check_manifest.read_manifest(self.ui)
        self.assertEqual(ignore, check_manifest.IgnoreList())

    def test_read_manifest(self):
        import check_manifest
        from check_manifest import IgnoreList
        with open('MANIFEST.in', 'w') as f:
            f.write('exclude *.gif\n')
            f.write('global-exclude *.png\n')
        ignore = check_manifest.read_manifest(self.ui)
        self.assertEqual(ignore, IgnoreList().exclude('*.gif').global_exclude('*.png'))


class TestMain(unittest.TestCase):

    def setUp(self):
        self._cm_patcher = mock.patch('check_manifest.check_manifest')
        self._check_manifest = self._cm_patcher.start()
        self._se_patcher = mock.patch('sys.exit')
        self._sys_exit = self._se_patcher.start()
        self.ui = MockUI()
        self._ui_patcher = mock.patch('check_manifest.UI', self._make_ui)
        self._ui_patcher.start()
        self._orig_sys_argv = sys.argv
        sys.argv = ['check-manifest']

    def tearDown(self):
        sys.argv = self._orig_sys_argv
        self._se_patcher.stop()
        self._cm_patcher.stop()
        self._ui_patcher.stop()

    def _make_ui(self, verbosity):
        self.ui.verbosity = verbosity
        return self.ui

    def test(self):
        from check_manifest import main
        sys.argv.append('-v')
        main()

    def test_exit_code_1_on_error(self):
        from check_manifest import main
        self._check_manifest.return_value = False
        main()
        self._sys_exit.assert_called_with(1)

    def test_exit_code_2_on_failure(self):
        from check_manifest import Failure, main
        self._check_manifest.side_effect = Failure('msg')
        main()
        self.assertEqual(self.ui.errors, ['msg'])
        self._sys_exit.assert_called_with(2)

    def test_extra_ignore_args(self):
        import check_manifest
        sys.argv.append('--ignore=x,y,z*')
        check_manifest.main()
        ignore = check_manifest.IgnoreList().global_exclude('x', 'y', 'z*')
        self.assertEqual(self._check_manifest.call_args.kwargs['extra_ignore'],
                         ignore)

    def test_ignore_bad_ideas_args(self):
        import check_manifest
        sys.argv.append('--ignore-bad-ideas=x,y,z*')
        check_manifest.main()
        ignore = check_manifest.IgnoreList().global_exclude('x', 'y', 'z*')
        self.assertEqual(self._check_manifest.call_args.kwargs['extra_ignore_bad_ideas'],
                         ignore)

    def test_verbose_arg(self):
        import check_manifest
        sys.argv.append('--verbose')
        check_manifest.main()
        self.assertEqual(self.ui.verbosity, 2)

    def test_quiet_arg(self):
        import check_manifest
        sys.argv.append('--quiet')
        check_manifest.main()
        self.assertEqual(self.ui.verbosity, 0)

    def test_verbose_and_quiet_arg(self):
        import check_manifest
        sys.argv.append('--verbose')
        sys.argv.append('--quiet')
        check_manifest.main()
        # the two arguments cancel each other out:
        # 1 (default verbosity) + 1 - 1 = 1.
        self.assertEqual(self.ui.verbosity, 1)


class TestZestIntegration(unittest.TestCase):

    def setUp(self):
        sys.modules['zest'] = mock.Mock()
        sys.modules['zest.releaser'] = mock.Mock()
        sys.modules['zest.releaser.utils'] = mock.Mock()
        self.ask = sys.modules['zest.releaser.utils'].ask
        self.ui = MockUI()
        self._ui_patcher = mock.patch('check_manifest.UI', return_value=self.ui)
        self._ui_patcher.start()

    def tearDown(self):
        self._ui_patcher.stop()
        del sys.modules['zest.releaser.utils']
        del sys.modules['zest.releaser']
        del sys.modules['zest']

    @mock.patch('check_manifest.is_package', lambda d: False)
    @mock.patch('check_manifest.check_manifest')
    def test_zest_releaser_check_not_a_package(self, check_manifest):
        from check_manifest import zest_releaser_check
        zest_releaser_check(dict(workingdir='.'))
        check_manifest.assert_not_called()

    @mock.patch('check_manifest.is_package', lambda d: True)
    @mock.patch('check_manifest.check_manifest')
    def test_zest_releaser_check_user_disagrees(self, check_manifest):
        from check_manifest import zest_releaser_check
        self.ask.return_value = False
        zest_releaser_check(dict(workingdir='.'))
        check_manifest.assert_not_called()

    @mock.patch('check_manifest.is_package', lambda d: True)
    @mock.patch('sys.exit')
    @mock.patch('check_manifest.check_manifest')
    def test_zest_releaser_check_all_okay(self, check_manifest, sys_exit):
        from check_manifest import zest_releaser_check
        self.ask.return_value = True
        check_manifest.return_value = True
        zest_releaser_check(dict(workingdir='.'))
        sys_exit.assert_not_called()

    @mock.patch('check_manifest.is_package', lambda d: True)
    @mock.patch('sys.exit')
    @mock.patch('check_manifest.check_manifest')
    def test_zest_releaser_check_error_user_aborts(self, check_manifest,
                                                   sys_exit):
        from check_manifest import zest_releaser_check
        self.ask.side_effect = [True, False]
        check_manifest.return_value = False
        zest_releaser_check(dict(workingdir='.'))
        sys_exit.assert_called_with(1)

    @mock.patch('check_manifest.is_package', lambda d: True)
    @mock.patch('sys.exit')
    @mock.patch('check_manifest.check_manifest')
    def test_zest_releaser_check_error_user_plods_on(self, check_manifest,
                                                     sys_exit):
        from check_manifest import zest_releaser_check
        self.ask.side_effect = [True, True]
        check_manifest.return_value = False
        zest_releaser_check(dict(workingdir='.'))
        sys_exit.assert_not_called()

    @mock.patch('check_manifest.is_package', lambda d: True)
    @mock.patch('sys.exit')
    @mock.patch('check_manifest.check_manifest')
    def test_zest_releaser_check_failure_user_aborts(self, check_manifest,
                                                     sys_exit):
        from check_manifest import Failure, zest_releaser_check
        self.ask.side_effect = [True, False]
        check_manifest.side_effect = Failure('msg')
        zest_releaser_check(dict(workingdir='.'))
        self.assertEqual(self.ui.errors, ['msg'])
        sys_exit.assert_called_with(2)

    @mock.patch('check_manifest.is_package', lambda d: True)
    @mock.patch('sys.exit')
    @mock.patch('check_manifest.check_manifest')
    def test_zest_releaser_check_failure_user_plods_on(self, check_manifest,
                                                       sys_exit):
        from check_manifest import Failure, zest_releaser_check
        self.ask.side_effect = [True, True]
        check_manifest.side_effect = Failure('msg')
        zest_releaser_check(dict(workingdir='.'))
        self.assertEqual(self.ui.errors, ['msg'])
        sys_exit.assert_not_called()


class VCSHelper:

    # override in subclasses
    command = None  # type: Optional[str]

    def is_installed(self):
        try:
            p = subprocess.Popen([self.command, '--version'],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            stdout, stderr = p.communicate()
            rc = p.wait()
            return (rc == 0)
        except OSError:
            return False

    def _run(self, *command):
        # Windows doesn't like Unicode arguments to subprocess.Popen(), on Py2:
        # https://github.com/mgedmin/check-manifest/issues/23#issuecomment-33933031
        if str is bytes:
            command = [s.encode(locale.getpreferredencoding()) for s in command]
        print('$', ' '.join(command))
        p = subprocess.Popen(command, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
        stdout, stderr = p.communicate()
        rc = p.wait()
        if stdout:
            print(
                stdout if isinstance(stdout, str) else
                stdout.decode('ascii', 'backslashreplace')
            )
        if rc:
            raise subprocess.CalledProcessError(rc, command[0], output=stdout)


class VCSMixin:

    def setUp(self):
        if not self.vcs.is_installed() and CAN_SKIP_TESTS:
            self.skipTest("%s is not installed" % self.vcs.command)
        self.tmpdir = tempfile.mkdtemp(prefix='test-', suffix='-check-manifest')
        self.olddir = os.getcwd()
        os.chdir(self.tmpdir)
        self.ui = MockUI()

    def tearDown(self):
        os.chdir(self.olddir)
        rmtree(self.tmpdir)

    def _create_file(self, filename):
        assert not os.path.isabs(filename)
        basedir = os.path.dirname(filename)
        if basedir and not os.path.isdir(basedir):
            os.makedirs(basedir)
        open(filename, 'w').close()

    def _create_files(self, filenames):
        for filename in filenames:
            self._create_file(filename)

    def _init_vcs(self):
        self.vcs._init_vcs()

    def _add_to_vcs(self, filenames):
        self.vcs._add_to_vcs(filenames)

    def _commit(self):
        self.vcs._commit()

    def _create_and_add_to_vcs(self, filenames):
        self._create_files(filenames)
        self._add_to_vcs(filenames)

    def test_get_vcs_files(self):
        from check_manifest import get_vcs_files
        self._init_vcs()
        self._create_and_add_to_vcs(['a.txt', 'b/b.txt', 'b/c/d.txt'])
        self._commit()
        self._create_files(['b/x.txt', 'd/d.txt', 'i.txt'])
        self.assertEqual(get_vcs_files(self.ui),
                         ['a.txt', 'b/b.txt', 'b/c/d.txt'])

    def test_get_vcs_files_added_but_uncommitted(self):
        from check_manifest import get_vcs_files
        self._init_vcs()
        self._create_and_add_to_vcs(['a.txt', 'b/b.txt', 'b/c/d.txt'])
        self._create_files(['b/x.txt', 'd/d.txt', 'i.txt'])
        self.assertEqual(get_vcs_files(self.ui),
                         ['a.txt', 'b/b.txt', 'b/c/d.txt'])

    def test_get_vcs_files_deleted_but_not_removed(self):
        if self.vcs.command == 'bzr':
            self.skipTest("this cosmetic feature is not supported with bzr")
            # see the longer explanation in test_missing_source_files
        from check_manifest import get_vcs_files
        self._init_vcs()
        self._create_and_add_to_vcs(['a.txt'])
        self._commit()
        os.unlink('a.txt')
        self.assertEqual(get_vcs_files(self.ui), ['a.txt'])

    def test_get_vcs_files_in_a_subdir(self):
        from check_manifest import get_vcs_files
        self._init_vcs()
        self._create_and_add_to_vcs(['a.txt', 'b/b.txt', 'b/c/d.txt'])
        self._commit()
        self._create_files(['b/x.txt', 'd/d.txt', 'i.txt'])
        os.chdir('b')
        self.assertEqual(get_vcs_files(self.ui), ['b.txt', 'c/d.txt'])

    def test_get_vcs_files_nonascii_filenames(self):
        # This test will fail if your locale is incapable of expressing
        # "eacute".  UTF-8 or Latin-1 should work.
        from check_manifest import get_vcs_files
        self._init_vcs()
        filename = "\u00E9.txt"
        self._create_and_add_to_vcs([filename])
        self.assertEqual(get_vcs_files(self.ui), [filename])

    def test_get_vcs_files_empty(self):
        from check_manifest import get_vcs_files
        self._init_vcs()
        self.assertEqual(get_vcs_files(self.ui), [])


class GitHelper(VCSHelper):

    command = 'git'

    def _init_vcs(self):
        self._run('git', 'init')
        self._run('git', 'config', 'user.name', 'Unit Test')
        self._run('git', 'config', 'user.email', 'test@example.com')

    def _add_to_vcs(self, filenames):
        # Note that we use --force to prevent errors when we want to
        # add foo.egg-info and the user running the tests has
        # '*.egg-info' in her global .gitignore file.
        self._run('git', 'add', '--force', '--', *filenames)

    def _commit(self):
        self._run('git', 'commit', '-m', 'Initial')


class TestGit(VCSMixin, unittest.TestCase):
    vcs = GitHelper()

    def _init_repo_with_files(self, dirname, filenames):
        os.mkdir(dirname)
        os.chdir(dirname)
        self._init_vcs()
        self._create_and_add_to_vcs(filenames)
        self._commit()
        os.chdir(self.tmpdir)

    def _add_submodule(self, repo, subdir, subrepo):
        os.chdir(repo)
        self.vcs._run('git', 'submodule', 'add', subrepo, subdir)
        self._commit()
        os.chdir(self.tmpdir)

    def test_detect_git_submodule(self):
        from check_manifest import Failure, detect_vcs
        with self.assertRaises(Failure) as cm:
            detect_vcs(self.ui)
        self.assertEqual(str(cm.exception),
                         "Couldn't find version control data"
                         " (git/hg/bzr/svn supported)")
        # now create a .git file like in a submodule
        open(os.path.join(self.tmpdir, '.git'), 'w').close()
        self.assertEqual(detect_vcs(self.ui).metadata_name, '.git')

    def test_get_versioned_files_with_git_submodules(self):
        from check_manifest import get_vcs_files
        self._init_repo_with_files('repo1', ['file1', 'file2'])
        self._init_repo_with_files('repo2', ['file3'])
        self._init_repo_with_files('repo3', ['file4'])
        self._add_submodule('repo2', 'sub3', '../repo3')
        self._init_repo_with_files('main', ['file5', 'subdir/file6'])
        self._add_submodule('main', 'sub1', '../repo1')
        self._add_submodule('main', 'subdir/sub2', '../repo2')
        os.chdir('main')
        self.vcs._run('git', 'submodule', 'update', '--init', '--recursive')
        self.assertEqual(
            get_vcs_files(self.ui),
            [
                '.gitmodules',
                'file5',
                'sub1/file1',
                'sub1/file2',
                'subdir/file6',
                'subdir/sub2/.gitmodules',
                'subdir/sub2/file3',
                'subdir/sub2/sub3/file4',
            ])

    def test_get_versioned_files_with_git_submodules_with_git_index_file_set(self):
        with mock.patch.dict(os.environ, {"GIT_INDEX_FILE": ".git/index"}):
            self.test_get_versioned_files_with_git_submodules()


class BzrHelper(VCSHelper):

    command = 'bzr'

    def _init_vcs(self):
        self._run('bzr', 'init')
        self._run('bzr', 'whoami', '--branch', 'Unit Test <test@example.com>')

    def _add_to_vcs(self, filenames):
        self._run('bzr', 'add', '--', *filenames)

    def _commit(self):
        self._run('bzr', 'commit', '-m', 'Initial')


class TestBzr(VCSMixin, unittest.TestCase):
    vcs = BzrHelper()


@unittest.skipIf(HAS_OEM_CODEC,
                 "Python 3.6 lets us use 'oem' codec instead of guessing")
class TestBzrTerminalCharsetDetectionOnOldPythons(unittest.TestCase):

    @mock.patch('sys.stdin')
    @mock.patch('sys.stdout')
    def test_terminal_encoding_not_known(self, mock_stdout, mock_stdin):
        from check_manifest import Bazaar
        mock_stdout.encoding = None
        mock_stdin.encoding = None
        self.assertEqual(Bazaar._get_terminal_encoding(), None)

    @mock.patch('sys.stdout')
    def test_terminal_encoding_stdout_known(self, mock_stdout):
        from check_manifest import Bazaar
        mock_stdout.encoding = 'UTF-8'
        self.assertEqual(Bazaar._get_terminal_encoding(), 'UTF-8')

    @mock.patch('sys.stdin')
    @mock.patch('sys.stdout')
    def test_terminal_encoding_stdin_known(self, mock_stdout, mock_stdin):
        from check_manifest import Bazaar
        mock_stdout.encoding = None
        mock_stdin.encoding = 'UTF-8'
        self.assertEqual(Bazaar._get_terminal_encoding(), 'UTF-8')

    @mock.patch('sys.stdout')
    def test_terminal_encoding_cp0(self, mock_stdout):
        from check_manifest import Bazaar
        mock_stdout.encoding = 'cp0'
        self.assertEqual(Bazaar._get_terminal_encoding(), None)


@unittest.skipIf(not HAS_OEM_CODEC,
                 "'oem' codec not available on Python before 3.6")
class TestBzrTerminalCharsetDetectionOnNewPythons(unittest.TestCase):

    def test_terminal_encoding_cp0(self):
        from check_manifest import Bazaar
        self.assertEqual(Bazaar._get_terminal_encoding(), "oem")


class HgHelper(VCSHelper):

    command = 'hg'

    def _init_vcs(self):
        self._run('hg', 'init')
        with open('.hg/hgrc', 'a') as f:
            f.write('\n[ui]\nusername = Unit Test <test@example.com\n')

    def _add_to_vcs(self, filenames):
        self._run('hg', 'add', '--', *filenames)

    def _commit(self):
        self._run('hg', 'commit', '-m', 'Initial')


class TestHg(VCSMixin, unittest.TestCase):
    vcs = HgHelper()


class SvnHelper(VCSHelper):

    command = 'svn'

    def _init_vcs(self):
        self._run('svnadmin', 'create', 'repo')
        self._run('svn', 'co', 'file:///' + os.path.abspath('repo').replace(os.path.sep, '/'), 'checkout')
        os.chdir('checkout')

    def _add_directories_and_sort(self, filelist):
        from check_manifest import normalize_names
        names = set(normalize_names(filelist))
        names.update([posixpath.dirname(fn) for fn in names])
        return sorted(names - {''})

    def _add_to_vcs(self, filenames):
        self._run('svn', 'add', '-N', '--', *self._add_directories_and_sort(filenames))

    def _commit(self):
        self._run('svn', 'commit', '-m', 'Initial')


class TestSvn(VCSMixin, unittest.TestCase):
    vcs = SvnHelper()

    def test_svn_externals(self):
        from check_manifest import get_vcs_files
        self.vcs._run('svnadmin', 'create', 'repo2')
        repo2_url = 'file:///' + os.path.abspath('repo2').replace(os.path.sep, '/')
        self.vcs._init_vcs()
        self.vcs._run('svn', 'propset', 'svn:externals', 'ext %s' % repo2_url, '.')
        self.vcs._run('svn', 'up')
        self._create_files(['a.txt', 'ext/b.txt'])
        self.vcs._run('svn', 'add', 'a.txt', 'ext/b.txt')
        self.assertEqual(get_vcs_files(self.ui),
                         ['a.txt', 'ext/b.txt'])


class TestSvnExtraErrors(unittest.TestCase):

    def test_svn_xml_parsing_warning(self):
        from check_manifest import Subversion
        ui = MockUI()
        svn = Subversion(ui)
        entry = ET.XML('<entry path="foo/bar.txt"></entry>')
        self.assertFalse(svn.is_interesting(entry))
        self.assertEqual(
            ui.warnings,
            ['svn status --xml parse error:'
             ' <entry path="foo/bar.txt"> without <wc-status>'])


class TestUserInterface(unittest.TestCase):

    def make_ui(self, verbosity=1):
        from check_manifest import UI
        ui = UI(verbosity=verbosity)
        ui.stdout = StringIO()
        ui.stderr = StringIO()
        return ui

    def test_info(self):
        ui = self.make_ui(verbosity=1)
        ui.info("Reticulating splines")
        self.assertEqual(ui.stdout.getvalue(),
                         "Reticulating splines\n")

    def test_info_verbose(self):
        ui = self.make_ui(verbosity=2)
        ui.info("Reticulating splines")
        self.assertEqual(ui.stdout.getvalue(),
                         "Reticulating splines\n")

    def test_info_quiet(self):
        ui = self.make_ui(verbosity=0)
        ui.info("Reticulating splines")
        self.assertEqual(ui.stdout.getvalue(), "")

    def test_info_begin_continue_end(self):
        ui = self.make_ui(verbosity=1)
        ui.info_begin("Reticulating splines...")
        ui.info_continue(" nearly done...")
        ui.info_continue(" almost done...")
        ui.info_end(" done!")
        self.assertEqual(ui.stdout.getvalue(), "")

    def test_info_begin_continue_end_verbose(self):
        ui = self.make_ui(verbosity=2)
        ui.info_begin("Reticulating splines...")
        ui.info_continue(" nearly done...")
        ui.info_continue(" almost done...")
        ui.info_end(" done!")
        self.assertEqual(
            ui.stdout.getvalue(),
            "Reticulating splines... nearly done... almost done... done!\n")

    def test_info_emits_newline_when_needed(self):
        ui = self.make_ui(verbosity=1)
        ui.info_begin("Computering...")
        ui.info("Forgot to turn the gas off!")
        self.assertEqual(
            ui.stdout.getvalue(),
            "Forgot to turn the gas off!\n")

    def test_info_emits_newline_when_needed_verbose(self):
        ui = self.make_ui(verbosity=2)
        ui.info_begin("Computering...")
        ui.info("Forgot to turn the gas off!")
        self.assertEqual(
            ui.stdout.getvalue(),
            "Computering...\n"
            "Forgot to turn the gas off!\n")

    def test_warning(self):
        ui = self.make_ui(verbosity=1)
        ui.info_begin("Computering...")
        ui.warning("Forgot to turn the gas off!")
        self.assertEqual(ui.stdout.getvalue(), "")
        self.assertEqual(
            ui.stderr.getvalue(),
            "Forgot to turn the gas off!\n")

    def test_warning_verbose(self):
        ui = self.make_ui(verbosity=2)
        ui.info_begin("Computering...")
        ui.warning("Forgot to turn the gas off!")
        self.assertEqual(
            ui.stdout.getvalue(),
            "Computering...\n")
        self.assertEqual(
            ui.stderr.getvalue(),
            "Forgot to turn the gas off!\n")

    def test_error(self):
        ui = self.make_ui(verbosity=1)
        ui.info_begin("Computering...")
        ui.error("Forgot to turn the gas off!")
        self.assertEqual(ui.stdout.getvalue(), "")
        self.assertEqual(
            ui.stderr.getvalue(),
            "Forgot to turn the gas off!\n")

    def test_error_verbose(self):
        ui = self.make_ui(verbosity=2)
        ui.info_begin("Computering...")
        ui.error("Forgot to turn the gas off!")
        self.assertEqual(
            ui.stdout.getvalue(),
            "Computering...\n")
        self.assertEqual(
            ui.stderr.getvalue(),
            "Forgot to turn the gas off!\n")


class TestIgnoreList(unittest.TestCase):

    def setUp(self):
        from check_manifest import IgnoreList
        self.ignore = IgnoreList()

    def test_repr(self):
        from check_manifest import IgnoreList
        ignore = IgnoreList()
        self.assertEqual(repr(ignore), "IgnoreList([])")

    def test_exclude_pattern(self):
        self.ignore.exclude('*.txt')
        self.assertEqual(self.ignore.filter([
            'foo.md',
            'bar.txt',
            'subdir/bar.txt',
        ]), [
            'foo.md',
            'subdir/bar.txt',
        ])

    def test_exclude_file(self):
        self.ignore.exclude('bar.txt')
        self.assertEqual(self.ignore.filter([
            'foo.md',
            'bar.txt',
            'subdir/bar.txt',
        ]), [
            'foo.md',
            'subdir/bar.txt',
        ])

    def test_exclude_doest_apply_to_directories(self):
        self.ignore.exclude('subdir')
        self.assertEqual(self.ignore.filter([
            'foo.md',
            'subdir/bar.txt',
        ]), [
            'foo.md',
            'subdir/bar.txt',
        ])

    def test_global_exclude(self):
        self.ignore.global_exclude('a*.txt')
        self.assertEqual(self.ignore.filter([
            'bar.txt',        # make sure full filenames are matched
            'afile.txt',
            'subdir/afile.txt',
            'adir/file.txt',  # make sure * doesn't match /
        ]), [
            'bar.txt',
            'adir/file.txt',
        ])

    def test_global_exclude_does_not_apply_to_directories(self):
        self.ignore.global_exclude('subdir')
        self.assertEqual(self.ignore.filter([
            'bar.txt',
            'subdir/afile.txt',
        ]), [
            'bar.txt',
            'subdir/afile.txt',
        ])

    def test_recursive_exclude(self):
        self.ignore.recursive_exclude('subdir', 'a*.txt')
        self.assertEqual(self.ignore.filter([
            'afile.txt',
            'subdir/afile.txt',
            'subdir/extra/afile.txt',
            'subdir/adir/file.txt',
            'other/afile.txt',
        ]), [
            'afile.txt',
            'subdir/adir/file.txt',
            'other/afile.txt',
        ])

    def test_recursive_exclude_does_not_apply_to_directories(self):
        self.ignore.recursive_exclude('subdir', 'dir')
        self.assertEqual(self.ignore.filter([
            'afile.txt',
            'subdir/dir/afile.txt',
        ]), [
            'afile.txt',
            'subdir/dir/afile.txt',
        ])

    def test_recursive_exclude_can_prune(self):
        self.ignore.recursive_exclude('subdir', '*')
        self.assertEqual(self.ignore.filter([
            'afile.txt',
            'subdir/afile.txt',
            'subdir/dir/afile.txt',
            'subdir/dir/dir/afile.txt',
        ]), [
            'afile.txt',
        ])

    def test_prune(self):
        self.ignore.prune('subdir')
        self.assertEqual(self.ignore.filter([
            'foo.md',
            'subdir/bar.txt',
            'unrelated/subdir/baz.txt',
        ]), [
            'foo.md',
            'unrelated/subdir/baz.txt',
        ])

    def test_prune_subdir(self):
        self.ignore.prune('a/b')
        self.assertEqual(self.ignore.filter([
            'foo.md',
            'a/b/bar.txt',
            'a/c/bar.txt',
        ]), [
            'foo.md',
            'a/c/bar.txt',
        ])

    def test_prune_glob(self):
        self.ignore.prune('su*r')
        self.assertEqual(self.ignore.filter([
            'foo.md',
            'subdir/bar.txt',
            'unrelated/subdir/baz.txt',
        ]), [
            'foo.md',
            'unrelated/subdir/baz.txt',
        ])

    def test_prune_glob_is_not_too_greedy(self):
        self.ignore.prune('su*r')
        self.assertEqual(self.ignore.filter([
            'foo.md',
            # super-unrelated/subdir matches su*r if you allow * to match /,
            # which fnmatch does!
            'super-unrelated/subdir/qux.txt',
        ]), [
            'foo.md',
            'super-unrelated/subdir/qux.txt',
        ])

    def test_default_excludes_pkg_info(self):
        from check_manifest import IgnoreList
        ignore = IgnoreList.default()
        self.assertEqual(ignore.filter([
            'PKG-INFO',
            'bar.txt',
        ]), [
            'bar.txt',
        ])

    def test_default_excludes_egg_info(self):
        from check_manifest import IgnoreList
        ignore = IgnoreList.default()
        self.assertEqual(ignore.filter([
            'mypackage.egg-info/PKG-INFO',
            'mypackage.egg-info/SOURCES.txt',
            'mypackage.egg-info/requires.txt',
            'bar.txt',
        ]), [
            'bar.txt',
        ])

    def test_default_excludes_egg_info_in_a_subdirectory(self):
        from check_manifest import IgnoreList
        ignore = IgnoreList.default()
        self.assertEqual(ignore.filter([
            'src/mypackage.egg-info/PKG-INFO',
            'src/mypackage.egg-info/SOURCES.txt',
            'src/mypackage.egg-info/requires.txt',
            'bar.txt',
        ]), [
            'bar.txt',
        ])


def pick_installed_vcs():
    preferred_order = [GitHelper, HgHelper, BzrHelper, SvnHelper]
    force = os.getenv('FORCE_TEST_VCS')
    if force:
        for cls in preferred_order:
            if force == cls.command:
                return cls()
        raise ValueError('Unsupported FORCE_TEST_VCS=%s (supported: %s)'
                         % (force, '/'.join(cls.command for cls in preferred_order)))
    for cls in preferred_order:
        vcs = cls()
        if vcs.is_installed():
            return vcs
    return None


class TestCheckManifest(unittest.TestCase):

    _vcs = pick_installed_vcs()

    def setUp(self):
        if self._vcs is None:
            self.fail('at least one version control system should be installed')
        self.oldpwd = os.getcwd()
        self.tmpdir = tempfile.mkdtemp(prefix='test-', suffix='-check-manifest')
        os.chdir(self.tmpdir)
        self._stdout_patcher = mock.patch('sys.stdout', StringIO())
        self._stdout_patcher.start()
        self._stderr_patcher = mock.patch('sys.stderr', StringIO())
        self._stderr_patcher.start()

    def tearDown(self):
        self._stderr_patcher.stop()
        self._stdout_patcher.stop()
        os.chdir(self.oldpwd)
        rmtree(self.tmpdir)

    def _create_repo_with_code(self, add_to_vcs=True):
        self._vcs._init_vcs()
        with open('setup.py', 'w') as f:
            f.write("from setuptools import setup\n")
            f.write("setup(name='sample', py_modules=['sample'])\n")
        with open('sample.py', 'w') as f:
            f.write("# wow. such code. so amaze\n")
        if add_to_vcs:
            self._vcs._add_to_vcs(['setup.py', 'sample.py'])

    def _create_repo_with_code_in_subdir(self):
        os.mkdir('subdir')
        os.chdir('subdir')
        self._create_repo_with_code()
        # NB: when self._vcs is SvnHelper, we're actually in
        # ./subdir/checkout rather than in ./subdir
        subdir = os.path.basename(os.getcwd())
        os.chdir(os.pardir)
        return subdir

    def _add_to_vcs(self, filename, content=''):
        if os.path.sep in filename and not os.path.isdir(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))
        with open(filename, 'w') as f:
            f.write(content)
        self._vcs._add_to_vcs([filename])

    def test_not_python_project(self):
        from check_manifest import Failure, check_manifest
        with self.assertRaises(Failure) as cm:
            check_manifest()
        self.assertEqual(
            str(cm.exception),
            "This is not a Python project (no setup.py/pyproject.toml).")

    def test_forgot_to_git_add_anything(self):
        from check_manifest import Failure, check_manifest
        self._create_repo_with_code(add_to_vcs=False)
        with self.assertRaises(Failure) as cm:
            check_manifest()
        self.assertEqual(str(cm.exception),
                         "There are no files added to version control!")

    def test_all_is_well(self):
        from check_manifest import check_manifest
        self._create_repo_with_code()
        self.assertTrue(check_manifest(), sys.stderr.getvalue())

    def test_relative_pathname(self):
        from check_manifest import check_manifest
        subdir = self._create_repo_with_code_in_subdir()
        self.assertTrue(check_manifest(subdir), sys.stderr.getvalue())

    def test_relative_python(self):
        # https://github.com/mgedmin/check-manifest/issues/36
        from check_manifest import check_manifest
        subdir = self._create_repo_with_code_in_subdir()
        python = os.path.relpath(sys.executable)
        self.assertTrue(check_manifest(subdir, python=python),
                        sys.stderr.getvalue())

    def test_python_from_path(self):
        # https://github.com/mgedmin/check-manifest/issues/57
        from check_manifest import check_manifest

        # We need a Python interpeter to be in PATH.
        python = 'python'
        if hasattr(shutil, 'which'):
            for python in 'python', 'python3', os.path.basename(sys.executable):
                if shutil.which(python):
                    break
        subdir = self._create_repo_with_code_in_subdir()
        self.assertTrue(check_manifest(subdir, python=python),
                        sys.stderr.getvalue())

    def test_extra_ignore(self):
        from check_manifest import IgnoreList, check_manifest
        self._create_repo_with_code()
        self._add_to_vcs('unrelated.txt')
        ignore = IgnoreList().global_exclude('*.txt')
        self.assertTrue(check_manifest(extra_ignore=ignore),
                        sys.stderr.getvalue())

    def test_suggestions(self):
        from check_manifest import check_manifest
        self._create_repo_with_code()
        self._add_to_vcs('unrelated.txt')
        self.assertFalse(check_manifest())
        self.assertIn("missing from sdist:\n  unrelated.txt",
                      sys.stderr.getvalue())
        self.assertIn("suggested MANIFEST.in rules:\n  include *.txt",
                      sys.stdout.getvalue())

    def test_suggestions_create(self):
        from check_manifest import check_manifest
        self._create_repo_with_code()
        self._add_to_vcs('unrelated.txt')
        self.assertFalse(check_manifest(create=True))
        self.assertIn("missing from sdist:\n  unrelated.txt",
                      sys.stderr.getvalue())
        self.assertIn("suggested MANIFEST.in rules:\n  include *.txt",
                      sys.stdout.getvalue())
        self.assertIn("creating MANIFEST.in",
                      sys.stdout.getvalue())
        with open('MANIFEST.in') as f:
            self.assertEqual(f.read(), "include *.txt\n")

    def test_suggestions_update(self):
        from check_manifest import check_manifest
        self._create_repo_with_code()
        self._add_to_vcs('unrelated.txt')
        self._add_to_vcs('MANIFEST.in', '#tbd')
        self.assertFalse(check_manifest(update=True))
        self.assertIn("missing from sdist:\n  unrelated.txt",
                      sys.stderr.getvalue())
        self.assertIn("suggested MANIFEST.in rules:\n  include *.txt",
                      sys.stdout.getvalue())
        self.assertIn("updating MANIFEST.in",
                      sys.stdout.getvalue())
        with open('MANIFEST.in') as f:
            self.assertEqual(
                f.read(),
                "#tbd\n# added by check-manifest\ninclude *.txt\n")

    def test_suggestions_all_unknown_patterns(self):
        from check_manifest import check_manifest
        self._create_repo_with_code()
        self._add_to_vcs('.dunno-what-to-do-with-this')
        self.assertFalse(check_manifest(update=True))
        self.assertIn("missing from sdist:\n  .dunno-what-to-do-with-this",
                      sys.stderr.getvalue())
        self.assertIn(
            "don't know how to come up with rules matching any of the files, sorry!",
            sys.stdout.getvalue())

    def test_suggestions_some_unknown_patterns(self):
        from check_manifest import check_manifest
        self._create_repo_with_code()
        self._add_to_vcs('.dunno-what-to-do-with-this')
        self._add_to_vcs('unrelated.txt')
        self.assertFalse(check_manifest(update=True))
        self.assertIn(
            "don't know how to come up with rules matching\n  .dunno-what-to-do-with-this",
            sys.stdout.getvalue())
        self.assertIn("creating MANIFEST.in",
                      sys.stdout.getvalue())
        with open('MANIFEST.in') as f:
            self.assertEqual(f.read(), "include *.txt\n")

    def test_MANIFEST_in_does_not_need_to_be_added_to_be_considered(self):
        from check_manifest import check_manifest
        self._create_repo_with_code()
        self._add_to_vcs('unrelated.txt')
        with open('MANIFEST.in', 'w') as f:
            f.write("include *.txt\n")
        self.assertFalse(check_manifest())
        self.assertIn("missing from VCS:\n  MANIFEST.in", sys.stderr.getvalue())
        self.assertNotIn("missing from sdist", sys.stderr.getvalue())

    def test_setup_py_does_not_need_to_be_added_to_be_considered(self):
        from check_manifest import check_manifest
        self._create_repo_with_code(add_to_vcs=False)
        self._add_to_vcs('sample.py')
        self.assertFalse(check_manifest())
        self.assertIn("missing from VCS:\n  setup.py", sys.stderr.getvalue())
        self.assertNotIn("missing from sdist", sys.stderr.getvalue())

    def test_bad_ideas(self):
        from check_manifest import check_manifest
        self._create_repo_with_code()
        self._add_to_vcs('foo.egg-info')
        self._add_to_vcs('moo.mo')
        self.assertFalse(check_manifest())
        self.assertIn("you have foo.egg-info in source control!",
                      sys.stderr.getvalue())
        self.assertIn("this also applies to the following:\n  moo.mo",
                      sys.stderr.getvalue())

    def test_ignore_bad_ideas(self):
        from check_manifest import IgnoreList, check_manifest
        self._create_repo_with_code()
        with open('setup.cfg', 'w') as f:
            f.write('[check-manifest]\n'
                    'ignore =\n'
                    '  subdir/bar.egg-info\n'
                    'ignore-bad-ideas =\n'
                    '  subdir/bar.egg-info\n')
        self._add_to_vcs('foo.egg-info')
        self._add_to_vcs('moo.mo')
        self._add_to_vcs(os.path.join('subdir', 'bar.egg-info'))
        ignore = IgnoreList().global_exclude('*.mo')
        self.assertFalse(check_manifest(extra_ignore_bad_ideas=ignore))
        self.assertIn("you have foo.egg-info in source control!",
                      sys.stderr.getvalue())
        self.assertNotIn("moo.mo", sys.stderr.getvalue())
        self.assertNotIn("bar.egg-info", sys.stderr.getvalue())

    def test_missing_source_files(self):
        # https://github.com/mgedmin/check-manifest/issues/32
        from check_manifest import check_manifest
        self._create_repo_with_code()
        self._add_to_vcs('missing.py')
        os.unlink('missing.py')
        check_manifest()
        if self._vcs.command != 'bzr':
            # 'bzr ls' doesn't list files that were deleted but not
            # marked for deletion.  'bzr st' does, but it doesn't list
            # unmodified files.  Importing bzrlib and using the API to
            # get the file list we need is (a) complicated, (b) opens
            # the optional dependency can of worms, and (c) not viable
            # under Python 3 unless we fork off a Python 2 subprocess.
            # Manually combining 'bzr ls' and 'bzr st' outputs just to
            # produce a cosmetic warning message seems like overkill.
            self.assertIn(
                "some files listed as being under source control are missing:\n"
                "  missing.py",
                sys.stderr.getvalue())
