# -*- coding: utf-8 -*-
"""Tests for the battle panel window: when it shows the full information, and where it stays."""
from __future__ import absolute_import, print_function, unicode_literals

import json
import sys
import types
import unittest

from zanju_crt import config
from zanju_crt.gameface import battle_panel


class _Logger(object):

    def info(self, *args):
        pass

    def error(self, *args):
        pass

    def exception(self, *args):
        raise


class _Window(object):

    def __init__(self, parent_size):
        self.position = (0, 0)
        self.parent = _Parent(parent_size)

    def move(self, x, y):
        self.position = (x, y)


class _Parent(object):

    def __init__(self, size):
        self.size = size


class _Key(object):
    """The key of the extended markers, and the callbacks that wait to run."""

    def __init__(self):
        self.down = False
        self.callbacks = {}
        self.next_id = 0

    def callback(self, delay, function):
        self.next_id += 1
        self.callbacks[self.next_id] = function
        return self.next_id

    def cancelCallback(self, callback_id):
        self.callbacks.pop(callback_id, None)

    def run_callbacks(self):
        pending, self.callbacks = self.callbacks, {}
        for function in pending.values():
            function()


class ShowFullTest(unittest.TestCase):

    def test_always_and_never_ignore_the_key(self):
        for extended in (False, True):
            self.assertTrue(battle_panel.show_full(config.DETAILS_ALWAYS, extended))
            self.assertFalse(battle_panel.show_full(config.DETAILS_NEVER, extended))

    def test_alt_follows_the_key(self):
        self.assertFalse(battle_panel.show_full(config.DETAILS_ALT, False))
        self.assertTrue(battle_panel.show_full(config.DETAILS_ALT, True))


class PanelTest(unittest.TestCase):

    def setUp(self):
        self.saved_modules = dict(sys.modules)
        self.key = _Key()
        big_world = types.ModuleType(str('BigWorld'))
        big_world.callback = self.key.callback
        big_world.cancelCallback = self.key.cancelCallback
        sys.modules[str('BigWorld')] = big_world
        command_mapping = types.ModuleType(str('CommandMapping'))
        command_mapping.CMD_VEHICLE_MARKERS_SHOW_INFO = 'markers'
        key = self.key
        command_mapping.g_instance = types.ModuleType(str('g_instance'))
        command_mapping.g_instance.isActive = lambda command: command == 'markers' and key.down
        sys.modules[str('CommandMapping')] = command_mapping
        config._state.clear()
        config._state.update(config.DEFAULTS)
        self.panel = battle_panel.Panel(_Logger())

    def tearDown(self):
        sys.modules.clear()
        sys.modules.update(self.saved_modules)

    def _full(self):
        return json.loads(self.panel.payload)['full']

    def _start(self, details):
        config.apply({'panelDetails': details})
        # open() without its window: only the payload and the setting.
        self.panel.details = config.panel_details()
        self.panel.update({'rows': []})

    def test_the_payload_carries_the_setting(self):
        self._start(config.DETAILS_ALWAYS)
        self.assertTrue(self._full())
        self._start(config.DETAILS_NEVER)
        self.assertFalse(self._full())

    def test_the_payload_carries_the_style_and_the_figures(self):
        self._start(config.DETAILS_ALWAYS)
        sent = json.loads(self.panel.payload)
        self.assertEqual((sent['style'], sent['figures']), ('flat', 'both'))
        config.apply({'panelStyle': 'round', 'panelFigures': 'value'})
        self.panel.update({'rows': []})
        sent = json.loads(self.panel.payload)
        self.assertEqual((sent['style'], sent['figures']), ('round', 'value'))

    def test_with_alt_the_key_shows_the_full_information_while_it_is_down(self):
        self._start(config.DETAILS_ALT)
        self.assertFalse(self._full())
        self.key.down = True
        self.panel._set_extended(True)
        self.assertTrue(self._full())
        self.key.down = False
        self.panel._set_extended(False)
        self.assertFalse(self._full())
        self.assertEqual(self.key.callbacks, {})

    def test_a_lost_release_of_the_key_ends_the_full_information(self):
        self._start(config.DETAILS_ALT)
        self.key.down = True
        self.panel._set_extended(True)
        self.key.run_callbacks()
        self.assertTrue(self._full())
        # The game lost the keyboard: the key is up, and no event says so.
        self.key.down = False
        self.key.run_callbacks()
        self.assertFalse(self._full())
        self.assertEqual(self.key.callbacks, {})

    def test_a_larger_form_goes_back_to_its_place_when_it_shrinks(self):
        self.panel.window = _Window((1920.0, 1080.0))
        self.panel.on_sized({'width': 300, 'height': 100})
        self.panel._move(1500, 1000)
        self.panel.anchor = (1500, 1000)
        self.panel.on_sized({'width': 300, 'height': 200})
        self.assertEqual(self.panel.window.position, (1500, 880))
        self.panel.on_sized({'width': 300, 'height': 60})
        self.assertEqual(self.panel.window.position, (1500, 1000))


if __name__ == '__main__':
    unittest.main()
