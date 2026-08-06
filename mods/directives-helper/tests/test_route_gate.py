# -*- coding: utf-8 -*-
"""Tests for the lobby-route half of the window's visibility.

The routes below are verbatim from a session that opened each offending screen in turn, as
recorded in `python.log` — the strings are the contract, so they are worth pinning literally
rather than paraphrasing.
"""
from __future__ import unicode_literals

import unittest

from zanju_dh import route_gate


class BareHangarRouteTest(unittest.TestCase):

    def test_the_plain_garage_shows_the_window(self):
        self.assertTrue(route_gate.is_bare_hangar_route('subScope/subLayer/hangar/{root}'))

    def test_a_garage_still_navigating_shows_the_window(self):
        # The machine reports the route without its leaf while a navigation is in flight.
        self.assertTrue(route_gate.is_bare_hangar_route('subScope/subLayer/hangar'))

    def test_another_modes_garage_shows_the_window(self):
        # The reason this is a suffix test and not an allowlist: every mode prefixes the route,
        # and an allowlist would silently omit whichever ones nobody thought to add.
        self.assertTrue(
            route_gate.is_bare_hangar_route('subScope/subLayer/comp7Light/hangar/{root}'))

    def test_the_playlist_editor_hides_the_window(self):
        self.assertFalse(
            route_gate.is_bare_hangar_route('subScope/subLayer/hangar/editVehiclePlaylists'))

    def test_the_directives_screen_hides_the_window(self):
        self.assertFalse(
            route_gate.is_bare_hangar_route('subScope/subLayer/hangar/loadout/instructions'))

    def test_the_equipment_screen_hides_the_window(self):
        self.assertFalse(
            route_gate.is_bare_hangar_route('subScope/subLayer/hangar/loadout/equipment'))

    def test_a_route_outside_the_garage_hides_the_window(self):
        self.assertFalse(route_gate.is_bare_hangar_route('subScope/subLayer/techtree'))

    def test_an_unreadable_route_hides_the_window(self):
        self.assertFalse(route_gate.is_bare_hangar_route(''))
        self.assertFalse(route_gate.is_bare_hangar_route(None))


class DegradationTest(unittest.TestCase):
    """Until a route has been seen the window must not be held hidden: it is gated on the
    loadout panel as well, and a garage that was already up when the mod loaded never
    produces a route change of its own."""

    def setUp(self):
        self.restore = route_gate._route

    def tearDown(self):
        route_gate._route = self.restore

    def test_no_route_yet_leaves_the_window_visible(self):
        route_gate._route = None
        self.assertTrue(route_gate.is_visible())

    def test_a_known_route_decides(self):
        route_gate._route = 'subScope/subLayer/hangar/loadout/equipment'
        self.assertFalse(route_gate.is_visible())
        route_gate._route = 'subScope/subLayer/hangar/{root}'
        self.assertTrue(route_gate.is_visible())
