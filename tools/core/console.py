"""Small console-output helpers for readable CLI logs."""

from __future__ import print_function

import os
import sys

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"


def _supports_color():
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stdout.isatty()


def _style(text, *codes):
    if not _supports_color():
        return text
    return "{}{}{}".format("".join(codes), text, _RESET)


def section(title):
    print()
    print(_style("== {} ==".format(title), _BOLD, _CYAN))


def success(message):
    print(_style(message, _GREEN))


def warning(message):
    print(_style(message, _YELLOW))


def detail(message, verbose=False):
    if verbose:
        print(_style("  {}".format(message), _DIM))


def dim(message):
    """Print de-emphasised text that should not compete with a command's own output."""

    print(_style(message, _DIM))
