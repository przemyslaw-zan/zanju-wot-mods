# -*- coding: utf-8 -*-
"""Tests for the directives collector.

The client APIs are reached through lazy imports that fail outside the game, so the module
degrades to an empty snapshot here. What is worth pinning is the shaping logic: which rows
survive, how they are split and sorted, and the totals — plus the degradation contract
itself, since the collector feeds a window the game is in the middle of building.
"""
from __future__ import unicode_literals

import logging
import unittest

from zanju_dh import collector


class SilentLogger(logging.Logger):

    def __init__(self):
        logging.Logger.__init__(self, 'test')
        self.exceptions = []
        self.addHandler(logging.NullHandler())

    def exception(self, message, *args, **kwargs):
        self.exceptions.append(message)


class FakeVehicle(object):
    """Stands in for the vehicle in the garage, for the auto-resupply flag only."""

    def __init__(self, auto=False):
        self._auto = auto

    def isAutoBattleBoosterEquip(self):
        return self._auto


class FakeBooster(object):
    """Stands in for a BattleBooster GUI item."""

    def __init__(self, int_cd, name, count, crew=False, usable=True, learnt=False):
        self.intCD = int_cd
        self.userName = name
        self.inventoryCount = count
        self._crew = crew
        self._usable = usable
        self._learnt = learnt

    def isCrewBooster(self):
        return self._crew

    def isAffectsOnVehicle(self, vehicle):
        return self._usable

    def isAffectedSkillLearnt(self, vehicle):
        return self._learnt


class EmptySnapshotTest(unittest.TestCase):

    def test_shape_is_stable(self):
        snapshot = collector.empty_snapshot()
        self.assertEqual(
            sorted(snapshot),
            ['autoResupply', 'categories', 'hasVehicle', 'resupplyWarning', 'vehicleName'],
        )
        self.assertEqual([group['category'] for group in snapshot['categories']],
                         list(collector.CATEGORY_ORDER))

    def test_collect_degrades_without_a_client(self):
        logger = SilentLogger()
        self.assertEqual(collector.collect(logger), collector.empty_snapshot())
        self.assertTrue(logger.exceptions, 'the failure should be reported')


class DescribeTest(unittest.TestCase):

    def setUp(self):
        self.logger = SilentLogger()

    def describe(self, item, vehicle=None, equipped=frozenset(), show_unowned=False):
        return collector._describe(item, vehicle, equipped, show_unowned, self.logger)

    def test_reads_a_directive_the_player_owns(self):
        entry = self.describe(FakeBooster(52987, 'Repairs', 75, crew=True), vehicle=object())
        self.assertEqual(entry['intCD'], 52987)
        self.assertEqual(entry['name'], 'Repairs')
        self.assertEqual(entry['count'], 75)
        self.assertEqual(entry['category'], collector.CATEGORY_CREW_GRANT)
        self.assertFalse(entry['equipped'])

    def test_drops_everything_when_no_tank_is_selected(self):
        # Nothing can be fitted without a vehicle, so nothing is offered.
        self.assertIsNone(self.describe(FakeBooster(1, 'Repairs', 3, crew=True)))

    def test_skips_directives_the_player_does_not_own(self):
        # The items cache lists every directive that exists, not just owned ones.
        self.assertIsNone(self.describe(FakeBooster(1, 'Never bought', 0)))

    def test_keeps_a_fitted_directive_with_an_empty_depot(self):
        # Fitting one moves it out of the depot, so the count can be zero while it is in use.
        entry = self.describe(FakeBooster(52475, 'Improved Aiming', 0), equipped=frozenset([52475]))
        self.assertIsNotNone(entry)
        self.assertEqual(entry['count'], 0)
        self.assertTrue(entry['equipped'])

    def test_equipment_directives_get_their_own_section(self):
        vehicle = object()
        entry = self.describe(FakeBooster(2, 'Improved Aiming', 3, crew=False), vehicle=vehicle)
        self.assertEqual(entry['category'], collector.CATEGORY_EQUIPMENT)

    def test_a_trained_perk_means_the_directive_improves_it(self):
        vehicle = object()
        entry = self.describe(FakeBooster(1, 'Repairs', 3, crew=True, learnt=True), vehicle=vehicle)
        self.assertEqual(entry['category'], collector.CATEGORY_CREW_IMPROVE)

    def test_an_untrained_perk_means_the_directive_grants_it(self):
        vehicle = object()
        entry = self.describe(FakeBooster(1, 'Repairs', 3, crew=True, learnt=False), vehicle=vehicle)
        self.assertEqual(entry['category'], collector.CATEGORY_CREW_GRANT)

    def test_drops_directives_that_do_not_fit_the_tank(self):
        vehicle = object()
        self.assertIsNone(self.describe(FakeBooster(2, 'Off-Road Driving', 3, usable=False), vehicle=vehicle))

    def test_keeps_the_fitted_directive_even_if_it_no_longer_fits(self):
        # Whatever is actually mounted must stay visible, or the window would contradict the
        # tank it is describing.
        vehicle = object()
        entry = self.describe(
            FakeBooster(9, 'Fitted', 1, usable=False), vehicle=vehicle, equipped=frozenset([9]))
        self.assertIsNotNone(entry)
        self.assertTrue(entry['equipped'])


class ShowUnownedTest(unittest.TestCase):
    """Listing what the player could buy, so the window can send them to the store."""

    def setUp(self):
        self.logger = SilentLogger()

    def describe(self, item, vehicle=None, equipped=frozenset(), show_unowned=True):
        return collector._describe(item, vehicle, equipped, show_unowned, self.logger)

    def test_lists_a_directive_the_player_owns_none_of(self):
        entry = self.describe(FakeBooster(7, 'Repairs', 0), vehicle=object())
        self.assertIsNotNone(entry)
        self.assertEqual(entry['count'], 0)
        self.assertFalse(entry['owned'])

    def test_hidden_again_when_the_option_is_off(self):
        self.assertIsNone(self.describe(
            FakeBooster(7, 'Repairs', 0), vehicle=object(), show_unowned=False))

    def test_still_drops_one_the_tank_cannot_take(self):
        # "Owns none of it" is not a reason to offer something that would not fit anyway.
        self.assertIsNone(self.describe(
            FakeBooster(7, 'Off-Road Driving', 0, usable=False), vehicle=object()))

    def test_still_needs_a_tank_selected(self):
        self.assertIsNone(self.describe(FakeBooster(7, 'Repairs', 0)))

    def test_owned_directives_are_marked_as_owned(self):
        entry = self.describe(FakeBooster(7, 'Repairs', 3), vehicle=object())
        self.assertTrue(entry['owned'])

    def test_the_fitted_one_counts_as_owned_with_an_empty_depot(self):
        # Fitting moves it out of the depot, so its count reads zero while it is in use --
        # that must not turn the mounted directive into a buy button.
        entry = self.describe(FakeBooster(7, 'Repairs', 0), vehicle=object(),
                              equipped=frozenset([7]))
        self.assertTrue(entry['owned'])
        self.assertTrue(entry['equipped'])

    def test_sorted_in_with_the_rest_rather_than_split_off(self):
        # What a directive does is what the sections are for; owning it is a property of the
        # row, so an unowned crew directive still lands in its own effect section.
        entry = self.describe(FakeBooster(7, 'Repairs', 0, crew=True, learnt=True),
                              vehicle=object())
        self.assertEqual(entry['category'], collector.CATEGORY_CREW_IMPROVE)


class CategoryTest(unittest.TestCase):

    def entries(self):
        return [
            {'name': 'Repairs', 'count': 75},
            {'name': 'Adrenaline', 'count': 2},
            {'name': 'brothers in arms', 'count': 9},
        ]

    def test_totals_count_directives_not_types(self):
        group = collector._category(collector.CATEGORY_CREW_GRANT, self.entries())
        self.assertEqual(group['total'], 86)

    def test_sorts_case_insensitively_so_the_list_does_not_reshuffle(self):
        group = collector._category(collector.CATEGORY_CREW_GRANT, self.entries())
        self.assertEqual([entry['name'] for entry in group['directives']],
                         ['Adrenaline', 'brothers in arms', 'Repairs'])

    def test_empty_category_totals_zero(self):
        group = collector._category(collector.CATEGORY_EQUIPMENT, [])
        self.assertEqual(group['total'], 0)
        self.assertEqual(group['directives'], [])


class AutoResupplyTest(unittest.TestCase):
    """None means "nothing to report", and the window must be able to tell that from False:
    a failed read that looked like "disabled" would offer a toggle acting on a guess."""

    def setUp(self):
        self.logger = SilentLogger()

    def test_reads_the_setting_from_the_vehicle(self):
        self.assertTrue(collector.auto_resupply(FakeVehicle(auto=True), self.logger))
        self.assertFalse(collector.auto_resupply(FakeVehicle(auto=False), self.logger))

    def test_reports_nothing_without_a_vehicle(self):
        self.assertIsNone(collector.auto_resupply(None, self.logger))

    def test_reports_nothing_when_the_client_does_not_offer_the_setting(self):
        self.assertIsNone(collector.auto_resupply(object(), self.logger))

    def test_accepts_the_setting_as_a_property(self):
        # It is a method on this client while its siblings on the same class are properties;
        # a future build swapping it over must not read as "disabled".
        class PropertyVehicle(object):
            isAutoBattleBoosterEquip = True

        self.assertTrue(collector.auto_resupply(PropertyVehicle(), self.logger))

    def test_reports_nothing_when_the_read_fails(self):
        class BrokenVehicle(object):

            def isAutoBattleBoosterEquip(self):
                raise ValueError('no')

        self.assertIsNone(collector.auto_resupply(BrokenVehicle(), self.logger))
        self.assertTrue(self.logger.exceptions, 'the failure should be reported')


class ResupplyWarningTest(unittest.TestCase):
    """Fitting the last copy is the one case where leaving auto-resupply on spends money:
    with nothing left in the depot the client buys a replacement after the battle."""

    def categories(self, count, equipped=True):
        return [{'category': collector.CATEGORY_EQUIPMENT, 'total': count, 'directives': [
            {'name': 'Improved Aiming', 'count': count, 'equipped': equipped},
        ]}]

    def test_warns_about_the_last_one(self):
        self.assertTrue(collector.warns_about_resupply(True, self.categories(0)))

    def test_silent_while_the_depot_still_has_spares(self):
        self.assertFalse(collector.warns_about_resupply(True, self.categories(4)))

    def test_silent_when_auto_resupply_is_off(self):
        # Nothing is bought, so running the depot dry costs nothing.
        self.assertFalse(collector.warns_about_resupply(False, self.categories(0)))

    def test_silent_when_the_setting_could_not_be_read(self):
        self.assertFalse(collector.warns_about_resupply(None, self.categories(0)))

    def test_ignores_directives_that_are_not_fitted(self):
        # Owning none of something is only a problem for the one going into battle.
        self.assertFalse(collector.warns_about_resupply(True, self.categories(0, equipped=False)))

    def test_silent_with_nothing_fitted_at_all(self):
        self.assertFalse(collector.warns_about_resupply(True, []))


if __name__ == '__main__':
    unittest.main()
