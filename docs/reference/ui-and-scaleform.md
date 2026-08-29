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
| `TOP_SUB_VIEW` | 6 | screens the client draws over the garage |
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

Three things follow for stacking against other mods. A mod SWF on `WINDOW` draws above the whole garage document. It therefore covers every Gameface mod widget, and every tooltip those widgets open, whatever `z-index` they carry.

No band below the garage document is open to a mod, so a Scaleform mod view cannot go under a Gameface one. A band also applies to a whole view and not to an element inside it. A tooltip drawn inside a view stays in the band of that view, so a bar on `WINDOW` plus a tooltip over the platoon window needs two views.

`research-progress-bar` names its band in one place, the `ViewSettings` call in `scaleform/hooks.py`. To try another band, change that constant and rebuild. Nothing above `WINDOW` is proven for a mod view: no mod in the log above sits higher than band 7.

## Window Lifetime

This repository uses a pragmatic rule:

- keep the custom window persistent for ordinary hide/show cases when that is stable
- dispose it completely when a route or UI context proves that a hidden window still interferes with native behavior

## Hangar Visibility Rules

Default hangar visibility is not only a matter of one container alias.
In practice, route changes and container-layer changes both matter.
Some hangar-local overlays announce themselves only through lobby-state-machine route changes.

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

## Input And Focus Notes

Hidden custom windows can still interfere with native UI behavior if they remain part of WoT's active window stack.
When that happens, hiding the SWF is not enough; the view must be disposed and recreated on return to the safe context.

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
