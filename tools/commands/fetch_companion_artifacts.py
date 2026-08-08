"""Download the manifest-pinned companion artifacts into the ignored local cache."""

from __future__ import annotations

import sys

from ..core.mod_cli import run_entrypoint
from ..core.companion_artifacts import CompanionArtifactError, fetch_manifest_artifacts, load_manifest
from ..core.console import detail, section, success


def parse_args(argv):
    force = False
    verbose = False
    for arg in argv:
        if arg == "--force":
            force = True
            continue
        if arg == "--verbose":
            verbose = True
            continue
        raise RuntimeError("Unknown argument: {}".format(arg))
    return force, verbose


def _main():
    force, verbose = parse_args(sys.argv[1:])
    section("Fetch companion artifacts")
    manifest = load_manifest()
    results = fetch_manifest_artifacts(manifest=manifest, force=force)

    downloaded_count = 0
    verified_count = 0
    for result in results:
        if result["downloaded"]:
            downloaded_count += 1
        else:
            verified_count += 1
        if verbose:
            status = "downloaded" if result["downloaded"] else "verified"
            artifact = result["artifact"]
            detail("{}: {} -> {}".format(status, artifact["filename"], result["path"]), verbose=True)

    success(
        "Companion artifact cache ready (downloaded: {}, verified: {})".format(
            downloaded_count,
            verified_count,
        )
    )


def main():
    # run_entrypoint, not a guard under `if __name__`: zwm imports this module and calls
    # main() directly, so anything handled only in the __main__ block never ran for the
    # command's actual users -- domain errors reached them as tracebacks.
    return run_entrypoint(_main)


if __name__ == "__main__":
    sys.exit(main())
