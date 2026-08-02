# -*- coding: utf-8 -*-
"""Tests for the shared "is this subscription still running" rule and the client readers.

The rule itself is pure and gets the thorough treatment. The readers can only be checked
for their degradation contract here — with no WoT client to talk to they must return an
empty string rather than raise, because they run inside a tooltip that the game is in the
middle of building.
"""
from __future__ import unicode_literals

import logging
import unittest

from zanju_pt import subscriptions
from zanju_pt.formatting import end_text_if_running

NOW = 1800000000  # no underscore separators: this runs on Python 2.7
HOUR = 3600


class SilentLogger(logging.Logger):
    """Captures exception() calls so tests can assert on them without printing."""

    def __init__(self):
        logging.Logger.__init__(self, 'test')
        self.exceptions = []
        self.addHandler(logging.NullHandler())

    def exception(self, message, *args, **kwargs):
        self.exceptions.append(message)


class EndTextIfRunningTest(unittest.TestCase):

    def test_returns_text_for_a_future_expiry(self):
        self.assertTrue(end_text_if_running(NOW + HOUR, NOW))

    def test_returns_nothing_once_the_expiry_has_passed(self):
        # The client can still advertise a subscription after it lapsed, because the
        # server confirmation lags; a past expiry means "not running" regardless.
        self.assertEqual(end_text_if_running(NOW - 1, NOW), '')

    def test_returns_nothing_exactly_at_the_expiry(self):
        self.assertEqual(end_text_if_running(NOW, NOW), '')

    def test_returns_nothing_when_not_active(self):
        self.assertEqual(end_text_if_running(NOW + HOUR, NOW, is_active=False), '')

    def test_returns_nothing_for_a_missing_expiry(self):
        for expiry in (0, None, ''):
            self.assertEqual(end_text_if_running(expiry, NOW), '', 'expiry={0!r}'.format(expiry))

    def test_returns_nothing_for_an_unusable_expiry(self):
        for expiry in ('soon', object()):
            self.assertEqual(end_text_if_running(expiry, NOW), '', 'expiry={0!r}'.format(expiry))

    def test_accepts_a_string_expiry_from_the_client(self):
        self.assertEqual(
            end_text_if_running(str(NOW + HOUR), NOW),
            end_text_if_running(NOW + HOUR, NOW),
        )

    def test_truncates_a_fractional_expiry(self):
        self.assertEqual(
            end_text_if_running(NOW + HOUR + 0.7, NOW),
            end_text_if_running(NOW + HOUR, NOW),
        )


class ReaderDegradationTest(unittest.TestCase):
    """Without a client the reader must stay quiet and empty, not raise."""

    def setUp(self):
        self.logger = SilentLogger()

    def test_premium_reader_returns_empty_without_a_client(self):
        self.assertEqual(subscriptions.premium_ends_on(self.logger), '')

    def test_reader_reports_the_failure(self):
        subscriptions.premium_ends_on(self.logger)
        self.assertEqual(len(self.logger.exceptions), 1)


if __name__ == '__main__':
    unittest.main()
