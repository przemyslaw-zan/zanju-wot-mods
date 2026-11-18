# TODO

Open work only. When an item is finished, delete it from here and put whatever is worth keeping in [the technical reference](docs/reference/README.md) — the backlog is not a changelog, and a finished item left in it reads as a thing still to do.

## Format-And-Lint Follow-Up

- Rerun `zwm lint check` after the `research-progress-bar` cleanup and reassess whether `max-complexity = 25` should stay as-is or be tightened further.

## General Refactor Backlog

- Broad runtime splitting for `research-progress-bar` is mostly complete; only reopen it if `mods/research-progress-bar/src/zanju_rpb/main.py` or `mods/research-progress-bar/src/zanju_rpb/scaleform/modes.py` grow enough to justify another targeted slice.

## Gameface Mods: The Rest Of The In-Game Check Of The Sub-Views And The Shared Plumbing

Every Gameface mod of ours now rides on a child view of its own (see [Getting code into a document](docs/reference/gameface-mod-widgets.md#getting-code-into-a-document)), and the duplicated script plumbing is in `mods-common/gameface/` (see [Shared Modules](docs/reference/runtime-layout-and-packaging.md#shared-modules)). With all mods together, the garage parts of DH, PT, CT and CRT and the CRT battle panel passed in game on 16 October 2026, and each of them passed alone on 25 October 2026. One part of the [in-game check](docs/testing.md#in-game-check-after-a-change-to-a-shared-module) is still open:

- DH in a mode garage, when one is in rotation: the window comes from a child of that mode's root view, and the log names the root view.

Delete this section when it passes, and move any finding into the reference.

## Crucible Tracker: Open Checks

See [Crucible](docs/reference/crucible.md#in-battle) for what the battle panel counts and what was measured.

- A reconnect into a battle: the panel must show the conditions with no figures, and the log must say `a reconnect, so the counters are off`. No battle has dropped yet.
- More award rules in `AWARD_RULES` of `crucible.py`, when a mission asks for an award other than High Caliber, Top Gun, Fighter or Duelist. Each rule needs the terms of the award from the player, and the record name from `DB_ID_TO_RECORD`.
- Spotted enemies: compare `spotted` in the totals of `Battle panel at the end:` with "Spotted" in the detailed battle results. Any battle with the panel open shows it.
- Critical hits: compare `critsCount` in the same totals with "Critical hits" in the detailed battle results.
- Duelist: a real mission must show that the server counts the kills of enemies that damaged the player, also when the damage came after the kill.
- Kills of different classes: only a mission with more kills than classes, such as 3 kills of 2 classes, can show the rule of the server. The panel expects at least that many kills that cover at least that many classes.
- Whether the server checks "within the view range of your vehicle" against the capped view range, as the panel does. Only a real mission that the hits beyond the range decide can show it.

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

## CI / Toolchain Backlog

- Restore a "WoT is running" guard for deploy/cleanup/cycle. It was removed in the Docker migration because a Linux container can't enumerate Windows host processes (`tasklist`). Viable options: (a) a host **PowerShell** wrapper that runs the `tasklist` check before invoking the container (no install needed — PowerShell is built in); (b) a file-lock probe on a known WoT-held file; (c) a `--force`/`--skip-running-check` opt-out if a host check is reintroduced. Until then, deploy relies on file-lock `PermissionError` handling (in-use files are skipped) — close WoT manually.

## Release And Distribution Backlog

- Add a `research-progress-bar` release checklist for wgmods.net and modpack submission: standalone companion bundle contents, config/i18n copy requirements, no-optional-UI-API smoke test, and re-test expectations for each WoT version even when no code change is planned.

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
- The probe ships **off** — it is a diagnostic for a bug nobody is actively hunting, and a
  release should not carry its timer and log stream idling. **Arm it before attempting a
  reproduction**, or the steps above produce nothing at all. Arming needs no code change:

      %APPDATA%\Wargaming.net\WorldOfTanks\mods\Zanju\research-progress-bar\probe.on

  Create that file (empty — only its existence is read), restart the client, and `Loadout bar
  probe armed by probe.on` appears in `game.log`. Delete it to disarm. The build stays
  byte-identical to the one users get, and nothing is left sitting in the working tree waiting
  to be committed by accident. `ShippedStateTest` pins the source default off.
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

## Research Progress Bar: Is A Gameface Bar Worth It?

Open question, not started. The bar sits on `WindowLayer.WINDOW` (7) and draws over the x5 counter mod. To get under that counter costs either the dimming of band 3 or a rewrite of the bar as a Gameface view. Two cheap measurements decide it. Take both before you write any Gameface code.

Context: no band below 7 works for a Scaleform mod view. `MARKER` (3) draws under the garage document, but that band composites with the scene, so the whole view goes dim. `VIEW` (4) gives an empty garage. `SUB_VIEW` (5) is the garage document.

`TOP_SUB_VIEW` (6) belongs to the legacy Scaleform lobby. A view there makes the legacy page call `setRequiresOldStyle`. The lobby header then gains a background, and the container pushes the view down the screen. See [Window Layers](docs/reference/ui-and-scaleform.md#window-layers).

**Measurement 1: does a Gameface view escape the legacy chrome on band 6?** The claim is that `OLD_STYLE_VIEW` triggers the chrome, and that a Wulf view lacks that flag. That is an inference from the name of a constant. The legacy lobby SWF makes the decision, and we did not decompile it. The trigger could instead be an occupied sub-view container.

Test this without a rewrite. The campaign tracker card is already a working standalone Gameface window. Change `_layer()` in `mods/campaign-tracker/src/zanju_ct/gameface/card_window.py` to return `WindowLayer.TOP_SUB_VIEW`. Run `zwm cycle campaign-tracker`, then open the garage and look at the top bar. If the header keeps its transparent hangar style, the inference holds.

**Measurement 2: which band holds the x5 counter?** Nobody knows yet, and the answer decides whether band 6 helps at all. If the counter sits on `SUB_VIEW` (5), no band above it helps, and the rewrite buys nothing.

The mod is `oldskool.x5counter_1.0.1.wotmod`. It ships a standalone Gameface view under the item ID `OldSkoolX5CounterView`, with an empty `extension`, so it is not a hangar injection. The mod also obfuscates its Python with pjorion, behind a zlib and marshal payload, and it mangles the inner names. The file therefore does not give up the band. Dump the Wulf window manager instead. Log the layer and the layout ID of every window.

Our earlier band log named `GUIFlash`, `xfw_injector`, `ModsListButton`, `TomatoGGLobbyUI` and `ExpectedVehicleValueGarage` on band 7. It did not name this counter.

**Cost if both measurements pass.** The bar is the largest ActionScript surface in the repo. A rewrite must carry the embedded fonts, the bitmap masks, the marker hit tests, the keyboard pick stack and the mode buttons. Weigh that against the dimming of band 3, which costs one constant and no new code.

## Research Progress Bar Guardrails

- Garage layering, settled for now. The bar sits on `WindowLayer.WINDOW` (7). Every band below it charges something, and [Window Layers](docs/reference/ui-and-scaleform.md#window-layers) records the price of each. The bar therefore draws over the Gameface garage document, and over every mod widget inside it. To lower it further needs a Gameface rewrite. Read the section above first.
- Evaluate whether tank research totals should include the cost of prerequisite modules before a tank unlock.
- Check which upgrade is actually reachable right now and list all currently missing upgrades.
- Turn `research-progress-bar` `configVersion` into a real migration hook: add versioned forward migrations, defaults for new keys, and pruning for renamed/removed keys instead of only carrying `configVersion = 1` forward on save.
- Out of scope unless explicitly requested: changing mode semantics.
- Out of scope unless explicitly requested: redesigning the Scaleform layout.
- Out of scope unless explicitly requested: removing the production garage visibility-probe behavior.
- Future AS3 naming/package cleanup: build a second fake test mod and use it to collision-test default-package class names, helper names, and source/output path overlap before renaming `ResearchProgressBar*.as` files or introducing an AS3 package tree; the earlier unique-path finding justifies this test method, but file-path collisions and class-name collisions need to be validated separately.
- Future refactor guardrail: treat reflective prestige/elite adapter helpers in `zanju_rpb.main` as load-bearing runtime-contract code, not obvious dead code; before deleting or simplifying them, validate in-game across elite non-tier XI vehicles, tier XI vehicles, `eliteMode=customization_only`, and repeated vehicle switches.

## Research Progress Bar: Where The Bar Is Allowed To Show

Checked at client 2.4.0.0. Nothing changed yet. The bar has **no battle-mode condition**. Every rule it has asks where the player stands in the lobby. The Onslaught hide then falls out of one of those rules by accident, not by intent.

`_get_scaleform_block_reason` in `mods/research-progress-bar/src/zanju_rpb/scaleform/gate.py` asks six questions in order. The first failure names the block reason in the log:

1. `is_active` — the mod is running.
2. `scaleformPrototypeEnabled` — the config kill switch.
3. `preview_present` — a vehicle preview is up.
4. `vehicle_present` — a tank is in the garage.
5. The lobby route is exactly `subScope/subLayer/hangar` or `subScope/subLayer/hangar/{root}`.
6. The SUB_VIEW and TOP_SUB_VIEW aliases are a hangar view or the bar itself.

A `None` payload then hides the bar as `populated_no_modes`, outside the gate.

Rule 5 is the one that hides the bar in Onslaught. It also hides it in Frontline, Steel Hunter, Last Stand and Fun Random. Ranked, Mapbox and Maps Training share the plain `hangar` route, so the bar remains there. That is the wanted answer, reached by accident.

### Two faults, separable

**Rule 5 is an exact match of two strings.** Any garage with a lobby state of its own loses the bar, whatever the mode. This is the stricter form of the fault the campaign tracker fixed in 1.1.0. A seasonal garage is the case to worry about, and one is live already. `VIEW_ALIAS.LEGACY_LOBBY_HANGAR` is `legacyHangar`. Rule 6 accepts it through `_HANGAR_VIEW_ALIASES`, and rule 5 rejects the route `subScope/subLayer/legacyHangar`. Rule 5 runs first, so the legacy garage loses the bar that rule 6 means to allow.

**The route comes out of log text, and the gate fails open.** `main.py` attaches a `logging.Handler` to the logger `gui.lobby_state_machine.lobby_state_machine`. It matches the prefixes `Visible route changed to: ` and `Navigating to `. Reword either line, or quiet that logger, and `_current_lobby_route_path` stays `None`. Rule 5 reads `if current_lobby_route_path is not None`, so a missing route skips the rule rather than fails it. The bar then shows in Onslaught, with nothing in the log to say why. The campaign tracker instead subscribes to `LobbyStateMachine.onVisibleRouteChanged` and reads `getStateID()`. That needs no text, and it fails closed.

### What to do

- Replace the log scraping with the `onVisibleRouteChanged` subscription in the shared `mods-common/route_gate.py`: import it in `research-progress-bar`, and the build ships it. Same signal, no parsing.
- Then settle the rule itself. **Decide this first, it is not obvious.** One option matches a trailing `hangar` segment the way the tracker does, then subtracts Onslaught by name, because the reason to hide there is the shape of that mode's UI. The other gates on the battle mode.
- Do not copy the tracker's mode gate. It answers "random battles alone". Ranked earns vehicle XP and must keep the bar.

