"""
Development/test quick cycle helper for WoT mods.

Runs cleanup + build + deploy in one command.

Usage:
    zwm cycle --all
    zwm cycle research-progress-bar
    zwm cycle mod-a mod-b
    zwm cycle --dry-run
    zwm cycle --fresh-log
    zwm cycle --verbose research-progress-bar
    python -m tools.commands.cycle research-progress-bar

Behavior:
- With --all: cycles all mods under mods/
- With mod args: cycles only selected mods
- With --dry-run: runs cleanup in dry-run mode and skips build + deploy
- With --fresh-log: truncates game.log before cycle (no archive, opt-in)
- Close WoT before cycling (no automatic running-process check; in-use files are skipped)
- The cycle updates files on disk only; WoT must be restarted to load changed
    Python/UI/package assets.
"""

from __future__ import annotations

import os
import subprocess
import sys

from ..core.console import detail, section, success
from ..core.env import load_env
from ..core.mod_cli import resolve_mod_targets, run_entrypoint, split_targeting_args


def fresh_log(dry_run):
    env = load_env()
    game_dir = env.get("WOT_GAME_DIR", "")
    if not game_dir:
        raise RuntimeError("WOT_GAME_DIR is not set (required for --fresh-log).")

    # game.log, not python.log: client 2.4.0.0 writes Python logging into game.log and leaves
    # python.log empty. game.log also appends across launches, so a truncation here is the only
    # thing separating this cycle's lines from every earlier session's.
    log_path = os.path.join(game_dir, "game.log")

    if dry_run:
        success("Dry-run: fresh log would be created")
        detail("Path: {}".format(log_path), verbose=True)
        return

    os.makedirs(game_dir, exist_ok=True)
    with open(log_path, "w", encoding="utf-8"):
        pass
    success("Fresh log created")
    detail("Path: {}".format(log_path), verbose=True)


def run_cmd(cmd, verbose=False):
    detail("Running: {}".format(" ".join(cmd)), verbose=verbose)
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError as exc:
        # The sub-command has already printed why it failed; repeating its traceback here
        # buries that under a stack from this process, which did nothing wrong.
        # cmd is [python, "-m", <module>, ...]; name the step, not the interpreter.
        step = cmd[2] if len(cmd) > 2 and cmd[1] == "-m" else cmd[0]
        raise RuntimeError(
            "cycle stopped: {} failed (exit {})".format(step, exc.returncode)
        ) from None


def parse_args(argv):
    flags, mod_names = split_targeting_args(
        argv,
        {
            "--dry-run": "dry_run",
            "--all": "run_all",
            "--fresh-log": "fresh_log",
            "--verbose": "verbose",
        },
    )
    return flags["dry_run"], flags["run_all"], flags["fresh_log"], flags["verbose"], mod_names


def _subcommand_cmd(module, run_all, verbose, mod_names, extra_flags=()):
    cmd = [sys.executable, "-m", module]
    if run_all:
        cmd.append("--all")
    else:
        cmd.extend(mod_names)
    cmd.extend(extra_flags)
    if verbose:
        cmd.append("--verbose")
    return cmd


def _main():
    dry_run, run_all, fresh_log_flag, verbose, requested_mods = parse_args(sys.argv[1:])
    mod_names = resolve_mod_targets(run_all, requested_mods, "cycle")
    if mod_names is None:
        return

    if fresh_log_flag:
        fresh_log(dry_run)

    section("Step 1/3: cleanup")
    cleanup_extra = ["--dry-run"] if dry_run else []
    run_cmd(_subcommand_cmd("tools.commands.cleanup", run_all, verbose, mod_names, cleanup_extra), verbose=verbose)

    if dry_run:
        success("Dry-run mode: build + deploy steps skipped.")
        return

    section("Step 2/3: build")
    run_cmd(_subcommand_cmd("tools.commands.build", run_all, verbose, mod_names), verbose=verbose)

    section("Step 3/3: deploy")
    run_cmd(_subcommand_cmd("tools.commands.deploy", run_all, verbose, mod_names), verbose=verbose)

    section("Cycle complete")
    success("Cleanup + build + deploy finished.")
    success("Next step: launch WoT to load the updated mod package.")


def main():
    return run_entrypoint(_main)


if __name__ == "__main__":
    main()
