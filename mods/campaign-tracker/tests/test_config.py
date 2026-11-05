# -*- coding: utf-8 -*-
"""Tests for the settings: what the file and the menu may hold, and how the two forms map."""
from __future__ import absolute_import, print_function, unicode_literals

import unittest

from zanju_ct import config


class ConfigTest(unittest.TestCase):

    def setUp(self):
        config._state.clear()
        config._state.update(config.DEFAULTS)

    def test_the_banners_show_on_the_right_by_default(self):
        self.assertTrue(config.is_enabled())
        self.assertEqual(config.tray_side(), 'right')

    def test_an_unknown_side_or_key_is_dropped(self):
        self.assertEqual(config.sanitize({'traySide': 'top', 'other': 1}), {})
        self.assertEqual(config.apply({'traySide': 'middle'}), [])
        self.assertEqual(config.tray_side(), 'right')

    def test_apply_reports_only_what_changed(self):
        self.assertEqual(config.apply({'traySide': 'left', 'enabled': True}), ['traySide'])
        self.assertEqual(config.apply({'traySide': 'left'}), [])

    def test_the_menu_stores_the_side_as_an_index(self):
        self.assertEqual(config.menu_values(), {'enabled': True, 'traySide': 0})
        config.apply({'traySide': 'left'})
        self.assertEqual(config.menu_values()['traySide'], 1)

    def test_the_menu_index_maps_back_to_a_side(self):
        self.assertEqual(config.from_menu({'traySide': 1}), {'traySide': 'left'})
        self.assertEqual(config.from_menu({'traySide': 0, 'enabled': False}),
                         {'traySide': 'right', 'enabled': False})

    def test_a_menu_index_out_of_range_changes_nothing(self):
        self.assertEqual(config.from_menu({'traySide': 7}), {})
        self.assertEqual(config.from_menu({'traySide': 'x'}), {})

    def test_the_template_carries_the_author_the_version_and_the_link(self):
        template = config.menu_template()
        self.assertEqual(template['modAuthor'], config.MOD_AUTHOR)
        self.assertEqual(template['modVersion'], config.MOD_VERSION)
        self.assertEqual(template['modUrl'], config.MOD_URL)

    def test_the_template_carries_the_defaults_not_the_current_values(self):
        config.apply({'traySide': 'left'})
        template = config.menu_template()
        self.assertEqual(template['column1'][0]['value'], 0)
        self.assertEqual(template['column1'][0]['varName'], 'traySide')


if __name__ == '__main__':
    unittest.main()
