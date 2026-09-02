"""Query upstream release APIs, resolve a pinned version set, and rewrite the tracked manifest."""

from __future__ import annotations

import copy
import os
import re
import sys
import tempfile
from urllib.parse import quote

from ..core.mod_cli import run_entrypoint
from ..core.companion_artifacts import (
    COMPANION_ARTIFACT_SCHEMA_VERSION,
    RESEARCH_PROGRESS_BAR_BUNDLE,
    CompanionArtifactError,
    compute_file_sha256,
    download_url_to_path,
    fetch_json,
    load_manifest,
    save_manifest,
    utc_now_iso,
)
from ..core.console import detail, section, success

_GITHUB_MODMENU_RELEASE_URL = "https://api.github.com/repos/Aslain/modmenu/releases/latest"
_GITLAB_OPENWG_GAMEFACE_RELEASE_URL = (
    "https://gitlab.com/api/v4/projects/openwg%2Fwot.gameface/releases/permalink/latest"
)
_GITLAB_DESCRIPTION_LINK_RE = re.compile(r"\[(?P<name>[^\]]+)\]\((?P<url>[^)]+)\)")


def parse_args(argv):
    dry_run = False
    verbose = False
    for arg in argv:
        if arg == "--dry-run":
            dry_run = True
            continue
        if arg == "--verbose":
            verbose = True
            continue
        raise RuntimeError("Unknown argument: {}".format(arg))
    return dry_run, verbose


def _main():
    dry_run, verbose = parse_args(sys.argv[1:])
    section("Update companion manifest")
    current_manifest = load_manifest()
    candidate_manifest = _build_candidate_manifest(current_manifest)
    _hydrate_checksums(candidate_manifest)

    changed = _manifest_changed(current_manifest, candidate_manifest)

    if dry_run:
        if not changed:
            success("Dry-run: no manifest changes detected")
            return
        if verbose:
            for artifact_id, artifact in candidate_manifest["artifacts"].items():
                detail(
                    "Would update {} {} -> {}".format(artifact_id, artifact["version"], artifact["downloadUrl"]),
                    verbose=True,
                )
        else:
            success("Dry-run: {} artifacts resolved and checksummed".format(len(candidate_manifest["artifacts"])))
        return

    if not changed:
        success("No manifest changes detected.")
        return

    candidate_manifest["updatedAt"] = utc_now_iso()

    save_manifest(candidate_manifest)
    if verbose:
        for artifact_id, artifact in candidate_manifest["artifacts"].items():
            detail("Updated {} {}".format(artifact_id, artifact["filename"]), verbose=True)
    success("Companion manifest updated: tools/companion_artifacts_manifest.json")


def _build_candidate_manifest(current_manifest=None):
    modmenu = _resolve_modmenu_artifact()

    # Gameface is tracked from its own OpenWG upstream, not the copy the mods-list
    # release happens to bundle, so a new OpenWG release is picked up as soon as it
    # ships rather than waiting for mods-list to re-bundle it. The release
    # description carries both a .wotmod (WoT) and a .mtmod (Lesta) upload link;
    # _parse_gitlab_description_assets keeps only the .wotmod.
    openwg_gameface_project_id = _fetch_gitlab_project_id("openwg/wot.gameface")
    openwg_gameface_release = fetch_json(_GITLAB_OPENWG_GAMEFACE_RELEASE_URL)
    openwg_gameface_assets = _parse_gitlab_description_assets(
        openwg_gameface_release, openwg_gameface_project_id
    )
    openwg_gameface = _resolve_gitlab_description_artifact(
        artifact_id="openwg_gameface",
        display_name="OpenWG Gameface",
        release_data=openwg_gameface_release,
        assets=openwg_gameface_assets,
        filename_prefix="net.openwg.gameface_",
        provider="gitlab-release-description",
        project="openwg/wot.gameface",
        notes="Gameface runtime for the configurator, tracked from OpenWG upstream.",
    )

    return {
        "schemaVersion": COMPANION_ARTIFACT_SCHEMA_VERSION,
        "updatedAt": "",
        # Carried over from the file, never regenerated: which mods ship which companions is
        # authored here, while only the artifact versions come from upstream. Rebuilding this
        # section would silently delete every bundle added since the default was written --
        # and because the command reports "manifest updated", the loss looks like a success.
        "bundles": _carry_over_bundles(current_manifest),
        "artifacts": {
            "modmenu": modmenu,
            "openwg_gameface": openwg_gameface,
        },
    }


def _carry_over_bundles(current_manifest):
    """Bundles from the existing manifest, or the default one when bootstrapping.

    The fallback only applies when there is no manifest yet, or it defines no bundles at all;
    a manifest that already has bundles is authoritative and is passed through untouched.
    """
    bundles = (current_manifest or {}).get("bundles")
    if isinstance(bundles, dict) and bundles:
        return copy.deepcopy(bundles)
    return {
        RESEARCH_PROGRESS_BAR_BUNDLE: {
            "description": "Standalone configurator companion chain for Research Progress Bar.",
            "artifactIds": ["modmenu", "openwg_gameface"],
        }
    }


def _resolve_modmenu_artifact():
    """The configurator Research Progress Bar draws its settings page in.

    Mod Menu replaced `aslain.modssettingsapi`, and it keeps the same Python API: the mod still
    reads `g_modsSettingsApi` out of `gui.aslainMenu`. Only the package changed, and the change
    matters because the two ids ship the same script package. A client holding both refuses one
    of them and says so in a dialog, which is what the old pin did to anyone whose modpack had
    already moved on. Two copies of Mod Menu itself carry one id and raise nothing.
    """
    release_data = fetch_json(_GITHUB_MODMENU_RELEASE_URL)
    assets = release_data.get("assets") or []
    asset = None
    for item in assets:
        name = item.get("name")
        if isinstance(name, str) and name.endswith(".wotmod") and name.startswith("aslain.modmenu_"):
            asset = item
            break
    if asset is None:
        raise CompanionArtifactError(
            "Could not resolve aslain.modmenu .wotmod asset from the latest GitHub release"
        )

    filename = asset["name"]
    version = _extract_version_from_filename(filename, "aslain.modmenu_")
    return {
        "displayName": "Aslain's Mod Menu",
        "provider": "github-release-api",
        "project": "Aslain/modmenu",
        "releaseTag": release_data.get("tag_name") or version,
        "version": version,
        "filename": filename,
        "downloadUrl": asset["browser_download_url"],
        "sha256": "0" * 64,
        "notes": "In-game settings window for research-progress-bar. Needs OpenWG Gameface 1.1.6 or newer.",
    }


def _parse_gitlab_description_assets(release_data, project_id):
    description = release_data.get("description") or ""
    assets = {}
    for match in _GITLAB_DESCRIPTION_LINK_RE.finditer(description):
        name = match.group("name").strip()
        url = match.group("url").strip()
        if not name.endswith(".wotmod"):
            continue
        if url.startswith("/uploads/"):
            url = "https://gitlab.com/-/project/{}{}".format(project_id, url)
        elif url.startswith("/"):
            url = "https://gitlab.com{}".format(url)
        assets[name] = url
    return assets


def _fetch_gitlab_project_id(project_path):
    project_url = "https://gitlab.com/api/v4/projects/{}".format(quote(project_path, safe=""))
    project_data = fetch_json(project_url)
    project_id = project_data.get("id")
    if not isinstance(project_id, int):
        raise CompanionArtifactError("Could not resolve GitLab project id for {}".format(project_path))
    return project_id


def _resolve_gitlab_description_artifact(
    artifact_id, display_name, release_data, assets, filename_prefix, provider, project, notes
):
    selected_name = None
    selected_url = None
    for name in sorted(assets):
        if name.startswith(filename_prefix) and name.endswith(".wotmod"):
            selected_name = name
            selected_url = assets[name]
            break

    if selected_name is None or selected_url is None:
        raise CompanionArtifactError(
            "Could not resolve '{}' from the {} release description".format(artifact_id, project)
        )

    version = _extract_version_from_filename(selected_name, filename_prefix)
    return {
        "displayName": display_name,
        "provider": provider,
        "project": project,
        "releaseTag": release_data.get("tag_name") or version,
        "version": version,
        "filename": selected_name,
        "downloadUrl": selected_url,
        "sha256": "0" * 64,
        "notes": notes,
    }


def _extract_version_from_filename(filename, filename_prefix):
    suffix = ".wotmod"
    if not filename.startswith(filename_prefix) or not filename.endswith(suffix):
        raise CompanionArtifactError("Unexpected artifact filename: {}".format(filename))
    return filename[len(filename_prefix) : -len(suffix)]


def _hydrate_checksums(manifest):
    with tempfile.TemporaryDirectory(prefix="companion-artifacts-update-") as temp_dir:
        for artifact in manifest["artifacts"].values():
            temp_path = os.path.join(temp_dir, artifact["filename"])
            download_url_to_path(artifact["downloadUrl"], temp_path)
            artifact["sha256"] = compute_file_sha256(temp_path)


def _manifest_changed(current_manifest, candidate_manifest):
    return _normalized_manifest(current_manifest) != _normalized_manifest(candidate_manifest)


def _normalized_manifest(manifest):
    normalized = {
        "schemaVersion": manifest.get("schemaVersion"),
        "bundles": manifest.get("bundles") or {},
        "artifacts": manifest.get("artifacts") or {},
    }
    return normalized


def main():
    # run_entrypoint, not a guard under `if __name__`: zwm imports this module and calls
    # main() directly, so anything handled only in the __main__ block never ran for the
    # command's actual users -- domain errors reached them as tracebacks.
    return run_entrypoint(_main)


if __name__ == "__main__":
    sys.exit(main())
