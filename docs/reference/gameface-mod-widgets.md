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
  the view model (`toString()` yields its field names as JSON). A child view of the mod's own,
  below, is the better answer, and every mod of ours now uses one.

**A mod can add a sub-view of its own instead.** A `ViewComponent` attaches each child with `setChildView(posId, child)`. The client then lists that child in `window.subViews`, also when the document's own code never uses it. OpenWG's bootstrap finds an inject model on such a child as on any other sub-view. Thus the mod takes no sub-view that another mod could want, and no other mod can clobber it.

To add one:

1. Patch the parent's `_onLoading`. Let the original run first, so that the parent's own children are in place.
2. Build a small `ViewComponent` whose model carries the `ModInjectModel`.
3. Call `_registerChild(posId, child)`. After the original `_onLoading`, this attaches the child at once.
4. Make sure that `getChildView(posId)` returns the child. If it does not, unregister the child.

Measured on 2.4.0.2 with `LobbyHeader` and `LobbyFooter`: the client attached children at `R.dynamic_ids.demo_window.bottom_panel()` and at the arbitrary number `0x5A4E4448`. The header document listed both as sub-views, and the footer took a child at `0x5A4E4448` too. The position ID needs no entry in OpenWG's `res_map`, so the client does not restart. Use a number far above the resource IDs, which count up from zero and were near 136,000 on 2.4.0.2. `directives-helper` puts its bar probe in both lobby bars this way.

Measured on 2.4.1.0 in the garage document `main`, with a throwaway probe on 14 October 2026:

- A child from a patched `RandomHangar._onLoading`, through `_registerChild`, attached at `0x5A435241`.
- `gui.shared.system_factory.registerDynamicRandomHangarPresenters(posId, factory)` is a second route, with no patch. `RandomHangar._getChildComponents` reads that list, and the client builds the child with its own children. No client code calls this function on 2.4.1.0. A factory registered in the mod's `init()` attached at `0x5A43525A` on every garage build.
- The document listed both children among its 29 sub-views. The scripts of both loaded into the same document, next to the campaign-tracker root, and each one found the root and the tray entry of the other within 160 ms.
- `MutationObserver` exists in `main`. An attribute change by one script reached an observer in the other script in 0 to 1 ms. A poll every 100 ms took up to 87 ms.

Our mods use these position IDs, each one the ASCII of a short name. Two children of one parent need two IDs, so give a new mod an ID of its own:

| Mod | Parent | Position ID |
| --- | --- | --- |
| `directives-helper` | `LobbyHeader`, `LobbyFooter` (bar probe), `RandomHangar` and each mode garage (window) | `0x5A4E4448` (`ZNDH`) |
| `campaign-tracker` | `RandomHangar` | `0x5A4E4354` (`ZNCT`) |
| `crucible-tracker` | `RandomHangar` | `0x5A435254` (`ZCRT`) |
| `premium-time` | `LobbyHeader` | `0x5A4E5054` (`ZNPT`) |

`mods-common/hangar_child.py` holds both routes. `install` adds a child to `RandomHangar`: it tries the dynamic presenter list first and falls back to the patch. `attach` patches the `_onLoading` of any root view, from a list of (module, class) pairs, and skips a class that the client does not have. `make_factory` builds the child for both. A factory that raises breaks the build of the whole garage, because `ViewComponent._constructChild` logs and raises again, so every step inside the child catches its own errors.

**A child of `RandomHangar` reaches the random garage only.** Each mode extension builds a root view of its own, with a layout of its own, such as `R.views.comp7.mono.lobby.hangar()`. Each mode garage is thus a separate document. A widget that shows in a mode garage needs a child in the root view of that mode too. `hangar_child.MODE_GARAGES` names them on 2.4.1.0:

| Mode | Root view |
| --- | --- |
| `comp7` | `comp7.gui.impl.lobby.hangar.comp7_hangar.Comp7Hangar` |
| `comp7_light` | `comp7_light.gui.impl.lobby.hangar.comp7_light_hangar.Comp7LightHangar` |
| `frontline` | `frontline.gui.impl.lobby.hangar_view.FrontlineHangar` |
| `fun_random` | `fun_random.gui.impl.lobby.hangar.fun_random_hangar.FunRandomHangar` |
| `last_stand` | `last_stand.gui.impl.lobby.hangar_view.HangarView` |

Each of them builds the same `MainMenuPresenter` and `VehicleMenuPresenter` as `RandomHangar`. `FunRandomHangar` inherits `_onLoading`, so `uninstall` deletes the patch there instead of putting a method back.

**A root view builds every child inside its `_onLoading`.** `ViewComponent._onLoading` calls `_initChildren`, which constructs each presenter, and each presenter builds its model. So the client's own sub-view models, such as `MainMenuModel`, are created while the root's `_onLoading` runs. `hangar_child.inside_patched_root()` is true in that time. `directives-helper` uses it for its fallback: the window claims a client sub-view with `view_claim` only in a garage root view that it has no child in, such as the garage of a mode that is new to the mod.

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
- Keep the drag handle between the garage's top bar and bottom bar. Each bar takes every press across its strip, also where it draws nothing. See [The Lobby Bars Take Input Where They Draw Nothing](#the-lobby-bars-take-input-where-they-draw-nothing).
- Do not trust the screen size when the module starts, which is when a widget places itself. On 2.4.1.0 `window.innerWidth` can be 1 at that moment. Take a size smaller than any screen as unknown, and wait for a real size before the first placement.
- Store the viewport size alongside the coordinates, so a later resolution or UI-scale change
  can rescale the position proportionally instead of stranding the widget.

## The Lobby Bars Take Input Where They Draw Nothing

This section comes from client 2.4.0.2. We read these files:

- `gui/flash/lobby.swf`, the legacy lobby page
- `mono/hangar/views/header/header.html/bundle.js` and `mono/hangar/header/header.css`, the top bar
- `mono/hangar/views/footer/footer.html/bundle.js` and `mono/hangar/footer/footer.css`, the bottom bar
- `mono/hangar/chunks/lib.js`, the shared chunk

Then we measured the result in game at 1920×1200 and one pixel per rem. A probe ran inside each bar document, and the documents logged the presses they received. A player report of a `directives-helper` window stuck under the top bar started the work.

The garage's top bar and bottom bar are documents of their own, `mono/hangar/header` and `mono/hangar/footer`, and they sit over `main`. The legacy lobby page holds each of them in a `GFInjectComponent` across the full width. The header sits at the top of the stage, and the footer at the bottom. Each bar sets the size of that surface itself.

Both bars use the shared hook `useSyncSizeTexture`, in mirror image:

- The header's App root calls `useSyncSizeTexture(0, 250)`. The hook resizes the view to the `offsetHeight` of the root plus 250rem below it. Then it removes those 250rem from the hit area with `viewEnv.setHitAreaPaddingsRem`. The battle button's glow draws there and takes no input.
- The footer's `App_footer` element calls `useSyncSizeTexture(250, 0)`. The extra 250rem go above the element, and they leave the hit area in the same way.

Thus each hit area is one element: a strip across the full width of the screen. The measurements agree. The header view was 326 pixels tall, the 76-pixel App root plus 250rem. The footer view was 308 pixels tall at y=892, the 58-pixel `App_footer` element plus 250rem.

Measure the right element in each bar. In the header, it is the outermost element with an `App_` class. In the footer, the outermost `App_` element fills the whole view, the 250rem above the bar included. The sized element is the `App_footer` element inside it.

In the garage neither strip has a background. An earlier client drew a solid bar there, so the player could see the area was in use. The background now comes back only in the old style, `App_base__oldStyle` and `App_footer__oldStyle`, which [a view on band 6](ui-and-scaleform.md#top_sub_view-6-brings-the-legacy-lobby-back-with-it) turns on. Without it each strip looks like part of the garage scene, but it still takes every press. A widget in `main` under a strip does not get the press. No `z-index` changes that, because the documents are separate.

The inner row of a strip belongs to its bar too. With a 76-pixel App root, presses at y=76 and above reached the header document, and presses at y=80 and below reached `main`. So a handle must start at the row under the strip's bottom edge. We did not measure the edge row of the bottom bar. `directives-helper` keeps one row clear there too, and in game its handle stayed easy to grab at that limit.

### The Strip Heights

The top bar's height follows the client's width breakpoints. The breakpoint uses the screen width in rem, from `viewEnv.getClientSizeRem()`, not in pixels:

| Screen width | Top bar height |
| --- | --- |
| under 1600rem | 57rem |
| 1600rem or more (`mediaMediumWidth`) | 59rem |
| 1920rem or more (`mediaLargeWidth`) | 76rem |
| 2560rem or more (`mediaExtraLargeWidth`) | 82rem |

The App root also has 6rem of bottom padding, and the padding is inside these heights. At 1920 pixels wide the root measured 76 pixels, the same as its `height: 76rem`. `getComputedStyle` reports no `box-sizing` in this renderer, so read the height, not the style. For example, 3840 pixels at two pixels per rem is 1920rem wide. There the top bar is 76rem, or 152 pixels.

The bottom bar's stylesheet gives no height. The bar takes its height from its content and its padding. At 1920 pixels wide it measured 58 pixels. Its padding grows by 6rem at 2560rem and wider.

### Reading The Strips Live

A widget in `main` cannot read the bar documents. `directives-helper` therefore puts a probe, `bar_probe.js`, into both of them. It takes none of their own sub-views: it adds a child of its own to `LobbyHeader` and to `LobbyFooter`, as in [Getting code into a document](#getting-code-into-a-document). Python tells each probe the class prefix of the element to measure. The probe adds the view position from `viewEnv.getViewGlobalPositionRem()` to the element's rectangle, and reports the strip in screen pixels with a command. Python passes each report on to the window's model, with the bar it came from. All three documents measured the same pixels per rem.

The reports come late. In the measured run the window placed itself, and the first reports arrived one second after that. Until then a widget has two choices: fixed limits copied from the stylesheets, or the screen edges alone. `directives-helper` uses the screen edges, so it keeps no client numbers to maintain. A window saved under a bar shows there for about a second, and then moves when the report arrives. If no report ever comes, the window loses only the protection from the bars. When a report arrives, move the widget only if it is outside the new limits.

The first placement has a trap of its own. When a module in `main` starts on 2.4.1.0, `window.innerWidth` and `window.innerHeight` can be 1. In the first 2.4.1.0 session, all five garage loads read 1 by 1. In the next session, the one garage load read the real size. A check for a size above 0 takes 1 by 1 as the screen. The 2.4.1.0 `game.log` shows what follows:

```text
[zanju.directiveshelper] placed the window at 0,0 from the stored 1326,187 (stored at 1920x1200, now 1x1), ...
[zanju.directiveshelper] ignoring a top bar report that does not fit the screen: {"bottom": 76.0, ...}
```

The stored position rescales to 0,0. The top bar report looks like it does not fit a screen 1 pixel high. A placement that reads the size at that moment also picks the smallest breakpoint. It skips every clamp that needs the screen size too. So take a width or height under 100 pixels as an unknown size. `directives-helper` keeps the window hidden until the size is real, for at most three seconds. While the size is unknown, it uses the bar reports without the check against the screen height. On 2.4.0.2, `viewEnv.getClientSizePx()` gave the real size at that moment. On 2.4.1.0 nobody measured it, because the `innerWidth` of 1 hid it.

For a draggable widget the result is direct: a drag handle under a strip is lost. Keep the whole handle between the bars, and keep enough of it on screen sideways. Clamp it on every move and when the widget places itself at start. That start clamp frees a widget that a player already dropped there. Measured: a window stored at y=10 came back at y=77, directly under a top bar of 76 pixels. Clamp it again when the limits change: a bar report, a new screen size or interface scale, or a new size of the widget. `directives-helper` keeps the window's narrowest width on screen sideways, so only a wider window can hang off the right edge.

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
| `crucible-tracker` | widget root | 1001 |

The number decides nothing outside this document. Every view is a document of its own, and the band it sits in decides which document draws over which. A Scaleform mod view on `WINDOW` therefore covers everything here, whatever number the roots carry. See [Window Layers](ui-and-scaleform.md#window-layers).

Ordering *within* a root is a separate question from the number above. Sibling widgets paint in document order, so a later sibling covers the tooltip of an earlier one. Lift the whole widget on `:hover` rather than just its tooltip, or the tooltip appears to detach from the thing it describes.

## Sharing the row beside the vehicle name

`campaign-tracker` and `crucible-tracker` hang their banners beside the garage's vehicle name block. When both are installed, their banners must stand in one row, and neither may cover the other. Each mod must also work alone.

**They share the arithmetic, not the elements.** Each mod keeps its own root, its own `z-index` and its own pointer handling. A shared container would put both mods under one root that must not take pointer events, and elements under such a root do not reliably get them. The mods agree only on where each row starts, through a hidden list in the garage document:

```html
<div id="zanju-banner-tray" style="display: none">
  <i data-owner="zanju.campaigntracker" data-rank="10" data-side="right" data-width="212" data-seq="4"></i>
  <i data-owner="zanju.crucibletracker" data-rank="20" data-side="right" data-width="64" data-seq="2"></i>
</div>
```

`mods-common/gameface/tray.js` holds the contract, and the build copies it into each of the two mods. On every layout pass a mod does this:

1. It finds the list, or creates it.
2. It writes its own entry: its `MOD_ID`, its fixed rank, its side, and the measured width of its row. An unchanged entry writes nothing.
3. It works out where its row starts. On each side the lowest rank stands nearest the name, and two equal ranks sort by owner. On the right, a row starts after every nearer row. On the left, a row ends before every nearer row.
4. It places only its own banners, from that start, left to right.

A row that is not on screen removes its entry, so the other row closes the gap. A mod that is alone is the only entry, and its row starts at the vehicle name block.

**The list is a contract between mods, and players mix releases.** A new version can add an attribute. Every version must ignore an attribute that it does not know, and must read a missing side as the right side. The order comes from the rank, never from the load order of the mods.

**Each mod follows the rows of the others with a `MutationObserver`.** Measured on 2.4.1.0: both scripts loaded into `main` side by side, and an attribute change by one reached an observer in the other in 0 to 1 ms. A poll every 100 ms took up to 87 ms. Each mod keeps its own poll as the backstop.

The player picks the side in the settings of each mod. Measured on 2.4.1.0 with probe banners: a banner left of the vehicle name gets its hover like one on the right, and a banner under a root with a higher `z-index` still gets its hover.

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
| `width: max-content`, and by extension `fit-content` | Dropped — the width falls back to `auto`, so a block-level box silently stays as wide as its surface. Measured in `campaign-tracker`: the declaration changed nothing at all. There is therefore no way to size a box from its own content in a document the mod owns, which leaves a stated width as the only option in CSS. A script can measure the width instead: see [Fixed Text Columns](#fixed-text-columns). |
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

**Tint an icon with a mask, never with a coloured copy of the file.** `mask-image` works here. The game's own stylesheets use it 339 times. Ship one white PNG with the shape in its alpha channel. Give the box `background-color` for the colour and `mask-image` for the shape. One file then serves every colour a state needs, and the colour sits in the stylesheet beside the palette rather than baked into an asset.

Copy the client's spelling exactly. It writes `mask-image`, `mask-repeat`, `mask-size`, `mask-position` and `mask-mode: alpha`, all unprefixed. `-webkit-mask-image` appears in none of its stylesheets. `MentorAssignmentDialog.css` in `gui-part1.pkg` is the worked example. `campaign-tracker` tints its banner icons the same way.

Know the failure mode before trying it, because it is loud rather than silent. A mask the renderer will not load leaves the `background-color` filling the whole box. A broken icon therefore appears as a solid rectangle rather than as nothing at all.

**Draw a ring or an arc with gradients.** The client has both parts, in garage documents. The search spinner of its platoon button (`mono/hangar/chunks/widget2.css`) is a ring. It has `background-image: conic-gradient(from 90deg at 50% 50%, #fff 0deg, transparent 360deg)` and `mask: radial-gradient(farthest-side, transparent 2rem, #000 0)`. `ArcProgressbar` of its pet screen (`mono/pet_system/pet_storage/pet_storage.css`) fills an arc. A stop of its `conic-gradient` reads `var(--progressbarMaskPercentage)`, and the script sets that property on the parent element. The client's React wrapper sets a custom property with `style.setProperty`. The dial of `crucible-tracker` combines the two forms with hard stops. A hard stop in a radial mask draws a jagged circle at this size. Thus each edge of the dial's mask has a ramp of 0.5rem. The client's battle stylesheets use `radial-gradient` and `mask-image`, but none uses `conic-gradient`. The form still works there: a battle on 2.4.1.1 showed the ring and its arc in the panel window of the mod.

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

## Fixed Text Columns

A flex item with `flex: 0 0 auto` takes the width of its text. Thus a counter beside a flexible bar moves the bar on each change. The renderer has no `ch` unit and no `max-content`. So state the width of the column in `rem`, from the longest text it can hold. Take the widths from the `hmtx` table of the font. The fonts are in `gui/gameface/fonts/` in the GUI packages. These are the advance widths in em on EU 2.4.1.0:

| Glyph | `PFDINMax-CompressedRegular` | `Warhelios-Regular` |
| --- | --- | --- |
| `0`, `3`, `4`, `5`, `6`, `8`, `9` | 0.380 | 0.480 |
| `2` | 0.363 | 0.480 |
| `7` | 0.322 | 0.480 |
| `1` | 0.310 | 0.480 |
| comma, colon | 0.193 | 0.240 |
| space | 0.195 | 0.240 |
| slash | 0.256 | 0.266 |

The inherited `letter-spacing: 0.02em` adds 0.02 em per glyph in PFDINMax. The languages that use Warhelios have no letter spacing. Warhelios has tabular digits and PFDINMax does not. Thus a text of the same length can change its width in PFDINMax. Right-align the text in the column when the end of the text does not change. Then only the characters that change move. In `crucible-tracker`, `88,888 / 88,888` at 13rem is 67rem in PFDINMax and 78rem in Warhelios, and the column is 80rem.

**Measure a column that must follow the font.** A stated width must hold the widest font, so it wastes space in the other fonts. The dial column of `crucible-tracker` measures instead. A hidden probe holds the widest text of the figures, with `8` for each digit. The probe has `position: absolute`, `visibility: hidden` and `white-space: nowrap`, as the digit probe of `premium-time` does. A `ResizeObserver` on the probe writes the width to a custom property of the panel. The column has `width: var(--zanju-crt-figures-width)`, and `min-width` keeps the width of the ring. Without the full information, the panel has `width: calc(var(--zanju-crt-figures-width) + 18rem)`, which adds the frame. The custom property stays on the panel through a new render, so the panel has no flash of another width. The client's battle stylesheets have `width: calc(var(--card-width) - 4rem)`, but no `var()` in `flex`. Thus put the property in `width`. A battle on 2.4.1.1 showed the form without the full information in PFDINMax. With a required value of 2,500, the panel was 75rem wide, the width that the table above gives.

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

**Mirroring the rule is not enough, because a standalone document has no `lang`.** The client's markup says `<html lang="en">`. Its startup code then calls `document.documentElement.setAttribute("lang", resources.resolve("langCode"))`, where `langCode` is `R.strings.settings.LANGUAGE_CODE()`. A document that the mod owns does not run that code, so no `html[lang=...]` rule matches, and PFDINMax stays in use. PFDINMax has no CJK glyphs. On the Chinese client, the `campaign-tracker` card thus showed only digits and Latin letters ([issue #31](https://github.com/przemyslaw-zan/zanju-wot-mods/issues/31)).

Set the attribute yourself before the first render. `helpers.getClientLanguage()` in Python reads the same `#settings:LANGUAGE_CODE` string. `campaign-tracker` sends it in the card payload, and `applyLanguage` in `card_panel.js` sets it. An injected widget does not need this, because it lives in a client document that already carries `lang`.

**The client's region, not the family name, decides which glyphs you get.** Gameface draws only with the fonts that `res/gui/flash/fontconfig.xml` lists, never with the fonts of the operating system. The engine reads the `gameface` section of this file in `gf_fonts.cpp`. Each `fontfamily` maps a `name` to one `path` per `style` and `weight`, and `deffontfamily` names the default family. The engine also knows `fontfamilyfallback`, `hieroglyphical` and `sdfsize`, but the EU file uses none of them. The file is loose, not in a package, and it is packed BigWorld XML.

On EU 2.4.0.1, `Warhelios` maps to `Warhelios-Regular.ttf` and `Warhelios-Bold.ttf`, which have no CJK glyphs. But the GUI packages in every region ship `WarheliosZHCN`, `WarheliosZHTW`, `WarheliosJA` and `WarheliosKO`, each a separate family by its internal name. The Chinese client thus maps `Warhelios` to CJK glyphs, probably to the `WarheliosZHCN` files. Nobody read its `fontconfig.xml`, but the client showed the result. The garage banner in issue #31 drew "先锋-2" through the `html[lang=zh_cn]` rule. On 1 October 2026, the reporter also confirmed the `campaign-tracker` 1.2.1 card on that client, with Chinese text in every line from the client. As a result, a client in another language cannot show CJK text, even with `lang` set correctly.

To test CJK text on a client in another language, do these steps. The procedure worked on EU 2.4.0.1 on 30 September 2026: the card drew Chinese in both the title weight and the body weight.

1. Decode `res/gui/flash/fontconfig.xml` into plain XML. Keep the Scaleform `config` section, because the same file supplies it.
2. In the `Warhelios` family, change the `normal` path to `gui/gameface/fonts/WarheliosZHCN-Medium.ttf` and the `bold` path to `gui/gameface/fonts/WarheliosZHCN-Bold.ttf`.
3. Save the result as `res_mods/<client version>/gui/flash/fontconfig.xml`.
4. Make the document set `lang` to `zh_cn`, and give it some Chinese text to draw.
5. After the test, delete the override. It changes `Warhelios` across the whole client.

Copy the values rather than linking the game's stylesheet: linking pins the mod to a resource path, and that file also sets `width` and `height` to `100%`, which fights the sizing a standalone panel needs. Re-check them after a client update — the word gap in "Text wraps by flex line" above is measured against PFDINMax at this letter spacing.

**The game's `body` is rarely the whole inherited environment.** What a moved subtree inherited came from every ancestor it had, and the nearest one setting a property wins. A widget wrapping the subtree typically sets `color`, `font-size` and `line-height` of its own, so those come from the widget and only the untouched ones — family, weight, letter spacing — come from the game. Reproducing the game's `body` alone gets the second group right and silently restyles the first: in this repo it turned every unstyled line in a tooltip from a cool grey to the game's warm cream, which reads as correct until it is put beside the original.

Walk the old ancestor chain before writing the new base, and take each inheritable property from the nearest ancestor that set it.

**Sizing needs the same care, in two places.**

The *width* is the first. A block-level flex container is as wide as the space it is given, so measuring one reports the width of whatever native surface the view started with rather than the width of the content. State the width instead. Taking the root out of the flow to shrink-wrap it looks like the other answer and is a worse one: the document then has no height, the engine never finishes sizing the view, and it logs `Size calculation timeout. Set the default view size.` before falling back to a size of its own.

The *moment of measurement* is the second, and it fails intermittently, which makes it hard to read. `getBoundingClientRect()` called in the same frame that built the DOM reports the layout as it stood **before** the new content. The height comes back short, `resizeViewPx` hands the native surface that short height, and whatever sits at the bottom of the panel falls outside it and is clipped. It reads as random because the error is the difference between the old layout and the new one, so it depends on what was rendered previously.

Wait two animation frames after every render, not only after the first one, then measure. Measure once more a frame later and republish only if the number changed — that costs one comparison and catches a late settle such as a font arriving between the two passes.

**A `ResizeObserver` catches what the wait misses.** Two frames are not always enough for the first layout of a new window. On 25 October 2026 the Crucible battle panel opened in its short form and measured 300 by 22: its padding, with its one row still at zero height. The layout was right a moment later, but nothing measured it again until the next payload, so the row stayed cut. The client's own views that follow their content attach a `ResizeObserver` to their root, and resize the view from its callback, which runs after each layout that changes the size. Gameface has it natively. `crucible-tracker` does the same in `battle_panel.js`, and the panel opened at its full size from then on. `card_host.js` still waits for frames, and no hover card has shown the fault yet.

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

A mod document's `console.error` reaches `game.log`, one line per call:

```
[2026-09-02 11:49:04.975] [ERROR] [Main] [UI] [Gameface] [zanju.campaigntracker] widgets.js loaded
```

Checked at client **2.4.0.0**, with 448 such lines from one session.

**The `net.openwg.console` flag is no longer the gate.** Earlier clients forwarded `console.error` to `python.log` only while that mod was on, and it ships off. The lines above arrived with `mods/configs/net.openwg.wot.common/console.json` untouched, still reading `{"enabled": false}`. Every Gameface engine warning carries the same `[UI]` tag, so the host writes these rather than a Python forwarder. The flag still binds the in-game console overlay to its shortcut. Set it if you want the overlay.

`console.log` is a separate question, and it is **untested here**. Every document in this repository writes with `console.error`, which is what OpenWG's own `debug.js` does. Nothing in these logs shows whether `console.log` now arrives. Keep to `console.error` until somebody checks.

Before 2.4 this cost a whole session. Diagnostics were written, the client was run, and the log came back empty. The flag was off, and nothing warned about it. That trap is gone. The narrower lesson survives it: when a `console.error` you are certain runs produces no line, suspect the plumbing before the code.
