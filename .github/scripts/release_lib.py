"""Shared helpers for the per-mod release pipeline.

Release model:

- Each mod version gets its own write-once release, tagged ``<mod-dir>@<version>``
  (for example ``premium-time@1.0.1``). Once published it is never edited; a version
  bump in ``meta.xml`` is what produces the next one.
- A single "Latest Releases" index release holds GitHub's ``Latest`` badge, so the
  repository sidebar and ``/releases/latest`` always point at it. It carries no assets
  and only links to the per-mod releases.

The index is published under a rotating dated tag rather than a fixed one. That keeps
its displayed date current (GitHub has no API to refresh ``published_at`` on an existing
release, so an edited-in-place index would read as months old), and it means the
pipeline never has to reuse a tag name -- an operation that is permanently unavailable
once a name has been used by an immutable release.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
MODS_DIR = os.path.join(REPO_ROOT, "mods")
DIST_DIR = os.path.join(REPO_ROOT, "dist")
WOT_VERSION_MANIFEST_PATH = os.path.join(REPO_ROOT, "tools", "wot_version_manifest.json")

# Separator between mod name and version in a release tag. '@' rather than '-v' because
# every mod directory name already contains hyphens, and rather than '/' because a tag
# named "premium-time" could then never coexist with "premium-time/..." in the ref
# namespace, foreclosing a rolling per-mod tag later.
TAG_SEPARATOR = "@"

# Prefix for the rotating index tag; the date and time are appended per publish. A trial
# run needs no special prefix, since every run burns a fresh dated name anyway.
HUB_TAG_PREFIX = "index"


def run_command(cmd, check=True):
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if check and result.returncode != 0:
        message = ["Command failed: {}".format(" ".join(cmd))]
        if result.stdout:
            message.append(result.stdout.rstrip())
        if result.stderr:
            message.append(result.stderr.rstrip())
        raise RuntimeError("\n".join(message))
    return result


def gh_command(args, repo):
    cmd = ["gh"]
    if repo:
        cmd.extend(["-R", repo])
    cmd.extend(args)
    return cmd


def read_meta(mod_dir):
    root = ET.parse(os.path.join(mod_dir, "meta.xml")).getroot()
    return {
        "id": root.findtext("id", "").strip(),
        "name": root.findtext("name", "").strip(),
        "version": root.findtext("version", "").strip(),
    }


def read_wot_version():
    with open(WOT_VERSION_MANIFEST_PATH, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    return (manifest.get("wotClientVersion") or "").strip()


def version_tuple(version):
    """Parse a dotted version into a comparable tuple, ignoring any trailing suffix."""

    parts = []
    for chunk in version.split("."):
        match = re.match(r"^(\d+)", chunk)
        parts.append(int(match.group(1)) if match else 0)
    return tuple(parts)


def is_published_version(version):
    """0.x.x is treated as internal: a mod earns its first release when it reaches 1.0.0."""

    return version_tuple(version)[:1] >= (1,)


def release_tag(mod_name, version):
    return "{}{}{}".format(mod_name, TAG_SEPARATOR, version)


def release_title(display_name, version):
    return "{} {}".format(display_name, version)


def iter_mods():
    """Yield every mod under mods/, whether or not it is eligible for release."""

    if not os.path.isdir(MODS_DIR):
        return

    for mod_name in sorted(os.listdir(MODS_DIR)):
        mod_dir = os.path.join(MODS_DIR, mod_name)
        if not os.path.isfile(os.path.join(mod_dir, "meta.xml")):
            continue

        meta = read_meta(mod_dir)
        if not meta["id"] or not meta["version"]:
            raise RuntimeError("{} has missing id or version in meta.xml".format(mod_name))

        bundle_name = "{}_{}".format(meta["id"], meta["version"])
        yield {
            "mod_name": mod_name,
            "display_name": meta["name"] or mod_name,
            "mod_id": meta["id"],
            "version": meta["version"],
            "bundle_name": bundle_name,
            "zip_path": os.path.join(DIST_DIR, bundle_name, "{}.zip".format(bundle_name)),
            "changelog_path": os.path.join(mod_dir, "CHANGELOG.md"),
            "tag": release_tag(mod_name, meta["version"]),
        }


def extract_changelog_section(changelog_path, version):
    """Return the changelog entry for one version, without its heading.

    Missing or empty sections raise rather than publishing an empty release body: a
    version bump is the release signal, so a bump with no changelog entry is a mistake
    worth failing the build over.
    """

    if not os.path.isfile(changelog_path):
        raise RuntimeError("Missing changelog: {}".format(changelog_path))

    with open(changelog_path, "r", encoding="utf-8") as fh:
        lines = fh.read().splitlines()

    heading = re.compile(r"^##\s+" + re.escape(version) + r"(\s|$)")
    any_heading = re.compile(r"^##\s")

    collected = []
    capturing = False
    for line in lines:
        if capturing:
            if any_heading.match(line):
                break
            collected.append(line)
        elif heading.match(line):
            capturing = True

    if not capturing:
        raise RuntimeError(
            "No '## {}' section found in {}. Add the changelog entry for this version "
            "before releasing it.".format(version, changelog_path)
        )

    body = "\n".join(collected).strip()
    if not body:
        raise RuntimeError("The '## {}' section in {} is empty.".format(version, changelog_path))
    return body


def list_releases(repo):
    """Return every published release as {tagName, name, isLatest} dicts."""

    result = run_command(
        gh_command(["release", "list", "--limit", "500", "--json", "tagName,name,isLatest"], repo),
    )
    return json.loads(result.stdout or "[]")


def release_exists(repo, tag):
    result = run_command(gh_command(["release", "view", tag, "--json", "tagName"], repo), check=False)
    if result.returncode == 0:
        return True

    combined = "\n".join(part for part in (result.stdout, result.stderr) if part).lower()
    if "not found" in combined or "release not found" in combined:
        return False

    message = ["Could not inspect release '{}'".format(tag)]
    if result.stdout:
        message.append(result.stdout.rstrip())
    if result.stderr:
        message.append(result.stderr.rstrip())
    raise RuntimeError("\n".join(message))


def write_output(name, value):
    """Append a step output for the workflow, when running under GitHub Actions."""

    output_path = os.environ.get("GITHUB_OUTPUT", "").strip()
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as fh:
        fh.write("{}={}\n".format(name, value))
