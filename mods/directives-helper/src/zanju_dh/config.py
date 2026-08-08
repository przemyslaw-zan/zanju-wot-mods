# -*- coding: utf-8 -*-
"""Remembered window state: where the window sits and whether it is folded.

Stored in AppData rather than next to the package so a modpack reinstall does not reset it
(see storage.py). The file is written whenever the JS side reports a change, which is on
drag release and on a fold toggle -- both rare, so there is no write throttling.

The viewport the position was captured at is stored alongside it. WoT's UI scale is
quantized per resolution bucket, so raw pixels stop meaning the same thing when the player
changes resolution; keeping the capture viewport lets the window be rescaled proportionally
instead of ending up off-screen. See docs/reference/gameface-mod-widgets.md.
"""
from __future__ import print_function, unicode_literals

import io
import json
import logging
import os

from .storage import atomic_write_text, resolve_mod_data_dir

_logger = logging.getLogger('zanju.directiveshelper')

_FILE_NAME = 'window.json'
_CONFIG_VERSION = 1

# x/y are the window's top-left in pixels; None means "not positioned yet", which the JS
# side reads as "use the default corner". `width` is 0 until the player resizes it, which the
# JS reads as "size to the stylesheet's default".
_DEFAULTS = {
    'configVersion': _CONFIG_VERSION,
    'x': None,
    'y': None,
    'width': 0,
    'viewportWidth': 0,
    'viewportHeight': 0,
    'folded': False,
    'showUnowned': False,
}

_state = dict(_DEFAULTS)


def load():
    """Read the stored state, falling back to defaults for anything missing or broken."""
    path = _config_path()
    if not path or not os.path.isfile(path):
        return current()

    try:
        with io.open(path, 'r', encoding='utf-8') as handle:
            stored = json.loads(handle.read())
    except Exception:
        _logger.exception('Failed to read the window state; using defaults')
        return current()

    if isinstance(stored, dict):
        _state.update(_sanitize(stored))
    return current()


def current():
    return dict(_state)


def update(x=None, y=None, width=None, viewport_width=None, viewport_height=None,
           folded=None, show_unowned=None):
    """Apply a change reported by the window and persist it. Returns the new state."""
    changes = {
        'x': x,
        'y': y,
        'width': width,
        'viewportWidth': viewport_width,
        'viewportHeight': viewport_height,
        'folded': folded,
        'showUnowned': show_unowned,
    }
    _state.update(_sanitize({k: v for k, v in changes.items() if v is not None}))
    save()
    return current()


def save():
    path = _config_path()
    if not path:
        return False
    try:
        payload = dict(_state)
        payload['configVersion'] = _CONFIG_VERSION
        # json.dumps returns bytes on Python 2.7 while the writer opens the file in text
        # mode, which only accepts unicode; the default ensure_ascii makes the decode safe.
        text = json.dumps(payload, indent=4, sort_keys=True)
        if not isinstance(text, type(u'')):
            text = text.decode('ascii')
        atomic_write_text(path, text, _logger)
        return True
    except Exception:
        _logger.exception('Failed to write the window state')
        return False


def _sanitize(values):
    clean = {}
    for key in ('x', 'y', 'width', 'viewportWidth', 'viewportHeight'):
        if key in values:
            number = _as_int(values[key])
            if number is not None:
                clean[key] = number
    for key in ('folded', 'showUnowned'):
        if key in values:
            clean[key] = bool(values[key])
    return clean


def _as_int(value):
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    # Negative coordinates would park the window off-screen; a stored viewport of 0 means
    # "unknown", which the JS side already treats as "do not rescale".
    return max(0, number)


def _config_path():
    data_dir = resolve_mod_data_dir()
    if not data_dir:
        return None
    return os.path.join(data_dir, _FILE_NAME)
