# -*- coding: utf-8 -*-
"""Tests for the lobby-route half of the window's visibility.

The routes below are verbatim from a session that opened each offending screen in turn, as
recorded in `python.log` — the strings are the contract, so they are worth pinning literally
rather than paraphrasing.
"""
from __future__ import unicode_literals

import logging
import unittest

from zanju_dh import route_gate


class SilentLogger(logging.Logger):

    def __init__(self):
        logging.Logger.__init__(self, 'test')
        self.exceptions = []
        self.addHandler(logging.NullHandler())

    def exception(self, message, *args, **kwargs):
        self.exceptions.append(message)


class FakeEvent(list):
    """The game's `Event`: a list whose `+=` refuses a delegate it already holds, and which
    the lobby empties wholesale when it clears the manager that owns it."""

    def __iadd__(self, delegate):
        if delegate not in self:
            self.append(delegate)
        return self

    def __isub__(self, delegate):
        if delegate in self:
            self.remove(delegate)
        return self


class FakeState(object):

    def __init__(self, route):
        self._route = route

    def getStateID(self):
        return self._route


class FakeRouteInfo(object):

    def __init__(self, route):
        self.state = FakeState(route) if route else None


class FakeMachine(object):

    def __init__(self, route=None):
        self.onVisibleRouteChanged = FakeEvent()
        self.visibleRouteInfo = FakeRouteInfo(route)

    def go(self, route):
        """Drive a route change the way the client would."""
        self.visibleRouteInfo = FakeRouteInfo(route)
        for delegate in list(self.onVisibleRouteChanged):
            delegate(self.visibleRouteInfo)

    def tear_down_lobby(self):
        """What a battle does: EventManager.clear() empties every event it owns, leaving the
        machine itself intact."""
        del self.onVisibleRouteChanged[:]


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


class SubscriptionTest(unittest.TestCase):
    """Staying subscribed across a lobby teardown.

    The failure this pins: the lobby clears the event manager on the way into a battle, so the
    handler is dropped while the machine object survives. An install that skipped re-subscribing
    because the machine looked unchanged stopped hearing routes for the rest of the session, and
    the window stayed hidden behind whatever route was last seen -- the FINAL state the lobby
    passes through on its way out, which is not a garage route.
    """

    def setUp(self):
        self.logger = SilentLogger()
        self.seen = []
        self.real_get_machine = route_gate._get_machine

    def tearDown(self):
        route_gate._get_machine = self.real_get_machine
        route_gate.uninstall(self.logger)

    def install(self, machine):
        route_gate._get_machine = lambda: machine
        route_gate.install(self.logger, self.seen.append)

    def test_subscribes_once_per_machine(self):
        machine = FakeMachine('subScope/subLayer/hangar/{root}')
        self.install(machine)
        self.install(machine)
        self.assertEqual(len(machine.onVisibleRouteChanged), 1,
                         'a repeat install must not stack handlers')

    def test_resubscribes_after_the_lobby_cleared_the_event(self):
        machine = FakeMachine('subScope/subLayer/hangar/{root}')
        self.install(machine)
        machine.tear_down_lobby()
        self.assertEqual(machine.onVisibleRouteChanged, [])

        # Same machine object, handler gone: this is the case identity comparison misses.
        self.install(machine)
        self.assertEqual(len(machine.onVisibleRouteChanged), 1)

        machine.go('subScope/subLayer/hangar/loadout/equipment')
        self.assertFalse(route_gate.is_visible(), 'routes must be reaching us again')

    def test_a_stale_route_is_re_read_on_install(self):
        # The window came out of a battle: the last route anyone saw was the lobby's FINAL
        # state, and no navigation is coming to correct it.
        machine = FakeMachine('subScope/subLayer/FINAL')
        self.install(machine)
        self.assertFalse(route_gate.is_visible())
        machine.tear_down_lobby()

        machine.visibleRouteInfo = FakeRouteInfo('subScope/subLayer/hangar/{root}')
        self.install(machine)
        self.assertTrue(route_gate.is_visible(), 'the fresh route must win over the stale one')

    def test_re_reading_the_route_reports_the_change(self):
        # Nothing else will: the navigation that would have announced it happened while the
        # subscription was dropped.
        machine = FakeMachine('subScope/subLayer/FINAL')
        self.install(machine)
        del self.seen[:]
        machine.tear_down_lobby()
        machine.visibleRouteInfo = FakeRouteInfo('subScope/subLayer/hangar/{root}')
        self.install(machine)
        self.assertEqual(self.seen, [True])

    def test_a_new_machine_is_subscribed_to(self):
        first = FakeMachine('subScope/subLayer/hangar/{root}')
        self.install(first)
        second = FakeMachine('subScope/subLayer/hangar/{root}')
        self.install(second)
        self.assertEqual(len(second.onVisibleRouteChanged), 1)

    def test_no_machine_yet_is_not_an_error(self):
        route_gate._get_machine = lambda: None
        route_gate.install(self.logger, self.seen.append)
        self.assertEqual(self.logger.exceptions, [])
        self.assertTrue(route_gate.is_visible())
