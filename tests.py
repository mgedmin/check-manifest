import doctest
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

    def test_strip_slashes(self):
        from check_manifest import strip_slashes
        self.assertEqual(strip_slashes(["a", "b/", "c/d", "e/f/"]),
                         ["a", "b", "c/d", "e/f"])

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


def test_suite():
    return unittest.TestSuite([
        unittest.makeSuite(Tests),
        doctest.DocTestSuite('check_manifest'),
    ])

