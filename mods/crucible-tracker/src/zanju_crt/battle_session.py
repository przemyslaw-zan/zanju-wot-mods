# -*- coding: utf-8 -*-
"""The Crucible mission in battle: which battles show the panel, and what the panel counts.

When the battle page populates, the session reads the transport that the garage wrote: first the
copy in memory, then the file (see transport). The panel opens only when the settings allow it,
a series is active, and the battle type and the tier of the vehicle are the mission's own.

The tracker (see progress) counts each condition from the client's battle controllers:

- A hit on an enemy: feedback `PLAYER_DAMAGED_HP_ENEMY`, with the HP, the attack reason, the
  distance to the target, the view range and the server time. Fire and ramming count too.
- A kill: `PLAYER_KILLED_ENEMY`, with the class of the enemy from the arena data.
- Radio and track assist: `PLAYER_ASSIST_TO_KILL_ENEMY`, told apart by the battle event type.
- Stun assist, blocked damage and crits: `PLAYER_ASSIST_TO_STUN_ENEMY`, `PLAYER_USED_ARMOR` and
  `PLAYER_DAMAGED_DEVICE_ENEMY`.
- Damage received and full HP: the HP of the player's vehicle, read on each change of it.
- The battle summary of the server: the totals of damage, assist and blocked damage. The panel
  takes a total from it when the total is higher.
- The start of the battle: the arena period. The battle starts at `periodEndTime - periodLength`
  of the period BATTLE, in the clock of `BigWorld.serverTime()`.
- An award: the result keys of its rule in crucible.AWARD_RULES, and for High Caliber, the total
  HP of the enemy team from the arena, and every direct shot of the player that hits an ally.
  The client calls `Vehicle.showDamageFromShot(attackerID, ...)` on each vehicle that a shell
  hits, to draw the hit, also when team damage is off and the hit does no damage.

After a reconnect, the client has lost the events from before it, so no figure is sure. The
panel then shows the conditions with no progress, and only a time limit still counts down. A
reconnect is an entry into an arena that this vehicle first entered more than 30 s before (see
battle_record).

At the end of a battle, the session logs the figure of each condition and the totals, to compare
with the result of the mission.

Every client import stays inside a function, so this module is importable outside the game.
"""
from __future__ import absolute_import, print_function, unicode_literals

import time

from . import battle_record, card_window, collector, config, crucible, progress, transport
from .gameface import battle_panel
from .localization import get_text as _loc

# The client string between two sets of conditions, the same one that the hover card uses.
_OR_KEY = '#user_missions:hub/challenge_missions/card/or'
# The client's own terms of High Caliber, one per line. The third is the rule on hitting allies.
_HIGH_CALIBER_TERMS_KEY = '#achievements:mainGun_condition'
_ALLY_RULE_LINE = 2
_ALLY_RULE_FALLBACK = 'The player must not hit any allies by direct shots.'
# Each hit and kill is logged while a condition depends on the distance, the time or the HP, so
# the log shows what the panel counted. At most this many lines per battle.
_MAX_HIT_LOGS = 40
# The longest view range the arena allows when the client cannot say, in metres.
_DEFAULT_MAX_VIEW_RANGE = 445.0
# An entry into an arena that the vehicle first entered more than this many seconds before is a
# reconnect. At a first entry, the battle page populates a few seconds before battle_record writes
# the entry, so the record of this arena is not there yet.
_REJOIN_SECONDS = 30

_state = {'installed': False, 'logger': None, 'session': None}
_patched = []


class _Session(object):
    """The panel and the tracker of one battle."""

    def __init__(self, logger, active, provider, counting=True):
        self.logger = logger
        self.active = active
        self.provider = provider
        # False after a reconnect: the events from before it are lost, so no figure is sure.
        self.counting = counting
        self.tracker = progress.Tracker([('postBattle', active.get('postBattle') or [])], collector.award_name)
        self.panel = battle_panel.Panel(logger)
        self.subscriptions = []
        self.hit_logs = 0
        self.summary_logged = False
        self.time_offset = 0.0
        self.labels = {}
        # Hits and kills are logged only for the conditions that the log can check.
        self.log_hits = any(spec.get('distance') is not None or spec.get('timeLimit') is not None
                            or spec.get('fullHealth') or spec.get('classes') or spec.get('eventCount')
                            for spec in self.tracker.specs if spec.get('live'))

    # -- life ---------------------------------------------------------------------------------

    def start(self):
        import BigWorld
        from PlayerEvents import g_playerEvents
        shared = self.provider.shared
        self._subscribe(shared.feedback.onPlayerFeedbackReceived, self._on_feedback)
        self._subscribe(shared.feedback.onPlayerSummaryFeedbackReceived, self._on_summary)
        self._subscribe(shared.vehicleState.onVehicleStateUpdated, self._on_vehicle_state)
        self._subscribe(g_playerEvents.onArenaPeriodChange, self._on_period)
        # The JavaScript counts the time limit down against its own clock.
        self.time_offset = round(BigWorld.serverTime() - time.time(), 1)
        self.labels = {'mission': _loc('LABEL_MISSION'), 'or': _client_text(_OR_KEY, self.logger),
                       'noAllyHits': _ally_rule(self.logger)}
        self._read_period()
        self._read_health()
        self.panel.open(self.payload())

    def stop(self):
        import BigWorld
        try:
            # The figures of the panel at the end, to compare with the hits above and with the result.
            self.logger.info('Battle panel at the end: %s', progress.summary(self.tracker, BigWorld.serverTime()))
        except Exception:
            self.logger.exception('Failed to log the figures of the battle panel')
        while self.subscriptions:
            event, handler = self.subscriptions.pop()
            try:
                event -= handler
            except Exception:
                self.logger.exception('Failed to unsubscribe from a battle event')
        self.panel.close()

    def _subscribe(self, event, handler):
        def guarded(*args, **kwargs):
            # Runs inside the client's own event dispatch, so nothing may leave it.
            try:
                handler(*args, **kwargs)
            except Exception:
                self.logger.exception('Failed to follow a battle event')
        event += guarded
        self.subscriptions.append((event, guarded))

    def push(self):
        self.panel.update(self.payload())

    def payload(self):
        import BigWorld
        now = BigWorld.serverTime()
        active = self.active
        return {
            'lang': card_window.client_language(),
            'labels': self.labels,
            'timeOffset': self.time_offset,
            'series': {
                'name': active.get('name') or '',
                'stage': active.get('stage'),
                'total': active.get('total'),
                'shields': active.get('shields'),
                'shieldsLimit': active.get('shieldsLimit'),
            },
            'group': 'or' if self.tracker.set_count > 1 else 'and',
            'rows': progress.panel_rows(self.tracker, active.get('rows') or [], now, _number_format,
                                        self.counting),
            'done': self.counting and progress.MET in self.tracker.set_states(now),
        }

    # -- events -------------------------------------------------------------------------------

    def _on_feedback(self, events):
        from gui.battle_control.battle_constants import FEEDBACK_EVENT_ID as FET
        for event in events:
            kind = event.getType()
            if kind == FET.PLAYER_DAMAGED_HP_ENEMY:
                self._on_hit(event)
            elif kind == FET.PLAYER_KILLED_ENEMY:
                self._on_kill(event.getTargetID())
            elif kind == FET.PLAYER_ASSIST_TO_KILL_ENEMY:
                self.tracker.add_result(_assist_key(event.getBattleEventType()), event.getExtra().getDamage())
            elif kind == FET.PLAYER_ASSIST_TO_STUN_ENEMY:
                self.tracker.add_result('damageAssistedStun', event.getExtra().getDamage())
            elif kind == FET.PLAYER_USED_ARMOR:
                self.tracker.add_result('damageBlockedByArmor', event.getExtra().getDamage())
            elif kind == FET.PLAYER_DAMAGED_DEVICE_ENEMY:
                self.tracker.add_result('critsCount', event.getExtra().getCritsCount())
        self._read_health()
        self.push()

    def _on_hit(self, event):
        import BigWorld
        extra = event.getExtra()
        target = event.getTargetID()
        damage = extra.getDamage()
        reason = extra.getAttackReasonID()
        distance = self._distance_to(target)
        view_range = self._view_range()
        now = BigWorld.serverTime()
        self.tracker.on_damage(target, damage, reason, distance, view_range, now)
        start = self.tracker.battle_start
        self._log_hit('Hit on %s: %s HP, reason %s, distance %s, view range %s, %s s into the battle',
                      target, damage, reason, _metres(distance), _metres(view_range),
                      int(now - start) if start is not None else '?')

    def on_shot_hit(self, target_id, attacker_id):
        """A shell hit a vehicle. A direct shot of the player on an ally ends High Caliber."""
        import BigWorld
        player_vehicle = getattr(BigWorld.player(), 'playerVehicleID', None)
        if attacker_id != player_vehicle or target_id == player_vehicle or self.tracker.ally_hit:
            return
        try:
            is_ally = self.provider.getArenaDP().isAlly(target_id)
        except Exception:
            return
        if not is_ally:
            return
        self.tracker.on_ally_hit()
        self.logger.info('A direct shot of the player hit the ally %s', target_id)
        self.push()

    def _on_kill(self, target):
        vehicle_class = self._vehicle_class(target)
        self.tracker.on_kill(target, vehicle_class)
        self._log_hit('Kill of %s: class %s, last hit reason %s, full HP %s', target, vehicle_class,
                      self.tracker.last_reason.get(target), self.tracker.full_health)

    def _log_hit(self, message, *args):
        if not self.log_hits or self.hit_logs >= _MAX_HIT_LOGS:
            return
        self.hit_logs += 1
        self.logger.info(message, *args)

    def _on_summary(self, event):
        values = {
            'damageDealt': event.getTotalDamage(),
            'damageBlockedByArmor': event.getTotalBlockedDamage(),
            'damageAssistedStun': event.getTotalStunDamage(),
            # The summary has radio and track assist apart, but gives only their sum by a method.
            'damageAssistedRadio': getattr(event, '_BattleSummaryFeedbackEvent__radioAssistDamage', None),
            'damageAssistedTrack': getattr(event, '_BattleSummaryFeedbackEvent__trackAssistDamage', None),
        }
        if not self.summary_logged:
            self.summary_logged = True
            self.logger.info('Battle summary from the server: %s; the panel had %s', sorted(values.items()),
                             sorted((key, self.tracker.totals[key]) for key in values))
        self.tracker.raise_results(values)
        self.push()

    def _on_vehicle_state(self, state, value):
        from gui.battle_control.battle_constants import VEHICLE_VIEW_STATE
        if state == VEHICLE_VIEW_STATE.HEALTH:
            self._read_health()
            self.push()

    def _on_period(self, *args):
        self._read_period()
        self.push()

    # -- client reads -------------------------------------------------------------------------

    def _read_period(self):
        import BigWorld
        from constants import ARENA_PERIOD
        player = BigWorld.player()
        self.tracker.set_enemy_health(_enemy_health(player))
        if self.tracker.battle_start is not None:
            return
        arena = getattr(player, 'arena', None)
        if arena is None or arena.period != ARENA_PERIOD.BATTLE:
            return
        start = arena.periodEndTime - arena.periodLength
        self.tracker.set_battle_start(start)
        self.logger.info('Battle start at server time %.1f, %.1f s ago', start, BigWorld.serverTime() - start)

    def _read_health(self):
        import BigWorld
        player = BigWorld.player()
        vehicle_id = getattr(player, 'playerVehicleID', None)
        vehicle = BigWorld.entity(vehicle_id) if vehicle_id else None
        health = getattr(vehicle, 'health', None) if vehicle is not None else None
        self.tracker.set_health(health, self._vehicle_type(vehicle_id, 'maxHealth'))

    def _vehicle_type(self, vehicle_id, name):
        return _vehicle_type(self.provider, vehicle_id, name)

    def _vehicle_class(self, vehicle_id):
        return self._vehicle_type(vehicle_id, 'classTag')

    def _distance_to(self, target_id):
        """The distance from the player's vehicle to the target, or None when the target is not in
        the client's world. The positions are read when the hit arrives, a moment after the shot."""
        import BigWorld
        target = BigWorld.entity(target_id)
        if target is None:
            return None
        player = BigWorld.player()
        own = BigWorld.entity(getattr(player, 'playerVehicleID', None))
        own_position = own.position if own is not None else player.getOwnVehiclePosition()
        return (target.position - own_position).length

    def _view_range(self):
        """The view range of the player's vehicle, as the minimap draws it: capped at the arena's
        maximum, `VISIBILITY.MAX_RADIUS` (445 m) unless an arena modifier changes it. The garage
        can show more, but the battle uses the capped range."""
        try:
            radius = self.provider.shared.feedback.getVehicleAttrs().get('circularVisionRadius')
        except Exception:
            radius = None
        if radius is None:
            return None
        try:
            highest = self.provider.arenaVisitor.getVisibilityMaxRadius()
        except Exception:
            highest = _DEFAULT_MAX_VIEW_RANGE
        return min(float(radius), float(highest))


def _enemy_health(player):
    """The total HP of the enemy team at full health, from the arena data, or 0."""
    arena = getattr(player, 'arena', None)
    team = getattr(player, 'team', None)
    if arena is None or team is None:
        return 0
    return sum((vehicle.get('maxHealth') or 0) for vehicle in arena.vehicles.values() if vehicle.get('team') != team)


def _rejoined(logger):
    """Whether this is a reconnect into a battle that the vehicle entered before."""
    battle = battle_record.current_battle()
    if battle is None:
        return False
    account, int_cd, _, arena_id = battle
    entered = battle_record.first_entry(account, int_cd, arena_id, logger)
    return entered is not None and time.time() - entered > _REJOIN_SECONDS


def _ally_rule(logger):
    """The client's own words for the rule on hitting allies, in the language of the client."""
    text = _client_text(_HIGH_CALIBER_TERMS_KEY, logger)
    if isinstance(text, bytes):
        # The client can return UTF-8 bytes on Python 2, and the bullet below is not ASCII.
        text = text.decode('utf-8', 'replace')
    lines = [line.strip().lstrip('\u2022').strip() for line in text.split('\n')]
    lines = [line for line in lines if line]
    return lines[_ALLY_RULE_LINE] if len(lines) > _ALLY_RULE_LINE else _ALLY_RULE_FALLBACK


def _on_show_damage_from_shot(vehicle, attacker_id):
    session = _state['session']
    if session is None:
        return
    try:
        session.on_shot_hit(getattr(vehicle, 'id', None), attacker_id)
    except Exception:
        _state['logger'].exception('Failed to follow a hit on a vehicle')


def _patch_vehicle_hits(logger):
    """Follow each shell that hits a vehicle. Patched once, and a hit outside a session costs one
    check. The original runs first and whole, so the patch never changes what the client draws."""
    try:
        from Vehicle import Vehicle
    except Exception:
        logger.exception('Failed to reach the vehicle class; the panel cannot see hits on allies')
        return
    original = Vehicle.showDamageFromShot

    def showDamageFromShot(self, attackerID, *args, **kwargs):
        result = original(self, attackerID, *args, **kwargs)
        _on_show_damage_from_shot(self, attackerID)
        return result

    Vehicle.showDamageFromShot = showDamageFromShot
    _patched.append((Vehicle, 'showDamageFromShot', original))


def _vehicle_type(provider, vehicle_id, name):
    """One field of the type of a vehicle in this battle, from the arena data, or None."""
    try:
        return getattr(provider.getArenaDP().getVehicleInfo(vehicle_id).vehicleType, name)
    except Exception:
        return None


def _assist_key(battle_event_type):
    from BattleFeedbackCommon import BATTLE_EVENT_TYPE
    if battle_event_type == BATTLE_EVENT_TYPE.RADIO_ASSIST:
        return 'damageAssistedRadio'
    if battle_event_type == BATTLE_EVENT_TYPE.TRACK_ASSIST:
        return 'damageAssistedTrack'
    return None


def _metres(value):
    return '-' if value is None else '%.0f m' % value


def _number_format(value):
    """A figure with the digit grouping that the client uses."""
    try:
        from gui.impl import backport
        return backport.getIntegralFormat(int(round(value)))
    except Exception:
        return '{0:,}'.format(int(round(value)))


def _client_text(key, logger):
    try:
        from helpers import i18n
        return i18n.makeString(key)
    except Exception:
        logger.exception('Failed to read the client string %s', key)
        return ''


# -- battle page --------------------------------------------------------------------------------

def _account_dbid():
    try:
        from gui.shared.utils import getPlayerDatabaseID
        return getPlayerDatabaseID()
    except Exception:
        return None


def _read_transport(account, logger):
    """The transport for this account, and where it came from."""
    data = transport.remembered(account)
    if data is not None:
        return data, 'memory'
    return transport.load(account, logger), 'file'


def _start(logger):
    """Open the panel for this battle when it counts for the mission. Returns the session or None."""
    if not config.battle_enabled():
        logger.info('Battle panel: off in the settings')
        return None
    import BattleReplay
    if BattleReplay.g_replayCtrl.isPlaying:
        # A replay is somebody's past battle, and the transport is the viewer's series now.
        return None
    import BigWorld
    from helpers import dependency
    from skeletons.gui.battle_session import IBattleSessionProvider
    account = _account_dbid()
    data, source = _read_transport(account, logger)
    active = (data or {}).get('active')
    player = BigWorld.player()
    arena = getattr(player, 'arena', None)
    provider = dependency.instance(IBattleSessionProvider)
    level = _vehicle_type(provider, getattr(player, 'playerVehicleID', None), 'level')
    reason = crucible.battle_mismatch(active, getattr(arena, 'bonusType', None), level)
    if reason is not None:
        logger.info('Battle panel: not in this battle, %s (transport from the %s)', reason, source)
        return None
    counting = not _rejoined(logger)
    session = _Session(logger, active, provider, counting)
    session.start()
    logger.info('Battle panel: mission %s, %d condition(s) in %d set(s), transport from the %s%s',
                active.get('questID'), len(session.tracker.specs), session.tracker.set_count, source,
                '' if counting else '; a reconnect, so the counters are off')
    return session


def _on_page_populated():
    _end()
    logger = _state['logger']
    try:
        _state['session'] = _start(logger)
    except Exception:
        logger.exception('Failed to open the battle panel')


def _end():
    session = _state['session']
    _state['session'] = None
    if session is not None:
        try:
            session.stop()
        except Exception:
            _state['logger'].exception('Failed to close the battle panel')


def install(logger):
    """Open the panel on each battle page, and close it with the page."""
    if _state['installed']:
        return
    from gui.Scaleform.daapi.view.battle.shared.page import SharedPage
    from PlayerEvents import g_playerEvents
    _state['logger'] = logger
    original_populate = SharedPage._populate
    original_dispose = SharedPage._dispose

    def _populate(self, *args, **kwargs):
        result = original_populate(self, *args, **kwargs)
        _on_page_populated()
        return result

    def _dispose(self, *args, **kwargs):
        _end()
        return original_dispose(self, *args, **kwargs)

    SharedPage._populate = _populate
    SharedPage._dispose = _dispose
    _patched.append((SharedPage, '_populate', original_populate))
    _patched.append((SharedPage, '_dispose', original_dispose))
    _patch_vehicle_hits(logger)
    g_playerEvents.onAvatarBecomeNonPlayer += _on_avatar_left
    _state['installed'] = True


def _on_avatar_left(*args):
    # The battle ended without a dispose of the page, such as on a disconnect.
    _end()


def uninstall(logger):
    if not _state['installed']:
        return
    _end()
    try:
        from PlayerEvents import g_playerEvents
        g_playerEvents.onAvatarBecomeNonPlayer -= _on_avatar_left
    except Exception:
        logger.exception('Failed to unsubscribe from onAvatarBecomeNonPlayer')
    while _patched:
        owner, name, original = _patched.pop()
        setattr(owner, name, original)
    _state['installed'] = False


def on_settings_changed(keys):
    """Close the panel of this battle when the settings turn it off. Turned on again, it opens
    with the next battle. A panel that stays open takes its style and figures at once."""
    if not config.battle_enabled():
        _end()
        return
    session = _state['session']
    if session is not None and ('panelStyle' in keys or 'panelFigures' in keys):
        try:
            session.push()
        except Exception:
            _state['logger'].exception('Failed to update the battle panel')
