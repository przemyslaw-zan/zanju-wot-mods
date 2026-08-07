"""Write-side actions for clickable progress bar markers.

Counterpart to collector.py, which only reads. Each public entry point resolves the
currently selected vehicle and starts WG's own research flow, which shows the game's
native confirmation dialog before spending anything. The client's regular sync events
then refresh the bar. Every path is guarded so a failure degrades to opening WG's
native screen for that item -- never a raise back into the Scaleform view and never
a silent spend.

Symbols verified against the decompiled EU client (the game's own context-menu
"Research" handler uses the same path):

  * Tech-tree research: gui.shared.gui_items.items_actions.factory.doAction(
    UNLOCK_ITEM, itemCD, UnlockProps). UnlockItemAction runs WG's
    UnlockItemConfirmator dialog plugin before unlocking, and falls back to the
    exchange-XP dialog when even vehicle XP + free XP is short.
  * Field modifications: factory.doAction(PURCHASE_POST_PROGRESSION_STEPS, vehicle,
    [step_id]) -- WG's confirm-then-research chain (AsyncGUIItemAction._confirm shows
    the PostProgressionResearch dialog; only a confirmed dialog runs the purchase).
  * Loadout-switch toggle (essentials / auxiliary): factory action
    SWITCH_PREBATTLE_AMMO_PANEL_AVAILABILITY(vehicle, group_id, enabled) -- the same
    call WG's field-mods screen makes (post_progression_cfg_component
    ._onPrebattleSwitchToggleClick). Free, so it applies without any dialog.
  * Module buy-and-mount (offered after a module research lands):
    BuyAndInstallWithOptionalSellItemAction(moduleCD, vehicleCD).doAction() -- built
    directly because the factory's BUY_AND_INSTALL_* constants are not registered in
    its action map. Its @adisp_process doAction runs BuyAndInstallItemProcessor with
    skipConfirm=False (the IGUIItemAction default), so its BuyAndInstallConfirmator
    shows showBuyModuleDialog (BuyModuleDialogView) as the confirm step -- the
    buy-and-mount popup -- and only spends if the player confirms. WG's action
    rejects non-modules, so vehicles never reach it. The *WithOptionalSell* subclass
    is required for the popup's "sell previous module" checkbox to be honoured; the
    plain BuyAndInstallItemAction discards the dialog result and never sells.

BigWorld scripting uses Python 2.7. Avoid Python-3-only syntax.
"""
from __future__ import print_function, unicode_literals

import logging

import BigWorld
from CurrentVehicle import g_currentVehicle
from helpers import dependency
from skeletons.gui.shared import IItemsCache

from . import collector as _collector_api
from . import panel_watch
from .constants import (
    MARKER_CLICK_ACTION_FIELD_MOD,
    MARKER_CLICK_ACTION_FIELD_MOD_PICK,
    MARKER_CLICK_ACTION_FIELD_MOD_SELECT,
    MARKER_CLICK_ACTION_FIELD_MOD_TOGGLE,
    MARKER_CLICK_ACTION_RESEARCH,
    MARKER_CLICK_ACTION_UPGRADES,
)

_logger = logging.getLogger('zanju.researchprogressbar.actions')

# The server batches the inventory diff carrying a toggled switch state: the
# action's success code returns in well under a second, while the diff lands
# seconds later (observed >2s). Poll the readable state until it flips.
_HANGAR_REFRESH_POLL_INTERVAL = 0.3
_HANGAR_REFRESH_MAX_WAIT = 15.0
# Research / pair-pick sit behind a confirm dialog the player may read for a while,
# so their wait has to outlast that, not just the server round-trip.
_POST_PROGRESSION_REFRESH_MAX_WAIT = 120.0
# After a module research is started, how long to keep waiting for it to land before
# offering the buy-and-mount popup -- must outlast the player reading the research
# confirm dialog, and gives up quietly if they cancel it.
_MODULE_RESEARCH_BUY_MAX_WAIT = 120.0

# Live InteractingItem wrappers backing the hangar loadout bar, cached between
# toggles. The gc scan that finds them is the mod's main share of the refresh
# freeze, so it runs at click time (merging into the game's own click freeze)
# and only when the cache holds no live wrapper. The hangar recreates the
# wrappers e.g. when reloading after a battle; dead ones are pruned on use.
_loadout_wrapper_cache = []


def _execute_marker_click_action(action_kind, action_id, action_extra=None, on_state_changed=None):
    """Dispatches a marker click coming from the Scaleform view.

    `action_extra` is a second id only some kinds need (the pick action's chosen
    modification id); it is ignored for the others.
    """
    _logger.info('Marker click received: kind=%r id=%r extra=%r', action_kind, action_id, action_extra)
    try:
        action_id = int(action_id)
    except Exception:
        _logger.warning('Ignoring marker click with invalid id: %r', action_id)
        return

    if action_kind == MARKER_CLICK_ACTION_RESEARCH:
        _research_unlock(action_id)
    elif action_kind == MARKER_CLICK_ACTION_FIELD_MOD:
        _unlock_field_mod(action_id)
    elif action_kind == MARKER_CLICK_ACTION_FIELD_MOD_TOGGLE:
        _toggle_field_mod_feature(action_id, on_state_changed)
    elif action_kind == MARKER_CLICK_ACTION_FIELD_MOD_PICK:
        try:
            modification_id = int(action_extra)
        except Exception:
            _logger.warning('Ignoring pair pick with invalid modification id: %r', action_extra)
            return
        _pick_field_mod_pair(action_id, modification_id)
    elif action_kind == MARKER_CLICK_ACTION_FIELD_MOD_SELECT:
        _select_field_mod_slot(on_state_changed)
    elif action_kind == MARKER_CLICK_ACTION_UPGRADES:
        _open_upgrades_screen()
    else:
        _logger.warning('Ignoring marker click with unknown kind: %r', action_kind)


def _select_field_mod_slot(on_state_changed=None):
    """Opens WG's second-slot-category picker (SelectSlotSpecDialog) for the vehicle.

    WG's own field-mods screen reaches this via the SET_EQUIPMENT_SLOT_TYPE action:
    its _confirm shows select_slot_spec_dialog.showDialog(vehicle) and, on a valid
    pick, its _action applies the chosen slot type. Running the action here opens the
    same modal directly from the bar.

    Run as an async action so a confirmed pick (rather than a cancelled dialog) is
    distinguishable: the hangar loadout bar no more re-renders the new category on
    its own than it does a toggled loadout switch, so it needs the same refresh once
    the pick lands.
    """
    vehicle = _get_current_vehicle()
    if vehicle is None:
        return

    try:
        from adisp import adisp_process
        import gui.shared.gui_items.items_actions.factory as actions_factory

        previous_slot_id = _resolve_dyn_slot_type_id(vehicle)

        @adisp_process
        def _run_select():
            action = actions_factory.getAction(actions_factory.SET_EQUIPMENT_SLOT_TYPE, vehicle)
            result = yield actions_factory.asyncDoAction(action)
            _logger.info('Slot select: action finished, result=%r', result)
            if result:
                _refresh_hangar_when_state_lands(
                    vehicle,
                    _resolve_dyn_slot_type_id,
                    lambda slot_id: slot_id != previous_slot_id,
                    'slot category',
                    on_state_changed,
                )

        _run_select()
        # Pre-warm the wrapper cache while the game is already busy opening the
        # dialog, so the later refresh does not add its own gc-scan freeze.
        _get_loadout_wrappers()
    except Exception:
        _logger.exception('Marker click slot-spec select failed')


def _read_post_progression_snapshot(vehicle):
    """A comparable snapshot of the vehicle's post-progression state.

    Covers both flows the hangar loadout panel renders from: researching a step
    grows `state.unlocks`, and picking a dual modification rewrites `state.pairs`
    (the two halves of the raw per-vehicle post-progression record). One predicate
    -- "the snapshot changed" -- therefore serves research and pair picks alike.

    Returns None when unreadable, which callers treat as "not landed yet".
    """
    try:
        pp = getattr(vehicle, 'postProgression', None)
        if pp is None:
            return None
        state = pp.getState(True)
        unlocks = frozenset(getattr(state, 'unlocks', ()) or ())
        pairs = getattr(state, 'pairs', None) or {}
        return unlocks, tuple(sorted(pairs.items()))
    except Exception:
        _logger.exception('Failed to read the post-progression snapshot')
        return None


def _refresh_loadout_bar_when_post_progression_lands(vehicle, what):
    """Refreshes the hangar loadout panel once a field-mod change is readable.

    The panel renders from an InteractingItem holding a vehicle COPY, and nothing
    rebuilds that copy for the same vehicle (see _refresh_hangar_loadout_bar). A
    field-mod research or pair pick changes the very post-progression state the
    panel's loadout is derived from, so leaving the copy stale leaves the panel
    inconsistent with the real vehicle -- it blanks until a vehicle change. The
    toggle path has always refreshed for this reason; research and pair picks
    need the same treatment.

    Nothing is refreshed if the change never lands (a cancelled confirm dialog):
    there is no stale copy to fix in that case.
    """
    baseline = _read_post_progression_snapshot(vehicle)
    _refresh_hangar_when_state_lands(
        vehicle,
        _read_post_progression_snapshot,
        lambda snapshot: snapshot is not None and snapshot != baseline,
        what,
        refresh_on_timeout=False,
        # These run behind a confirm dialog the player may read for a while, so the
        # wait has to outlast that rather than the toggle's instant round-trip.
        max_wait=_POST_PROGRESSION_REFRESH_MAX_WAIT,
    )
    # Pre-warm the wrapper cache while the game is already busy with the click, so
    # the later refresh does not add its own gc-scan freeze.
    _get_loadout_wrappers()


def _resolve_dyn_slot_type_id(vehicle):
    """The vehicle's selected second-slot ("dynamic slot") type id, 0 when unset.

    Inventory-backed and server-confirmed -- RoleSlotModItem derives the category it
    displays from exactly this value (__applyDynamicSlotCategory looks up
    items.inventory.getDynSlotTypeID(vehTypeCD)), so it changes when the pick lands.
    """
    try:
        items = dependency.instance(IItemsCache).items
        return items.inventory.getDynSlotTypeID(vehicle.intCD)
    except Exception:
        _logger.exception('Failed to read the dynamic slot type id')
        return None


def _pick_field_mod_pair(step_id, modification_id):
    """Picks dual-modification `modification_id` on post-progression step `step_id`
    via WG's own pair-purchase flow.

    Goes through the items-actions factory PURCHASE_POST_PROGRESSION_PAIR action,
    whose _confirm shows WG's pair-modification dialog naming the choice; only a
    confirmed dialog purchases. The pick is free, but the confirm still names the
    modification so a mis-click (e.g. right-click meant for the other option) is
    catchable. On any failure, fall back to opening WG's field-mods screen.
    """
    vehicle = _get_current_vehicle()
    if vehicle is None:
        return

    try:
        import gui.shared.gui_items.items_actions.factory as actions_factory
        actions_factory.doAction(
            actions_factory.PURCHASE_POST_PROGRESSION_PAIR,
            vehicle,
            int(step_id),
            int(modification_id),
        )
        _refresh_loadout_bar_when_post_progression_lands(vehicle, 'pair modification pick')
    except Exception:
        _logger.exception(
            'Marker click pair pick failed for step %s mod %s', step_id, modification_id,
        )
        _open_field_mods_screen(vehicle)


def _research_unlock(intcd):
    """Researches tech-tree item `intcd` for the selected vehicle via WG's own flow."""
    vehicle = _get_current_vehicle()
    if vehicle is None:
        return

    try:
        row = _find_unlock_row(vehicle, intcd)
        if row is None:
            _logger.warning(
                'Marker click: %s is not an available unlock; opening research screen', intcd,
            )
            _open_research_screen(vehicle)
            return
        if not _start_unlock_action(vehicle, intcd, row):
            _open_research_screen(vehicle)
            return
        # Modules only: once the research actually lands, follow it with WG's own
        # buy-and-mount popup so the player can purchase and fit it right away.
        # Vehicles are researched only -- buying a vehicle is left to the player.
        if _collector_api._is_vehicle_module_unlock(intcd):
            _offer_buy_and_mount_after_module_research(vehicle, intcd)
    except Exception:
        _logger.exception('Marker click research failed for %s', intcd)
        _open_research_screen(vehicle)


def _offer_buy_and_mount_after_module_research(vehicle, intcd):
    """Waits for a just-started module research to land, then opens WG's buy-and-mount
    popup for that module.

    The unlock action returns as soon as its confirm dialog is shown; the module is
    only researched once the player confirms and the server round-trip lands (seconds
    later), so poll the unlock state and act on the flip. If the player cancels the
    confirm dialog the research never lands and the wait just times out -- no popup,
    nothing bought.
    """
    vehicle_intcd = getattr(vehicle, 'intCD', None)
    poll_state = {'elapsed': 0.0}

    def _poll():
        current_vehicle = _get_current_vehicle()
        if current_vehicle is None or getattr(current_vehicle, 'intCD', None) != vehicle_intcd:
            _logger.info('Buy offer: vehicle changed before module %s researched; stopping', intcd)
            return
        if _is_item_unlocked(intcd):
            _logger.info('Buy offer: module %s researched after %.1fs; opening buy-and-mount dialog',
                         intcd, poll_state['elapsed'])
            _open_buy_and_install_dialog(intcd, vehicle_intcd)
            return

        poll_state['elapsed'] += _HANGAR_REFRESH_POLL_INTERVAL
        if poll_state['elapsed'] >= _MODULE_RESEARCH_BUY_MAX_WAIT:
            _logger.info('Buy offer: module %s not researched after %.1fs; no popup',
                         intcd, poll_state['elapsed'])
            return
        BigWorld.callback(_HANGAR_REFRESH_POLL_INTERVAL, _poll)

    BigWorld.callback(_HANGAR_REFRESH_POLL_INTERVAL, _poll)


def _is_item_unlocked(intcd):
    """Whether tech-tree item `intcd` is now researched (in the account unlock set)."""
    try:
        items = dependency.instance(IItemsCache).items
        return int(intcd) in items.stats.unlocks
    except Exception:
        _logger.exception('Failed to read unlock state for %s', intcd)
        return False


def _open_buy_and_install_dialog(intcd, vehicle_intcd):
    """Opens WG's buy-and-mount popup (BuyModuleDialogView) for module `intcd`.

    The action builds BuyAndInstallItemProcessor with skipConfirm=False (the
    IGUIItemAction default), whose confirm step is showBuyModuleDialog -- the popup
    that lets the player buy and mount the module or cancel. Nothing is spent unless
    they confirm there, and the action rejects anything that is not a vehicle module
    (a second guard behind our module-only gate). doAction is @adisp_process, so
    calling it fires the flow directly.

    Use the *WithOptionalSell* subclass, not the plain BuyAndInstallItemAction: the
    popup carries a "sell previous module" checkbox, and only this subclass acts on
    it. Its doAction captures the currently installed module first, then reads the
    dialog result for AUTO_SELL_KEY ('sellPreviousModule') and runs ModuleSeller on
    the replaced module. The base class discards that result, so the box appears to
    be ignored -- the old module is silently kept.

    The factory's BUY_AND_INSTALL_AND_SELL_ITEM / BUY_AND_INSTALL_ITEM constants are
    not registered in its action map (doAction there just logs "Action type is not
    found"), so build the action directly -- the same object getAction would
    construct: (itemCD, rootCD).
    """
    try:
        from gui.shared.gui_items.items_actions.actions import (
            BuyAndInstallWithOptionalSellItemAction,
        )
        BuyAndInstallWithOptionalSellItemAction(int(intcd), int(vehicle_intcd)).doAction()
    except Exception:
        _logger.exception('Failed to open buy-and-mount dialog for module %s', intcd)


def _unlock_field_mod(step_id):
    """Researches post-progression step `step_id` via WG's confirm-and-research flow."""
    vehicle = _get_current_vehicle()
    if vehicle is None:
        return

    try:
        import gui.shared.gui_items.items_actions.factory as actions_factory
        actions_factory.doAction(
            actions_factory.PURCHASE_POST_PROGRESSION_STEPS,
            vehicle,
            [int(step_id)],
        )
        _refresh_loadout_bar_when_post_progression_lands(vehicle, 'field mod research')
    except Exception:
        _logger.exception('Marker click field mod research failed for %s', step_id)
        _open_field_mods_screen(vehicle)


def _toggle_field_mod_feature(group_id, on_state_changed=None):
    """Toggles the loadout-switch feature `group_id` (essentials / auxiliary).

    Free and dialog-less by design -- WG's own field-mods screen applies it the
    same way. The current state is re-read at click time so a stale bar cannot
    double-toggle, and `on_state_changed` runs after the async action completes
    so the bar refreshes with the server-confirmed state.
    """
    vehicle = _get_current_vehicle()
    if vehicle is None:
        return

    try:
        from adisp import adisp_process
        import gui.shared.gui_items.items_actions.factory as actions_factory

        currently_active = _resolve_setup_switch_active(vehicle, group_id)
        _logger.info(
            'Toggle: group=%s currently_active=%s -> requesting %s',
            group_id, currently_active, not currently_active,
        )

        @adisp_process
        def _run_toggle():
            action = actions_factory.getAction(
                actions_factory.SWITCH_PREBATTLE_AMMO_PANEL_AVAILABILITY,
                vehicle,
                int(group_id),
                not currently_active,
            )
            result = yield actions_factory.asyncDoAction(action)
            _logger.info('Toggle: action finished, result=%r', result)
            if result:
                _refresh_hangar_when_state_lands(
                    vehicle,
                    lambda veh: _resolve_setup_switch_active(veh, group_id),
                    lambda active: active == (not currently_active),
                    'loadout switch state',
                    on_state_changed,
                )

        _run_toggle()
        # Pre-warm the wrapper cache while the game is already busy processing
        # the click, so the later refresh does not add its own gc-scan freeze.
        _get_loadout_wrappers()
    except Exception:
        _logger.exception('Marker click loadout-switch toggle failed for group %s', group_id)
        _open_field_mods_screen(vehicle)


def _refresh_hangar_when_state_lands(
    vehicle,
    read_state,
    has_landed,
    what,
    on_state_changed=None,
    refresh_on_timeout=True,
    max_wait=_HANGAR_REFRESH_MAX_WAIT,
):
    """Refreshes the hangar loadout bar once a server-side change is readable.

    An action's success code returns quickly, but the inventory diff carrying the
    new state arrives with a LATER batched server sync (observed from ~0.1s up to
    multiple seconds), so refreshing on a fixed delay can re-read the stale state.
    Poll `read_state` instead and refresh exactly when `has_landed` accepts what it
    returns, giving up after a generous cap. `what` only names the change in logs.
    """
    poll_state = {'elapsed': 0.0}
    vehicle_intcd = getattr(vehicle, 'intCD', None)

    def _poll():
        # Re-resolve the vehicle each tick: itemsCache can replace the gui item
        # instance when the sync lands, leaving the captured object stale.
        current_vehicle = _get_current_vehicle()
        if current_vehicle is None or getattr(current_vehicle, 'intCD', None) != vehicle_intcd:
            _logger.info('Refresh: vehicle changed while waiting for %s; stopping', what)
            return

        current_state = read_state(current_vehicle)
        if has_landed(current_state):
            _logger.info(
                'Refresh: %s landed as %r after %.1fs',
                what,
                current_state,
                poll_state['elapsed'],
            )
            _refresh_hangar_loadout_bar(current_vehicle)
            if callable(on_state_changed):
                on_state_changed()
            return

        poll_state['elapsed'] += _HANGAR_REFRESH_POLL_INTERVAL
        if poll_state['elapsed'] >= max_wait:
            if not refresh_on_timeout:
                # The change never landed (e.g. a cancelled confirm dialog), so the
                # panel's copy is still consistent -- nothing to refresh.
                _logger.info(
                    'Refresh: %s never landed after %.1fs; nothing to refresh',
                    what,
                    poll_state['elapsed'],
                )
                return
            _logger.warning(
                'Refresh: %s still reads %r after %.1fs; refreshing anyway',
                what,
                current_state,
                poll_state['elapsed'],
            )
            _refresh_hangar_loadout_bar(current_vehicle)
            return
        BigWorld.callback(_HANGAR_REFRESH_POLL_INTERVAL, _poll)

    BigWorld.callback(_HANGAR_REFRESH_POLL_INTERVAL, _poll)


def _refresh_hangar_loadout_bar(current_vehicle):
    """Refreshes the hangar bottom bar's loadout-switch state in place.

    The 2.x hangar bottom bar (crew / modules / directives / ammunition /
    consumables) is LoadoutPresenter and its child presenters, which all render
    from an InteractingItem holding a vehicle COPY made when the panel loaded.
    For the same vehicle no client event rebuilds that copy (only a real
    vehicle change does), so the loadout-switch state dots never refresh in
    place. The fix mirrors what the vehicle-change path does, but scoped to the
    bar: swap a fresh vehicle copy into the wrapper (built like WG's own
    __createVehicleCopy, battle abilities included) and fire the wrapper's
    onItemUpdated, whose LoadoutPresenter handler pushes the fresh copy into
    the ammunition groups controller and rewrites the switch models. This
    touches only the loadout bar, unlike g_currentVehicle.onChanged, which
    re-renders the whole hangar.

    The live wrappers come from the pre-warmed cache (see _get_loadout_wrappers);
    only wrappers holding the current vehicle are touched.
    """
    try:
        # Bracketing the repair is the point: this is the moment the panel is known to blank,
        # and the probe logs only on a change, so a line here means this call did it. The only
        # place the probe is allowed to look for panels, since it is already click frequency --
        # the same reason the wrapper scan below is affordable here.
        panel_watch.note_all('before loadout bar repair', _logger, discover=True)
        items = dependency.instance(IItemsCache).items
        refreshed = 0
        for wrapper in _get_loadout_wrappers():
            try:
                held_item = wrapper.getItem()
                if held_item is None or getattr(held_item, 'intCD', None) != current_vehicle.intCD:
                    continue
                fresh_copy = items.getVehicleCopy(current_vehicle)
                try:
                    fresh_copy.battleAbilities.setInstalled(*current_vehicle.battleAbilities.installed)
                    fresh_copy.battleAbilities.setLayout(*current_vehicle.battleAbilities.layout)
                except Exception:
                    _logger.exception('Failed to mirror battle abilities onto vehicle copy')
                wrapper.setItem(fresh_copy)
                wrapper.onItemUpdated(None)
                refreshed += 1
            except Exception:
                _logger.exception('Failed to refresh an InteractingItem wrapper')

        _logger.info('Refresh: refreshed %s loadout bar wrapper(s)', refreshed)
        panel_watch.note_all('after loadout bar repair', _logger)
    except Exception:
        _logger.exception('Failed to refresh hangar loadout bar')


def _get_loadout_wrappers():
    """Live InteractingItem wrappers of the hangar loadout bar, cached.

    A wrapper is live while its onItemUpdated event still has subscribers (WG's
    Event subclasses list, so emptiness means the owning presenter tree was
    finalized) and it still holds an item. Wrapper instances survive vehicle
    changes -- LoadoutPresenter reuses them via setItem -- so the gc scan only
    reruns when the hangar view was rebuilt.
    """
    live_wrappers = [w for w in _loadout_wrapper_cache if _is_live_loadout_wrapper(w)]
    if not live_wrappers:
        try:
            import gc
            from gui.impl.lobby.tank_setup.interactors.base import InteractingItem
            live_wrappers = [
                obj for obj in gc.get_objects()
                if isinstance(obj, InteractingItem) and _is_live_loadout_wrapper(obj)
            ]
            _logger.info('Refresh: gc rescan found %s live loadout wrapper(s)', len(live_wrappers))
        except Exception:
            _logger.exception('Failed to scan for loadout bar wrappers')
            live_wrappers = []

    _loadout_wrapper_cache[:] = live_wrappers
    return live_wrappers


def _is_live_loadout_wrapper(wrapper):
    try:
        return wrapper.getItem() is not None and len(wrapper.onItemUpdated) > 0
    except Exception:
        return False


def _resolve_setup_switch_active(vehicle, group_id):
    """The loadout switch's current on/off state, read live like the collector does."""
    pp = getattr(vehicle, 'postProgression', None)
    try:
        state = pp.getState(True)
    except Exception:
        _logger.exception('Failed to read post-progression state for toggle')
        state = None
    return _collector_api._resolve_post_progression_setup_switch_active(
        pp,
        state,
        vehicle,
        int(group_id),
    )


def _start_unlock_action(vehicle, intcd, row):
    """Starts WG's tech-tree unlock action. Returns False if a symbol was unreachable.

    `row` is the vehicle's own unlock-graph tuple (unlockIdx, xpCost, itemCD, required)
    from getUnlocksDescrs() -- the same shape collector.py reads.
    """
    try:
        from gui.Scaleform.daapi.view.lobby.techtree.settings import UnlockProps
        import gui.shared.gui_items.items_actions.factory as actions_factory
    except Exception:
        _logger.exception('WG research symbols unavailable for %s', intcd)
        return False

    try:
        unlock_idx, raw_xp_cost, required = row[0], row[1], row[3]
        raw_xp_cost = int(raw_xp_cost)
        effective_xp_cost, discount_percent = _resolve_effective_unlock_cost(intcd, raw_xp_cost)
        if _collector_api._resolve_unlock_item_type(intcd) == 'vehicle':
            _ensure_tech_tree_data_loaded()
        # UnlockProps(parentID, unlockIdx, xpCost, required, discount, xpFullCost):
        # xpCost is the effective (paid) cost. Vehicle unlocks must carry the blueprint
        # discount the bar showed, or WG validates against the full cost and raises the
        # exchange-XP dialog; modules must keep the raw cost with discount 0, or WG's
        # unlock validator rejects the request.
        props = UnlockProps(
            vehicle.intCD,
            int(unlock_idx),
            int(effective_xp_cost),
            set(required),
            int(discount_percent),
            raw_xp_cost,
        )
        actions_factory.doAction(actions_factory.UNLOCK_ITEM, intcd, props)
        return True
    except Exception:
        _logger.exception('Failed to start WG unlock action for %s', intcd)
        return False


def _ensure_tech_tree_data_loaded():
    """Loads WG's tech-tree data provider unless it already is.

    WG validates a VEHICLE unlock with g_techTreeDP.isNext2Unlock(), which walks the
    node graph the provider builds from the tech-tree XML -- it ignores the
    `required` set carried by UnlockProps (that path is only used for modules). The
    provider loads lazily, normally the first time the research screen opens, and an
    unloaded one has no nodes, so isNext2Unlock() reports False and the unlock is
    rejected with 'required_locked'. That made the first vehicle click of a session
    fail until the player had visited the research screen once.

    load() returns immediately once loaded, so the XML parse is paid at most once
    per session, and only when a vehicle (not a module) is actually being unlocked.
    """
    try:
        from gui.Scaleform.daapi.view.lobby.techtree.techtree_dp import g_techTreeDP
        g_techTreeDP.load()
    except Exception:
        _logger.exception('Failed to load the tech tree data provider before unlock')


def _resolve_effective_unlock_cost(intcd, raw_xp_cost):
    """Returns (effective_cost, discount_percent), blueprint-discounted for vehicles."""
    if _collector_api._resolve_unlock_item_type(intcd) != 'vehicle':
        return raw_xp_cost, 0

    try:
        items = dependency.instance(IItemsCache).items
    except Exception:
        _logger.exception('itemsCache unavailable for blueprint discount of %s', intcd)
        return raw_xp_cost, 0

    state = _collector_api._resolve_unlock_research_state(intcd, raw_xp_cost, items)
    blueprint_info = state.get('blueprint_info') or {}
    return (
        state.get('xp_cost', raw_xp_cost),
        blueprint_info.get('discount_percent') or 0,
    )


def _find_unlock_row(vehicle, intcd):
    """The (unlockIdx, xpCost, itemCD, required) row for `intcd`, or None."""
    try:
        for row in vehicle.getUnlocksDescrs():
            if row[2] == intcd:
                return row
    except Exception:
        _logger.exception('Failed to iterate unlock descriptors for %s', intcd)
    return None


def _get_current_vehicle():
    try:
        if not g_currentVehicle.isPresent():
            return None
        return g_currentVehicle.item
    except Exception:
        _logger.exception('Failed to resolve current vehicle for marker click')
        return None


def _open_research_screen(vehicle):
    if vehicle is None:
        return
    try:
        from gui.shared.event_dispatcher import showResearchView
        showResearchView(vehicle.intCD)
    except Exception:
        _logger.exception('Failed to open research screen')


def _open_field_mods_screen(vehicle):
    if vehicle is None:
        return
    try:
        from gui.shared.event_dispatcher import showVehPostProgressionView
        showVehPostProgressionView(vehicle.intCD)
    except Exception:
        _logger.exception('Failed to open post-progression screen')
        _open_research_screen(vehicle)


def _open_upgrades_screen():
    """Opens WG's Tier 11 upgrades overlay (the Vehicle Hub skill tree) for the
    current vehicle.

    Tier 11 upgrades are the vehicle skill tree, and its screen is a new overlay
    layered over the post-progression system -- NOT the plain post-progression
    (field-mods) view, which renders a broken variant of that system for skill-
    tree vehicles. WG's own showVehicleHubVehSkillTree(intCD) navigates to the
    vehicleHub/vehSkillTree view; the itemsCache arg is dependency-injected, so
    only intCD is needed. It self-guards on vehicle.postProgression
    .isVehSkillTree(), so it opens only for the skill-tree vehicles the upgrades
    markers appear on. The flat bar cannot represent the branching tree, so the
    click just opens that screen -- nothing is spent from the bar.
    """
    vehicle = _get_current_vehicle()
    if vehicle is None:
        return

    try:
        from gui.shared.event_dispatcher import showVehicleHubVehSkillTree
        showVehicleHubVehSkillTree(vehicle.intCD)
    except Exception:
        _logger.exception('Failed to open Tier 11 upgrades screen')
