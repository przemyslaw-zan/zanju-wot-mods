"""Stable constants for the campaign tracker mod."""
from __future__ import absolute_import, print_function, unicode_literals

# MOD_ID / MOD_NAME come from meta.xml via the build-generated _mod_meta module
# (see tools/commands/build.py). meta.xml is the single authored source of these values.
from ._mod_meta import MOD_ID, MOD_NAME  # noqa: F401

LOGGER_NAME = 'zanju.campaigntracker'
