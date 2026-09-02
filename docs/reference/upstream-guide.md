# The Upstream Modding Guide

[modding.wot-tools.dev](https://modding.wot-tools.dev/) is a 79-page client-modding handbook. It is broader than this section, and better organised. These pages now defer to it for anything general, and keep only what we measured ourselves.

Read it directly. It is static HTML with an [llms.txt](https://modding.wot-tools.dev/llms.txt) index, so a page can be fetched and searched without a browser. Guessing URLs fails; take them from that index.

## What we defer to it for

| Subject | Page |
| --- | --- |
| Loader lifecycle, `init()`/`fini()`, safe wrappers | [first-mod](https://modding.wot-tools.dev/first-mod.html), [hook-composition](https://modding.wot-tools.dev/hook-composition.html) |
| Python 2.7 traps, named loggers, unicode boundaries | [python27-runtime](https://modding.wot-tools.dev/python27-runtime.html) |
| Readiness order across account, avatar, arena, view | [readiness-matrix](https://modding.wot-tools.dev/readiness-matrix.html), [lifecycle](https://modding.wot-tools.dev/lifecycle.html) |
| Event families and their failure contracts | [event-buses](https://modding.wot-tools.dev/event-buses.html) |
| `BigWorld.callback` ownership, `wg_async` futures | [callback-lifecycle](https://modding.wot-tools.dev/callback-lifecycle.html) |
| Dependency resolution and service readiness | [dependency-services](https://modding.wot-tools.dev/dependency-services.html) |
| Identifier scopes: entity, inventory, compact descriptor | [state-scope](https://modding.wot-tools.dev/state-scope.html), [vehicles-items](https://modding.wot-tools.dev/vehicles-items.html) |
| Native request flows and cache confirmation | [automation-processors](https://modding.wot-tools.dev/automation-processors.html) |
| Standalone Gameface windows, sizing, scaling, input | [gameface-standalone](https://modding.wot-tools.dev/gameface-standalone.html), [gameface-layout-input](https://modding.wot-tools.dev/gameface-layout-input.html) |
| Resource maps, `coui://` paths, cache invalidation | [gameface-resources](https://modding.wot-tools.dev/gameface-resources.html), [resource-cache-invalidation](https://modding.wot-tools.dev/resource-cache-invalidation.html) |
| Replay rewind as a lifecycle boundary | [gameface-lifecycle](https://modding.wot-tools.dev/gameface-lifecycle.html) |
| Coordinate spaces, projection, minimap | [spatial-coordinates-projection](https://modding.wot-tools.dev/spatial-coordinates-projection.html) |
| Hangar space, CGF systems, subhangar groups | [hangar-garage-runtime](https://modding.wot-tools.dev/hangar-garage-runtime.html) |
| Embedded browser bridge, loopback tools | [embedded-browser-bridge](https://modding.wot-tools.dev/embedded-browser-bridge.html), [local-tools-bridges](https://modding.wot-tools.dev/local-tools-bridges.html) |

## What it does not cover

Keep writing these here, because nothing upstream answers them:

- The Gameface CSS subset and the holes in it. See [Gameface Mod Widgets](gameface-mod-widgets.md).
- OpenWG injection mechanics: sub-view scanning, the one-mod-per-sub-view collision, push against poll.
- Mod Menu, and the ModsSettings API it replaced. See [In-Game Settings](in-game-settings.md).
- Scaleform stage scaling and the DAAPI reverse channel. See [UI And Scaleform](ui-and-scaleform.md).
- Gun marker geometry, `twinGun` against `dualGun`. See [Gun Marker Sizing](gun-marker-sizing.md).
- Personal missions. See [Personal Missions](personal-missions.md).
- Measured timings: the premium mask lag, items-cache sync durations, the delay before `onSyncCompleted`.

## Where the guide is wrong

Four claims fail against client 2.3.1.3. Each was checked twice: read out of the shipped bytecode, then observed in a running client through a throwaway probe mod. The probe has been removed, so the log excerpts below are the record it left.

The fourth one is the serious one: it breaks the data path of the guide's whole standalone Gameface series.

### `dependency` does not come from `frameworks.wulf`

[dependency-services](https://modding.wot-tools.dev/dependency-services.html) shows this import:

```python
from frameworks.wulf import dependency
```

`frameworks/wulf/__init__.py` re-exports 40 names and this is not one of them, so the example fails. The module every current caller uses is `helpers.dependency`, which is what the guide's own tutorials import four pages later.

Confirmed on a running client, 2.3.1.3:

```text
U1 guide says: from frameworks.wulf import dependency
   -> AttributeError: module frameworks.wulf has no attribute u'dependency'
U1 real path:  from helpers import dependency
   -> OK, <module 'helpers.dependency' from 'scripts/client/helpers/dependency.pyc'>
U1 frameworks.wulf.__all__ holds 40 names, dependency present: False
```

Probe tag: `U1`. Status: **confirmed at runtime**.

### `DefaultHangarState` cannot recognize a mode garage

[gameface-lifecycle](https://modding.wot-tools.dev/gameface-lifecycle.html) says to show a garage overlay only while the visible state is the normal hangar state, "commonly represented by `DefaultHangarState`". Those classes come out of a factory, and each mode extension calls that factory again:

```python
# gui/impl/lobby/hangar/states.py
HangarState, DefaultHangarState, AllVehiclesState, EasyTankEquipState = \
    generateBasicHangarStateClasses(SubScopeSubLayerState, R.invalid)

# fun_random/gui/impl/lobby/hangar/states.py calls the same factory again
```

Each call builds a different class object, so `getStateByCls(DefaultHangarState)` matches the core garage and nothing else. A mode garage answers False and the overlay stays hidden there. The client's own `OverlapCtrlMixin._onVisibleRouteChanged` makes this exact comparison and carries the same limit.

Read the route string instead. It names the mode as a prefix and the screen as a suffix, so one test covers every mode. See `is_bare_hangar_route` in `mods/directives-helper/src/zanju_dh/route_gate.py`, and the route table in [Directives And Battle Boosters](directives-and-battle-boosters.md#when-the-window-shows).

Probe tag: `U2`. Each route the lobby reports is logged with the answer the guide's test gives, and every registered hangar state is listed with its class.

Run 2 settled it. With every mode extension loaded the lobby registers **58 states whose route names a hangar**, across six garage roots. Only one matches the core class:

| Garage route | State class | Matches core |
| --- | --- | --- |
| `subScope/subLayer/hangar/{root}` | `GeneratedDefaultHangarState` | **yes** |
| `subScope/subLayer/comp7/hangar/{root}` | `Comp7RootHangarState` | no |
| `subScope/subLayer/comp7Light/hangar/{root}` | `Comp7LightRootHangarState` | no |
| `subScope/subLayer/frontline/hangar/{root}` | `FrontlineRootHangarState` | no |
| `subScope/subLayer/lastStand/hangar/{root}` | `LastStandRootHangarState` | no |
| `subScope/subLayer/funRandomHangar/{root}` | `GeneratedDefaultHangarState` | **no** |

The last row is the one to show the author. Fun Random's garage state carries the **same class name** as the core one and is still a different class object, so `getStateByCls(DefaultHangarState)` answers False while the player stands in an ordinary garage. Anyone debugging by printing the class name sees `GeneratedDefaultHangarState` and concludes the test should have passed.

Worth knowing on its own: **a mode's Python is not importable unless that mode is loaded.** The extension package sits on disk either way. A static reading of the packages and a runtime import answer different questions. The runtime answer also depends on what the account can currently play.

Status: **confirmed at runtime.** Five of six garage roots fail the guide's test.

### The `len(resource_map)` warning does not describe this client

[gameface-resources](https://modding.wot-tools.dev/gameface-resources.html) says: "Do not use `len(resource_map)` as the next key when native keys can be sparse." `net.openwg.gameface` 1.1.6 does exactly that, so the warning reads as a live hazard in the helper the same guide tells you to depend on.

It is not one here. The shipped `gui/unbound/res_map.json` holds 131,570 entries keyed `0` through `131569` with no gaps, so `len()` lands one past the end every time. The warning is still worth keeping as a rule, but it describes a client that could exist rather than this one.

```python
# openwg_gameface.ResMapManager._add_mod_items_to_resource_map
numeric_item_id = len(resource_map)
```

The other rule on that page is the useful one, and it is real. The helper does `del item['itemID']` on the dictionary it was given. It parses its own JSON file, so today only its own transient copy suffers. A caller that ever hands OpenWG a dictionary it still needs should pass a copy.

Probe tag: `U3`. Status: **confirmed, and downgraded from a bug to a rule.** Run 1 showed twelve mod entries allocated densely from 131570 upward, ours last:

```text
U3 res map validated: False        <- first launch, before the restart
U3 res map validated: True         <- second launch
U3 mod entries registered: 12
U3   MoEGarageGameFaceView -> 131570 (hex 201f2)
U3   FightButtonTextView   -> 131571 (hex 201f3)
...
U3   mods/zanju/ClientProbe/panelLayoutID -> 131581 (hex 201fd)
```

Seven other installed mods already register resource-map entries, so the standalone route is well travelled in the wild rather than exotic.

### The JavaScript model API does not exist

This is the one worth reporting first. [gameface-standalone](https://modding.wot-tools.dev/gameface-standalone.html) gives this as the way a standalone panel reads its model and follows updates:

```javascript
currentModel = viewEnv.getViewModel();
render(currentModel.payload);
viewEnv.onDataChanged(() => { ... });
```

None of those three calls exists on client 2.3.1.3:

```text
[ClientProbe] getViewModel failed: TypeError: viewEnv.getViewModel is not a function
[ClientProbe] onDataChanged failed: TypeError: viewEnv.onDataChanged is not a function
[ClientProbe] onScaleUpdated failed: TypeError: viewEnv.onScaleUpdated is not a function
```

`getViewModel` appears **zero** times across the client's own 605 Gameface bundles. `viewEnv.onDataChanged` appears 520 times, but only ever as an event name inside `engine.on("viewEnv.onDataChanged", handler)` — never as a method. The likely cause is a confusion with the Python side, where `ViewImpl.getViewModel()` is real and the guide uses it correctly in the same tutorial.

What the client and OpenWG both use instead:

```javascript
const model = window.model;                        // root model of this document, resId 0
// a sub-view model is window.subViews.get(resId).model
engine.on('viewEnv.onDataChanged', handler);
const callbackId = viewEnv.addDataChangedCallback('model', 0, true);
engine.on('self.onScaleUpdated', onScale);         // not viewEnv.onScaleUpdated
```

The rest of the guide's standalone advice held up. `viewEnv.getScale()` and `viewEnv.resizeViewPx()` both work, and the panel came out at exactly the authored size.

This affects the guide's Levels 4, 5, 6 and 9 tutorials, which all render a standalone panel through the same three calls.

Status: **confirmed at runtime, cause identified.**

## Related Reading

- [Reading The Client's Own Code](reading-the-clients-code.md) — how to check a claim against the shipped client.
- [Resources And External Links](../resources.md)
