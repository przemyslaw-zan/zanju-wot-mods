# -*- coding: utf-8 -*-
"""The settings of the Crucible tracker.

- `garageEnabled` shows the banner in the garage.
- `battleEnabled` shows the panel in battle.
- `traySide` puts the banner on the left or the right side of the vehicle name, in the shared
  banner tray that campaign-tracker uses too. See tray.js.
- `panelDetails` is when the battle panel shows its full information: always, while the key of
  the extended vehicle markers is held (Alt by default), or never. Without it, the panel shows
  only the icon, the bar and the figures of each condition. See gameface/battle_panel.py.
- `panelStyle` is how the battle panel shows the progress of a condition: a flat bar, or a round
  dial with the text on its right. See battle.js.
- `panelFigures` is what the figures of the battle panel show: the current and the required
  value, or only the current value.
- `panelPosition` is where the player last dragged the battle panel to, or None for the default
  place. Mod Menu does not show it.

The settings live in `config.json` in AppData, so a modpack reinstall does not reset them (see
storage). Mod Menu shows them in game when it is installed. The file is the source of truth and
the menu is a mirror of it: see mod_menu and docs/reference/in-game-settings.md.
"""
from __future__ import absolute_import, print_function, unicode_literals

import io
import json
import os

from . import mod_menu
from .constants import MOD_AUTHOR, MOD_CONFIG_DIR_NAME, MOD_NAME, MOD_URL, MOD_VERSION
from .localization import get_text as _loc
from .localization import get_wg_text
from .localization import make_tooltip as _loc_tooltip
from .storage import atomic_write_text, resolve_mod_data_dir

SIDE_RIGHT = 'right'
SIDE_LEFT = 'left'
# The order of the sides in the menu. The menu stores the index, the file stores the name.
_SIDES = (SIDE_RIGHT, SIDE_LEFT)
DETAILS_ALWAYS = 'always'
DETAILS_ALT = 'alt'
DETAILS_NEVER = 'never'
# The order in the menu, the same as the client's own setting for the details of the damage log.
_DETAILS = (DETAILS_ALWAYS, DETAILS_ALT, DETAILS_NEVER)
# The labels of that setting of the client, in the language of the client. The English text is
# there only for a client that lost the keys.
_DETAILS_LABELS = (
    ('#settings:feedback/tab/damageLogPanel/details/always', 'Display always'),
    ('#settings:feedback/tab/damageLogPanel/details/byAlt', 'Press Alt to display'),
    ('#settings:feedback/tab/damageLogPanel/details/hide', 'Do not display'),
)
STYLE_FLAT = 'flat'
STYLE_ROUND = 'round'
_STYLES = (STYLE_FLAT, STYLE_ROUND)
FIGURES_BOTH = 'both'
FIGURES_VALUE = 'value'
_FIGURES = (FIGURES_BOTH, FIGURES_VALUE)
_FLAGS = ('enabled', 'garageEnabled', 'battleEnabled')
# The settings with a fixed set of values, each with its values in the order of the menu.
_CHOICES = (
    ('traySide', _SIDES),
    ('panelDetails', _DETAILS),
    ('panelStyle', _STYLES),
    ('panelFigures', _FIGURES),
)

_FILE_NAME = 'config.json'
_CONFIG_VERSION = 1

DEFAULTS = {
    'enabled': True,
    'garageEnabled': True,
    'battleEnabled': True,
    'traySide': SIDE_LEFT,
    'panelDetails': DETAILS_ALWAYS,
    'panelStyle': STYLE_FLAT,
    'panelFigures': FIGURES_BOTH,
    'panelPosition': None,
}

# The fields of `panelPosition`. The position is kept with the size of the screen it was dragged
# on, so a change of resolution moves the panel to the same relative place.
_POSITION_FIELDS = ('x', 'y', 'parentWidth', 'parentHeight')

_state = dict(DEFAULTS)


def current():
    return dict(_state)


def garage_enabled():
    return bool(_state['enabled'] and _state['garageEnabled'])


def battle_enabled():
    return bool(_state['enabled'] and _state['battleEnabled'])


def tray_side():
    return _state['traySide']


def panel_details():
    return _state['panelDetails']


def panel_style():
    return _state['panelStyle']


def panel_figures():
    return _state['panelFigures']


def panel_position():
    position = _state.get('panelPosition')
    return dict(position) if position else None


def set_panel_position(position, logger):
    """Keep where the player dragged the battle panel to, and save it. False when it is invalid."""
    clean = _sanitize_position(position)
    if clean is None:
        return False
    _state['panelPosition'] = clean
    return save(logger)


def _sanitize_position(position):
    if not isinstance(position, dict):
        return None
    clean = {}
    for key in _POSITION_FIELDS:
        try:
            clean[key] = int(round(float(position[key])))
        except (KeyError, TypeError, ValueError):
            return None
    if clean['parentWidth'] <= 0 or clean['parentHeight'] <= 0:
        return None
    return clean


def sanitize(values):
    """Keep only the known keys, each in its valid form. Anything else is dropped."""
    clean = {}
    for key in _FLAGS:
        if key in values:
            clean[key] = bool(values[key])
    for key, names in _CHOICES:
        if key in values and values[key] in names:
            clean[key] = values[key]
    if 'panelPosition' in values:
        # None, or anything that is not a valid position, puts the panel back in its default place.
        clean['panelPosition'] = _sanitize_position(values['panelPosition'])
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
    values = dict((key, bool(state[key])) for key in _FLAGS)
    for key, names in _CHOICES:
        values[key] = names.index(state[key]) if state[key] in names else 0
    return values


def from_menu(settings):
    """The config form of what the menu sent. Keys the menu did not send stay out."""
    changes = dict((key, bool(settings[key])) for key in _FLAGS if key in settings)
    for key, names in _CHOICES:
        if key in settings:
            try:
                changes[key] = names[int(settings[key])]
            except (TypeError, ValueError, IndexError):
                pass
    return changes


def menu_template():
    # Built from the defaults, never from the current values: the per-mod Reset of the menu
    # restores what the template says.
    values = menu_values(DEFAULTS)
    # The garage in the left column, the battle in the right one, each under its own switch.
    return {
        'modDisplayName': MOD_NAME,
        'modAuthor': MOD_AUTHOR,
        'modVersion': MOD_VERSION,
        'modUrl': MOD_URL,
        'enabled': values['enabled'],
        'column1': [
            {
                'type': 'CheckBox',
                'text': _loc('SETTING_GARAGE'),
                'tooltip': _loc_tooltip('SETTING_GARAGE', 'TOOLTIP_GARAGE_BODY'),
                'value': values['garageEnabled'],
                'varName': 'garageEnabled',
            },
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
        'column2': [
            {
                'type': 'CheckBox',
                'text': _loc('SETTING_BATTLE'),
                'tooltip': _loc_tooltip('SETTING_BATTLE', 'TOOLTIP_BATTLE_BODY'),
                'value': values['battleEnabled'],
                'varName': 'battleEnabled',
            },
            {
                'type': 'RadioButtonGroup',
                'text': _loc('SETTING_PANEL_DETAILS'),
                'tooltip': _loc_tooltip('SETTING_PANEL_DETAILS', 'TOOLTIP_PANEL_DETAILS_BODY'),
                'options': [{'label': get_wg_text(key, default)} for key, default in _DETAILS_LABELS],
                'value': values['panelDetails'],
                'varName': 'panelDetails',
            },
            {
                'type': 'RadioButtonGroup',
                'text': _loc('SETTING_PANEL_STYLE'),
                'tooltip': _loc_tooltip('SETTING_PANEL_STYLE', 'TOOLTIP_PANEL_STYLE_BODY'),
                'options': [
                    {'label': _loc('SETTING_PANEL_STYLE_FLAT')},
                    {'label': _loc('SETTING_PANEL_STYLE_ROUND')},
                ],
                'value': values['panelStyle'],
                'varName': 'panelStyle',
            },
            {
                'type': 'RadioButtonGroup',
                'text': _loc('SETTING_PANEL_FIGURES'),
                'tooltip': _loc_tooltip('SETTING_PANEL_FIGURES', 'TOOLTIP_PANEL_FIGURES_BODY'),
                'options': [
                    {'label': _loc('SETTING_PANEL_FIGURES_BOTH')},
                    {'label': _loc('SETTING_PANEL_FIGURES_VALUE')},
                ],
                'value': values['panelFigures'],
                'varName': 'panelFigures',
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
