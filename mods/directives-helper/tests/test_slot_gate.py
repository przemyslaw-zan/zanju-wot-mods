# -*- coding: utf-8 -*-
"""Tests for the directives-slot gate.

This is the gate that keeps the window off a tank that has nowhere to put a directive. It is
worth pinning because getting it wrong is expensive rather than untidy: fitting a directive on
such a tank leaves it unable to enter battle until it is sold and bought back (issue #18), and
the client's own processor does not refuse the request.

`_current_vehicle` is stood in for the way `route_gate._get_machine` is: the real one reads
`CurrentVehicle`, which only exists inside the game.
"""
from __future__ import unicode_literals

import unittest

from zanju_dh import slot_gate


class FakeEquipment(object):
    """Stands in for `vehicle.battleBoosters.installed`, whose length is the slot count."""

    def __init__(self, slots):
        self._slots = [None] * slots

    def __len__(self):
        return len(self._slots)


class FakeBoosters(object):

    def __init__(self, slots):
        self.installed = FakeEquipment(slots)


class FakeVehicle(object):

    def __init__(self, slots):
        self.battleBoosters = FakeBoosters(slots)


class UnreadableVehicle(object):
    """A client that has changed shape under the mod."""

    @property
    def battleBoosters(self):
        raise AttributeError('battleBoosters')


class HasDirectiveSlotTest(unittest.TestCase):

    def test_a_tank_with_a_slot_can_take_a_directive(self):
        self.assertTrue(slot_gate.has_directive_slot(FakeVehicle(1)))

    def test_a_tank_without_a_slot_cannot(self):
        # The tier II case from issue #18: the mode still lists a directives section, but the
        # tank has no slot in it, so the game draws none and nothing may be fitted.
        self.assertFalse(slot_gate.has_directive_slot(FakeVehicle(0)))

    def test_no_tank_is_left_to_the_loadout_panel(self):
        # "Is there a tank at all" is the panel's question; answering it here as well would
        # hide the window for the second or two before the garage has finished assembling.
        self.assertTrue(slot_gate.has_directive_slot(None))

    def test_a_client_that_will_not_answer_keeps_the_window(self):
        # A window that shows in the wrong place is a nuisance, one that never shows is a
        # broken mod -- the same degradation the other two gates use.
        self.assertTrue(slot_gate.has_directive_slot(UnreadableVehicle()))


class IsVisibleTest(unittest.TestCase):

    def setUp(self):
        self._original = slot_gate._current_vehicle
        slot_gate._reported = None

    def tearDown(self):
        slot_gate._current_vehicle = self._original
        slot_gate._reported = None

    def _selected(self, vehicle):
        slot_gate._current_vehicle = lambda: vehicle

    def test_follows_the_selected_tank(self):
        self._selected(FakeVehicle(1))
        self.assertTrue(slot_gate.is_visible())
        self._selected(FakeVehicle(0))
        self.assertFalse(slot_gate.is_visible())

    def test_degrades_to_visible_outside_the_game(self):
        # The real `_current_vehicle` cannot import CurrentVehicle here, which reads as "no
        # tank" rather than as an error.
        self.assertTrue(slot_gate.is_visible())


if __name__ == '__main__':
    unittest.main()
