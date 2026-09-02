# Events And Callbacks

## Current Vehicle Events

Typical hooks:

```python
from CurrentVehicle import g_currentVehicle, g_currentPreviewVehicle

g_currentVehicle.onChanged += handler
g_currentVehicle.onChangeStarted += handler

g_currentPreviewVehicle.onChanged += handler
g_currentPreviewVehicle.onChangeStarted += handler
g_currentPreviewVehicle.onComponentInstalled += handler
g_currentPreviewVehicle.onPostProgressionChanged += handler
g_currentPreviewVehicle.onVehicleUnlocked += handler
g_currentPreviewVehicle.onVehicleInventoryChanged += handler
g_currentPreviewVehicle.onSelected += handler
```

## Player Events

```python
from PlayerEvents import g_playerEvents

g_playerEvents.onInventoryResync += handler
g_playerEvents.onDossiersResync += handler
g_playerEvents.onStatsResync += handler
```

## Items Cache Sync Events

```python
itemsCache.onSyncStarted += handler
itemsCache.onSyncCompleted += handler
itemsCache.onSyncFailed += handler
itemsCache.onPMSyncCompleted += handler
```

Typical post-progression diff check:

```python
def _onSyncCompleted(self, _, diff):
    if self.intCD in diff.get(GUI_ITEM_TYPE.VEH_POST_PROGRESSION, {}):
        self._onPostProgressionUpdate()
```

## Client Update Manager

Key-based callback pattern:

```python
from gui.ClientUpdateManager import g_clientUpdateManager

g_clientUpdateManager.addCallbacks({
    'inventory': self._onInventoryUpdate,
    'stats.unlocks': self._onUpdateUnlocks,
    'cache.vehsLock': self._onLocksUpdate,
    'groupLocks': self._onRotationUpdate,
})

g_clientUpdateManager.removeObjectCallbacks(self)
```

## A Listener That Raises Stops The Ones Behind It

`Event.Event` iterates a snapshot, logs a listener failure, and then **re-raises** it. Our handlers
share these events with the client's own, and subscription order decides who runs first, so an
exception escaping a mod handler can stop a Wargaming handler that was going to run next. Wrap
every handler body. `Event.SafeEvent` isolates failures instead, and the two are not
distinguishable by name — check the type before relying on either.

The full comparison of `Event`, `SafeEvent`, `SynchronousEvent`, `ContextEvent` and the GUI event
bus is upstream in [event-buses](https://modding.wot-tools.dev/event-buses.html). Subscribe and
unsubscribe order, handler identity and teardown are in
[hooks-events](https://modding.wot-tools.dev/hooks-events.html). See
[The Upstream Modding Guide](upstream-guide.md).

## Notes

- **`g_currentVehicle` throws your subscription away on every lobby teardown.** It extends
  `_CachedVehicle`, whose `destroy()` calls `self._eManager.clear()` — that empties `onChanged`
  and `onChangeStarted` for *every* listener, mods included, and the singleton is then re-`init()`ed
  for the next lobby. A handler attached once at mod load is silently gone afterwards, so
  subscribe on each hangar build rather than behind a "bound once" latch. `Event.__iadd__`
  ignores a delegate it already holds, so re-binding is free; `x not in event` works too, since
  `Event` subclasses `list`, and is worth logging when it fires.
  - The failure is quietly asymmetric and easy to misread: `g_playerEvents` survives, so
    inventory-driven refreshes keep working while vehicle-switch refreshes stop. The symptom
    reads as "switching tanks doesn't update, but touching an item does".
  - Where one exists, a hook owned by the view is sturdier than any subscription:
    `LoadoutPresenter._updateAmmunitionGroupsController` fires on tank switch, setup switch and
    item install, and cannot outlive or fall behind the panel it belongs to.
- **A subscription's own expiry timestamp passing does not mean the client knows it ended.**
  The client only learns premium ended when the server pushes a new premium mask, so the
  header view model keeps reporting `state=Active` past `expiryTime`. Measured live on EU
  2.3.1.0: **48 seconds** between the expiry timestamp and the
  `{'premium': {'premMask': 0, ...}}` diff landing — and the server rewrote the expiry to the
  moment it processed the change rather than the original time. Anything counting down to a
  subscription's end has to hold at zero across that gap; handing the label back at zero
  repaints it from the state captured while the subscription was still running.
- Prefer explicit unsubscribe paths in reverse order during shutdown.
- Treat sync callbacks as noisy and diff-driven; filter them down to the specific GUI item types or cache keys you actually need.
- Early transition events often arrive before every dependent object is ready, so keep guards around vehicle and preview state.
- `g_currentVehicle.onChanged` only fires on a vehicle *switch*. It is not enough to
  follow server-confirmed changes to the selected vehicle (a research, purchase or
  unlock): those arrive as an items-cache sync, so the UI silently keeps showing the
  pre-change state until the player switches vehicles. Subscribe to
  `itemsCache.onSyncCompleted(updateReason, invalidItems)` as well
  (`ItemsCache.__invalidateData`/`__invalidateFullData` fire it with those two args).
  Filtering it is optional if the resulting update is coalesced to the next tick and
  exits early while the UI is hidden — correctness is easier to keep than a diff filter.
- **A full account sync runs on every return to the garage, and an inventory diff can land inside it.** Measured on EU 2.3.1.3 (client 2.3.1.10158) across one session: `__runItemsCacheSync` took 0.6 to 0.9 seconds for 13 of its 17 runs, and 5 to 7 seconds for the other four. `g_playerEvents.onClientUpdated` keeps firing throughout, so anything that rebuilds from the items cache on a client update can read a half-filled one. What comes back is not an error. It is items whose unsynced parts are missing.
  - `ItemsRequester.getItems` logs `Trying to create fitting item type N when requesters are not fully synced` for such a read, once per item type per sync — `request()` clears the record — so a session logs far fewer notices than it makes early reads.
  - The gate is `ItemsRequester.__fittingItemRequesters`, a set of five: inventory, stats, shop, vehicle rotation and recycle bin. The message re-derives a *different*, nine-requester list for its text alone, so it names requesters the gate never tested. In the measured case the gate tripped on `RecycleBinRequester` while the text also named Dossier, Goodies, Ranked and BattleRoyale. Read the list as "something is unsynced", not as the cause.
  - `ItemsRequester.isSynced()` asks a wider question: fourteen requesters, including epic meta game, gift system, anonymizer and game restrictions. It is safe to gate on, but it holds a view back for requesters that no fitting item reads.
  - What works: gate the read on the same five the client gates on, and let `itemsCache.onSyncCompleted` deliver the refresh that was held back, rather than dropping it. See `collector.requesters_synced` and `window_inject.refresh` in directives-helper.
  - `onSyncCompleted` is a safe place to land the held-back refresh, and it is later than it looks. Measured across four garage returns: `__runItemsCacheSync elapsed` logged at 15:08:29.080 while `onSyncCompleted` reached the mod at 15:08:33.279 — over four seconds after the sync the line reports. The catch-up therefore runs well clear of the sync, not on its heels.
  - Verified on four returns to the garage: the guard read the account as unsynced each time, held one refresh each time, and the client logged no notice. In every case the diff came from another mod claiming a pet gift during lobby init, roughly 0.7 seconds into the sync.
- **A torn-down wulf view model keeps accepting updates, and the client never frees it.** A mod that keeps its own list of attached view models cannot learn from the list when a view dies. Setting a property on a model whose view was destroyed by a battle does not raise, so an except-branch that drops the model on failure never runs: measured on EU 2.3.1.3, a session that attached 27 models dropped none.
  - Holding those models weakly does not help either. With a `weakref.WeakSet` the count still climbed 1 to 12 across five lobby entries, which proves the mod's own list was never what kept them alive — something on the client side retains every one for the life of the session. Hold them strongly and let the list grow: a weak reference prunes nothing here, and it trades a measured, harmless leak for the risk of a model disappearing while it is still in use, which fails silently.
  - The practical cost is small and worth measuring before chasing it: the payload is built once per refresh whatever the list holds, and the extra work is one ignored property set per dead model.
- If the hangar ammo panel blanks after an action, the cause is the
  stale-`InteractingItem` copy (see the loadout-panel section below) — a
  post-progression change the panel renders from, made without refreshing its
  vehicle copy. It looks identical to a focus bug; it isn't. Fix it by refreshing
  the panel after the change lands, not by holding off the overlay's own rebuild.
  - History worth keeping: this symptom was first (wrongly) blamed on rebuilding
    the overlay's marker sprites while a modal confirm dialog was up — the theory
    being that destroying sprites during/just-after the dialog corrupts WG's focus
    stack. A "defer the rebuild until the dialog closes and settles" guard was built
    and then removed, because with it in place (verified by log) the rebuild landed
    well clear of the dialog and the panel *still* blanked — proving the rebuild
    timing was never the cause. If a focus-corruption symptom ever shows up that is
    genuinely tied to rebuilding under a modal (distinct from the stale copy), that
    guard is the approach to revive; there's no evidence it's needed today.

## Refreshing The Hangar Bottom Bar (Loadout Panel) After A Server-Side Change

Verified live on EU 2.3 while wiring the loadout-switch toggle; implementation
in `mods/research-progress-bar/src/zanju_rpb/actions.py`.

The 2.x hangar bottom bar (crew / modules / directives / ammunition /
consumables, with the loadout switches and their status dots) is
`gui.impl.lobby.hangar.presenters.loadout_presenter.LoadoutPresenter` plus its
child presenters — NOT the classic `ammunition_panel` view, whose refresh
hooks (`AmmunitionInjectEvent.INVALIDATE_INJECT_VIEW`, its
`g_currentVehicle.onChanged` full update) fire into nothing in this hangar.

Why it never refreshes in place: all these presenters render from an
`InteractingItem` (`gui.impl.lobby.tank_setup.interactors.base`) holding a
vehicle COPY made when the panel loaded. `LoadoutPresenter.__onVehicleChanged`
only rebuilds that copy when the vehicle actually changes
(`needToRecreate = intCD differs or item dead`); a same-vehicle
`g_currentVehicle.onChanged` keeps the stale copy — raising the event
repeatedly just re-reads stale data (and re-renders the whole hangar).

Working refresh recipe, scoped to the bar:

1. Wait until the changed state is actually READABLE. An item-action's success
   code returns fast (~0.3s), but the inventory diff carrying the new state
   arrives with a later batched server sync (observed ~0.1s up to many
   seconds). Poll the readable state, re-resolving `g_currentVehicle.item`
   each tick — itemsCache can REPLACE the gui item instance when the diff
   lands, so a captured reference can stay stale forever.
2. Swap a fresh copy into the live `InteractingItem` (mirror WG's
   `__createVehicleCopy`: `items.getVehicleCopy(current)` + battle-abilities
   sync), found via `gc.get_objects()` isinstance scan (fine at click
   frequency).
3. Fire `wrapper.onItemUpdated(None)`: `LoadoutPresenter.__onItemUpdated`
   pushes the fresh copy into its ammunition groups controller
   (`updateVehicle` + `updateGroupsModels` → `_setupStates`), rewriting the
   switch models without touching the rest of the hangar.

Note: swapping the copy discards un-applied draft edits in the bar (same as a
vehicle re-selection).

**This refresh is mandatory after every post-progression change made from the
hangar, not an optional nicety.** The panel does not merely look stale without it —
it renders from a vehicle copy that no longer matches the real vehicle's
post-progression state and **blanks entirely until a vehicle change**. A field-mod
research or dual-modification pick done from an overlay (rather than from WG's
field-mods screen, where the hangar panel is not live) hits exactly this. Symptom
to recognise: the ammo panel disappears and only a vehicle switch brings it back —
that is the stale-`InteractingItem` signature, *not* a focus or timing problem.

Each change needs its own readable, server-confirmed value to wait on, since the
action's success code returns before the diff lands:

- loadout switch: the disabled-switch state (see
  `_resolve_post_progression_setup_switch_active`).
- second slot category: `items.inventory.getDynSlotTypeID(vehIntCD)` (0 when
  unset). This is the value `RoleSlotModItem.__applyDynamicSlotCategory` derives
  its displayed category from, so it is exactly what the panel re-reads.
- field-mod research / dual pick: a snapshot of `pp.getState(True)` — `unlocks`
  grows on a research, `pairs` changes on a pick, so comparing both against a
  pre-action baseline covers either. Take the baseline right after dispatching:
  `doAction` returns immediately (verified: the confirm dialog loads ~4ms after the
  click, while the diff lands seconds later when the player confirms), so the
  baseline is genuinely pre-purchase. Allow a wait long enough to outlast the
  player reading that dialog, and skip the refresh if the change never lands (a
  cancelled dialog leaves nothing stale to fix).

Performance: the gc scan and WG's group-model rebuild each cause a small
main-thread hitch. Cache the found wrappers between uses (they survive vehicle
changes — LoadoutPresenter reuses them via `setItem`; liveness =
`getItem() is not None and len(wrapper.onItemUpdated) > 0`, since WG's `Event`
subclasses `list` and a finalized presenter tree leaves it empty) and pre-warm
the cache at click time so the scan merges into the game's own click freeze
instead of stacking a second one. The rebuild cost itself is WG's — their own
UI freezes the same way on this update.
