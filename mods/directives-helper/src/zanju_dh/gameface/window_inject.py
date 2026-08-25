# -*- coding: utf-8 -*-
"""Attaches the directives window to the garage's Gameface document.

The window is plain HTML/JS running inside the game's own hangar document. Getting it there
means using `net.openwg.gameface`: its bootstrap runs in every Gameface document and loads
whatever a `ModInjectModel` on one of that document's SUB-views lists. We attach such a
model, plus our own data model (`zanjuDhWindow`) carrying the directive snapshot and the
remembered window state, which window.js reads.

Placement is collision-aware. `gf_mod_inject` always writes to the fixed field name
`ModInjectModel`, so two mods that pick the same sub-view silently clobber each other, last
writer wins. We hook several candidate hangar sub-views, attach to the first free one, and
then leave the others alone for the next mod -- see view_claim for why that last part is not
optional. The JS finds our data by scanning sub-views, so which candidate we land on does not
matter to it.

See docs/reference/gameface-mod-widgets.md for the wider set of rules this follows.
"""
from __future__ import print_function, unicode_literals

import logging

from frameworks.wulf import ViewModel

from .. import collector, config, loadout_panel, repair, route_gate, slot_gate, view_claim
from ..localization import get_text as _loc

_MODULE_URL = 'coui://gui/gameface/mods/zanju_directives/window.js'
_STYLE_URL = 'coui://gui/gameface/mods/zanju_directives/window.css'
_INJECT_NAME = 'zanju_dh_window'
_DATA_PROPERTY = 'zanjuDhWindow'
# The field gf_mod_inject always writes to; its presence means a mod already claimed the view.
_INJECT_FIELD = 'ModInjectModel'

# Hangar sub-views to try, most preferred first. All live in the persistent
# `mono/hangar/main` document, which loads once per garage session.
#
# The order is only a preference: the client decides which of these it builds first, and we
# attach to whichever free one reaches us first. Coexisting with other mods rests on attaching
# to exactly one of them, not on the order -- see view_claim.
_CANDIDATE_MODELS = (
    ('gui.impl.gen.view_models.views.lobby.hangar.main_menu_model', 'MainMenuModel'),
    ('gui.impl.gen.view_models.views.lobby.hangar.mode_state_model', 'ModeStateModel'),
    ('gui.impl.gen.view_models.views.lobby.hangar.vehicle_menu_model', 'VehicleMenuModel'),
)

_module_logger = logging.getLogger('zanju.directiveshelper')

# The view model class this mod attached to, so it never takes a second one. See view_claim.
_claimed_class = None

_patched = []
# Live data models, so a change in the depot or the selected tank can be pushed to whichever
# hangar views are currently carrying one. Entries are dropped as soon as one stops accepting
# updates, which is how a torn-down view leaves the list.
_models = []

# Visibility is the conjunction of three questions, each owned by the module that can answer it:
# does this mode offer directives at all (loadout_panel), is the garage what the player is
# actually looking at (route_gate), and does the tank in the garage have a directives slot
# (slot_gate). They are genuinely different -- the panel stays alive underneath a screen drawn
# over the garage and keeps answering yes, and it reports its mode's sections for every tank in
# that mode however few slots any one of them has -- which is why none can serve as another.
#
# All three are read live rather than cached here. An earlier version mirrored them into module
# globals updated from their callbacks, which meant the answer could be pushed from stale state
# by a caller that had not heard from one of them yet.


class _WindowDataModel(ViewModel):
    """Snapshot plus remembered window state, read by window.js."""

    def __init__(self, payload, state):
        self._payload = payload
        self._state = state
        super(_WindowDataModel, self).__init__(properties=9, commands=7)

    def _initialize(self):
        super(_WindowDataModel, self)._initialize()
        # The snapshot travels as JSON in a single string property: wulf arrays would need a
        # nested view model per row, and the window re-renders wholesale anyway.
        self._addStringProperty('snapshot', self._payload)
        self._addNumberProperty('x', self._state['x'] if self._state['x'] is not None else -1)
        self._addNumberProperty('y', self._state['y'] if self._state['y'] is not None else -1)
        self._addNumberProperty('viewportWidth', self._state['viewportWidth'])
        self._addNumberProperty('viewportHeight', self._state['viewportHeight'])
        self._addBoolProperty('folded', self._state['folded'])
        # Property indices are assigned in declaration order across every type, which is how
        # the setters below address them. This view is usually built before the loadout panel
        # has come up, so it commonly starts hidden and the panel's own arrival turns it on.
        self._addBoolProperty('visible', _should_be_visible())
        # Appended after `visible` on purpose: the indices above are addressed by number, so
        # inserting anything earlier would silently repoint every setter.
        self._addNumberProperty('width', self._state['width'])
        self._addBoolProperty('showUnowned', self._state['showUnowned'])
        # JS -> Python. `_addCommand` takes only the name and returns a Command; the handler
        # is bound to it with `+=` (it wraps an Event), which is how the game's own generated
        # view models declare theirs. A wulf command carries exactly one map argument.
        self.setPosition = self._addCommand('setPosition')
        self.setPosition += self.__onSetPosition
        self.setFolded = self._addCommand('setFolded')
        self.setFolded += self.__onSetFolded
        self.equip = self._addCommand('equip')
        self.equip += self.__onEquip
        self.toggleAutoResupply = self._addCommand('toggleAutoResupply')
        self.toggleAutoResupply += self.__onToggleAutoResupply
        self.setSize = self._addCommand('setSize')
        self.setSize += self.__onSetSize
        self.setShowUnowned = self._addCommand('setShowUnowned')
        self.setShowUnowned += self.__onSetShowUnowned
        self.buy = self._addCommand('buy')
        self.buy += self.__onBuy

    # Indices matching the declaration order in _initialize.
    _SNAPSHOT_INDEX = 0
    _VISIBLE_INDEX = 6
    _SHOW_UNOWNED_INDEX = 8

    def setSnapshot(self, payload):
        self._payload = payload
        self._setString(self._SNAPSHOT_INDEX, payload)

    def setVisible(self, visible):
        self._setBool(self._VISIBLE_INDEX, bool(visible))

    def setShowUnownedValue(self, value):
        self._setBool(self._SHOW_UNOWNED_INDEX, bool(value))

    def __onSetPosition(self, *args):
        arg = args[0] if args else None
        config.update(
            x=_map_get(arg, 'x'),
            y=_map_get(arg, 'y'),
            viewport_width=_map_get(arg, 'w'),
            viewport_height=_map_get(arg, 'h'),
        )

    def __onEquip(self, *args):
        arg = args[0] if args else None
        equip_directive(_map_get(arg, 'intCD'), _module_logger)

    def __onToggleAutoResupply(self, *args):
        toggle_auto_resupply(_module_logger)

    def __onSetSize(self, *args):
        arg = args[0] if args else None
        config.update(
            width=_map_get(arg, 'width'),
            viewport_width=_map_get(arg, 'w'),
            viewport_height=_map_get(arg, 'h'),
        )

    def __onSetShowUnowned(self, *args):
        arg = args[0] if args else None
        value = _map_get(arg, 'showUnowned')
        if value is None:
            return
        config.update(show_unowned=bool(value))
        # The listing itself changes, not just a style, so the snapshot has to be rebuilt.
        refresh(_module_logger)

    def __onBuy(self, *args):
        arg = args[0] if args else None
        offer_purchase(_map_get(arg, 'intCD'), _module_logger)

    def __onSetFolded(self, *args):
        arg = args[0] if args else None
        value = _map_get(arg, 'folded')
        if value is not None:
            config.update(folded=bool(value))


def _map_get(arg, key):
    """Read a key from the single map argument a wulf command carries.

    It may arrive as a plain dict or as a wrapped map exposing .get(); tolerate both, and
    treat anything unreadable as absent rather than raising inside a UI callback.
    """
    if isinstance(arg, dict):
        return arg.get(key)
    getter = getattr(arg, 'get', None)
    if callable(getter):
        try:
            return arg.get(key)
        except Exception:
            return None
    return None


def _build_payload(logger):
    """Snapshot plus its labels, as JSON for the window to render.

    The labels travel with the data so translation stays on the Python side, where the
    localization bundle lives; the JS only ever renders what it is handed.

    A snapshot with no tank in it is not an error and does not hide anything: the window is
    built well before the garage has finished assembling, so an empty first payload is the
    normal case, and every later refresh replaces it. Whether there is a vehicle at all is the
    loadout panel's answer, not this one's.
    """
    import json
    try:
        state = config.current()
        snapshot = collector.collect(logger, show_unowned=state['showUnowned'])
        snapshot['showUnowned'] = state['showUnowned']
        snapshot['labels'] = {
            'title': _loc('WINDOW_TITLE'),
            'equipment': _loc('CATEGORY_EQUIPMENT'),
            'crewImprove': _loc('CATEGORY_CREW_IMPROVE'),
            'crewGrant': _loc('CATEGORY_CREW_GRANT'),
            'sectionEmpty': _loc('LABEL_SECTION_EMPTY'),
            'autoResupply': _loc('LABEL_AUTO_RESUPPLY'),
            'resupplyWarning': _loc('LABEL_RESUPPLY_WARNING'),
            'showUnowned': _loc('LABEL_SHOW_UNOWNED'),
            'buyHint': _loc('LABEL_BUY_HINT'),
            'buyUnavailable': _loc('LABEL_BUY_UNAVAILABLE'),
        }
        return json.dumps(snapshot)
    except Exception:
        logger.exception('Failed to serialise the directives snapshot')
        return '{}'


def _is_claimed(model, logger):
    """True when another mod already attached its inject model to this view.

    There is no getter for a child model by name, but the native proxy serialises its field
    names, which is enough to spot the fixed field gf_mod_inject writes to.
    """
    try:
        return _INJECT_FIELD in '{0}'.format(model)
    except Exception:
        logger.exception('Failed to inspect a candidate view model')
        return False


def equip_directive(int_cd, logger):
    """Fit the directive with this intCD to the selected vehicle.

    Goes through the client's own action rather than writing the layout directly: the action
    validates, buys the directive if the depot is empty, shows the usual messages, and — most
    importantly — rebuilds the whole equipment layout correctly. Writing
    `inventory.setAndFillLayouts` by hand risks clearing the vehicle's consumables, since the
    raw layout it takes covers those too.
    """
    try:
        int_cd = int(int_cd)
    except (TypeError, ValueError):
        return

    try:
        from CurrentVehicle import g_currentVehicle
        if not g_currentVehicle.isPresent():
            return
        vehicle = g_currentVehicle.item
        if not slot_gate.has_directive_slot(vehicle):
            # The window checks this too, so it should not be on screen for such a tank at all.
            # The check runs again here because this is the last point before the client's own
            # processor, which does not refuse the request but corrupts the tank's stored layout
            # instead -- see slot_gate and issue #18.
            logger.warning(
                'The selected vehicle has no directives slot; not fitting directive %s', int_cd)
            return
        booster = _find_booster(vehicle, int_cd, logger)
        if booster is None:
            logger.warning('Directive %s is not available for this vehicle', int_cd)
            return

        # Clicking the directive that is already fitted takes it off again; the JS side just
        # reports which tile was clicked and lets this decide.
        removing = _is_installed(vehicle, int_cd)

        # A vehicle has two loadouts, each with its own directive slot. `battleBoosters.layout`
        # is the working set for the setup currently selected, which is also the one the
        # snapshot reports, so setting it here targets the loadout the player is looking at.
        logger.info(
            '%s directive %s in loadout %s',
            'Removing' if removing else 'Fitting', int_cd, _selected_setup_index(vehicle))
        # An empty layout slot is what the processor turns into "nothing fitted".
        vehicle.battleBoosters.setLayout(None if removing else booster)
        _install(vehicle, int_cd, logger)
    except Exception:
        logger.exception('Failed to fit directive %s', int_cd)


def offer_purchase(int_cd, logger):
    """Offer to buy a directive the player owns none of, through the game's own dialog.

    `showBattleBoosterBuyDialog` opens `BoosterBuyWindowView`: the client's purchase dialog for
    directives, with the price, a quantity selector and the auto-resupply toggle. Nothing is
    spent until the player accepts it there, so this mod never buys anything off a single click
    -- the same rule research-progress-bar follows for its own purchases.

    Falls back to the store page if the dialog cannot be started. That fallback only covers a
    failure to *start* it: the call is `wg_async`, so anything that goes wrong once the dialog
    is running surfaces in the client rather than here.
    """
    try:
        int_cd = int(int_cd)
    except (TypeError, ValueError):
        return

    try:
        from gui.shared.event_dispatcher import showBattleBoosterBuyDialog
        logger.info('Opening the purchase dialog for directive %s', int_cd)
        showBattleBoosterBuyDialog(int_cd)
        return
    except Exception:
        logger.exception(
            'Could not open the purchase dialog for directive %s; using the store page', int_cd)

    try:
        from gui import shop
        shop.showBattleBooster(
            itemId=int_cd, source=shop.Source.EXTERNAL, origin=shop.Origin.BATTLE_BOOSTERS)
    except Exception:
        logger.exception('Failed to open the store for directive %s', int_cd)


def toggle_auto_resupply(logger):
    """Flip the selected vehicle's automatic directive resupply.

    The setting is a bit in the vehicle's inventory settings, so it is changed the same way
    every other per-vehicle switch is: a settings processor that asks the server to rewrite
    the flag. The game's own control for it is the "Auto-resupply" checkbox on the directives
    tab of the tank setup screen, which drives this same processor.

    Its interactor there defers the request to the named `techMaintenance` adisp queue, which
    only the tank setup flow pumps; as with fitting a directive, we run the processor on our
    own adisp process instead so the request actually leaves the client.
    """
    try:
        from adisp import adisp_process
        from gui.shared.gui_items.processors.vehicle import VehicleAutoBattleBoosterEquipProcessor
        from CurrentVehicle import g_currentVehicle
        if not g_currentVehicle.isPresent():
            return
        vehicle = g_currentVehicle.item
        current = collector.auto_resupply(vehicle, logger)
        if current is None:
            # Unreadable rather than off; flipping it would be a guess at the current state.
            logger.warning('Auto-resupply state is unknown; leaving the setting alone')
            return
        target = not current

        @adisp_process
        def run():
            result = yield VehicleAutoBattleBoosterEquipProcessor(vehicle, target).request()
            logger.info('Auto-resupply set to %s: success=%s',
                        target, getattr(result, 'success', None))
            if getattr(result, 'userMsg', None):
                logger.info('Auto-resupply message: %s', result.userMsg)
            refresh(logger)

        logger.info('Turning auto-resupply %s', 'on' if target else 'off')
        run()
    except Exception:
        logger.exception('Failed to toggle auto-resupply')


def _install(vehicle, int_cd, logger):
    """Run the client's install processor for the vehicle's current directive layout.

    The higher-level `BUY_AND_INSTALL_BATTLE_BOOSTERS` action would be the tidier entry
    point, but its inner step runs on the named `techMaintenance` adisp queue, which is only
    pumped inside the game's own tank-setup flow: called from here it started and never
    finished, so nothing ever reached the server. Driving the processor through our own
    adisp process avoids that queue entirely.

    Skipping the action also means no purchase can happen by accident: the processor's
    validators simply fail when the directive is not already owned.
    """
    from adisp import adisp_process
    from gui.shared.gui_items.processors.vehicle import BuyAndInstallBattleBoostersProcessor

    @adisp_process
    def run():
        result = yield BuyAndInstallBattleBoostersProcessor(vehicle).request()
        success = getattr(result, 'success', None)
        logger.info('Directive %s install result: success=%s', int_cd, success)
        if getattr(result, 'userMsg', None):
            logger.info('Directive %s install message: %s', int_cd, result.userMsg)
        refresh(logger)

    run()


def _is_installed(vehicle, int_cd):
    try:
        installed = vehicle.battleBoosters.installed.getItems()
        return any(int(item.intCD) == int_cd for item in installed if item is not None)
    except Exception:
        return False


def _selected_setup_index(vehicle):
    """Index of the loadout currently selected, for the log line only."""
    try:
        return vehicle.battleBoosters.setupLayouts.layoutIndex
    except Exception:
        return '?'


def _find_booster(vehicle, int_cd, logger):
    from gui.shared.gui_items import GUI_ITEM_TYPE
    from gui.shared.utils.requesters.ItemsRequester import REQ_CRITERIA
    from helpers import dependency
    from skeletons.gui.shared import IItemsCache
    items_cache = dependency.instance(IItemsCache)
    items = items_cache.items.getItems(GUI_ITEM_TYPE.BATTLE_BOOSTER, REQ_CRITERIA.BATTLE_BOOSTER.ALL)
    for item in items.values():
        try:
            if int(item.intCD) == int_cd:
                return item
        except Exception:
            continue
    return None


def refresh(logger):
    """Rebuild the snapshot and push it to every live window model."""
    if not _models:
        return
    payload = _build_payload(logger)
    _push(lambda model: model.setSnapshot(payload), logger)


def _should_be_visible():
    return loadout_panel.is_visible() and route_gate.is_visible() and slot_gate.is_visible()


def _apply_visibility(logger):
    visible = _should_be_visible()
    _push(lambda model: model.setVisible(visible), logger)


def _push(action, logger):
    """Apply `action` to each live model, forgetting the ones that have been torn down."""
    for model in list(_models):
        try:
            action(model)
        except Exception:
            # A view that has gone away rejects updates; drop it rather than log on a timer.
            _forget(model)


def _forget(model):
    try:
        _models.remove(model)
    except ValueError:
        pass


def _on_panel_visibility(visible):
    # The value is ignored on purpose: _apply_visibility re-reads both sources, so a callback
    # can never push a decision made from one of them alone.
    _apply_visibility(_module_logger)


def _on_route_visibility(visible):
    _module_logger.info('Garage is the visible route: %s', visible)
    _apply_visibility(_module_logger)


def _on_panel_update():
    # The loadout bar re-read the vehicle, so what the window shows has changed with it. This
    # covers the selected tank and the selected setup, and keeps working after a lobby
    # teardown has emptied the events _bind_events subscribes to.
    #
    # This re-applies visibility as well: a different tank can decide whether the window
    # applies at all, and this hook is the one signal that survives a lobby teardown.
    _apply_visibility(_module_logger)
    refresh(_module_logger)


def _bind_events(logger):
    """Refresh on the things that change what the window shows.

    Called every time a hangar view is built rather than once per session, because the client
    throws our subscriptions away: `g_currentVehicle` clears its whole event manager in
    `destroy()`, which runs on every lobby teardown, so a handler attached once is silently
    gone afterwards -- vehicle changes stop refreshing the window while inventory changes,
    which ride a longer-lived event, carry on working.

    `Event.__iadd__` ignores a delegate it already holds, so re-binding costs nothing; the
    explicit membership test is only there to log when a subscription actually had to be
    replaced.
    """
    try:
        from PlayerEvents import g_playerEvents
        # The inventory diff carries both depot changes and the fitted directive.
        if _on_client_updated not in g_playerEvents.onClientUpdated:
            g_playerEvents.onClientUpdated += _on_client_updated
            logger.info('Subscribed to client updates')
    except Exception:
        logger.exception('Failed to subscribe to client updates; the window will not refresh')

    try:
        from CurrentVehicle import g_currentVehicle
        if _on_vehicle_changed not in g_currentVehicle.onChanged:
            g_currentVehicle.onChanged += _on_vehicle_changed
            logger.info('Subscribed to vehicle changes')
    except Exception:
        logger.exception('Failed to subscribe to vehicle changes')

    # The lobby state machine belongs to the lobby app, so it is a different object after every
    # teardown; `install` compares identity and only re-subscribes when it actually changed.
    route_gate.install(logger, _on_route_visibility)

    # The garage build is the earliest point where the account's inventory is there to read.
    # Version 1.0.1 could leave a tank recording a directive it cannot hold, and such a tank is
    # refused a battle until the record is cleared. `check` stops looking once it has seen a
    # clean garage, so this costs a call and nothing else for the rest of the session -- see
    # repair.py.
    repair.check(logger)


def _unbind_events(logger):
    try:
        from PlayerEvents import g_playerEvents
        g_playerEvents.onClientUpdated -= _on_client_updated
    except Exception:
        pass
    try:
        from CurrentVehicle import g_currentVehicle
        g_currentVehicle.onChanged -= _on_vehicle_changed
    except Exception:
        pass


def _on_client_updated(diff, *args):
    # Only an inventory change can affect what the window shows; every other diff (credits,
    # quests, ...) arrives constantly and would rebuild the snapshot for nothing.
    if isinstance(diff, dict) and 'inventory' not in diff:
        return
    refresh(_module_logger)


def _on_vehicle_changed(*args):
    # The new tank may have no directives slot, which hides the window rather than emptying it.
    _apply_visibility(_module_logger)
    refresh(_module_logger)


def install(logger):
    """Patch the candidate hangar views. Returns True when at least one was hooked."""
    if _patched:
        return True

    try:
        from openwg_gameface import gf_mod_inject
    except ImportError:
        logger.info(
            'net.openwg.gameface not found; the directives window is disabled '
            '(install the OpenWG Gameface library to enable it)'
        )
        return False

    config.load()
    # Patched here rather than when a hangar view appears: the panel's presenter may well load
    # before our view models do, and missing its arrival would leave the window hidden for the
    # rest of the session.
    loadout_panel.install(logger, _on_panel_visibility, _on_panel_update)
    # Almost certainly a no-op here -- the lobby app that owns the state machine does not exist
    # this early -- but it costs nothing and `_bind_events` retries on every hangar build.
    route_gate.install(logger, _on_route_visibility)

    for module_path, class_name in _CANDIDATE_MODELS:
        model_class = _import_model(module_path, class_name, logger)
        if model_class is None:
            continue
        _patch(model_class, gf_mod_inject, logger)

    if not _patched:
        logger.warning('No hangar view could be hooked; the directives window is disabled')
        return False

    logger.info('Directives window installed (%d candidate views)', len(_patched))
    return True


def _import_model(module_path, class_name, logger):
    try:
        module = __import__(module_path, globals(), locals(), [str(class_name)])
        return getattr(module, class_name)
    except Exception:
        logger.info('Hangar view %s.%s not found; skipping it', module_path, class_name)
        return None


def _patch(model_class, gf_mod_inject, logger):
    original = model_class._initialize

    def _initialize_with_window(self):
        global _claimed_class
        original(self)
        try:
            claim, _claimed_class = view_claim.decide(
                model_class, _is_claimed(self, logger), _claimed_class)
            if not claim:
                return
            gf_mod_inject(
                self,
                str(_INJECT_NAME),
                styles=[str(_STYLE_URL)],
                modules=[str(_MODULE_URL)],
            )
            data_model = _WindowDataModel(_build_payload(logger), config.current())
            self._addViewModelProperty(str(_DATA_PROPERTY), data_model)
            _models.append(data_model)
            _bind_events(logger)
            logger.info('Directives window attached to %s', model_class.__name__)
        except Exception:
            _claimed_class = None
            logger.exception('Failed to attach the directives window model')

    model_class._initialize = _initialize_with_window
    _patched.append((model_class, original))


def uninstall(logger):
    global _claimed_class
    _claimed_class = None
    _unbind_events(logger)
    loadout_panel.uninstall(logger)
    route_gate.uninstall(logger)
    del _models[:]
    while _patched:
        model_class, original = _patched.pop()
        try:
            model_class._initialize = original
        except Exception:
            logger.exception('Failed to restore %s._initialize', model_class.__name__)
