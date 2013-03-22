import unittest


class TestFileMatching(unittest.TestCase):

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
