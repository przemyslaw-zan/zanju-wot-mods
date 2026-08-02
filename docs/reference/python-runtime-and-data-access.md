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

Additional useful imports seen in this repo's WoT-facing code:

```python
from gui.shared.gui_items.vehicle_equipment import VehicleEquipment
from gui.shared.money import Money, Currency, DynamicMoney
from items.vehicles import getItemByCompactDescr, getVehicleType
from dossiers2.custom.cache import getCache as getDossiersCache
```

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

That gives access to:

- current inventory data
- vehicle objects
- account stats
- unlock state
- XP pools

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

- Treat early-load and transition states as unstable until the target object is confirmed present.
- Prefer stable item-cache data over deeper runtime internals when both expose the same fact.
- Guard every assumption around preview vehicle state, missing descriptors, and UI transitions.
