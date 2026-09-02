# Research, XP, And Post-Progression

## Vehicle XP And Free XP

Typical access pattern:

```python
stats = self.itemsCache.items.stats
veh_xp = stats.vehiclesXPs.get(veh_intCD, 0)
free_xp = stats.freeXP
actual_free_xp = stats.actualFreeXP
pp_xp = stats.postProgressionXP
ext_money = stats.getMoneyExt(veh_intCD)
```

Useful related data:

- `stats.unlocks`
- `stats.initialUnlocks`
- `stats.eliteVehicles`
- `stats.multipliedVehicles`
- `stats.prestigeMilestonesAchieved`

## Vehicle Research Surface

Vehicle-facing XP and unlock properties:

```python
vehicle.xp
vehicle.dailyXPFactor
vehicle.isElite
vehicle.isFullyElite
vehicle.getUnlocksDescrs()
vehicle.getUnlockDescrByIntCD(intCD)
vehicle.getAutoUnlockedItems()
vehicle.getEliteStatusProgress()
```

Module and equipment surfaces commonly used during research/mod-state work:

```python
vehicle.modules
vehicle.optDevices
vehicle.consumables
vehicle.battleBoosters
vehicle.battleAbilities
vehicle.shells
vehicle.setupLayouts
```

Checking whether a module is unlocked:

```python
unlocks = self.itemsCache.items.stats.unlocks
is_module_unlocked = module_intCD in unlocks
```

## Post-Progression Imports

Common post-progression imports:

```python
from post_progression_common import ACTION_TYPES, VEH_SKILL_TREE_ID_OFFSET
from skeletons.gui.game_control import IVehiclePostProgressionController
from gui.veh_post_progression.models.progression import PostProgressionItem
from gui.veh_post_progression.models.modifications import PostProgressionActionItem
```

Additional useful post-progression constants and helpers:

```python
from post_progression_common import (
	ACTION_TYPES,
	PAIR_TYPES,
	TankSetupLayouts,
	TankSetups,
	TankSetupGroupsId,
	TANK_SETUP_GROUPS,
	FEATURE_BY_GROUP_ID,
	GROUP_ID_BY_FEATURE,
	GROUP_ID_BY_LAYOUT,
	ROLESLOT_FEATURE,
	SETUPS_FEATURES,
	FEATURES_NAMES,
	VehicleState,
	makeActionCompDescr,
	parseActionCompDescr,
	VEH_SKILL_TREE_ID_OFFSET,
)
```

## Post-Progression Objects

Common live object surface:

```python
pp = vehicle.postProgression

pp.isActive(vehicle)
pp.isExists()
pp.isAvailable(vehicle)
pp.isVehSkillTree()
pp.getCompletion()
pp.iterOrderedSteps()
pp.iterUnorderedSteps()
pp.getStep(stepID)
pp.getFirstPurchasableStep(balance)
pp.getState()
pp.getRawTree()
```

Vehicle-level helpers:

```python
vehicle.postProgression
vehicle.isPostProgressionActive
vehicle.isPostProgressionExists
vehicle.isRoleSlotActive
vehicle.postProgressionAvailability(unlockOnly=False)
```

Controller access pattern:

```python
from skeletons.gui.game_control import IVehiclePostProgressionController

class MyMod(object):
	postProgressionCtrl = dependency.descriptor(IVehiclePostProgressionController)
```

## Research Progress Bar Production Surface

The shipping `research-progress-bar` mod now keeps a narrow production-only post-progression boundary.
These are the live surfaces that still matter for reproducing the current field-mod and Tier XI UI payload shape:

```python
vehicle.isPostProgressionExists
vehicle.postProgression

pp.isVehSkillTree()
pp.iterUnorderedSteps()
pp.getState(True)
pp.getFirstPurchasableStep(stats.getMoneyExt(vehicle.intCD))

step.stepID
step.id
step.level
step.getLevel()
step.getType()
step.action

step.isUnlocked()        # state == UNLOCKED: prereqs met, not yet bought (reachable now)
step.isReceived()        # state == RECEIVED: already bought
step.isLocked()          # state == LOCKED: no prerequisite path unlocked yet
step.isRestricted()      # state == RESTRICTED: externally blocked
step.getState()          # the raw 4-state value
step.mayPurchase(balance, ignoreState=False)
step.getNextStepIDs()    # child edges  (descriptor.unlocks)
step.getParentStepIDs()  # prereq edges (descriptor.requiredUnlocks)

action.getTechName()
action.getLocName()
action.getImageName()
action.getSlotCategory()
action._descriptor.name
action._descriptor.locName
action._descriptor.imgName
action._descriptor.categories
```

Current production payload expectations:

- `iterUnorderedSteps()` plus `stepID`/`level` provide total-step and unlocked-level counts.
- `getType()` is the stable source for Tier XI node XP buckets: `common` or `special` -> `10000`, `major` -> `20000`, `final` -> `25000`.
- `pp.getState(True).unlocks` is sufficient for researched/unresearched splits.
- `pp.getFirstPurchasableStep(balance)` is only used as a safe hint for the next Tier XI XP threshold.
- Tier XI marker text and icon/category metadata come from `step.action` getter methods and descriptor fields, plus the session UI-name cache populated from the vehicle hub.
- Real Tier XI action nodes can also carry runtime state and stat detail derived from the garage-side post-progression state: setup-switch nodes reuse the shared `loadout_switch` marker type, role-slot nodes switch between `role_slot` and the active slot-category icon, and other real nodes can surface KPI stat lines in their tooltips.
- Aggregate minor/major placeholders stay intentionally generic: they still use the circle/rhomb marker types and do not expose per-node KPI details even though their bucket seed action supplies naming/icon metadata elsewhere in the payload.

### Tier XI node reachability (tree state)

Each step carries the client's own 4-state machine, computed in
`PostProgressionStepItem.__getState(progressionState)` (verified against the
decompiled EU 2.3 client):

- `RESTRICTED` if `isRestricted()` (externally blocked), else
- `RECEIVED` if the step id is in the progression's unlock set (already bought), else
- `UNLOCKED` if `unlockStrategy([progressionState.isUnlocked(req) for req in requiredUnlocks])` — **reachable now**, else
- `LOCKED` (no prerequisite path unlocked yet).

`unlockStrategy` is per node, read from the tree XML: it defaults to `all` (AND —
every prerequisite unlocked) and is `any` (OR — at least one prerequisite unlocked)
when the node declares `<unlockStrategyAny>` (`items/components/post_progression_components.TreeStep`).
So an OR-join node becomes reachable as soon as one neighbour is unlocked, and the
client already knows which nodes are OR vs AND — no need to reconstruct it.

The bar uses this to gray out a minor/major bucket whose remaining nodes are all
`LOCKED`/`RESTRICTED` (none `UNLOCKED`), rather than the XP-only cost heuristic.
**Naming gotcha:** `step.isUnlocked()` (the item) is the `UNLOCKED` state
(reachable, not bought), whereas the collector's "unlocked step ids" set is
`progressionState.isUnlocked(stepID)` = the `RECEIVED`/bought state — opposite ends
of the lifecycle. Read node states directly off the steps from
`iterUnorderedSteps()`; their `__state` is baked from the live progression state at
build time, so `step.getState()` needs no argument. Treat a missing/unreadable
state as reachable (older clients) so the graying only ever hides truly blocked
nodes.

Exploratory surfaces removed from production code but still worth remembering if deeper investigation is needed later:

- post-progression controller settings traversal
- `pp.getRawTree()` traversal
- broad category-hint probing over arbitrary objects
- method-probe ladders over step objects
- `PostProgressionStepItem.getPrice()` during scheduled hangar updates

The write-side flows below have no upstream equivalent. For the general contract they sit inside
— one in-flight guard per request domain, and why a success response is not a cache confirmation —
read [automation-processors](https://modding.wot-tools.dev/automation-processors.html). See
[The Upstream Modding Guide](upstream-guide.md).

## Safety Notes For This Repo

Live testing in this repository established a practical safety boundary:

- shallow post-progression reads can be stable
- deep scheduled-update traversal can hard-crash the client with no Python traceback
- presenter/view-model materialization is often safer than deeper runtime probing when the same value is already exposed through UI state

Validated local safety boundary:

- `PostProgressionStepItem.getType()` was stable in scheduled hangar updates used by this repo
- `PostProgressionStepItem.getPrice()` should still be treated as unsafe in scheduled hangar updates
- `pp.getFirstPurchasableStep(balance)` is useful as a safer hint source than deeper price traversal

## Tier XI / Vehicle Hub Notes

Tier XI data often surfaces through the vehicle hub and skill-tree presenters rather than through a single clean always-available garage-side API.
Treat those UI-derived values as session-scoped data sources, not as proof that deeper object traversal is safe in all contexts.

The most important practical consequence is that presenter-populated data can be reused once the relevant UI has been opened in the session, but it should not be treated as a guaranteed always-available garage-side API.

## Write-Side Research Actions (Marker Clicks)

The bar's clickable markers run WG's own research flows through the items-actions
factory (`gui.shared.gui_items.items_actions.factory`), the same path the game's
context-menu "Research" handler uses. Both flows show WG's native confirmation
dialog before spending anything, so a mod-triggered click can never spend silently.
Symbols verified against the decompiled EU 2.3 client; implementation in
`mods/research-progress-bar/src/zanju_rpb/actions.py`.

- Tech tree (module or next vehicle):
  `factory.doAction(factory.UNLOCK_ITEM, intCD, UnlockProps(...))` with
  `UnlockProps(parentID, unlockIdx, xpCost, required, discount, xpFullCost)` from
  `gui.Scaleform.daapi.view.lobby.techtree.settings`, built from the vehicle's own
  `getUnlocksDescrs()` row `(unlockIdx, xpCost, itemCD, required)`.
  - `UnlockItemAction` runs an `UnlockItemConfirmator` dialog plugin; when even
    vehicle XP + free XP is short it opens the exchange-XP dialog instead.
  - Vehicle unlocks must pass the blueprint-discounted cost plus discount percent
    plus raw full cost, or WG validates against the full cost. Module unlocks must
    keep the raw cost with discount 0, or WG's validator rejects the request.
  - Buy-and-mount after a module research: shows WG's own "purchase and mount"
    popup. **Gotcha:** the factory's `BUY_AND_INSTALL_ITEM` constant is *not*
    registered in its `_ACTION_MAP`, so `factory.doAction(BUY_AND_INSTALL_ITEM, ...)`
    just logs `Action type is not found buyAndInstallItemAction` and does nothing.
    Build the action directly instead:
    `BuyAndInstallWithOptionalSellItemAction(moduleCD, vehicleCD).doAction()` (from
    `gui.shared.gui_items.items_actions.actions`). **Use that subclass, not the plain
    `BuyAndInstallItemAction`:** the popup carries a "sell previous module" checkbox,
    and only the subclass acts on it — its `doAction` captures the installed module
    first, then reads `AUTO_SELL_KEY` (`'sellPreviousModule'`) out of the dialog
    result and runs `ModuleSeller` on the replaced module. The base class discards
    that result, so the box silently does nothing.
    Its `doAction` is `@adisp_process`,
    so calling it fires the flow; it runs `BuyAndInstallItemProcessor` with
    `skipConfirm=False` (the `IGUIItemAction` default), whose
    `BuyAndInstallConfirmator._gfMakeMeta` returns
    `showBuyModuleDialog(item, installedModule, currency, installReason)` =
    `BuyModuleDialogView` as the confirm step; only a confirmed dialog spends. The
    action raises `SoftException` for non-`GUI_ITEM_TYPE.VEHICLE_MODULES` items, so
    vehicles cannot reach it. UNLOCK_ITEM returns as soon as its confirm dialog
    opens, and the module is only researched once the server round-trip lands, so
    wait for `moduleCD in itemsCache.items.stats.unlocks` before offering the popup
    (a cancelled research never lands -> no popup).
  - **The tech-tree data provider must be loaded before a VEHICLE unlock.**
    `UnlockItemValidator._validate` branches on item type: for a vehicle it calls
    `g_techTreeDP.isNext2Unlock(itemCD, **unlockStats._asdict())` and ignores the
    `required` set in UnlockProps; only the module branch uses
    `vehicle.getUnlocksDescr(unlockIdx)` + `unlockStats.isSeqUnlocked(required)`.
    `g_techTreeDP` (`gui.Scaleform.daapi.view.lobby.techtree.techtree_dp`) builds its
    node graph lazily in `load()`, normally the first time the research screen opens.
    An unloaded provider has empty `__topLevels`/`__nextLevels`, so `isNext2Unlock()`
    returns False and the unlock fails with `required_locked` — which looks exactly
    like a genuine prerequisite problem. Call `g_techTreeDP.load()` first (a no-op
    once loaded, so the XML parse is paid at most once per session).
- Field modifications:
  `factory.doAction(factory.PURCHASE_POST_PROGRESSION_STEPS, vehicle, [step_id])`
  runs WG's confirm-then-research chain (`AsyncGUIItemAction._confirm` shows the
  PostProgressionResearch dialog; only a confirmed dialog purchases).
  - `gui.shared.event_dispatcher.showPostProgressionResearchDialog` is NOT a
    research entry point: it only shows the dialog and returns the choice.
  - Step structure (EU 2.3): each field-mod level pairs a LEVELED base step
    (SimpleModItem / FeatureModItem / RoleSlotModItem action, paid in XP) with a
    free `MultiModsItem` child at the same level holding the two selectable
    variants. The leveled step is the only purchasable one — always research it,
    never the MultiModsItem (it costs nothing and cannot be researched; the
    variant is a separate free selection on WG's screen). Grouping steps by
    level therefore yields two entries on pair levels; resolve the purchase
    target as the first non-MultiModsItem entry.
- Tier 11 upgrades: the flat bar cannot represent the branching upgrade tree, so
  a click on a reachable minor / major / final node does not buy a specific node
  — it opens WG's own upgrades overlay where the player picks and buys. Nothing
  is spent from the bar. Tier 11 upgrades are the vehicle skill tree, so the
  entry point is `gui.shared.event_dispatcher.showVehicleHubVehSkillTree(intCD)`
  (navigates to `vehicleHub/vehSkillTree`; `itemsCache` is dependency-injected so
  only `intCD` is passed). It self-guards on `vehicle.postProgression
  .isVehSkillTree()`. Do NOT use `showVehPostProgressionView` for this — that
  plain post-progression (field-mods) view renders a broken variant of the system
  for skill-tree vehicles.
- Fallbacks: `gui.shared.event_dispatcher.showResearchView(intCD)` and
  `showVehPostProgressionView(intCD)` open the native screens when an action
  symbol is unreachable.
