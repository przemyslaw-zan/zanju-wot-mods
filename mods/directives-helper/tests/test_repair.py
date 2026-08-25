# -*- coding: utf-8 -*-
"""Tests for reading the invalid directive state out of the raw inventory.

The repair itself is a server command and cannot be tested here. What can, and what decides
whether a tank is written to at all, is the reading: which raw inventory entries count as a
directive, and the rule that a tank with a real directive slot is never touched.
"""
from __future__ import unicode_literals

import unittest

from zanju_dh import repair


class RecordedDirectivesTest(unittest.TestCase):

    def test_reads_the_fitted_directive(self):
        self.assertEqual(repair.recorded_directives({'boosters': [28155]}), (28155,))

    def test_reads_the_refill_layout(self):
        # `boostersLayout` is one list per loadout, so the entries are nested one deep.
        self.assertEqual(repair.recorded_directives({'boostersLayout': [[28155]]}), (28155,))

    def test_reports_each_entry_once(self):
        data = {'boosters': [28155], 'boostersLayout': [[28155], [28155]]}
        self.assertEqual(repair.recorded_directives(data), (28155,))

    def test_reads_every_entry_of_the_reported_tank(self):
        # The three consumables the server recorded as directives in issue #18.
        data = {'boosters': [1275, 763, 2555], 'boostersLayout': [[1275, 763, 2555]]}
        self.assertEqual(repair.recorded_directives(data), (1275, 763, 2555))

    def test_an_empty_slot_is_not_an_entry(self):
        # Empty slots read as ZERO_COMP_DESCR, which is 0.
        self.assertEqual(repair.recorded_directives({'boosters': [0, 0]}), ())

    def test_a_tank_with_no_directive_keys_reads_as_empty(self):
        self.assertEqual(repair.recorded_directives({'compDescr': 1}), ())

    def test_survives_a_shape_it_does_not_expect(self):
        # The raw inventory is the client's own dictionary, so this reads whatever is there.
        self.assertEqual(repair.recorded_directives({'boosters': None}), ())
        self.assertEqual(repair.recorded_directives({'boostersLayout': 28155}), ())


class InvalidDirectivesTest(unittest.TestCase):

    def test_a_tank_with_a_slot_is_left_alone(self):
        # A fitted directive on a tank that has a slot for it is the normal case, and the one
        # the mod must never write to.
        self.assertEqual(repair.invalid_directives((28155,), 1), ())

    def test_a_tank_with_no_slot_and_a_record_is_invalid(self):
        self.assertEqual(
            repair.invalid_directives((1275, 763, 2555), 0), (1275, 763, 2555))

    def test_a_tank_with_no_slot_and_no_record_is_fine(self):
        self.assertEqual(repair.invalid_directives((), 0), ())


if __name__ == '__main__':
    unittest.main()
