# -*- coding: utf-8 -*-
"""Tests for the battle progress of a Crucible mission.

The conditions are the verbatim ones of test_crucible, except the sets of TWO_SETS.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import unittest

from test_crucible import (DAMAGE_OR_KILLS, DEALT_BLOCKED_RECEIVED, DUELIST, EARLY_DAMAGE, FAR_DAMAGE_OR_KILLS,
                           FULL_HEALTH_KILLS, HIGH_CALIBER, TOP_FIVE, TWICE_HEALTH, TWO_SETS, _conditions)
from zanju_crt import progress

# The index of each attack reason in the client's ATTACK_REASONS.
SHOT = 0
FIRE = 1
RAM = 2
AWARD_NAMES = {228: 'mainGun', 34: 'warrior', 522: 'fighter', 523: 'duelist'}.get


class ResultsTest(unittest.TestCase):

    def test_damage_counts_towards_a_total(self):
        tracker = progress.Tracker(DAMAGE_OR_KILLS)
        tracker.on_damage(7, 1200, SHOT)
        tracker.on_damage(8, 400, FIRE)
        self.assertEqual(tracker.condition(0, 0)['value'], 1600)
        self.assertEqual(tracker.condition(0, 0)['state'], progress.OPEN)
        tracker.on_damage(7, 1900, SHOT)
        self.assertEqual(tracker.condition(0, 0)['state'], progress.MET)

    def test_kills_count_towards_a_total(self):
        tracker = progress.Tracker(DAMAGE_OR_KILLS)
        for target in (1, 2, 3):
            tracker.on_kill(target, 'heavyTank')
        self.assertEqual((tracker.condition(1, 0)['value'], tracker.condition(1, 0)['state']), (3, progress.MET))

    def test_a_sum_adds_dealt_blocked_and_received_damage(self):
        tracker = progress.Tracker(DEALT_BLOCKED_RECEIVED)
        tracker.set_health(1500, 1500)
        tracker.on_damage(1, 1000, SHOT)
        tracker.add_result('damageBlockedByArmor', 2000)
        tracker.set_health(1100, 1500)
        self.assertEqual(tracker.condition(0, 0)['value'], 3400)

    def test_each_spotted_enemy_counts_once(self):
        conditions = _conditions(
            '[["results", [["key", [["value", "spotted"]]], ["greaterOrEqual", [["value", 2.0]]]]]]')
        tracker = progress.Tracker(conditions)
        self.assertEqual([tracker.on_spot(target) for target in (1, 1, 2)], [True, False, True])
        self.assertEqual((tracker.condition(0, 0)['value'], tracker.condition(0, 0)['state']), (2, progress.MET))

    def test_the_summary_raises_the_totals_but_never_lowers_them(self):
        tracker = progress.Tracker(DEALT_BLOCKED_RECEIVED)
        tracker.on_damage(1, 1000, SHOT)
        tracker.raise_results({'damageDealt': 600, 'damageBlockedByArmor': 900})
        self.assertEqual(tracker.totals['damageDealt'], 1000)
        self.assertEqual(tracker.totals['damageBlockedByArmor'], 900)

    def test_damage_against_own_health_needs_the_health(self):
        tracker = progress.Tracker(TWICE_HEALTH)
        tracker.on_damage(1, 1000, SHOT)
        self.assertEqual(tracker.condition(0, 0), {'live': False, 'state': progress.OPEN, 'set': 0})
        tracker.set_health(1500, 1500)
        self.assertEqual(tracker.condition(0, 0)['target'], 3000)
        self.assertEqual(tracker.condition(0, 0)['value'], 1000)

    def test_a_condition_the_panel_cannot_count_is_not_live(self):
        tracker = progress.Tracker(TOP_FIVE)
        tracker.on_damage(1, 5000, SHOT)
        self.assertFalse(tracker.condition(0, 0)['live'])


class HealthTest(unittest.TestCase):

    def test_blocked_damage_against_own_health_needs_the_health(self):
        conditions = _conditions(
            '[["results", [["key", [["value", "damageBlockedByArmor"]]], ["greaterOrEqual", [["value", 2.0]]], '
            '["compareWithMaxHealth", [["value", true]]]]]]')
        tracker = progress.Tracker(conditions)
        tracker.set_health(1500, 1500)
        tracker.add_result('damageBlockedByArmor', 2400)
        self.assertEqual((tracker.condition(0, 0)['value'], tracker.condition(0, 0)['target']), (2400, 3000))
        tracker.add_result('damageBlockedByArmor', 600)
        self.assertEqual(tracker.condition(0, 0)['state'], progress.MET)

    def test_received_damage_is_the_drop_in_health(self):
        tracker = progress.Tracker(DEALT_BLOCKED_RECEIVED)
        tracker.set_health(1500, 1500)
        tracker.set_health(1200, 1500)
        tracker.set_health(-50, 1500)
        self.assertEqual(tracker.totals['damageReceived'], 1500)
        self.assertEqual(tracker.health, 0)

    def test_a_reconnect_counts_the_health_lost_before_it(self):
        tracker = progress.Tracker(DEALT_BLOCKED_RECEIVED)
        tracker.set_health(900, 1500)
        self.assertEqual(tracker.totals['damageReceived'], 600)
        self.assertFalse(tracker.full_health)

    def test_kills_at_full_health_stop_counting_after_damage(self):
        tracker = progress.Tracker(FULL_HEALTH_KILLS)
        tracker.set_health(1500, 1500)
        tracker.on_kill(1, 'lightTank')
        tracker.set_health(1400, 1500)
        tracker.on_kill(2, 'lightTank')
        item = tracker.condition(0, 0)
        self.assertEqual((item['value'], item['state']), (1, progress.CLOSED))
        self.assertEqual(tracker.totals['kills'], 2)

    def test_kills_at_full_health_that_were_met_stay_met(self):
        tracker = progress.Tracker(FULL_HEALTH_KILLS)
        tracker.set_health(1500, 1500)
        for target in (1, 2, 3):
            tracker.on_kill(target, 'SPG')
        tracker.set_health(10, 1500)
        self.assertEqual(tracker.condition(0, 0)['state'], progress.MET)


class DamageConditionTest(unittest.TestCase):

    def test_damage_from_far_counts_only_from_far_enough(self):
        tracker = progress.Tracker(FAR_DAMAGE_OR_KILLS)
        tracker.on_damage(1, 500, SHOT, distance=250.0)
        tracker.on_damage(1, 400, SHOT, distance=150.0)
        tracker.on_damage(2, 300, SHOT, distance=None)
        self.assertEqual(tracker.condition(0, 0)['value'], 500)

    def test_damage_within_view_range_compares_with_the_view_range(self):
        conditions = _conditions(
            '[["vehicleDamage", [["distance", [["value", 0]]], ["greaterOrEqual", [["value", 3000.0]]]]]]')
        tracker = progress.Tracker(conditions)
        tracker.on_damage(1, 500, SHOT, distance=300.0, view_range=380.0)
        tracker.on_damage(1, 400, SHOT, distance=420.0, view_range=380.0)
        tracker.on_damage(1, 300, SHOT, distance=300.0, view_range=None)
        self.assertEqual(tracker.condition(0, 0)['value'], 500)

    def test_a_negative_distance_is_at_most_that_far(self):
        conditions = _conditions(
            '[["vehicleDamage", [["distance", [["value", -50]]], ["greaterOrEqual", [["value", 1000.0]]]]]]')
        tracker = progress.Tracker(conditions)
        tracker.on_damage(1, 500, SHOT, distance=40.0)
        tracker.on_damage(1, 400, SHOT, distance=60.0)
        self.assertEqual(tracker.condition(0, 0)['value'], 500)

    def test_fire_and_ramming_count_towards_a_damage_condition(self):
        tracker = progress.Tracker(EARLY_DAMAGE)
        tracker.on_damage(1, 500, SHOT)
        tracker.on_damage(1, 200, FIRE)
        tracker.on_damage(1, 100, RAM)
        self.assertEqual(tracker.condition(0, 0)['value'], 800)
        self.assertEqual(tracker.totals['damageDealt'], 800)

    def test_a_condition_that_names_a_reason_counts_only_that_reason(self):
        conditions = _conditions(
            '[["vehicleDamage", [["attackReason", [["value", 2]]], ["greaterOrEqual", [["value", 500.0]]]]]]')
        tracker = progress.Tracker(conditions)
        tracker.on_damage(1, 500, SHOT)
        tracker.on_damage(1, 120, RAM)
        self.assertEqual(tracker.condition(0, 0)['value'], 120)

    def test_an_event_count_counts_the_hits(self):
        conditions = _conditions(
            '[["vehicleDamage", [["eventCount", [["value", true]]], ["greaterOrEqual", [["value", 10.0]]]]]]')
        tracker = progress.Tracker(conditions)
        tracker.on_damage(1, 500, SHOT)
        tracker.on_damage(2, 30, SHOT)
        self.assertEqual(tracker.condition(0, 0)['value'], 2)

    def test_the_time_limit_counts_from_the_battle_start(self):
        tracker = progress.Tracker(EARLY_DAMAGE)
        tracker.set_battle_start(1000.0)
        tracker.on_damage(1, 800, SHOT, server_time=1100.0)
        tracker.on_damage(1, 900, SHOT, server_time=1301.0)
        item = tracker.condition(0, 1200.0)
        self.assertEqual((item['value'], item['deadline'], item['timeLimit']), (800, 1300.0, 300.0))
        self.assertEqual(item['state'], progress.OPEN)
        self.assertEqual(tracker.condition(0, 1300.0)['state'], progress.CLOSED)

    def test_before_the_battle_starts_there_is_no_deadline_yet(self):
        tracker = progress.Tracker(EARLY_DAMAGE)
        item = tracker.condition(0, 50.0)
        self.assertEqual((item['deadline'], item['timeLimit'], item['state']), (None, 300.0, progress.OPEN))


class KillConditionTest(unittest.TestCase):

    def test_a_kill_condition_can_name_the_classes_that_count(self):
        conditions = _conditions(
            '[["vehicleKills", [["classes", [["value", ["AT-SPG"]]]], ["greaterOrEqual", [["value", 2.0]]]]]]')
        tracker = progress.Tracker(conditions)
        tracker.on_kill(1, 'AT-SPG')
        tracker.on_kill(2, 'heavyTank')
        self.assertEqual(tracker.condition(0, 0)['value'], 1)

    def test_a_kill_by_fire_or_ramming_counts(self):
        conditions = _conditions('[["vehicleKills", [["greaterOrEqual", [["value", 2.0]]]]]]')
        tracker = progress.Tracker(conditions)
        tracker.on_damage(1, 50, FIRE)
        tracker.on_kill(1, 'mediumTank')
        tracker.on_damage(2, 80, RAM)
        tracker.on_kill(2, 'mediumTank')
        self.assertEqual(tracker.condition(0, 0)['value'], 2)

    def test_a_kill_condition_that_names_a_reason_takes_the_reason_of_the_last_hit(self):
        conditions = _conditions(
            '[["vehicleKills", [["attackReason", [["value", 2]]], ["greaterOrEqual", [["value", 2.0]]]]]]')
        tracker = progress.Tracker(conditions)
        tracker.on_damage(1, 300, RAM)
        tracker.on_damage(1, 50, SHOT)
        tracker.on_kill(1, 'mediumTank')
        tracker.on_damage(2, 80, RAM)
        tracker.on_kill(2, 'mediumTank')
        self.assertEqual(tracker.condition(0, 0)['value'], 1)


def _diverse(kills, classes):
    return _conditions('[["vehicleKills", [["classesDiversity", [["value", %d]]], '
                       '["greaterOrEqual", [["value", %d.0]]]]]]' % (classes, kills))


class DiverseKillsTest(unittest.TestCase):

    def test_a_second_kill_of_one_class_does_not_count_when_each_kill_needs_a_new_class(self):
        tracker = progress.Tracker(_diverse(2, 2))
        tracker.on_kill(1, 'heavyTank')
        tracker.on_kill(2, 'heavyTank')
        self.assertEqual((tracker.condition(0, 0)['value'], tracker.condition(0, 0)['state']), (1, progress.OPEN))
        tracker.on_kill(3, 'mediumTank')
        # With the classes covered, every kill counts, as in the other kill conditions.
        self.assertEqual((tracker.condition(0, 0)['value'], tracker.condition(0, 0)['state']), (3, progress.MET))

    def test_a_kill_of_one_class_counts_again_while_enough_kills_are_left_for_the_classes(self):
        tracker = progress.Tracker(_diverse(3, 2))
        for target in (1, 2, 3):
            tracker.on_kill(target, 'heavyTank')
        self.assertEqual(tracker.condition(0, 0)['value'], 2)
        tracker.on_kill(4, 'lightTank')
        self.assertEqual((tracker.condition(0, 0)['value'], tracker.condition(0, 0)['state']), (4, progress.MET))

    def test_the_classes_come_in_the_order_of_the_client_filters(self):
        tracker = progress.Tracker(_diverse(3, 3))
        for target, vehicle_class in enumerate(('SPG', 'lightTank', 'AT-SPG', 'lightTank')):
            tracker.on_kill(target, vehicle_class)
        self.assertEqual(tracker.classes(0), ['lightTank', 'AT-SPG', 'SPG'])

    def test_a_kill_of_a_class_the_condition_leaves_out_adds_no_class(self):
        conditions = _conditions('[["vehicleKills", [["classes", [["value", ["heavyTank", "AT-SPG"]]]], '
                                 '["classesDiversity", [["value", 2]]], ["greaterOrEqual", [["value", 2.0]]]]]]')
        tracker = progress.Tracker(conditions)
        tracker.on_kill(1, 'lightTank')
        tracker.on_kill(2, 'AT-SPG')
        self.assertEqual((tracker.condition(0, 0)['value'], tracker.classes(0)), (1, ['AT-SPG']))


class AwardTest(unittest.TestCase):

    def test_high_caliber_asks_for_a_fifth_of_the_enemy_health(self):
        tracker = progress.Tracker(HIGH_CALIBER, AWARD_NAMES)
        tracker.on_damage(1, 1500, SHOT)
        self.assertFalse(tracker.condition(0, 0)['live'])
        tracker.set_enemy_health(20000)
        item = tracker.condition(0, 0)
        self.assertEqual((item['value'], item['target'], item['state']), (1500, 4000.0, progress.OPEN))

    def test_high_caliber_never_asks_for_less_than_1000(self):
        tracker = progress.Tracker(HIGH_CALIBER, AWARD_NAMES)
        tracker.set_enemy_health(3000)
        self.assertEqual(tracker.condition(0, 0)['target'], 1000.0)

    def test_a_direct_shot_on_an_ally_ends_high_caliber_whatever_the_damage(self):
        tracker = progress.Tracker(HIGH_CALIBER, AWARD_NAMES)
        tracker.set_enemy_health(20000)
        tracker.on_damage(1, 5000, SHOT)
        self.assertEqual(tracker.condition(0, 0)['state'], progress.MET)
        tracker.on_ally_hit()
        item = tracker.condition(0, 0)
        self.assertEqual((item['state'], item['allyHit']), (progress.CLOSED, True))
        self.assertTrue(progress.summary(tracker, 0).endswith('an ally was hit by a direct shot'))

    def test_the_rule_on_allies_shows_on_the_row_and_breaks_with_a_hit(self):
        tracker = progress.Tracker(HIGH_CALIBER, AWARD_NAMES)
        tracker.set_enemy_health(20000)
        rows = [{'text': 'Earn the High Caliber award', 'icon': 'achievement'}]
        self.assertEqual(progress.panel_rows(tracker, rows, 0)[0]['rules'], [{'key': 'noAllyHits', 'broken': False}])
        tracker.on_ally_hit()
        self.assertEqual(progress.panel_rows(tracker, rows, 0)[0]['rules'], [{'key': 'noAllyHits', 'broken': True}])

    def test_an_ally_hit_does_not_touch_other_conditions(self):
        tracker = progress.Tracker(DAMAGE_OR_KILLS)
        tracker.on_ally_hit()
        tracker.on_damage(1, 4000, SHOT)
        self.assertEqual(tracker.condition(0, 0)['state'], progress.MET)
        self.assertNotIn('rules', progress.panel_rows(tracker, [{'text': 'a'}, {'text': 'b'}], 0)[0])

    def test_top_gun_asks_for_six_kills(self):
        tracker = progress.Tracker(_conditions('[["achievements", [["value", [34]]]]]'), AWARD_NAMES)
        for target in range(6):
            tracker.on_kill(target, 'lightTank')
        item = tracker.condition(0, 0)
        self.assertEqual((item['value'], item['target'], item['state']), (6, 6.0, progress.MET))

    def test_fighter_is_met_at_four_or_five_kills_and_a_sixth_ends_it(self):
        tracker = progress.Tracker(_conditions('[["achievements", [["value", [522]]]]]'), AWARD_NAMES)
        states = []
        for target in range(6):
            tracker.on_kill(target, 'lightTank')
            states.append(tracker.condition(0, 0)['state'])
        self.assertEqual(states, [progress.OPEN] * 3 + [progress.MET] * 2 + [progress.CLOSED])
        rows = progress.panel_rows(tracker, [{'text': 'Earn the Fighter award', 'icon': 'achievement'}], 0)
        self.assertEqual(rows[0]['rules'], [{'key': 'fighter_descr', 'broken': False},
                                            {'key': 'fighter_maximum', 'broken': True}])

    def test_fighter_or_top_gun_stays_met_from_four_kills_on(self):
        either = _conditions('[["or", [["achievements", [["value", [522]]]], ["achievements", [["value", [34]]]]]]]')
        tracker = progress.Tracker(either, AWARD_NAMES)
        met = []
        for target in range(7):
            tracker.on_kill(target, 'lightTank')
            met.append(progress.MET in tracker.set_states(0))
        self.assertEqual(met, [False, False, False, True, True, True, True])
        self.assertEqual(tracker.set_states(0), [progress.CLOSED, progress.MET])

    def test_duelist_counts_the_kills_of_enemies_that_damaged_the_player_in_any_order(self):
        tracker = progress.Tracker(DUELIST, AWARD_NAMES)
        tracker.on_damaged_by(1)
        tracker.on_kill(1, 'heavyTank')
        tracker.on_kill(2, 'mediumTank')
        tracker.on_damaged_by(3)
        self.assertEqual(tracker.condition(0, 0)['value'], 1)
        # Damage after the kill counts too: the server judges the award after the battle.
        tracker.on_damaged_by(2)
        item = tracker.condition(0, 0)
        self.assertEqual((item['value'], item['target'], item['state']), (2, 2.0, progress.MET))
        rows = progress.panel_rows(tracker, [{'text': 'Earn the Duelist award', 'icon': 'achievement'}], 0)
        self.assertEqual(rows[0]['rules'], [{'key': 'duelist_descr', 'broken': False}])

    def test_an_award_without_its_name_shows_no_progress(self):
        tracker = progress.Tracker(HIGH_CALIBER)
        tracker.set_enemy_health(20000)
        self.assertFalse(tracker.condition(0, 0)['live'])


class SetTest(unittest.TestCase):

    def test_a_set_is_met_when_all_its_conditions_are(self):
        tracker = progress.Tracker(TWO_SETS)
        tracker.set_health(1500, 1500)
        tracker.on_damage(1, 2100, SHOT)
        self.assertEqual(tracker.set_states(0), [progress.OPEN, progress.OPEN])
        tracker.on_kill(1, 'lightTank')
        self.assertEqual(tracker.set_states(0), [progress.MET, progress.OPEN])

    def test_a_set_with_a_closed_condition_is_closed(self):
        tracker = progress.Tracker(TWO_SETS)
        tracker.set_health(1500, 1500)
        tracker.set_health(1000, 1500)
        self.assertEqual(tracker.set_states(0), [progress.CLOSED, progress.OPEN])


class SummaryTest(unittest.TestCase):

    def test_the_end_line_has_each_condition_and_the_totals(self):
        tracker = progress.Tracker(DAMAGE_OR_KILLS)
        tracker.on_damage(1, 1750, SHOT)
        self.assertEqual(progress.summary(tracker, 0), '1: 1750/3500 open; 2: 0/3 open | totals: damageDealt 1750')
        self.assertEqual(progress.summary(progress.Tracker(TOP_FIVE), 0), '1: not counted | totals: none')

    def test_the_end_line_names_the_kills_and_classes_of_a_condition_with_different_classes(self):
        tracker = progress.Tracker(_diverse(2, 2))
        self.assertEqual(progress.summary(tracker, 0), '1: 0/2 open (0 kills of no class) | totals: none')
        tracker.on_kill(1, 'heavyTank')
        tracker.on_kill(2, 'heavyTank')
        self.assertEqual(progress.summary(tracker, 0), '1: 1/2 open (2 kills of heavyTank) | totals: kills 2')


class PanelRowsTest(unittest.TestCase):

    ROWS = [{'text': 'Cause 3,500 HP of damage', 'icon': 'hurt_vehicles', 'live': True},
            {'text': 'Destroy 3 enemy vehicles', 'icon': 'kill_vehicles', 'live': True}]

    def test_rows_take_the_progress_of_their_condition(self):
        tracker = progress.Tracker(DAMAGE_OR_KILLS)
        tracker.on_damage(1, 1750, SHOT)
        rows = progress.panel_rows(tracker, self.ROWS, 0)
        self.assertEqual([row['set'] for row in rows], [0, 1])
        self.assertEqual((rows[0]['valueText'], rows[0]['targetText'], rows[0]['ratio']), ('1,750', '3,500', 0.5))
        self.assertEqual(rows[1]['state'], progress.OPEN)

    def test_the_ratio_stops_at_full(self):
        tracker = progress.Tracker(DAMAGE_OR_KILLS)
        tracker.on_damage(1, 9000, SHOT)
        self.assertEqual(progress.panel_rows(tracker, self.ROWS, 0)[0]['ratio'], 1.0)

    def test_rows_that_do_not_match_the_conditions_show_no_progress(self):
        tracker = progress.Tracker(EARLY_DAMAGE)
        rows = progress.panel_rows(tracker, self.ROWS, 0)
        self.assertEqual([row['live'] for row in rows], [False, False])
        self.assertEqual([row['set'] for row in rows], [0, 1])

    def test_after_a_reconnect_no_row_counts_but_a_time_limit_still_runs(self):
        tracker = progress.Tracker(EARLY_DAMAGE)
        tracker.set_battle_start(1000.0)
        rows = progress.panel_rows(tracker, self.ROWS[:1], 1100.0, counting=False)
        self.assertEqual(rows[0]['live'], False)
        self.assertEqual((rows[0]['deadline'], rows[0]['timeLimit']), (1300.0, 300.0))
        self.assertNotIn('valueText', rows[0])

    def test_a_condition_with_different_classes_lists_the_classes_destroyed_from_the_start(self):
        tracker = progress.Tracker(_diverse(2, 2))
        rows = self.ROWS[1:]
        self.assertEqual(progress.panel_rows(tracker, rows, 0)[0]['classes'], [])
        tracker.on_kill(1, 'mediumTank')
        tracker.on_kill(2, 'lightTank')
        self.assertEqual(progress.panel_rows(tracker, rows, 0)[0]['classes'], ['lightTank', 'mediumTank'])
        self.assertNotIn('classes', progress.panel_rows(progress.Tracker(FULL_HEALTH_KILLS), rows, 0)[0])

    def test_a_number_format_from_the_client_writes_the_figures(self):
        tracker = progress.Tracker(DAMAGE_OR_KILLS)
        rows = progress.panel_rows(tracker, self.ROWS, 0, number_format=lambda value: '<%d>' % value)
        self.assertEqual(rows[0]['targetText'], '<3500>')


if __name__ == '__main__':
    unittest.main()
