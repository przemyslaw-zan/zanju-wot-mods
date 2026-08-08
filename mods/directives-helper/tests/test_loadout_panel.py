# -*- coding: utf-8 -*-
"""Tests for the loadout-panel visibility gate.

The client hooks are installed by `install()`, which needs a running game, so what is pinned
here is the decision the hooks feed: reading a panel's sections, tracking several panels
across a mode switch, and the degradation rules. Those are what decide whether the window
appears at all, and getting them wrong is invisible until someone loads the game.
"""
from __future__ import unicode_literals

import logging
import unittest

from zanju_dh import loadout_panel


class SilentLogger(logging.Logger):

    def __init__(self):
        logging.Logger.__init__(self, 'test')
        self.exceptions = []
        self.addHandler(logging.NullHandler())

    def exception(self, message, *args, **kwargs):
        self.exceptions.append(message)


class FakeGroup(object):

    def __init__(self, *sections):
        self.sections = sections


class FakeController(object):

    def __init__(self, groups):
        self._groups = groups

    def _getGroups(self):
        return self._groups


class FakePresenter(object):
    """Stands in for a mode's loadout panel presenter."""

    def __init__(self, groups=None):
        self._getGroupController = FakeController(groups) if groups is not None else None


class FakePresenterClass(object):
    """Stands in for the client class install() patches."""

    def _onLoading(self):
        pass


class LoadoutPanelTest(unittest.TestCase):

    def setUp(self):
        self.logger = SilentLogger()
        self.seen = []
        # install() needs a running client, so patch a stand-in class instead: that leaves the
        # module in the state a successful install() produces, hooks and all.
        loadout_panel._patch(FakePresenterClass, '_onLoading', self.logger)
        loadout_panel._callback = self.seen.append

    def tearDown(self):
        loadout_panel.uninstall(self.logger)

    def randomGroups(self):
        # What every mode that keeps directives ends up with, Onslaught included.
        return [FakeGroup('optDevices', 'battleBoosters'), FakeGroup('shells', 'consumables')]


class OffersDirectivesTest(LoadoutPanelTest):

    def test_finds_the_directives_section(self):
        panel = FakePresenter(self.randomGroups())
        self.assertTrue(loadout_panel.offers_directives(panel, self.logger))

    def test_a_mode_without_directives_is_reported_as_such(self):
        # Fun Random drops the section when its sub-mode disables boosters.
        panel = FakePresenter([FakeGroup('optDevices'), FakeGroup('shells', 'consumables')])
        self.assertFalse(loadout_panel.offers_directives(panel, self.logger))

    def test_no_vehicle_means_no_sections(self):
        # The panel exists before a tank is picked, with nothing to describe yet.
        self.assertFalse(loadout_panel.offers_directives(FakePresenter([]), self.logger))

    def test_a_panel_without_a_controller_offers_nothing(self):
        self.assertFalse(loadout_panel.offers_directives(FakePresenter(), self.logger))

    def test_an_unreadable_panel_is_reported_not_raised(self):
        # This runs inside the client's own view lifecycle; raising would break the garage.
        class BrokenPresenter(object):

            @property
            def _getGroupController(self):
                raise ValueError('no')

        self.assertFalse(loadout_panel.offers_directives(BrokenPresenter(), self.logger))
        self.assertTrue(self.logger.exceptions, 'the failure should be reported')


class VisibilityTest(LoadoutPanelTest):

    def test_hidden_until_a_panel_appears(self):
        self.assertFalse(loadout_panel.is_visible())

    def test_a_panel_with_directives_shows_the_window(self):
        panel = FakePresenter(self.randomGroups())
        loadout_panel._track(panel, self.logger)
        self.assertTrue(loadout_panel.is_visible())
        self.assertEqual(self.seen, [True])

    def test_a_panel_without_directives_does_not(self):
        panel = FakePresenter([FakeGroup('shells')])
        loadout_panel._track(panel, self.logger)
        self.assertFalse(loadout_panel.is_visible())
        # Reported even though it is the default: the window may have been built while a
        # previous panel was up, so the first answer is always pushed rather than assumed.
        self.assertEqual(self.seen, [False])

    def test_a_collected_panel_stops_counting(self):
        # The panels are held weakly, so one that is destroyed without its teardown hook
        # running cannot pin the window open for the rest of the session.
        loadout_panel._track(FakePresenter(self.randomGroups()), self.logger)
        self.assertFalse(loadout_panel.is_visible())

    def test_leaving_the_garage_hides_the_window(self):
        panel = FakePresenter(self.randomGroups())
        loadout_panel._track(panel, self.logger)
        loadout_panel._forget(panel, self.logger)
        self.assertFalse(loadout_panel.is_visible())
        self.assertEqual(self.seen, [True, False])

    def test_the_new_panel_decides_during_a_mode_switch(self):
        # The incoming mode's panel can load before the outgoing one is torn down, so
        # visibility has to consider every panel on screen rather than the last one seen.
        old = FakePresenter(self.randomGroups())
        new = FakePresenter([FakeGroup('shells')])
        loadout_panel._track(old, self.logger)
        loadout_panel._track(new, self.logger)
        self.assertTrue(loadout_panel.is_visible(), 'the old panel is still up')
        loadout_panel._forget(old, self.logger)
        self.assertFalse(loadout_panel.is_visible())

    def test_a_panel_that_gains_directives_is_re_read(self):
        # Last Stand rebuilds its groups from the player's panel preset without reloading.
        panel = FakePresenter([FakeGroup('shells')])
        loadout_panel._track(panel, self.logger)
        panel._getGroupController = FakeController(self.randomGroups())
        loadout_panel._track(panel, self.logger)
        self.assertTrue(loadout_panel.is_visible())

    def test_the_same_answer_is_reported_once(self):
        panel = FakePresenter(self.randomGroups())
        loadout_panel._track(panel, self.logger)
        loadout_panel._track(panel, self.logger)
        self.assertEqual(self.seen, [True], 'the window should not be told twice')

    def test_forgetting_an_unknown_panel_is_harmless(self):
        loadout_panel._forget(FakePresenter(), self.logger)
        self.assertFalse(loadout_panel.is_visible())


class UpdateCallbackTest(LoadoutPanelTest):
    """The panel re-reads the vehicle whenever the selected tank or setup changes, and that
    hook lives as long as the panel does. It is the refresh signal that survives a lobby
    teardown, which empties the event managers a subscription would otherwise rely on."""

    def setUp(self):
        LoadoutPanelTest.setUp(self)
        self.updates = []
        loadout_panel._update_callback = lambda: self.updates.append(True)

    def test_every_read_asks_for_a_refresh(self):
        panel = FakePresenter(self.randomGroups())
        loadout_panel._track(panel, self.logger)
        loadout_panel._track(panel, self.logger)
        self.assertEqual(len(self.updates), 2,
                         'a repeated read still means the loadout changed')

    def test_a_panel_without_directives_still_refreshes(self):
        # The window may be hidden now but has to be right the moment it is shown again.
        loadout_panel._track(FakePresenter([FakeGroup('shells')]), self.logger)
        self.assertEqual(len(self.updates), 1)

    def test_a_failing_refresh_does_not_break_the_panel(self):
        # This runs inside the client's own view lifecycle.
        def boom():
            raise ValueError('no')

        loadout_panel._update_callback = boom
        panel = FakePresenter(self.randomGroups())
        loadout_panel._track(panel, self.logger)
        self.assertTrue(loadout_panel.is_visible(), 'tracking still succeeded')
        self.assertTrue(self.logger.exceptions, 'the failure should be reported')


class DegradationTest(unittest.TestCase):

    def test_visible_when_the_panel_could_not_be_followed(self):
        # A window that never appears is a broken mod; one that appears in the wrong place is
        # merely untidy. With no hooks installed, show it.
        self.assertFalse(loadout_panel._patched)
        self.assertTrue(loadout_panel.is_visible())


if __name__ == '__main__':
    unittest.main()
