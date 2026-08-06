# TODO

Follow-up backlog after the initial Python format-and-lint tooling rollout.

## Format-And-Lint Follow-Up

- Rerun `zwm lint check` after the `research-progress-bar` cleanup and reassess whether `max-complexity = 25` should stay as-is or be tightened further.

## General Refactor Backlog

- Broad runtime splitting for `research-progress-bar` is mostly complete; only reopen it if `mods/research-progress-bar/src/zanju_rpb/main.py` or `mods/research-progress-bar/src/zanju_rpb/scaleform/modes.py` grow enough to justify another targeted slice.

## Shared Runtime `localization.py` (Build-Time Staging)

Planned; do it on the mainline as its own change (not on `premium-time`) once the in-flight branches land. Context: `zanju_pt/localization.py` and `zanju_rpb/localization.py` are ~98% identical copies (only docstring, logger name, and `get_wg_text` differ), the empty-value fix already had to be mirrored by hand once, and `crew-post-progression` would add a third copy.

- Decision: single authored source staged into each mod's package at build time. Rejected alternatives: a shared `.wotmod` library (VFS version-skew between independently installed mods; breaks the self-contained-mods philosophy) and committed copies with a lint sync-check (more tooling, drift is only CI-caught instead of impossible). Precedent for staging: `_mod_meta` is already generated into every package at build, and committed `constants.py` imports it as a sibling that does not exist in the tree.
- Canonical file location: outside `mods/` (e.g. `runtime-common/localization.py`) — several tools iterate `mods/` expecting each subdir to be a mod with `meta.xml` (release notes, `build --all`, `deploy`, `cleanup`); otherwise teach all iterators to skip non-mod dirs.
- Genericize the file: derive logger via `MOD_ID + '.i18n'` (yields the exact current names for both mods), keep `get_wg_text` everywhere (harmless where unused), neutral docstring.
- Import rule: the shared module imports `from ._mod_meta import MOD_ID` directly (the only sibling guaranteed in every package by the build itself) — not `.constants`.
- Build change: mirror `bundle_generated_mod_meta` — compile the shared file into every internal package as `<pkg>/localization.pyc`; hard error if a mod's own `src/` contains a colliding filename (silent shadowing would reintroduce drift).
- Lint: add the canonical path to the py2.7 flake8 coverage (current glob is `mods/*/src`).
- Delete both per-mod copies.
- Accepted consequences: IDE shows unresolved `.localization` imports in callers (cosmetic; flake8 does not resolve imports — verified green); `python.log` tracebacks cite `mods/<pkg>/localization.py`, a path with no matching file under `src/`; a one-time modify/delete merge conflict with `premium-time`'s copy (resolve by taking the delete); future per-mod divergence requires parameterizing the shared file or an explicit opt-out (defer until needed).
- Verified non-issues: nothing outside the game imports the mod packages (no py3 probes/tests reach into `src/`); deploy ships the built `.wotmod`, untouched.

## Testing Backlog

Scaffolding is in place (`zwm test`, `testing/`, see [Testing](docs/testing.md)). `premium-time`
and `directives-helper` are covered; `research-progress-bar` has one suite so far.

- Broaden `mods/research-progress-bar/tests/`. `panel_watch.py` is tested because it keeps every
  client import inside a function; most of the mod does not, and `constants.py` pulls in
  `gui.Scaleform.daapi.settings.views` at module scope — so reaching the rest needs client stub
  modules added to `GAME_STUB_MODULES` in `testing/zwm_test_env.py`. Good next targets: the
  `config.py` normalizers (mode/bool coercion, legacy-key migration), `mode_state.py`, and the
  percent/label formatting in `scaleform/modes.py`. Skip `collector.py`: faking enough of the
  client to reach it would encode more assumptions than the tests verify.
  - Worth applying deliberately when splitting modules: "no client import at module scope" is
    what decides whether something can be tested at all.
- When the shared `localization.py` lands (see above), move its tests to the canonical copy so the
  parser is covered once rather than per mod.

## CI / Toolchain Backlog

- Restore a "WoT is running" guard for deploy/cleanup/cycle. It was removed in the Docker migration because a Linux container can't enumerate Windows host processes (`tasklist`). Viable options: (a) a host **PowerShell** wrapper that runs the `tasklist` check before invoking the container (no install needed — PowerShell is built in); (b) a file-lock probe on a known WoT-held file; (c) a `--force`/`--skip-running-check` opt-out if a host check is reintroduced. Until then, deploy relies on file-lock `PermissionError` handling (in-use files are skipped) — close WoT manually.

## Release And Distribution Backlog

- Add a `research-progress-bar` release checklist for wgmods.net and modpack submission: standalone companion bundle contents, config/i18n copy requirements, no-optional-UI-API smoke test, and re-test expectations for each WoT version even when no code change is planned.
- Resolved: `meta.xml` stays in releases, trimmed to the spec fields `id`/`version`/`name`/`description`. The Wargaming *Mod Packages* spec marks it optional (only `res/` is required) but `id`/`version` give clean load-order and same-id version de-dup, so keeping it is worthwhile. It is now the single source of truth for those values (build generates the runtime `_mod_meta` and all scripts read it via `tools/mod_meta.py`).

## Localization / Font Coverage

- Current state: text outside the embedded Roboto Mono range (Korean, Greek, Cyrillic, etc.) falls back to the `Malgun Gothic` device font. This is wired centrally through `ResearchProgressBarFonts.setText` / `setHtmlText`, so every text field — tooltips, mode buttons, counters, markers, status line — picks it up. Fixes issue #3 (Korean) and covers European scripts.
- Gap: Malgun Gothic does not cover Japanese (kana/kanji), Chinese (Han), Thai, Arabic, or Hebrew, which still render as boxes. WoT ships clients in several of those languages, but no single guaranteed-present Windows font covers all of CJK.
- Universal fix to investigate: instead of hardcoding an OS font, point the fallback at one of WoT's own registered Scaleform fonts (GFx `$`-prefixed, e.g. `$FieldFont`), whose per-locale glyph fallback Wargaming already configures. GFx would then resolve whatever the active client language needs, covering every WoT-supported language at once — the genuinely universal solution.
- Why it is not a quick swap: the code change is one line (`FALLBACK_FONT_NAME` in `ResearchProgressBarFonts.as`, now centralized), but the validation is the real work:
  - Confirm the exact WoT font name in-game; it may differ between client versions.
  - Verify a mod-loaded SWF can resolve WoT's `$`-named GFx fonts from its own context.
  - `embedFonts` semantics differ for GFx font-lib fonts (likely `embedFonts = true` with the `$` name, not the `embedFonts = false` device-font path used for Malgun Gothic).
  - Add a graceful chain (WoT font -> Malgun Gothic -> `_sans`) so a wrong/missing name degrades instead of showing boxes.
  - Needs an in-game test cycle per target language.
- Keep the Malgun Gothic fallback as the shipped baseline until the WoT-font approach is validated.

## Hangar Loadout Bar Blanking (unfinished investigation)

The original symptom is still unexplained: researching a field modification from the progress
bar's overlay makes the hangar's ammo/loadout bar disappear until the vehicle is switched. The
existing refresh recipe (see [Events And Callbacks](docs/reference/events-and-callbacks.md))
ran and reported success in the log, and the panel blanked anyway — so the recipe is either
insufficient for that flow or fixing the wrong thing.

- `zanju_rpb/panel_watch.py` was written to settle it and has never produced a reading. It
  samples the panel either side of a repair and on a 1s timer, and logs only when its answer
  changes; a `WARNING` line names which of three stories is true (stale vehicle copy / sections
  emptied / sections gone). **Reproduce the blanking once with it enabled and read the log.**
- `ENABLED = True` at the top of that module is the switch. It ships enabled today. Decide
  deliberately: leave it on until the bug is caught, or flip it off and lose the diagnostic.
  It only discovers panels at repair time, so it costs nothing outside a garage.
- Candidate lead if the probe exonerates the stale copy: the repair fires
  `wrapper.onItemUpdated(None)`, which lands on `_updateAmmunitionGroupsController(recreate=False)`
  and updates the section models *in place*. `InteractingItem` also has `onAcceptComplete`,
  whose handler passes `recreate=True` and rebuilds them — the path the game itself uses after
  an accepted change. A field-mod research can change the panel's shape (it is how the second
  loadout is unlocked), so a full recreate may be the correct repair.

## Research Progress Bar Dynamic Coloring

- Done so far: marker **icons**, Field Mods **level labels**, and tooltip **prerequisite icons** are recoloured at runtime to their marker's state via a single per-state colour table in `ResearchProgressBarIconTint.as` (multiply `ColorTransform` on each `Bitmap`, not the shared `BitmapData`; prestige badges excluded). The exact-vs-brighter design question is settled as **exact dash colour** (constants sampled from the dash PNGs: default `0x9CA4AB`, green `0x9CCB68`, yellow `0xE4B55A`, white `0xF6F1E7`).
- Follow-up: extend the same runtime tint to the **marker dashes** and the **progress-bar fills**, retiring the per-colour PNGs so the whole bar's palette lives in one code table.
  - **Marker dashes (4 → 1):** `marker_default/green/yellow/white.png` (4×14) share a pixel-identical alpha; they differ only in hue. Collapse to one greyscale master tinted per `markerState` in `ResearchProgressBarMarkers.createMarkerBitmap`. `marker_white` already works as the near-white master (white = identity tint). The four tint colours are the same constants already in `ResearchProgressBarIconTint`.
  - **Progress-bar fills (4 → 2):** `progress_bar_green/yellow/white.png` (80×8) share an identical alpha (full rect), hue-only difference → one greyscale master. `progress_bar_base.png` has a **different** alpha (the empty track) → keep it a separate asset. The three colour fills are stacked (`ResearchProgressBarViewFactory` lines ~66-73) but each is masked to a **disjoint** horizontal slice (`completedMaskShape`/`combatMaskShape`/`freeMaskShape`), so they never blend — keep the three `Bitmap` instances, embed the one master, and apply a **different `ColorTransform` per instance**; masks stay untouched.
  - Both plug into the existing `ResearchProgressBarIconTint` colour table (single source of truth); build a shared `tintBitmap(bitmap, color)` helper so dashes and fills reuse the icon path.
  - Caveat: multiply-tint needs a near-white master; if a specific green/yellow must read deeper than `white × tint` can reach, that one master needs a brightness lift (same as the filter-icon pass).
- Verifier: `scratchpad/png_probe.py` (pure-Python PNG decoder, no PIL) reports per-variant alpha match / hue / peak and samples dash peak RGB — rerun it if the assets change before wiring.

## Research Progress Bar Guardrails

- Fix the garage layering / z-index issue between the mod UI and the filters window; some mod tooltips still render below foreground elements.
- Evaluate whether tank research totals should include the cost of prerequisite modules before a tank unlock.
- Check which upgrade is actually reachable right now and list all currently missing upgrades.
- Turn `research-progress-bar` `configVersion` into a real migration hook: add versioned forward migrations, defaults for new keys, and pruning for renamed/removed keys instead of only carrying `configVersion = 1` forward on save.
- Out of scope unless explicitly requested: changing mode semantics.
- Out of scope unless explicitly requested: redesigning the Scaleform layout.
- Out of scope unless explicitly requested: removing the production garage visibility-probe behavior.
- Future AS3 naming/package cleanup: build a second fake test mod and use it to collision-test default-package class names, helper names, and source/output path overlap before renaming `ResearchProgressBar*.as` files or introducing an AS3 package tree; the earlier unique-path finding justifies this test method, but file-path collisions and class-name collisions need to be validated separately.
- Future refactor guardrail: treat reflective prestige/elite adapter helpers in `zanju_rpb.main` as load-bearing runtime-contract code, not obvious dead code; before deleting or simplifying them, validate in-game across elite non-tier XI vehicles, tier XI vehicles, `eliteMode=customization_only`, and repeated vehicle switches.