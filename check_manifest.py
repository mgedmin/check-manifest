#!/usr/bin/env python
"""Check the MANIFEST.in file in a Python source package for completeness.

This script works by building a source distribution archive (by running
setup.py sdist), then checking the file list in the archive against the
file list in version control (Subversion, Git, Mercurial, Bazaar are
supported).

Since the first check can fail to catch missing MANIFEST.in entries when
you've got the right setuptools version control system support plugins
installed, the script copies all the versioned files into a temporary
directory before building the source distribution.  This also avoids
issues with stale egg-info/SOURCES.txt files that may cause files not mentioned
in MANIFEST.in to be included nevertheless.

The current implementation probably doesn't work on Windows.
"""
from __future__ import print_function

import argparse
import fnmatch
import locale
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from contextlib import contextmanager

try:
    import ConfigParser
except ImportError:
    # Python 3.x
    import configparser as ConfigParser


__version__ = '0.15'
__author__ = 'Marius Gedminas <marius@gedmin.as>'
__licence__ = 'MIT'
__url__ = 'https://github.com/mgedmin/check-manifest'


class Failure(Exception):
    """An expected failure (as opposed to a bug in this script)."""


#
# User interface
#

_to_be_continued = False
def _check_tbc():
    global _to_be_continued
    if _to_be_continued:
        print()
        _to_be_continued = False


def info(message):
    _check_tbc()
    print(message)


def info_begin(message):
    global _to_be_continued
    _check_tbc()
    sys.stdout.write(message)
    sys.stdout.flush()
    _to_be_continued = True


def info_continue(message):
    global _to_be_continued
    sys.stdout.write(message)
    sys.stdout.flush()
    _to_be_continued = True


def info_end(message):
    global _to_be_continued
    print(message)
    _to_be_continued = False


def error(message):
    _check_tbc()
    print(message, file=sys.stderr)


def warning(message):
    _check_tbc()
    print(message, file=sys.stderr)


def format_list(list_of_strings):
    return "\n".join("  " + s for s in list_of_strings)


def format_difference(seq_a, seq_b, name_a, name_b):
    # What about a unified diff?
    ## return format_list(difflib.unified_diff(seq_a, seq_b, name_a, name_b,
    ##                                         lineterm=''))
    # Maybe not
    missing_from_a = sorted(set(seq_b) - set(seq_a))
    missing_from_b = sorted(set(seq_a) - set(seq_b))
    res = []
    if missing_from_a:
        res.append("missing from %s:\n%s"
                   % (name_a, format_list(missing_from_a)))
    if missing_from_b:
        res.append("missing from %s:\n%s"
                   % (name_b, format_list(missing_from_b)))
    return '\n'.join(res)


#
# Filesystem/OS utilities
#

class CommandFailed(Failure):
    def __init__(self, command, status, output):
        Failure.__init__(self, "%s failed (status %s):\n%s" % (
                               command, status, output))


def run(command):
    """Run a command [cmd, arg1, arg2, ...].

    Returns the output (stdout + stderr).

    Raises CommandFailed in cases of error.
    """
    pipe = subprocess.Popen(command, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    output = pipe.communicate()[0].decode(locale.getpreferredencoding(False))
    status = pipe.wait()
    if status != 0:
        raise CommandFailed(command, status, output)
    return output


@contextmanager
def cd(directory):
    """Change the current working directory, temporarily.

    Use as a context manager: with cd(d): ...
    """
    old_dir = os.getcwd()
    try:
        os.chdir(directory)
        yield
    finally:
        os.chdir(old_dir)


@contextmanager
def mkdtemp(hint=''):
    """Create a temporary directory, then clean it up.

    Use as a context manager: with mkdtemp('-purpose'): ...
    """
    dirname = tempfile.mkdtemp(prefix='check-manifest-', suffix=hint)
    try:
        yield dirname
    finally:
        shutil.rmtree(dirname)


def copy_files(filelist, destdir):
    """Copy a list of files to destdir, preserving directory structure.

    File names should be relative to the current working directory.
    """
    for filename in filelist:
        destfile = os.path.join(destdir, filename)
        # filename should not be absolute, but let's double-check
        assert destfile.startswith(destdir + os.path.sep)
        destfiledir = os.path.dirname(destfile)
        if not os.path.isdir(destfiledir):
            os.makedirs(destfiledir)
        if os.path.isdir(filename):
            os.mkdir(destfile)
        else:
            shutil.copy2(filename, destfile)


def get_one_file_in(dirname):
    """Return the pathname of the one file in a directory.

    Raises if the directory has no files or more than one file.
    """
    files = os.listdir(dirname)
    if len(files) > 1:
        raise Failure('More than one file exists in %s:\n%s' %
                      (dirname, '\n'.join(sorted(files))))
    elif not files:
        raise Failure('No files found in %s' % dirname)
    return os.path.join(dirname, files[0])


def get_archive_file_list(archive_filename):
    """Return the list of files in an archive.

    Supports .tar.gz and .zip.
    """
    if archive_filename.endswith('.zip'):
        with zipfile.ZipFile(archive_filename) as zf:
            return add_directories(zf.namelist())
    elif archive_filename.endswith(('.tar.gz', '.tar.bz2', '.tar')):
        with tarfile.open(archive_filename) as tf:
            return tf.getnames()
    else:
        ext = os.path.splitext(archive_filename)[-1]
        raise Failure('Unrecognized archive type: %s' % ext)


def strip_toplevel_name(filelist):
    """Strip toplevel name from a file list.

        >>> strip_toplevel_name(['a', 'a/b', 'a/c', 'a/c/d'])
        ['b', 'c', 'c/d']

        >>> strip_toplevel_name(['a/b', 'a/c', 'a/c/d'])
        ['b', 'c', 'c/d']

    """
    if not filelist:
        return filelist
    prefix = filelist[0]
    if '/' in prefix:
        prefix = prefix.partition('/')[0] + '/'
        names = filelist
    else:
        prefix = prefix + '/'
        names = filelist[1:]
    for name in names:
        if not name.startswith(prefix):
            raise Failure("File doesn't have the common prefix (%s): %s"
                          % (name, prefix))
    return [name[len(prefix):] for name in names]


class VCS(object):

    @classmethod
    def detect(cls, location):
        return os.path.isdir(os.path.join(location, cls.metadata_name))


class Git(VCS):
    metadata_name = '.git'

    @staticmethod
    def get_versioned_files():
        """List all files versioned by git in the current directory."""
        output = run(['git', 'ls-files'])
        return add_directories(output.splitlines())


class Mercurial(VCS):
    metadata_name = '.hg'

    @staticmethod
    def get_versioned_files():
        """List all files under Mercurial control in the current directory."""
        output = run(['hg', 'status', '-ncam', '.'])
        return add_directories(output.splitlines())


class Bazaar(VCS):
    metadata_name = '.bzr'

    @staticmethod
    def get_versioned_files():
        """List all files versioned in Bazaar in the current directory."""
        output = run(['bzr', 'ls', '-VR'])
        return output.splitlines()


class Subversion(VCS):
    metadata_name = '.svn'

    @staticmethod
    def get_versioned_files():
        """List all files under SVN control in the current directory."""
        output = run(['svn', 'st', '-vq'])
        return sorted(line[41:] for line in output.splitlines()
                      if line[41:] != '.')


def detect_vcs():
    """Detect the version control system used for the current directory."""
    location = os.path.abspath('.')
    while True:
        for vcs in Git, Mercurial, Bazaar, Subversion:
            if vcs.detect(location):
                return vcs
        parent = os.path.dirname(location)
        if parent == location:
            raise Failure("Couldn't find version control data"
                          " (git/hg/bzr/svn supported)")
        location = parent


def get_vcs_files():
    """List all files under version control in the current directory."""
    vcs = detect_vcs()
    return normalize_names(vcs.get_versioned_files())


def normalize_names(names):
    """Some VCS print directory names with trailing slashes.  Strip them.

    Easiest is to normalize the path.
    """
    return [os.path.normpath(name) for name in names]


def add_directories(names):
    """Git/Mercurial/zip files omit directories, let's add them back."""
    res = list(names)
    seen = set(names)
    for name in names:
        while True:
            name = os.path.dirname(name)
            if not name or name in seen:
                break
            res.append(name)
            seen.add(name)
    return sorted(res)


#
# Packaging logic
#

# it's fine if any of these are missing in the VCS or in the sdist
IGNORE = [
    'PKG-INFO',     # always generated
    '*.egg-info',   # always generated
    '*.egg-info/*', # always generated
    'setup.cfg',    # always generated, sometimes also kept in source control
    # it's not a problem if the sdist is lacking these files:
    '.hgtags', '.hgignore', '.gitignore', '.bzrignore',
    # it's convenient to ship compiled .mo files in sdists, but they shouldn't
    # be checked in
    '*.mo',
]

WARN_ABOUT_FILES_IN_VCS = [
    # generated files should not be committed into the VCS
    'PKG-INFO',
    '*.egg-info',
    '*.mo',
]

SUGGESTIONS = [(re.compile(pattern), suggestion) for pattern, suggestion in [
    # regexp -> suggestion
    ('^([^/]+[.](cfg|ini))$',       r'include \1'),
    ('^([.]travis[.]yml)$',         r'include \1'),
    ('^([A-Z]+)$',                  r'include \1'),
    ('^(Makefile)$',                r'include \1'),
    ('^[^/]+[.](txt|rst|py)$',      r'include *.\1'),
    ('^([a-zA-Z_][a-zA-Z_0-9]*)/'
     '.*[.](py|zcml|pt|mako|xml|html|txt|rst|css|png|jpg|dot|po|pot|mo|ui|desktop|bat)$',
                                    r'recursive-include \1 *.\2'),
    ('^([a-zA-Z_][a-zA-Z_0-9]*)/(Makefile)$',
                                    r'recursive-include \1 \2'),
    # catch-all rules that actually cover some of the above; somewhat
    # experimental: I fear false positives
    ('^([a-zA-Z_0-9]+)$',           r'include \1'),
    ('^[^/]+[.]([a-zA-Z_0-9]+)$',   r'include *.\1'),
    ('^([a-zA-Z_][a-zA-Z_0-9]*)/.*[.]([a-zA-Z_0-9]+)$',
                                    r'recursive-include \1 *.\2'),
]]


def read_config():
    """Read configuration from setup.cfg."""
    # XXX modifies global state, which is kind of evil
    config = ConfigParser.ConfigParser()
    config.read(['setup.cfg'])
    if not config.has_section('check-manifest'):
        return
    if (config.has_option('check-manifest', 'ignore-default-rules')
            and config.getboolean('check-manifest', 'ignore-default-rules')):
        del IGNORE[:]
    if config.has_option('check-manifest', 'ignore'):
        patterns = [p.strip() for p in config.get('check-manifest',
                                                  'ignore').splitlines()]
        IGNORE.extend(p for p in patterns if p)


def file_matches(filename, patterns):
    """Does this filename match any of the patterns?"""
    return any(fnmatch.fnmatch(filename, pat) for pat in patterns)


def strip_sdist_extras(filelist):
    """Strip generated files that are only present in source distributions."""
    return [name for name in filelist
            if not file_matches(name, IGNORE)]


def find_bad_ideas(filelist):
    """Find files matching WARN_ABOUT_FILES_IN_VCS patterns."""
    return [name for name in filelist
            if file_matches(name, WARN_ABOUT_FILES_IN_VCS)]


def find_suggestions(filelist):
    """Suggest MANIFEST.in patterns for missing files."""
    suggestions = set()
    unknowns = []
    for filename in filelist:
        if os.path.isdir(filename):
            # it's impossible to add empty directories via MANIFEST.in anyway,
            # and non-empty directories will be added automatically when we
            # specify patterns for files inside them
            continue
        for pattern, suggestion in SUGGESTIONS:
            m = pattern.match(filename)
            if m is not None:
                suggestions.add(pattern.sub(suggestion, filename))
                break
        else:
            unknowns.append(filename)
    return sorted(suggestions), unknowns


def is_package(source_tree='.'):
    """Is the directory the root of a Python package?

    Note: the term "package" here refers to a collection of files
    with a setup.py, not to a directory with an __init__.py.
    """
    return os.path.exists(os.path.join(source_tree, 'setup.py'))


def check_manifest(source_tree='.', create=False, update=False,
                   python=sys.executable):
    """Compare a generated source distribution with list of files in a VCS.

    Returns True if the manifest is fine.
    """
    all_ok = True
    with cd(source_tree):
        if not is_package(source_tree):
            raise Failure('This is not a Python project (no setup.py).')
        read_config()
        info_begin("listing source files under version control")
        all_source_files = sorted(get_vcs_files())
        source_files = strip_sdist_extras(all_source_files)
        info_continue(": %d files and directories" % len(source_files))
        info_begin("copying source files to a temporary directory")
        with mkdtemp('-sources') as tempsourcedir:
            copy_files(source_files, tempsourcedir)
            if os.path.exists('MANIFEST.in') and 'MANIFEST.in' not in source_files:
                copy_files(['MANIFEST.in'], tempsourcedir)
            info_begin("building an sdist")
            with cd(tempsourcedir):
                with mkdtemp('-sdist') as tempdir:
                    run([python, 'setup.py', 'sdist', '-d', tempdir])
                    sdist_filename = get_one_file_in(tempdir)
                    info_continue(": %s" % os.path.basename(sdist_filename))
                    sdist_files = sorted(normalize_names(strip_sdist_extras(
                        strip_toplevel_name(get_archive_file_list(sdist_filename)))))
                    info_continue(": %d files and directories" % len(sdist_files))
        if source_files == sdist_files:
            info("files in version control match files in the sdist")
        else:
            error("files in version control do not match the sdist!\n%s"
                  % format_difference(source_files, sdist_files,
                                      "VCS", "sdist"))
            missing_files = set(source_files) - set(sdist_files)
            suggestions, unknowns = find_suggestions(missing_files)
            user_asked_for_help = update or (create and not
                                                os.path.exists('MANIFEST.in'))
            if suggestions:
                info("suggested MANIFEST.in rules:\n%s"
                     % format_list(suggestions))
                if user_asked_for_help:
                    with open('MANIFEST.in', 'a') as f:
                        if f.tell() == 0:
                            info("creating MANIFEST.in")
                        else:
                            info("updating MANIFEST.in")
                            f.write('\n# added by check_manifest.py\n')
                        f.write('\n'.join(suggestions) + '\n')
                    if unknowns:
                        info("don't know how to come up with rules matching\n%s"
                             % format_list(unknowns))
            elif user_asked_for_help:
                info("don't know how to come up with rules"
                     " matching any of the files, sorry!")
            all_ok = False
        bad_ideas = find_bad_ideas(all_source_files)
        if bad_ideas:
            warning("you have %s in source control!\nthat's a bad idea:"
                    " auto-generated files should not be versioned"
                    % bad_ideas[0])
            if len(bad_ideas) > 1:
                warning("this also applies to the following:\n%s"
                        % format_list(bad_ideas[1:]))
            all_ok = False
    return all_ok


#
# Main script
#

def main():
    parser = argparse.ArgumentParser(
        description="Check a Python MANIFEST.in file for completeness",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('source_tree', default='.', nargs='?',
        help='location for the source tree')
    parser.add_argument('--version', action='version',
                        version='%(prog)s version ' + __version__)
    parser.add_argument('-c', '--create', action='store_true',
        help='create a MANIFEST.in if missing')
    parser.add_argument('-u', '--update', action='store_true',
        help='append suggestions to MANIFEST.in (implies --create)')
    parser.add_argument('-p', '--python', default=sys.executable,
        help='use this Python interpreter for running setup.py sdist')
    parser.add_argument('--ignore', metavar='patterns', default=None,
                        help='ignore files/directories matching these'
                             ' comma-separated patterns')
    args = parser.parse_args()

    if args.ignore:
        IGNORE.extend(args.ignore.split(','))

    try:
        if not check_manifest(args.source_tree, create=args.create,
                              update=args.update, python=args.python):
            sys.exit(1)
    except Failure as e:
        error(e)
        sys.exit(2)


#
# zest.releaser integration
#

def zest_releaser_check(data):
    """Check the completeness of MANIFEST.in before the release.

    This is an entry point for zest.releaser.  See the documentation at
    http://zestreleaser.readthedocs.org/en/latest/entrypoints.html
    """
    from zest.releaser.utils import ask
    source_tree = data['workingdir']
    if not is_package(source_tree):
        # You can use zest.releaser on things that are not Python packages.
        # It's pointless to run check-manifest in those circumstances.
        # See https://github.com/mgedmin/check-manifest/issues/9 for details.
        return
    if not ask("Do you want to run check-manifest?"):
        return
    try:
        if not check_manifest(source_tree):
            if not ask("MANIFEST.in is not in order. "
                       " Do you want to continue despite that?", default=False):
                sys.exit(1)
    except Failure as e:
        error(e)
        if not ask("Something bad happened. "
                   " Do you want to continue despite that?", default=False):
            sys.exit(2)


if __name__ == '__main__':
    main()
