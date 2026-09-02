# UI And Scaleform

This page covers the Scaleform route and the layer model both routes share. [Choosing A UI Approach](choosing-a-ui-approach.md) compares it against the other two.

## Preferred UI Pattern In This Repo

For custom lobby UI, the stable pattern is:

- compile ActionScript externally
- register the SWF through WoT view settings
- use a WoT-compatible root such as `net.wg.infrastructure.base.AbstractView`
- let WoT own the display tree attachment

A plain `Sprite` root is not enough for this load path.

## Build Hook

If a mod has `ui/compile_ui.py`, `zwm build` runs it automatically before packaging.
Generated SWF output belongs in ignored build folders under `ui/build/`.

## Window Layers

Every view the client shows, Scaleform or Gameface, sits in a numbered band. The band alone decides what draws over what. A view is its own document, so a CSS `z-index` inside one view never lifts anything over another view. `WindowLayer` in `frameworks.wulf.gui_constants` holds the bands. The values below come from the client itself, and the third column names what this repository saw in each band.

| Band | Value | Seen there |
| --- | --- | --- |
| `UNDEFINED` | 0 | |
| `ROOT` | 1 | |
| `HIDDEN_SERVICE_LAYOUT` | 2 | |
| `MARKER` | 3 | `lobbyVehicleMarkerView` |
| `VIEW` | 4 | `lobby`, `login` — the main view of the client |
| `SUB_VIEW` | 5 | `hangar` — the Gameface garage document, and every mod injected into it |
| `TOP_SUB_VIEW` | 6 | screens the client draws over the garage — belongs to the legacy lobby, see below |
| `WINDOW` | 7 | native windows, and every third-party mod view in one log: `GUIFlash`, `xfw_injector`, `ModsListButton`, `TomatoGGLobbyUI`, `ExpectedVehicleValueGarage` |
| `FULLSCREEN_WINDOW` | 8 | |
| `SYSTEM_MESSAGE` | 9 | |
| `TOP_WINDOW` | 10 | |
| `OVERLAY` | 11 | |
| `IME` | 12 | |
| `SERVICE_LAYOUT` | 13 | |
| `TOOLTIP` | 14 | |
| `CURSOR` | 15 | |
| `WAITING` | 16 | `waiting` |

To read the table from your own client, take one file out of the scripts package. Load it with the interpreter the client uses:

```bash
unzip -j res/packages/scripts.pkg scripts/client/frameworks/wulf/gui_constants.pyc
python2.7 -c "import marshal; f=open('gui_constants.pyc','rb'); f.read(8); c=marshal.load(f); print [(x.co_names, x.co_consts) for x in c.co_consts if getattr(x,'co_name','')=='WindowLayer']"
```

**A mod view belongs on `WINDOW` or above.** `VIEW` and `SUB_VIEW` belong to the client. A mod view on `VIEW` takes the place of the lobby view. That lobby view owns the container the garage document needs, so the garage container never appears and the client shows an empty garage:

```
Loading of view WulfPackageLayoutAdapter (key = ViewKey[alias=hangar, ...], layer=5 ...) is requested but the container 5 is still not exist!
GFxLayerItem name= mono/hangar/main creation on layer= 5 has failed. The layer was not found.
SFChildInjector: adding view wrapper to container 5 is failed.
```

**Within one band, order follows activation.** A band decides which *group* draws over which. It does not order the windows inside it, and clicking re-orders them. Measured on 2.3.1.3 with a mod-owned window on `WINDOW` beside the native platoon window, which is also on `WINDOW`:

| Action | Result |
| --- | --- |
| the mod window is the active one | it covers the platoon window |
| click the platoon window | the platoon window covers the mod window |
| click the mod window again | the mod window is on top again |

So band 7 puts a mod view **among** the native windows, not above them. That is fine for a panel the player interacts with, and wrong for anything that must stay visible over a native window without being clicked — a tooltip, a passive readout, a warning.

**`TOP_WINDOW` (10) clears the platoon window, but it is not empty.** Measured with the same panel moved to band 10: it drew over the platoon window at all times, and clicking the platoon window no longer raised it. Activation stopped deciding, because the two are no longer in the same band.

Band 10 is where the client's own menus live, though. From one session's log:

| Band | Native occupants seen |
| --- | --- |
| 7 `WINDOW` | the platoon window, and third-party mod views |
| 9 `SYSTEM_MESSAGE` | the client's system messages |
| 10 `TOP_WINDOW` | `lobbyMenu`, `ingameMenu`, `settingsWindow`, `simpleDialog`, `QuitGameDialogWindow` |
| 11 `OVERLAY` | `AslainMenuWindow`, a third-party mod |

So a panel on band 10 ties with the Escape menu and the settings window on activation, and a panel on band 11 sits *above* them. We have not tested band 11. The upstream guide's [gameface-standalone](https://modding.wot-tools.dev/gameface-standalone.html) page reports that a passive garage panel there prevents a second Escape press from closing the menu, and that `show(False)` does not fix it because focus and stacking are different problems. Nothing we measured contradicts that.

**Choose the band by what has to be cleared, not by height.** Band 7 suits a persistent panel that must not interfere with native menus. Band 10 clears the platoon window at the cost of tying with the menus. Band 11 clears everything and breaks Escape. Band 10 stays below `TOOLTIP` (14) and `CURSOR` (15) either way, so native tooltips and the cursor still draw over it.

The same session showed a second mod on band 7, `SFWindow(alias=ExpectedVehicleValueGarage)`, so several mods and the client already share it.

**A mod window on band 7 behaves like a native window in every other respect too.** Measured with a mod-owned Gameface window beside the platoon window on 2.3.1.3:

| Behaviour | Native platoon window | Mod window on band 7 |
| --- | --- | --- |
| Drag to rotate, started outside the window | rotates | rotates |
| Pointer crosses the window mid-drag | rotation pauses, cursor becomes the plain pointer | the same |
| Pointer leaves the window, button still held | rotation resumes | the same |
| Escape while the window has focus | disbands the platoon, the window's own handling | falls through to the lobby, which opens the game menu |

Two things follow. The drag behaviour is the *native* one rather than a bug: the window occupies its rectangle exactly as a native window does, so a standalone panel needs none of the `pointer-events` work an injected widget needs. And a mod window has **no Escape handling of its own** — the key cascades past it to the global lobby handler, so Escape neither closes the panel nor reaches the window underneath. A panel that should close on Escape has to handle the key itself.

Three things follow for stacking against other mods. A mod SWF on `WINDOW` draws above the whole garage document. It therefore covers every Gameface mod widget, and every tooltip those widgets open, whatever `z-index` they carry.

**A mod can go below the garage document.** This page previously said no band under it was open, and that a Scaleform mod view therefore could not sit beneath a Gameface one. That is wrong. `VIEW` (4) is the lobby's own and taking it breaks the garage, as above — but `MARKER` (3) is below the garage document, is not the lobby, and the client uses it for both kinds of view:

```
SFWindow(layer=3,   alias=lobbyVehicleMarkerView)     Scaleform
WindowImpl(layer=3, content=PetHouseMarkerView)       Gameface, in a plain WindowImpl
```

So a mod view on band 3 draws under the garage document, and under anything a mod injected into it — which is the only way to sit beneath another mod's tooltip when that tooltip is drawn inside a garage document.

Measured with `research-progress-bar` moved there on 2.3.1.3: **the ordering works exactly as the band numbers say.** The bar and its tooltip both went under the garage document, including under another mod's counter injected into `mono/hangar/header`.

**It comes out dimmed, and the band is what dims it.** The whole view is darker at band 3 than the same view at band 7. Sampled pixels show what is happening. The bar's own green, `#789E4E` in the source art, reads back as `#5A773D`. A marker's green, `#9CCB68`, reads back as `#5A773D` as well.

Two different source colours cannot land on one result through a scrim drawn over the band. A scrim of colour `C` and opacity `o` gives `(1 - o) * source + o * C`, so equal results from unequal sources force `o = 1`, and an opaque scrim would hide the view entirely. The two samples must therefore have been blended with different things behind them, which is the signature of compositing against the scene rather than over the finished image. That fits the band's purpose, since its other tenants are world markers.

**No colour transform can undo it.** Reversing a blend against an unknown, position-dependent background needs a correction per pixel, and a view has one colour transform for the whole of it. There is also nothing to correct at the view's end: a display-tree dump at band 3 reported `concatenated: mult=1,1,1,1 offset=0,0,0,0`, so the view already draws at full strength and the loss happens after it.

### `TOP_SUB_VIEW` (6) Brings The Legacy Lobby Back With It

Band 6 sits above the garage document and below `WINDOW`, which makes it look like the band that gets a mod view under other mods without the dimming. It is not, and the reason is worth knowing before spending a run on it.

A view there is not dimmed. It is also not alone: band 6 is where the legacy Scaleform lobby put its sub-views, and it still owns the band. A view placed there goes into the old `LobbyPage` sub-view container. The legacy page then calls `setRequiresOldStyle` back into Python — it is a plain DAAPI method on `LobbyPageMeta`, so the SWF is the caller — and `LobbyView` raises `LOBBY_HEADER_OVERLAPPING` and `LOBBY_FOOTER_OVERLAPPING` in response. Two things follow, both visible in an ordinary garage:

- The lobby header gains a background. In the garage the header normally draws straight over the 3D scene; under the legacy layout it gets the solid bar the legacy screens were built against.
- The view is pushed down the screen. The container insets its contents below that header, and everything inside moves with it.

Neither is a defect to work around. The client is reacting correctly to what looks to it like a legacy screen, and the flag it sets is the same one the crew and customization screens depend on, so overriding it trades a z-order preference for a risk to screens that matter.

**The practical result: there is no band below `WINDOW` (7) that a Scaleform mod view can use.** `MARKER` (3) works but composites with the scene, `VIEW` (4) breaks the garage, `SUB_VIEW` (5) is the garage document, and `TOP_SUB_VIEW` (6) drags the legacy chrome in. A Gameface view might do better on band 6, since the old-style flag is what triggers the chrome and a Wulf view does not carry it, but that is untested here.

Splitting the view is usually the better answer anyway. The part that needs to be over other windows can be a second view on a high band while the rest stays on `WINDOW` — see `research-progress-bar`, whose bar is on 7 and whose tooltip is on `TOP_WINDOW` (10).

Two consequences worth carrying:

- Going below the garage document means going below its *rendering*, not only below its widgets. Budget for the view looking different there, not merely lower.
- Whether a view on band 3 still receives the clicks the document above declined is a separate question, and the one to settle before relying on it. Input passthrough is known to work *within* the garage document at the DOM level, which is a different mechanism.

A band also applies to a whole view and not to an element inside it. A tooltip drawn inside a view stays in the band of that view, so a bar on `WINDOW` plus a tooltip over the platoon window needs two views.

`research-progress-bar` names its band in one place, the `ViewSettings` call in `scaleform/hooks.py`. To try another band, change that constant and rebuild. No mod in the log above sits higher than band 7, but a mod view is not held there: a mod-owned window on `TOP_WINDOW` (10) was measured working in the garage, as below. `OVERLAY` (11) sits above the native lobby menu on band 10. We did not test it; the upstream guide reports that a panel there prevents the second Escape press from closing the menu.

A band is not only a Scaleform question. A mod that builds its own Wulf window gets to name a band whatever renders inside it, so a **standalone Gameface panel reaches these bands too**. The rule that a mod view belongs on `WINDOW` or above applies to it unchanged. See [Choosing A UI Approach](choosing-a-ui-approach.md).

## Window Lifetime And Focus

**A destroyed Wulf window leaves its Python object behind.** The client destroys a mod's window along with the lobby main window it was parented to, but the Python wrapper survives and keeps answering attribute access. It raises only when a call reaches through to `proxy`, which is `None` by then:

```
File "frameworks/wulf/windows_system/window.py", line 479, in show
AttributeError: 'NoneType' object has no attribute 'show'
```

So a stored reference is not evidence that a window exists. Code that guards on `if self._window is not None` builds once, survives the first lobby rebuild in name only, and then fails on every use for the rest of the session. Test liveness instead — `proxy is not None`, and a `windowStatus` that is not `DESTROYING` or `DESTROYED` — and rebuild when it answers no.

Rebuild against the **current** main window each time, resolved from the windows manager rather than remembered. That is the same rule the lobby state machine needs, for the same reason: both belong to the lobby app, so both are different objects after a teardown. See `route_gate.py` in `directives-helper`.


A hidden window is still in the client's active window stack, and it can still interfere with
native behaviour from there. Hiding the SWF is not enough when that happens: dispose the view and
recreate it on return to the safe context. Otherwise keep the window persistent across ordinary
hide and show, which is cheaper and stable.

The general rule that a view instance must never be permanent module state is upstream, in
[gui-frameworks](https://modding.wot-tools.dev/gui-frameworks.html).

For deciding *when* a garage overlay belongs on screen, read the lobby's visible route rather than
a container alias. See `route_gate.py` in `directives-helper` and the route table in
[Directives And Battle Boosters](directives-and-battle-boosters.md#when-the-window-shows).

## Appending To A Classic Blocks Tooltip

Some lobby tooltips are still built in Python as *blocks* rather than rendered by Gameface,
which makes them far easier to extend than their Gameface counterparts: wrap the data class's
`_packBlocks`, call the original, and append.

The header's Premium Account tooltip is one of these — `AmmunitionEmptyBlockTooltipData`,
selected by the `#tooltips:header/premium_buy` alias. A single data class backs several
tooltips, so **gate on the alias** or the addition shows up on unrelated ones:

```python
original = AmmunitionEmptyBlockTooltipData._packBlocks

def _packBlocks_with_extra(self, *args, **kwargs):
    blocks = original(self, *args, **kwargs)
    if <this instance's alias is the one we want>:
        blocks.append(<extra text block>)
    return blocks
```

Worth knowing which side a given tooltip is on before planning any work: the Gameface *param*
tooltip used by the WoT Plus button needs a shadowed copy of the document shell and re-diffing
on every client update, while this costs one wrapped method. See
[WoT Plus Subscriptions](wot-plus-subscriptions.md) for that comparison.

## Measured Layout Data

When native UI geometry is unstable across resolution changes, use measured resolution buckets instead of parsing display-tree bounds every frame.
That tradeoff is acceptable when the target anchor is effectively static for a given width bucket.

## Interface Scale (Stage Scaling)

WoT's interface scale (Settings → General) is applied by scaling the whole GFx stage, not by resizing it.
At x2 the stage reports `stage.scaleX == stage.scaleY == 2`, while `stage.stageWidth` / `stage.stageHeight` keep reporting the **full client pixels** (engine logs this as `Main view setAppScale: 2.00` / `Main view resized: <client/scale>`).

Consequences for a custom view:

- A view that lays out against raw `stage.stageWidth` is built at full pixel width and then rendered at the stage scale, so at x2 it ends up roughly double width and overflows the screen.
- Lay out against the **logical** size instead: derive the factor from the view's own `transform.concatenatedMatrix.a` (1 at x1, 2 at x2) and divide stage dimensions by it. At x1 this is a no-op. See `ResearchProgressBarLobby.resolveEffectiveScale` and `ResearchProgressBarStageSupport.resolveBarLayout`.
- Re-layout on scale change as well as resize. `stageWidth` / `stageHeight` stay constant when only the scale changes, so a size-only change check misses it — track the effective scale explicitly (`_lastEffectiveScale`).
- For mouse hit-testing and tooltip placement, never compare `getBounds(stage)` (stage-local) against `event.stageX/Y` (global pixels). Convert the global point with `globalToLocal` and work entirely in the view's local space, so it is scale-agnostic (`ResearchProgressBarTooltipView`).

Reading the factor from Python: `ServicesLocator.settingsCore.interfaceScale` is an `InterfaceScaleManager` whose resolved factor lives in its mangled `__scaleValue`; `getSetting(GRAPHICS.INTERFACE_SCALE) == 0.0` means "auto", not the factor. Avoid calling its getters (`getScaleOptions()`, `getIndex()`) at volatile moments — they re-validate the active scale against the current resolution and can reset an unsupported scale back to x1.

Repro note: x2 is only offered when the logical canvas stays at least 1024x768 (render height of roughly 1536 or more). At shorter resolutions WoT lists only `['auto', 'x1']` and silently clamps x2 back to x1 on any UI rebuild, so reproducing the x2 layout locally needs a tall (e.g. DSR) resolution.

## Flash → Python (DAAPI Reverse Channel)

Python → flash calls go through `self.flashObject.as_xxx(...)`. The reverse
direction works because `View._populate` binds `flashObject.script = self`
(see `DAAPIEntity.turnDAAPIon` in the decompiled client): GFx then injects the
Python view's public methods into same-named **declared** `public var
name:Function` slots on the AS3 document class. This is the same pattern WG's
own meta classes use (e.g. `ServerStatsMeta.relogin`). AVM2 classes are sealed,
so the declared var is required — an undeclared dynamic call cannot receive the
injection. Guard the var for null before calling; it stays null until DAAPI
init completes.

In this repo: `ResearchProgressBarLobby.onMarkerClickAction` (AS3 slot) →
`_ScaleformGarageView.onMarkerClickAction` (Python) → `zanju_rpb.actions`.

## Hand Cursor Over Clickable Elements

WoT renders its own engine cursor, but GFx cursor semantics still apply: a
sprite with `buttonMode = true` and `useHandCursor = true` makes GFx dispatch
`scaleform.gfx.MouseCursorEvent.CURSOR_CHANGE` on roll-over, which WoT's
`CursorManager` (see `BaseCursorManager.onChangeCursorHandler` in the
decompiled AS3) forwards to the engine via `WG.setCursor`. No manual cursor
management is needed — set the two flags on the clickable sprite.
