# Choosing A UI Approach

Four routes put a mod's information on the screen, and this repository uses three of them. The choice is not old against new. It follows from one question: who owns the surface the pixels come from.

- **Python only.** Change what the client already draws. No new UI of your own.
- **Gameface widget (injected).** HTML, CSS, and JavaScript inside a document the client owns.
- **Gameface panel (standalone).** The same web stack, in a document and a window the *mod* owns.
- **Scaleform view.** A compiled SWF that the client loads as a view of its own.

Scaleform is the older engine and Gameface is the current one. For a mod, that is not the useful difference. What separates the routes is who owns the window, because the window decides the band, and [Window Layers](ui-and-scaleform.md#window-layers) says what a band decides. An injected widget inherits the host document's band. A standalone panel and a Scaleform view each hold a band of their own.

## Side by side

| | Python only | Gameface widget (injected) | Gameface panel (standalone) | Scaleform view |
| --- | --- | --- | --- | --- |
| Used by | `salvo-reticle-fix` | `campaign-tracker`, `directives-helper`, `premium-time` | `campaign-tracker`, for its banner tooltip | `research-progress-bar`, one view for the bar and one for its tooltip |
| Needs another mod | no | yes, `net.openwg.gameface` | yes, `net.openwg.gameface`, for the resource map only | no |
| Build step | none | none, the files ship as they are | none, plus one `res_map` entry | `mxmlc` on an API mirror, run by `zwm build` through `ui/compile_ui.py` |
| Draws in | wherever the client draws it | the band of the host document, 5 for the garage | a band of its own, chosen per window | a band of its own, 7 or above |
| Against native windows | n/a | always behind them | band 7 shares with them and activation decides; band 10 stays on top | the same |
| Escape key | n/a | the host document's | cascades past the panel to the lobby menu; handle it yourself to close the panel | the same |
| Layout | the client's | flex, in a CSS subset with holes in it | the same CSS subset | by hand, in ActionScript |
| Fonts and scale | the client's | the client's, through `rem` | the client's, through `rem` and `viewEnv.getScale()` | embedded fonts, and the stage scale read by hand |
| Input | the client's | `pointer-events`, and the garage still needs its drag | the native surface is the hit area, so size it exactly | `mouseEnabled` and `mouseChildren`, per object |
| Data from Python | direct, all of it is Python | view model properties and commands | the same, on a model the mod defines | DAAPI calls out, one declared slot back |
| Two mods at once | no conflict | one mod per sub-view, the first free one wins | no conflict, each window is separate | one alias per view |
| Unit tests | Python | Python, plus `node --test` against the shipped module | the same | Python only, and none for the ActionScript |
| Debug output | `python.log` | `console.error` reaches `python.log` and `console.log` does not, but only once `net.openwg.console` is enabled | the same | a round trip through Python |
| Breaks when | the patched client code changes | the host document or its sub-views change | the Wulf view or window contract changes | the API mirror or the view settings go stale |
| Costs a restart | no | no | yes, once, when the `res_map` entry changes | no |

The settings menu is a separate question from all of this. Any route can register with the ModsSettings API, which is a companion artifact rather than a UI decision. See [In-Game Settings](in-game-settings.md).

## Decide by what you need

1. The client already draws the thing, and you want it to say something else. Patch it in Python.
2. It has to sit among the garage panels and read as part of them. Inject a Gameface widget.
3. It has to draw over the garage document, over a native window, or over another mod's widget. Take a band of your own: a standalone Gameface panel if you want the web stack, a Scaleform view if the mod must not depend on `net.openwg.gameface`.
4. It has to anchor to an element the client draws. Only an injected widget can measure that element. A standalone panel or a Scaleform view has to be told where the anchor is.
5. It has to draw *under* the garage document, to sit beneath another mod's widget. Only `MARKER` (3) is open, and it composites with the 3D scene, so a view there comes out dim. Every other band below 7 belongs to the client. See [Window Layers](ui-and-scaleform.md#window-layers).

## Mixing two routes

Nothing stops a mod from taking two routes at once. Python is the bus between them: both surfaces read the same module, and neither one needs to know the other exists. The question is not whether it works. The question is where the seam runs.

**A seam between whole surfaces is cheap.** Each half stands on its own and the two share data only. A Scaleform bar plus a Gameface settings window is a clean split, because nothing has to line up between them. Pick this seam whenever the two halves answer different questions.

**A seam through one interaction is expensive.** A hover that starts in HTML and draws in ActionScript has to carry the pointer across Python on every move. The two engines also disagree about units: Gameface scales through `rem`, and Scaleform scales the whole stage instead of resizing it. So the position needs a conversion at each end, and the tooltip lags the widget it belongs to. Split by feature, not by element.

**The cheap version of the same idea keeps one engine.** Two Scaleform views, one for the bar on band 7 and one for its tooltip on a high band, share a coordinate space and a content renderer. This is what `research-progress-bar` does. The bar is one view on band 7, and its tooltip is a second view on band 10. Both compile from the same ActionScript.

`campaign-tracker` shows the other side. Its tooltip is HTML, its banners anchor to a Gameface element that a SWF cannot measure, and only a view above band 7 draws over a native window. The options used to be three bad ones: a cross-engine seam through the hover, a rewrite of the tooltip in ActionScript, or a whole widget that gives up its anchor. Hiding the tooltip while a window covered it cost the least. That is what shipped, until the fourth option below.

**A standalone Gameface panel is a fourth option, and it is the cheapest seam of the four.** Keep the banners injected, so they still measure their anchor, and move only the tooltip into a standalone window on its own band. The tooltip's position still has to cross Python, so the seam does not disappear. What disappears is the reason the seam was expensive: both halves are the same renderer, both scale through `rem`, and the tooltip's markup and CSS move over unchanged. The Scaleform version of this needed a unit conversion at each end because the two engines disagree about scale. This one does not.

**Shipped, on band 10.** A throwaway probe mod first built the panel on `WindowLayer.TOP_WINDOW` (10). It stayed over the platoon window at all times, and a click could no longer raise the native window past it. Band 7 does not do this — it is shared with the platoon window and ordered by activation. `campaign-tracker` 1.1.0 ships the route on that band.

Band 10 is not a free win. It is also where `lobbyMenu`, `settingsWindow` and the client's dialogs sit, so a panel there ties with them on activation. Going higher is worse: the upstream guide reports that band 11, above the menu, prevents the second Escape press from closing it. Both mods here settled on band 10. A tooltip that is gone in a second pays little for the tie. A panel that stays up all session should weigh it again. See [Window Layers](ui-and-scaleform.md#window-layers).

The seam costs about 2 ms. Measured on the probe: Python published a model update and the panel's JavaScript reported receiving it two milliseconds later, three times running. A tooltip that follows the pointer through Python is therefore viable, which was the open question.

### Which of our mods this actually helps

The route is proven, which is not the same as a reason to use it. Weigh it per mod.

- **`campaign-tracker`** — the case that took it, in 1.1.0. Its tooltip is the exact shape the route suits. It appears for a moment, it must cover a native window, and it is already HTML. Band 10 covering system messages costs nothing for a tooltip that is gone in a second.
- **`directives-helper`** — a weaker case, and probably a no. Moving it standalone would drop the OpenWG sub-view collision handling and the `pointer-events` work, which is real value. But it is a panel that stands there for the whole garage session, so band 10 would cover system messages all that time, and band 7 loses to activation. The injected version already hides itself off the garage route and works.
- **`premium-time`** — no case. It rewrites labels inside the header document, so it has to be in that document.
- **`research-progress-bar`** — no case. Its tooltip did have to clear a native window. A second Scaleform view answered that, without leaving the engine the tooltip was already written in. Reach for this route only when the panel is HTML already.

There is a third thing to mix with. The client draws its own tooltips on band 14, and `viewEnv.handleViewEvent` opens one from a Gameface widget. That is the cheapest way above a native window, as long as the content fits a native tooltip template. See [Gameface Mod Widgets](gameface-mod-widgets.md) and the cost recorded in [WoT Plus Subscriptions](wot-plus-subscriptions.md#cost-of-the-tooltip-integration).

## What each route costs

### Python only

The cheapest route, and the most native, because the client keeps drawing its own UI. `salvo-reticle-fix` changes one value the client already uses for the reticle. A classic blocks tooltip takes an extra block the same way, by a wrapped `_packBlocks`. See [Appending To A Classic Blocks Tooltip](ui-and-scaleform.md#appending-to-a-classic-blocks-tooltip).

The limit is hard: this route says nothing the client has no place for. It also holds you to the client's own wording and layout, which is usually the point.

### Gameface widget

The widget looks like the garage without any styling work, and it follows the interface scale through `rem`. The JavaScript is a real ES module, so `node --test` runs the same file the client loads. All three Gameface mods here carry such tests.

Three costs come with it. The renderer implements a subset of CSS, and the holes are not obvious. There is no usable inline layout, and the renderer ignores several text properties outright. The garage listens for drag-to-rotate on the whole scene, so every widget has to hand input back.

The third cost is the band. It belongs to the host document, so a native window covers the widget whatever `z-index` it carries. [Gameface Mod Widgets](gameface-mod-widgets.md) holds the list and the evidence for each entry.

One more cost is easy to miss. The route needs `net.openwg.gameface` installed, so the mod carries a dependency the player can remove.

### Gameface panel (standalone)

The mod builds its own view model, its own `ViewImpl`, and its own `WindowImpl`, then parents that window to the lobby's main window on whatever band it names. The web stack, the CSS subset, the `rem` scaling and the testing story are all the same as the injected route. Four things differ.

It **holds a band of its own**, which is the whole point. It is not sealed inside the garage document, so a native window no longer covers it by construction.

It **needs an entry in the Gameface resource map**, because the document is one the client has never registered. The entry ships inside the `.wotmod` at `res/mods/configs/res_map/<mod>.json`, and OpenWG merges it. Changing that entry restarts the client once. The dependency on `net.openwg.gameface` therefore stays, but narrows to the resource map.

It **owns its own hit area**. The native surface is what the client hit-tests, so the panel must publish its real size through `resizeViewPx` and Python must expect the same number. Get that right and the `pointer-events: none` root and its single hot child are no longer needed. Measured on 2.3.1.3, the result is the *native* interaction: drag-to-rotate started outside the panel keeps working, pauses while the pointer crosses the panel, and resumes past it, exactly as it does over the platoon window. Get the size wrong and the mod pauses rotation over a rectangle the player cannot see.

It **has no generated setters**. A hand-written view model registers storage with `_addStringProperty`, but `model.setPayload(...)` raises `AttributeError` until the matching setter is written by hand against the same property index.

The upstream guide covers the mechanics in full: [gameface-standalone](https://modding.wot-tools.dev/gameface-standalone.html) and [gameface-layout-input](https://modding.wot-tools.dev/gameface-layout-input.html). See [The Upstream Modding Guide](upstream-guide.md).

### Scaleform view

The view holds a band of its own, and it needs no other mod installed. That second point is now the only thing separating it from a standalone Gameface panel, which reaches the same bands but carries the `net.openwg.gameface` dependency. It draws above the garage document and above every widget inside it.

Everything else is work. There is no CSS and no flex, so layout is arithmetic in ActionScript. The view has to embed its own fonts. The interface scale reaches the view as a stage scale rather than a size. A view that reads `stage.stageWidth` therefore lays itself out at double width at x2.

The ActionScript also has no test runner: `zwm test` covers Python and Node only. One garage bar takes 17 `.as` files. See [UI And Scaleform](ui-and-scaleform.md) for the mechanics and [Research Progress Bar UI](research-progress-bar-ui.md) for how one is put together.

## The route to avoid

A mod can shadow a client file, because a mod's `res/` overrides the same path inside the game packages. This reaches places nothing else does, such as the document root of the tooltips document. It also means a verbatim copy of a game file, which every client update forces you to re-diff. `premium-time` did this for one tooltip line and removed it: client 2.3.1.0 swapped a stylesheet in that shell, and the stale copy would have left unrelated hangar tooltips unstyled. See [Cost of the tooltip integration](wot-plus-subscriptions.md#cost-of-the-tooltip-integration).
