import doctest
import os
import shutil
import subprocess
import tempfile
import unittest


class Tests(unittest.TestCase):

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


class VCSMixin(object):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='test-', suffix='-check-manifest')
        self.olddir = os.getcwd()
        os.chdir(self.tmpdir)

    def tearDown(self):
        os.chdir(self.olddir)
        shutil.rmtree(self.tmpdir)

    def _run(self, *command):
        try:
            subprocess.check_output(command, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            print(' '.join(command))
            print(e.output)
            raise

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


def test_suite():
    return unittest.TestSuite([
        unittest.makeSuite(Tests),
        unittest.makeSuite(TestGit),
        unittest.makeSuite(TestBzr),
        unittest.makeSuite(TestHg),
        unittest.makeSuite(TestSvn),
        doctest.DocTestSuite('check_manifest'),
    ])
