# -*- coding: utf-8 -*-
"""Tests for the XP figures each mode hands to its own marker tooltips.

The bar and the tooltip are two separate Scaleform views. The bar reads a mode's fill
values directly. The tooltip sees one flattened marker list, so every marker carries a
copy of the figures its own mode uses. When the two disagree, the bar shows progress
while its tooltips report 0%. That is what an elite vehicle did before this fix.
"""
from __future__ import unicode_literals

import unittest

from zanju_rpb.scaleform import modes


def make_mode(bar_fill_mode='', completed_value=0.0, primary=0.0, secondary=0.0, costs=(1000,)):
    markers = [{'id': 'marker_{0}'.format(cost), 'costXp': cost} for cost in costs]
    return modes._make_mode(
        'test_mode', 'Test', 100000, primary, secondary, '', '', '', '',
        markers=markers,
        completed_value=completed_value,
        bar_fill_mode=bar_fill_mode,
    )


class ModeMarkerXpTest(unittest.TestCase):

    def test_a_normal_mode_measures_markers_against_unspent_xp(self):
        # Research and field mods hold spendable XP, which is what a marker costs.
        mode = make_mode(primary=30000, secondary=5000, completed_value=12000)
        modes._stamp_tooltip_indices([mode])
        marker = mode['markers'][0]
        self.assertEqual(30000, marker['tooltipCombatXp'])
        self.assertEqual(5000, marker['tooltipFreeXp'])

    def test_a_completed_only_mode_measures_markers_against_everything_earned(self):
        # The regression: an elite level costs base XP as it arrives, so the progress
        # already made is the only figure to measure a marker against.
        mode = make_mode(
            bar_fill_mode=modes.BAR_FILL_MODE_COMPLETED_ONLY,
            completed_value=42700,
            primary=0.0,
            secondary=0.0,
        )
        modes._stamp_tooltip_indices([mode])
        marker = mode['markers'][0]
        self.assertEqual(42700, marker['tooltipCombatXp'])
        self.assertEqual(0, marker['tooltipFreeXp'])


class FakeVehicle(object):

    userName = 'Tier XI Test Vehicle'
    intCD = 49169


class EliteModeTooltipXpTest(unittest.TestCase):
    """The reported bug, from the payload the collector produces to the marker."""

    LEVEL = 26
    IN_LEVEL_XP = 1200

    def elite_mode(self):
        payload = modes.build_scaleform_view_payload(
            FakeVehicle(),
            {
                'vehicle': {'tier': 11},
                'tech_tree': {'is_elite': True, 'is_fully_elite': True},
                'field_mods': {'is_veh_skill_tree': True, 'total_steps': 30, 'unlocked_steps': 4},
                'elite_progression': {
                    'available': True,
                    'current_level': self.LEVEL,
                    'current_xp': self.IN_LEVEL_XP,
                    'next_level_xp': 2500,
                    'max_level': modes.ELITE_MAX_LEVEL,
                },
            },
            mode_preferences={'eliteMode': modes.ELITE_MODE_ON},
        )
        for mode in payload['modes']:
            if mode['id'] == modes.MODE_ELITE_PROGRESSION:
                return mode
        self.fail('the payload carries no elite mode')

    def stat_tracker_marker(self):
        for marker in self.elite_mode()['markers']:
            if marker['id'] == 'elite_t11_stat_tracker':
                return marker
        self.fail('the elite mode carries no stat tracker marker')

    def test_the_stat_tracker_reports_the_levels_already_earned(self):
        marker = self.stat_tracker_marker()
        earned = modes._elite_cumulative_xp_to_level(self.LEVEL) + self.IN_LEVEL_XP
        self.assertEqual(earned, marker['tooltipCombatXp'])
        self.assertTrue(marker['tooltipCombatXp'] > 0)

    def test_the_stat_tracker_is_still_locked_at_this_level(self):
        # Level 26 of the 35 the reward needs: real progress, but not yet complete.
        marker = self.stat_tracker_marker()
        self.assertEqual(35, marker['level'])
        self.assertEqual('locked', marker['markerState'])
        self.assertTrue(marker['tooltipCombatXp'] < marker['costXp'])


if __name__ == '__main__':
    unittest.main()
