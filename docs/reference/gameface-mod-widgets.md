# Gameface Mod Widgets

How to put a mod's own interactive HTML widget into the garage, and the traps this
renderer sets. Verified against WoT **2.3.1.0**.

[Choosing A UI Approach](choosing-a-ui-approach.md) says when to take this route rather than one of the other two.

Sources: the `premium-time` header integration in this repo, and
[drizzer14/garage-progress-bar](https://github.com/drizzer14/garage-progress-bar), whose
widget solves the same problems and whose author documented the reasoning in-code.

This page is about the **injected** route: a mod's HTML inside a document the client owns. That is
what pins a widget to the host document's band and creates most of the traps below. A mod can
instead own its window and its band outright — see the standalone route in
[Choosing A UI Approach](choosing-a-ui-approach.md), whose mechanics are upstream in
[gameface-standalone](https://modding.wot-tools.dev/gameface-standalone.html).

## Getting code into a document

For the injected route, `net.openwg.gameface` is the only practical way in. Its bootstrap runs in every Gameface
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

## Hearing about changes from Python

The other direction has a trap. Python writing a view-model property does **not** raise an
event on the JS side, so the obvious implementation is a `setInterval` that re-reads the model
— and that is a poll, with the latency to match. A widget on a one-second timer looks visibly
broken next to the game's own panels: the player switches tank, the ammo bar updates at once,
and the widget follows a beat later.

The engine does have a push signal. Register interest in a sub-view's model and listen for the
document's data-changed event:

```js
engine.on('viewEnv.onDataChanged', onChanged);
// Third argument covers descendants — a mod's own child model, not just the sub-view's.
viewEnv.addDataChangedCallback('model', resId, true);
```

This is what `net.openwg.gameface`'s own `res/gui/gameface/mods/libs/model.js` (`ModelObserver`)
does, and it is the reference for the exact call shapes. Two things it does not spell out:

- **The event is document-wide.** The callback registration names one `resId`, but the
  `engine.on` handler fires for *any* registered write in that document, at whatever rate the
  document happens to change. So the handler must be cheap. Anything that scans every sub-view
  to locate its own model has to remember which one it found and re-check that one directly,
  falling back to the scan only when it comes up empty — otherwise the push costs more than the
  poll it replaced.
- **The subscription names one sub-view, and the garage replaces it.** `addDataChangedCallback` is registered against a single `resId`. Picking a different tank tears the sub-view down and builds a new one with a new id, and the subscription is left naming a view that no longer exists — every push after the first tank change goes nowhere. A model *finder* that rescans on demand hides this, because the data keeps arriving on the poll: the symptom is not "no data" but "data that is a second late, but only after the player has switched tank once". Re-register whenever the id you found moves, and do not guard the whole thing behind a "already subscribed" flag on the document.
- **Keep the interval as a backstop, and make its rate adaptive.** `engine` and `viewEnv` are
  not guaranteed to be there, and the subscription cannot be made until the sub-view carrying
  the model exists — which is often *not* true on the first tick. Poll fast until the
  subscription succeeds, then drop to a slow safety-net rate. A rate decided once at start-up
  gets this backwards and stays fast forever.

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
shells, consumables, optional devices and directives. Onslaught, Onslaught light, Frontline, Last
Stand and Fun Random each subclass it from their own extension package, and none of them
overrides these three methods, so a patch on the base class covers all five:

| Hook | Meaning |
| --- | --- |
| `_onLoading` | the panel is now on screen |
| `_updateAmmunitionGroupsController` | the vehicle, setup or mode changed — re-read it |
| `_finalize` | the panel is gone |

**Battle Royale is not one of them.** Its panel is `BattleRoyaleLoadoutPresenter`, a plain
`ViewComponent` reached through `LoadoutContainerPresenter`, with no relation to
`LoadoutPresenter`. A base-class patch never fires in that garage, so a widget gated this way
stays hidden there. Decide whether that is what you want: the "degrade to visible" rule below does
not help, because the hook installs correctly and is simply never called.

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

## Stacking against other mods

**`position: fixed` creates a stacking context on its own**, with or without a `z-index`. A mod's overlay root is usually fixed and full-screen, which seals its whole subtree into one layer of the page: a tooltip inside it asking for a huge `z-index` still cannot rise above anything the *root* sits under. So the number that decides where a mod sits against other mods belongs on that root, and nowhere else. Left unset, a fixed root sorts as zero and loses to every mod that named a number.

Mods in this repository take these, so a new one has somewhere to sit without a collision:

| Mod | Root | Number |
| --- | --- | --- |
| `directives-helper` | window overlay | 900 |
| `campaign-tracker` | widget root | 1000 |

The number decides nothing outside this document. Every view is a document of its own, and the band it sits in decides which document draws over which. A Scaleform mod view on `WINDOW` therefore covers everything here, whatever number the roots carry. See [Window Layers](ui-and-scaleform.md#window-layers).

Ordering *within* a root is a separate question from the number above. Sibling widgets paint in document order, so a later sibling covers the tooltip of an earlier one. Lift the whole widget on `:hover` rather than just its tooltip, or the tooltip appears to detach from the thing it describes.

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
| `display: inline`, `display: inline-block`, `ch` units | Effectively unavailable — see "Text wraps by flex line" below |
| `width: max-content`, and by extension `fit-content` | Dropped — the width falls back to `auto`, so a block-level box silently stays as wide as its surface. Measured in `campaign-tracker`: the declaration changed nothing at all. There is therefore no way to size a box from its own content in a document the mod owns, which leaves a stated width as the only option. |
| `display: flex`, `min-width`, `text-align`, `letter-spacing` | Used heavily by the game; safe |

**Blockify flex items yourself.** A flex item is supposed to be blockified automatically, so a
`<span>` child of a `display: flex` parent should behave as a block container. Do not rely on
it: set `display: block` (or use a `div`) whenever you give a flex child a `width`, a `height`,
`text-align`, or absolutely positioned children. The symptom of getting this wrong is nasty
because it is silent and *asymmetric* — the identical rule works wherever something else already
forced the element to `display: block`, so the same class centres correctly in one place and not
another, and no amount of tuning the text properties fixes the broken one.

**`flex: 1` does not zero the basis.** The shorthand is supposed to mean `flex-grow: 1; flex-shrink: 1; flex-basis: 0`, which makes sibling items come out the same width. Here the item keeps being sized from its content and then given an equal share of the slack, so two items with different text end up different widths — the `flex-basis: auto` behaviour. The symptom is a layout that is *almost* right: two rows of `X / Y` centred on their separator drifted apart by half the difference between their numbers, about 2.5rem. State the basis with a unit instead — `flex: 0 0 19rem` — which is the game's own fixed-width flex item (48 uses of `flex: 0 0 13rem`). To centre something between two flexible sides, give both sides the same stated width and centre the row: the offsets cancel and the middle lands in the middle whatever the content is.

**Text wraps by flex line, not by inline flow.** There is no usable inline layout here. The game's own stylesheets carry `display: flex` 7821 times, `display: block` 114 times, and `display: inline` 3 times. None of those three uses puts two inline boxes on one line. A paragraph with one coloured word in it cannot be a block with a `<span>` inside: the span stacks above the text and reads as a heading above it. The game's own answer is to split the string on spaces, give every word its own element, and wrap the row with `display: flex; flex-wrap: wrap` — its formatted-text component does exactly this, and `.FormatText_base` carries those two properties. Supply the gap between words yourself with `margin-right`, because the split threw the real space away. Measure it rather than guess it: PFDINMax, the family `body` sets, gives its space an advance of 0.195 em, and the inherited `letter-spacing: 0.02em` supplies the rest. See `buildRestriction` and `appendWords` in `campaign-tracker`.

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

## A Standalone Document Inherits None Of The Game's Base Styling

The Gameface bootstrap sets the root font size to the interface scale — `document.documentElement.style.fontSize = scale + 'px'` — which is why `rem` is the unit everything here is written in. One `rem` is one pixel at scale 1.

The consequence only bites a document the mod owns. An element with no `font-size` of its own renders at `1rem`, which is **one pixel**. Inside a document the client owns that never happens, because `mono/hangar/global/global.css` sets a base on `body`. A standalone document gets none of the game's stylesheets, so the first build of a moved tooltip drew the whole thing a pixel tall.

Declare the base yourself. These are the values that file sets, on 2.3.1.3:

```css
body {
    color: #ede6d9;          /* var(--color-general-primary) */
    font-size: 14rem;
    font-family: PFDINMax;
    font-weight: 400;
    letter-spacing: 0.02em;
}
```

It also switches to `Warhelios` with `letter-spacing: 0` for `html[lang]` of `ja`, `ko`, `zh_tw`, `zh_sg`, `zh_cn`, `vi` and `th`, which a document rendering the client's own strings should mirror.

Copy the values rather than linking the game's stylesheet: linking pins the mod to a resource path, and that file also sets `width` and `height` to `100%`, which fights the sizing a standalone panel needs. Re-check them after a client update — the word gap in "Text wraps by flex line" above is measured against PFDINMax at this letter spacing.

**The game's `body` is rarely the whole inherited environment.** What a moved subtree inherited came from every ancestor it had, and the nearest one setting a property wins. A widget wrapping the subtree typically sets `color`, `font-size` and `line-height` of its own, so those come from the widget and only the untouched ones — family, weight, letter spacing — come from the game. Reproducing the game's `body` alone gets the second group right and silently restyles the first: in this repo it turned every unstyled line in a tooltip from a cool grey to the game's warm cream, which reads as correct until it is put beside the original.

Walk the old ancestor chain before writing the new base, and take each inheritable property from the nearest ancestor that set it.

**Sizing needs the same care, in two places.**

The *width* is the first. A block-level flex container is as wide as the space it is given, so measuring one reports the width of whatever native surface the view started with rather than the width of the content. State the width instead. Taking the root out of the flow to shrink-wrap it looks like the other answer and is a worse one: the document then has no height, the engine never finishes sizing the view, and it logs `Size calculation timeout. Set the default view size.` before falling back to a size of its own.

The *moment of measurement* is the second, and it fails intermittently, which makes it hard to read. `getBoundingClientRect()` called in the same frame that built the DOM reports the layout as it stood **before** the new content. The height comes back short, `resizeViewPx` hands the native surface that short height, and whatever sits at the bottom of the panel falls outside it and is clipped. It reads as random because the error is the difference between the old layout and the new one, so it depends on what was rendered previously.

Wait two animation frames after every render, not only after the first one, then measure. Measure once more a frame later and republish only if the number changed — that costs one comparison and catches a late settle such as a font arriving between the two passes.

**A hidden window runs no frames, which turns that wait into a deadlock.** `requestAnimationFrame` does not fire in a Wulf window that is hidden, so a panel cannot measure itself while it is off screen. Python waiting for a size before showing the window, and JavaScript waiting for a frame before reporting one, is a stand-off that produces no error at all: eleven hovers produced no measurement until an unrelated route change happened to render the view.

Order it the other way round. Show the window first, at whatever size and position it last had, and keep the panel's own root transparent until Python has moved it:

```css
.panel        { opacity: 0; }
.panel-shown  { opacity: 1; }
```

The window is then on screen and empty for the frame or two the measurement takes, which paints nothing and costs one extra push to reveal. Guard that push against re-rendering: a payload arriving with the same identity is a changed field, not a new panel, and rebuilding the DOM there would discard a measurement that was already correct and start the handshake again.

## An Overlay That Carries Its Own Text Can Shift Its Siblings

`directives-helper` draws a 48rem icon tile with three absolutely positioned overlays: the perk gain top-right, the depot count bottom-left, and the name above the tile, shown on hover. Pointing at a tile made that tile's gain and count paint some 40rem to the left, over the neighbouring tile, until the pointer left again.

**The elements were never wrong.** A check ran on every render comparing each overlay's `getBoundingClientRect` with its tile's, across 37 rebuilds with the fault occurring, and never once reported a box outside its tile. The rectangles were right and the pixels were not, which is why nine rounds of restructuring the DOM changed nothing.

What fixed it was rebuilding the name overlay in the client's own shape. It had been one absolutely positioned box carrying `transform: translateX(-50%)`, its own text, and its own background. It became a positioned box that only positions — no transform, centred instead by overhanging the tile equally on both sides with `justify-content: center` — with the panel and the text on an inner `display: flex` child. That is how `Counter` is built in the client's own stylesheets: `Counter_base` positions, `Counter_value` holds the text, `Counter_bg` paints behind.

**Do not read this as "transforms are broken".** The client's stylesheets use `transform` 30,644 times and `translateX(-50%)` alone 504 times. Four things changed together here and none was isolated, so what is established is the shape that works, not the single declaration at fault. If you need the diagnosis narrowed, the cheap experiment is to put the transform back on its own.

The general lesson is the one the `Counter` pattern already states: a positioned box positions, and text lives in a flex child of it. An overlay that positions itself *and* renders text *and* paints a background is the shape that misbehaved.

## Logging

`console.log` is **not** forwarded to `python.log`. `console.error` is, and arrives prefixed `ERROR: Main: [Gameface] ...`. OpenWG's own `debug.js` uses `console.error` for the same reason.

**Neither one is forwarded until the console mod is turned on.** The forwarding belongs to `net.openwg.console`, and that mod ships disabled. `mods/configs/net.openwg.wot.common/console.json` holds one flag:

```json
{ "enabled": false, "shortcut": "CTRL+ALT+`" }
```

While it reads `false`, the loader still reports the mod as loaded in `python.log`, and every `console.error` in every mod document goes nowhere. Nothing warns you. A whole session of diagnostics was written and read back as an empty log before anyone checked the flag, so check it first: if a `console.error` you are certain runs produces no line, the flag is the reason, not the code.

Set it to `true` and restart the client. The same flag also binds the in-game console overlay to its shortcut.
