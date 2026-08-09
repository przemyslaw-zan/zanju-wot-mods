# Customization Screen

How the vehicle customization screen is put together, and where a mod can get inside it.
Verified against WoT **2.3.1.0** by decompiling the shipped `scripts.pkg`; see
[Reading The Client's Own Code](reading-the-clients-code.md) for the method.

## It Is Scaleform, Not Gameface

Entering customization loads a Scaleform window:

```text
Loading window: SFWindow(uniqueID=745, layer=5, decorator=None, content=None,
                         viewKey=ViewKey[alias=customization, name=customization])
```

So the Gameface widget route used by `premium-time` and `directives-helper` does not apply
here — see [Gameface Mod Widgets](gameface-mod-widgets.md) for what that route can reach.
The Scaleform pattern in [UI And Scaleform](ui-and-scaleform.md) is the relevant one.

Parts of the flow *are* Gameface, and Wargaming is migrating more of it: the cart
(`CustomizationCartState`, keyed on `R.views.lobby.customization.CustomizationCart()`), the
rarity reward screen, and the progression-styles onboarding view all ship as Gameface
documents under `gui/gameface/_dist/production/lobby/customization/`.

## The Screen Logs Nothing

Nothing under `gui.Scaleform.daapi.view.lobby.customization` writes to `python.log` at all —
entering the screen, switching tabs and applying a style are all silent. Only the lobby state
machine and the resulting server sync are visible. A mod cannot observe this screen through a
logging handler the way `research-progress-bar` reads route changes; it needs Python hooks.

Route on entry, in order: `subScope/subLayer/customization` → `.../customization/loading` →
`.../customization/main` → `subScope/topLayer/customization/edit`. The hangar's own state is
killed on the way in and rebuilt on the way out.

## Applying An Item Is Visible In The Inventory Diff

A style application arrives as an `onClientUpdate` diff under `inventory` key `12`, which is
`customizationItem` in `items.ITEM_TYPE_NAMES`:

```python
{12: {1: {4: {252: {0: 1}, 18: {0: 1}}},
      2: {53249: {15: '\x04\x10\xfc\x01'}},
      3: {},
      4: {4: {252: {53249: 1}, 18: None}}}}
```

Inside it, `4` is `CustomizationType.STYLE`. So section `4` reads *style 252 installed on
vehicle 53249, style 18 unset*, and section `2` is the repacked outfit for that vehicle at
season mask `15` (all four seasons). Useful as a confirmation signal, but the context's own
events are the better hook — they fire before the round trip.

## The Model Layer Is Not In The View

This is the fact that makes a replacement UI practical. `CustomizationContext` is owned by
the **service**, and created by the lobby **state**, not by the view:

```python
# _MainState._onEntered, in .../customization/states.py
self.__hangarSpace.space.turretAndGunAngles.set(...)
self.__setupTankTransformation()
self.__c11n.onVisibilityChanged(True)
self.__c11n.createCtx(**{k: event.params.get(k) for k in ('season', 'modeId', 'tabId', 'itemCD')})
_CustomizationEditState.goTo()
```

`CustomizationService` holds `createCtx` / `getCtx` / `destroyCtx`; `MainView` is a presenter
over the result. Everything below therefore survives a view replacement:

| Surface | What it gives you |
| --- | --- |
| `ICustomizationService.getCtx()` | modes, tabs, seasons, outfits, install/remove, `isOutfitsModified`, apply |
| `ctx.events` | ~35 events (`onTabChanged`, `onItemInstalled`, `onCarouselFiltered`, `onItemsBought`, …) — observation needs no patching |
| `CustomizationCarouselDataProvider` | filtering, sorting and grouping of the item list |
| `VehicleAnchorsUpdater` | anchor positions projected to screen coordinates |
| `gui/customization/processors/cart.py` | purchase flow |
| `_MainState` | camera, tank transform, hangar space, exit confirmation |

## Replacing A Registered View

The screen is one `ViewSettings` entry in `gui/Scaleform/daapi/view/lobby/__init__.py`:

```python
ViewSettings(VIEW_ALIAS.LOBBY_CUSTOMIZATION, CustomizationMainView,
             'customizationMainView.swf', WindowLayer.SUB_VIEW,
             VIEW_ALIAS.LOBBY_CUSTOMIZATION, ScopeTemplates.LOBBY_SUB_SCOPE)
```

`EntitiesFactories.addSettings` raises on a duplicate alias, so a second registration is not
an option. The supported route is the extension override. `PackageImporter._loadPackage`
strips any base registration whose alias an extension has claimed:

```python
settings = imported.getViewSettings()
if not isExtention:
    settings = self._getHandlesWithoutExtensionOverride(settings, arenaGuiType)
g_entitiesFactories.initSettings(settings)
```

and `app_factory.createLobby` loads base packages first, extension packages second:

```python
self.__importer.load(lobby.proxy, sf_config.COMMON_PACKAGES + lobbyPackages)
self.__importer.load(lobby.proxy, g_overrideScaleFormViewsConfig.lobbyPackages, None, True)
```

Nothing in the shipped client calls `initExtensionLobbyPackages`, so the registry is empty
and the seam is free for a mod to take. What a mod must get right:

- **Register before the lobby is created.** Mod `init()` at client start-up is early enough.
- **Use the absolute package path.** The build lands `src/<pkg>/` at
  `res/scripts/client/gui/mods/<pkg>/`, so the path is `gui.mods.<pkg>.<module>`.
- **Provide all three package functions.** `getViewSettings`, `getContextMenuHandlers` and
  `getBusinessHandlers` are each required; a missing one raises `SoftException` during lobby
  creation. Empty tuples are fine for the last two — the client's own lobby package keeps its
  `LOAD_VIEW` listener for the alias, and it resolves through the factory to whatever is
  registered.
- **Keep the package module's imports light.** It is imported at registration time, long
  before the lobby exists. Import the view class inside `getViewSettings()`.
- **Roll back a failed registration.** `initExtensionLobbyPackages` appends to its package
  list *before* validating aliases, so a mid-way failure can leave the base view suppressed
  with no replacement — a screen that opens to nothing. Pre-check the alias, and on failure
  remove both the package path and any aliases recorded under the extension's name.
- **Subclass `View`.** `ViewFactory.validate` rejects anything else, and requires a non-empty
  `url`. `gui.Scaleform.daapi.LobbySubView` is a thin `View` subclass and is what the client
  uses here.

## The Host Must Be A SWF

`_MainState` is an `SFViewLobbyState` keyed to `ViewKey(VIEW_ALIAS.LOBBY_CUSTOMIZATION)`, and
`_getHandlesWithoutExtensionOverride` only strips view settings and context-menu handlers —
**state registrators are not overridable**, so the base state always registers and always
wants a Scaleform view at that alias.

Hosting the UI in Gameface instead is not blocked by that (`registerStates` could be patched)
but by layout IDs: a Wulf view needs a `layoutID` from the client's generated `R` resources,
and a mod cannot mint one. The customization Gameface documents that do exist belong to
Wargaming's own views.

## Cost Of A Full Replacement

The presentation layer is roughly 1.4 MB of Flash across ~15 SWFs — `customizationMainView`
(188 KB), `customizationPropertiesSheet` (344 KB), `customizationComponents` (329 KB),
`customizationBottomPanel` (190 KB), `customizationCarouselView` (130 KB),
`customizationAnchorView` (145 KB), plus popovers and style info.

One lever against that: mod SWFs already link against Wargaming's own AS3 classes by
compiling against a local stub and resolving the real class at runtime — `research-progress-bar`
does exactly this for `net.wg.infrastructure.base.AbstractView` in `ui/wot-api/`. Extending
the stub set to their component library would mean reusing their renderers instead of drawing
everything from scratch. Unvalidated beyond the one class.

The standing risk is ownership rather than feasibility: replacing the screen means every
customization feature Wargaming ships — attachments, stat trackers and progression styles are
all recent — is absent until the mod implements it.

## Carousel Filtering And Sorting

Worth knowing even without a replacement UI, since these are the cheapest improvements
available:

- **Filters do not persist.** `CustomizationCarouselDataProvider.__carouselFilters` and
  `__selectedGroup` are built in `__init__` and dropped in `_dispose`, i.e. per screen entry.
  Filter state resets every time the player walks in.
- **There is no text search.** Filtering is toggles (historic / owned / applied / rarity /
  form factor) plus a group dropdown, defined in `__initFilters`.
- **Sort order is fixed.** `comparisonKey` orders by type → national emblem → rarity → group
  → id, and `__createSortCriteria` returns `None` except when camouflage-dependent items are
  in play.

## Related Reading

- [UI And Scaleform](ui-and-scaleform.md)
- [Gameface Mod Widgets](gameface-mod-widgets.md)
- [Reading The Client's Own Code](reading-the-clients-code.md)
