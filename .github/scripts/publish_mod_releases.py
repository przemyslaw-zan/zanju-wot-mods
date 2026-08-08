"""Publish a release for every mod whose current version has not been released yet.

One rule drives all of it: a mod at version >= 1.0.0 with no release tagged
``<mod-dir>@<version>`` gets one. Bootstrapping the scheme, a new mod reaching 1.0.0,
and a day-to-day version bump are all the same case, which makes the step idempotent --
re-running it after a failure publishes exactly what is still missing.
"""

from __future__ import annotations

import argparse
import os
import sys

from release_lib import (
    REPO_ROOT,
    extract_changelog_section,
    gh_command,
    is_published_version,
    iter_mods,
    read_wot_version,
    release_exists,
    release_title,
    run_command,
    write_output,
)

NOTES_DIR = os.path.join(REPO_ROOT, ".tmp")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", "").strip(),
        help="owner/repo used for gh commands and links.",
    )
    parser.add_argument(
        "--commit",
        default=os.environ.get("GITHUB_SHA", "").strip(),
        help="Commit the release tag is created at.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be published without creating any release.",
    )
    return parser.parse_args(argv)


def render_notes(mod, repo, commit):
    # The title and tag are both acronyms, so the body carries the full name -- otherwise
    # nothing on the release page would say which mod this is.
    sections = [
        "**{}**".format(mod["display_name"]),
        "",
        extract_changelog_section(mod["changelog_path"], mod["version"]),
        "",
        "---",
        "",
    ]

    wot_version = read_wot_version()
    if wot_version:
        sections.append("- Target WoT client version: `{}`".format(wot_version))
    if repo and commit:
        sections.append(
            "- Full changelog: [CHANGELOG.md](https://github.com/{}/blob/{}/mods/{}/CHANGELOG.md)".format(
                repo, commit, mod["mod_name"]
            )
        )
        sections.append("- Built from commit [{}](https://github.com/{}/commit/{})".format(commit[:7], repo, commit))
    if repo:
        sections.extend(
            [
                "",
                "Download `{}` below, then follow "
                "[Installing Mods](https://github.com/{}/blob/master/docs/installing-mods.md).".format(
                    os.path.basename(mod["zip_path"]), repo
                ),
            ]
        )

    return "\n".join(sections).rstrip() + "\n"


def publish(mod, repo, commit, notes_path):
    if not os.path.isfile(mod["zip_path"]):
        raise RuntimeError(
            "Expected built release zip for {} at {}. Run the build before publishing.".format(
                mod["mod_name"], mod["zip_path"]
            )
        )

    args = ["release", "create", mod["tag"], mod["zip_path"]]
    if commit:
        args.extend(["--target", commit])
    args.extend(
        [
            "--title",
            release_title(mod["acronym"], mod["version"]),
            "--notes-file",
            notes_path,
            # Every per-mod release must opt out explicitly: make_latest defaults to true,
            # so a single omission moves the Latest badge off the index release.
            "--latest=false",
        ]
    )
    run_command(gh_command(args, repo))


def main(argv=None):
    args = parse_args(argv)
    os.makedirs(NOTES_DIR, exist_ok=True)

    published = []
    for mod in iter_mods():
        if not is_published_version(mod["version"]):
            print("skip {} {} (pre-1.0 versions stay internal)".format(mod["mod_name"], mod["version"]))
            continue

        if release_exists(args.repo, mod["tag"]):
            print("skip {} (already released)".format(mod["tag"]))
            continue

        notes = render_notes(mod, args.repo, args.commit)
        if args.dry_run:
            print("would publish {}\n{}".format(mod["tag"], notes))
            published.append(mod["tag"])
            continue

        notes_path = os.path.join(NOTES_DIR, "{}-notes.md".format(mod["bundle_name"]))
        with open(notes_path, "w", encoding="utf-8") as fh:
            fh.write(notes)

        publish(mod, args.repo, args.commit, notes_path)
        print("published {}".format(mod["tag"]))
        published.append(mod["tag"])

    write_output("published", str(len(published)))
    write_output("tags", " ".join(published))
    print("{} release(s) published".format(len(published)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None
