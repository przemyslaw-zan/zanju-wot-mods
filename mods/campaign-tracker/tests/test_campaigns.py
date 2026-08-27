# -*- coding: utf-8 -*-
"""Tests for the campaign matching rules.

`campaigns` keeps no client imports at module scope, so its logic runs outside the game. The
objects it is given are the client's own, which the fakes here stand in for: a classifier
answers `matchVehicle`, a mission answers its classifier and its tier range.
"""
from __future__ import print_function, unicode_literals

import unittest

from zanju_ct import campaigns


class _Classifier(object):
    def __init__(self, accepted):
        self._accepted = accepted

    def matchVehicle(self, vehicle_type):
        return vehicle_type in self._accepted


class _RaisingClassifier(object):
    def matchVehicle(self, vehicle_type):
        raise ValueError('the client changed this call')


class _Mission(object):
    def __init__(self, classifier, min_level=1, max_level=11):
        self._classifier = classifier
        self._min_level = min_level
        self._max_level = max_level

    def getQuestClassifier(self):
        return self._classifier

    def getVehMinLevel(self):
        return self._min_level

    def getVehMaxLevel(self):
        return self._max_level


class OrderBranchesTest(unittest.TestCase):
    def test_sorts_into_campaign_order(self):
        self.assertEqual(campaigns.order_branches(['pm2', 'regular']), ['regular', 'pm2'])

    def test_keeps_the_exclusive_third_campaign_alone(self):
        self.assertEqual(campaigns.order_branches(['pm3']), ['pm3'])

    def test_drops_a_campaign_this_version_does_not_know(self):
        self.assertEqual(campaigns.order_branches(['pm4', 'pm2']), ['pm2'])

    def test_reports_nothing_for_an_empty_or_missing_list(self):
        self.assertEqual(campaigns.order_branches([]), [])
        self.assertEqual(campaigns.order_branches(None), [])


class LevelFitsTest(unittest.TestCase):
    def test_accepts_a_tier_inside_the_range(self):
        self.assertTrue(campaigns.level_fits(8, 5, 11))

    def test_accepts_the_bounds_themselves(self):
        self.assertTrue(campaigns.level_fits(5, 5, 11))
        self.assertTrue(campaigns.level_fits(11, 5, 11))

    def test_refuses_a_tier_below_the_minimum(self):
        self.assertFalse(campaigns.level_fits(4, 5, 11))

    def test_refuses_a_tier_above_the_maximum(self):
        self.assertFalse(campaigns.level_fits(10, 5, 9))

    def test_treats_a_missing_bound_as_no_bound(self):
        self.assertTrue(campaigns.level_fits(3, None, None))

    def test_refuses_an_unknown_tier(self):
        self.assertFalse(campaigns.level_fits(None, 5, 11))


class AcceptsVehicleTest(unittest.TestCase):
    def test_accepts_the_right_line_at_the_right_tier(self):
        mission = _Mission(_Classifier(['heavy']), min_level=5)
        self.assertTrue(campaigns.accepts_vehicle(mission, 'heavy', 8))

    def test_refuses_another_line(self):
        mission = _Mission(_Classifier(['heavy']))
        self.assertFalse(campaigns.accepts_vehicle(mission, 'light', 8))

    def test_refuses_the_right_line_at_the_wrong_tier(self):
        mission = _Mission(_Classifier(['heavy']), min_level=9)
        self.assertFalse(campaigns.accepts_vehicle(mission, 'heavy', 8))

    def test_refuses_a_mission_with_no_classifier(self):
        self.assertFalse(campaigns.accepts_vehicle(_Mission(None), 'heavy', 8))

    def test_refuses_a_mission_that_cannot_answer(self):
        mission = _Mission(_RaisingClassifier())
        self.assertFalse(campaigns.accepts_vehicle(mission, 'heavy', 8))


class FindMatchingMissionTest(unittest.TestCase):
    def test_returns_the_mission_of_the_line_the_vehicle_falls_in(self):
        light = _Mission(_Classifier(['light']))
        heavy = _Mission(_Classifier(['heavy']))
        self.assertIs(campaigns.find_matching_mission([light, heavy], 'heavy', 8), heavy)

    def test_returns_nothing_when_no_line_accepts_the_vehicle(self):
        light = _Mission(_Classifier(['light']))
        self.assertIsNone(campaigns.find_matching_mission([light], 'heavy', 8))

    def test_returns_nothing_when_the_tier_is_too_low_for_the_matching_line(self):
        heavy = _Mission(_Classifier(['heavy']), min_level=10)
        self.assertIsNone(campaigns.find_matching_mission([heavy], 'heavy', 8))

    def test_tolerates_an_empty_or_missing_selection(self):
        self.assertIsNone(campaigns.find_matching_mission([], 'heavy', 8))
        self.assertIsNone(campaigns.find_matching_mission(None, 'heavy', 8))


class BuildMissionIdTest(unittest.TestCase):
    """The banner label, built from the game's own translated short mission name."""

    def test_keeps_campaign_1_which_is_already_short(self):
        for short_name in ('LT-1', 'MT-1', 'HT-1', 'TD-1', 'SPG-13'):
            self.assertEqual(campaigns.build_mission_id(short_name), short_name)

    def test_cuts_a_campaign_2_line_to_two_letters(self):
        self.assertEqual(campaigns.build_mission_id('Union-10'), 'UN-10')
        self.assertEqual(campaigns.build_mission_id('Bloc-15'), 'BL-15')
        self.assertEqual(campaigns.build_mission_id('Alliance-8'), 'AL-8')
        self.assertEqual(campaigns.build_mission_id('Coalition-9'), 'CO-9')

    def test_cuts_a_campaign_3_line_to_two_letters(self):
        self.assertEqual(campaigns.build_mission_id('Vanguard-3'), 'VA-3')
        self.assertEqual(campaigns.build_mission_id('Ambush-7'), 'AM-7')
        self.assertEqual(campaigns.build_mission_id('Assistance-15'), 'AS-15')

    def test_keeps_the_whole_number(self):
        self.assertEqual(campaigns.build_mission_id('Union-100'), 'UN-100')

    def test_shortens_a_translated_line_the_same_way(self):
        # Nothing here knows the English names, which is what lets another language work.
        self.assertEqual(campaigns.build_mission_id('Koalicja-3'), 'KO-3')
        self.assertEqual(campaigns.build_mission_id('\u0421\u043e\u044e\u0437-10'), '\u0421\u041e-10')

    def test_accepts_a_dash_other_than_a_hyphen(self):
        self.assertEqual(campaigns.build_mission_id('Union\u201310'), 'UN\u201310')

    def test_keeps_a_line_already_written_in_capitals(self):
        self.assertEqual(campaigns.build_mission_id('SAU-4'), 'SAU-4')

    def test_keeps_a_name_it_cannot_split(self):
        # Not the shape this expects, so the game's own short name beats two letters of it.
        self.assertEqual(campaigns.build_mission_id('Sabotage'), 'Sabotage')

    def test_falls_back_to_the_line_and_the_number(self):
        self.assertEqual(campaigns.build_mission_id('', 'Vanguard', 3), 'VA-3')
        self.assertEqual(campaigns.build_mission_id(None, 'LT', 7), 'LT-7')

    def test_falls_back_to_the_number_alone_without_a_line(self):
        self.assertEqual(campaigns.build_mission_id(None, None, 7), '7')

    def test_ignores_a_short_name_the_client_failed_to_translate(self):
        unresolved = '#personal_missions_details:quest_1_1_short'
        self.assertEqual(campaigns.build_mission_id(unresolved, 'LT', 1), 'LT-1')

    def test_gives_nothing_when_there_is_nothing_to_build_from(self):
        self.assertEqual(campaigns.build_mission_id(None, None, None), '')


class PaceTest(unittest.TestCase):
    """25 to reach in 10 battles is 2.5 a battle -- what the readings below measure against."""

    def test_reads_the_total_as_a_percentage_of_the_average(self):
        # 2.5 a battle expects 5 by the second battle, so 6 stands at 120 percent of it.
        self.assertEqual(campaigns.pace(6, 25, 2, 10)['percent'], 120)
        self.assertEqual(campaigns.pace(4, 25, 2, 10)['percent'], 80)

    def test_reports_behind_when_the_total_trails_the_average(self):
        reading = campaigns.pace(7, 25, 3, 10)
        self.assertFalse(reading['ahead'])
        # 7.5 expected by the third battle, and 7 is 93 percent of that.
        self.assertEqual(reading['percent'], 93)

    def test_reports_ahead_when_the_total_leads_the_average(self):
        reading = campaigns.pace(8, 25, 3, 10)
        self.assertTrue(reading['ahead'])
        self.assertEqual(reading['percent'], 106)

    def test_counts_exactly_on_the_average_as_ahead(self):
        # 5 after 2 battles is exactly 2.5 a battle. On the average is not behind it.
        reading = campaigns.pace(5, 25, 2, 10)
        self.assertTrue(reading['ahead'])
        self.assertEqual(reading['percent'], 100)

    def test_never_reads_a_hundred_while_the_total_is_behind(self):
        # 1000 in 10 battles expects 500 by the fifth, and 498 is 99.6 percent of that.
        # Rounding to the nearest would paint a behind reading as one that is on the average.
        reading = campaigns.pace(498, 1000, 5, 10)
        self.assertFalse(reading['ahead'])
        self.assertEqual(reading['percent'], 99)

    def test_says_nothing_before_the_first_battle(self):
        self.assertIsNone(campaigns.pace(0, 25, 0, 10))

    def test_says_nothing_once_the_total_is_reached(self):
        self.assertIsNone(campaigns.pace(25, 25, 3, 10))
        self.assertIsNone(campaigns.pace(26, 25, 3, 10))

    def test_says_nothing_when_no_battles_are_left(self):
        self.assertIsNone(campaigns.pace(7, 25, 10, 10))

    def test_tolerates_missing_or_nonsense_numbers(self):
        self.assertIsNone(campaigns.pace(None, 25, 3, 10))
        self.assertIsNone(campaigns.pace(7, 0, 3, 10))
        self.assertIsNone(campaigns.pace(7, 25, 3, 0))


class NumeralTest(unittest.TestCase):
    def test_numbers_the_campaigns_the_way_players_name_them(self):
        self.assertEqual(campaigns.numeral('regular'), 'I')
        self.assertEqual(campaigns.numeral('pm2'), 'II')
        self.assertEqual(campaigns.numeral('pm3'), 'III')

    def test_gives_no_numeral_to_an_unknown_campaign(self):
        self.assertEqual(campaigns.numeral('pm4'), '')


if __name__ == '__main__':
    unittest.main()
