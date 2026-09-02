"""Stable constants for the research progress bar mod."""
from __future__ import print_function, unicode_literals

from gui.Scaleform.daapi.settings.views import VIEW_ALIAS

# MOD_ID / MOD_NAME come from meta.xml via the build-generated _mod_meta module
# (see tools/build.py). meta.xml is the single authored source of these values.
from ._mod_meta import MOD_ID, MOD_NAME  # noqa: F401

MOD_CONFIG_DIR_NAME = 'research-progress-bar'
SCALEFORM_VIEW_ALIAS = 'ResearchProgressBarLobby'
SCALEFORM_FILE_NAME = 'research-progress-bar-lobby.swf'
# The tooltip is a view of its own so it can hold its own window band. A band applies to a whole
# view, not to an element inside it, and the bar and its tooltip want different ones: the bar low
# enough for other mods' widgets to cover it, the tooltip above the native windows.
TOOLTIP_VIEW_ALIAS = 'ResearchProgressBarTooltip'
TOOLTIP_FILE_NAME = 'research-progress-bar-tooltip.swf'

# Marker click action kinds, shared between the Scaleform marker payload
# (scaleform/modes.py) and the write-side dispatcher (actions.py).
MARKER_CLICK_ACTION_RESEARCH = 'research'
MARKER_CLICK_ACTION_FIELD_MOD = 'field_mod'
MARKER_CLICK_ACTION_FIELD_MOD_TOGGLE = 'field_mod_toggle'
MARKER_CLICK_ACTION_FIELD_MOD_PICK = 'field_mod_pick'
MARKER_CLICK_ACTION_FIELD_MOD_SELECT = 'field_mod_select'
MARKER_CLICK_ACTION_UPGRADES = 'upgrades'
_VISIBILITY_PROBE_DELAY = 0.25
_VISIBLE_ROUTE_PREFIX = 'Visible route changed to: '
_NAVIGATING_ROUTE_PREFIX = 'Navigating to '

_HANGAR_VIEW_ALIASES = frozenset((VIEW_ALIAS.LOBBY_HANGAR, VIEW_ALIAS.LEGACY_LOBBY_HANGAR))

_TIER_FIELD_MOD_RULES = {
    6: {'max_level': 5, 'xp_per_level': 3500},
    7: {'max_level': 5, 'xp_per_level': 7000},
    8: {'max_level': 6, 'xp_per_level': 11500},
    9: {'max_level': 7, 'xp_per_level': 20000},
    10: {'max_level': 8, 'xp_per_level': 28000},
}

_UNLOCK_MARKER_TYPE_BY_GUI_NAME = {
    'vehicleGun': 'gun',
    'vehicleTurret': 'turret',
    'vehicleEngine': 'engine',
    'vehicleChassis': 'suspension',
    'vehicleRadio': 'radio',
    'vehicle': 'vehicle',
}
