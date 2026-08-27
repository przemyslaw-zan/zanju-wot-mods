"""
zanju_ct.main

Shows one small garage banner per active personal missions campaign. Each banner carries the
campaign number over the mission the selected vehicle is currently working on, and its hover
card gives the operation, the full mission name and the condition progress. A campaign the
vehicle fits no mission in stays on screen in grey.

BigWorld scripting uses Python 2.7. Avoid Python-3-only syntax.
"""
from __future__ import absolute_import, print_function, unicode_literals

import logging

from .constants import LOGGER_NAME, MOD_ID
from .gameface import widgets_inject

_logger = logging.getLogger(LOGGER_NAME)


def init():
    _logger.info('%s initializing', MOD_ID)
    try:
        widgets_inject.install(_logger)
        _logger.info('%s initialized', MOD_ID)
    except Exception:
        _logger.exception('%s failed to initialize', MOD_ID)


def fini():
    try:
        widgets_inject.uninstall(_logger)
    except Exception:
        _logger.exception('%s error in fini', MOD_ID)
