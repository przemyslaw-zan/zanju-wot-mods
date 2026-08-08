# Runtime Layout And Packaging

## Typical WoT Runtime Folders

Common runtime locations:

- `mods/<game-version>/`
- `mods/configs/`
- `res_mods/<game-version>/`
- `res_mods/configs/`

## Package Shape

A `.wotmod` commonly contains:

- `res/` — the only required element; everything below lives under it
- compiled Python scripts under `res/scripts/client/gui/mods/*.pyc`
- optional Scaleform assets under `res/gui/flash/*.swf`
- optional Gameface assets under `res/gui/gameface/mods/<namespace>/*` — the HTML/CSS/JS a
  widget injects into a game document
- optional localisation assets under `res/mods/<namespace>/text/*.yml`
- optional `meta.xml` manifest at the archive root (`<id>`, `<version>`, `<name>`, `<description>`)
- optional root `LICENSE.md`

## `gui/gameface` Is Not `gui/unbound`

The client ships both, and only the first holds web assets. Counted across `gui-part1.pkg` on
2.3.1.1:

| Path | Contents |
| --- | --- |
| `gui/gameface/` | 159 `.js`, 144 `.css`, 128 `.html` — the compiled documents, under `_dist/` |
| `gui/unbound/` | 42 files, all `.unbound` — Unbound's own declarative view format |

A widget's assets therefore go under `res/gui/gameface/`, which is also the prefix its
`coui://` URLs resolve against. Community guides that send Gameface overrides to
`gui/unbound/` are wrong on this point.

## Repository Build Rules

In this repository:

- build and lint run inside the toolchain image (`tools/Dockerfile` → `ghcr.io/przemyslaw-zan/zanju-wot-mods/toolchain`); Docker is the only local prerequisite
- authored Python sources live under `mods/<mod-name>/src/`
- `zwm build` compiles them into the runtime package shape
- config is not shipped: each mod self-creates its config in AppData on first run, so it survives modpack reinstalls
- authored `i18n/*.yml` files are bundled inside the `.wotmod` at `res/mods/<meta.id>/text/*.yml` (the single localisation destination — no loose config copies); the runtime reads them from the mounted package VFS via `ResMgr` at `mods/<meta.id>/text/<lang>.yml`
- `ui/compile_ui.py` is auto-run by `zwm build` when present

## Entry Point Rule

For this WoT stack, keep a top-level `mod_*.py` bootstrap in `src/`.
Package-only entry points were not reliably auto-discovered.

## Import Safety Rule

Do not use the same module name for both:

- the top-level bootstrap file
- the internal package directory

That pattern can shadow the package in `sys.modules` and break imports.

## Release Output

Build results go to `dist/`.
That output is intended to be disposable build output rather than authored source.
