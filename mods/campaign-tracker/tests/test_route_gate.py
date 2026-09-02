# -*- coding: utf-8 -*-
"""Tests for the lobby-route half of the widgets' visibility.

Every route below is verbatim from the client. All 58 registered states whose route names a
hangar were enumerated from a running client on 2.3.1.3 with each mode extension loaded, so the
fixture is the shape of the real route space rather than the screens somebody happened to open.
"""
from __future__ import print_function, unicode_literals

import unittest

from zanju_ct import route_gate

# One entry per garage the lobby registers. A garage root is the route itself or the route plus
# `{root}`; anything deeper is a screen drawn over that garage.
GARAGE_ROOTS = (
    'subScope/subLayer/hangar',
    'subScope/subLayer/comp7/hangar',
    'subScope/subLayer/comp7Light/hangar',
    'subScope/subLayer/frontline/hangar',
    'subScope/subLayer/lastStand/hangar',
    'subScope/subLayer/funRandomHangar',
    'subScope/subLayer/legacyHangar',
    'subScope/subLayer/battleRoyale/battleRoyaleHangar',
)

# The leaves the client hangs off a garage root. None of these is the bare garage.
SCREENS = (
    'allVehicles',
    'easyTankEquip',
    'editVehiclePlaylists',
    'loadout',
    'loadout/shells',
    'loadout/equipment',
    'loadout/instructions',
    'loadout/consumables',
    'loadout/battleAbilities',
    'loadout/ls_consumables',
)


class BareHangarRouteTest(unittest.TestCase):

    def test_the_plain_garage_shows_the_widgets(self):
        self.assertTrue(route_gate.is_bare_hangar_route('subScope/subLayer/hangar/{root}'))

    def test_a_garage_still_navigating_shows_the_widgets(self):
        # The machine reports the route without its leaf while a navigation is in flight.
        self.assertTrue(route_gate.is_bare_hangar_route('subScope/subLayer/hangar'))

    def test_a_mode_that_folds_its_name_into_the_segment_shows_the_widgets(self):
        # Three modes do not prefix a path. They rename the segment, so an equality test on
        # 'hangar' misses them and the widgets stay hidden in those garages.
        for route in ('subScope/subLayer/funRandomHangar',
                      'subScope/subLayer/funRandomHangar/{root}',
                      'subScope/subLayer/legacyHangar',
                      'subScope/subLayer/battleRoyale/battleRoyaleHangar'):
            self.assertTrue(route_gate.is_bare_hangar_route(route), route)

    def test_a_screen_over_the_garage_hides_the_widgets(self):
        for route in ('subScope/subLayer/hangar/editVehiclePlaylists',
                      'subScope/subLayer/hangar/loadout/instructions',
                      'subScope/subLayer/funRandomHangar/loadout/shells'):
            self.assertFalse(route_gate.is_bare_hangar_route(route), route)

    def test_a_route_outside_the_garage_hides_the_widgets(self):
        self.assertFalse(route_gate.is_bare_hangar_route('subScope/subLayer/techtree'))

    def test_an_unreadable_route_hides_the_widgets(self):
        self.assertFalse(route_gate.is_bare_hangar_route(''))
        self.assertFalse(route_gate.is_bare_hangar_route(None))

    def test_every_registered_hangar_route_in_the_client(self):
        for root in GARAGE_ROOTS:
            self.assertTrue(route_gate.is_bare_hangar_route(root), root)
            self.assertTrue(route_gate.is_bare_hangar_route(root + '/{root}'), root)
            for screen in SCREENS:
                route = root + '/' + screen
                self.assertFalse(route_gate.is_bare_hangar_route(route), route)


if __name__ == '__main__':
    unittest.main()
