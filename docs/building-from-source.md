# Building From Source

This page is for users who want to build the mods in this repository. The whole
toolchain (Python 3 tooling, Python 2.7 for `.pyc` output, Java + Apache Flex
SDK for UI, and the lint tools) ships inside one Docker image, so **the only
thing you need to install is Docker**.

## Prerequisites

- **Docker Desktop** (the engine — it just runs in the background).
- Optional, recommended: **VS Code** + the **Dev Containers** extension for the in-editor workflow.

No local Python 2.7/3, Java, or Flex SDK is required.

The published image is `ghcr.io/przemyslaw-zan/zanju-wot-mods/toolchain` (public). It
carries Python 3 (ruff/black/autopep8), Python 2.7 (flake8 3.9.x), the Apache Flex
SDK (`mxmlc`), and the `zwm` command. CI builds and publishes it; locally you just pull it.

## Dev Container (recommended)

Open the repo in VS Code → **Reopen in Container**. You stay in VS Code; the
integrated terminal, interpreter, and the `zwm` command run inside the image.
See [Developing Mods](developing-mods.md) for the full loop.

## Standalone `docker run` (no VS Code)

`zwm` is baked into the image. Run any command with the repo bind-mounted. PowerShell:

```powershell
# Build one mod (output lands in dist/ on your checkout)
docker run --rm -v "${PWD}:/workspace" -w /workspace `
  ghcr.io/przemyslaw-zan/zanju-wot-mods/toolchain zwm build research-progress-bar

# Build everything
docker run --rm -v "${PWD}:/workspace" -w /workspace `
  ghcr.io/przemyslaw-zan/zanju-wot-mods/toolchain zwm build --all

# Lint (Python 3 + Python 2.7)
docker run --rm -v "${PWD}:/workspace" -w /workspace `
  ghcr.io/przemyslaw-zan/zanju-wot-mods/toolchain zwm lint
```

`zwm <command>` is the alias for `python3 -m tools.commands.<module>`; either works.

For `research-progress-bar`, the default build includes the standalone configurator
companion chain when the manifest defines it. Fetch the pinned companion artifacts first:

```powershell
docker run --rm -v "${PWD}:/workspace" -w /workspace `
  ghcr.io/przemyslaw-zan/zanju-wot-mods/toolchain `
  bash -c 'zwm fetch-companion-artifacts && zwm build research-progress-bar'
```

To build only the main package without the companion `.wotmod` files, add `--no-companion-bundle`.

The tracked companion manifest lives at `tools/companion_artifacts_manifest.json`. Downloaded
companion `.wotmod` files are cached under the ignored `.cache/companion-wotmods/`.

The pinned WoT target version lives at `tools/wot_version_manifest.json`. If your local game
updates, refresh it before build/deploy (run inside the image as above):
`zwm update-wot-version-manifest`.

## CI Releases

Pushes to `master` lint, build all mods inside the image, and then publish. The toolchain
image itself is rebuilt and pushed to GHCR only when `tools/Dockerfile` or the
`requirements-*.txt` files change.

Publishing follows a single rule: a mod at version `1.0.0` or higher whose `meta.xml`
version has no release yet gets one, tagged `<mod-name>@<version>` (for example
`premium-time@1.0.1`). Releases are never edited afterwards, so a push with no version
bump publishes nothing. Versions below `1.0.0` are treated as internal and are not
released.

Whenever at least one mod is released, the `Latest Releases` index release is republished
under a fresh dated tag and marked as GitHub's latest release, so
`/releases/latest` always resolves to a current list of every mod's newest download. The
index carries no assets of its own and is rendered from the releases that actually exist,
so a partly failed run self-corrects on the next one.

Release notes for each mod are taken from its `mods/<name>/CHANGELOG.md` section matching
the version being released, so that section must exist before the version can ship.

> Do not enable GitHub's **immutable releases** setting on this repository. It permanently
> reserves the tag name of every release published while it is on — even after that release
> is deleted, and even if the setting is later turned off. The index republishes by deleting
> its previous dated tag, which that setting would block.

## Output

Successful builds are written to `dist/` as bundle directories. For end users, the main
installation artifact is the generated zip inside each bundle directory.

Each built mod bundle includes:

- `<mod-id>_<version>.zip` containing the install-ready `mods/` tree
- `mods/<wot_client_version>/<mod-id>_<version>.wotmod` (translations are bundled inside it at `res/mods/<id>/text/*.yml`)

## Deploy To A Local WoT Install

`zwm deploy` copies pre-built artifacts from `dist/`, so build first. Deploy needs your
WoT install mounted at `/game`; the Dev Container does this from `WOT_GAME_DIR` in `.env`
(see [Developing Mods](developing-mods.md)). Standalone:

```powershell
docker run --rm -v "${PWD}:/workspace" -v "C:\Games\World_of_Tanks_EU:/game" `
  -e WOT_GAME_DIR=/game -w /workspace `
  ghcr.io/przemyslaw-zan/zanju-wot-mods/toolchain zwm deploy research-progress-bar
```

**Close WoT before deploy/cleanup/cycle.** There is no automatic running-process check
(it can't see the Windows host from the container); in-use files are simply skipped.

## Important Runtime Note

WoT does not hot-reload Python, SWF, or packaged mod changes from disk. After deployment,
restart the game before treating the new package as active.

## Next Steps

- For packaging/runtime conventions, see [Architecture](architecture.md).
- For the full edit-test-debug loop, see [Developing Mods](developing-mods.md).
