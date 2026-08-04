"""zwm test — run each mod's own unit tests.

Tests belong to the mods, not to this tooling: they exist to keep the shipped runtime
behaviour stable. A mod opts in simply by having a `tests/` directory; there is nothing
to register centrally.

Discovery inside `mods/<name>/tests/`:

    test_*.py        Python 2.7 unittest, run against the mod's src/ with the client
                     import environment faked in (see testing/zwm_test_env.py). Python
                     2.7 because that is what the WoT client runs.
    *.test.js        Gameface/browser JavaScript, run with Node's built-in test runner
                     (`node --test`). No npm dependencies are involved.
    run_tests.py     Escape hatch: if present, it is executed with Python 3 and owns the
                     whole run for that mod; nothing else is auto-discovered.

Node is optional: mods without JavaScript never need it, and when JS tests exist but
Node is missing the suite is reported as SKIPPED rather than failing, so the command
stays usable on toolchain images built before Node was added. Pass --strict (CI may
want this once the image ships Node) to turn such a skip into a failure.
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys

from ..core.console import detail, section, success, warning
from ..core.mod_cli import ensure_mod_dirs_exist, resolve_mod_targets, run_entrypoint
from ..core.mod_meta import read_meta
from ..core.paths import MODS_DIR, REPO_ROOT
from .lint import format_command, resolve_py27_python

try:
    from shutil import which as find_executable
except ImportError:  # pragma: no cover - Python 2 fallback, unused on the py3 toolchain
    from distutils.spawn import find_executable  # type: ignore

PY27_TEST_PATTERN = "test_*.py"
JS_TEST_PATTERN = "*.test.js"
HOOK_NAME = "run_tests.py"
PY27_RUNNER = os.path.join(REPO_ROOT, "testing", "run_py27_tests.py")

PASSED = "passed"
FAILED = "failed"
SKIPPED = "skipped"


def tests_dir_for(mod_name):
    return os.path.join(MODS_DIR, mod_name, "tests")


def find_test_files(tests_dir, pattern):
    return sorted(glob.glob(os.path.join(tests_dir, "**", pattern), recursive=True))


def run_command(cmd, cwd=None, verbose=False):
    detail("Running: {}".format(format_command(cmd)), verbose=verbose)
    return subprocess.call(cmd, cwd=cwd or REPO_ROOT)


def run_py27_suite(mod_name, tests_dir, verbose):
    meta = read_meta(mod_name)
    cmd = [
        resolve_py27_python(None),
        PY27_RUNNER,
        "--src",
        os.path.join(MODS_DIR, mod_name, "src"),
        "--tests",
        tests_dir,
        "--mod-id",
        meta["id"],
        "--mod-name",
        meta["name"],
        "--pattern",
        PY27_TEST_PATTERN,
    ]
    if verbose:
        cmd.append("--verbose")
    return PASSED if run_command(cmd, verbose=verbose) == 0 else FAILED


def run_js_suite(mod_name, tests_dir, verbose, strict):
    node = find_executable("node")
    if not node:
        message = "Node not found: JavaScript tests for {} were NOT run".format(mod_name)
        if strict:
            raise RuntimeError(message + " (--strict)")
        warning(message)
        return SKIPPED

    # Explicit file list rather than the tests/ directory. Node 18 reads a directory argument
    # as "discover test files here", but Node 20+ reads it as a module path and dies with
    # MODULE_NOT_FOUND before running a single test. Naming the files works on every version,
    # and they are already discovered to decide whether this suite runs at all.
    cmd = [node, "--test"] + find_test_files(tests_dir, JS_TEST_PATTERN)
    return PASSED if run_command(cmd, cwd=os.path.join(MODS_DIR, mod_name), verbose=verbose) == 0 else FAILED


def run_hook(mod_name, hook_path, verbose):
    cmd = [sys.executable, hook_path]
    if verbose:
        cmd.append("--verbose")
    return PASSED if run_command(cmd, cwd=os.path.join(MODS_DIR, mod_name), verbose=verbose) == 0 else FAILED


def test_mod(mod_name, verbose, strict):
    """Run every suite a mod declares. Returns a list of (label, outcome) pairs."""
    tests_dir = tests_dir_for(mod_name)
    if not os.path.isdir(tests_dir):
        detail("No tests/ directory", verbose=verbose)
        return []

    hook_path = os.path.join(tests_dir, HOOK_NAME)
    if os.path.isfile(hook_path):
        return [("{} (hook)".format(HOOK_NAME), run_hook(mod_name, hook_path, verbose))]

    results = []
    if find_test_files(tests_dir, PY27_TEST_PATTERN):
        results.append(("python2.7", run_py27_suite(mod_name, tests_dir, verbose)))
    if find_test_files(tests_dir, JS_TEST_PATTERN):
        results.append(("javascript", run_js_suite(mod_name, tests_dir, verbose, strict)))

    if not results:
        warning("tests/ exists but contains no {} or {} files".format(PY27_TEST_PATTERN, JS_TEST_PATTERN))
    return results


def parse_args(argv):
    run_all = False
    verbose = False
    strict = False
    targets = []
    for arg in argv:
        if arg == "--all":
            run_all = True
        elif arg == "--verbose":
            verbose = True
        elif arg == "--strict":
            strict = True
        else:
            targets.append(arg)
    return run_all, verbose, strict, targets


def _main():
    run_all, verbose, strict, requested = parse_args(sys.argv[1:])
    mod_names = resolve_mod_targets(run_all, requested, "test")
    if mod_names is None:
        return 0
    ensure_mod_dirs_exist(mod_names)

    outcomes = []
    for mod_name in mod_names:
        section("Testing {}".format(mod_name))
        for label, outcome in test_mod(mod_name, verbose, strict):
            outcomes.append((mod_name, label, outcome))

    section("Test summary")
    if not outcomes:
        warning("No mod declared tests (add mods/<name>/tests/)")
        return 0

    for mod_name, label, outcome in outcomes:
        line = "{}: {} {}".format(mod_name, label, outcome)
        if outcome == PASSED:
            success(line)
        else:
            warning(line)

    if any(outcome == FAILED for _, _, outcome in outcomes):
        raise RuntimeError("Tests failed")
    if any(outcome == SKIPPED for _, _, outcome in outcomes):
        warning("Some suites were skipped; see the notes above")
    success("All executed test suites passed")
    return 0


def main():
    return run_entrypoint(_main)


if __name__ == "__main__":
    sys.exit(main())
