"""
zanju_srf.main

Removes the fixed shell-spread term from the aiming reticle of twin-gun vehicles in
Salvo Fire mode, so the circle shows dispersion only -- the same thing it shows on every
other vehicle. There is nothing to configure, so the mod keeps no config file and
registers no settings menu.

BigWorld scripting uses Python 2.7. Avoid Python-3-only syntax.
"""
from __future__ import print_function, unicode_literals

import logging

from . import gun_marker
from .constants import MOD_ID

_logger = logging.getLogger('zanju.salvoreticlefix')


def init():
    _logger.info('%s initializing', MOD_ID)
    try:
        gun_marker.install(_logger)
        _logger.info('%s initialized', MOD_ID)
    except Exception:
        _logger.exception('%s failed to initialize', MOD_ID)


def fini():
    try:
        gun_marker.uninstall(_logger)
    except Exception:
        _logger.exception('%s error in fini', MOD_ID)
