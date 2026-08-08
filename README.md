# Zanju's WoT Mods

Source repository for World of Tanks mods, build tooling, and game-facing technical notes.

## Included Mods

### [Zanju's Directives Helper](mods/directives-helper/README.md)

[![release](https://img.shields.io/github/v/release/przemyslaw-zan/zanju-wot-mods?filter=directives-helper%40*)](https://github.com/przemyslaw-zan/zanju-wot-mods/releases/latest)

Garage window for fitting directives and warning before auto-resupply spends any resources.

### [Zanju's Premium Time](mods/premium-time/README.md)

[![release](https://img.shields.io/github/v/release/przemyslaw-zan/zanju-wot-mods?filter=premium-time%40*)](https://github.com/przemyslaw-zan/zanju-wot-mods/releases/latest)

Precise premium account countdown in the lobby header, with the exact end time in its tooltip.

### [Zanju's Research Progress Bar](mods/research-progress-bar/README.md)

[![release](https://img.shields.io/github/v/release/przemyslaw-zan/zanju-wot-mods?filter=research-progress-bar%40*)](https://github.com/przemyslaw-zan/zanju-wot-mods/releases/latest)

Custom hangar progress bar covering research, field modifications, Tier XI upgrade-tree progress, and elite progress modes.

## Install And Use

Use this path if you want to install a prepared mod package and keep it updated.

- [Installing Mods](docs/installing-mods.md)
- Each mod version is published as its own GitHub release, tagged `<mod-name>@<version>`. The
  [Latest Releases](https://github.com/przemyslaw-zan/zanju-wot-mods/releases/latest) index always lists the current
  release of every mod, so that one link stays correct as mods update independently.

## Build From Source

Use this path if you want to build `.wotmod` packages yourself without changing the code.

- Prerequisites: **Docker Desktop only** — the whole toolchain (Python 3, Python 2.7, Node, Java + Apache Flex SDK) ships in the published image `ghcr.io/przemyslaw-zan/zanju-wot-mods/toolchain`
- The target WoT version is pinned in `tools/wot_version_manifest.json`
- Standalone configurator bundles additionally require the pinned companion artifacts fetched into the local ignored cache

- [Building From Source](docs/building-from-source.md)
- [Architecture](docs/architecture.md)

## Develop And Extend

Use this path if you want to change code, add features, or create new mods in this workspace.

- Prerequisites: **Docker Desktop** + the VS Code **Dev Containers** extension; a local WoT install; `.env` copied from `.env.example` with `WOT_GAME_DIR` set
- Open the repo in VS Code → **Reopen in Container**; the `zwm` command is ready in the container terminal
- `swfdump` (Apache Flex SDK) ships in the image for SWF inspection; FFDec is a separate optional tool if you need a GUI decompiler
- Run `zwm help` to list the available commands
- Run `zwm lint check` before build or deploy, and `zwm test --all` to run the mods' unit tests

- [Developing Mods](docs/developing-mods.md)
- [Testing](docs/testing.md)
- [Architecture](docs/architecture.md)
- [Technical Reference](docs/reference/README.md)
- [Debugging](docs/debugging.md)

## Translate

Use this path if you want to add or update a language for a mod.

- Prerequisites: **Python 3 and Git only** — no Docker or Dev Container (that is only for building packages)
- Edit `mods/<mod-name>/i18n/<code>.yml`, then run `python3 -m tools.commands.lint i18n` to refresh the coverage table

- [Translating](docs/translating.md)

## Reference

- [Technical Reference](docs/reference/README.md)
- [Resources And External Links](docs/resources.md)
