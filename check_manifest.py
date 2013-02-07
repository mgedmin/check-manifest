#!/usr/bin/python
"""Check the MANIFEST.in file in a Python source package for completeness.

Here's the plan:
    This script works by building a source distribution archive (by running
    setup.py sdist), then checking the file list in the archive against the
    file list in version control (Subversion, Git, Mercurial, Bazaar are
    supported).

    Since the first check can fail to catch missing MANIFEST.in entries when
    you've got the right setuptools plugins installed, the script performs a
    second test: unpacks the source distribution into a temporary directory,
    then builds a second source distribution, and compares the file list again.

    Alternatively it may be a better idea to export the source tree into a
    temporary directory, build an sdist there, then compare it with the version
    control list?

Features currently implemented:

    * getting file list from Subversion (executes svn in a subprocess)
    * getting file list from Mercurial (executes hg in a subprocess)
    * getting file list from Git (executes git in a subprocess)
    * getting file list from Bazaar (executes bzr in a subprocess)
    * comparing it with the list of files in a .tar.gz source distribution

It is currently usable for checking if you can produce complete source
distributions for uploading to PyPI, provided that your package lives in SVN.

It's not usable for checking the completeness of a MANIFEST.in: the presence
of the right setuptools plugin on your system might mean you're getting a
complete sdist even without a complete MANIFEST.in.  (That's why the plan
talks about a second sdist and/or VCS export.)

The current implementation probably doesn't work on Windows.
"""

import argparse
import re
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from contextlib import contextmanager


__version__ = '0.6'
__author__ = 'Marius Gedminas <marius@gedmin.as>'
__licence__ = 'GPL v2 or later' # or ask me for MIT
__url__ = 'https://gist.github.com/4277075' # for now


class Failure(Exception):
    """An expected failure (as opposed to a bug in this script)."""


#
# User interface
#

_to_be_continued = False
def _check_tbc():
    global _to_be_continued
    if _to_be_continued:
        print
        _to_be_continued = False


def info(message):
    _check_tbc()
    print message


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
    print message
    _to_be_continued = False


def error(message):
    _check_tbc()
    print >> sys.stderr, message


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
        Failure.__init__("%s failed (status %s):\n%s" % (
                               command, status, output))


def run(command):
    """Run a command [cmd, arg1, arg2, ...].

    Returns the output (stdout + stderr).

    Raises CommandFailed in cases of error.
    """
    pipe = subprocess.Popen(command, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    output, _ = pipe.communicate()
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


def get_vcs_files():
    """List all files under version control in the current directory."""
    if os.path.exists('.svn'):
        return get_svn_files()
    if os.path.exists('.hg'):
        return get_hg_files()
    if os.path.exists('.git'):
        return get_git_files()
    if os.path.exists('.bzr'):
        return get_bzr_files()
    raise Failure("Couldn't find version control data (git/hg/bzr/svn supported)")


def get_git_files():
    """List all files versioned by git in the current directory."""
    output = run(['git', 'ls-files'])
    return add_directories(output.splitlines())


def get_hg_files():
    """List all files under Mercurial control in the current directory."""
    output = run(['hg', 'status', '-ncam'])
    return add_directories(output.splitlines())


def get_bzr_files():
    """List all files versioned in Bazaar in the current directory."""
    output = run(['bzr', 'ls', '-VR'])
    return strip_slashes(output.splitlines())


def get_svn_files():
    """List all files under SVN control in the current directory."""
    # XXX: augh, this does network traffic... and only looks at the files
    # in the last revision you got when you svn up'ed -- if you svn add new
    # files, they won't be shown, even after commit, until you do an update
    # again!
    # I should use svn st -v perhaps, or do an sdist from an svn export
    output = run(['svn', 'ls', '-R', '--non-interactive'])
    return strip_slashes(output.splitlines())


def strip_slashes(names):
    """Svn/Bzr print directory names with trailing slashes.  Strip them."""
    return [name.rstrip('/') for name in names]


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

IGNORE = set([
    'PKG-INFO',  # always generated
    'setup.cfg', # always generated, sometimes also kept in source control
    # it's not a problem if the sdist is lacking these files:
    '.hgtags', '.hgignore', '.gitignore', '.bzrignore',
])

SUGGESTIONS = [(re.compile(pattern), suggestion) for pattern, suggestion in [
    # regexp -> suggestion
    ('^([^/]+[.](cfg|ini))$',       r'include \1'),
    ('^([A-Z]+)$',                  r'include \1'),
    ('^[^/]+[.](txt|rst|py)$',      r'include *.\1'),
    ('^([a-zA-Z_][a-zA-Z_0-9]*)/'
     '.*[.](py|zcml|pt|mako|xml|html|txt|rst|css|png|jpg|dot|po|pot|mo|ui|desktop|bat)$',
                                    r'recursive-include \1 *.\2'),
    ('^([a-zA-Z_][a-zA-Z_0-9]*)/(Makefile)$',
                                    r'recursive-include \1 \2'),
]]



def strip_sdist_extras(filelist):
    """Strip generated files that are only present in source distributions."""
    return [name for name in filelist
            if name not in IGNORE
               and not name.endswith('.egg-info')
               and '.egg-info/' not in name]


def find_suggestions(filelist):
    """Suggest MANIFEST.in patterns for missing files."""
    suggestions = set()
    for filename in filelist:
        for pattern, suggestion in SUGGESTIONS:
            m = pattern.match(filename)
            if m is not None:
                suggestions.add(pattern.sub(suggestion, filename))
    return sorted(suggestions)


def is_package(source_tree='.'):
    """Is the directory the root of a Python package?

    Note: the term "package" here refers to a collection of files
    with a setup.py, not to a directory with an __init__.py.
    """
    return os.path.exists(os.path.join(source_tree, 'setup.py'))


def check_manifest(source_tree='.', create=False, update=False):
    """Compare a generated source distribution with list of files in a VCS.

    Returns True if the manifest is fine.
    """
    with cd(source_tree):
        if not is_package(source_tree):
            raise Failure('This is not a Python project (no setup.py).')
        info_begin("listing source files under version control")
        source_files = sorted(strip_sdist_extras(get_vcs_files()))
        info_continue(": %d files and directories" % len(source_files))
        info_begin("building an sdist")
        with mkdtemp('-sdist') as tempdir:
            run(['python', 'setup.py', 'sdist', '-d', tempdir])
            sdist_filename = get_one_file_in(tempdir)
            info_continue(": %s" % os.path.basename(sdist_filename))
            sdist_files = sorted(strip_sdist_extras(strip_toplevel_name(
                                    get_archive_file_list(sdist_filename))))
            info_continue(": %d files and directories" % len(sdist_files))
        if source_files != sdist_files:
            error("files in version control do not match the sdist!\n%s"
                  % format_difference(source_files, sdist_files,
                                      "VCS", "sdist"))
            missing_files = set(source_files) - set(sdist_files)
            suggestions = find_suggestions(missing_files)
            if suggestions:
                info("suggested MANIFEST.in rules:\n%s"
                     % format_list(suggestions))
                if update or (create and not os.path.exists('MANIFEST.in')):
                    with open('MANIFEST.in', 'a') as f:
                        if f.tell() == 0:
                            info("creating MANIFEST.in")
                        else:
                            info("updating MANIFEST.in")
                            f.write('\n# added by check_manifest.py\n')
                        f.write('\n'.join(suggestions) + '\n')
            return False
        else:
            info("files in version control match files in the sdist")
        return True


#
# Main script
#

def main():
    parser = argparse.ArgumentParser(
        description="Check a Python MANIFEST.in file for completeness",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('source_tree', default='.', nargs='?',
        help='location for the source tree')
    parser.add_argument('-c', '--create', action='store_true',
        help='create a MANIFEST.in if missing')
    parser.add_argument('-u', '--update', action='store_true',
        help='append suggestions to MANIFEST.in (implies --create)')
    args = parser.parse_args()
    try:
        if not check_manifest(args.source_tree, create=args.create,
                              update=args.update):
            sys.exit(1)
    except Failure, e:
        error(e)
        sys.exit(2)


if __name__ == '__main__':
    main()