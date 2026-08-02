# -*- coding: utf-8 -*-
"""Tests for the runtime localization loader.

Run via `zwm test premium-time`, which puts the mod's src/ on the path and fakes the
build-generated `_mod_meta` module (see testing/zwm_test_env.py).

The parser is the interesting part: `i18n/*.yml` files are authored by translators and
hand-edited on GitHub, so it has to survive whatever shape they arrive in. In particular
an empty value means "not translated yet" and must fall through to English rather than
blanking the string in-game.
"""
from __future__ import unicode_literals

import unittest

from zanju_pt import localization


class ParseFlatYamlTest(unittest.TestCase):

    def parse(self, text):
        return localization._parse_flat_yaml(text)

    def test_reads_plain_key_value_pairs(self):
        self.assertEqual(self.parse('KEY: value'), {'KEY': 'value'})

    def test_trims_surrounding_whitespace(self):
        self.assertEqual(self.parse('   KEY   :   value   '), {'KEY': 'value'})

    def test_reads_double_quoted_values(self):
        self.assertEqual(self.parse('KEY: "value"'), {'KEY': 'value'})

    def test_decodes_escapes_in_double_quoted_values(self):
        self.assertEqual(self.parse(r'KEY: "line\nbreak"'), {'KEY': 'line\nbreak'})

    def test_decodes_escaped_quotes(self):
        self.assertEqual(self.parse(r'KEY: "say \"hi\""'), {'KEY': 'say "hi"'})

    def test_reads_single_quoted_values(self):
        self.assertEqual(self.parse("KEY: 'value'"), {'KEY': 'value'})

    def test_keeps_colons_inside_values(self):
        self.assertEqual(self.parse('KEY: Ends on: soon'), {'KEY': 'Ends on: soon'})

    def test_keeps_non_ascii_values(self):
        self.assertEqual(self.parse('KEY: Kończy się'), {'KEY': 'Kończy się'})

    def test_skips_comments_and_blank_lines(self):
        text = '\n'.join([
            '# a comment',
            '',
            '   ',
            'KEY: value',
        ])
        self.assertEqual(self.parse(text), {'KEY': 'value'})

    def test_skips_lines_without_a_separator(self):
        self.assertEqual(self.parse('not a pair\nKEY: value'), {'KEY': 'value'})

    def test_skips_entries_with_no_key(self):
        self.assertEqual(self.parse(': orphan'), {})

    def test_skips_untranslated_empty_values(self):
        # The convention behind i18n/_template.yml: a key left empty is untranslated, so it
        # must not land in the bundle at all — otherwise it would shadow the English text
        # merged underneath and show as blank in-game.
        for line in ('KEY:', 'KEY: ""', "KEY: ''", 'KEY:    '):
            self.assertEqual(self.parse(line), {}, 'should skip: {0!r}'.format(line))

    def test_keeps_later_duplicate_keys(self):
        self.assertEqual(self.parse('KEY: first\nKEY: second'), {'KEY': 'second'})

    def test_falls_back_to_raw_text_for_malformed_quotes(self):
        # Not valid JSON, but a translator would still expect to see something sensible.
        parsed = self.parse('KEY: "unterminated\\"')
        self.assertEqual(list(parsed), ['KEY'])
        self.assertTrue(parsed['KEY'])

    def test_reads_a_full_file(self):
        text = '\n'.join([
            '# Header counter units',
            'UNIT_DAY_SHORT: "d"',
            'UNIT_HOUR_SHORT: "h"',
            'UNIT_MINUTE_SHORT: "m"',
            '',
            '# Tooltips',
            'TOOLTIP_ENDS_ON: "Ends on:"',
            'TOOLTIP_UNTRANSLATED: ""',
        ])
        self.assertEqual(self.parse(text), {
            'UNIT_DAY_SHORT': 'd',
            'UNIT_HOUR_SHORT': 'h',
            'UNIT_MINUTE_SHORT': 'm',
            'TOOLTIP_ENDS_ON': 'Ends on:',
        })


class GetTextTest(unittest.TestCase):

    def setUp(self):
        # No client, so no bundle can be read: every lookup falls back to the key itself.
        localization._bundle_cache.clear()
        self.addCleanup(localization._bundle_cache.clear)

    def test_returns_the_key_when_no_translation_is_available(self):
        self.assertEqual(localization.get_text('TOOLTIP_ENDS_ON'), 'TOOLTIP_ENDS_ON')

    def test_applies_format_arguments(self):
        localization._bundle_cache[('en', 'en')] = {'GREETING': 'Ends in {days} days'}
        self.assertEqual(localization.get_text('GREETING', days=3), 'Ends in 3 days')

    def test_returns_the_template_when_a_placeholder_is_unknown(self):
        # A translator can mistype a placeholder; showing the raw template beats crashing
        # the view that asked for the string.
        localization._bundle_cache[('en', 'en')] = {'GREETING': 'Ends in {dayz} days'}
        self.assertEqual(localization.get_text('GREETING', days=3), 'Ends in {dayz} days')

    def test_returns_the_template_when_a_placeholder_is_malformed(self):
        localization._bundle_cache[('en', 'en')] = {'GREETING': 'Ends in {days days'}
        self.assertEqual(localization.get_text('GREETING', days=3), 'Ends in {days days')

    def test_ignores_extra_format_arguments(self):
        localization._bundle_cache[('en', 'en')] = {'GREETING': 'Ends soon'}
        self.assertEqual(localization.get_text('GREETING', days=3), 'Ends soon')


class MakeTooltipTest(unittest.TestCase):

    def setUp(self):
        localization._bundle_cache.clear()
        self.addCleanup(localization._bundle_cache.clear)

    def test_wraps_header_and_body_in_the_client_markup(self):
        localization._bundle_cache[('en', 'en')] = {'H': 'Title', 'B': 'Body text'}
        self.assertEqual(
            localization.make_tooltip('H', 'B'),
            '{HEADER}Title{/HEADER}{BODY}Body text{/BODY}',
        )


class LanguageCodeTest(unittest.TestCase):

    def test_normalizes_client_language_codes(self):
        self.assertEqual(localization._normalize_language_code('EN'), 'en')
        self.assertEqual(localization._normalize_language_code('pt-br'), 'pt_br')
        self.assertEqual(localization._normalize_language_code('en_US.UTF-8'), 'en_us')
        self.assertEqual(localization._normalize_language_code('  pl  '), 'pl')

    def test_rejects_empty_language_codes(self):
        self.assertIsNone(localization._normalize_language_code(''))
        self.assertIsNone(localization._normalize_language_code(None))

    def test_defaults_to_english_without_a_client(self):
        self.assertEqual(localization._detect_client_language(), 'en')

    def test_text_domain_follows_the_mod_id(self):
        # Translations are read from the mounted package VFS, not from disk.
        self.assertEqual(localization._TEXT_DOMAIN, 'mods/zanju.premiumtime/text')


if __name__ == '__main__':
    unittest.main()
