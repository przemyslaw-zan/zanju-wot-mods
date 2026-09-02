"""Compile the research progress bar Scaleform SWF."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-file",
        default=os.path.join(SCRIPT_DIR, "ResearchProgressBarLobby.as"),
        help="Path to the ActionScript entrypoint.",
    )
    parser.add_argument(
        "--output-file",
        default=os.path.join(
            SCRIPT_DIR,
            "build",
            "res",
            "gui",
            "flash",
            "research-progress-bar-lobby.swf",
        ),
        help="Path to the compiled SWF output.",
    )
    parser.add_argument(
        "--tooltip-source-file",
        default=os.path.join(SCRIPT_DIR, "ResearchProgressBarTooltipLobby.as"),
        help="Path to the tooltip view's ActionScript entrypoint.",
    )
    parser.add_argument(
        "--tooltip-output-file",
        default=os.path.join(
            SCRIPT_DIR,
            "build",
            "res",
            "gui",
            "flash",
            "research-progress-bar-tooltip.swf",
        ),
        help="Path to the compiled tooltip SWF output.",
    )
    parser.add_argument(
        "--api-source-dir",
        default=os.path.join(SCRIPT_DIR, "wot-api"),
        help="Directory containing local ActionScript WoT API mirror sources.",
    )
    parser.add_argument(
        "--api-swc",
        default=os.path.join(SCRIPT_DIR, "build", "wot-api.swc"),
        help="Path to the generated WoT API mirror SWC.",
    )
    parser.add_argument(
        "--target-player",
        default="32.0",
        help="Flash target player version passed to mxmlc.",
    )
    parser.add_argument(
        "--swf-version",
        default="17",
        help="SWF version passed to mxmlc.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress compiler command and tool output unless a step fails.",
    )
    return parser.parse_args(argv)


def require_tool(name):
    tool_path = shutil.which(name)
    if not tool_path:
        raise RuntimeError("{} was not found on PATH.".format(name))
    return tool_path


def run_cmd(cmd, quiet=False):
    if not quiet:
        print("Running: {}".format(" ".join(cmd)))
        subprocess.check_call(cmd)
        return

    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        command = " ".join(cmd)
        message = ["Command failed: {}".format(command)]
        if result.stdout:
            message.append(result.stdout.rstrip())
        if result.stderr:
            message.append(result.stderr.rstrip())
        raise RuntimeError("\n".join(message))


def run_cmd_verbose(cmd, label):
    print(label)
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)

    stdout_lines = [line for line in (result.stdout or "").splitlines() if line.strip()]
    stderr_lines = [line for line in (result.stderr or "").splitlines() if line.strip()]
    for line in stdout_lines + stderr_lines:
        if line.startswith("Loading configuration file "):
            continue
        print("  {}".format(line))

    if result.returncode != 0:
        raise RuntimeError("Command failed: {}".format(" ".join(cmd)))


def main(argv=None):
    args = parse_args(argv)
    compc = require_tool("compc")
    mxmlc = require_tool("mxmlc")

    source_dir = os.path.dirname(os.path.abspath(args.source_file))
    output_dir = os.path.dirname(os.path.abspath(args.output_file))
    api_dir = os.path.dirname(os.path.abspath(args.api_swc))

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(api_dir, exist_ok=True)

    api_arguments = [
        compc,
        "-output",
        os.path.abspath(args.api_swc),
        "-source-path={}".format(os.path.abspath(args.api_source_dir)),
        "-target-player={}".format(args.target_player),
        "-include-sources={}".format(os.path.abspath(args.api_source_dir)),
    ]
    if args.quiet:
        run_cmd(api_arguments, quiet=True)
    else:
        run_cmd_verbose(api_arguments, label="Compiling API SWC")
        print()

    def compile_swf(source_file, output_file, width, height, label):
        arguments = [
            mxmlc,
            "-output",
            os.path.abspath(output_file),
            "-source-path",
            source_dir,
            "-external-library-path+={}".format(os.path.abspath(args.api_swc)),
            "-static-link-runtime-shared-libraries=true",
            "-target-player={}".format(args.target_player),
            "-swf-version={}".format(args.swf_version),
            "-default-size",
            str(width),
            str(height),
            "-default-frame-rate",
            "30",
            os.path.abspath(source_file),
        ]
        if args.quiet:
            run_cmd(arguments, quiet=True)
        else:
            run_cmd_verbose(arguments, label=label)

    compile_swf(args.source_file, args.output_file, 1920, 220, "Compiling lobby SWF")

    # The tooltip is a view of its own so it can sit on its own window band: a band applies to a
    # whole view, and the bar and its tooltip want different ones. Full-screen, because the
    # tooltip is placed anywhere the cursor goes and is clamped against the stage.
    tooltip_output_dir = os.path.dirname(os.path.abspath(args.tooltip_output_file))
    os.makedirs(tooltip_output_dir, exist_ok=True)
    if not args.quiet:
        print()
    compile_swf(
        args.tooltip_source_file,
        args.tooltip_output_file,
        1920,
        1080,
        "Compiling tooltip SWF",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
