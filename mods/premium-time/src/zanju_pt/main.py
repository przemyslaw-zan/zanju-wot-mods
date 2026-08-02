"""
zanju_pt.main

Integrates remaining premium time into the lobby header: the Premium Account button
shows a live countdown instead of its static day count, and its hover tooltip gains
the exact end date and time. There is nothing to configure, so the mod keeps no
config file and registers no settings menu.

BigWorld scripting uses Python 2.7. Avoid Python-3-only syntax.
"""
from __future__ import print_function, unicode_literals

import logging

from . import tooltip_blocks
from .constants import MOD_ID
from .gameface import header_inject

_logger = logging.getLogger('zanju.premiumtime')


def init():
    _logger.info('%s initializing', MOD_ID)
    try:
        header_inject.install(_logger)
        tooltip_blocks.install(_logger)
        _logger.info('%s initialized', MOD_ID)
    except Exception:
        _logger.exception('%s failed to initialize', MOD_ID)


def fini():
    try:
        tooltip_blocks.uninstall(_logger)
        header_inject.uninstall(_logger)
    except Exception:
        _logger.exception('%s error in fini', MOD_ID)
