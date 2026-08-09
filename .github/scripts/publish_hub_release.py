"""Republish the "Latest Releases" index that holds GitHub's Latest badge.

The index carries no assets of its own -- it is a table of links to the current release
of each mod, so the repository sidebar and ``/releases/latest`` always land somewhere
useful no matter which mod shipped most recently.

It is rendered from the releases that are actually published, not from ``meta.xml``, so
a partially failed run produces an index that matches reality and the next run repairs
it.

Each run publishes a new dated tag and then deletes the previous index. Creating before
deleting means the badge moves to the new index first, so there is no moment where the
repository has no latest release.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

from release_lib import (
    HUB_TAG_PREFIX,
    REPO_ROOT,
    TAG_SEPARATOR,
    gh_command,
    iter_mods,
    list_releases,
    read_wot_version,
    run_command,
    version_tuple,
    write_output,
)

NOTES_PATH = os.path.join(REPO_ROOT, ".tmp", "hub-release-notes.md")
HUB_TITLE = "Latest Releases"


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
        help="Commit the index tag is created at.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the rendered index without publishing or deleting anything.",
    )
    return parser.parse_args(argv)


def utc_now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def format_stamp(now):
    # Built without %-d/%#d so it stays portable across the Linux CI runner and local
    # Windows runs, matching the day-month-year style used in the mod changelogs.
    return "{day} {month} {year} {time} UTC".format(
        day=now.day, month=now.strftime("%B"), year=now.year, time=now.strftime("%H:%M")
    )


def format_release_date(timestamp):
    """Render gh's ISO-8601 publish timestamp as "8 August 2026".

    Degrades to a dash rather than raising: the date is decoration on an index that is
    rebuilt from scratch every release, so an unparseable value is not worth failing a
    publish over.
    """

    try:
        parsed = dt.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return "—"
    return "{day} {month} {year}".format(day=parsed.day, month=parsed.strftime("%B"), year=parsed.year)


def hub_tag(now):
    # Minute resolution: runs are serialised by the workflow's concurrency group and a
    # build takes minutes, so this cannot collide in practice -- and it never needs to,
    # because a fresh tag each time is the point.
    return "{}-{}".format(HUB_TAG_PREFIX, now.strftime("%Y-%m-%d-%H-%M"))


def find_current_releases(repo):
    """Map each mod to its highest published release, as seen on GitHub."""

    known_mods = {mod["acronym"]: mod for mod in iter_mods()}
    current = {}

    for release in list_releases(repo):
        tag = release.get("tagName") or ""
        if TAG_SEPARATOR not in tag:
            continue

        acronym, _, version = tag.partition(TAG_SEPARATOR)
        if acronym not in known_mods or not version:
            continue

        existing = current.get(acronym)
        if existing is None or version_tuple(version) > version_tuple(existing["version"]):
            current[acronym] = {
                "mod_name": known_mods[acronym]["mod_name"],
                "display_name": known_mods[acronym]["display_name"],
                "version": version,
                "tag": tag,
                "published_at": release.get("publishedAt") or "",
            }

    # Sorted by full name so the index table matches the order the README lists mods in.
    return sorted(current.values(), key=lambda release: release["display_name"])


def find_zip_asset(repo, tag):
    result = run_command(gh_command(["release", "view", tag, "--json", "assets"], repo), check=False)
    if result.returncode != 0:
        return None
    for asset in json.loads(result.stdout or "{}").get("assets") or []:
        if (asset.get("name") or "").endswith(".zip"):
            return asset["name"]
    return None


def render_notes(repo, releases, now):
    lines = [
        "The current release of each mod. Each row links straight to the download, and to "
        "that release's own page where its changelog entry lives.",
        "",
        "| Mod | Release | Released | Download |",
        "| --- | --- | --- | --- |",
    ]

    for release in releases:
        release_url = "https://github.com/{}/releases/tag/{}".format(repo, release["tag"])
        asset = find_zip_asset(repo, release["tag"])
        if asset:
            download = "[{}](https://github.com/{}/releases/download/{}/{})".format(asset, repo, release["tag"], asset)
        else:
            # No zip attached (an interrupted upload, say) -- an empty cell is honest about
            # that rather than dressing the release page up as a download.
            download = "—"
        lines.append(
            # The version itself is the link to that release's page, so the column carries
            # both facts without a second column repeating the version inside a tag.
            "| {} | [{}]({}) | {} | {} |".format(
                release["display_name"],
                release["version"],
                release_url,
                format_release_date(release["published_at"]),
                download,
            )
        )

    wot_version = read_wot_version()
    lines.append("")
    if wot_version:
        lines.append("- Target WoT client version: `{}`".format(wot_version))
    lines.append("- Index updated: `{}`".format(format_stamp(now)))
    lines.extend(
        [
            "",
            "> The `Source code` archives below are attached automatically by GitHub and are "
            "not mod downloads -- use the links in the table.",
        ]
    )
    return "\n".join(lines) + "\n"


def create_hub(repo, tag, commit, notes_path):
    args = ["release", "create", tag]
    if commit:
        args.extend(["--target", commit])
    # --latest is what keeps the index in the repository sidebar and behind
    # /releases/latest; every per-mod release opts out of it.
    args.extend(["--title", HUB_TITLE, "--notes-file", notes_path, "--latest"])
    run_command(gh_command(args, repo))


def is_index_tag(tag):
    return tag.startswith("{}-".format(HUB_TAG_PREFIX))


def delete_stale_hubs(repo, keep_tag):
    for release in list_releases(repo):
        tag = release.get("tagName") or ""
        if not is_index_tag(tag) or tag == keep_tag:
            continue
        # --cleanup-tag removes the dated tag too, so the tag list does not grow one
        # entry per release forever.
        run_command(gh_command(["release", "delete", tag, "--yes", "--cleanup-tag"], repo))
        print("removed stale index {}".format(tag))


def main(argv=None):
    args = parse_args(argv)

    releases = find_current_releases(args.repo)
    if not releases:
        raise RuntimeError("No per-mod releases are published yet, so there is nothing to index.")

    now = utc_now()
    tag = hub_tag(now)
    notes = render_notes(args.repo, releases, now)

    if args.dry_run:
        print("would publish index {} with:\n{}".format(tag, notes))
        return 0

    os.makedirs(os.path.dirname(NOTES_PATH), exist_ok=True)
    with open(NOTES_PATH, "w", encoding="utf-8") as fh:
        fh.write(notes)

    create_hub(args.repo, tag, args.commit, NOTES_PATH)
    print("published index {}".format(tag))

    delete_stale_hubs(args.repo, tag)

    write_output("hub_tag", tag)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None
