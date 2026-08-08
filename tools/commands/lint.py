from __future__ import print_function

import argparse
import glob
import io
import os
import subprocess
import sys

from ..core.console import detail, section, success, warning
from ..core.env import load_env, subprocess_env
from ..core.i18n_audit import (
    audit_code_key_coverage,
    check_readme_coverage,
    check_templates,
    compute_translation_coverage,
    write_readme_coverage,
    write_templates,
)
from ..core.paths import REPO_ROOT

try:
    from shutil import which as find_executable
except ImportError:
    from distutils.spawn import find_executable  # type: ignore


# Python 2.7 inside the toolchain image; used when no override / env var is given.
DEFAULT_PY2_EXE = "/opt/python2.7/bin/python2.7"
SAFE_AUTOPEP8_SELECT = "E1,E2,E3,W291,W292,W293,W391"
COMMAND_CHOICES = (
    "check",
    "fix",
    "py3-check",
    "py3-format",
    "py3-format-check",
    "py3-lint",
    "py27-lint",
    "py27-format",
    "py27-format-check",
    "i18n",
    "i18n-check",
)
ALIAS_COMMANDS = {
    "py3-check": ("check", {"py3_only": True}),
    "py3-format-check": ("py3-format", {"check": True}),
    "py27-format-check": ("py27-format", {"check": True}),
}
_CI_ENV_VARS = ("CI", "GITHUB_ACTIONS", "GITLAB_CI", "TF_BUILD", "BUILD_BUILDID")


def quote_arg(value):
    if any(ch in value for ch in (" ", "\t")):
        return '"{}"'.format(value)
    return value


def format_command(cmd):
    return " ".join(quote_arg(part) for part in cmd)


def env_flag(name):
    value = os.environ.get(name)
    if value is None:
        return False
    return value.strip().lower() not in ("", "0", "false", "no")


def default_verbose():
    return any(env_flag(name) for name in _CI_ENV_VARS)


def _to_text(value):
    if value is None:
        return ""
    if isinstance(value, type("")):
        return value
    try:
        return value.decode("utf-8", "replace")
    except AttributeError:
        return "{}".format(value)


def execute_command(cmd, verbose=False):
    if verbose:
        returncode = subprocess.call(cmd, cwd=REPO_ROOT, env=subprocess_env())
        return {"returncode": returncode, "stdout": "", "stderr": ""}

    process = subprocess.Popen(
        cmd, cwd=REPO_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=subprocess_env()
    )
    stdout, stderr = process.communicate()
    return {
        "returncode": process.returncode,
        "stdout": _to_text(stdout),
        "stderr": _to_text(stderr),
    }


def run_command(cmd, title, success_message=None, verbose=False):
    section(title)
    try:
        if verbose:
            detail("Command: {}".format(format_command(cmd)), verbose=True)
        result = execute_command(cmd, verbose=verbose)
    except OSError as exc:
        raise RuntimeError("Failed to run {}: {}".format(cmd[0], exc))

    if result["returncode"] != 0:
        if verbose:
            raise RuntimeError("{} failed with exit code {}".format(title, result["returncode"]))

        message = ["{} failed.".format(title), "Command: {}".format(format_command(cmd))]
        if result["stdout"]:
            message.append(result["stdout"].rstrip())
        if result["stderr"]:
            message.append(result["stderr"].rstrip())
        raise RuntimeError("\n".join(message))

    if success_message:
        success(success_message)


def expand_patterns(patterns):
    paths = []
    seen = set()
    for pattern in patterns:
        abs_pattern = os.path.join(REPO_ROOT, pattern)
        matches = glob.glob(abs_pattern)
        if not matches and not any(ch in pattern for ch in ("*", "?", "[")) and os.path.exists(abs_pattern):
            matches = [abs_pattern]
        for abs_path in sorted(matches):
            rel_path = os.path.relpath(abs_path, REPO_ROOT)
            if rel_path in seen:
                continue
            seen.add(rel_path)
            paths.append(rel_path)
    return paths


def get_py3_targets():
    return expand_patterns(
        [
            os.path.join("tools", "*.py"),
            os.path.join("mods", "*", "ui", "compile_ui.py"),
            # Release automation runs on the CI host's Python 3 rather than in the toolchain
            # image, but it is maintained like the rest of the Python 3 tooling, so it is
            # held to the same formatting and lint rules.
            os.path.join(".github", "scripts", "*.py"),
        ]
    )


def get_py27_targets():
    # Mod tests run on Python 2.7 against the mod runtime, and testing/ holds the shared
    # 2.7 launcher, so all three are linted with the same 2.7 rules as mods/<name>/src.
    return expand_patterns(
        [
            os.path.join("mods", "*", "src"),
            os.path.join("mods", "*", "tests"),
            "testing",
        ]
    )


def check_py27_source_encoding(targets):
    """Fail on non-ASCII Python 2.7 sources that lack a PEP 263 encoding declaration.

    Python 2 defaults to ASCII source, so such a file cannot be imported -- but this
    slips past both other gates: flake8 does not report it, and `py_compile` (what the
    build uses) accepts the file and emits a working .pyc. The breakage therefore only
    appears when something imports the source, such as the mod's own unit tests.
    """
    offenders = []
    for target in targets:
        abs_target = os.path.join(REPO_ROOT, target)
        paths = [abs_target]
        if os.path.isdir(abs_target):
            paths = [
                os.path.join(dirpath, name)
                for dirpath, _, filenames in os.walk(abs_target)
                for name in filenames
                if name.endswith(".py")
            ]
        for path in paths:
            if not path.endswith(".py"):
                continue
            with io.open(path, "rb") as handle:
                raw = handle.read()
            if all(byte < 0x80 for byte in bytearray(raw)):
                continue
            first_lines = raw.split(b"\n")[:2]
            if any(b"coding:" in line or b"coding=" in line for line in first_lines):
                continue
            offenders.append(os.path.relpath(path, REPO_ROOT))

    if offenders:
        raise RuntimeError(
            "Non-ASCII Python 2.7 source without a `# -*- coding: utf-8 -*-` header "
            "(Python 2 cannot import these):\n  " + "\n  ".join(sorted(offenders))
        )


def resolve_command_path(value, label):
    if os.path.isabs(value) or os.path.isfile(value):
        if not os.path.exists(value):
            raise RuntimeError("{} does not exist: {}".format(label, value))
        return value

    resolved = find_executable(value)
    if not resolved:
        raise RuntimeError("{} was not found: {}".format(label, value))
    return resolved


def resolve_py27_python(override):
    if override:
        return resolve_command_path(override, "Python 2.7 executable override")

    env = load_env()
    py27_python = env.get("WOT_PYTHON2_EXE", "").strip() or DEFAULT_PY2_EXE
    return resolve_command_path(py27_python, "WOT_PYTHON2_EXE")


def python_has_module(python_executable, module_name):
    cmd = [python_executable, "-c", "import {0}".format(module_name)]
    try:
        with io.open(os.devnull, "wb") as devnull:
            return subprocess.call(
                cmd, cwd=REPO_ROOT, stdout=devnull, stderr=devnull, env=subprocess_env()
            ) == 0
    except OSError:
        return False


def ensure_py27_lint_runtime(py27_python):
    if python_has_module(py27_python, "flake8"):
        return

    quoted_python = quote_arg(py27_python)
    raise RuntimeError(
        "Selected Python for py27 lint does not have Flake8 installed: {0}. "
        "Install the pinned lint dependency with: {1} -m pip install -r requirements-lint-py27.txt".format(
            py27_python,
            quoted_python,
        )
    )


def require_targets(targets, label):
    if targets:
        return targets
    warning("No {} targets found.".format(label))
    return []


def run_py3_format(check, verbose=False):
    targets = require_targets(get_py3_targets(), "Python 3")
    if not targets:
        return

    cmd = [sys.executable, "-m", "black"]
    if check:
        cmd.append("--check")
    cmd.extend(targets)
    run_command(
        cmd,
        "Python 3 format check" if check else "Python 3 format",
        success_message="Python 3 format check passed" if check else "Python 3 formatting applied",
        verbose=verbose,
    )


def run_py3_lint(fix, verbose=False):
    targets = require_targets(get_py3_targets(), "Python 3")
    if not targets:
        return

    cmd = [sys.executable, "-m", "ruff", "check"]
    if fix:
        cmd.append("--fix")
    cmd.extend(targets)
    run_command(
        cmd,
        "Python 3 lint" if not fix else "Python 3 lint fixes",
        success_message="Python 3 lint passed" if not fix else "Python 3 lint fixes complete",
        verbose=verbose,
    )


def run_py27_lint(py27_python, verbose=False):
    targets = require_targets(get_py27_targets(), "Python 2.7")
    if not targets:
        return

    ensure_py27_lint_runtime(py27_python)
    check_py27_source_encoding(targets)

    cmd = [py27_python, "-m", "tools.flake8_compat", "--config", ".flake8"]
    cmd.extend(targets)
    run_command(cmd, "Python 2.7 lint", success_message="Python 2.7 lint passed", verbose=verbose)


def run_py27_format(check, verbose=False):
    targets = require_targets(get_py27_targets(), "Python 2.7")
    if not targets:
        return

    cmd = [
        sys.executable,
        "-m",
        "autopep8",
        "--recursive",
        "--max-line-length",
        "120",
        "--select",
        SAFE_AUTOPEP8_SELECT,
    ]
    if check:
        cmd.extend(["--diff", "--exit-code"])
    else:
        cmd.append("--in-place")
    cmd.extend(targets)
    run_command(
        cmd,
        "Python 2.7 format check" if check else "Python 2.7 format",
        success_message="Python 2.7 format check passed" if check else "Python 2.7 formatting applied",
        verbose=verbose,
    )


def _raise_on_code_key_coverage():
    problems = audit_code_key_coverage()
    if problems:
        message = ["Localization key coverage failed (keys used in code but absent from en.yml):"]
        message.extend("  - {}".format(problem) for problem in problems)
        raise RuntimeError("\n".join(message))


def _report_translation_coverage(verbose=False):
    for mod_name, mod_coverage in sorted(compute_translation_coverage().items()):
        for lang in mod_coverage["languages"]:
            total = lang["total"] or 1
            percent = round(100.0 * lang["present"] / total)
            note = " ({0} missing)".format(len(lang["missing"])) if lang["missing"] else ""
            if lang["extra"]:
                note += " ({0} unknown)".format(len(lang["extra"]))
            detail(
                "{0}: {1} {2}% ({3}/{4}){5}".format(
                    mod_name, lang["code"], percent, lang["present"], lang["total"], note
                ),
                verbose=verbose,
            )


def run_i18n_check(verbose=False):
    section("Localization")
    _raise_on_code_key_coverage()

    # A language being incomplete never fails the build (translations are community-maintained),
    # but the generated files must be committed up to date -- a stale or missing README coverage
    # section or i18n template IS a failure. Contributors run `zwm lint i18n` and commit the result.
    problems = check_readme_coverage() + check_templates()
    if problems:
        message = ["Generated localization files are out of date or missing:"]
        message.extend("  - {0}".format(problem) for problem in problems)
        message.append("Run `zwm lint i18n` and commit the updated files.")
        raise RuntimeError("\n".join(message))

    success("Localization key coverage, README coverage, and i18n templates up to date")
    _report_translation_coverage(verbose=verbose)


def run_i18n_write(verbose=False):
    section("Localization")
    _raise_on_code_key_coverage()

    updated = write_readme_coverage()
    if updated:
        success("Refreshed translation coverage in README for: {0}".format(", ".join(updated)))
    else:
        success("Translation coverage READMEs already up to date")

    updated_templates = write_templates()
    if updated_templates:
        success("Refreshed i18n template for: {0}".format(", ".join(updated_templates)))
    else:
        success("i18n templates already up to date")
    _report_translation_coverage(verbose=verbose)


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="zwm lint",
        description="Run the repository Python format and lint workflow.",
        epilog=(
            "Defaults:\n"
            "  zwm lint                  Run the default 'check' workflow.\n"
            "\n"
            "Commands:\n"
            "  check                         Python 3 format-check + lint, then Python 2.7 lint + format-check.\n"
            "  fix                           Apply Python 3 Ruff fixes + Black formatting, then Python 2.7 lint.\n"
            "  py3-check                     Alias for: check --py3-only\n"
            "  py3-format                    Run Black on Python 3 targets.\n"
            "  py3-format-check             Alias for: py3-format --check\n"
            "  py3-lint                      Run Ruff on Python 3 targets.\n"
            "  py27-lint                     Run flake8 compatibility checks on Python 2.7 targets.\n"
            "  py27-format                   Run autopep8 on Python 2.7 targets.\n"
            "  py27-format-check            Alias for: py27-format --check\n"
            "  i18n                          Regenerate each mod's README coverage table and i18n template.\n"
            "  i18n-check                    Verify key coverage and that generated i18n files are current.\n"
            "\n"
            "Examples:\n"
            "  zwm lint\n"
            "  zwm lint --verbose\n"
            "  zwm lint fix --py3-only\n"
            "  zwm lint py3-format --check"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="check",
        metavar="COMMAND",
        choices=COMMAND_CHOICES,
        help="Command to run. Defaults to 'check'.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only with py3-format or py27-format; check formatting instead of rewriting files.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=default_verbose(),
        help="Show underlying commands and raw tool output. Enabled automatically when CI is detected.",
    )
    parser.add_argument(
        "--py3-only",
        action="store_true",
        help="Only with composite commands such as check or fix; skip the Python 2.7 surface.",
    )
    parser.add_argument(
        "--py27-only",
        action="store_true",
        help="Only with the default check workflow; skip the Python 3 surface.",
    )
    parser.add_argument(
        "--py27-python",
        help="Override the Python 2.7 executable used for flake8 when a command runs the Python 2.7 lint step.",
    )
    return parser.parse_args(argv)


def normalize_args(args):
    alias = ALIAS_COMMANDS.get(args.command)
    if not alias:
        return args

    command, overrides = alias
    args.command = command
    for name, value in overrides.items():
        setattr(args, name, value)
    return args


def command_runs_py27_lint(args):
    if args.py3_only:
        return False
    return args.command in ("check", "fix", "py27-lint")


def validate_args(args):
    if args.py3_only and args.py27_only:
        raise RuntimeError("Choose only one of --py3-only or --py27-only.")

    if args.py3_only and args.command not in ("check", "fix"):
        raise RuntimeError("--py3-only is only valid with the check or fix workflows.")

    if args.py27_only and args.command != "check":
        raise RuntimeError("--py27-only is only valid with the default check workflow.")

    if args.check and args.command not in ("py3-format", "py27-format"):
        if args.command == "check":
            raise RuntimeError(
                "The default command already runs checks. Use 'zwm lint', 'py3-format --check', "
                "or 'py27-format --check'."
            )
        raise RuntimeError("--check is only valid with py3-format or py27-format.")

    if args.command == "fix" and args.py27_only:
        raise RuntimeError("fix only applies Python 3 auto-fixes. Use py27-format explicitly.")

    if args.py27_python and not command_runs_py27_lint(args):
        raise RuntimeError("--py27-python is only valid when the selected workflow runs Python 2.7 lint.")


def run_check(args):
    if not args.py27_only:
        run_py3_format(check=True, verbose=args.verbose)
        run_py3_lint(fix=False, verbose=args.verbose)

    if not args.py3_only:
        run_py27_lint(resolve_py27_python(args.py27_python), verbose=args.verbose)
        run_py27_format(check=True, verbose=args.verbose)

    run_i18n_check(verbose=args.verbose)


def run_fix(args):
    run_py3_lint(fix=True, verbose=args.verbose)
    run_py3_format(check=False, verbose=args.verbose)

    if not args.py3_only:
        run_py27_lint(resolve_py27_python(args.py27_python), verbose=args.verbose)
        warning(
            "Note: Python 2.7 autoformatting stays explicit for now. "
            'Use "zwm lint py27-format-check" or "python -m tools.commands.lint py27-format-check" '
            "to review that diff first."
        )


def _main(argv=None):
    args = normalize_args(parse_args(argv or sys.argv[1:]))
    validate_args(args)

    if args.command == "check":
        run_check(args)
        section("Lint complete")
        success("All requested lint checks passed")
        return 0

    if args.command == "fix":
        run_fix(args)
        section("Lint complete")
        success("Requested Python 3 lint fixes and formatting applied")
        return 0

    if args.command == "py3-format":
        run_py3_format(check=args.check, verbose=args.verbose)
        return 0

    if args.command == "py3-lint":
        run_py3_lint(fix=False, verbose=args.verbose)
        return 0

    if args.command == "py27-lint":
        run_py27_lint(resolve_py27_python(args.py27_python), verbose=args.verbose)
        return 0

    if args.command == "py27-format":
        run_py27_format(check=args.check, verbose=args.verbose)
        return 0

    if args.command == "i18n":
        run_i18n_write(verbose=args.verbose)
        return 0

    if args.command == "i18n-check":
        run_i18n_check(verbose=args.verbose)
        return 0

    raise RuntimeError("Unsupported command: {}".format(args.command))


def main(argv=None):
    try:
        return _main(argv)
    except RuntimeError as exc:
        raise SystemExit(str(exc))


if __name__ == "__main__":
    sys.exit(main())
