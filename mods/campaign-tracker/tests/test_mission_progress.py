# -*- coding: utf-8 -*-
"""Tests for the parts of the progress reader that do not need a running client.

The one covered here is the split of a condition description, because both halves of it are
guesses about a string the client composes. The client writes a condition, a newline, the word
"Restriction!" in Scaleform markup, then the rule that word introduces. The widget document
renders none of that markup, so a missed split reaches the card as visible angle brackets.
"""
from __future__ import absolute_import, print_function, unicode_literals

import unittest

from zanju_ct import mission_progress


class _Logger(object):
    """Records the exception() calls the reader makes instead of printing them."""

    def __init__(self):
        self.failures = []

    def exception(self, message, *args):
        self.failures.append(message)


class _Progress(object):
    """Stands in for a client `BodyProgress`, which is all the split reads."""

    def __init__(self, description, limiter=None):
        self._description = description
        self._limiter = limiter

    def getDescription(self):
        return self._description

    def getLimiter(self):
        return self._limiter


_ALERT = "<font face='$FieldFont' size='14' color='#EE7000'>Restriction!</font>"


class PlainTests(unittest.TestCase):

    def test_markup_is_taken_out(self):
        self.assertEqual(mission_progress._plain(_ALERT), 'Restriction!')

    def test_entities_are_read_back(self):
        self.assertEqual(mission_progress._plain('Spot &amp; shoot'), 'Spot & shoot')
        # `&amp;` is replaced last, so an escaped entity survives as itself.
        self.assertEqual(mission_progress._plain('&amp;lt;'), '&lt;')

    def test_nothing_is_not_an_error(self):
        self.assertEqual(mission_progress._plain(None), '')


class SplitRestrictionTests(unittest.TestCase):

    def setUp(self):
        self.logger = _Logger()
        # The label lookup needs a client. Without one it answers with an empty string, which
        # leaves the label in the rule rather than cutting the wrong text out of it.
        self.label = mission_progress._restriction_label(self.logger)

    def test_a_condition_without_a_limiter_keeps_its_whole_description(self):
        progress = _Progress('Destroy 2 enemy vehicles.')
        text, label, restriction = mission_progress._split_restriction(progress, self.logger)
        self.assertEqual(text, 'Destroy 2 enemy vehicles.')
        self.assertEqual(label, '')
        self.assertEqual(restriction, '')

    def test_a_limiter_is_split_off_and_stripped(self):
        progress = _Progress(
            'Be the top player by vehicles destroyed.\n%s Destroy 2 enemy vehicles.' % _ALERT,
            limiter=object())
        text, label, restriction = mission_progress._split_restriction(progress, self.logger)
        self.assertEqual(text, 'Be the top player by vehicles destroyed.')
        # No client here, so the label stays at the front of the rule rather than being cut off
        # by a guess. Either way, no markup survives.
        self.assertEqual((label + ' ' + restriction).strip(),
                         'Restriction! Destroy 2 enemy vehicles.')
        self.assertNotIn('<', label + restriction)

    def test_the_last_newline_is_the_one_the_client_put_there(self):
        progress = _Progress('First line.\nSecond line.\n%s Rule.' % _ALERT, limiter=object())
        text, _, restriction = mission_progress._split_restriction(progress, self.logger)
        self.assertEqual(text, 'First line.\nSecond line.')
        self.assertTrue(restriction.endswith('Rule.'))

    def test_a_newline_without_a_limiter_is_left_alone(self):
        progress = _Progress('First line.\nSecond line.')
        text, label, restriction = mission_progress._split_restriction(progress, self.logger)
        self.assertEqual(text, 'First line.\nSecond line.')
        self.assertEqual(restriction, '')

    def test_a_limiter_the_client_will_not_report_keeps_the_row(self):
        class _Broken(_Progress):

            def getLimiter(self):
                raise AttributeError('no such method')

        progress = _Broken('Be the top player.\n%s Destroy 2.' % _ALERT)
        # Its own logger, because setUp already asked for the label without a client to give it.
        logger = _Logger()
        text, _, restriction = mission_progress._split_restriction(progress, logger)
        # The description is handed over as the client composed it. Markup is only taken out of
        # a restriction the client agrees is there, and here it will not say.
        self.assertEqual(text, progress.getDescription())
        self.assertEqual(restriction, '')
        self.assertEqual(len(logger.failures), 1)


class UnlimitedLabelTests(unittest.TestCase):
    """A one-battle mission has no battle budget, so it must not claim an unlimited one.

    The client gates its own line the same way: `getDummyHeaderType` answers `DISPLAY_TYPE.NONE`
    for exactly these missions, and a header typed NONE draws nothing.
    """

    class _Quest(object):

        def __init__(self, one_battle):
            self._one_battle = one_battle

        def isOneBattleQuest(self):
            return self._one_battle

    def test_a_one_battle_mission_says_nothing_about_its_battles(self):
        for is_main in (True, False):
            self.assertEqual(
                mission_progress._unlimited_label(self._Quest(True), is_main), '')

    def test_a_mission_with_no_limit_asks_the_client_for_the_wording(self):
        # No client here, so the lookup raises rather than answering. What matters is that it
        # is reached at all: a mission with no battle limit must not fall silent.
        self.assertRaises(Exception,
                          mission_progress._unlimited_label, self._Quest(False), True)


if __name__ == '__main__':
    unittest.main()
