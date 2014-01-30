import doctest
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import zipfile
from contextlib import closing

try:
    import unittest2 as unittest    # Python 2.6
except ImportError:
    import unittest

try:
    from cStringIO import StringIO  # Python 2.x
except ImportError:
    from io import StringIO         # Python 3.x

import mock


class Tests(unittest.TestCase):

    def setUp(self):
        import check_manifest
        self.warnings = []
        self._real_warning = check_manifest.warning
        check_manifest.warning = self.warnings.append

    def tearDown(self):
        import check_manifest
        check_manifest.warning = self._real_warning

    def make_temp_dir(self):
        tmpdir = tempfile.mkdtemp(prefix='test-', suffix='-check-manifest')
        self.addCleanup(shutil.rmtree, tmpdir)
        return tmpdir

    def create_zip_file(self, filename, filenames):
        with closing(zipfile.ZipFile(filename, 'w')) as zf:
            for fn in filenames:
                zf.writestr(fn, '')

    def test_run_success(self):
        from check_manifest import run
        self.assertEqual(run(["true"]), "")

    def test_run_failure(self):
        from check_manifest import run, CommandFailed
        with self.assertRaises(CommandFailed) as cm:
            run(["false"])
        self.assertEqual(str(cm.exception),
                         "['false'] failed (status 1):\n")

    def test_run_no_such_program(self):
        from check_manifest import run, Failure
        with self.assertRaises(Failure) as cm:
            run(["there-is-really-no-such-program"])
        self.assertTrue(
            str(cm.exception).startswith(
                "could not run ['there-is-really-no-such-program']:"
                " [Errno 2] No such file or directory"))

    def test_copy_files(self):
        from check_manifest import copy_files
        actions = []
        with mock.patch('os.path.isdir', lambda d: d in ('b', '/dest/dir')):
            with mock.patch('os.makedirs',
                            lambda d: actions.append('makedirs %s' % d)):
                with mock.patch('os.mkdir',
                                lambda d: actions.append('mkdir %s' % d)):
                    with mock.patch('shutil.copy2',
                                    lambda s, d: actions.append('cp %s %s' % (s, d))):
                        copy_files(['a', 'b', 'c/d/e'], '/dest/dir')
        self.assertEqual(
            actions,
            [
                'cp a /dest/dir/a',
                'mkdir /dest/dir/b',
                'makedirs /dest/dir/c/d',
                'cp c/d/e /dest/dir/c/d/e',
            ])

    def test_get_one_file_in(self):
        from check_manifest import get_one_file_in
        with mock.patch('os.listdir', lambda dir: ['a']):
            self.assertEqual(get_one_file_in('/some/dir'),
                             '/some/dir/a')

    def test_get_one_file_in_empty_directory(self):
        from check_manifest import get_one_file_in, Failure
        with mock.patch('os.listdir', lambda dir: []):
            with self.assertRaises(Failure) as cm:
                get_one_file_in('/some/dir')
            self.assertEqual(str(cm.exception),
                             "No files found in /some/dir")

    def test_get_one_file_in_too_many(self):
        from check_manifest import get_one_file_in, Failure
        with mock.patch('os.listdir', lambda dir: ['b', 'a']):
            with self.assertRaises(Failure) as cm:
                get_one_file_in('/some/dir')
            self.assertEqual(str(cm.exception),
                             "More than one file exists in /some/dir:\na\nb")

    def test_get_archive_file_list_unrecognized_archive(self):
        from check_manifest import get_archive_file_list, Failure
        with self.assertRaises(Failure) as cm:
            get_archive_file_list('archive.rar')
        self.assertEqual(str(cm.exception), 'Unrecognized archive type: .rar')

    def test_get_archive_file_list_zip(self):
        from check_manifest import get_archive_file_list
        filename = os.path.join(self.make_temp_dir(), 'archive.zip')
        self.create_zip_file(filename, ['a', 'b/c'])
        self.assertEqual(get_archive_file_list(filename),
                         ['a', 'b', 'b/c'])

    def test_format_list(self):
        from check_manifest import format_list
        self.assertEqual(format_list([]), "")
        self.assertEqual(format_list(['a']), "  a")
        self.assertEqual(format_list(['a', 'b']), "  a\n  b")

    def test_format_difference(self):
        from check_manifest import format_difference
        self.assertEqual(
            format_difference(["a", "b"], ["a", "b"], "1st", "2nd"),
            "")
        self.assertEqual(
            format_difference(["a", "b"], ["b", "c"], "1st", "2nd"),
            "missing from 1st:\n"
            "  c\n"
            "missing from 2nd:\n"
            "  a")

    def test_strip_toplevel_name_empty_list(self):
        from check_manifest import strip_toplevel_name
        self.assertEqual(strip_toplevel_name([]), [])

    def test_strip_toplevel_name_no_common_prefix(self):
        from check_manifest import strip_toplevel_name, Failure
        self.assertRaises(Failure, strip_toplevel_name, ["a/b", "c/d"])

    def test_detect_vcs_no_vcs(self):
        from check_manifest import detect_vcs, Failure
        with mock.patch('check_manifest.VCS.detect', staticmethod(lambda *a: False)):
            with self.assertRaises(Failure) as cm:
                detect_vcs()
            self.assertEqual(str(cm.exception),
                             "Couldn't find version control data"
                             " (git/hg/bzr/svn supported)")

    def test_normalize_names(self):
        from check_manifest import normalize_names
        self.assertEqual(normalize_names(["a", "b/", "c/d", "e/f/", "g/h/../i"]),
                         ["a", "b", "c/d", "e/f", "g/i"])

    def test_add_directories(self):
        from check_manifest import add_directories
        self.assertEqual(add_directories(["a", "b", "c/d", "e/f"]),
                         ["a", "b", "c", "c/d", "e", "e/f"])

    def test_file_matches(self):
        from check_manifest import file_matches
        patterns = ['setup.cfg', '*.egg-info', '*.egg-info/*']
        self.assertFalse(file_matches('setup.py', patterns))
        self.assertTrue(file_matches('setup.cfg', patterns))
        self.assertTrue(file_matches('src/zope.foo.egg-info', patterns))
        self.assertTrue(file_matches('src/zope.foo.egg-info/SOURCES.txt',
                                     patterns))

    def test_strip_sdist_extras(self):
        from check_manifest import strip_sdist_extras
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
            'setup.py',
            'README.txt',
            'src',
            'src/zope',
            'src/zope/__init__.py',
            'src/zope/foo',
            'src/zope/foo/__init__.py',
            'src/zope/foo/language.po',
        ]
        self.assertEqual(strip_sdist_extras(filelist), expected)

    def test_strip_sdist_extras_with_manifest(self):
        import check_manifest
        from check_manifest import strip_sdist_extras
        from check_manifest import _get_ignore_from_manifest as parse
        orig_ignore = check_manifest.IGNORE
        orig_ignore_regexps = check_manifest.IGNORE_REGEXPS
        manifest_in = """
        graft src
        exclude *.cfg
        global-exclude *.mo
        prune src/dump
        recursive-exclude src/zope *.sh
        """
        # Keep the indentation visually clear in the test, but remove
        # leading whitespace programmatically.
        manifest_in = textwrap.dedent(manifest_in)
        filelist = [
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
        ]
        expected = [
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
        ]

        # This will change the definitions.
        try:
            # This is normally done in read_manifest:
            ignore, ignore_regexps = parse(manifest_in)
            check_manifest.IGNORE.extend(ignore)
            check_manifest.IGNORE_REGEXPS.extend(ignore_regexps)
            # Filter the file list.
            result = strip_sdist_extras(filelist)
        finally:
            # Restore the original definitions
            check_manifest.IGNORE = orig_ignore
            check_manifest.IGNORE_REGEXPS = orig_ignore_regexps
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
        ]
        expected_rules = [
            'recursive-include docs *.png',
            'recursive-include docs *.rst',
            'recursive-include docs Makefile',
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

    def test_get_ignore_from_manifest(self):
        from check_manifest import _get_ignore_from_manifest as parse
        # The return value is a tuple with two lists:
        # ([<list of filename ignores>], [<list of regular expressions>])
        self.assertEqual(parse(''),
                         ([], []))
        self.assertEqual(parse('      \n        '),
                         ([], []))
        self.assertEqual(parse('exclude *.cfg'),
                         ([], ['[^/]*\.cfg']))
        self.assertEqual(parse('#exclude *.cfg'),
                         ([], []))
        self.assertEqual(parse('exclude          *.cfg'),
                         ([], ['[^/]*\.cfg']))
        self.assertEqual(parse('\texclude\t*.cfg foo.*   bar.txt'),
                         (['bar.txt'], ['[^/]*\.cfg', 'foo\.[^/]*']))
        self.assertEqual(parse('exclude some/directory/*.cfg'),
                         ([], ['some/directory/[^/]*\.cfg']))
        self.assertEqual(parse('include *.cfg'),
                         ([], []))
        self.assertEqual(parse('global-exclude *.pyc'),
                         (['*.pyc'], []))
        self.assertEqual(parse('global-exclude *.pyc *.sh'),
                         (['*.pyc', '*.sh'], []))
        self.assertEqual(parse('recursive-exclude dir *.pyc'),
                         (['dir/*.pyc'], []))
        self.assertEqual(parse('recursive-exclude dir *.pyc foo*.sh'),
                         (['dir/*.pyc', 'dir/foo*.sh', 'dir/*/foo*.sh'], []))
        self.assertEqual(parse('recursive-exclude dir nopattern.xml'),
                         (['dir/nopattern.xml', 'dir/*/nopattern.xml'], []))
        # We should not fail when a recursive-exclude line is wrong:
        self.assertEqual(parse('recursive-exclude dirwithoutpattern'),
                         ([], []))
        self.assertEqual(parse('prune dir'),
                         (['dir', 'dir/*'], []))
        # You should not add a slash at the end of a prune, but let's
        # not fail over it or end up with double slashes.
        self.assertEqual(parse('prune dir/'),
                         (['dir', 'dir/*'], []))
        text = """
            #exclude *.01
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
        """
        # Keep the indentation visually clear in the test, but remove
        # leading whitespace programmatically.
        text = textwrap.dedent(text)
        self.assertEqual(
            parse(text),
            ([
                'bar.txt',
                '*.10',
                '*.11',
                '*.12',
                '30',
                '30/*',
                '40/*.41',
                '42/*.43',
                '42/44.*',
                '42/*/44.*',
            ], [
                '[^/]*\.02',
                '[^/]*\.03',
                '04\.[^/]*',
                '[^/]*\.05',
                'some/directory/[^/]*\.cfg',
            ]))


class VCSMixin(object):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='test-', suffix='-check-manifest')
        self.olddir = os.getcwd()
        os.chdir(self.tmpdir)

    def tearDown(self):
        os.chdir(self.olddir)
        shutil.rmtree(self.tmpdir)

    def _run(self, *command):
        p = subprocess.Popen(command, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
        stdout, stderr = p.communicate()
        rc = p.wait()
        if rc:
            print(' '.join(command))
            print(stdout)
            raise subprocess.CalledProcessError(rc, command[0], output=stdout)

    def _create_file(self, filename):
        assert not os.path.isabs(filename)
        basedir = os.path.dirname(filename)
        if basedir and not os.path.isdir(basedir):
            os.makedirs(basedir)
        open(filename, 'w').close()

    def _create_files(self, filenames):
        for filename in filenames:
            self._create_file(filename)

    def _create_and_add_to_vcs(self, filenames):
        self._create_files(filenames)
        self._add_to_vcs(filenames)

    def test_get_vcs_files(self):
        from check_manifest import get_vcs_files
        self._init_vcs()
        self._create_and_add_to_vcs(['a.txt', 'b/b.txt', 'b/c/d.txt'])
        self._commit()
        self._create_files(['b/x.txt', 'd/d.txt', 'i.txt'])
        self.assertEqual(get_vcs_files(),
                         ['a.txt', 'b', 'b/b.txt', 'b/c', 'b/c/d.txt'])

    def test_get_vcs_files_added_but_uncommitted(self):
        from check_manifest import get_vcs_files
        self._init_vcs()
        self._create_and_add_to_vcs(['a.txt', 'b/b.txt', 'b/c/d.txt'])
        self._create_files(['b/x.txt', 'd/d.txt', 'i.txt'])
        self.assertEqual(get_vcs_files(),
                         ['a.txt', 'b', 'b/b.txt', 'b/c', 'b/c/d.txt'])

    def test_get_vcs_files_in_a_subdir(self):
        from check_manifest import get_vcs_files
        self._init_vcs()
        self._create_and_add_to_vcs(['a.txt', 'b/b.txt', 'b/c/d.txt'])
        self._commit()
        self._create_files(['b/x.txt', 'd/d.txt', 'i.txt'])
        os.chdir('b')
        self.assertEqual(get_vcs_files(), ['b.txt', 'c', 'c/d.txt'])


class TestGit(VCSMixin, unittest.TestCase):

    def _init_vcs(self):
        self._run('git', 'init')
        self._run('git', 'config', 'user.name', 'Unit Test')
        self._run('git', 'config', 'user.email', 'test@example.com')

    def _add_to_vcs(self, filenames):
        self._run('git', 'add', '--', *filenames)

    def _commit(self):
        self._run('git', 'commit', '-m', 'Initial')


class TestBzr(VCSMixin, unittest.TestCase):

    def _init_vcs(self):
        self._run('bzr', 'init')
        self._run('bzr', 'whoami', '--branch', 'Unit Test <test@example.com>')

    def _add_to_vcs(self, filenames):
        self._run('bzr', 'add', '--', *filenames)

    def _commit(self):
        self._run('bzr', 'commit', '-m', 'Initial')


class TestHg(VCSMixin, unittest.TestCase):

    def _init_vcs(self):
        self._run('hg', 'init')
        with open('.hg/hgrc', 'a') as f:
            f.write('\n[ui]\nusername = Unit Test <test@example.com\n')

    def _add_to_vcs(self, filenames):
        self._run('hg', 'add', '--', *filenames)

    def _commit(self):
        self._run('hg', 'commit', '-m', 'Initial')


class TestSvn(VCSMixin, unittest.TestCase):

    def _init_vcs(self):
        self._run('svnadmin', 'create', 'repo')
        self._run('svn', 'co', 'file:///' + os.path.abspath('repo'), 'checkout')
        os.chdir('checkout')

    def _add_to_vcs(self, filenames):
        from check_manifest import add_directories
        self._run('svn', 'add', '-N', '--', *add_directories(filenames))

    def _commit(self):
        self._run('svn', 'commit', '-m', 'Initial')


class TestUserInterface(unittest.TestCase):

    def setUp(self):
        self.real_stdout = sys.stdout
        self.real_stderr = sys.stderr
        sys.stdout = StringIO()
        sys.stderr = StringIO()

    def tearDown(self):
        sys.stderr = self.real_stderr
        sys.stdout = self.real_stdout

    def test_info(self):
        from check_manifest import info
        info("Reticulating splines")
        self.assertEqual(sys.stdout.getvalue(),
                         "Reticulating splines\n")

    def test_info_begin_continue_end(self):
        from check_manifest import info_begin, info_continue, info_end
        info_begin("Reticulating splines...")
        info_continue(" nearly done...")
        info_continue(" almost done...")
        info_end(" done!")
        self.assertEqual(
            sys.stdout.getvalue(),
            "Reticulating splines... nearly done... almost done... done!\n")

    def test_info_emits_newline_when_needed(self):
        from check_manifest import info_begin, info
        info_begin("Computering...")
        info("Forgot to turn the gas off!")
        self.assertEqual(
            sys.stdout.getvalue(),
            "Computering...\n"
            "Forgot to turn the gas off!\n")

    def test_warning(self):
        from check_manifest import info_begin, warning
        info_begin("Computering...")
        warning("Forgot to turn the gas off!")
        self.assertEqual(
            sys.stdout.getvalue(),
            "Computering...\n")
        self.assertEqual(
            sys.stderr.getvalue(),
            "Forgot to turn the gas off!\n")

    def test_error(self):
        from check_manifest import info_begin, error
        info_begin("Computering...")
        error("Forgot to turn the gas off!")
        self.assertEqual(
            sys.stdout.getvalue(),
            "Computering...\n")
        self.assertEqual(
            sys.stderr.getvalue(),
            "Forgot to turn the gas off!\n")


def test_suite():
    return unittest.TestSuite([
        unittest.makeSuite(Tests),
        unittest.makeSuite(TestGit),
        unittest.makeSuite(TestBzr),
        unittest.makeSuite(TestHg),
        unittest.makeSuite(TestSvn),
        unittest.makeSuite(TestUserInterface),
        doctest.DocTestSuite('check_manifest'),
    ])
