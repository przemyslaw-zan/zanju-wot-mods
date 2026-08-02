# Gameface Mod Widgets

How to put a mod's own interactive HTML widget into the garage, and the traps this
renderer sets. Verified against WoT **2.3.1.0**.

Sources: the `premium-time` header integration in this repo, and
[drizzer14/garage-progress-bar](https://github.com/drizzer14/garage-progress-bar), whose
widget solves the same problems and whose author documented the reasoning in-code.

## Getting code into a document

`net.openwg.gameface` is the only practical route. Its bootstrap runs in every Gameface
document and scans that document's **sub-views** for a `ModInjectModel`, then loads the
styles/scripts/modules it lists. `openwg_gameface.gf_mod_inject(model, name, modules=[...])`
attaches one.

Two consequences that are easy to get wrong:

- **Root views are never scanned.** Only `window.subViews` is walked, so a view whose model
  is the document root (`window.model`) can never be reached this way. This is why the WoT
  Plus tooltip needed a shadowed document shell instead (see
  [WoT Plus Subscriptions](wot-plus-subscriptions.md)).
- **One mod per sub-view.** `gf_mod_inject` always writes to the fixed field name
  `ModInjectModel`, so two mods targeting the same sub-view silently clobber each other,
  last writer wins. A widget that wants to coexist should keep a priority list of candidate
  sub-views and inject onto the first *free* one; occupancy can be detected by serialising
  the view model (`toString()` yields its field names as JSON).

Documents worth knowing (`mono/hangar/...`): `main` is the persistent garage document and
loads exactly once per garage session; `header` and `footer` likewise; `tooltips` and
`vehicle_tooltip` are recreated constantly. A widget that should live for the whole garage
session belongs in `main`.

## Talking back to Python

Wulf view-model **commands** are the JS→Python channel (a data model with `commands=0` has
none). Wulf surfaces a command as a callable on the model, and it takes exactly **one map
argument** — passing a bare scalar is rejected by Gameface as "not a map", so scalars are
conventionally wrapped as `{value: x}`. Whether the callable lives on the wrapped proxy or
its unwrapped value differs across builds, so try both.

That is how a widget persists state: the JS reports e.g. its dragged position through a
command, Python stores it, and the next push re-applies the same coordinates.

## Pointer events: the big one

**The widget root must be `pointer-events: none`.** The garage listens for drag-to-rotate on
the scene; an overlay that accepts pointer events anywhere will steal it and the player can
no longer turn their tank.

Re-enable pointer events on exactly **one** child — a transparent "hot" overlay covering the
interactive area — and route all interaction through it. In this Coherent build, elements
nested under a `pointer-events: none` root do **not** reliably receive events even when they
set `pointer-events: auto` themselves, so a single hot element is the reliable shape rather
than per-control opt-in.

## Dragging

- **Give the drag its own handle.** An ungated drag makes every click on the widget a
  potential accidental move, and conflicts with clicks the widget itself wants. The reference
  gates on Ctrl; a title bar that is the only draggable strip works as well and costs the
  player no modifier (`directives-helper`).
- Listen for `mousedown` at **document level in the capture phase**, registered once behind a
  flag that survives re-mounts.
- Claim a drag only when `root.contains(e.target)` — ownership by DOM subtree, not by
  hit-testing rectangles. OpenWG drops several mods into the same document as body siblings
  at similar z-index, any of which may also be draggable; a rect test can match two widgets
  at once and then registration order decides nondeterministically. Never
  `stopImmediatePropagation()` for an event that is not yours.
- Clamp to the viewport so the widget cannot be dragged off-screen.
- Store the viewport size alongside the coordinates, so a later resolution or UI-scale change
  can rescale the position proportionally instead of stranding the widget.

## Showing the widget only when it belongs

A garage widget usually wants to be visible on the garage screen and nowhere else. Two ways
to decide, and only one of them survives contact with the game's alternative modes.

**Do not match the lobby route.** The lobby logs `Navigating to <route>` and
`Visible route changed to: <State>(<route>)` under `gui.lobby_state_machine.lobby_state_machine`,
which is tempting to read with a logging handler. It does not generalise: routes are
mode-prefixed, so Onslaught's garage is `subScope/subLayer/comp7Light/hangar/{root}` rather
than `subScope/subLayer/hangar/{root}`, and every mode needs its own entry. Worse, a route
says nothing about what the screen actually offers.

**Hook the panel that owns the feature.** For anything tied to the vehicle's loadout, that is
`gui.impl.lobby.hangar.presenters.loadout_presenter.LoadoutPresenter` — the bottom bar with
shells, consumables, optional devices and directives. Every mode subclasses it (Onslaught,
Frontline, Last Stand, Fun Random, Battle Royale) and only Battle Royale overrides its
lifecycle, so patching the base class covers all of them:

| Hook | Meaning |
| --- | --- |
| `_onLoading` | the panel is now on screen |
| `_updateAmmunitionGroupsController` | the vehicle, setup or mode changed — re-read it |
| `_finalize` | the panel is gone |

Which slots the panel carries comes from its groups controller, reachable as the presenter's
`_getGroupController` property. `controller._getGroups()` returns `GroupData(groupID, sections)`
records, and a feature's slot exists exactly when its `TankSetupConstants` name is among the
`sections` — `battleBoosters` for directives, `optDevices`, `shells`, `consumables`,
`battleAbilities`. Asking the controller rather than reproducing its decision matters because
modes disagree and some change their mind while the player stands in them: Fun Random builds
its groups from the active sub-mode's configuration flags, Last Stand from the player's chosen
panel preset, Onslaught just reuses the random-battle groups.

Hold the tracked presenters weakly and key visibility on "any panel on screen offers it": the
incoming mode's panel can load before the outgoing one is torn down. Degrade to *visible* if
the hook cannot be installed — a widget in the wrong place is a nuisance, one that never
appears is a broken mod.

## Layout and units

- `position: fixed` for the root.
- Prefer `vh` over `rem` for a vertical anchor. WoT's UI scale keeps `rem`-sized things at a
  constant apparent size but is quantized per resolution bucket, so a `rem` offset drifts
  across resolutions; `vh` is unquantized and height-proportional.

## CSS the renderer does not implement

Confirmed by the game's own stylesheets never using them, and by live warnings:

| Property | Status |
| --- | --- |
| `font-variant-numeric`, `font-feature-settings` | Ignored — tabular figures unavailable even though PFDINMax ships `tnum` |
| `align-items: baseline` | Rejected outright: *"Trying to set alignItems property to invalid value"* |
| `display: inline-block`, `ch` units | Never used by the game; avoid |
| `display: flex`, `min-width`, `text-align`, `letter-spacing` | Used heavily by the game; safe |

**Blockify flex items yourself.** A flex item is supposed to be blockified automatically, so a
`<span>` child of a `display: flex` parent should behave as a block container. Do not rely on
it: set `display: block` (or use a `div`) whenever you give a flex child a `width`, a `height`,
`text-align`, or absolutely positioned children. The symptom of getting this wrong is nasty
because it is silent and *asymmetric* — the identical rule works wherever something else already
forced the element to `display: block`, so the same class centres correctly in one place and not
another, and no amount of tuning the text properties fixes the broken one.

**Prefer drawing a small mark to typing it.** `text-align: center` centres a glyph's *advance
width*, not its ink, so a character with uneven side bearings (`!` is the classic) sits visibly
off inside a round badge. Two positioned boxes are centred by arithmetic, come out identical
everywhere, and put the stroke weight under your control rather than the font's — see the warning
badge in `directives-helper`, drawn as a rounded stem plus a dot.

`text-indent` and negative `letter-spacing` were both tried as nudges and neither moved the
glyph, but that evidence is confounded: the element was an unblockified flex item at the time,
i.e. an inline box, where neither property affects placement. Whether they work on a proper block
container here is untested — do not treat them as known-broken.

To monospace digits without a monospace font, lay each digit out in a fixed-width flex cell
sized from a measured probe (see `header_patch.js` in `premium-time`).

## Logging

`console.log` is **not** forwarded to `python.log`; `console.error` is, and arrives prefixed
`ERROR: Main: [Gameface] ...`. OpenWG's own `debug.js` uses `console.error` for the same
reason.
