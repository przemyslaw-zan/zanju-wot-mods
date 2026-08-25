# Zanju's WoT Mods

[![license](https://img.shields.io/github/license/przemyslaw-zan/zanju-wot-mods?color=green&style=flat)](LICENSE.md) [![WoT](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Fprzemyslaw-zan%2Fzanju-wot-mods%2Fmaster%2Ftools%2Fwot_version_manifest.json&query=%24.wotClientVersion&label=WoT&color=green&style=flat)](tools/wot_version_manifest.json) [![stars](https://img.shields.io/github/stars/przemyslaw-zan/zanju-wot-mods?color=green&style=flat)](https://github.com/przemyslaw-zan/zanju-wot-mods/stargazers) [![downloads](https://img.shields.io/github/downloads/przemyslaw-zan/zanju-wot-mods/total?color=green&style=flat)](https://github.com/przemyslaw-zan/zanju-wot-mods/releases/latest)

Source repository for World of Tanks mods, build tooling, and game-facing technical notes.

## Included Mods

### [Zanju's Campaign Tracker](mods/campaign-tracker/README.md)

In development, not released yet.

One garage widget per active personal missions campaign. Each widget names the mission the selected vehicle works on. Its hover card gives the line, the stage, and the condition progress.

### [Zanju's Directives Helper](mods/directives-helper/README.md)

[![release](https://img.shields.io/github/v/release/przemyslaw-zan/zanju-wot-mods?filter=DH%40*&color=green&style=flat)](https://github.com/przemyslaw-zan/zanju-wot-mods/releases/latest)

Garage window for fitting directives and warning before auto-resupply spends any resources.

### [Zanju's Premium Time](mods/premium-time/README.md)

[![release](https://img.shields.io/github/v/release/przemyslaw-zan/zanju-wot-mods?filter=PT%40*&color=green&style=flat)](https://github.com/przemyslaw-zan/zanju-wot-mods/releases/latest)

Shows actual remaining premium account time in the lobby header, with the exact end time in its tooltip.

### [Zanju's Research Progress Bar](mods/research-progress-bar/README.md)

[![release](https://img.shields.io/github/v/release/przemyslaw-zan/zanju-wot-mods?filter=RPB%40*&color=green&style=flat)](https://github.com/przemyslaw-zan/zanju-wot-mods/releases/latest)

Hangar progress bar covering research, field modifications, Tier XI upgrades, and elite progress modes.

### [Zanju's Salvo Reticle Fix](mods/salvo-reticle-fix/README.md)

[![release](https://img.shields.io/github/v/release/przemyslaw-zan/zanju-wot-mods?filter=SRF%40*&color=green&style=flat)](https://github.com/przemyslaw-zan/zanju-wot-mods/releases/latest)

Strips the fixed shell-spread offset from the reticle of twin-gun vehicles in Salvo Fire mode, so the circle shows dispersion only, like every other vehicle's does.

## Install And Use

Use this path if you want to install a prepared mod package and keep it updated.

- [Installing Mods](docs/installing-mods.md)
- Each mod version is published as its own GitHub release, tagged `<ACRONYM>@<version>` (for example `PT@1.0.1`). The [Latest Releases](https://github.com/przemyslaw-zan/zanju-wot-mods/releases/latest) index always lists the current release of every mod, so that one link stays correct as mods update independently.

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
