# -*- coding: utf-8 -*-
"""Tests for which screen a badge click opens.

The two campaign styles differ: campaigns 1 and 2 give every mission its own screen, while
campaign 3 shows a list. These check the branch is picked on the campaign, and that a campaign
with nothing running opens nothing at all.

The client dispatchers themselves are imported inside `navigation`'s own functions, so the
tests below only reach as far as the decision. What each dispatcher then does is the client's
business and is not restated here.
"""
from __future__ import absolute_import, print_function, unicode_literals

import unittest

from zanju_ct import collector, navigation


class _Logger(object):
    def __init__(self):
        self.messages = []

    def info(self, message, *args):
        self.messages.append(message)

    def warning(self, message, *args):
        self.messages.append(message)

    def exception(self, message, *args):
        self.messages.append(message)


class _Quest(object):
    def getID(self):
        return 4207

    def getOperationID(self):
        return 9

    def getChainID(self):
        return 2

    def getQuestClassifier(self):
        return None


class OpenMissionTest(unittest.TestCase):
    """Replaces the mission lookup so no client is needed to reach the decision."""

    def setUp(self):
        self._real_finder = collector.find_active_mission
        self.opened = []

        def _fake_page(quest, logger):
            self.opened.append(('page', quest.getID()))
            return True

        def _fake_list(quest, logger):
            self.opened.append(('list', quest.getOperationID()))
            return True

        self._real_page = navigation._open_mission_page
        self._real_list = navigation._open_mission_list
        navigation._open_mission_page = _fake_page
        navigation._open_mission_list = _fake_list

    def tearDown(self):
        collector.find_active_mission = self._real_finder
        navigation._open_mission_page = self._real_page
        navigation._open_mission_list = self._real_list

    def _with_mission(self, quest):
        collector.find_active_mission = lambda branch, logger: quest

    def test_campaign_1_opens_the_missions_own_screen(self):
        self._with_mission(_Quest())
        self.assertTrue(navigation.open_mission('regular', _Logger()))
        self.assertEqual(self.opened, [('page', 4207)])

    def test_campaign_2_opens_the_missions_own_screen(self):
        self._with_mission(_Quest())
        self.assertTrue(navigation.open_mission('pm2', _Logger()))
        self.assertEqual(self.opened, [('page', 4207)])

    def test_campaign_3_opens_the_mission_list_instead(self):
        # It has no per-mission screen, so the list of its operation is the mission screen.
        self._with_mission(_Quest())
        self.assertTrue(navigation.open_mission('pm3', _Logger()))
        self.assertEqual(self.opened, [('list', 9)])

    def test_opens_nothing_when_the_campaign_has_no_active_mission(self):
        self._with_mission(None)
        logger = _Logger()
        self.assertFalse(navigation.open_mission('pm2', logger))
        self.assertEqual(self.opened, [])
        self.assertEqual(len(logger.messages), 1)

    def test_reports_failure_instead_of_raising(self):
        def _boom(quest, logger):
            raise ValueError('the client changed this call')

        navigation._open_mission_page = _boom
        self._with_mission(_Quest())
        logger = _Logger()
        self.assertFalse(navigation.open_mission('regular', logger))
        self.assertEqual(len(logger.messages), 1)


if __name__ == '__main__':
    unittest.main()
