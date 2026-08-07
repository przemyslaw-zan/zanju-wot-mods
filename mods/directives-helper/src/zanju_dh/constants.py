"""Stable constants for the directives helper mod."""
from __future__ import print_function, unicode_literals

# MOD_ID / MOD_NAME come from meta.xml via the build-generated _mod_meta module
# (see tools/commands/build.py). meta.xml is the single authored source of these values.
from ._mod_meta import MOD_ID, MOD_NAME  # noqa: F401

# AppData subfolder holding this mod's config; see storage.resolve_mod_data_dir().
MOD_CONFIG_DIR_NAME = 'directives-helper'
