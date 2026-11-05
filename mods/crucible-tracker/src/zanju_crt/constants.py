"""Stable constants for the Crucible tracker mod."""
from __future__ import absolute_import, print_function, unicode_literals

# MOD_ID / MOD_NAME / MOD_VERSION come from meta.xml via the build-generated _mod_meta module
# (see tools/commands/build.py). meta.xml is the single authored source of these values.
# MOD_AUTHOR / MOD_URL come from tools/core/mod_meta.py, because meta.xml has no field for them.
from ._mod_meta import MOD_AUTHOR, MOD_ID, MOD_NAME, MOD_URL, MOD_VERSION  # noqa: F401

LOGGER_NAME = 'zanju.crucibletracker'

# AppData subfolder holding this mod's config and the battle transport; see
# storage.resolve_mod_data_dir(). The name decides where the player's settings are, so it must
# never change.
MOD_CONFIG_DIR_NAME = 'crucible-tracker'
