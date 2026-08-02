# -*- coding: utf-8 -*-
"""Tests for the end-time formatting helpers.

These run without a WoT client, which is the interesting half of the contract: every
client API the module touches is imported lazily inside a try/except so the mod degrades
to stdlib formatting instead of breaking the tooltip it is feeding.
"""
from __future__ import unicode_literals

import calendar
import os
import time
import unittest

from zanju_pt import formatting


class FixedTimezoneTest(unittest.TestCase):
    """Pins TZ so offset formatting is asserted against a known zone, not the runner's."""

    TZ = None

    def setUp(self):
        if self.TZ is None:
            return
        self._previous_tz = os.environ.get('TZ')
        os.environ['TZ'] = self.TZ
        time.tzset()
        self.addCleanup(self._restore_tz)

    def _restore_tz(self):
        if self._previous_tz is None:
            os.environ.pop('TZ', None)
        else:
            os.environ['TZ'] = self._previous_tz
        time.tzset()


class ServerTimeTest(unittest.TestCase):

    def test_falls_back_to_the_client_clock_without_a_client(self):
        self.assertAlmostEqual(formatting.server_now(), time.time(), delta=5)

    def test_offset_is_zero_without_a_client(self):
        self.assertAlmostEqual(formatting.server_time_offset(), 0.0, delta=1)


class FormatEndDateTimeTest(FixedTimezoneTest):
    TZ = 'UTC'

    def test_formats_date_and_time_with_seconds(self):
        # Seconds matter: the tooltip shows an exact end moment, not a rounded one.
        timestamp = calendar.timegm((2026, 7, 27, 14, 5, 9, 0, 0, 0))
        self.assertEqual(formatting.format_end_datetime(timestamp), '2026-07-27 14:05:09')

    def test_returns_empty_string_for_unformattable_input(self):
        # Note: None is not unformattable — time.localtime(None) means "now" — so the
        # guard is exercised with a value the stdlib genuinely rejects.
        self.assertEqual(formatting.format_end_datetime('not-a-timestamp'), '')
        self.assertEqual(formatting.format_end_datetime(float('nan')), '')


class UtcOffsetLabelTest(unittest.TestCase):

    def _label_in(self, tz, timestamp):
        previous = os.environ.get('TZ')
        os.environ['TZ'] = tz
        time.tzset()
        try:
            return formatting.utc_offset_label(timestamp)
        finally:
            if previous is None:
                os.environ.pop('TZ', None)
            else:
                os.environ['TZ'] = previous
            time.tzset()

    def test_utc_has_a_zero_offset(self):
        self.assertEqual(self._label_in('UTC', calendar.timegm((2026, 1, 15, 12, 0, 0, 0, 0, 0))), 'UTC+0')

    def test_reports_standard_time_offset(self):
        # Warsaw in January: CET, one hour ahead.
        self.assertEqual(
            self._label_in('Europe/Warsaw', calendar.timegm((2026, 1, 15, 12, 0, 0, 0, 0, 0))),
            'UTC+1',
        )

    def test_reports_daylight_saving_offset(self):
        # Same zone in July: CEST, two hours ahead. The offset is resolved at the target
        # timestamp, so a subscription ending after a DST switch is labelled correctly.
        self.assertEqual(
            self._label_in('Europe/Warsaw', calendar.timegm((2026, 7, 15, 12, 0, 0, 0, 0, 0))),
            'UTC+2',
        )

    def test_reports_negative_offsets(self):
        self.assertEqual(
            self._label_in('America/New_York', calendar.timegm((2026, 1, 15, 12, 0, 0, 0, 0, 0))),
            'UTC-5',
        )

    def test_reports_half_hour_offsets(self):
        self.assertEqual(
            self._label_in('Asia/Kolkata', calendar.timegm((2026, 1, 15, 12, 0, 0, 0, 0, 0))),
            'UTC+5:30',
        )

    def test_returns_empty_string_for_unusable_input(self):
        self.assertEqual(formatting.utc_offset_label('not-a-timestamp'), '')


class EndDateTimeTextTest(FixedTimezoneTest):
    TZ = 'UTC'

    def test_appends_the_offset_label(self):
        timestamp = calendar.timegm((2026, 7, 27, 14, 5, 9, 0, 0, 0))
        self.assertEqual(formatting.end_datetime_text(timestamp), '2026-07-27 14:05:09 UTC+0')

    def test_returns_empty_string_when_the_timestamp_cannot_be_formatted(self):
        self.assertEqual(formatting.end_datetime_text('not-a-timestamp'), '')


class EndsOnLabelTest(unittest.TestCase):

    def test_falls_back_to_the_key_without_a_translation_bundle(self):
        from zanju_pt import localization

        localization._bundle_cache.clear()
        self.addCleanup(localization._bundle_cache.clear)
        self.assertEqual(formatting.ends_on_label(), 'TOOLTIP_ENDS_ON')

    def test_uses_the_translated_label_when_present(self):
        from zanju_pt import localization

        localization._bundle_cache.clear()
        localization._bundle_cache[('en', 'en')] = {'TOOLTIP_ENDS_ON': 'Ends on:'}
        self.addCleanup(localization._bundle_cache.clear)
        self.assertEqual(formatting.ends_on_label(), 'Ends on:')


class BuildHeaderPayloadTest(unittest.TestCase):
    """The payload handed to header_patch.js through a wulf view model."""

    def test_time_offset_is_a_whole_number(self):
        # Regression guard: wulf number properties are integer only. Passing the raw
        # float offset makes addNumberField raise, the data model never attaches, and
        # the header button silently keeps its default label.
        offset = formatting.build_header_payload()['timeOffset']
        self.assertIsInstance(offset, int)
        self.assertNotIsInstance(offset, float)

    def test_offset_is_zero_without_a_client(self):
        self.assertEqual(formatting.build_header_payload()['timeOffset'], 0)

    def test_carries_every_unit_label_the_counter_needs(self):
        payload = formatting.build_header_payload()
        self.assertEqual(
            sorted(payload),
            ['dayUnit', 'hourUnit', 'minuteUnit', 'secondUnit', 'timeOffset'],
        )

    def test_unit_labels_are_non_empty_strings(self):
        payload = formatting.build_header_payload()
        for key in ('dayUnit', 'hourUnit', 'minuteUnit', 'secondUnit'):
            self.assertTrue(payload[key], key)


if __name__ == '__main__':
    unittest.main()
