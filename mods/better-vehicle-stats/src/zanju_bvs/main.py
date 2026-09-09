"""
zanju_bvs.main

Puts the values behind the modifier rows into the vehicle stat lists. The client shows a
row for a dispersion factor or a terrain resistance only when something modifies it, and
that row states the modifier rather than the value. This mod hides those rows and prints
the values instead, on all four stat surfaces.

BigWorld scripting uses Python 2.7. Avoid Python-3-only syntax.
"""
from __future__ import print_function, unicode_literals

import logging

from . import integration
from .constants import MOD_ID

_logger = logging.getLogger('zanju.bettervehiclestats')


def init():
    _logger.info('%s initializing', MOD_ID)
    try:
        integration.install(_logger)
        _logger.info('%s initialized', MOD_ID)
    except Exception:
        _logger.exception('%s failed to initialize', MOD_ID)


def fini():
    try:
        integration.uninstall(_logger)
    except Exception:
        _logger.exception('%s error in fini', MOD_ID)
