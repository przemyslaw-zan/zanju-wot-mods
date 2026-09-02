# -*- coding: utf-8 -*-
"""Attaches the campaign widgets to the garage's Gameface document.

The widgets are plain HTML/JS running inside the game's own hangar document. Getting them
there means using `net.openwg.gameface`: its bootstrap runs in every Gameface document and
loads whatever a `ModInjectModel` on one of that document's SUB-views lists. We attach such a
model, plus our own data model (`zanjuCtWidgets`) carrying the campaign snapshot, which
widgets.js reads.

The banners are fixed beside the garage's vehicle name block, so no position is persisted. The
one thing they send back is a click: the JS reports which campaign was clicked and which keys
were held with it, and Python either opens the client's own screen for that campaign's mission
(see navigation) or pauses or resets it (see mission_actions).

Placement is collision-aware. `gf_mod_inject` always writes to the fixed field name
`ModInjectModel`, so two mods that pick the same sub-view silently clobber each other, last
writer wins. We hook several candidate hangar sub-views, attach to the first free one, and
then leave the others alone for the next mod -- see view_claim for why that last part is not
optional. The JS finds our data by scanning sub-views, so which candidate we land on does not
matter to it.

See docs/reference/gameface-mod-widgets.md for the wider set of rules this follows.
"""
from __future__ import absolute_import, print_function, unicode_literals

import json
import logging

from frameworks.wulf import ViewModel

from .. import collector, held_keys, mission_actions, navigation, route_gate, view_claim
from . import card_window
from ..constants import LOGGER_NAME
from ..localization import get_text as _loc

_MODULE_URL = 'coui://gui/gameface/mods/zanju_campaigns/widgets.js'
_STYLE_URL = 'coui://gui/gameface/mods/zanju_campaigns/widgets.css'
_INJECT_NAME = 'zanju_ct_widgets'
_DATA_PROPERTY = 'zanjuCtWidgets'
# The field gf_mod_inject always writes to; its presence means a mod already claimed the view.
_INJECT_FIELD = 'ModInjectModel'

# Hangar sub-views to try, most preferred first. All live in the persistent
# `mono/hangar/main` document, which loads once per garage session.
#
# The order is only a preference: the client decides which of these it builds first, and we
# attach to whichever free one reaches us first. Coexisting with other mods rests on attaching
# to exactly one of them, not on the order -- see view_claim.
_CANDIDATE_MODELS = (
    ('gui.impl.gen.view_models.views.lobby.hangar.mode_state_model', 'ModeStateModel'),
    ('gui.impl.gen.view_models.views.lobby.hangar.vehicle_menu_model', 'VehicleMenuModel'),
    ('gui.impl.gen.view_models.views.lobby.hangar.main_menu_model', 'MainMenuModel'),
)

_module_logger = logging.getLogger(LOGGER_NAME)

# Last campaign count reported to the log, so the payload build can report when the answer
# changes without writing a line on every tank switch. `None` means nothing logged yet.
_last_logged_count = None

# Client strings this mod reads instead of shipping its own. Written as the keys themselves
# rather than through `gui.Scaleform.locale`, because that module holds these very strings and
# the key is the half worth reading here. Each one names the same thing the widget names:
#
# - the two condition group headings, which the game's own mission card prints in that exact
#   place, and the separator it prints between two conditions of an "or" group
# - the state a mission is in once its primary objective is met and its secondary one is not
_KEY_PRIMARY = '#personal_missions:detailedView/conditionslabel'
_KEY_SECONDARY = '#personal_missions:detailedView/conditionsFullylabel'
_KEY_OR = '#personal_missions:conditions/orGroup'
_KEY_IMPROVING = '#ingame_gui:statistics/tab/quests/status/increaseResult'

# The view model class this mod attached to, so it never takes a second one. See view_claim.
_claimed_class = None

_patched = []
# Live data models, so a change of tank or of mission progress can be pushed to whichever
# hangar views are currently carrying one.
#
# Entries accumulate, and that is left alone deliberately. Nothing here can tell when a view
# dies: a torn-down view model accepts updates and ignores them rather than refusing them, so
# the drop path in `_push` never runs. Holding them weakly does not help either, because the
# client keeps every model it built for the whole session, so the count climbs either way.
# Measured on EU 2.3.1.3 across this mod and the sibling directives mod, which shares the
# pattern. The cost is one ignored property set per dead entry, since the payload is built
# once per refresh whatever this list holds.
_models = []


class _WidgetsDataModel(ViewModel):
    """The campaign snapshot and whether to show it, read by widgets.js."""

    def __init__(self, payload):
        self._payload = payload
        # The counts reach the native view model, so they have to match what _initialize
        # actually adds: three properties, and two commands since the card window took its
        # hover reports through one of its own.
        super(_WidgetsDataModel, self).__init__(properties=3, commands=2)

    def _initialize(self):
        super(_WidgetsDataModel, self)._initialize()
        # The snapshot travels as JSON in a single string property: wulf arrays would need a
        # nested view model per row, and the widgets re-render wholesale anyway.
        self._addStringProperty('snapshot', self._payload)
        # Property indices are assigned in declaration order across every type, which is how
        # the setters below address them. This view is usually built before the lobby has
        # settled, so `visible` starts from whatever the route gate can answer at that point.
        self._addBoolProperty('visible', route_gate.is_visible())
        # Which modifier keys are held, as one string. Pushed on its own rather than folded
        # into the snapshot: a key change must not cost a rebuild of every card, and the
        # snapshot is far too big to resend for two booleans.
        self._addStringProperty('heldKeys', held_keys.text())
        # JS -> Python. `_addCommand` takes only the name and returns a Command; the handler
        # is bound to it with `+=` (it wraps an Event), which is how the game's own generated
        # view models declare theirs. A wulf command carries exactly one map argument.
        self.missionAction = self._addCommand('missionAction')
        self.missionAction += self.__onMissionAction
        # The hover card draws in a window of the mod's own, so the banners cannot open it with
        # CSS any more. They report which one the pointer is on, and where it sits.
        self.cardHover = self._addCommand('cardHover')
        self.cardHover += self.__onCardHover

    # Indices matching the declaration order in _initialize.
    _SNAPSHOT_INDEX = 0
    _VISIBLE_INDEX = 1
    _HELD_KEYS_INDEX = 2

    def setSnapshot(self, payload):
        self._payload = payload
        self._setString(self._SNAPSHOT_INDEX, payload)

    def setVisible(self, visible):
        self._setBool(self._VISIBLE_INDEX, bool(visible))

    def setHeldKeys(self, text):
        self._setString(self._HELD_KEYS_INDEX, text)

    def __onCardHover(self, *args):
        """The pointer entered or left a banner. An empty branch means it left."""
        arg = args[0] if args else None
        branch = _map_get(arg, 'branch')
        if not branch:
            _module_logger.debug('Hover left')
            card_window.hide(_module_logger)
            return
        _module_logger.debug('Hover on %s', branch)
        _show_card(branch, arg, _module_logger)

    def __onMissionAction(self, *args):
        """A banner was clicked. Which action it asks for depends on the keys held with it."""
        arg = args[0] if args else None
        branch = _map_get(arg, 'branch')
        if not branch:
            return
        action = _map_get(arg, 'action') or mission_actions.ACTION_OPEN
        if action == mission_actions.ACTION_OPEN:
            navigation.open_mission(branch, _module_logger)
            return

        # Resolved here rather than in `mission_actions`, which stays free of `collector` so
        # the two do not import each other. Resolved fresh on every click for the same reason
        # `navigation` does: the mission behind a banner can change between render and click.
        quest = collector.find_active_mission(branch, _module_logger)
        if quest is None:
            _module_logger.info('Campaign %s has no active mission to %s', branch, action)
            return
        mission_actions.perform(quest, action, _module_logger)


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
    """Snapshot plus its labels, as JSON for the widgets to render.

    The labels travel with the data so translation stays on the Python side, where the
    localization bundle lives; the JS only ever renders what it is handed.

    A snapshot with no campaigns in it is not an error and does not hide anything: the models
    are built well before the garage has finished assembling, so an empty first payload is the
    normal case, and every later refresh replaces it.
    """
    try:
        snapshot = collector.collect(logger)
        _log_payload_change(snapshot, logger)
        snapshot['labels'] = {
            'noMission': _loc('LABEL_NO_MISSION'),
            'paused': _loc('LABEL_PAUSED'),
            # `_client_text` here and below: the client's own words, which spare a
            # translator four strings and give every language the game ships.
            'primaryConditions': _client_text(_KEY_PRIMARY, logger),
            'secondaryConditions': _client_text(_KEY_SECONDARY, logger),
            'or': _client_text(_KEY_OR, logger),
            'lockedVehicles': _loc('LABEL_LOCKED_VEHICLES'),
            'vehicleLocked': _loc('LABEL_VEHICLE_LOCKED'),
            'improving': _client_text(_KEY_IMPROVING, logger),
            'pawned': _loc('LABEL_PAWNED'),
            'hintOpen': _loc('LABEL_HINT_OPEN'),
            'hintPause': _loc('LABEL_HINT_PAUSE'),
            'hintResume': _loc('LABEL_HINT_RESUME'),
            'hintReset': _loc('LABEL_HINT_RESET'),
        }
        return json.dumps(snapshot)
    except Exception:
        logger.exception('Failed to serialise the campaign snapshot')
        return '{}'


def _client_text(key, logger, **format_kwargs):
    """A string the client already ships translated, or an empty string.

    An empty answer is the right failure here. The widget draws whatever it is handed, so a
    key the client drops leaves its line blank and costs nothing else. The secondary heading
    keeps its element even when empty, because that element carries the rule dividing the two
    condition groups, and losing the rule would read worse than losing the word.
    """
    try:
        from helpers import i18n
        return i18n.makeString(key, **format_kwargs)
    except Exception:
        logger.exception('Failed to read the client string %s', key)
        return ''


def _log_payload_change(snapshot, logger):
    """Report how many campaigns a snapshot found, when that number changes.

    The banners cannot appear before the client has the mission data, and how long that takes
    is not something this mod controls. Timing it is the only way to tell a slow client from a
    slow mod, so the first build is logged and every later change of the count -- which is what
    a reader of `python.log` needs to place the banners' arrival against the garage's.
    """
    global _last_logged_count
    try:
        count = len(snapshot.get('campaigns') or ())
    except Exception:
        return
    if count == _last_logged_count:
        return
    _last_logged_count = count
    logger.info('Snapshot has %d active campaign(s), vehicle in garage: %s',
                count, bool(snapshot.get('hasVehicle')))


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


def refresh(logger):
    """Rebuild the snapshot and push it to every live widget model."""
    if not _models:
        return
    payload = _build_payload(logger)
    _push(lambda model: model.setSnapshot(payload), logger)


def _show_card(branch, arg, logger):
    """Hand the card window the entry behind one banner, plus where that banner sits.

    The snapshot is rebuilt rather than cached: a hover is a rare event at human speed, and a
    cached copy would be the one thing on screen that could disagree with the banner above it.
    """
    try:
        snapshot = json.loads(_build_payload(logger))
    except Exception:
        logger.exception('Failed to read the snapshot for the hover card')
        return
    entry = None
    for row in snapshot.get('campaigns') or ():
        if row.get('branch') == branch:
            entry = row
            break
    if entry is None:
        card_window.hide(logger)
        return
    rect = (
        _int(_map_get(arg, 'x')), _int(_map_get(arg, 'y')),
        _int(_map_get(arg, 'w')), _int(_map_get(arg, 'h')),
    )
    card_window.show(branch, rect, entry, snapshot.get('labels') or {},
                     held_keys.text(), logger)


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _apply_held_keys(logger):
    text = held_keys.text()
    _push(lambda model: model.setHeldKeys(text), logger)
    # The card draws its own hint lines now, so it needs the keys too.
    card_window.set_held_keys(text, logger)


def _on_held_keys_changed():
    _apply_held_keys(_module_logger)


def _apply_visibility(logger):
    visible = route_gate.is_visible()
    _push(lambda model: model.setVisible(visible), logger)
    if not visible:
        # Leaving the garage does not move the pointer, so no banner reports a leave. Without
        # this the card would stay on screen over whatever replaced the garage.
        card_window.hide(logger)


def _push(action, logger):
    """Apply `action` to each model still alive, dropping any that refuses the update."""
    for model in list(_models):
        try:
            action(model)
        except Exception:
            # Not the teardown path: a torn-down view accepts updates and ignores them, so
            # nothing reaches here when one dies. This covers a model that fails for some
            # other reason, which has not been seen and is worth a line if it ever is.
            _forget(model)
            logger.info('Dropped a widgets model that refused an update (%d live)', len(_models))


def _forget(model):
    try:
        _models.remove(model)
    except ValueError:
        pass


def _on_route_visibility(visible):
    _module_logger.info('Garage is the visible route: %s', visible)
    _apply_visibility(_module_logger)
    if visible:
        # The hangar view models are built before the garage is on screen, so the payload they
        # started with can already be stale by the time the player sees it -- the mission data
        # may have landed in between, and on a return from another lobby screen the tank may
        # have changed. Rebuilding here costs one snapshot and closes that gap.
        refresh(_module_logger)


def _bind_events(logger):
    """Refresh on the things that change what the widgets show.

    Called every time a hangar view is built rather than once per session, because the client
    throws our subscriptions away: `g_currentVehicle` clears its whole event manager in
    `destroy()`, which runs on every lobby teardown, so a handler attached once is silently
    gone afterwards.

    `Event.__iadd__` ignores a delegate it already holds, so re-binding costs nothing; the
    explicit membership test is only there to log when a subscription actually had to be
    replaced.
    """
    try:
        from CurrentVehicle import g_currentVehicle
        if _on_vehicle_changed not in g_currentVehicle.onChanged:
            g_currentVehicle.onChanged += _on_vehicle_changed
            logger.info('Subscribed to vehicle changes')
    except Exception:
        logger.exception('Failed to subscribe to vehicle changes')

    _bind_missions(logger)
    # Built here rather than at load: the card needs the lobby's main window as its parent, and
    # that window does not exist until a hangar view is being built. `install` is a no-op once
    # the window stands, and the window is destroyed on teardown with everything else.
    card_window.install(logger)
    # The lobby state machine belongs to the lobby app, so it is a different object after every
    # teardown; `install` compares identity and only re-subscribes when it actually changed.
    route_gate.install(logger, _on_route_visibility)
    # Unlike the route gate, this subscribes to a module-level singleton that survives every
    # lobby teardown, so it is made once here and never retried.
    held_keys.install(logger, _on_held_keys_changed)


def _bind_missions(logger):
    """Follow the personal missions cache, which owns everything the banners show.

    `onPMSyncCompleted` fires when the cache has re-read the missions -- a mission selected or
    finished, a campaign switched, condition progress arriving after a battle. That is the one
    event that covers all of them, so it is the only mission subscription made here.

    `onSyncCompleted` on the same cache is deliberately not used. `EventsCache.update()` fires
    it immediately before `onPMSyncCompleted` on every path that reaches either, so listening
    to both only builds the same snapshot twice.
    """
    try:
        from helpers import dependency
        from skeletons.gui.server_events import IEventsCache
        events_cache = dependency.instance(IEventsCache)
        if _on_missions_synced not in events_cache.onPMSyncCompleted:
            events_cache.onPMSyncCompleted += _on_missions_synced
            logger.info('Subscribed to personal mission updates')
    except Exception:
        logger.exception('Failed to subscribe to personal mission updates')


def _unbind_events(logger):
    try:
        from CurrentVehicle import g_currentVehicle
        g_currentVehicle.onChanged -= _on_vehicle_changed
    except Exception:
        pass
    try:
        from helpers import dependency
        from skeletons.gui.server_events import IEventsCache
        dependency.instance(IEventsCache).onPMSyncCompleted -= _on_missions_synced
    except Exception:
        pass


def _on_vehicle_changed(*args):
    # A different tank falls in a different line, so every banner can change at once.
    refresh(_module_logger)


def _on_missions_synced(*args):
    refresh(_module_logger)


def install(logger):
    """Patch the candidate hangar views. Returns True when at least one was hooked."""
    if _patched:
        return True

    try:
        from openwg_gameface import gf_mod_inject
    except ImportError:
        logger.info(
            'net.openwg.gameface not found; the campaign widgets are disabled '
            '(install the OpenWG Gameface library to enable it)'
        )
        return False

    # Almost certainly a no-op here -- the lobby app that owns the state machine does not exist
    # this early -- but it costs nothing and `_bind_events` retries on every hangar build.
    route_gate.install(logger, _on_route_visibility)
    # Unlike the route gate, this subscribes to a module-level singleton that survives every
    # lobby teardown, so it is made once here and never retried.
    held_keys.install(logger, _on_held_keys_changed)

    for module_path, class_name in _CANDIDATE_MODELS:
        model_class = _import_model(module_path, class_name, logger)
        if model_class is None:
            continue
        _patch(model_class, gf_mod_inject, logger)

    if not _patched:
        logger.warning('No hangar view could be hooked; the campaign widgets are disabled')
        return False

    logger.info('Campaign widgets installed (%d candidate views)', len(_patched))
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

    def _initialize_with_widgets(self):
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
            # Subscribed before the snapshot is read, not after. A mission sync landing between
            # the two would otherwise be missed twice over: too early for the subscription to
            # hear it, too late for a payload that was already built.
            _bind_events(logger)
            data_model = _WidgetsDataModel(_build_payload(logger))
            self._addViewModelProperty(str(_DATA_PROPERTY), data_model)
            _models.append(data_model)
            logger.info('Campaign widgets attached to %s (%d live)',
                        model_class.__name__, len(_models))
        except Exception:
            _claimed_class = None
            logger.exception('Failed to attach the campaign widgets model')

    model_class._initialize = _initialize_with_widgets
    _patched.append((model_class, original))


def uninstall(logger):
    global _claimed_class
    _claimed_class = None
    _unbind_events(logger)
    card_window.uninstall(logger)
    route_gate.uninstall(logger)
    held_keys.uninstall(logger)
    del _models[:]
    while _patched:
        model_class, original = _patched.pop()
        try:
            model_class._initialize = original
        except Exception:
            logger.exception('Failed to restore %s._initialize', model_class.__name__)
