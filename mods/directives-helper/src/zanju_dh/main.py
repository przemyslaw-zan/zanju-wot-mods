"""
zanju_dh.main

Shows the player's directives in a movable garage window: how many are owned in the depot,
split into crew and equipment directives, which of them fit the selected vehicle, and which
one is currently fitted to it.

BigWorld scripting uses Python 2.7. Avoid Python-3-only syntax.
"""
from __future__ import print_function, unicode_literals

import logging

from .constants import MOD_ID
from .gameface import window_inject

_logger = logging.getLogger('zanju.directiveshelper')


def init():
    _logger.info('%s initializing', MOD_ID)
    try:
        window_inject.install(_logger)
        _logger.info('%s initialized', MOD_ID)
    except Exception:
        _logger.exception('%s failed to initialize', MOD_ID)


def fini():
    try:
        window_inject.uninstall(_logger)
    except Exception:
        _logger.exception('%s error in fini', MOD_ID)
