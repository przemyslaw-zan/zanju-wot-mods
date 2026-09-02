# Developing Mods

This page is for contributors working on the code in this repository.

> Only adding or updating a translation? You do not need this toolchain — see
> [Translating](translating.md), which needs just Python 3.

## Toolchain

The entire toolchain ships inside one Docker image
(`ghcr.io/przemyslaw-zan/zanju-wot-mods/toolchain`, public), so **Docker Desktop is
the only thing you install**. The image carries:

- Python 3 with the repo commands (`zwm`) and Black / Ruff / autopep8.
- Python 2.7 with Flake8 3.9.x, to compile and lint WoT-compatible `.pyc` files.
- Java + Apache Flex SDK (`mxmlc`) for ActionScript UI.

A local World of Tanks install is still needed for runtime validation (deploy/cycle).

## Local Setup (Dev Container)

1. Install **Docker Desktop** and the VS Code **Dev Containers** extension.
2. Copy `.env.example` to `.env` and set `WOT_GAME_DIR` to your WoT install path
   (e.g. `c:\Games\World_of_Tanks_EU`). Docker Compose reads it to bind-mount your
   install at `/game`; inside the container the tools see `WOT_GAME_DIR=/game`.
3. Open the repo in VS Code → **Reopen in Container**.

You stay in VS Code — same editor, terminal, and Source Control. Only the backend
(interpreter, terminal, tooling) runs inside the image. The first open pulls the
image; later opens reuse the container. The `zwm` command is baked into the image,
so it is ready in the terminal immediately:

```bash
zwm build research-progress-bar
zwm lint
zwm cycle research-progress-bar    # cleanup + build + deploy
zwm deploy research-progress-bar
zwm cleanup research-progress-bar
zwm help                           # list commands
```

`zwm <command>` is the human alias for `python3 -m tools.commands.<module>` (which also works).

Without VS Code, run any command via plain `docker run` — see the standalone
reference in [Building From Source](building-from-source.md#standalone-docker-run-no-vs-code).

For mod-targeting commands, pass one or more mod names explicitly; use `--all` only
when you really want every mod. `zwm deploy` expects current build output in
`dist/`. **Close WoT before `zwm cleanup`, `zwm deploy`, and `zwm cycle`** —
there is no automatic running-process check (the container can't see the Windows host);
in-use files are simply skipped.

Every releasable mod must keep a `mods/<name>/CHANGELOG.md` with a `## <version>` section for
each released version: the release notes are generated from the section matching `meta.xml`,
and a version bump without a matching section fails the release build. Bumping the version in
`meta.xml` is what triggers a release, and versions below `1.0.0` are never published.

## Python Format and Lint Workflow

The repo-level entry point is:

```powershell
zwm lint
zwm lint check
```

That command is the current default gate locally and in CI for:

- Python 3 format check with Black.
- Python 3 lint with Ruff.
- Python 2.7 lint with Flake8 3.9.x.
- Python 2.7 conservative format check with autopep8 diff mode.

The Python 2.7 Flake8 gate also enforces a McCabe complexity limit so new changes do not keep pushing large runtime functions upward unchecked.

CI runs the same `zwm lint` steps inside the toolchain image, so the Python 3 (Black/Ruff/autopep8) and Python 2.7 (Flake8 3.9.x against `mods/*/src`) surfaces use the exact interpreters you get locally — no environment drift. Every push to a non-`master` branch and every PR runs lint; on `master` the "Master Workflow" runs lint as a gate before building and publishing.

Useful variants:

```powershell
zwm lint fix
zwm lint py3-check
zwm lint py3-format
zwm lint py3-format-check
zwm lint py27-lint
zwm lint py27-format-check
zwm lint py27-format
```

The Python 2.7 autopep8 path is intentionally conservative. It only applies low-risk whitespace, indentation, and blank-line fixes. CI checks that surface in diff mode, while local rewriting stays an explicit reviewed step via `zwm lint py27-format`.

## Recommended Daily Loop

1. Edit source files.
2. Run `zwm lint` or `zwm lint check`.
3. Run `zwm test --all` if the mod has tests (see [Testing](testing.md)).
4. If you want to normalize existing Python 2.7 formatting, review `zwm lint py27-format-check` before applying `zwm lint py27-format`.
5. Close WoT, then run `zwm cycle <mod-name>`.
6. Restart or relaunch WoT.
7. Reproduce the scenario.
8. Inspect `game.log`.

## Useful Commands

Full format and lint gate:

```powershell
zwm lint
zwm lint check
```

Python 3 auto-fixes plus Python 2.7 lint:

```powershell
zwm lint fix
```

Run the mods' unit tests:

```powershell
zwm test --all
zwm test premium-time
```

Build one mod:

```powershell
zwm build research-progress-bar
```

Cleanup one deployed mod:

```powershell
zwm cleanup research-progress-bar
```

Cleanup, rebuild, and redeploy one mod:

```powershell
zwm cycle research-progress-bar
```

Fresh log plus redeploy:

```powershell
zwm cycle --fresh-log research-progress-bar
```

## Repository Conventions

- Keep a thin top-level `mod_*.py` bootstrap in `src/`.
- Put implementation into a uniquely named internal package.
- Use explicit relative imports inside the package.
- Let each mod create its own config in AppData on first run. Nothing ships as a loose file, so a modpack reinstall cannot wipe it.
- Treat generated SWF output and release bundles as build artifacts, not source.
- A mod opts into unit tests by adding `tests/`; `zwm test` discovers them by convention.

## Where To Go Next

- [Architecture](architecture.md) for packaging, runtime layout, and UI patterns.
- [Testing](testing.md) for how mod unit tests are discovered and run.
- [Debugging](debugging.md) for triage and stability rules.
- [Technical Reference](reference/README.md) for game-facing APIs and runtime knowledge.
