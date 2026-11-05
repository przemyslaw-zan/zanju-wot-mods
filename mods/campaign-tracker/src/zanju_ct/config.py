# -*- coding: utf-8 -*-
"""The settings of the campaign tracker: whether the banners show, and on which side they stand.

The settings live in `config.json` in AppData, so a modpack reinstall does not reset them (see
storage). Mod Menu shows them in game when it is installed. The file is the source of truth and
the menu is a mirror of it: see mod_menu and docs/reference/in-game-settings.md.

The banners stand in the shared banner tray beside the vehicle name. `traySide` picks the side,
and the banners of the other mods on the same side share the row with these. See tray.js.
"""
from __future__ import absolute_import, print_function, unicode_literals

import io
import json
import os

from . import mod_menu
from .constants import MOD_AUTHOR, MOD_CONFIG_DIR_NAME, MOD_NAME, MOD_URL, MOD_VERSION
from .localization import get_text as _loc
from .localization import make_tooltip as _loc_tooltip
from .storage import atomic_write_text, resolve_mod_data_dir

SIDE_RIGHT = 'right'
SIDE_LEFT = 'left'
# The order of the sides in the menu. The menu stores the index, the file stores the name.
_SIDES = (SIDE_RIGHT, SIDE_LEFT)

_FILE_NAME = 'config.json'
_CONFIG_VERSION = 1

DEFAULTS = {
    'enabled': True,
    'traySide': SIDE_RIGHT,
}

_state = dict(DEFAULTS)


def current():
    return dict(_state)


def is_enabled():
    return bool(_state['enabled'])


def tray_side():
    return _state['traySide']


def sanitize(values):
    """Keep only the known keys, each in its valid form. Anything else is dropped."""
    clean = {}
    if 'enabled' in values:
        clean['enabled'] = bool(values['enabled'])
    if 'traySide' in values and values['traySide'] in _SIDES:
        clean['traySide'] = values['traySide']
    return clean


def apply(changes):
    """Take the valid changes into the state. Returns the names of the keys that changed."""
    changed = []
    for key, value in sorted(sanitize(changes).items()):
        if _state.get(key) != value:
            _state[key] = value
            changed.append(key)
    return changed


def load(logger):
    """Read config.json, with the defaults for anything missing or broken.

    A missing file is written with the defaults, so a player without Mod Menu finds a file to
    edit, as every mod of this repository does on its first start.
    """
    path = _path()
    if not path:
        return current()
    if not os.path.isfile(path):
        save(logger)
        return current()
    try:
        with io.open(path, 'r', encoding='utf-8') as handle:
            stored = json.loads(handle.read())
    except Exception:
        logger.exception('Failed to read %s; using the defaults', path)
        return current()
    if isinstance(stored, dict):
        apply(stored)
    return current()


def save(logger):
    path = _path()
    if not path:
        return False
    payload = dict(_state)
    payload['configVersion'] = _CONFIG_VERSION
    # json.dumps returns bytes on Python 2 while the writer opens the file in text mode, which
    # only accepts unicode. The default ensure_ascii makes the decode safe.
    text = json.dumps(payload, indent=4, sort_keys=True)
    if not isinstance(text, type(u'')):
        text = text.decode('ascii')
    return atomic_write_text(path, text, logger)


def _path():
    data_dir = resolve_mod_data_dir(MOD_CONFIG_DIR_NAME)
    if not data_dir:
        return None
    return os.path.join(data_dir, _FILE_NAME)


def menu_values(state=None):
    """The menu's form of the settings. The menu stores a radio group as an index."""
    state = _state if state is None else state
    return {
        'enabled': bool(state['enabled']),
        'traySide': _SIDES.index(state['traySide']) if state['traySide'] in _SIDES else 0,
    }


def from_menu(settings):
    """The config form of what the menu sent. Keys the menu did not send stay out."""
    changes = {}
    if 'enabled' in settings:
        changes['enabled'] = bool(settings['enabled'])
    if 'traySide' in settings:
        try:
            changes['traySide'] = _SIDES[int(settings['traySide'])]
        except (TypeError, ValueError, IndexError):
            pass
    return changes


def menu_template():
    # Built from the defaults, never from the current values: the per-mod Reset of the menu
    # restores what the template says.
    values = menu_values(DEFAULTS)
    return {
        'modDisplayName': MOD_NAME,
        'modAuthor': MOD_AUTHOR,
        'modVersion': MOD_VERSION,
        'modUrl': MOD_URL,
        'enabled': values['enabled'],
        'column1': [
            {
                'type': 'RadioButtonGroup',
                'text': _loc('SETTING_TRAY_SIDE'),
                'tooltip': _loc_tooltip('SETTING_TRAY_SIDE', 'TOOLTIP_TRAY_SIDE_BODY'),
                'options': [
                    {'label': _loc('SETTING_TRAY_SIDE_RIGHT')},
                    {'label': _loc('SETTING_TRAY_SIDE_LEFT')},
                ],
                'value': values['traySide'],
                'varName': 'traySide',
            },
        ],
    }


def register_menu(mod_id, logger, on_changed):
    """Show the settings in Mod Menu. `on_changed(keys)` runs after a change was saved."""
    def _on_menu_change(settings):
        changed = apply(from_menu(settings))
        if not changed:
            return
        save(logger)
        logger.info('Settings changed in Mod Menu: %s', ', '.join(changed))
        on_changed(changed)

    return mod_menu.register(mod_id, menu_template(), menu_values(DEFAULTS), menu_values(),
                             _on_menu_change, logger)
