#!/usr/bin/env -S uv run --script
# /// script
# dependencies = [
#   "pyyaml",
# ]
# ///

import argparse
import pathlib
import shlex
import shutil
import subprocess
import sys

import yaml


REPO = "mgedmin/check-manifest"
BRANCH = "master"


here = pathlib.Path(__file__).parent


def pretty_print_command(command: list[str], width: int | None = None) -> None:
    terminal_width = shutil.get_terminal_size().columns - 2
    if not width:
        width = terminal_width - 2  # leave space for the \ at the end

    words: list[str] = []
    can_join = False
    for arg in command:
        if arg.startswith('-'):
            can_join = False
        if can_join:
            words[-1] += ' ' + shlex.quote(arg)
            can_join = False
        else:
            words.append(shlex.quote(arg))
            if arg.startswith('-'):
                can_join = True

    indent = ' ' * len(words[0])

    lines: list[str] = []
    cur_line: list[str] = []
    cur_width = 0
    for word in words:
        space_len = 1 if cur_line else 0
        if cur_width + space_len + len(word) <= width:
            # word fits
            cur_line.append(word)
            cur_width += space_len + len(word)
        else:
            # word does not fit, need to wrap
            cur_line.append('\\')
            lines.append(' '.join(cur_line))
            cur_line = [indent, word]
            cur_width = len(indent) + 1 + len(word)
    if cur_line:
        lines.append(' '.join(cur_line))

    # align the \ on the right
    longest_width = max(
        len(line) for line in lines if len(line) <= terminal_width
    )
    lines[:-1] = [
        line.rstrip('\\').ljust(longest_width) + '\\'
        for line in lines[:-1]
    ]

    print(*lines, sep='\n')


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update GitHub branch protection rules"
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Print the gh api command without executing it",
    )
    args = parser.parse_args()

    with open(here / "workflows" / "build.yml") as fp:
        workflow = yaml.safe_load(fp)
        test_name_template = workflow['jobs']['build']['name']
        lint_name_template = workflow['jobs']['lint']['name']
        test_matrix = workflow['jobs']['build']['strategy']['matrix']
        lint_matrix = workflow['jobs']['lint']['strategy']['matrix']

    assert '${{ matrix.python-version }}' in test_name_template
    assert '${{ matrix.os }}' in test_name_template
    assert '${{ matrix.vcs }}' in test_name_template
    pythons = test_matrix['python-version']
    oses = test_matrix['os']
    vcses = test_matrix['vcs']
    test_names = [
        test_name_template
        .replace('${{ matrix.python-version }}', python_version)
        .replace('${{ matrix.os }}', os)
        .replace('${{ matrix.vcs }}', vcs)
        for python_version in pythons
        for os in oses
        for vcs in vcses
    ]

    assert lint_name_template == '${{ matrix.toxenv }}'
    lint_names = lint_matrix['toxenv']

    check_names = test_names + lint_names

    command = [
        'gh',
        'api',
        '-X', 'PUT',
        "-H", "Accept: application/vnd.github+json",
        "-H", "X-GitHub-Api-Version: 2022-11-28",
        (
            f"/repos/{REPO}/branches/{BRANCH}/protection/"
            "required_status_checks/contexts"
        ),
    ]
    for name in check_names:
        command += ["-f", f"contexts[]={name}"]

    # Using a shorter width because I don't want multiple -f contexts[]=one -f
    # contexts[]=two args to be squished into each line near the end
    pretty_print_command(command, width=40)
    if not args.dry_run:
        rc = subprocess.run(command).returncode
        sys.exit(rc)


if __name__ == "__main__":
    main()
