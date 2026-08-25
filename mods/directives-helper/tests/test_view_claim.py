# -*- coding: utf-8 -*-
"""Tests for the rule that keeps this mod from starving other mods of a hangar sub-view.

The regression these guard against: the mod attached to every free candidate rather than one,
so whichever mod's patch ran first took them all and `directives-helper` never appeared.
"""
from __future__ import absolute_import, print_function, unicode_literals

import unittest

from zanju_dh import view_claim


class _ModeState(object):
    pass


class _VehicleMenu(object):
    pass


class _MainMenu(object):
    pass


class DecideTest(unittest.TestCase):
    def test_attaches_to_the_first_free_candidate(self):
        claim, claimed = view_claim.decide(_ModeState, is_claimed=False, claimed_class=None)
        self.assertTrue(claim)
        self.assertIs(claimed, _ModeState)

    def test_leaves_every_later_candidate_alone(self):
        # The bug: without this, the mod took all three and the next mod along got nothing.
        claim, claimed = view_claim.decide(
            _VehicleMenu, is_claimed=False, claimed_class=_ModeState)
        self.assertFalse(claim)
        self.assertIs(claimed, _ModeState)

    def test_re_attaches_to_its_own_class_when_the_garage_is_rebuilt(self):
        # Every garage entry builds fresh view models, so the same class comes round again.
        claim, claimed = view_claim.decide(
            _ModeState, is_claimed=False, claimed_class=_ModeState)
        self.assertTrue(claim)
        self.assertIs(claimed, _ModeState)

    def test_never_takes_a_view_another_mod_already_holds(self):
        claim, claimed = view_claim.decide(_ModeState, is_claimed=True, claimed_class=None)
        self.assertFalse(claim)
        self.assertIsNone(claimed)

    def test_gives_up_its_usual_view_when_another_mod_takes_it(self):
        # Its preference is dropped, so the next free candidate can adopt it this session
        # rather than the mod going without a view entirely.
        claim, claimed = view_claim.decide(
            _ModeState, is_claimed=True, claimed_class=_ModeState)
        self.assertFalse(claim)
        self.assertIsNone(claimed)

    def test_adopts_the_next_free_candidate_after_giving_one_up(self):
        _, claimed = view_claim.decide(_ModeState, is_claimed=True, claimed_class=_ModeState)
        claim, claimed = view_claim.decide(
            _VehicleMenu, is_claimed=False, claimed_class=claimed)
        self.assertTrue(claim)
        self.assertIs(claimed, _VehicleMenu)

    def test_keeps_its_preference_when_a_different_view_is_taken(self):
        claim, claimed = view_claim.decide(
            _MainMenu, is_claimed=True, claimed_class=_ModeState)
        self.assertFalse(claim)
        self.assertIs(claimed, _ModeState)


class ThreeCandidatesTest(unittest.TestCase):
    """Walks the whole candidate list the way the client's view building does."""

    CANDIDATES = (_ModeState, _VehicleMenu, _MainMenu)

    def _walk(self, taken_by_others=()):
        claimed_class = None
        attached = []
        for candidate in self.CANDIDATES:
            claim, claimed_class = view_claim.decide(
                candidate, candidate in taken_by_others, claimed_class)
            if claim:
                attached.append(candidate)
        return attached

    def test_attaches_to_exactly_one_view(self):
        self.assertEqual(self._walk(), [_ModeState])

    def test_leaves_the_other_two_free_for_other_mods(self):
        attached = self._walk()
        self.assertEqual(len(attached), 1)
        remaining = [c for c in self.CANDIDATES if c not in attached]
        self.assertEqual(len(remaining), 2)

    def test_steps_past_views_other_mods_hold(self):
        self.assertEqual(self._walk(taken_by_others=(_ModeState,)), [_VehicleMenu])
        self.assertEqual(
            self._walk(taken_by_others=(_ModeState, _VehicleMenu)), [_MainMenu])

    def test_attaches_to_nothing_when_every_candidate_is_taken(self):
        self.assertEqual(self._walk(taken_by_others=self.CANDIDATES), [])


if __name__ == '__main__':
    unittest.main()
