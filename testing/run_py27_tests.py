# -*- coding: utf-8 -*-
"""Python 2.7 test launcher for a single mod's `tests/` directory.

Invoked by `zwm test` (tools/commands/test.py) with the mod's paths and identity:

    python2.7 testing/run_py27_tests.py --src mods/<name>/src --tests mods/<name>/tests \\
        --mod-id <meta id> --mod-name <meta name>

It installs the import environment (see zwm_test_env) and then runs stdlib unittest
discovery over `test_*.py`. Tests are plain `unittest.TestCase` classes so the same
files stay runnable by any unittest-compatible runner.
"""
from __future__ import print_function, unicode_literals

import argparse
import logging
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import zwm_test_env  # noqa: E402  (path set up above)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True, help="mod src/ directory")
    parser.add_argument("--tests", required=True, help="mod tests/ directory")
    parser.add_argument("--mod-id", default="", help="meta.xml id")
    parser.add_argument("--mod-name", default="", help="meta.xml name")
    parser.add_argument("--pattern", default="test_*.py", help="test file pattern")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    # Mod code logs through the stdlib logger; without a handler Python 2.7 prints
    # "No handlers could be found for logger ..." into the middle of the test report.
    # Tests that exercise error paths log on purpose, so swallow it rather than see it.
    logging.getLogger().addHandler(logging.NullHandler())

    zwm_test_env.install(src_dir=args.src, mod_id=args.mod_id, mod_name=args.mod_name)

    tests_dir = os.path.abspath(args.tests)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)

    suite = unittest.TestLoader().discover(tests_dir, pattern=args.pattern, top_level_dir=tests_dir)
    runner = unittest.TextTestRunner(verbosity=2 if args.verbose else 1)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
