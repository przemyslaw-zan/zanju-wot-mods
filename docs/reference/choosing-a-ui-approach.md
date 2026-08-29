# Choosing A UI Approach

Three routes put a mod's information on the screen, and this repository uses all three. The choice is not old against new. It follows from one question: who owns the surface the pixels come from.

- **Python only.** Change what the client already draws. No new UI of your own.
- **Gameface widget.** HTML, CSS, and JavaScript inside a document the client owns.
- **Scaleform view.** A compiled SWF that the client loads as a view of its own.

Scaleform is the older engine and Gameface is the current one. For a mod, that is not the useful difference. A Gameface widget looks native and costs no drawing code, and it rides in a document the client owns. A Scaleform view needs no other mod installed, and it holds a band of its own. [Window Layers](ui-and-scaleform.md#window-layers) says what a band decides.

## Side by side

| | Python only | Gameface widget | Scaleform view |
| --- | --- | --- | --- |
| Used by | `salvo-reticle-fix` | `campaign-tracker`, `directives-helper`, `premium-time` | `research-progress-bar` |
| Needs another mod | no | yes, `net.openwg.gameface` | no |
| Build step | none | none, the files ship as they are | `mxmlc` on an API mirror, run by `zwm build` through `ui/compile_ui.py` |
| Draws in | wherever the client draws it | the band of the host document, 5 for the garage | a band of its own, 7 or above |
| Layout | the client's | flex, in a CSS subset with holes in it | by hand, in ActionScript |
| Fonts and scale | the client's | the client's, through `rem` | embedded fonts, and the stage scale read by hand |
| Input | the client's | `pointer-events`, and the garage still needs its drag | `mouseEnabled` and `mouseChildren`, per object |
| Data from Python | direct, all of it is Python | view model properties and commands | DAAPI calls out, one declared slot back |
| Two mods at once | no conflict | one mod per sub-view, the first free one wins | one alias per view |
| Unit tests | Python | Python, plus `node --test` against the shipped module | Python only, and none for the ActionScript |
| Debug output | `python.log` | `console.error` reaches `python.log`, `console.log` does not | a round trip through Python |
| Breaks when | the patched client code changes | the host document or its sub-views change | the API mirror or the view settings go stale |

The settings menu is a separate question from all of this. Any route can register with the ModsSettings API, which is a companion artifact rather than a UI decision. See [In-Game Settings](in-game-settings.md).

## Decide by what you need

1. The client already draws the thing, and you want it to say something else. Patch it in Python.
2. It has to sit among the garage panels and read as part of them. Write a Gameface widget.
3. It has to draw over the garage document, or over another mod's widget. Write a Scaleform view.
4. It has to draw over a native window, such as the platoon window. Only a Scaleform view can reach those bands, and no HTML route reaches them at a price worth paying.

## Mixing two routes

Nothing stops a mod from taking two routes at once. Python is the bus between them: both surfaces read the same module, and neither one needs to know the other exists. The question is not whether it works. The question is where the seam runs.

**A seam between whole surfaces is cheap.** Each half stands on its own and the two share data only. A Scaleform bar plus a Gameface settings window is a clean split, because nothing has to line up between them. Pick this seam whenever the two halves answer different questions.

**A seam through one interaction is expensive.** A hover that starts in HTML and draws in ActionScript has to carry the pointer across Python on every move. The two engines also disagree about units: Gameface scales through `rem`, and Scaleform scales the whole stage instead of resizing it. So the position needs a conversion at each end, and the tooltip lags the widget it belongs to. Split by feature, not by element.

**The cheap version of the same idea keeps one engine.** Two Scaleform views, one for the bar on band 7 and one for its tooltip on a high band, share a coordinate space and a content renderer. This is the plan for `research-progress-bar`, whose tooltip is already ActionScript.

`campaign-tracker` shows the other side. Its card is HTML, its banners anchor to a Gameface element that a SWF cannot measure, and only a view above band 7 draws over a native window. Every option there is a bad one: a cross-engine seam through the hover, a rewrite of the card in ActionScript, or a whole widget that gives up its anchor. Hiding the card while a window covers it costs the least and keeps the mod on one route.

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

### Scaleform view

The view holds a band of its own, which is the only reason to choose it. It needs no other mod, and it draws above the garage document and above every widget inside it.

Everything else is work. There is no CSS and no flex, so layout is arithmetic in ActionScript. The view has to embed its own fonts. The interface scale reaches the view as a stage scale rather than a size. A view that reads `stage.stageWidth` therefore lays itself out at double width at x2.

The ActionScript also has no test runner: `zwm test` covers Python and Node only. One garage bar takes 17 `.as` files. See [UI And Scaleform](ui-and-scaleform.md) for the mechanics and [Research Progress Bar UI](research-progress-bar-ui.md) for how one is put together.

## The route to avoid

A mod can shadow a client file, because a mod's `res/` overrides the same path inside the game packages. This reaches places nothing else does, such as the document root of the tooltips document. It also means a verbatim copy of a game file, which every client update forces you to re-diff. `premium-time` did this for one tooltip line and removed it: client 2.3.1.0 swapped a stylesheet in that shell, and the stale copy would have left unrelated hangar tooltips unstyled. See [Cost of the tooltip integration](wot-plus-subscriptions.md#cost-of-the-tooltip-integration).
