# -*- coding: utf-8 -*-
"""Tests for the parts of the collector that do not need a running client.

The one covered here is `_is_mode_locked`, because of how it failed in practice. It reads the
client's global `constants` module, and this package has a `constants` module of its own
sitting next to the collector. Python 2 resolves a bare `import constants` to the sibling
unless the module opts into absolute imports, so the read raised `ImportError` on every
snapshot and was swallowed by the guard around it -- visible only as a log line.

These tests put a stand-in for each client module on the import path and check the collector
reaches those rather than its own neighbour.
"""
from __future__ import absolute_import, print_function, unicode_literals

import sys
import types
import unittest

from zanju_ct import collector


class _Logger(object):
    """Records what the collector logs instead of printing it."""

    def __init__(self):
        self.failures = []
        self.notes = []

    def exception(self, message, *args):
        self.failures.append(message)

    def info(self, message, *args):
        self.notes.extend(args)


class _VehicleType(object):
    def __init__(self, tags):
        self.tags = tags


def _check_for_tags(tags, checked):
    """Stands in for the client's own helper of the same name."""
    return bool(set(tags or ()) & set(checked or ()))


class _ClientModulesTest(unittest.TestCase):
    """Installs stand-ins for the client modules `_is_mode_locked` imports, then removes them."""

    # The client's own set; only membership matters here.
    BATTLE_MODE_TAGS = frozenset(['event_battles', 'epic_battles', 'battle_royale'])

    def setUp(self):
        self._saved = {}
        constants = types.ModuleType(str('constants'))
        constants.BATTLE_MODE_VEHICLE_TAGS = self.BATTLE_MODE_TAGS

        gui = types.ModuleType(str('gui'))
        gui_shared = types.ModuleType(str('gui.shared'))
        gui_items = types.ModuleType(str('gui.shared.gui_items'))
        # A plain function, not a staticmethod: a staticmethod object is a descriptor and is
        # not callable when it is read straight off a module.
        gui_items.checkForTags = _check_for_tags
        gui.shared = gui_shared
        gui_shared.gui_items = gui_items

        for name, module in (
            ('constants', constants),
            ('gui', gui),
            ('gui.shared', gui_shared),
            ('gui.shared.gui_items', gui_items),
        ):
            self._saved[name] = sys.modules.get(name)
            sys.modules[str(name)] = module

    def tearDown(self):
        for name, module in self._saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[str(name)] = module


class IsModeLockedTest(_ClientModulesTest):
    def test_reads_the_clients_constants_not_the_packages_own(self):
        logger = _Logger()
        vehicle = _VehicleType(['event_battles'])
        self.assertTrue(collector._is_mode_locked(vehicle, logger))
        # The regression: this used to find `zanju_ct.constants`, raise, and log instead.
        self.assertEqual(logger.failures, [])

    def test_accepts_a_vehicle_with_no_battle_mode_tag(self):
        logger = _Logger()
        self.assertFalse(collector._is_mode_locked(_VehicleType(['lightTank']), logger))
        self.assertEqual(logger.failures, [])

    def test_accepts_a_vehicle_with_no_tags_at_all(self):
        logger = _Logger()
        self.assertFalse(collector._is_mode_locked(_VehicleType([]), logger))
        self.assertEqual(logger.failures, [])

    def test_treats_an_unreadable_vehicle_as_not_locked(self):
        logger = _Logger()

        class _Broken(object):
            @property
            def tags(self):
                raise ValueError('the client changed this attribute')

        self.assertFalse(collector._is_mode_locked(_Broken(), logger))
        self.assertEqual(len(logger.failures), 1)


class PackageConstantsTest(unittest.TestCase):
    def test_the_packages_own_constants_module_is_still_reachable(self):
        # The fix must not cost the sibling import the rest of the package relies on.
        from zanju_ct import constants
        self.assertTrue(constants.LOGGER_NAME)
        self.assertFalse(hasattr(constants, 'BATTLE_MODE_VEHICLE_TAGS'))


class IdleReasonLogTests(unittest.TestCase):
    """The log is the only place the ways of having no mission stay apart, so it has to work.

    A snapshot is built many times over the life of a garage. A reason that logged on every one
    of them would bury the log rather than explain it, so only a change is reported.
    """

    def setUp(self):
        collector._idle_reasons.clear()
        collector._last_idle_reasons = frozenset()
        self.logger = _Logger()

    def test_a_new_reason_is_reported_once(self):
        collector._note_idle('one')
        collector._log_idle_reasons(self.logger)
        collector._log_idle_reasons(self.logger)
        self.assertEqual(self.logger.notes, ['one'])

    def test_a_second_reason_is_reported_without_repeating_the_first(self):
        collector._note_idle('one')
        collector._log_idle_reasons(self.logger)
        collector._note_idle('two')
        collector._log_idle_reasons(self.logger)
        self.assertEqual(self.logger.notes, ['one', 'two'])

    def test_a_reason_that_goes_away_and_returns_is_reported_again(self):
        collector._note_idle('one')
        collector._log_idle_reasons(self.logger)
        collector._idle_reasons.clear()
        collector._log_idle_reasons(self.logger)
        collector._note_idle('one')
        collector._log_idle_reasons(self.logger)
        self.assertEqual(self.logger.notes, ['one', 'one'])


if __name__ == '__main__':
    unittest.main()
