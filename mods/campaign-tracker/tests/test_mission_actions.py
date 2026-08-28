# -*- coding: utf-8 -*-
"""Tests for which actions a mission accepts.

`read_actions` mirrors the rules the client applies to its own pause and reset buttons, and
getting it wrong is worse than showing nothing: the card would offer an action the game then
refuses, and the player would have no way of telling that from the mod being broken.

The client modules it reads are stood in for here -- the operation lists it checks against, and
the events cache it asks which campaign is running.
"""
from __future__ import absolute_import, print_function, unicode_literals

import sys
import types
import unittest

from zanju_ct import mission_actions

# The client's own values: operation 7, Object 279 (e), and nothing else.
PAUSABLE = (7,)
DISCARDABLE = (7,)


class _Logger(object):
    def __init__(self):
        self.failures = []

    def exception(self, message, *args):
        self.failures.append(message)

    def warning(self, message, *args):
        self.failures.append(message)


class _Quest(object):
    """The handful of answers `read_actions` asks a mission for."""

    def __init__(self, operation_id=7, unlocked=True, in_progress=True,
                 available=True, paused=False):
        self._operation_id = operation_id
        self._unlocked = unlocked
        self._in_progress = in_progress
        self._available = available
        self.isOnPause = paused

    def getOperationID(self):
        return self._operation_id

    def isUnlocked(self):
        return self._unlocked

    def isInProgress(self):
        return self._in_progress

    def isAvailable(self):
        # The client answers with a named tuple of (success, reason).
        return (self._available, '' if self._available else 'noVehicle')

    def getID(self):
        return 42


class _ActionsTest(unittest.TestCase):
    """Stands in for the client modules `read_actions` reads."""

    ACTIVE_CAMPAIGNS = ['regular', 'pm2']

    def setUp(self):
        self._saved = {}
        self._active = list(self.ACTIVE_CAMPAIGNS)

        pm_constants = types.ModuleType(str('gui.server_events.pm_constants'))
        pm_constants.PAUSABLE_OPERATIONS_IDS = PAUSABLE
        pm_constants.DISCARDABLE_OPERATIONS_IDS = DISCARDABLE

        personal_missions = types.ModuleType(str('personal_missions'))

        class _PM_BRANCH(object):
            PERSONAL_MISSION_3 = 4
            TYPE_TO_NAME = {0: 'regular', 2: 'pm2', 4: 'pm3'}

        personal_missions.PM_BRANCH = _PM_BRANCH

        test = self

        class _Missions(object):
            def getActiveCampaigns(self):
                return test._active

        class _Cache(object):
            def getPersonalMissions(self):
                return _Missions()

        helpers = types.ModuleType(str('helpers'))
        dependency = types.ModuleType(str('helpers.dependency'))
        dependency.instance = lambda _interface: _Cache()
        helpers.dependency = dependency

        skeletons = types.ModuleType(str('skeletons'))
        skeletons_gui = types.ModuleType(str('skeletons.gui'))
        server_events = types.ModuleType(str('skeletons.gui.server_events'))
        server_events.IEventsCache = object
        skeletons.gui = skeletons_gui
        skeletons_gui.server_events = server_events

        gui = types.ModuleType(str('gui'))
        gui_server_events = types.ModuleType(str('gui.server_events'))
        gui.server_events = gui_server_events
        gui_server_events.pm_constants = pm_constants

        for name, module in (
            ('gui', gui),
            ('gui.server_events', gui_server_events),
            ('gui.server_events.pm_constants', pm_constants),
            ('personal_missions', personal_missions),
            ('helpers', helpers),
            ('helpers.dependency', dependency),
            ('skeletons', skeletons),
            ('skeletons.gui', skeletons_gui),
            ('skeletons.gui.server_events', server_events),
        ):
            self._saved[name] = sys.modules.get(name)
            sys.modules[str(name)] = module

    def tearDown(self):
        for name, module in self._saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[str(name)] = module


class ReadActionsTest(_ActionsTest):
    def test_offers_both_actions_on_the_operation_that_allows_them(self):
        logger = _Logger()
        actions = mission_actions.read_actions(_Quest(), True, logger)
        self.assertTrue(actions['canPause'])
        self.assertTrue(actions['canReset'])
        self.assertEqual(logger.failures, [])

    def test_offers_neither_on_any_other_operation(self):
        # Campaign 1, campaign 2's earlier operations, and all of campaign 3.
        for operation_id in (1, 4, 5, 6, 8, 10):
            actions = mission_actions.read_actions(
                _Quest(operation_id=operation_id), True, _Logger())
            self.assertFalse(actions['canPause'], operation_id)
            self.assertFalse(actions['canReset'], operation_id)

    def test_offers_no_reset_when_there_is_no_progress_to_throw_away(self):
        actions = mission_actions.read_actions(_Quest(), False, _Logger())
        # Pause is unaffected: a mission with nothing done is still worth pausing.
        self.assertTrue(actions['canPause'])
        self.assertFalse(actions['canReset'])

    def test_offers_nothing_on_a_mission_that_is_not_running(self):
        for quest in (_Quest(unlocked=False), _Quest(in_progress=False),
                      _Quest(available=False)):
            actions = mission_actions.read_actions(quest, True, _Logger())
            self.assertFalse(actions['canPause'])
            self.assertFalse(actions['canReset'])

    def test_offers_nothing_while_campaign_3_is_the_active_campaign(self):
        self._active = ['pm3']
        actions = mission_actions.read_actions(_Quest(), True, _Logger())
        self.assertFalse(actions['canPause'])
        self.assertFalse(actions['canReset'])

    def test_reports_whether_the_mission_is_paused(self):
        self.assertTrue(mission_actions.read_actions(
            _Quest(paused=True), True, _Logger())['paused'])
        self.assertFalse(mission_actions.read_actions(
            _Quest(), True, _Logger())['paused'])

    def test_offers_nothing_when_the_mission_cannot_be_read(self):
        class _Broken(object):
            def isUnlocked(self):
                raise ValueError('the client changed this method')

            def getID(self):
                return 7

        logger = _Logger()
        actions = mission_actions.read_actions(_Broken(), True, logger)
        self.assertFalse(actions['canPause'])
        self.assertFalse(actions['canReset'])
        self.assertEqual(len(logger.failures), 1)


class PerformTest(_ActionsTest):
    def test_refuses_an_action_it_does_not_know(self):
        logger = _Logger()
        self.assertFalse(mission_actions.perform(_Quest(), 'delete', logger))
        # Refused before any client module is touched, so nothing was requested.
        self.assertEqual(len(logger.failures), 1)

    def test_refuses_the_plain_click_which_belongs_to_navigation(self):
        self.assertFalse(mission_actions.perform(
            _Quest(), mission_actions.ACTION_OPEN, _Logger()))


if __name__ == '__main__':
    unittest.main()
