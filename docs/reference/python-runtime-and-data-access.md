# Python Runtime And Data Access

## Core Import Paths

Common imports used in this repository include:

```python
from CurrentVehicle import g_currentVehicle, g_currentPreviewVehicle
from gui.ClientUpdateManager import g_clientUpdateManager
from gui.shared.gui_items.Vehicle import Vehicle
from gui.shared.gui_items import GUI_ITEM_TYPE, GUI_ITEM_TYPE_NAMES
from gui.shared.utils.requesters import REQ_CRITERIA
from gui.shared.money import Money, Currency, DynamicMoney
from skeletons.gui.shared import IItemsCache
from helpers import dependency
from items.vehicles import VehicleDescr, getItemByCompactDescr, getVehicleType
from items import getTypeOfCompactDescr
```

For how to find a symbol you do not already know, and how much a definition proves on its own,
read the guide's [source-navigation](https://modding.wot-tools.dev/source-navigation.html) rather
than growing this list. See [The Upstream Modding Guide](upstream-guide.md).

## Account And Player State

Useful event/state imports:

```python
from Event import Event, EventManager
from PlayerEvents import g_playerEvents
```

Premium account state lives on the items cache stats, the same fields the game's own header
presenter reads:

```python
stats = itemsCache.items.stats
stats.isPremium                  # bool
stats.activePremiumExpiryTime    # unix timestamp, 0 when not premium
```

The Gameface header has its own copy on the view model
(`UserAccountModel.subscriptions.premiumAccount`: `expiryTime` / `state`), which is what JS
running inside the header document should read. Note that `state` lags the timestamp — see
[Events And Callbacks](events-and-callbacks.md).

## Items Cache Pattern

The stable pattern for reading game data is dependency injection through `IItemsCache`.

```python
class MyMod(object):
    itemsCache = dependency.descriptor(IItemsCache)
```

That gives inventory data, vehicle objects, account stats, unlock state and XP pools. Note that
`dependency` comes from `helpers`. It is not exported by `frameworks.wulf`, whatever the upstream
guide's dependency page says — see [The Upstream Modding Guide](upstream-guide.md#dependency-does-not-come-from-frameworkswulf).

When the cache is trustworthy, and what an empty read means before the first sync, is upstream in
[account-lobby](https://modding.wot-tools.dev/account-lobby.html) and
[readiness-matrix](https://modding.wot-tools.dev/readiness-matrix.html). The measured cost of a
garage-return sync is in [Events And Callbacks](events-and-callbacks.md).

## Current Vehicle Access

Typical vehicle access points:

- `g_currentVehicle.item`
- `g_currentPreviewVehicle.isPresent()`
- `itemsCache.items.getVehicle(invID)`
- `itemsCache.items.getItemByCD(intCD)`

Typical singleton access:

```python
from CurrentVehicle import g_currentVehicle

vehicle = g_currentVehicle.item
int_cd = g_currentVehicle.intCD
inv_id = g_currentVehicle.invID
```

Useful state helpers include:

- `g_currentVehicle.isPresent()`
- `g_currentVehicle.isInHangar()`
- `g_currentVehicle.isLocked()`
- `g_currentVehicle.isReadyToFight()`
- `g_currentVehicle.isPostProgressionActive()`

### The Preview Vehicle Carries A Perfect Crew

`g_currentPreviewVehicle` is not the player's tank. It is a copy, and the client rewrites two
parts of it before showing it (`CurrentVehicle.py`, verified on 2.3.1.3):

```python
vehicle = self.itemsCache.items.getVehicleCopyByCD(vehicleCD)
vehicle.crew = vehicle.getPerfectCrew()
...
    vehicle.descriptor.removeOptionalDevice(slotID)
    vehicle.optDevices.installed[slotID] = None
vehicle.crew = vehicle.getPerfectCrew()
```

Every seat therefore reads as fully trained, and the optional devices are gone. Anything that
measures a crew or reads a fitted device gets a confident wrong answer rather than an error:

- `Tankman.crewMemberRealSkillLevel` returns the maximum, so a grant-perk directive computes a
  gain of `+0%`. See [Directives And Battle Boosters](directives-and-battle-boosters.md).
- `item.isAffectsOnVehicle(vehicle)` validates equipment directives against mounted optional
  devices, and the copy has none.

**Rule.** When the compact descriptor names a vehicle the account owns, resolve it through
`IItemsCache` and treat that inventory `Vehicle` as the authority. Use the preview object only
when no owned item exists, or when the question really is about the preview.

## GUI Item Types

Relevant GUI item types for research and equipment work:

```python
from gui.shared.gui_items import GUI_ITEM_TYPE

GUI_ITEM_TYPE.VEHICLE
GUI_ITEM_TYPE.TURRET
GUI_ITEM_TYPE.GUN
GUI_ITEM_TYPE.CHASSIS
GUI_ITEM_TYPE.ENGINE
GUI_ITEM_TYPE.RADIO
GUI_ITEM_TYPE.VEHICLE_MODULES
GUI_ITEM_TYPE.OPT_DEVICE
GUI_ITEM_TYPE.SHELL
GUI_ITEM_TYPE.VEH_POST_PROGRESSION
GUI_ITEM_TYPE.MODIFICATION
```

## Vehicle Queries

Typical inventory query pattern:

```python
from gui.shared.utils.requesters import REQ_CRITERIA

vehicles = self.itemsCache.items.getVehicles(
    criteria=REQ_CRITERIA.INVENTORY
            | ~REQ_CRITERIA.VEHICLE.MODE_HIDDEN
            | ~REQ_CRITERIA.VEHICLE.EVENT_BATTLE
            | REQ_CRITERIA.VEHICLE.ACTIVE_IN_NATION_GROUP
)
```

## Notes

- Prefer stable item-cache data over deeper runtime internals when both expose the same fact.
- Readiness order across account, avatar, cache and view is upstream in
  [readiness-matrix](https://modding.wot-tools.dev/readiness-matrix.html). Identifier scopes, and
  which of them survives what, are in [state-scope](https://modding.wot-tools.dev/state-scope.html).
