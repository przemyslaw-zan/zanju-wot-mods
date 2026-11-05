# -*- coding: utf-8 -*-
"""Tests for the battle session: which battles open the panel, and how client events reach it.

The client modules are stood in for. The stand-ins keep only what battle_session reads, with the
names and shapes of the 2.4.1.0 client: the feedback events, the arena period, the arena data of
each vehicle and the battle summary. The window is a recorder, so these tests check the payload
that the panel would draw.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import os
import shutil
import sys
import tempfile
import time
import types
import unittest

from test_crucible import EARLY_DAMAGE, HIGH_CALIBER, TWO_SETS
from zanju_crt import battle_record, battle_session, config, crucible, transport

ACCOUNT = 500725877
PLAYER_VEHICLE = 10
ENEMY = 20
ALLY = 11
ARENA = 2420717383125650945
VEHICLE_CD = 8049


class _Logger(object):
    def __init__(self):
        self.lines = []
        self.exceptions = []

    def info(self, message, *args):
        self.lines.append(message % args if args else message)

    def error(self, message, *args):
        self.lines.append(message % args if args else message)

    def exception(self, message, *args):
        self.exceptions.append(message)


class _Event(object):
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def __isub__(self, handler):
        self.handlers.remove(handler)
        return self

    def __call__(self, *args, **kwargs):
        for handler in list(self.handlers):
            handler(*args, **kwargs)


class _Vector(object):
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z

    def __sub__(self, other):
        return _Vector(self.x - other.x, self.y - other.y, self.z - other.z)

    @property
    def length(self):
        return (self.x ** 2 + self.y ** 2 + self.z ** 2) ** 0.5


class _Ns(object):
    def __init__(self, **values):
        self.__dict__.update(values)


class FET(object):
    PLAYER_KILLED_ENEMY = 1
    PLAYER_DAMAGED_HP_ENEMY = 2
    PLAYER_DAMAGED_DEVICE_ENEMY = 3
    PLAYER_ASSIST_TO_KILL_ENEMY = 5
    PLAYER_ASSIST_TO_STUN_ENEMY = 6
    PLAYER_USED_ARMOR = 7


class BET(object):
    RADIO_ASSIST = 5
    TRACK_ASSIST = 6


class _FeedbackEvent(object):
    def __init__(self, kind, target, damage=0, reason=0, battle_event_type=0, crits=0):
        self.kind, self.target, self.battle_event_type = kind, target, battle_event_type
        self.extra = _Ns(getDamage=lambda: damage, getAttackReasonID=lambda: reason, getCritsCount=lambda: crits)

    def getType(self):
        return self.kind

    def getTargetID(self):
        return self.target

    def getBattleEventType(self):
        return self.battle_event_type

    def getExtra(self):
        return self.extra


class _Panel(object):
    """Records what the session sends to the window."""

    instances = []

    def __init__(self, logger):
        self.payloads = []
        self.closed = False
        _Panel.instances.append(self)

    def open(self, payload):
        self.payloads.append(payload)

    def update(self, payload):
        self.payloads.append(payload)

    def close(self):
        self.closed = True


def _put_module(name, module):
    """Register a stand-in module, and every parent package it needs, as attributes too."""
    parts = name.split('.')
    for index in range(1, len(parts)):
        parent_name = '.'.join(parts[:index])
        if sys.modules.get(parent_name) is None:
            sys.modules[str(parent_name)] = types.ModuleType(str(parent_name))
        if index > 1:
            setattr(sys.modules['.'.join(parts[:index - 1])], str(parts[index - 1]), sys.modules[parent_name])
    sys.modules[str(name)] = module
    if len(parts) > 1:
        setattr(sys.modules['.'.join(parts[:-1])], str(parts[-1]), module)


def _module(name, **values):
    module = types.ModuleType(str(name))
    module.__dict__.update(values)
    _put_module(name, module)
    return module


class _Client(object):
    """The stand-ins of one battle."""

    def __init__(self, bonus_type=1, level=8):
        self.time = 900.0
        self.health = {PLAYER_VEHICLE: 1500}
        self.positions = {PLAYER_VEHICLE: _Vector(0, 0, 0), ENEMY: _Vector(250, 0, 0)}
        vehicles = {
            PLAYER_VEHICLE: {'team': 1, 'maxHealth': 1500, 'vehicleType': _Ns(type=_Ns(compactDescr=VEHICLE_CD))},
            ENEMY: {'team': 2, 'maxHealth': 1200, 'vehicleType': _Ns(type=_Ns(compactDescr=1))},
            21: {'team': 2, 'maxHealth': 1800, 'vehicleType': _Ns(type=_Ns(compactDescr=2))},
        }
        self.arena = _Ns(bonusType=bonus_type, period=2, periodEndTime=1000.0, periodLength=30.0, vehicles=vehicles)
        self.player = _Ns(arena=self.arena, playerVehicleID=PLAYER_VEHICLE, team=1, arenaUniqueID=ARENA)
        self.feedback = _Ns(onPlayerFeedbackReceived=_Event(), onPlayerSummaryFeedbackReceived=_Event(),
                            getVehicleAttrs=lambda: {'circularVisionRadius': 380.0})
        self.vehicle_state = _Ns(onVehicleStateUpdated=_Event())
        types_by_id = {PLAYER_VEHICLE: _Ns(level=level, maxHealth=1500, classTag='heavyTank'),
                       ENEMY: _Ns(level=8, maxHealth=1200, classTag='AT-SPG')}
        arena_dp = _Ns(getVehicleInfo=lambda vehicle_id: _Ns(vehicleType=types_by_id[vehicle_id]),
                       isAlly=lambda vehicle_id: vehicle_id in (PLAYER_VEHICLE, ALLY))
        self.provider = _Ns(shared=_Ns(feedback=self.feedback, vehicleState=self.vehicle_state),
                            arenaVisitor=_Ns(getVisibilityMaxRadius=lambda: 445.0),
                            getArenaDP=lambda: arena_dp)
        self.controller = _Ns(activeChallengeID=0, getChallengeProgress=lambda challenge_id: {})
        self.player_events = _Ns(onArenaPeriodChange=_Event(), onAvatarBecomeNonPlayer=_Event())

    def install(self):
        client = self

        class _Entity(object):
            def __init__(self, vehicle_id):
                self.health = client.health.get(vehicle_id)
                self.position = client.positions[vehicle_id]

        def entity(vehicle_id):
            return _Entity(vehicle_id) if vehicle_id in client.positions else None

        class IBattleSessionProvider(object):
            pass

        class IChallengesController(object):
            pass

        def instance(interface):
            return client.provider if interface is IBattleSessionProvider else client.controller

        _module('BigWorld', serverTime=lambda: client.time, player=lambda: client.player, entity=entity)
        _module('BattleReplay', g_replayCtrl=_Ns(isPlaying=False))
        _module('PlayerEvents', g_playerEvents=self.player_events)
        _module('constants', ARENA_PERIOD=_Ns(PREBATTLE=2, BATTLE=3))
        _module('BattleFeedbackCommon', BATTLE_EVENT_TYPE=BET)
        _module('gui.battle_control.battle_constants', FEEDBACK_EVENT_ID=FET, VEHICLE_VIEW_STATE=_Ns(HEALTH=4))
        _module('gui.impl.backport', getIntegralFormat=lambda value: '{0:,}'.format(value))
        _module('gui.shared.utils', getPlayerDatabaseID=lambda: ACCOUNT)
        _module('helpers', dependency=_Ns(instance=instance), i18n=_Ns(makeString=lambda key: 'OR'),
                getClientLanguage=lambda: 'en')
        _module('skeletons.gui.battle_session', IBattleSessionProvider=IBattleSessionProvider)
        _module('skeletons.gui.challenges', IChallengesController=IChallengesController)
        _module('dossiers2.custom.records', DB_ID_TO_RECORD={228: ('achievements', 'mainGun')})

    def start_battle(self):
        self.arena.period, self.arena.periodEndTime, self.arena.periodLength = 3, 1900.0, 900.0
        self.time = 1010.0
        self.player_events.onArenaPeriodChange(3, 1900.0, 900.0, None)

    def hit(self, damage, at):
        self.time = at
        self.feedback.onPlayerFeedbackReceived([_FeedbackEvent(FET.PLAYER_DAMAGED_HP_ENEMY, ENEMY, damage)])


def _transport(conditions, rows):
    mission = {'questID': 'challenge:56:1', 'group': 'and', 'rows': rows, 'levels': [6, 7, 8, 9, 10, 11]}
    series = {'id': 56, 'name': 'Spark', 'difficulty': 3, 'attempts': 4, 'allowedCompletions': 1, 'questCount': 3,
              'progress': {'quests': 1, 'attempts': 4, 'wins': 0}, 'isActive': True, 'endTime': 0,
              'expiringSoon': False, 'restartPrice': {}, 'restartCostText': '', 'freeRestarts': 0}
    snapshot = crucible.build_snapshot(True, [series], mission, 8)
    return crucible.transport(snapshot, conditions, ACCOUNT, 1792103120)


EARLY_ROWS = [{'title': 'Damage', 'text': 'Cause 2,500 HP of damage within the first 5 minutes of battle',
               'icon': 'hurt_vehicles', 'kind': 'damage', 'live': True, 'set': 0}]


class BattleSessionTest(unittest.TestCase):

    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.saved_env = os.environ.get('APPDATA')
        os.environ['APPDATA'] = self.base
        self.saved_modules = dict(sys.modules)
        self.saved_panel = battle_session.battle_panel.Panel
        battle_session.battle_panel.Panel = _Panel
        _Panel.instances = []
        config._state.clear()
        config._state.update(config.DEFAULTS)
        transport._remembered.clear()
        battle_session._state.update({'logger': _Logger(), 'session': None})
        self.logger = battle_session._state['logger']

    def tearDown(self):
        battle_session._end()
        battle_session.battle_panel.Panel = self.saved_panel
        sys.modules.clear()
        sys.modules.update(self.saved_modules)
        transport._remembered.clear()
        if self.saved_env is None:
            os.environ.pop('APPDATA', None)
        else:
            os.environ['APPDATA'] = self.saved_env
        shutil.rmtree(self.base)

    def _open(self, client, conditions=EARLY_DAMAGE, rows=EARLY_ROWS):
        client.install()
        transport._remembered[ACCOUNT] = _transport(conditions, rows)
        battle_session._on_page_populated()
        return battle_session._state['session']

    def test_a_random_battle_with_a_fitting_tier_opens_the_panel(self):
        session = self._open(_Client())
        self.assertIsNotNone(session)
        payload = _Panel.instances[0].payloads[-1]
        self.assertEqual(payload['series'], {'name': 'Spark', 'stage': 1, 'total': 3, 'shields': 4, 'shieldsLimit': 4})
        self.assertEqual(payload['labels']['or'], 'OR')
        row = payload['rows'][0]
        self.assertEqual((row['live'], row['valueText'], row['targetText']), (True, '0', '2,500'))
        # The battle has not started, so the time limit has no deadline yet.
        self.assertEqual((row['deadline'], row['timeLimit']), (None, 300.0))
        self.assertEqual(self.logger.exceptions, [])

    def test_the_battle_start_sets_the_deadline_and_hits_count_until_it(self):
        client = _Client()
        self._open(client)
        client.start_battle()
        client.hit(800, 1100.0)
        client.hit(900, 1400.0)
        row = _Panel.instances[0].payloads[-1]['rows'][0]
        self.assertEqual((row['valueText'], row['deadline'], row['state']), ('800', 1300.0, 'closed'))
        self.assertTrue(any('Hit on 20: 800 HP' in line and '250 m' in line for line in self.logger.lines))
        self.assertEqual(self.logger.exceptions, [])

    def test_another_battle_type_or_tier_opens_nothing(self):
        for client in (_Client(bonus_type=32), _Client(level=5)):
            self.assertIsNone(self._open(client))
        self.assertEqual(_Panel.instances, [])
        self.assertTrue(any('battle type 32' in line for line in self.logger.lines))

    def test_a_new_style_or_figures_setting_reaches_the_open_panel_at_once(self):
        self._open(_Client())
        sent = len(_Panel.instances[0].payloads)
        battle_session.on_settings_changed(['panelStyle'])
        self.assertEqual(len(_Panel.instances[0].payloads), sent + 1)
        battle_session.on_settings_changed(['panelFigures'])
        self.assertEqual(len(_Panel.instances[0].payloads), sent + 2)
        battle_session.on_settings_changed(['traySide'])
        self.assertEqual(len(_Panel.instances[0].payloads), sent + 2)
        self.assertEqual(self.logger.exceptions, [])

    def test_the_settings_can_turn_the_panel_off(self):
        config.apply({'battleEnabled': False})
        self.assertIsNone(self._open(_Client()))
        self.assertEqual(_Panel.instances, [])

    def test_no_transport_opens_nothing(self):
        client = _Client()
        client.install()
        battle_session._on_page_populated()
        self.assertIsNone(battle_session._state['session'])

    def test_the_end_of_the_page_closes_the_panel_and_lets_the_events_go(self):
        client = _Client()
        self._open(client)
        battle_session._end()
        self.assertTrue(_Panel.instances[0].closed)
        self.assertEqual(client.feedback.onPlayerFeedbackReceived.handlers, [])
        self.assertEqual(client.player_events.onArenaPeriodChange.handlers, [])

    def test_assist_and_summary_reach_the_totals(self):
        client = _Client()
        session = self._open(client, TWO_SETS, [{'text': text, 'live': True, 'set': index // 2}
                                                for index, text in enumerate('abcd')])
        client.feedback.onPlayerFeedbackReceived([
            _FeedbackEvent(FET.PLAYER_ASSIST_TO_KILL_ENEMY, ENEMY, 300, battle_event_type=BET.RADIO_ASSIST),
            _FeedbackEvent(FET.PLAYER_ASSIST_TO_KILL_ENEMY, ENEMY, 200, battle_event_type=BET.TRACK_ASSIST),
            _FeedbackEvent(FET.PLAYER_DAMAGED_DEVICE_ENEMY, ENEMY, crits=2),
        ])
        self.assertEqual((session.tracker.totals['damageAssistedRadio'], session.tracker.totals['damageAssistedTrack'],
                          session.tracker.totals['critsCount']), (300, 200, 2))

        class BattleSummaryFeedbackEvent(object):
            def __init__(self):
                self._BattleSummaryFeedbackEvent__radioAssistDamage = 1000
                self._BattleSummaryFeedbackEvent__trackAssistDamage = 100

            def getTotalDamage(self):
                return 2400

            def getTotalBlockedDamage(self):
                return 0

            def getTotalStunDamage(self):
                return 0

        client.feedback.onPlayerSummaryFeedbackReceived(BattleSummaryFeedbackEvent())
        self.assertEqual((session.tracker.totals['damageDealt'], session.tracker.totals['damageAssistedRadio'],
                          session.tracker.totals['damageAssistedTrack']), (2400, 1000, 200))
        payload = _Panel.instances[0].payloads[-1]
        self.assertEqual(payload['group'], 'or')
        self.assertEqual([row['set'] for row in payload['rows']], [0, 0, 1, 1])
        self.assertEqual(self.logger.exceptions, [])

    def test_a_kill_and_the_health_reach_the_tracker(self):
        client = _Client()
        session = self._open(client, TWO_SETS, [{'text': text, 'live': True} for text in 'abcd'])
        client.feedback.onPlayerFeedbackReceived([_FeedbackEvent(FET.PLAYER_KILLED_ENEMY, ENEMY)])
        self.assertEqual(session.tracker.condition(1, 0)['value'], 1)
        client.health[PLAYER_VEHICLE] = 1200
        client.vehicle_state.onVehicleStateUpdated(4, 1200)
        self.assertEqual(session.tracker.totals['damageReceived'], 300)
        self.assertFalse(session.tracker.full_health)

    def test_a_first_entry_counts(self):
        battle_record.record(ACCOUNT, VEHICLE_CD, 1, ARENA, self.logger)
        session = self._open(_Client())
        self.assertTrue(session.counting)
        self.assertTrue(_Panel.instances[0].payloads[-1]['rows'][0]['live'])

    def test_a_reconnect_turns_the_counters_off_but_keeps_the_time_limit(self):
        # Two minutes before, in the real clock: a record older than three hours is dropped.
        battle_record.record(ACCOUNT, VEHICLE_CD, 1, ARENA, self.logger, now=time.time() - 120)
        client = _Client()
        session = self._open(client)
        self.assertFalse(session.counting)
        client.start_battle()
        client.hit(800, 1100.0)
        row = _Panel.instances[0].payloads[-1]['rows'][0]
        self.assertEqual((row['live'], row['deadline'], row['timeLimit']), (False, 1300.0, 300.0))
        self.assertFalse(_Panel.instances[0].payloads[-1]['done'])
        self.assertTrue(any('a reconnect' in line for line in self.logger.lines))

    def test_high_caliber_counts_against_the_enemy_team_health(self):
        client = _Client()
        self._open(client, HIGH_CALIBER, [{'text': 'Earn the High Caliber award', 'icon': 'achievement'}])
        client.hit(450, 950.0)
        row = _Panel.instances[0].payloads[-1]['rows'][0]
        # A fifth of the 1,200 and 1,800 HP of the two enemies is 600, under the floor of 1,000.
        self.assertEqual((row['live'], row['valueText'], row['targetText']), (True, '450', '1,000'))
        self.assertEqual(row['rules'], [{'key': 'noAllyHits', 'broken': False}])
        self.assertTrue(_Panel.instances[0].payloads[-1]['labels']['noAllyHits'])
        self.assertEqual(self.logger.exceptions, [])

    def test_a_direct_shot_on_an_ally_breaks_the_rule_and_a_hit_on_an_enemy_does_not(self):
        client = _Client()
        session = self._open(client, HIGH_CALIBER, [{'text': 'Earn the High Caliber award', 'icon': 'achievement'}])
        session.on_shot_hit(ENEMY, PLAYER_VEHICLE)
        session.on_shot_hit(ALLY, ENEMY)
        self.assertFalse(session.tracker.ally_hit)
        session.on_shot_hit(ALLY, PLAYER_VEHICLE)
        row = _Panel.instances[0].payloads[-1]['rows'][0]
        self.assertEqual((row['state'], row['rules']), ('closed', [{'key': 'noAllyHits', 'broken': True}]))
        self.assertTrue(any('hit the ally 11' in line for line in self.logger.lines))

    def test_the_panel_logs_its_figures_at_the_end_of_the_battle(self):
        client = _Client()
        self._open(client)
        client.start_battle()
        client.hit(400, 1100.0)
        battle_session._end()
        end = [line for line in self.logger.lines if line.startswith('Battle panel at the end: ')]
        self.assertEqual(end, ['Battle panel at the end: 1: 400/2500 open | totals: damageDealt 400'])
        self.assertEqual(self.logger.exceptions, [])


if __name__ == '__main__':
    unittest.main()
