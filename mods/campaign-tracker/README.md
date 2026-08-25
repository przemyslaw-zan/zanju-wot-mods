# Zanju's Campaign Tracker

### This mod shows which personal mission your tank is on, without opening the missions screen.

- **One badge per campaign** — every active campaign gets a small badge in the garage. Each badge shows the campaign number over a short mission id: `LT-1`, `UN-10`, `VA-3`. Campaigns 1 and 2 run together, and campaign 3 runs alone, so you see two badges or one.
- **Named for your tank** — a badge names the mission your selected vehicle is on. Campaign 1 sorts vehicles by class, campaign 2 by nation alliance, campaign 3 by role. The badges follow every tank change.
- **Reads in your language** — the id comes from the game's own short mission name, then gets cut to fit. Nothing about it is hardcoded to English.
- **Grey when nothing applies** — a campaign your tank fits no mission in stays on screen in grey. You can tell "no mission" from "mod not running" at a glance.
- **Details on hover** — point at a badge for the operation, the full mission name, and the progress of every condition.
- **Sits beside your tank name** — the badges sit to the right of the vehicle name and experience block. They follow it when the garage moves it, and they stay clear of everything you click.

## Translations

Reference language `en` defines 9 strings. Translations are community-maintained and may lag behind; see [Translating](../../docs/translating.md) to add or update one, then regenerate this table with `zwm lint i18n`.

| Language | Coverage | Missing |
| --- | --- | --- |
| _none yet_ | — | — |

## Install And Use

If you already have the prepared mod zip file, follow the general install path in [Installing Mods](../../docs/installing-mods.md).

## Build From Source

For the general build/toolchain workflow, see [Building From Source](../../docs/building-from-source.md).

## Develop

For the wider repository workflow, see:

- [Developing Mods](../../docs/developing-mods.md)
- [Architecture](../../docs/architecture.md)
- [Technical Reference](../../docs/reference/README.md)
