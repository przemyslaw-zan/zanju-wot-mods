"""Single `zwm` entrypoint that dispatches to the repo tool modules.

    zwm <command> [args...]

Each command maps to a `tools.commands.<module>` whose `main()` reads `sys.argv`; this is
the human-facing alias for `python3 -m tools.commands.<module>`. Run `zwm help` for the list.
"""

import importlib
import sys

from tools.core.mod_cli import UsageError

# subcommand -> tools.commands submodule that exposes main()
_COMMANDS = {
    "build": "build",
    "lint": "lint",
    "test": "test",
    "cycle": "cycle",
    "deploy": "deploy",
    "cleanup": "cleanup",
    "fetch-companion-artifacts": "fetch_companion_artifacts",
    "update-companion-manifest": "update_companion_manifest",
    "update-wot-version-manifest": "update_wot_version_manifest",
}


def _print_help():
    print("usage: zwm <command> [args...]")
    print()
    print("commands:")
    for name in _COMMANDS:
        print("  {}".format(name))
    print("  help")


def _print_command_help(command, module):
    """Print the command module's own docstring as its usage text.

    Every command already documents its flags and shows worked examples there, so this stays
    correct by construction rather than being a second list to keep in step.
    """
    print((module.__doc__ or "").strip())


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("help", "-h", "--help"):
        _print_help()
        return 0

    command = argv[0]
    module_name = _COMMANDS.get(command)
    if module_name is None:
        sys.stderr.write("zwm: unknown command '{}'\n\n".format(command))
        _print_help()
        return 2

    module = importlib.import_module("tools.commands.{}".format(module_name))

    # Only intercept help for the hand-rolled parsers. Commands built on argparse print a
    # better, flag-level help of their own, and stealing -h from them would be a downgrade.
    if (module.__doc__ or "").strip() and any(a in ("-h", "--help") for a in argv[1:]):
        _print_command_help(command, module)
        return 0

    # The target main() reads sys.argv[1:]; drop the `zwm <command>` prefix for it.
    sys.argv = ["zwm {}".format(command), *argv[1:]]
    try:
        return module.main()
    except UsageError as exc:
        # The invocation was never valid, so show what a valid one looks like. A failure
        # during the work itself is a RuntimeError and reports itself instead.
        sys.stderr.write("zwm {}: {}\n\n".format(command, exc))
        _print_command_help(command, module)
        return 2


if __name__ == "__main__":
    sys.exit(main())
