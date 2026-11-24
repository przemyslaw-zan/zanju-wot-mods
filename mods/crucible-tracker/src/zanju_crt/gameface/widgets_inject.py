# -*- coding: utf-8 -*-
"""Attaches the Crucible banner to the garage's Gameface document.

The banner is plain HTML and JS inside the game's own garage document, `mono/hangar/main`.
`net.openwg.gameface` loads it from a `ModInjectModel` on a sub-view of that document. The model
rides on a child sub-view of the mod's own, which hangar_child adds to the random garage, so the
mod takes no sub-view that another mod could want. Our data model (`zanjuCrtWidgets`) carries
the Crucible snapshot as JSON, and widgets.js reads it.

The banner stands in the shared banner tray beside the vehicle name, on the side the config
names, next to the banners of campaign-tracker. See tray.js.

The banner sends two things back: a click, which opens the client's own Crucible screen, and a
hover, which shows the card in a window of the mod's own (see card_window).

Each refresh also writes the battle transport, the facts a battle needs about the active series
(see transport).

See docs/reference/gameface-mod-widgets.md for the wider set of rules this follows.
"""
from __future__ import absolute_import, print_function, unicode_literals

import json
import logging
import time

from frameworks.wulf import ViewModel

from .. import card_window, collector, config, crucible, hangar_child, mode_gate, navigation, route_gate, transport
from ..constants import LOGGER_NAME
from ..localization import get_text as _loc

_MODULE_URL = 'coui://gui/gameface/mods/zanju_crucible/widgets.js'
_STYLE_URL = 'coui://gui/gameface/mods/zanju_crucible/widgets.css'
_INJECT_NAME = 'zanju_crt_widgets'
_DATA_PROPERTY = 'zanjuCrtWidgets'
# Where the mod's own child sits among the children of the random garage view: 'ZCRT' in ASCII.
# Far above the client's resource IDs, which were near 136,000 on 2.4.0.2. Each of our mods has
# its own ID, listed in docs/reference/gameface-mod-widgets.md.
_POS_ID = 0x5A435254

# Client strings this mod reads instead of shipping its own, so every language the client ships
# gets the client's own words. Written as the keys themselves, because the key is the half worth
# reading here.
_CLIENT_KEYS = {
    'header': '#user_missions:hub/challenge_missions/header',
    # Beside a mission of the active series that the player completed.
    'completed': '#user_missions:hub/challenge_missions/missionsCompleted',
    'or': '#user_missions:hub/challenge_missions/card/or',
    'vehicleRestriction': '#user_missions:hub/challenge_missions/header/vehicleRestriction',
    'hard': '#user_missions:hub/challenge_missions/complexity/hard',
    'medium': '#user_missions:hub/challenge_missions/complexity/medium',
    'easy': '#user_missions:hub/challenge_missions/complexity/easy',
}

_module_logger = logging.getLogger(LOGGER_NAME)

# The hover card, in a window of the mod's own. See card_window.
_card = card_window.CardWindow(('mods', 'zanju', 'crucibletracker', 'views', 'CrucibleCard'),
                               'ZanjuCrucibleCard', 'zanju.crucibletracker.json')

# How many data models to keep, newest last. The client builds one garage document at a time, so
# only the last entry is ever on screen. The others cover a rebuild that overlaps the last one.
# Kept short for the reason campaign-tracker found: a dead model takes an update and ignores it.
_MAX_LIVE_MODELS = 4
_models = []
_attached_total = 0
_installed = []
# The last payload pushed, so an update that changes nothing pushes nothing. The items cache
# syncs often, and most syncs do not touch the Crucible.
_last_payload = [None]
# The series state last reported to the log, so the log says when it changes and not more often.
_last_logged = [None]


class _WidgetsDataModel(ViewModel):
    """The Crucible snapshot and whether to show it, read by widgets.js."""

    def __init__(self, payload):
        self._payload = payload
        # Two properties and two commands, which _initialize adds in this order.
        super(_WidgetsDataModel, self).__init__(properties=2, commands=2)

    def _initialize(self):
        super(_WidgetsDataModel, self)._initialize()
        # The snapshot travels as JSON in one string property. The banner and the card render
        # it whole, so a wulf array of nested models would buy nothing.
        self._addStringProperty('snapshot', self._payload)
        self._addBoolProperty('visible', _banner_visible())
        self.openCrucible = self._addCommand('openCrucible')
        self.openCrucible += self.__onOpenCrucible
        self.cardHover = self._addCommand('cardHover')
        self.cardHover += self.__onCardHover

    _SNAPSHOT_INDEX = 0
    _VISIBLE_INDEX = 1

    def setSnapshot(self, payload):
        self._payload = payload
        self._setString(self._SNAPSHOT_INDEX, payload)

    def setVisible(self, visible):
        self._setBool(self._VISIBLE_INDEX, bool(visible))

    def __onOpenCrucible(self, *args):
        # A command handler runs inside the client's own dispatch, so nothing may leave it.
        try:
            _card.hide(_module_logger)
            snapshot = _read_snapshot()
            active = snapshot.get('active') if snapshot else None
            navigation.open_crucible(active.get('id') if active else None, _module_logger)
        except Exception:
            _module_logger.exception('Failed to open the Crucible screen')

    def __onCardHover(self, *args):
        try:
            _on_card_hover(args[0] if args else None)
        except Exception:
            _module_logger.exception('Failed to handle a hover on the banner')


def _map_get(arg, key):
    """Read a key from the single map argument a wulf command carries."""
    if isinstance(arg, dict):
        return arg.get(key)
    getter = getattr(arg, 'get', None)
    if callable(getter):
        try:
            return arg.get(key)
        except Exception:
            return None
    return None


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _on_card_hover(arg):
    """The pointer entered or left the banner. An empty key means it left."""
    key = _map_get(arg, 'key')
    if not key:
        _card.hide(_module_logger)
        return
    snapshot = _read_snapshot()
    if not snapshot:
        _card.hide(_module_logger)
        return
    rect = (_int(_map_get(arg, 'x')), _int(_map_get(arg, 'y')),
            _int(_map_get(arg, 'w')), _int(_map_get(arg, 'h')))
    _card.show(key, rect, {'snapshot': snapshot}, _module_logger)


def _read_snapshot():
    try:
        return json.loads(_last_payload[0] or _build_payload(_module_logger))
    except Exception:
        _module_logger.exception('Failed to read the Crucible snapshot')
        return None


def _labels():
    labels = {
        'noActive': _loc('LABEL_NO_ACTIVE'),
        'mission': _loc('LABEL_MISSION'),
        'missionNumber': _loc('LABEL_MISSION_NUMBER'),
        'completions': _loc('LABEL_COMPLETIONS'),
        'available': _loc('LABEL_AVAILABLE'),
        'freeRestart': _loc('LABEL_FREE_RESTART'),
        'restartFor': _loc('LABEL_RESTART_FOR'),
        'inBattle': _loc('LABEL_IN_BATTLE'),
        'inBattleWarning': _loc('LABEL_IN_BATTLE_WARNING'),
        'hintOpen': _loc('LABEL_HINT_OPEN'),
        # The units of the countdown, the same keys and the same words as premium-time.
        'dayUnit': _loc('UNIT_DAY_SHORT'),
        'hourUnit': _loc('UNIT_HOUR_SHORT'),
        'minuteUnit': _loc('UNIT_MINUTE_SHORT'),
        'secondUnit': _loc('UNIT_SECOND_SHORT'),
    }
    for name, key in _CLIENT_KEYS.items():
        labels[name] = _client_text(key)
    return labels


def _client_text(key):
    """A string the client already ships translated, or an empty string."""
    try:
        from helpers import i18n
        return i18n.makeString(key)
    except Exception:
        _module_logger.exception('Failed to read the client string %s', key)
        return ''


def _build_payload(logger):
    """The snapshot plus its labels, as JSON. Also writes the battle transport."""
    try:
        snapshot, conditions = collector.collect(logger)
        try:
            _save_transport(snapshot, conditions, logger)
        except Exception:
            # The banner does not need the transport. Thus a transport error must not remove the
            # banner too.
            logger.exception('Failed to write the battle transport')
        _log_change(snapshot, logger)
        snapshot['labels'] = _labels()
        snapshot['layout'] = {'side': config.tray_side()}
        # The end times are server times, and the JavaScript counts down against its own clock.
        snapshot['timeOffset'] = collector.server_time_offset()
        return json.dumps(snapshot)
    except Exception:
        logger.exception('Failed to build the Crucible snapshot')
        return '{}'


def _save_transport(snapshot, conditions, logger):
    if not snapshot.get('enabled'):
        # Before the lobby has the Crucible settings, nothing is known. Writing "no series"
        # then would erase a good transport for a battle that a reconnect enters.
        return
    account = collector.account_dbid()
    data = crucible.transport(snapshot, conditions, account, int(time.time()))
    if transport.save(account, data, logger):
        active = (data or {}).get('active') or {}
        logger.info('Battle transport written: %s', active.get('questID') or 'no active series')


def _log_change(snapshot, logger):
    active = snapshot.get('active') or {}
    state = (snapshot.get('enabled'), len(snapshot.get('series') or ()), active.get('id'),
             active.get('stage'), active.get('shields'))
    if state == _last_logged[0]:
        return
    _last_logged[0] = state
    logger.info('Crucible: enabled %s, %d series, active %s, mission %s, shields %s', *state)


def refresh(logger):
    """Rebuild the snapshot and push it to every live model, when it changed."""
    payload = _build_payload(logger)
    if payload == _last_payload[0]:
        return
    _last_payload[0] = payload
    _push(lambda model: model.setSnapshot(payload), logger)
    try:
        _card.update({'snapshot': json.loads(payload)}, logger)
    except Exception:
        logger.exception('Failed to update the hover card')


def _banner_visible():
    """The settings allow the banner, the garage is on screen, and random battles are selected."""
    return config.garage_enabled() and route_gate.is_visible() and mode_gate.is_visible()


def _apply_visibility(logger):
    visible = _banner_visible()
    _push(lambda model: model.setVisible(visible), logger)
    if not visible:
        # Leaving the garage does not move the pointer, so the banner reports no leave.
        _card.hide(logger)


def _push(action, logger):
    for model in list(_models):
        try:
            action(model)
        except Exception:
            try:
                _models.remove(model)
            except ValueError:
                pass
            logger.info('Dropped a widgets model that refused an update (%d live)', len(_models))


def _on_mode_visibility(visible):
    _module_logger.info('Random battles is the selected mode: %s', visible)
    _apply_visibility(_module_logger)


def _on_route_visibility(visible):
    _module_logger.info('Garage is the visible route: %s', visible)
    _apply_visibility(_module_logger)
    if visible:
        refresh(_module_logger)


def _on_changed(*args):
    refresh(_module_logger)


def _crucible_events():
    from helpers import dependency
    from skeletons.gui.challenges import IChallengesController
    from skeletons.gui.shared import IItemsCache
    controller = dependency.instance(IChallengesController)
    items_cache = dependency.instance(IItemsCache)
    return (
        ('onChallengesSettingsChanged', controller.onChallengesSettingsChanged),
        ('onActiveChallengeChanged', controller.onActiveChallengeChanged),
        ('onChallengesClientUpdated', controller.onChallengesClientUpdated),
        # The tokens of a series change after a battle, and the client tells only the items cache.
        ('itemsCache.onSyncCompleted', items_cache.onSyncCompleted),
    )


def _bind_events(logger):
    """Refresh on the things that change what the banner shows.

    Called on every garage build rather than once, because the client throws some subscriptions
    away: `g_currentVehicle` clears its event manager on every lobby teardown. `Event` ignores a
    delegate it already holds, so binding again costs nothing.
    """
    try:
        from CurrentVehicle import g_currentVehicle
        if _on_changed not in g_currentVehicle.onChanged:
            g_currentVehicle.onChanged += _on_changed
    except Exception:
        logger.exception('Failed to subscribe to vehicle changes')
    try:
        for name, event in _crucible_events():
            if _on_changed not in event:
                event += _on_changed
                logger.info('Subscribed to %s', name)
    except Exception:
        logger.exception('Failed to subscribe to the Crucible updates')
    route_gate.install(logger, _on_route_visibility)
    mode_gate.install(logger, _on_mode_visibility)


def _unbind_events(logger):
    try:
        from CurrentVehicle import g_currentVehicle
        g_currentVehicle.onChanged -= _on_changed
    except Exception:
        pass
    try:
        for _name, event in _crucible_events():
            event -= _on_changed
    except Exception:
        pass


def _build_data_model():
    """The data model for one garage build. hangar_child calls this from the child's model."""
    global _attached_total
    _bind_events(_module_logger)
    payload = _build_payload(_module_logger)
    _last_payload[0] = payload
    data_model = _WidgetsDataModel(payload)
    _models.append(data_model)
    del _models[:-_MAX_LIVE_MODELS]
    _attached_total += 1
    _module_logger.info('Crucible banner attached (%d built, %d kept)', _attached_total, len(_models))
    return data_model


def on_settings_changed(keys):
    """Mod Menu changed a setting. The side reaches the banner with the next snapshot."""
    _last_payload[0] = None
    refresh(_module_logger)
    _apply_visibility(_module_logger)


def install(logger):
    """Give the random garage a child view that carries the banner. Returns True on success."""
    if _installed:
        return True
    route_gate.install(logger, _on_route_visibility)
    mode_gate.install(logger, _on_mode_visibility)
    route = hangar_child.install(logger, _POS_ID, _INJECT_NAME, [_STYLE_URL], [_MODULE_URL],
                                 _DATA_PROPERTY, _build_data_model)
    if route is None:
        logger.warning('The garage child view could not be set up; the Crucible banner is disabled')
        return False
    _installed.append(route)
    logger.info('Crucible banner installed (route %s)', route)
    return True


def uninstall(logger):
    del _installed[:]
    _unbind_events(logger)
    _card.uninstall(logger)
    route_gate.uninstall(logger)
    mode_gate.uninstall(logger)
    hangar_child.uninstall(logger)
    del _models[:]
