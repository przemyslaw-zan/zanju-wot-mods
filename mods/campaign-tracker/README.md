# Zanju's Campaign Tracker

### This mod shows which personal mission your tank is on, without opening the missions screen.

- **One badge per campaign** — every active campaign gets a small badge in the garage. Each badge shows the campaign number over a short mission id: `LT-1`, `UN-10`, `VA-3`. Campaigns 1 and 2 run together, and campaign 3 runs alone, so you see two badges or one.
- **Named for your tank** — a badge names the mission your selected vehicle is on. Campaign 1 sorts vehicles by class, campaign 2 by alliance, campaign 3 by role. The badges follow every tank change.
- **Reads in your language** — the id comes from the game's own short mission name, then gets cut to fit. Nothing about it is hardcoded to English.
- **Grey when nothing applies** — a campaign your tank fits no mission in stays on screen in grey. You can tell "no mission" from "mod not running" at a glance.
- **Details on hover** — point at a badge for the operation, the full mission name, and the progress of every condition.
- **Battle limits** — some missions, mostly in campaign 2, run to a battle limit. The badge reports the limit in the shape the mission uses:
  - A number of successes in a limited run: the successes so far, the number needed, and the battles left.
  - A total to build: the total, its target, and the battles left.
  - A number of times, in a row or in any order: what is in hand against what it takes.
- **Pace** — a mission that builds a total asks for one constant average: 25 hits in 10 battles is 2.5 a battle. The card says where you stand against that average as a percentage, where 100% is exactly on it. The badge tints the total green or red to match.
- **Locked vehicles** — campaign 3 has missions to complete in several different vehicles. A vehicle that finishes one is locked out of it. The card counts how many are still wanted, and names the ones already spent. The badge shows a lock when the tank in the garage is one of them, so you can see that this tank cannot move this mission without opening anything.
- **Click to open the mission** — a badge takes you to the game's own screen for that mission. Campaigns 1 and 2 open the mission itself, campaign 3 opens its mission list, because that is how each campaign shows a mission.
- **Pause or reset from the badge** — Shift + Click pauses a mission, or resumes a paused one. Ctrl + Click resets it, through the game's own confirmation dialog. The card lists what each click does and lights the line for the keys you hold. Only Object 279 (e) accepts these, because the game allows them nowhere else.
- **Sits beside your tank name** — the badges sit to the right of the vehicle name and experience block. They follow it when the garage moves it, and they stay clear of everything you click.

## Translations

Reference language `en` defines 16 strings. Translations are community-maintained and may lag behind; see [Translating](../../docs/translating.md) to add or update one, then regenerate this table with `zwm lint i18n`.

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
