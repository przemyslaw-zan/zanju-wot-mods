"""Compare the translation files that a pull request changes with the English source.

Usage: python3 -I check_i18n.py <base> <head>

<base> and <head> are commits, for example the base SHA and the head SHA of the pull request.
The script reads the files with `git show`. It does not check out or run code from the pull request.
It prints one block per changed translation file. Lines that start with "PROBLEM" need a review note.
Lines that start with "NOTE" need a look, but they are often correct.
"""

import re
import subprocess
import sys

KEY_LINE = re.compile(r'^([A-Z0-9_]+):\s*"((?:[^"\\]|\\.)*)"\s*$')
PLACEHOLDER = re.compile(r"\{\w+\}")
TAG = re.compile(r"</?[A-Za-z]+[^>]*>")
TEMPLATE_HEADER = "# Auto-generated translation template"
EXPECTED_FILE = re.compile(r"(/i18n/[^/]+\.yml|(^|/)README\.md)$")


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def read_file(commit, path):
    try:
        return git("show", "{0}:{1}".format(commit, path))
    except subprocess.CalledProcessError:
        return None


def parse(text):
    """Return the keys and values, and the lines that are not a comment, a blank line, or a key."""
    keys, bad_lines = {}, []
    for number, line in enumerate(text.splitlines(), 1):
        match = KEY_LINE.match(line)
        if match:
            keys[match.group(1)] = match.group(2)
        elif line.strip() and not line.lstrip().startswith("#"):
            bad_lines.append((number, line))
    return keys, bad_lines


def tokens(value):
    return {
        "placeholders": sorted(PLACEHOLDER.findall(value)),
        "tags": sorted(TAG.findall(value)),
        "line breaks (\\n)": value.count("\\n"),
    }


def check_file(base, head, path):
    print("== {0}".format(path))
    source_text = read_file(base, path.rsplit("/", 1)[0] + "/en.yml")
    text = read_file(head, path)
    if source_text is None or text is None:
        print("PROBLEM: cannot read the file or its en.yml.")
        return
    source, _ = parse(source_text)
    translation, bad_lines = parse(text)
    filled = {key for key, value in translation.items() if value}
    print("Filled: {0}/{1}".format(len(filled & source.keys()), len(source)))
    missing = sorted(source.keys() - filled)
    if missing:
        print("Missing or empty (falls back to English): {0}".format(", ".join(missing)))
    for key in sorted(translation.keys() - source.keys()):
        print("PROBLEM: key not in en.yml: {0}".format(key))
    for number, line in bad_lines:
        print("PROBLEM: line {0} is not a flat KEY: \"value\" line: {1}".format(number, line))
    if text.startswith(TEMPLATE_HEADER):
        print("PROBLEM: the file starts with the header of _template.yml.")
    for key in sorted(filled & source.keys()):
        expected, actual = tokens(source[key]), tokens(translation[key])
        for name in expected:
            if expected[name] != actual[name]:
                print("PROBLEM: {0}: {1} differ: en {2}, translation {3}".format(
                    key, name, expected[name], actual[name]))
        # A translation can use the quote marks of its language in place of \", so this is only a note.
        if source[key].count('\\"') != translation[key].count('\\"'):
            print("NOTE: {0}: the number of \\\" differs. Make sure that the quote marks are correct.".format(key))


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    base, head = argv[1], argv[2]
    changed = git("diff", "--name-only", "{0}...{1}".format(base, head)).split()
    for path in changed:
        if not EXPECTED_FILE.search(path):
            print("PROBLEM: the pull request also changes {0}. Review it with more care.".format(path))
    translations = [
        path for path in changed
        if re.search(r"/i18n/[^/]+\.yml$", path) and not path.endswith(("/en.yml", "/_template.yml"))
    ]
    if not translations:
        print("The pull request changes no translation file.")
    for path in translations:
        check_file(base, head, path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
