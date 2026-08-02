# -*- coding: utf-8 -*-
"""Tests for the remembered window state.

Values arrive from JavaScript, so they are whatever the browser side happened to send:
floats from a drag, strings, or nonsense after a bad edit of the stored file. The sanitizer
is what keeps a bad value from parking the window off-screen, and it is the part worth
pinning here. Writing to AppData is not exercised — there is no AppData outside the game,
and `save()` is expected to report failure rather than raise.
"""
from __future__ import unicode_literals

import unittest

from zanju_dh import config


class ResizeAndOptionsTest(unittest.TestCase):

    def test_width_starts_unset(self):
        # 0 means "never resized", which the window reads as "use the stylesheet's size".
        self.assertEqual(config._DEFAULTS['width'], 0)

    def test_remembers_a_resize(self):
        self.assertEqual(config.update(width=420)['width'], 420)

    def test_remembers_the_unowned_toggle(self):
        self.assertTrue(config.update(show_unowned=True)['showUnowned'])

    def test_the_unowned_toggle_can_be_turned_back_off(self):
        # False is a value, not a missing argument; a naive "skip None" filter drops it.
        config.update(show_unowned=True)
        self.assertFalse(config.update(show_unowned=False)['showUnowned'])


class SanitizeTest(unittest.TestCase):

    def test_rounds_fractional_pixels_from_a_drag(self):
        self.assertEqual(config._sanitize({'x': 12.6})['x'], 13)

    def test_accepts_numeric_strings(self):
        self.assertEqual(config._sanitize({'y': '40'})['y'], 40)

    def test_clamps_negative_coordinates(self):
        # A negative position would put the window past the top-left corner, out of reach.
        self.assertEqual(config._sanitize({'x': -50})['x'], 0)

    def test_drops_unusable_values(self):
        self.assertEqual(config._sanitize({'x': 'somewhere', 'y': None}), {})

    def test_coerces_folded_to_a_bool(self):
        self.assertIs(config._sanitize({'folded': 1})['folded'], True)
        self.assertIs(config._sanitize({'folded': 0})['folded'], False)

    def test_ignores_keys_it_does_not_own(self):
        self.assertEqual(config._sanitize({'nonsense': 5}), {})


class UpdateTest(unittest.TestCase):

    def setUp(self):
        self._original = config.current()
        self.addCleanup(lambda: config._state.update(self._original))

    def test_applies_only_the_reported_fields(self):
        config._state.update({'x': 10, 'y': 20, 'folded': False})
        config.update(folded=True)
        state = config.current()
        self.assertEqual((state['x'], state['y']), (10, 20), 'position must survive a fold')
        self.assertTrue(state['folded'])

    def test_records_the_viewport_a_position_was_captured_at(self):
        # Kept so a later resolution change can rescale the position proportionally.
        config.update(x=100, y=200, viewport_width=2560, viewport_height=1440)
        state = config.current()
        self.assertEqual(state['viewportWidth'], 2560)
        self.assertEqual(state['viewportHeight'], 1440)

    def test_returns_a_copy_so_callers_cannot_mutate_the_state(self):
        snapshot = config.current()
        snapshot['x'] = 9999
        self.assertNotEqual(config.current()['x'], 9999)


class DefaultsTest(unittest.TestCase):

    def test_starts_unpositioned(self):
        # None means "never positioned", which the window reads as "use the default corner".
        self.assertIsNone(config._DEFAULTS['x'])
        self.assertIsNone(config._DEFAULTS['y'])
        self.assertFalse(config._DEFAULTS['folded'])

    def test_save_reports_failure_without_appdata(self):
        self.assertFalse(config.save())


if __name__ == '__main__':
    unittest.main()
