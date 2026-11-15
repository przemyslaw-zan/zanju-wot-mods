# -*- coding: utf-8 -*-
"""Tests for the Crucible logic: series states, condition shapes and the snapshot.

The conditions below are verbatim from the client, dumped by a probe on 2.4.1.0 on
14 October 2026. Only the token conditions of the pre-battle part are cut, because nothing here
reads them.
"""
from __future__ import absolute_import, print_function, unicode_literals

import json
import unittest

from zanju_crt import crucible

_PRE = ('["preBattle", [["battle", [["bonusTypes", [["value", [1, 44, 46]]]]]], '
        '["vehicle", [["vehicleDescr", [["levels", [["value", [10, 11, 6, 7, 8, 9]]]]]]]]]]')


def _conditions(post_battle):
    return json.loads('[' + _PRE + ', ["postBattle", ' + post_battle + ']]')


DAMAGE_OR_KILLS = _conditions(
    '[["or", [["results", [["key", [["value", "damageDealt"]]], ["greaterOrEqual", [["value", 3500.0]]]]], '
    '["results", [["key", [["value", "kills"]]], ["greaterOrEqual", [["value", 3.0]]]]]]]]')
TOP_FIVE = _conditions('[["results", [["key", [["value", "damageDealt"]]], ["max", [["value", 5]]]]]]')
TWICE_HEALTH = _conditions(
    '[["results", [["key", [["value", "damageDealt"]]], ["greaterOrEqual", [["value", 2.0]]], '
    '["compareWithMaxHealth", [["value", true]]]]]]')
DEALT_BLOCKED_RECEIVED = _conditions(
    '[["results", [["plus", [["key", [["value", "damageDealt"]]], ["key", [["value", "damageBlockedByArmor"]]], '
    '["key", [["value", "damageReceived"]]]]], ["greaterOrEqual", [["value", 7500.0]]]]]]')
FAR_DAMAGE_OR_KILLS = _conditions(
    '[["or", [["vehicleDamage", [["distance", [["value", 200]]], ["greaterOrEqual", [["value", 2500.0]]]]], '
    '["results", [["key", [["value", "kills"]]], ["greaterOrEqual", [["value", 3.0]]]]]]]]')
EARLY_DAMAGE = _conditions(
    '[["vehicleDamage", [["limittedTime", [["value", 300]]], ["greaterOrEqual", [["value", 2500.0]]]]]]')
FULL_HEALTH_KILLS = _conditions(
    '[["vehicleKills", [["whileFullHealth", [["value", true]]], ["greaterOrEqual", [["value", 3.0]]]]]]')
HIGH_CALIBER = _conditions('[["achievements", [["value", [228]]]]]')
# Not from the dump: mission challenge:73:1 of 15 November 2026, "Penetrate enemy armor 10 times",
# in the form that ChallengeBattleResultsFormatter reads for the key `piercingEnemyHits`.
PENETRATIONS = _conditions(
    '[["results", [["key", [["value", "piercingEnemyHits"]]], ["greaterOrEqual", [["value", 10.0]]]]]]')
# Not from the dump: a choice of two sets of two conditions each, in the form the client parses an
# `or` of `and` groups.
TWO_SETS = _conditions(
    '[["or", [["and", [["results", [["key", [["value", "damageDealt"]]], ["greaterOrEqual", [["value", 2000.0]]]]], '
    '["vehicleKills", [["whileFullHealth", [["value", true]]], ["greaterOrEqual", [["value", 1.0]]]]]]], '
    '["and", [["results", [["key", [["value", "damageAssistedRadio"]]], ["greaterOrEqual", [["value", 2500.0]]]]], '
    '["achievements", [["value", [228]]]]]]]]]')


class HIT_FLAGS(object):
    """The values of VEHICLE_HIT_FLAGS in constants.py that the panel reads, on 2.4.1.1."""
    VEHICLE_KILLED = 1
    VEHICLE_WAS_DEAD_BEFORE_ATTACK = 2
    RICOCHET = 8
    MATERIAL_WITH_POSITIVE_DF_PIERCED_BY_PROJECTILE = 16
    MATERIAL_WITH_POSITIVE_DF_NOT_PIERCED_BY_PROJECTILE = 32
    DEVICE_PIERCED_BY_PROJECTILE = 256
    CHASSIS_DAMAGED_BY_PROJECTILE = 2048
    MATERIAL_WITH_POSITIVE_DF_PIERCED_BY_EXPLOSION = 8192
    ATTACK_IS_DIRECT_PROJECTILE = 1048576
    ATTACK_IS_EXTERNAL_EXPLOSION = 2097152
    MATERIAL_WITH_POSITIVE_DF_NOT_PIERCED_WITH_DAMAGE_BY_PROJECTILE = 33554432
    IS_ANY_DAMAGE_MASK = 16 | 8192 | 256 | 33554432


def _kinds(shapes):
    """The kind and the live flag of each shape, without the set index."""
    return [{'kind': shape['kind'], 'live': shape['live']} for shape in shapes]


class ConditionShapeTest(unittest.TestCase):

    def test_a_choice_of_two_results_is_an_or_group_of_two_live_rows(self):
        group, shapes = crucible.post_battle(DAMAGE_OR_KILLS)
        self.assertEqual(group, 'or')
        self.assertEqual(_kinds(shapes), [{'kind': 'total', 'live': True}, {'kind': 'total', 'live': True}])
        # Each condition of a plain choice is a set of its own.
        self.assertEqual([shape['set'] for shape in shapes], [0, 1])

    def test_top_players_by_damage_waits_for_the_results(self):
        group, shapes = crucible.post_battle(TOP_FIVE)
        self.assertEqual((group, _kinds(shapes)), ('and', [{'kind': 'top', 'live': False}]))

    def test_damage_against_own_health_is_counted_live(self):
        self.assertEqual(_kinds(crucible.post_battle(TWICE_HEALTH)[1]), [{'kind': 'healthMultiple', 'live': True}])

    def test_a_sum_of_dealt_blocked_and_received_damage_is_counted_live(self):
        self.assertEqual(_kinds(crucible.post_battle(DEALT_BLOCKED_RECEIVED)[1]), [{'kind': 'sum', 'live': True}])

    def test_a_sum_with_a_key_the_client_has_no_figure_for_waits_for_the_results(self):
        conditions = _conditions(
            '[["results", [["plus", [["key", [["value", "damageDealt"]]], ["key", [["value", "xp"]]]]], '
            '["greaterOrEqual", [["value", 100.0]]]]]]')
        self.assertEqual(_kinds(crucible.post_battle(conditions)[1]), [{'kind': 'sum', 'live': False}])

    def test_damage_by_distance_and_by_time_are_counted_live(self):
        group, shapes = crucible.post_battle(FAR_DAMAGE_OR_KILLS)
        self.assertEqual((group, _kinds(shapes)),
                         ('or', [{'kind': 'damage', 'live': True}, {'kind': 'total', 'live': True}]))
        self.assertEqual(_kinds(crucible.post_battle(EARLY_DAMAGE)[1]), [{'kind': 'damage', 'live': True}])

    def test_kills_at_full_health_are_counted_live(self):
        self.assertEqual(_kinds(crucible.post_battle(FULL_HEALTH_KILLS)[1]), [{'kind': 'kills', 'live': True}])

    def test_penetrations_of_enemy_armor_are_counted_live(self):
        self.assertEqual(_kinds(crucible.post_battle(PENETRATIONS)[1]), [{'kind': 'total', 'live': True}])
        spec = crucible.parse_condition(*crucible.condition_sets(PENETRATIONS)[0][0])
        self.assertEqual((spec['keys'], spec['target']), (['piercingEnemyHits'], 10.0))

    def test_only_a_shell_that_pierces_the_armor_is_a_penetration(self):
        f = HIT_FLAGS
        direct = f.ATTACK_IS_DIRECT_PROJECTILE
        pierced = direct | f.MATERIAL_WITH_POSITIVE_DF_PIERCED_BY_PROJECTILE
        self.assertTrue(crucible.penetrated(pierced, f))
        # The shot that destroys the enemy penetrates too.
        self.assertTrue(crucible.penetrated(pierced | f.VEHICLE_KILLED, f))
        # High explosive that does damage without a penetration, and the splash of a shell.
        he_damage = direct | f.MATERIAL_WITH_POSITIVE_DF_NOT_PIERCED_WITH_DAMAGE_BY_PROJECTILE
        self.assertFalse(crucible.penetrated(he_damage, f))
        splash = f.ATTACK_IS_EXTERNAL_EXPLOSION | f.MATERIAL_WITH_POSITIVE_DF_PIERCED_BY_EXPLOSION
        self.assertFalse(crucible.penetrated(splash, f))
        # A ricochet, a shot that the armor stops, and a hit on the tracks only.
        self.assertFalse(crucible.penetrated(direct | f.RICOCHET, f))
        self.assertFalse(crucible.penetrated(direct | f.MATERIAL_WITH_POSITIVE_DF_NOT_PIERCED_BY_PROJECTILE, f))
        tracks = direct | f.DEVICE_PIERCED_BY_PROJECTILE | f.CHASSIS_DAMAGED_BY_PROJECTILE
        self.assertFalse(crucible.penetrated(tracks, f))
        # A hit on a vehicle that was already destroyed.
        self.assertFalse(crucible.penetrated(pierced | f.VEHICLE_WAS_DEAD_BEFORE_ATTACK, f))

    def test_an_award_waits_for_the_results(self):
        self.assertEqual(_kinds(crucible.post_battle(HIGH_CALIBER)[1]), [{'kind': 'achievement', 'live': False}])

    def test_a_shape_nobody_knows_waits_for_the_results(self):
        conditions = _conditions('[["clanKills", [["greaterOrEqual", [["value", 1.0]]]]]]')
        self.assertEqual(_kinds(crucible.post_battle(conditions)[1]), [{'kind': 'unknown', 'live': False}])

    def test_alternative_sets_of_several_conditions_carry_their_set_index(self):
        group, shapes = crucible.post_battle(TWO_SETS)
        self.assertEqual(group, 'or')
        self.assertEqual([(shape['kind'], shape['live'], shape['set']) for shape in shapes],
                         [('total', True, 0), ('kills', True, 0), ('total', True, 1), ('achievement', False, 1)])

    def test_the_sets_hold_the_raw_conditions(self):
        sets = crucible.condition_sets(TWO_SETS)
        self.assertEqual([[name for name, _ in conditions] for conditions in sets],
                         [['results', 'vehicleKills'], ['results', 'achievements']])
        self.assertEqual([[name for name, _ in conditions] for conditions in crucible.condition_sets(EARLY_DAMAGE)],
                         [['vehicleDamage']])
        self.assertEqual(crucible.condition_sets([]), [])

    def test_a_live_condition_names_its_target_and_what_it_counts(self):
        def only(conditions):
            [[(name, value)]] = crucible.condition_sets(conditions)
            return crucible.parse_condition(name, value)
        self.assertEqual(only(EARLY_DAMAGE), {'kind': 'damage', 'live': True, 'target': 2500.0, 'distance': None,
                                              'timeLimit': 300.0, 'eventCount': False, 'attackReason': None})
        self.assertEqual(only(FULL_HEALTH_KILLS), {'kind': 'kills', 'live': True, 'target': 3.0, 'fullHealth': True,
                                                   'classes': [], 'attackReason': None})
        self.assertEqual(only(TWICE_HEALTH), {'kind': 'healthMultiple', 'live': True, 'keys': ['damageDealt'],
                                              'multiplier': 2.0, 'target': 2.0})
        self.assertEqual(only(DEALT_BLOCKED_RECEIVED)['keys'],
                         ['damageDealt', 'damageBlockedByArmor', 'damageReceived'])
        far = crucible.condition_sets(FAR_DAMAGE_OR_KILLS)[0][0]
        self.assertEqual(crucible.parse_condition(*far)['distance'], 200.0)

    def test_a_named_attack_reason_is_kept(self):
        ramming = _conditions('[["vehicleDamage", [["attackReason", [["value", 2]]], '
                              '["greaterOrEqual", [["value", 500.0]]]]]]')
        [[(name, value)]] = crucible.condition_sets(ramming)
        self.assertEqual(crucible.parse_condition(name, value)['attackReason'], 2)

    def test_an_award_with_a_rule_is_live_by_its_record_name(self):
        names = {228: 'mainGun', 34: 'warrior', 36: 'sniper'}.get
        [[(name, value)]] = crucible.condition_sets(HIGH_CALIBER)
        self.assertEqual(crucible.parse_condition(name, value, names),
                         {'kind': 'achievement', 'live': True, 'award': 'mainGun', 'keys': ['damageDealt'],
                          'target': None, 'enemyHealthShare': 0.2, 'minimum': 1000.0, 'noAllyHits': True})
        top_gun = crucible.parse_condition('achievements', [['value', [34]]], names)
        self.assertEqual((top_gun['live'], top_gun['keys'], top_gun['target']), (True, ['kills'], 6.0))
        # An award with no rule, or with no name to look it up by, shows its text only.
        self.assertFalse(crucible.parse_condition('achievements', [['value', [36]]], names)['live'])
        self.assertFalse(crucible.parse_condition(name, value)['live'])
        self.assertFalse(crucible.parse_condition('achievements', [['value', [228, 34]]], names)['live'])

    def test_a_field_the_panel_cannot_count_turns_the_count_off(self):
        unseen = _conditions('[["vehicleDamage", [["whileEnemyInvisible", [["value", true]]], '
                             '["greaterOrEqual", [["value", 1000.0]]]]]]')
        team = _conditions('[["results", [["key", [["value", "damageDealt"]]], ["total", [["value", true]]], '
                           '["greaterOrEqual", [["value", 9000.0]]]]]]')
        diverse = _conditions('[["vehicleKills", [["classesDiversity", [["value", 3]]], '
                              '["greaterOrEqual", [["value", 3.0]]]]]]')
        for conditions in (unseen, team, diverse):
            self.assertEqual([shape['live'] for shape in crucible.post_battle(conditions)[1]], [False])

    def test_tuples_from_the_client_read_like_the_lists_of_the_dump(self):
        result = [('key', [('value', 'kills')]), ('greaterOrEqual', [('value', 5.0)])]
        conditions = [('postBattle', [('results', result)])]
        self.assertEqual(_kinds(crucible.post_battle(conditions)[1]), [{'kind': 'total', 'live': True}])

    def test_the_pre_battle_part_names_the_battle_types_and_the_tiers(self):
        self.assertEqual(crucible.pre_battle(DAMAGE_OR_KILLS),
                         {'bonusTypes': [1, 44, 46], 'levels': [6, 7, 8, 9, 10, 11]})

    def test_missing_conditions_accept_any_battle_and_any_tier(self):
        self.assertEqual(crucible.pre_battle([]), {'bonusTypes': [], 'levels': []})
        self.assertEqual(crucible.post_battle([]), ('and', []))

    def test_a_vehicle_fits_by_tier(self):
        self.assertTrue(crucible.vehicle_fits([6, 7, 8], 8))
        self.assertFalse(crucible.vehicle_fits([6, 7, 8], 5))
        # With no tiers from a mission, the Crucible floor of tier VI decides.
        self.assertFalse(crucible.vehicle_fits([], 5))
        self.assertTrue(crucible.vehicle_fits([], 6))
        self.assertIsNone(crucible.vehicle_fits([6], None))


class SeriesStateTest(unittest.TestCase):

    def test_the_active_series_is_active_whatever_its_tokens_say(self):
        self.assertEqual(crucible.series_state(True, {'attempts': 0, 'quests': 2}, 1), 'active')

    def test_no_shields_after_a_start_is_a_failed_series(self):
        self.assertEqual(crucible.series_state(False, {'attempts': 0, 'quests': 2, 'wins': 0}, 1), 'failed')

    def test_enough_wins_is_a_completed_series(self):
        self.assertEqual(crucible.series_state(False, {'attempts': 3, 'quests': 1, 'wins': 2}, 2), 'completed')
        self.assertEqual(crucible.series_state(False, {'attempts': 3, 'quests': 1, 'wins': 1}, 2), 'inactive')

    def test_a_series_with_no_tokens_yet_is_inactive_rather_than_an_error(self):
        # The client's own state function raises KeyError here, before the lobby has synced.
        self.assertEqual(crucible.series_state(False, {}, 1), 'inactive')
        self.assertEqual(crucible.series_state(False, None, 1), 'inactive')


def _raw(**overrides):
    raw = {
        'id': 57, 'name': 'Flash', 'difficulty': 2, 'attempts': 4, 'allowedCompletions': 2,
        'questCount': 3, 'progress': {'attempts': 3, 'quests': 2, 'wins': 0}, 'isActive': True,
        'endTime': 1792564260, 'expiringSoon': False, 'restartPrice': {'gold': 200},
        'restartCostText': '200', 'freeRestarts': 1,
    }
    raw.update(overrides)
    return raw


class SnapshotTest(unittest.TestCase):

    def test_a_series_reads_like_the_client_screen(self):
        entry = crucible.series_entry(_raw())
        self.assertEqual(entry['difficulty'], 'medium')
        self.assertEqual((entry['stage'], entry['completed'], entry['total']), (2, 1, 3))
        self.assertEqual((entry['shields'], entry['shieldsLimit']), (3, 4))

    def test_the_restart_price_names_its_currency(self):
        entry = crucible.series_entry(_raw(restartPrice={'credits': 250000}, restartCostText='250,000'))
        self.assertEqual((entry['restartCurrency'], entry['restartCost'], entry['restartCostText']),
                         ('credits', 250000, '250,000'))
        self.assertEqual(crucible.series_entry(_raw())['restartCurrency'], 'gold')

    def test_a_series_with_no_restart_price_has_none(self):
        entry = crucible.series_entry(_raw(restartPrice={}, restartCostText=''))
        self.assertEqual((entry['restartCurrency'], entry['restartCost'], entry['restartCostText']), ('', 0, ''))
        self.assertIsNone(crucible.restart_price(None))

    def test_the_free_restarts_never_go_below_zero(self):
        self.assertEqual(crucible.series_entry(_raw(freeRestarts=-1))['freeRestarts'], 0)

    def test_with_an_active_series_the_countdown_runs_to_its_end(self):
        series = [_raw(id=1, isActive=False, endTime=100), _raw(id=2, endTime=500)]
        self.assertEqual(crucible.build_snapshot(True, series, None, 8)['nearestEnd'], 500)

    def test_without_one_it_runs_to_the_first_end_of_an_open_series(self):
        series = [
            _raw(id=1, isActive=False, endTime=900),
            _raw(id=2, isActive=False, endTime=300, progress={'attempts': 3, 'quests': 1, 'wins': 2}),
            _raw(id=3, isActive=False, endTime=600),
            _raw(id=4, isActive=False, endTime=0),
        ]
        # Series 2 ends first, but it is completed, so nothing is left to play in it.
        self.assertEqual(crucible.build_snapshot(True, series, None, 8)['nearestEnd'], 600)

    def test_what_the_player_can_do_follows_the_client_buttons(self):
        series = [
            _raw(id=1, isActive=False, progress={'attempts': 4, 'quests': 0, 'wins': 0}),
            _raw(id=2, isActive=False, progress={'attempts': 0, 'quests': 2, 'wins': 0}, freeRestarts=1),
            _raw(id=3, isActive=False, progress={'attempts': 0, 'quests': 2, 'wins': 0}, freeRestarts=0),
            _raw(id=4, isActive=False, progress={'attempts': 3, 'quests': 1, 'wins': 2}),
        ]
        found = [entry['availability'] for entry in crucible.build_snapshot(True, series, None, 8)['series']]
        self.assertEqual(found, ['start', 'freeRestart', 'paidRestart', 'none'])

    def test_the_active_series_says_so_and_its_end_is_the_countdown(self):
        series = [_raw(id=1), _raw(id=2, isActive=False)]
        snapshot = crucible.build_snapshot(True, series, None, 8)
        self.assertEqual([entry['availability'] for entry in snapshot['series']], ['active', 'start'])
        self.assertTrue(snapshot['active']['soonest'])

    def test_every_series_that_ends_first_is_marked_soonest(self):
        series = [
            _raw(id=1, isActive=False, endTime=300),
            _raw(id=2, isActive=False, endTime=300),
            _raw(id=3, isActive=False, endTime=900),
            _raw(id=4, isActive=False, endTime=300, progress={'attempts': 3, 'quests': 1, 'wins': 2}),
        ]
        marked = [entry['soonest'] for entry in crucible.build_snapshot(True, series, None, 8)['series']]
        # Series 4 ends then too, but it is completed, so the banner does not count down to it.
        self.assertEqual(marked, [True, True, False, False])

    def test_the_banner_counts_the_series_that_end_first_by_what_they_cost(self):
        failed = {'attempts': 0, 'quests': 2, 'wins': 0}
        series = [
            _raw(id=1, isActive=False, endTime=300, progress={}),
            _raw(id=2, isActive=False, endTime=300, progress=failed, freeRestarts=1),
            _raw(id=3, isActive=False, endTime=300, progress=failed, freeRestarts=0,
                 restartPrice={'credits': 250000}),
            _raw(id=4, isActive=False, endTime=300, progress=failed, freeRestarts=0, restartPrice={'gold': 200}),
            _raw(id=5, isActive=False, endTime=300, progress=failed, freeRestarts=0, restartPrice={'gold': 200}),
            # A later end, and a completed series of the same end, are not in the set.
            _raw(id=6, isActive=False, endTime=900, progress={}),
            _raw(id=7, isActive=False, endTime=300, progress={'attempts': 3, 'quests': 1, 'wins': 2}),
        ]
        snapshot = crucible.build_snapshot(True, series, None, 8)
        self.assertEqual(snapshot['soonestSet'], {'free': 2, 'paid': [{'currency': 'credits', 'count': 1},
                                                                      {'currency': 'gold', 'count': 2}]})
        self.assertFalse(snapshot['allCompleted'])

    def test_when_the_first_set_is_completed_the_banner_moves_to_the_next(self):
        done = {'attempts': 3, 'quests': 1, 'wins': 2}
        series = [
            _raw(id=1, isActive=False, endTime=300, progress=done),
            _raw(id=2, isActive=False, endTime=300, progress=done),
            _raw(id=3, isActive=False, endTime=900, progress={}),
            _raw(id=4, isActive=False, endTime=900, progress=done),
            _raw(id=5, isActive=False, endTime=1200, progress={}),
        ]
        snapshot = crucible.build_snapshot(True, series, None, 8)
        self.assertEqual(snapshot['nearestEnd'], 900)
        self.assertEqual(snapshot['soonestSet'], {'free': 1, 'paid': []})
        # The card highlights the same series that the banner counts.
        self.assertEqual([entry['soonest'] for entry in snapshot['series']], [False, False, True, False, False])

    def test_with_every_series_completed_nothing_is_left_to_count(self):
        done = {'attempts': 3, 'quests': 1, 'wins': 2}
        snapshot = crucible.build_snapshot(True, [_raw(id=1, isActive=False, progress=done),
                                                  _raw(id=2, isActive=False, progress=done)], None, 8)
        self.assertTrue(snapshot['allCompleted'])
        self.assertEqual((snapshot['nearestEnd'], snapshot['soonestSet']), (0, {'free': 0, 'paid': []}))
        self.assertFalse(crucible.build_snapshot(True, [], None, 8)['allCompleted'])

    def test_no_end_at_all_is_zero(self):
        self.assertEqual(crucible.build_snapshot(True, [_raw(isActive=False, endTime=0)], None, 8)['nearestEnd'], 0)

    def test_a_series_that_never_started_shows_every_shield(self):
        entry = crucible.series_entry(_raw(isActive=False, progress={'attempts': 0, 'quests': 0, 'wins': 0}))
        self.assertEqual(entry['state'], 'inactive')
        self.assertEqual(entry['shields'], 4)
        self.assertEqual(entry['completed'], 0)

    def test_the_active_series_carries_its_mission_and_the_tiers_decide_the_fit(self):
        mission = {'questID': 'challenge:57:2', 'group': 'and', 'rows': [], 'levels': [6, 7, 8]}
        snapshot = crucible.build_snapshot(True, [_raw(), _raw(id=58, isActive=False)], mission, 9)
        self.assertEqual(snapshot['active']['id'], 57)
        self.assertEqual(snapshot['active']['mission'], mission)
        self.assertFalse(snapshot['vehicleFits'])
        self.assertEqual(len(snapshot['series']), 2)

    def test_with_no_active_series_the_crucible_floor_decides_the_fit(self):
        series = [_raw(isActive=False)]
        self.assertFalse(crucible.build_snapshot(True, series, None, 5)['vehicleFits'])
        self.assertTrue(crucible.build_snapshot(True, series, None, 6)['vehicleFits'])
        self.assertTrue(crucible.build_snapshot(True, series, None, 11)['vehicleFits'])
        self.assertIsNone(crucible.build_snapshot(True, series, None, None)['vehicleFits'])

    def test_the_vehicles_in_battle_are_listed_in_order(self):
        snapshot = crucible.build_snapshot(True, [_raw(isActive=False)], None, 8, ['LHMTV', 'IS-3A'])
        self.assertEqual(snapshot['inBattle'], ['IS-3A', 'LHMTV'])
        self.assertEqual(crucible.build_snapshot(True, [], None, 8)['inBattle'], [])

    def test_the_active_series_lists_every_mission_against_the_current_one(self):
        missions = [{'group': 'and', 'rows': [{'text': 'a'}]}, {'group': 'or', 'rows': [{'text': 'b'}]}, None]
        snapshot = crucible.build_snapshot(True, [_raw(progress={'quests': 2, 'attempts': 3, 'wins': 0})],
                                           None, 8, missions=missions)
        self.assertEqual([(entry['stage'], entry['state'], entry['group']) for entry in snapshot['active']['missions']],
                         [(1, 'done', 'and'), (2, 'current', 'or'), (3, 'next', 'and')])
        # A quest the client has not synced yet has no rows.
        self.assertEqual(snapshot['active']['missions'][2]['rows'], [])

    def test_no_active_series_means_no_active_entry(self):
        snapshot = crucible.build_snapshot(True, [_raw(isActive=False)], None, 8)
        self.assertIsNone(snapshot['active'])

    def test_the_rows_take_the_client_text_and_the_live_flag_by_position(self):
        packed = [{'titleData': 'Damage', 'descrData': 'Cause 3,500 HP of damage', 'iconKey': 'hurt_vehicles'},
                  {'titleData': 'Destroy', 'descrData': 'Destroy 3 enemy vehicles', 'iconKey': 'kill_vehicles'}]
        rows = crucible.mission_rows(packed, crucible.post_battle(DAMAGE_OR_KILLS)[1])
        self.assertEqual([row['text'] for row in rows], ['Cause 3,500 HP of damage', 'Destroy 3 enemy vehicles'])
        self.assertEqual([row['live'] for row in rows], [True, True])

    def test_packed_groups_are_read_depth_first_like_the_raw_sets(self):
        # The client packs an `and` group inside an `or` as an item with items of its own.
        packed = [{'conditionType': 'and', 'items': [{'descrData': 'a'}, {'descrData': 'b'}]},
                  {'conditionType': 'and', 'items': [{'descrData': 'c'}, {'descrData': 'd'}]}]
        rows = crucible.mission_rows(packed, crucible.post_battle(TWO_SETS)[1])
        self.assertEqual([(row['text'], row['set'], row['live']) for row in rows],
                         [('a', 0, True), ('b', 0, True), ('c', 1, True), ('d', 1, False)])

    def test_rows_that_cannot_be_matched_are_never_called_live(self):
        packed = [{'descrData': 'one'}, {'descrData': 'two'}]
        rows = crucible.mission_rows(packed, crucible.post_battle(TWICE_HEALTH)[1])
        self.assertEqual([row['live'] for row in rows], [False, False])


class TokenTest(unittest.TestCase):

    @staticmethod
    def _ids(series_id):
        return (series_id, dict((key, 'challenge:{0}:{1}'.format(name, series_id)) for key, name in (
            ('active', 'active'), ('attempts', 'attempt'), ('quests', 'quest'), ('wins', 'win'))))

    def test_the_tokens_name_the_active_series_and_the_progress(self):
        tokens = {'challenge:active:56': (0, 1), 'challenge:quest:56': (0, 1), 'challenge:attempt:56': (0, 4),
                  'challenge:win:57': (0, 1), 'other': (0, 9)}
        active_id, progress = crucible.read_tokens([self._ids(56), self._ids(57)], tokens)
        self.assertEqual(active_id, 56)
        self.assertEqual(progress, {56: {'attempts': 4, 'quests': 1, 'wins': 0},
                                    57: {'attempts': 0, 'quests': 0, 'wins': 1}})

    def test_an_active_token_with_no_count_is_no_active_series(self):
        active_id, _ = crucible.read_tokens([self._ids(56)], {'challenge:active:56': (0, 0)})
        self.assertEqual(active_id, 0)


class InBattleTest(unittest.TestCase):

    VEHICLES = [(1, 'IS-3A'), (2, 'LHMTV'), (3, 'Vz. 63P')]

    def test_a_vehicle_in_a_random_battle_counts(self):
        self.assertEqual(crucible.counted_in_battle(self.VEHICLES, {1: 1, 2: 44, 3: 46}, [1, 44, 46]),
                         ['IS-3A', 'LHMTV', 'Vz. 63P'])

    def test_a_vehicle_in_another_mode_does_not(self):
        # 32 is not a battle type of the Crucible missions: it is Blogger Battles (BOB).
        self.assertEqual(crucible.counted_in_battle(self.VEHICLES, {1: 1, 2: 32, 3: 32}, [1, 44, 46]), ['IS-3A'])

    def test_a_vehicle_with_no_record_counts(self):
        self.assertEqual(crucible.counted_in_battle(self.VEHICLES, {2: 32}, [1]), ['IS-3A', 'Vz. 63P'])

    def test_no_battle_types_read_means_the_random_battles(self):
        self.assertEqual(crucible.counted_in_battle(self.VEHICLES, {1: 46, 2: 32, 3: 1}, []), ['IS-3A', 'Vz. 63P'])


class TransportTest(unittest.TestCase):

    def test_the_transport_holds_what_a_battle_checks_and_counts(self):
        mission = {'questID': 'challenge:57:3', 'group': 'or', 'rows': [{'text': 'x'}], 'levels': [6]}
        snapshot = crucible.build_snapshot(True, [_raw()], mission, 8)
        data = crucible.transport(snapshot, DAMAGE_OR_KILLS, 500725877, 1792000000)
        active = data['active']
        self.assertEqual(data['accountDBID'], 500725877)
        self.assertEqual(active['questID'], 'challenge:57:3')
        self.assertEqual(active['bonusTypes'], [1, 44, 46])
        self.assertEqual(active['levels'], [6, 7, 8, 9, 10, 11])
        self.assertEqual(active['postBattle'][0][0], 'or')

    def test_a_battle_counts_by_its_type_and_the_tier_of_the_vehicle(self):
        active = crucible.transport(crucible.build_snapshot(True, [_raw()], {'rows': []}, 8),
                                    DAMAGE_OR_KILLS, 1, 2)['active']
        self.assertIsNone(crucible.battle_mismatch(active, 1, 8))
        self.assertIsNone(crucible.battle_mismatch(active, 46, 11))
        self.assertIn('battle type 32', crucible.battle_mismatch(active, 32, 8))
        self.assertIn('tier 5', crucible.battle_mismatch(active, 1, 5))
        self.assertEqual(crucible.battle_mismatch(None, 1, 8), 'no active series')
        # A level the client could not read decides nothing.
        self.assertIsNone(crucible.battle_mismatch(active, 1, None))

    def test_no_active_series_has_nothing_to_transport(self):
        snapshot = crucible.build_snapshot(True, [_raw(isActive=False)], None, 8)
        self.assertIsNone(crucible.transport(snapshot, [], 1, 2))


if __name__ == '__main__':
    unittest.main()
