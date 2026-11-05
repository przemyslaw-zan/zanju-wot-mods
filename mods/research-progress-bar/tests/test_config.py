# -*- coding: utf-8 -*-
"""Tests for the template that Mod Menu gets."""
from __future__ import absolute_import, print_function, unicode_literals

import unittest

from zanju_rpb import config


class MenuTemplateTest(unittest.TestCase):

    def test_the_template_carries_the_author_the_version_and_the_link(self):
        template = config._build_mod_settings_template()
        self.assertEqual(template[config._mods_settings_native('modAuthor')], config.MOD_AUTHOR)
        self.assertEqual(template[config._mods_settings_native('modVersion')], config.MOD_VERSION)
        self.assertEqual(template[config._mods_settings_native('modUrl')], config.MOD_URL)


if __name__ == '__main__':
    unittest.main()
