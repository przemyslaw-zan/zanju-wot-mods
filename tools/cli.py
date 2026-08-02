"""Single `zwm` entrypoint that dispatches to the repo tool modules.

    zwm <command> [args...]

Each command maps to a `tools.commands.<module>` whose `main()` reads `sys.argv`; this is
the human-facing alias for `python3 -m tools.commands.<module>`. Run `zwm help` for the list.
"""

import importlib
import sys

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
    # The target main() reads sys.argv[1:]; drop the `zwm <command>` prefix for it.
    sys.argv = ["zwm {}".format(command), *argv[1:]]
    return module.main()


if __name__ == "__main__":
    sys.exit(main())
