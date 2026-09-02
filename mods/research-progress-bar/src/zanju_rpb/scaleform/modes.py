"""Scaleform payload builders for the research progress bar."""
from __future__ import print_function, unicode_literals

import re

from ..constants import (
    MARKER_CLICK_ACTION_FIELD_MOD,
    MARKER_CLICK_ACTION_FIELD_MOD_PICK,
    MARKER_CLICK_ACTION_FIELD_MOD_SELECT,
    MARKER_CLICK_ACTION_FIELD_MOD_TOGGLE,
    MARKER_CLICK_ACTION_RESEARCH,
    MARKER_CLICK_ACTION_UPGRADES,
)
from ..localization import get_text as _loc, get_wg_text as _wg_loc


MODE_REGULAR_RESEARCH = 'regular_research'
MODE_TIER11_UPGRADES = 'tier11_upgrades'
MODE_FIELD_MODS = 'field_mods'
MODE_ELITE_PROGRESSION = 'elite_progression'

FIELD_MODS_MODE_ALWAYS = 'always'
FIELD_MODS_MODE_UNTIL_COMPLETE = 'until_complete'
FIELD_MODS_MODE_OFF = 'off'

FIELD_MOD_DUAL_BUFF_HTML_COLOR = '#80D43A'
FIELD_MOD_DUAL_DEBUFF_HTML_COLOR = '#D95C56'
# Blue used for clickable/keyboard hint text in tooltips (matches the AS3
# TOOLTIP_CLICK_HINT_TEXT_COLOR).
FIELD_MOD_CLICK_HINT_HTML_COLOR = '#5FB2F2'
FIELD_MOD_MARKER_HIGHLIGHT_HTML_COLOR = '#F0CF74'
FIELD_MOD_MARKER_MUTED_HTML_COLOR = '#B8AC97'
FIELD_MOD_BAR_ICON_CATEGORIES = frozenset((
    'firepower',
    'survivability',
    'mobility',
    'stealth',
    'reconnaissance',
    'scouting',
))
FIELD_MOD_ROLE_SLOT_OPTION_CATEGORIES = (
    'firepower',
    'survivability',
    'mobility',
    'scouting',
)

ELITE_MODE_ON = 'on'
ELITE_MODE_CUSTOMIZATION_ONLY = 'customization_only'
ELITE_MODE_OFF = 'off'

ELITE_MAX_LEVEL = 350
ELITE_LEVEL_XP_SEGMENTS = (
    (1, 5, 1000),
    (5, 20, 1500),
    (20, 150, 2500),
    (150, 250, 3000),
    (250, ELITE_MAX_LEVEL, 4000),
)
ELITE_COLOR_MARKERS = (
    ('metal', 'ELITE_BADGE_METAL', 1),
    ('bronze', 'ELITE_BADGE_BRONZE', 20),
    ('silver', 'ELITE_BADGE_SILVER', 70),
    ('gold', 'ELITE_BADGE_GOLD', 150),
    ('red_gold', 'ELITE_BADGE_RED_GOLD', 250),
    ('prestige_elite', 'ELITE_BADGE_PRESTIGE', ELITE_MAX_LEVEL),
)
ELITE_T11_COSMETIC_MARKERS = (
    ('stat_tracker', 'ELITE_REWARD_STAT_TRACKER', 35),
    ('volumetric_style', 'ELITE_REWARD_VOLUMETRIC_STYLE', 75),
    ('gun_sleeve', 'ELITE_REWARD_GUN_SLEEVE', 155),
)

T11_CATEGORY_SORT_ORDER = {
    'firepower': 0,
    'survivability': 1,
    'scouting': 2,
    'mobility': 3,
    'special': 4,
    'mechanics': 5,
}

_T11_DESCRIPTION_TAG_TOKEN_RE = re.compile(
    r'%\((\w*?)(?:_?(Open|Start|Close|End))\)s|{(\w*?)(?:_?(Open|Start|Close|End))}'
)
_T11_DESCRIPTION_PLACEHOLDER_RE = re.compile(r'%\(([^)]+)\)s|{([^{}]+)}')
_T11_DESCRIPTION_TAG_COLORS = {
    'colorTag': '#EDE6D9',
}
_T11_DESCRIPTION_DEFAULT_TAG_COLOR = '#EDE6D9'


def build_scaleform_view_payload(vehicle, data, mode_preferences=None, preferred_mode_id=None):
    """Builds the full Scaleform payload, including empty-mode UI states."""
    preferences = _normalize_mode_preferences(mode_preferences)
    show_total_xp = preferences['showTotalXp']
    click_to_research = preferences['clickToResearch']
    modes = []

    if preferences['showResearch']:
        research_mode = _build_regular_research_mode(data, show_total_xp, click_to_research)
        if research_mode is not None:
            modes.append(research_mode)

    if preferences['showUpgrades']:
        tier11_mode = _build_tier11_mode(data, show_total_xp, click_to_research)
        if tier11_mode is not None:
            modes.append(tier11_mode)

    field_mods_mode = _build_field_mods_mode(
        data, preferences['fieldModsMode'], show_total_xp, click_to_research
    )
    if field_mods_mode is not None:
        modes.append(field_mods_mode)

    elite_mode = _build_elite_mode(data, preferences['eliteMode'])
    if elite_mode is not None:
        modes.append(elite_mode)

    if not show_total_xp:
        # Without the Total XP calculation the tooltip's Total XP row would just repeat
        # the Vehicle XP row, so every marker collapses to the single-row layout.
        for mode in modes:
            for marker in mode.get('markers') or []:
                marker['singleProgressRow'] = True

    _stamp_tooltip_indices(modes)
    selected_mode_id = _resolve_selected_mode_id(modes, preferred_mode_id) if modes else None
    return {
        'vehicleLabel': _build_vehicle_label(vehicle, data),
        'vehicleIntCD': getattr(vehicle, 'intCD', None),
        'selectedModeId': selected_mode_id,
        'separateStatusText': _build_separate_status_text(data, selected_mode_id, preferences),
        'modes': modes,
    }


def _resolve_selected_mode_id(modes, preferred_mode_id):
    normalized_preferred_mode_id = _normalize_selected_mode_id(preferred_mode_id)
    if normalized_preferred_mode_id is not None:
        for mode in modes:
            if _normalize_selected_mode_id(mode.get('id')) == normalized_preferred_mode_id:
                return normalized_preferred_mode_id

    return _normalize_selected_mode_id(modes[0].get('id'))


def _normalize_selected_mode_id(value):
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None
    return text


def _normalize_mode_preferences(mode_preferences):
    preferences = dict(mode_preferences or {})
    field_mods_mode = preferences.get('fieldModsMode') or FIELD_MODS_MODE_ALWAYS
    if field_mods_mode not in (
            FIELD_MODS_MODE_ALWAYS,
            FIELD_MODS_MODE_UNTIL_COMPLETE,
            FIELD_MODS_MODE_OFF):
        field_mods_mode = FIELD_MODS_MODE_ALWAYS
    elite_mode = preferences.get('eliteMode') or ELITE_MODE_ON
    if elite_mode not in (ELITE_MODE_ON, ELITE_MODE_CUSTOMIZATION_ONLY, ELITE_MODE_OFF):
        elite_mode = ELITE_MODE_ON

    return {
        'clickToResearch': bool(preferences.get('clickToResearch', True)),
        'showTotalXp': bool(preferences.get('showTotalXp', True)),
        'showResearchReminder': bool(preferences.get('showResearchReminder', True)),
        'showAcceleratedCrewTrainingReminder': bool(
            preferences.get('showAcceleratedCrewTrainingReminder', True)
        ),
        'showResearch': bool(preferences.get('showResearch', True)),
        'showUpgrades': bool(preferences.get('showUpgrades', True)),
        'fieldModsMode': field_mods_mode,
        'eliteMode': elite_mode,
    }


def _build_vehicle_label(vehicle, data):
    name = getattr(vehicle, 'userName', str(vehicle.intCD))
    tier = (data.get('vehicle') or {}).get('tier')
    if tier is None:
        return _loc('VEHICLE_LABEL_TIER_UNKNOWN_FORMAT', name=name)
    return _loc('VEHICLE_LABEL_TIER_FORMAT', name=name, tier=tier)


def _build_separate_status_text(data, selected_mode_id, preferences):
    if preferences.get('showResearchReminder', True) and _should_show_research_now_text(data, selected_mode_id):
        return _loc('SEPARATE_STATUS_RESEARCH_NOW')

    if (preferences.get('showAcceleratedCrewTrainingReminder', True)
            and _should_show_accelerate_crew_training_text(data)):
        return _loc('SEPARATE_STATUS_ACCELERATE_CREW_TRAINING')

    return ''


def _is_hypothetical_research_unlock(unlock):
    return bool((unlock or {}).get('is_hypothetical_t11'))


def _filter_real_research_unlocks(unlocks):
    return [unlock for unlock in (unlocks or []) if not _is_hypothetical_research_unlock(unlock)]


def _filter_hypothetical_research_unlocks(unlocks):
    return [unlock for unlock in (unlocks or []) if _is_hypothetical_research_unlock(unlock)]


def _resolve_hypothetical_research_unlock_cost(tech_tree):
    visible_unlocks = (tech_tree or {}).get('visible_unlocks') or []
    hypothetical_unlocks = _filter_hypothetical_research_unlocks(visible_unlocks)
    if not hypothetical_unlocks:
        return None

    costs = []
    unlock = None
    for unlock in hypothetical_unlocks:
        xp_cost = _to_int((unlock or {}).get('xp_cost'))
        if xp_cost is not None and xp_cost > 0:
            costs.append(xp_cost)

    if not costs:
        return None
    return max(costs)


def _should_show_accelerate_crew_training_text(data):
    crew_training = (data or {}).get('accelerate_crew_training') or {}
    tech_tree = (data or {}).get('tech_tree') or {}
    real_visible_unlocks = _filter_real_research_unlocks(tech_tree.get('visible_unlocks') or [])
    hypothetical_unlock_cost = _resolve_hypothetical_research_unlock_cost(tech_tree)
    vehicle_xp = max(0, _to_int(tech_tree.get('vehicle_xp')) or 0)

    if not crew_training.get('available'):
        return False
    if crew_training.get('enabled') is not False:
        return False
    if real_visible_unlocks:
        return False
    if hypothetical_unlock_cost is not None and vehicle_xp < hypothetical_unlock_cost:
        return False
    if hypothetical_unlock_cost is None and _build_regular_research_mode(data) is not None:
        return False
    if _build_field_mods_mode(data, FIELD_MODS_MODE_UNTIL_COMPLETE) is not None:
        return False
    if _build_tier11_mode(data) is not None:
        return False
    return True


def _should_show_research_now_text(data, selected_mode_id):
    normalized_mode_id = _normalize_selected_mode_id(selected_mode_id)
    tech_tree = (data or {}).get('tech_tree') or {}
    vehicle_xp = max(0, _to_int(tech_tree.get('vehicle_xp')) or 0)

    if normalized_mode_id == MODE_REGULAR_RESEARCH:
        return _is_regular_research_ready_now(tech_tree, vehicle_xp)
    if normalized_mode_id == MODE_FIELD_MODS:
        return _is_field_mods_ready_now(data, vehicle_xp)
    if normalized_mode_id == MODE_TIER11_UPGRADES:
        return _is_tier11_research_ready_now(data, vehicle_xp)
    return False


def _is_regular_research_ready_now(tech_tree, vehicle_xp):
    available_unlocks = _filter_real_research_unlocks((tech_tree or {}).get('available_unlocks') or [])
    if not available_unlocks:
        return False

    unlock = None
    for unlock in available_unlocks:
        xp_cost = _to_int((unlock or {}).get('xp_cost'))
        if xp_cost is None or xp_cost > vehicle_xp:
            return False
    return True


def _resolve_field_mods_next_vehicle_xp_cost(data):
    field_mods = (data or {}).get('field_mods') or {}
    tier_plan = field_mods.get('tier_plan') or {}

    next_level_xp_cost = _to_int(tier_plan.get('next_level_xp_cost'))
    if next_level_xp_cost is not None and next_level_xp_cost > 0:
        return next_level_xp_cost

    next_step_xp_cost = _to_int(field_mods.get('next_purchasable_step_xp'))
    if next_step_xp_cost is not None and next_step_xp_cost > 0:
        return next_step_xp_cost

    return None


def _is_field_mods_ready_now(data, vehicle_xp):
    next_cost = _resolve_field_mods_next_vehicle_xp_cost(data)
    return next_cost is not None and next_cost <= vehicle_xp


def _is_tier11_research_ready_now(data, vehicle_xp):
    field_mods = (data or {}).get('field_mods') or {}
    tech_tree = (data or {}).get('tech_tree') or {}
    if not _is_tier11_mode_enabled(field_mods, tech_tree):
        return False

    display_layout = _build_t11_display_layout(field_mods)
    placeholder_costs = []
    if display_layout.get('remaining_minor_count'):
        placeholder_costs.append(10000)
    if display_layout.get('remaining_major_count'):
        placeholder_costs.append(20000)

    if placeholder_costs:
        return all(cost <= vehicle_xp for cost in placeholder_costs)

    if display_layout.get('remaining_final_count'):
        return 25000 <= vehicle_xp

    next_step_xp_cost = _to_int(field_mods.get('next_purchasable_step_xp'))
    return next_step_xp_cost is not None and next_step_xp_cost > 0 and next_step_xp_cost <= vehicle_xp


def _build_regular_research_mode(data, show_total_xp=True, click_to_research=True):
    tech_tree = data.get('tech_tree') or {}
    visible_unlocks = tech_tree.get('visible_unlocks') or []
    available_unlocks = tech_tree.get('available_unlocks') or []
    locked_unlock_count = _to_int(tech_tree.get('locked_unlock_count')) or 0

    if not visible_unlocks:
        return None

    max_requirement_xp = max([1] + [int(item['xp_cost']) for item in visible_unlocks])
    vehicle_xp = min(_to_int(tech_tree.get('vehicle_xp')) or 0, max_requirement_xp)
    free_xp = min(
        _to_int(tech_tree.get('free_xp')) or 0,
        max(0, max_requirement_xp - vehicle_xp),
    )
    if not show_total_xp:
        free_xp = 0

    if locked_unlock_count > 0 and not available_unlocks:
        right_caption = _loc('CAPTION_LOCKED')
        right_text = str(locked_unlock_count)
    elif show_total_xp:
        right_caption = _loc('CAPTION_TOTAL_XP')
        right_text = _format_percent(vehicle_xp + free_xp, max_requirement_xp)
    else:
        right_caption = ''
        right_text = ''

    return _make_mode(
        MODE_REGULAR_RESEARCH,
        _loc('MODE_RESEARCH'),
        max_requirement_xp,
        vehicle_xp,
        free_xp,
        _format_percent(vehicle_xp, max_requirement_xp),
        _loc('CAPTION_VEHICLE_XP'),
        right_text,
        right_caption,
        markers=[_build_research_marker(item, click_to_research) for item in visible_unlocks],
    )


def _build_field_mods_mode(data, field_mods_mode=FIELD_MODS_MODE_ALWAYS, show_total_xp=True, click_to_research=True):
    field_mods = data.get('field_mods') or {}
    tier_plan = field_mods.get('tier_plan') or {}
    tech_tree = data.get('tech_tree') or {}

    if not _is_field_mods_mode_enabled(field_mods, tier_plan, tech_tree, field_mods_mode):
        return None

    max_level = _to_int(tier_plan.get('max_level')) or _to_int(field_mods.get('unique_level_count')) or 0
    current_level = _to_int(tier_plan.get('current_level'))
    if current_level is None:
        current_level = _to_int(field_mods.get('unique_unlocked_level_count')) or 0
    current_level = max(0, min(current_level, max_level))

    next_level = _to_int(tier_plan.get('next_level'))
    next_level_xp_cost = _to_int(tier_plan.get('next_level_xp_cost'))
    if next_level_xp_cost is None:
        next_level_xp_cost = _to_int(field_mods.get('next_purchasable_step_xp'))
    xp_per_level = _to_int(tier_plan.get('xp_per_level'))

    vehicle_xp = _to_int(tech_tree.get('vehicle_xp')) or 0
    free_xp = _to_int(tech_tree.get('free_xp')) or 0
    total_xp = _to_int(tech_tree.get('total_xp'))
    if total_xp is None:
        total_xp = vehicle_xp + free_xp
    if not show_total_xp:
        free_xp = 0
        total_xp = vehicle_xp

    remaining_levels = range(current_level + 1, max_level + 1)

    if next_level is None or current_level >= max_level:
        left_text = '100%'
        left_caption = _loc('CAPTION_VEHICLE_XP')
        right_text = '100%'
        right_caption = _loc('CAPTION_TOTAL_XP')
        if xp_per_level is not None and xp_per_level > 0 and max_level > 0:
            total_cost = xp_per_level * max_level
            primary_value = 0.0
            secondary_value = 0.0
            completed_value = total_cost
            bar_max_value = total_cost
            markers = _build_field_mod_markers(
                current_level,
                max_level,
                xp_per_level,
                0,
                0,
                field_mods,
                click_to_research,
            )
        else:
            primary_value = 0.0
            secondary_value = 0.0
            completed_value = float(max_level)
            bar_max_value = max_level
            markers = []
    elif xp_per_level is not None and xp_per_level > 0 and remaining_levels:
        total_cost = xp_per_level * max_level
        completed_total_cost = xp_per_level * current_level
        remaining_total_cost = xp_per_level * len(remaining_levels)
        primary_value = min(vehicle_xp, remaining_total_cost)
        secondary_value = min(free_xp, max(0, remaining_total_cost - primary_value))
        completed_value = completed_total_cost
        left_text = _format_percent(completed_total_cost + vehicle_xp, total_cost)
        left_caption = _loc('CAPTION_VEHICLE_XP')
        right_text = _format_percent(completed_total_cost + total_xp, total_cost)
        right_caption = _loc('CAPTION_TOTAL_XP')
        bar_max_value = total_cost
        markers = _build_field_mod_markers(
            current_level,
            max_level,
            xp_per_level,
            vehicle_xp,
            total_xp,
            field_mods,
            click_to_research,
        )
    else:
        primary_value, secondary_value = _build_fractional_fill(
            current_level,
            max_level,
            next_level_xp_cost,
            vehicle_xp,
            total_xp,
        )
        completed_value = 0.0
        left_text = _format_percent(vehicle_xp, next_level_xp_cost)
        left_caption = _loc('CAPTION_VEHICLE_XP')
        right_text = _format_percent(total_xp, next_level_xp_cost)
        right_caption = _loc('CAPTION_TOTAL_XP')
        bar_max_value = max_level
        markers = []

    if not show_total_xp:
        right_text = ''
        right_caption = ''

    return _make_mode(
        MODE_FIELD_MODS,
        _loc('MODE_FIELD_MODS'),
        bar_max_value,
        primary_value,
        secondary_value,
        left_text,
        left_caption,
        right_text,
        right_caption,
        markers=markers,
        completed_value=completed_value,
    )


def _build_tier11_mode(data, show_total_xp=True, click_to_research=True):
    field_mods = data.get('field_mods') or {}
    tech_tree = data.get('tech_tree') or {}
    if not _is_tier11_mode_enabled(field_mods, tech_tree):
        return None

    total_steps = _to_int(field_mods.get('total_steps')) or 0
    unlocked_steps = _to_int(field_mods.get('unlocked_steps')) or 0
    unlocked_steps = max(0, min(unlocked_steps, total_steps))

    next_step_xp_cost = _to_int(field_mods.get('next_purchasable_step_xp'))
    vehicle_xp = _to_int(tech_tree.get('vehicle_xp')) or 0
    free_xp = _to_int(tech_tree.get('free_xp')) or 0
    total_xp = _to_int(tech_tree.get('total_xp'))
    if total_xp is None:
        total_xp = vehicle_xp + free_xp
    if not show_total_xp:
        free_xp = 0
        total_xp = vehicle_xp

    display_layout = _build_t11_display_layout(field_mods)
    total_cost = display_layout['total_cost']

    if total_cost > 0:
        remaining_cost = display_layout['remaining_cost']
        if remaining_cost <= 0:
            return None
        primary_value = min(vehicle_xp, remaining_cost)
        secondary_value = min(free_xp, max(0, remaining_cost - primary_value))
        completed_value = display_layout['completed_cost']
        left_text = _format_percent(completed_value + vehicle_xp, total_cost)
        left_caption = _loc('CAPTION_VEHICLE_XP')
        right_text = _format_percent(completed_value + total_xp, total_cost)
        right_caption = _loc('CAPTION_TOTAL_XP')
        bar_max_value = total_cost
        markers = _build_t11_markers(
            display_layout,
            vehicle_xp,
            total_xp,
            click_to_research,
        )
    elif next_step_xp_cost:
        primary_value, secondary_value = _build_fractional_fill(
            unlocked_steps,
            total_steps,
            next_step_xp_cost,
            vehicle_xp,
            total_xp,
        )
        completed_value = 0.0
        left_text = _format_percent(vehicle_xp, next_step_xp_cost)
        left_caption = _loc('CAPTION_VEHICLE_XP')
        right_text = _format_percent(total_xp, next_step_xp_cost)
        right_caption = _loc('CAPTION_TOTAL_XP')
        bar_max_value = total_steps
        markers = []
    else:
        primary_value = float(unlocked_steps)
        secondary_value = 0.0
        completed_value = 0.0
        left_text = '0%'
        left_caption = _loc('CAPTION_VEHICLE_XP')
        right_text = _format_percent(unlocked_steps, total_steps)
        right_caption = _loc('CAPTION_TOTAL_XP')
        bar_max_value = total_steps
        markers = []

    if not show_total_xp:
        right_text = ''
        right_caption = ''

    return _make_mode(
        MODE_TIER11_UPGRADES,
        _loc('MODE_UPGRADES'),
        bar_max_value,
        primary_value,
        secondary_value,
        left_text,
        left_caption,
        right_text,
        right_caption,
        markers=markers,
        completed_value=completed_value,
        side_counter_text='{0}/{1}'.format(unlocked_steps, total_steps),
        side_counter_caption=_loc('CAPTION_UNLOCKED'),
    )


def _build_elite_mode(data, elite_mode=ELITE_MODE_ON):
    if elite_mode == ELITE_MODE_OFF:
        return None

    tech_tree = dict(data.get('tech_tree') or {})
    field_mods = data.get('field_mods') or {}
    vehicle_data = data.get('vehicle') or {}
    tech_tree['vehicle_tier'] = vehicle_data.get('tier')
    elite_progression = data.get('elite_progression') or {}
    if not _is_elite_progression_mode_enabled(tech_tree, elite_progression):
        return None

    include_t11_cosmetics = _is_tier11_mode_enabled(field_mods, tech_tree)
    if elite_mode == ELITE_MODE_CUSTOMIZATION_ONLY and not include_t11_cosmetics:
        return None

    progress_cap = _elite_total_required_xp()
    if elite_mode == ELITE_MODE_CUSTOMIZATION_ONLY:
        progress_cap = _elite_customization_total_required_xp()

    current_level = _to_int(elite_progression.get('current_level'))
    if current_level is None:
        return None

    current_level = max(1, min(current_level, ELITE_MAX_LEVEL))
    current_xp_value = _to_int(elite_progression.get('current_xp'))
    current_xp = max(0, current_xp_value or 0)
    next_level_xp = _to_int(elite_progression.get('next_level_xp'))
    remaining_xp = _to_int(elite_progression.get('remaining_xp'))
    if current_level >= ELITE_MAX_LEVEL:
        total_progress = _elite_total_required_xp()
        current_xp = _elite_required_xp_for_level(ELITE_MAX_LEVEL - 1)
        next_level_xp = current_xp
    else:
        if next_level_xp is None or next_level_xp <= 0:
            next_level_xp = _elite_required_xp_for_level(current_level)
        if current_xp_value is None and remaining_xp is not None and next_level_xp > 0:
            current_xp = min(remaining_xp, next_level_xp)
        current_xp = min(current_xp, next_level_xp)
        total_progress = min(
            _elite_total_required_xp(),
            _elite_cumulative_xp_to_level(current_level) + current_xp,
        )
    total_progress = min(progress_cap, total_progress)

    return _make_mode(
        MODE_ELITE_PROGRESSION,
        _loc('MODE_ELITE'),
        progress_cap,
        0.0,
        0.0,
        _loc('ELITE_LEVEL_FORMAT', level=current_level),
        _loc('ELITE_BASE_XP_PROGRESS_FORMAT', current=current_xp, target=next_level_xp),
        _format_percent(total_progress, progress_cap),
        _loc('CAPTION_BASE_XP'),
        markers=_build_elite_markers(
            total_progress,
            include_badges=(elite_mode == ELITE_MODE_ON),
            include_t11_cosmetics=include_t11_cosmetics,
        ),
        completed_value=total_progress,
        counter_layout='elite_status',
        bar_fill_mode='completed_only',
    )


def _build_elite_markers(current_total_xp, include_badges=True, include_t11_cosmetics=False):
    markers = []
    if include_badges:
        for marker_key, marker_label_key, level in ELITE_COLOR_MARKERS:
            if level <= 1:
                continue
            position_value = _elite_cumulative_xp_to_level(level)
            if level >= ELITE_MAX_LEVEL:
                position_value = _elite_total_required_xp()
            marker_name = _loc(marker_label_key)
            markers.append({
                'id': 'elite_{0}'.format(marker_key),
                'positionValue': position_value,
                'costXp': position_value,
                'itemType': 'unknown',
                'name': marker_name,
                'level': level,
                'tooltipTitle': _build_level_tooltip_title(level),
                'tooltipSubtitle': marker_name,
                'label': '',
                'iconCacheKey': 'elite:{0}'.format(marker_key),
                'hideTooltipIcon': False,
                'hideBarIcon': False,
                'markerState': 'completed' if position_value <= current_total_xp else 'locked',
                'singleProgressRow': True,
                'progressLabel': _loc('CAPTION_BASE_XP'),
                'progressReadyText': _loc('STATUS_READY_FOR_RESEARCH'),
                'progressXpLeftFormat': _loc('STATUS_XP_LEFT_FORMAT'),
                'completedLabel': _loc('CAPTION_UNLOCKED'),
                'isAvailable': True,
            })

    if include_t11_cosmetics:
        for marker_key, marker_label_key, level in ELITE_T11_COSMETIC_MARKERS:
            position_value = _elite_cumulative_xp_to_level(level)
            marker_name = _loc(marker_label_key)
            markers.append({
                'id': 'elite_t11_{0}'.format(marker_key),
                'positionValue': position_value,
                'costXp': position_value,
                'itemType': 'unknown',
                'name': marker_name,
                'level': level,
                'tooltipTitle': _build_level_tooltip_title(level),
                'tooltipSubtitle': marker_name,
                'label': '',
                'iconCacheKey': 'elite:t11_cosmetic',
                'hideTooltipIcon': False,
                'hideBarIcon': False,
                'markerState': 'completed' if position_value <= current_total_xp else 'locked',
                'singleProgressRow': True,
                'progressLabel': _loc('CAPTION_BASE_XP'),
                'progressReadyText': _loc('STATUS_READY_FOR_RESEARCH'),
                'progressXpLeftFormat': _loc('STATUS_XP_LEFT_FORMAT'),
                'completedLabel': _loc('CAPTION_UNLOCKED'),
                'isAvailable': True,
            })
    return markers


def _elite_total_required_xp():
    return _elite_cumulative_xp_to_level(ELITE_MAX_LEVEL)


def _elite_customization_total_required_xp():
    max_marker_level = max([level for _, _, level in ELITE_T11_COSMETIC_MARKERS] or [ELITE_MAX_LEVEL])
    return _elite_cumulative_xp_to_level(max_marker_level)


def _elite_required_xp_for_level(level):
    current_level = _to_int(level) or 0
    if current_level >= ELITE_MAX_LEVEL:
        return 0

    for start_level, next_level, xp_required in ELITE_LEVEL_XP_SEGMENTS:
        if current_level >= start_level and current_level < next_level:
            return xp_required

    return 0


def _elite_cumulative_xp_to_level(level):
    target_level = _to_int(level) or 0
    if target_level <= 1:
        return 0
    if target_level > ELITE_MAX_LEVEL:
        target_level = ELITE_MAX_LEVEL

    total_xp = 0
    for start_level, next_level, xp_required in ELITE_LEVEL_XP_SEGMENTS:
        if target_level <= start_level:
            break
        total_xp += max(0, min(target_level, next_level) - start_level) * xp_required
    return total_xp


def _build_research_marker(item, click_to_research=True):
    blueprint_count = item.get('blueprint_count')
    blueprint_total = item.get('blueprint_total')
    blueprint_discount_percent = item.get('blueprint_discount_percent')
    marker_name = item.get('name')
    if item.get('is_hypothetical_t11'):
        marker_name = _loc('HYPOTHETICAL_T11_VEHICLE_NAME')

    marker = {
        'id': 'unlock_{0}'.format(item['intcd']),
        'positionValue': item['xp_cost'],
        'costXp': item['xp_cost'],
        'itemType': item['item_type'],
        'progressLabel': _loc('CAPTION_VEHICLE_XP'),
        'totalProgressLabel': _loc('CAPTION_TOTAL_XP'),
        'progressReadyText': _loc('STATUS_READY_FOR_RESEARCH'),
        'progressXpLeftFormat': _loc('STATUS_XP_LEFT_FORMAT'),
        'isAvailable': item.get('is_available', True),
        'isHypotheticalT11': bool(item.get('is_hypothetical_t11')),
        'missingPrereqNames': item.get('missing_prereq_names', []),
        'missingPrereqs': item.get('missing_prereqs', []),
        'prerequisitesLabel': _loc('TOOLTIP_PREREQUISITES'),
        'costWithPrereqsXp': item.get('cost_with_prereqs_xp'),
        'costWithPrereqsLabel': _loc('TOOLTIP_COST_WITH_PREREQS'),
        'name': marker_name,
        'blueprintCount': blueprint_count,
        'blueprintTotal': blueprint_total,
        'blueprintDiscountPercent': blueprint_discount_percent,
        'blueprintTooltipText': _build_blueprint_tooltip_text(
            blueprint_count,
            blueprint_total,
            blueprint_discount_percent,
        ),
    }

    # Hypothetical tier 11 vehicles do not exist, so there is nothing to research.
    # Prerequisite-blocked items keep no click action either: WG's unlock flow only
    # accepts currently researchable unlocks. The view still gates on the displayed
    # XP readiness before enabling the click. Gated by the "Click to research or
    # purchase" setting.
    if click_to_research and item.get('is_available', True) and not item.get('is_hypothetical_t11'):
        marker['clickAction'] = {
            'kind': MARKER_CLICK_ACTION_RESEARCH,
            'id': item['intcd'],
        }
        # Modules are followed by the game's buy-and-mount popup once research lands,
        # so their hint says "research and purchase"; vehicles are only researched.
        is_module = bool(item.get('is_module'))
        marker['clickHintText'] = _loc(
            'TOOLTIP_CLICK_TO_RESEARCH_AND_PURCHASE' if is_module else 'TOOLTIP_CLICK_TO_RESEARCH'
        )
        # Research items with near-equal XP costs overlap on the bar and stack in one
        # tooltip, where a single click can only ever hit the topmost -- ambiguous.
        # The view numbers such a stack and lets the player press the matching key;
        # this template (with a literal {key} the view fills in) is that per-item
        # hint. Only research markers carry it -- they are the cost-positioned ones
        # that overlap; field-mod/upgrade markers sit at fixed, separated slots.
        marker['keyHintText'] = _loc(
            'TOOLTIP_KEY_TO_RESEARCH_AND_PURCHASE' if is_module else 'TOOLTIP_KEY_TO_RESEARCH'
        )

    return marker


def _build_blueprint_tooltip_text(count, total, discount_percent):
    if count is None or total is None or discount_percent is None:
        return None

    return _loc('BLUEPRINT_TOOLTIP_FORMAT', count=count, total=total, discount=discount_percent)


def _build_field_mod_markers(current_level, max_level, xp_per_level, vehicle_xp, total_xp,
                             field_mods=None, click_to_research=True):
    markers = []
    cumulative_total_cost = 0
    level_details = (field_mods or {}).get('level_details') or {}

    for level in range(1, max_level + 1):
        cumulative_total_cost += xp_per_level
        remaining_cost = max(0, (level - current_level) * xp_per_level)
        roman_level = _to_roman(level)
        level_detail = level_details.get(level)
        marker_state = _resolve_field_mod_marker_state(
            level,
            current_level,
            remaining_cost,
            vehicle_xp,
            total_xp,
        )
        click_action = None
        click_hint_text = None
        show_inline_pick_hints = False
        if click_to_research:
            click_action, click_hint_text, show_inline_pick_hints = _resolve_field_mod_interactivity(
                level, current_level, level_detail, marker_state
            )
        # Inline "Press X to purchase." hints live inside the dual option sections;
        # flag the detail so the tooltip builders render them (under each option
        # title, above its stats).
        if level_detail is not None:
            level_detail['_show_pick_hints'] = show_inline_pick_hints
        completed_tooltip_html = _build_field_mod_completed_tooltip_html(level_detail)
        completed_tooltip_text = _build_field_mod_completed_tooltip_text(level_detail)
        pending_tooltip_html = _build_field_mod_pending_tooltip_html(level_detail)
        pending_tooltip_text = _build_field_mod_pending_tooltip_text(level_detail)
        pre_progress_tooltip_html = None
        pre_progress_tooltip_text = None
        detail_tooltip_html = None
        detail_tooltip_text = None
        if _is_field_mod_pre_progress_detail(level_detail):
            pre_progress_tooltip_html = pending_tooltip_html
            pre_progress_tooltip_text = pending_tooltip_text
        else:
            detail_tooltip_html = pending_tooltip_html
            detail_tooltip_text = pending_tooltip_text
        raw_tooltip_subtitle = (
            _build_field_mod_tooltip_subtitle(level_detail)
            if marker_state != 'completed'
            else None
        )
        marker = {
            'id': 'field_mod_{0}'.format(level),
            'positionValue': cumulative_total_cost,
            'costXp': xp_per_level if level <= current_level else remaining_cost,
            'itemType': 'unknown',
            'isAvailable': True,
            'name': _build_level_tooltip_title(roman_level),
            'tooltipTitle': _build_level_tooltip_title(roman_level),
            'tooltipSubtitle': _escape_html(raw_tooltip_subtitle) if raw_tooltip_subtitle else None,
            'label': roman_level,
            'showBarLabel': True,
            'hideTooltipIcon': True,
            'hideBarIcon': True,
            'completedTooltipHtml': completed_tooltip_html,
            'completedTooltipText': completed_tooltip_text,
            'preProgressTooltipHtml': pre_progress_tooltip_html,
            'preProgressTooltipText': pre_progress_tooltip_text,
            'detailTooltipHtml': detail_tooltip_html,
            'detailTooltipText': detail_tooltip_text,
            'markerState': marker_state,
            'progressLabel': _loc('CAPTION_VEHICLE_XP'),
            'totalProgressLabel': _loc('CAPTION_TOTAL_XP'),
            'progressReadyText': _loc('STATUS_READY_FOR_RESEARCH'),
            'progressXpLeftFormat': _loc('STATUS_XP_LEFT_FORMAT'),
        }
        marker.update(_build_field_mod_marker_display(level_detail, roman_level))
        if click_action is not None:
            marker['clickAction'] = click_action
        if click_hint_text is not None:
            marker['clickHintText'] = click_hint_text
        markers.append(marker)

    return markers


def _resolve_field_mod_interactivity(level, current_level, level_detail, marker_state):
    """Interactivity for a field-mod level marker, gated by click-to-research upstream.

    Returns ``(click_action, click_hint_text, show_inline_pick_hints)``:
      - not-yet-researched next level -> research it;
      - completed loadout-switch (feature) -> toggle it;
      - completed second-slot (role_slot) -> open WG's screen to select/reassign;
      - completed dual, unpicked -> keyboard pick (hints shown inline per option);
      - completed dual, picked -> click to change to the other modification.
    """
    if marker_state != 'completed':
        step_id = _resolve_field_mod_click_step_id(level, current_level, level_detail)
        if step_id is not None:
            action = {'kind': MARKER_CLICK_ACTION_FIELD_MOD, 'id': step_id}
            return action, _loc('TOOLTIP_CLICK_TO_RESEARCH'), False
        return None, None, False

    kind = level_detail.get('kind') if level_detail else None

    if kind == 'feature':
        group_id = _resolve_field_mod_toggle_group_id(level_detail)
        if group_id is not None:
            action = {'kind': MARKER_CLICK_ACTION_FIELD_MOD_TOGGLE, 'id': group_id}
            hint = _loc(
                'TOOLTIP_CLICK_TO_DISABLE' if level_detail.get('is_active') else 'TOOLTIP_CLICK_TO_ENABLE'
            )
            return action, hint, False
        return None, None, False

    if kind == 'role_slot':
        # The A/B category selection lives inside WG's own modal, so we can only
        # open that screen; available whether or not a category is already picked.
        action = {
            'kind': MARKER_CLICK_ACTION_FIELD_MOD_SELECT,
            'id': _to_int(level_detail.get('research_step_id')) or 0,
        }
        return action, _loc('TOOLTIP_CLICK_TO_SELECT'), False

    if kind == 'dual':
        selected = _resolve_field_mod_dual_selected_choice_index(level_detail)
        if selected is None:
            pick_action = _resolve_field_mod_pick_action(level_detail)
            if pick_action is not None:
                return pick_action, None, True
            return None, None, False
        change_action = _resolve_field_mod_change_action(level_detail, selected)
        if change_action is not None:
            return change_action, _loc('TOOLTIP_CLICK_TO_CHANGE_MODIFICATION'), False
        return None, None, False

    return None, None, False


def _resolve_field_mod_change_action(level_detail, selected_choice_index):
    """Click action that swaps a picked dual level to its other modification.

    WG's PURCHASE_POST_PROGRESSION_PAIR with the not-currently-picked modification
    id switches the choice (and shows its own confirm dialog). A single click is
    enough because there are only two options.
    """
    pair_step_id = _to_int(level_detail.get('pair_step_id'))
    other_index = 2 if selected_choice_index == 1 else 1
    other_mod_id = _resolve_field_mod_choice_modification_id(level_detail, other_index)
    if pair_step_id is None or other_mod_id is None:
        return None
    return {
        'kind': MARKER_CLICK_ACTION_FIELD_MOD_PICK,
        'id': pair_step_id,
        'extra': other_mod_id,
    }


def _resolve_field_mod_pick_action(level_detail):
    """Keyboard pick action for an unlocked dual level whose variant is unpicked.

    The level is researched (its marker is 'completed') but neither Option A nor B
    is chosen yet. Pressing 1 picks A (choice index 1), 2 picks B (index 2) -- WoT's
    hangar GFx delivers no usable right-click, so the choice is by key. leftId/rightId
    carry each option's modification id for WG's PURCHASE_POST_PROGRESSION_PAIR action
    (which confirms via its own dialog). Returns None if already picked or the pick
    ids are unavailable.
    """
    if not level_detail or level_detail.get('kind') != 'dual':
        return None
    if _resolve_field_mod_dual_selected_choice_index(level_detail) is not None:
        return None

    pair_step_id = _to_int(level_detail.get('pair_step_id'))
    left_id = _resolve_field_mod_choice_modification_id(level_detail, 1)
    right_id = _resolve_field_mod_choice_modification_id(level_detail, 2)
    if pair_step_id is None or left_id is None or right_id is None:
        return None

    return {
        'kind': MARKER_CLICK_ACTION_FIELD_MOD_PICK,
        'id': pair_step_id,
        'leftId': left_id,
        'rightId': right_id,
    }


def _resolve_field_mod_choice_modification_id(level_detail, choice_index):
    choice = None
    for choice in level_detail.get('available_choices') or []:
        if _to_int(choice.get('choice_index')) == choice_index:
            return _to_int(choice.get('modification_id'))
    return None


def _resolve_field_mod_toggle_group_id(level_detail):
    """The setup-switch group id a click on this unlocked feature level toggles.

    Only the loadout-switch feature levels (essentials / auxiliary) are freely
    togglable; the group id feeds WG's SWITCH_PREBATTLE_AMMO_PANEL_AVAILABILITY
    action, which applies without a confirmation dialog.
    """
    if not level_detail or level_detail.get('kind') != 'feature':
        return None
    return level_detail.get('feature_group_id')


def _resolve_field_mod_click_step_id(level, current_level, level_detail):
    """The post-progression step id a click on this level's marker should research.

    Only the next unresearched level is directly researchable (earlier levels are
    complete, later ones are blocked by it as a prerequisite). The id is the
    level's LEVELED base step -- also on levels with a variant pair, since the
    pair lives in a free MultiModsItem child that is chosen separately and never
    purchased. Skill-tree based plans never populate step ids here.
    """
    if level != current_level + 1:
        return None
    if not level_detail:
        return None
    return level_detail.get('research_step_id')


def _is_field_mod_pre_progress_detail(level_detail):
    if not level_detail:
        return False
    return level_detail.get('kind') in ('role_slot', 'dual')


def _build_field_mod_marker_display(level_detail, roman_level):
    if not level_detail:
        return {
            'label': roman_level,
            'showBarLabel': True,
            'hideBarIcon': True,
        }

    kind = level_detail.get('kind')
    if kind == 'feature':
        return {
            'label': '',
            'showBarLabel': False,
            'hideBarIcon': False,
            'barItemType': 'loadout_switch',
            'itemType': 'loadout_switch',
        }

    if kind == 'role_slot':
        normalized_category = _normalize_t11_category(level_detail.get('category'))
        if level_detail.get('is_active') and normalized_category in FIELD_MOD_BAR_ICON_CATEGORIES:
            return {
                'label': '',
                'showBarLabel': False,
                'hideBarIcon': False,
                'barItemType': normalized_category,
                'itemType': normalized_category,
            }
        return {
            'label': '',
            'showBarLabel': False,
            'hideBarIcon': False,
            'barItemType': 'role_slot',
            'itemType': 'role_slot',
        }

    if kind == 'dual':
        selected_choice_index = _resolve_field_mod_dual_selected_choice_index(level_detail)
        return {
            'label': _build_field_mod_dual_marker_label(selected_choice_index),
            'showBarLabel': True,
            'hideBarIcon': True,
        }

    return {
        'label': roman_level,
        'showBarLabel': True,
        'hideBarIcon': True,
    }


def _build_level_tooltip_title(level):
    return _loc('TOOLTIP_LEVEL_FORMAT', level=level)


def _build_field_mod_tooltip_subtitle(level_detail):
    if not level_detail:
        return None

    kind = level_detail.get('kind')
    if kind == 'feature':
        return _build_field_mod_feature_label(level_detail.get('action_name'))
    if kind == 'role_slot':
        return _wg_loc(
            '#veh_post_progression:roleSlotTooltipView/title',
            _loc('FIELD_MOD_TOOLTIP_SUBTITLE_ROLE_SLOT'),
        )
    if kind == 'dual':
        return _loc('FIELD_MOD_TOOLTIP_SUBTITLE_DUAL')
    return None


def _build_field_mod_feature_label(action_name):
    return _wg_loc(
        '#veh_post_progression:setupTooltipView/name/{0}'.format(action_name),
        _humanize_field_mod_token(action_name),
    )


# Loadout-switch features, keyed by their normalized action name (see the
# collector's _normalize_post_progression_feature_identifier), map to a mod-owned
# i18n key naming what the loadout contains -- shown parenthetically after the
# switch's own label. Unknown features simply omit the parenthetical.
_FIELD_MOD_LOADOUT_CONTENTS_KEYS = {
    'shellsconsumablesswitch': 'FIELD_MOD_LOADOUT_ESSENTIALS_CONTENTS',
    'optdevboostersswitch': 'FIELD_MOD_LOADOUT_AUXILIARY_CONTENTS',
}


def _resolve_field_mod_loadout_contents(action_name):
    normalized = re.sub(r'[^a-z0-9]+', '', (action_name or '').lower())
    contents_key = _FIELD_MOD_LOADOUT_CONTENTS_KEYS.get(normalized)
    if contents_key is None:
        return None
    return _loc(contents_key)


def _build_field_mod_feature_completed_label(level_detail):
    action_name = level_detail.get('action_name')
    label = _build_field_mod_feature_label(action_name)
    contents = _resolve_field_mod_loadout_contents(action_name)
    if contents:
        return u'{0} ({1})'.format(label, contents)
    return label


def _build_field_mod_marker_html_text(text, is_highlighted, is_bold=False):
    if not text:
        return ''

    color = FIELD_MOD_MARKER_HIGHLIGHT_HTML_COLOR if is_highlighted else FIELD_MOD_MARKER_MUTED_HTML_COLOR
    escaped_text = _escape_html(text)
    if is_highlighted or is_bold:
        escaped_text = '<b>{0}</b>'.format(escaped_text)
    return '<font color="{0}">{1}</font>'.format(color, escaped_text)


def _resolve_field_mod_dual_selected_choice_index(level_detail):
    if not level_detail:
        return None

    selected_choice_index = _to_int(level_detail.get('selected_choice_index'))
    if selected_choice_index is not None:
        if selected_choice_index <= 0:
            return None
        if selected_choice_index == 1:
            return 1
        if selected_choice_index == 2:
            return 2

    selected_mod_name = level_detail.get('selected_mod_name')
    if selected_mod_name:
        name_text = u'{0}'.format(selected_mod_name)
        if name_text.endswith('_1'):
            return 1
        if name_text.endswith('_2'):
            return 2

    return None


def _build_field_mod_dual_marker_label(selected_choice_index):
    if selected_choice_index == 1:
        return 'A'
    if selected_choice_index == 2:
        return 'B'
    return '-'


def _build_field_mod_completed_tooltip_text(level_detail):
    if not level_detail:
        return None

    kind = level_detail.get('kind')
    if kind == 'feature':
        label = _build_field_mod_feature_completed_label(level_detail)
        value = _loc('FIELD_MOD_STATUS_ACTIVE') if level_detail.get('is_active') else _loc('FIELD_MOD_STATUS_INACTIVE')
        return _loc('FIELD_MOD_VALUE_FORMAT', label=label, value=value)

    if kind == 'role_slot':
        lines = []
        if level_detail.get('is_active'):
            label = _wg_loc(
                '#veh_post_progression:roleSlotTooltipView/title',
                'Second Slot Category',
            )
            value = _localize_field_mod_category(level_detail.get('category'))
            if value:
                lines.append(_loc('FIELD_MOD_VALUE_FORMAT', label=label, value=value))

        available_categories_text = _build_field_mod_available_categories_text(level_detail)
        if available_categories_text:
            lines.append(available_categories_text)
        return '\n'.join(lines) if lines else None

    if kind == 'dual':
        selected_mod_name = _build_field_mod_selected_mod_name(level_detail)
        if not selected_mod_name:
            return _build_field_mod_pending_tooltip_text(level_detail)

        selected_choice_lines = level_detail.get('selected_choice_lines') or []
        if not selected_choice_lines:
            return selected_mod_name

        lines = [selected_mod_name]
        line = None
        for line in selected_choice_lines:
            text = line.get('text')
            if text:
                lines.append(text)
        return '\n'.join(lines)
    return None


def _build_field_mod_completed_tooltip_html(level_detail):
    if not level_detail:
        return None

    if level_detail.get('kind') == 'feature':
        label = _build_field_mod_feature_completed_label(level_detail)
        is_active = bool(level_detail.get('is_active'))
        value = _loc('FIELD_MOD_STATUS_ACTIVE') if is_active else _loc('FIELD_MOD_STATUS_INACTIVE')
        value_color = FIELD_MOD_DUAL_BUFF_HTML_COLOR if is_active else FIELD_MOD_DUAL_DEBUFF_HTML_COLOR
        return '<b>{0}:</b> <font color="{1}"><b>{2}</b></font>'.format(
            _escape_html(label),
            value_color,
            _escape_html(value),
        )

    if level_detail.get('kind') == 'role_slot':
        html_lines = []
        if level_detail.get('is_active'):
            label = _wg_loc(
                '#veh_post_progression:roleSlotTooltipView/title',
                'Second Slot Category',
            )
            value = _localize_field_mod_category(level_detail.get('category'))
            if value:
                html_lines.append(_build_field_mod_label_value_html(label, value))

        available_categories_html = _build_field_mod_available_categories_html(level_detail)
        if available_categories_html:
            html_lines.append(available_categories_html)
        return '<br/>'.join(html_lines) if html_lines else None

    if level_detail.get('kind') != 'dual':
        return None

    selected_mod_name = _build_field_mod_selected_mod_name(level_detail)
    if not selected_mod_name:
        return _build_field_mod_pending_tooltip_html(level_detail)

    selected_choice_lines = level_detail.get('selected_choice_lines') or []
    if not selected_choice_lines:
        return None

    html_lines = ['<b>{0}</b>'.format(_escape_html(selected_mod_name))]
    line = None
    for line in selected_choice_lines:
        text = line.get('text')
        if not text:
            continue
        html_lines.append(
            '<font color="{0}">{1}</font>'.format(
                FIELD_MOD_DUAL_DEBUFF_HTML_COLOR if line.get('is_debuff') else FIELD_MOD_DUAL_BUFF_HTML_COLOR,
                _escape_html(text),
            )
        )

    return '<br/>'.join(html_lines)


def _build_field_mod_pending_tooltip_text(level_detail):
    if not level_detail:
        return None

    kind = level_detail.get('kind')
    if kind == 'role_slot':
        return _build_field_mod_available_categories_text(level_detail)

    if kind == 'dual':
        return _build_field_mod_dual_choice_names_text(level_detail)

    return None


def _build_field_mod_pending_tooltip_html(level_detail):
    if not level_detail:
        return None

    kind = level_detail.get('kind')
    if kind == 'role_slot':
        return _build_field_mod_available_categories_html(level_detail)

    if kind == 'dual':
        return _build_field_mod_dual_choice_names_html(level_detail)

    return None


def _build_field_mod_available_categories_text(level_detail):
    categories = _resolve_field_mod_role_slot_category_labels(level_detail)
    if not categories:
        return None
    return _loc(
        'FIELD_MOD_VALUE_FORMAT',
        label=_loc('FIELD_MOD_TOOLTIP_AVAILABLE_CATEGORIES'),
        value=', '.join(categories),
    )


def _build_field_mod_available_categories_html(level_detail):
    categories = _resolve_field_mod_role_slot_category_labels(level_detail)
    if not categories:
        return None
    return _build_field_mod_label_value_html(
        _loc('FIELD_MOD_TOOLTIP_AVAILABLE_CATEGORIES'),
        ', '.join(categories),
    )


def _build_field_mod_dual_choice_names_text(level_detail):
    option_sections = _resolve_field_mod_dual_option_sections(level_detail)
    if not option_sections:
        return None

    rendered_sections = []
    section = None
    for section in option_sections:
        lines = [
            _loc('FIELD_MOD_VALUE_FORMAT', label=section.get('label'), value=section.get('name'))
        ]
        hint = section.get('hint')
        if hint:
            lines.append(hint)
        stat = None
        for stat in section.get('lines') or []:
            text = stat.get('text')
            if text:
                lines.append(text)
        rendered_sections.append('\n'.join(lines))

    return '\n\n'.join(rendered_sections)


def _build_field_mod_dual_choice_names_html(level_detail):
    option_sections = _resolve_field_mod_dual_option_sections(level_detail)
    if not option_sections:
        return None

    rendered_sections = []
    section = None
    for section in option_sections:
        html_lines = [
            _build_field_mod_label_value_html(section.get('label'), section.get('name')),
        ]
        hint = section.get('hint')
        if hint:
            html_lines.append(
                '<font color="{0}">{1}</font>'.format(
                    FIELD_MOD_CLICK_HINT_HTML_COLOR, _escape_html(hint)
                )
            )
        stat = None
        for stat in section.get('lines') or []:
            text = stat.get('text')
            if not text:
                continue
            html_lines.append(_build_field_mod_dual_stat_html(text, bool(stat.get('is_debuff'))))
        rendered_sections.append('<br/>'.join([line for line in html_lines if line]))

    return '<br/><br/>'.join([section_html for section_html in rendered_sections if section_html])


def _resolve_field_mod_dual_option_sections(level_detail):
    show_hints = bool(level_detail.get('_show_pick_hints')) if level_detail else False
    option_sections = []
    choice_index = None
    for choice_index in (1, 2):
        option_name = _resolve_field_mod_dual_choice_name(level_detail, choice_index)
        if not option_name:
            continue
        option_label = _loc('FIELD_MOD_TOOLTIP_OPTION_A') if choice_index == 1 else _loc('FIELD_MOD_TOOLTIP_OPTION_B')
        choice = _resolve_field_mod_dual_choice(level_detail, choice_index) or {}
        section = {
            'label': option_label,
            'name': option_name,
            'lines': _resolve_field_mod_dual_choice_lines(choice),
        }
        if show_hints:
            section['hint'] = _loc(
                'TOOLTIP_KEY_OPTION_A' if choice_index == 1 else 'TOOLTIP_KEY_OPTION_B'
            )
        option_sections.append(section)
    return option_sections


def _resolve_field_mod_dual_choice_lines(choice):
    if not choice:
        return []

    result = []
    line = None
    for line in choice.get('lines') or []:
        text = line.get('text')
        if not text:
            continue
        result.append({
            'text': text,
            'is_debuff': bool(line.get('is_debuff')),
        })
    return result


def _resolve_field_mod_dual_choice(level_detail, choice_index):
    choice = None
    for choice in level_detail.get('available_choices') or []:
        if _to_int(choice.get('choice_index')) != choice_index:
            continue
        return choice
    return None


def _resolve_field_mod_dual_choice_name(level_detail, choice_index):
    choice = _resolve_field_mod_dual_choice(level_detail, choice_index)
    if choice is not None:
        return _localize_field_mod_mod_name(choice.get('mod_name'))
    return None


def _build_field_mod_label_value_html(label, value):
    if not label or not value:
        return None
    return '<b>{0}:</b> {1}'.format(_escape_html(label), _escape_html(value))


def _resolve_field_mod_role_slot_category_labels(level_detail):
    category_labels = []
    seen = set()
    category = None

    for category in level_detail.get('categories') or []:
        normalized_category = _normalize_field_mod_role_slot_category(category)
        if not normalized_category:
            continue
        label = _localize_field_mod_category(normalized_category)
        if not label or label in seen:
            continue
        seen.add(label)
        category_labels.append(label)

    if category_labels:
        return category_labels

    fallback_category = _normalize_field_mod_role_slot_category(level_detail.get('category'))
    if fallback_category:
        fallback_label = _localize_field_mod_category(fallback_category)
        if fallback_label:
            return [fallback_label]

    for category in FIELD_MOD_ROLE_SLOT_OPTION_CATEGORIES:
        label = _localize_field_mod_category(category)
        if not label or label in seen:
            continue
        seen.add(label)
        category_labels.append(label)
    return category_labels


def _build_field_mod_dual_stat_html(stat_text, is_debuff):
    color = FIELD_MOD_DUAL_DEBUFF_HTML_COLOR if is_debuff else FIELD_MOD_DUAL_BUFF_HTML_COLOR
    return '<font color="{0}">{1}</font>'.format(
        color,
        _escape_html(stat_text),
    )


def _resolve_t11_completed_tooltip_status_text():
    return _loc('CAPTION_UNLOCKED')


def _resolve_t11_completed_tooltip_status_html():
    return '<font color="{0}"><b>{1}</b></font>'.format(
        FIELD_MOD_MARKER_HIGHLIGHT_HTML_COLOR,
        _escape_html(_resolve_t11_completed_tooltip_status_text()),
    )


def _resolve_t11_action_status_text(action_node, marker_state):
    status_text = _build_t11_action_special_info_text(action_node)
    if status_text:
        return status_text
    if marker_state == 'completed':
        return _resolve_t11_completed_tooltip_status_text()
    return None


def _resolve_t11_action_status_html(action_node, marker_state):
    status_html = _build_t11_action_special_info_html(action_node)
    if status_html:
        return status_html
    if marker_state == 'completed':
        return _resolve_t11_completed_tooltip_status_html()
    return None


def _build_field_mod_selected_mod_name(level_detail):
    selected_mod_name = level_detail.get('selected_mod_name')
    if selected_mod_name:
        return _localize_field_mod_mod_name(selected_mod_name)

    selected_choice_index = _to_int(level_detail.get('selected_choice_index'))
    multi_action_name = level_detail.get('multi_action_name')
    if selected_choice_index is None or selected_choice_index <= 0 or not multi_action_name:
        return None

    selected_mod_name = '{0}_{1}'.format(multi_action_name, selected_choice_index)
    return _localize_field_mod_mod_name(selected_mod_name)


def _localize_field_mod_mod_name(mod_name):
    if not mod_name:
        return None
    return _wg_loc(
        '#artefacts:{0}/name'.format(mod_name),
        _humanize_field_mod_token(mod_name),
    )


def _escape_html(value):
    # Escapes HTML metacharacters and encodes non-ASCII code points as HTML numeric
    # entities (&#xXXXX;). Entities are pure ASCII, so they cross the Python->Scaleform
    # bridge unchanged and Flash's HTML parser decodes them back to the original code
    # points. Output is for htmlText fields only (a plain TextField shows entities
    # literally). Glyph coverage for the decoded code points is handled separately by
    # the fallback font (see FALLBACK_FONT_NAME in ResearchProgressBarFonts.as).
    if value is None:
        return ''
    if isinstance(value, bytes):
        try:
            text = value.decode('utf-8')
        except Exception:
            text = value.decode('latin-1')
    else:
        text = u'{0}'.format(value)

    result = []
    for c in text:
        code = ord(c)
        if c == '&':
            result.append('&amp;')
        elif c == '<':
            result.append('&lt;')
        elif c == '>':
            result.append('&gt;')
        elif c == '"':
            result.append('&quot;')
        elif code > 127:
            result.append('&#x{0:X};'.format(code))
        else:
            result.append(c)
    return ''.join(result)


def _localize_field_mod_category(category):
    localization_keys = _iter_field_mod_category_localization_keys(category)
    if not localization_keys:
        return _loc('FIELD_MOD_STATUS_INACTIVE')

    localization_key = None
    for localization_key in localization_keys:
        localized_text = _sanitize_field_mod_category_label(
            _wg_loc('#tank_setup:categories/{0}'.format(localization_key)),
            localization_key,
        ) or _sanitize_field_mod_category_label(
            _wg_loc('#veh_post_progression:categories/{0}'.format(localization_key)),
            localization_key,
        )
        if localized_text:
            return localized_text

    return _humanize_field_mod_token(localization_keys[0])


def _sanitize_field_mod_category_label(label, localization_key):
    text = u'{0}'.format(label or '').strip()
    if not text:
        return None

    normalized_text = text.lower()
    unresolved_values = (
        '#tank_setup:categories/{0}'.format(localization_key),
        'tank_setup:categories/{0}'.format(localization_key),
        '#veh_post_progression:categories/{0}'.format(localization_key),
        'veh_post_progression:categories/{0}'.format(localization_key),
        'categories/{0}'.format(localization_key),
    )
    if normalized_text in unresolved_values:
        return None
    return text


def _iter_field_mod_category_localization_keys(category):
    normalized_category = _normalize_t11_category(category)
    if not normalized_category:
        return []

    localization_keys = [normalized_category]
    alias_map = {
        'scouting': ('reconnaissance', 'stealth'),
        'mechanics': ('mechanic',),
    }
    alias = None
    for alias in alias_map.get(normalized_category, ()):
        if alias not in localization_keys:
            localization_keys.append(alias)
    return localization_keys


def _humanize_field_mod_token(value):
    if not value:
        return ''

    text = u'{0}'.format(value).replace('_', ' ').strip()
    if not text:
        return ''
    return text[0].upper() + text[1:]


def _build_t11_markers(display_layout, vehicle_xp, total_xp, click_to_research=True):
    completed_minor_nodes = display_layout['completed_minor_nodes']
    completed_major_nodes = display_layout['completed_major_nodes']
    remaining_minor_nodes = display_layout['remaining_minor_nodes']
    remaining_major_nodes = display_layout['remaining_major_nodes']
    remaining_final_nodes = display_layout['remaining_final_nodes']
    remaining_minor_count = display_layout['remaining_minor_count']
    remaining_major_count = display_layout['remaining_major_count']
    remaining_final_count = display_layout['remaining_final_count']
    markers = _build_t11_completed_markers(completed_minor_nodes, completed_major_nodes)
    completed_cost = display_layout['completed_cost']

    if remaining_minor_count > 0:
        minor_marker = _make_t11_marker(
            marker_id='t11_minor_upgrade',
            position_value=completed_cost + 10000,
            cost_xp=10000,
            name=_loc('UPGRADE_MINOR'),
            remaining_cost=10000,
            vehicle_xp=vehicle_xp,
            total_xp=total_xp,
            action_node=_first_t11_action_node(remaining_minor_nodes),
        )
        minor_marker['itemType'] = 'minor_upgrade'
        minor_marker['barItemType'] = 'minor_upgrade'
        minor_marker['iconPaths'] = []
        minor_marker['iconCacheKey'] = 'minor_upgrade'
        minor_marker['hideTooltipIcon'] = False
        minor_marker['name'] = _loc('UPGRADE_MINOR')
        minor_marker['tooltipSubtitle'] = _format_t11_upgrades_remaining(remaining_minor_count)
        if display_layout['minor_reachable']:
            _apply_t11_upgrades_click(minor_marker, click_to_research)
        else:
            _apply_t11_blocked_marker(minor_marker)
        markers.append(minor_marker)

    if remaining_major_count > 0:
        major_marker = _make_t11_marker(
            marker_id='t11_major_upgrade',
            position_value=completed_cost + 20000,
            cost_xp=20000,
            name=_loc('UPGRADE_MAJOR'),
            remaining_cost=20000,
            vehicle_xp=vehicle_xp,
            total_xp=total_xp,
            action_node=_first_t11_action_node(remaining_major_nodes),
        )
        major_marker['itemType'] = 'major_upgrade'
        major_marker['barItemType'] = 'major_upgrade'
        major_marker['iconPaths'] = []
        major_marker['iconCacheKey'] = 'major_upgrade'
        major_marker['hideTooltipIcon'] = False
        major_marker['name'] = _loc('UPGRADE_MAJOR')
        major_marker['tooltipSubtitle'] = _format_t11_upgrades_remaining(remaining_major_count)
        if display_layout['major_reachable']:
            _apply_t11_upgrades_click(major_marker, click_to_research)
        else:
            _apply_t11_blocked_marker(major_marker)
        markers.append(major_marker)

    if remaining_final_count > 0:
        final_node = _first_t11_action_node(remaining_final_nodes)
        final_available = remaining_minor_count == 0 and remaining_major_count == 0
        if final_available:
            final_state = _resolve_remaining_cost_marker_state(25000, vehicle_xp, total_xp)
        else:
            final_state = 'locked'
        final_marker = {
            'id': 't11_final_upgrade',
            'positionValue': display_layout['total_cost'],
            'costXp': 25000,
            'itemType': 'unknown',
            'isAvailable': final_available,
            'missingPrereqNames': [_loc('UPGRADE_ALL_OTHER_NODES')] if not final_available else [],
            'missingPrereqs': [],
            'prerequisitesLabel': _loc('TOOLTIP_PREREQUISITES'),
            # The final node's prerequisite is the abstract "all other nodes", so
            # there is no item list to price row-by-row. Surface the combined cost
            # (the whole remaining tree: this node plus every other remaining one)
            # the same way research-mode prerequisite items do, and the view then
            # measures its progress rows against that total instead of the node's
            # own 25k. Available final nodes have no prerequisites, so they keep
            # the plain cost.
            'costWithPrereqsXp': None if final_available else display_layout['remaining_cost'],
            'costWithPrereqsLabel': _loc('TOOLTIP_COST_WITH_PREREQS'),
            'name': _resolve_t11_action_node_name(final_node, _loc('UPGRADE_FINAL')),
            'label': '',
            'hideTooltipIcon': True,
            'markerState': final_state,
            'progressLabel': _loc('CAPTION_VEHICLE_XP'),
            'totalProgressLabel': _loc('CAPTION_TOTAL_XP'),
            'progressReadyText': _loc('STATUS_READY_FOR_RESEARCH'),
            'progressXpLeftFormat': _loc('STATUS_XP_LEFT_FORMAT'),
            'completedLabel': _loc('CAPTION_UNLOCKED'),
        }
        final_marker = _apply_t11_action_metadata(final_marker, final_node)
        final_marker = _apply_t11_action_tooltip_details(final_marker, final_node)
        _apply_t11_upgrades_click(final_marker, click_to_research)
        markers.append(_apply_t11_bar_icon(final_marker, True))

    return markers


def _apply_t11_upgrades_click(marker, click_to_research):
    """Arms the "open the upgrades screen" click on a remaining Tier 11 node.

    The flat bar cannot represent the branching upgrade tree, so a click does not
    buy a specific node -- it just opens WG's own upgrades screen where the player
    picks and buys. Gated by the "Click to research or purchase" setting; the view
    then only shows the hand cursor and blue hint when the node is actually
    reachable (its cost is within reach of a displayed XP row), and never on a
    final node still locked behind the other nodes (isAvailable is False there).
    """
    if not click_to_research:
        return marker

    marker['clickAction'] = {'kind': MARKER_CLICK_ACTION_UPGRADES, 'id': 0}
    marker['clickHintText'] = _loc('TOOLTIP_CLICK_TO_OPEN_UPGRADES')
    return marker


def _format_t11_upgrades_remaining(count):
    """The "Upgrades remaining: N" line shown under a minor/major bucket title,
    with the count in bold.

    A bucket stands in for every remaining node of its tier, so the count tells
    the player how many are left; a count-agnostic phrasing sidesteps per-language
    plural rules. Rendered through the HTML subtitle row, so the localized label
    and the count are each escaped (a translation may hold HTML-special characters)
    and the number is wrapped in <b>. Only ever called with count >= 1 -- the
    minor/major markers are not built when their bucket is empty.
    """
    template = _loc('UPGRADE_REMAINING')  # raw, e.g. "Upgrades remaining: {count}"
    bold_count = u'<b>{0}</b>'.format(_escape_html(u'{0}'.format(count)))
    return bold_count.join(_escape_html(part) for part in template.split(u'{count}'))


def _apply_t11_blocked_marker(marker):
    """Grays out a bucket marker whose remaining upgrades are all locked behind
    other, not-yet-researched nodes in the tree -- none is researchable now.

    Mirrors how a prerequisite-blocked research marker is drawn (default/gray
    icon, no click), but the branching tree has no single prerequisite list worth
    showing, so the tooltip carries a short "requires other upgrades" line instead
    of a prerequisite/progress table. The forced 'locked' state overrides the
    XP-based state so an affordable-but-unreachable node is not painted green.
    """
    marker['isAvailable'] = False
    marker['markerState'] = 'locked'
    marker['blockedText'] = _loc('UPGRADE_REQUIRES_OTHERS')
    marker.pop('clickAction', None)
    marker.pop('clickHintText', None)
    return marker


def _build_t11_completed_markers(completed_minor_count, completed_major_count):
    markers = []
    var_minor_nodes = completed_minor_count or []
    var_major_nodes = completed_major_count or []

    for index in range(len(var_minor_nodes)):
        minor_node = var_minor_nodes[index]
        markers.append(_make_t11_completed_marker(
            marker_id='t11_completed_minor_{0}'.format(index + 1),
            position_value=(index + 1) * 10000,
            cost_xp=10000,
            name=_resolve_t11_action_node_name(minor_node, _loc('UPGRADE_MINOR')),
            action_node=minor_node,
        ))

    completed_minor_cost = len(var_minor_nodes) * 10000
    for index in range(len(var_major_nodes)):
        major_node = var_major_nodes[index]
        markers.append(_make_t11_completed_marker(
            marker_id='t11_completed_major_{0}'.format(index + 1),
            position_value=completed_minor_cost + ((index + 1) * 20000),
            cost_xp=20000,
            name=_resolve_t11_action_node_name(major_node, _loc('UPGRADE_MAJOR')),
            action_node=major_node,
        ))

    return markers


def _build_t11_display_layout(field_mods):
    researched = field_mods.get('t11_bucket_researched') or {}
    unresearched = field_mods.get('t11_bucket_unresearched') or {}
    researched_action_nodes = field_mods.get('t11_action_nodes_researched') or []

    unresearched_action_nodes = field_mods.get('t11_action_nodes_unresearched') or []
    completed_minor_count = _to_int(researched.get('small_10k')) or 0
    completed_major_count = _to_int(researched.get('big_20k')) or 0
    remaining_minor_count = _to_int(unresearched.get('small_10k')) or 0
    remaining_major_count = _to_int(unresearched.get('big_20k')) or 0
    remaining_final_count = _to_int(unresearched.get('big_25k')) or 0
    completed_minor_nodes = _pad_t11_action_nodes(
        _sort_t11_action_nodes_by_category(_filter_t11_action_nodes(researched_action_nodes, 10000)),
        completed_minor_count,
        _loc('UPGRADE_MINOR')
    )
    completed_major_nodes = _pad_t11_action_nodes(
        _sort_t11_action_nodes_by_category(_filter_t11_action_nodes(researched_action_nodes, 20000)),
        completed_major_count,
        _loc('UPGRADE_MAJOR')
    )
    remaining_minor_nodes = _sort_t11_action_nodes_by_category(
        _filter_t11_action_nodes(unresearched_action_nodes, 10000)
    )
    remaining_major_nodes = _sort_t11_action_nodes_by_category(
        _filter_t11_action_nodes(unresearched_action_nodes, 20000)
    )
    remaining_final_nodes = _sort_t11_action_nodes_by_category(
        _filter_t11_action_nodes(unresearched_action_nodes, 25000)
    )
    completed_minor_cost = (_to_int(researched.get('small_10k')) or 0) * 10000
    completed_major_cost = (_to_int(researched.get('big_20k')) or 0) * 20000
    remaining_minor_cost = remaining_minor_count * 10000
    remaining_major_cost = remaining_major_count * 20000
    remaining_final_cost = remaining_final_count * 25000
    completed_cost = completed_minor_cost + completed_major_cost
    total_cost = completed_cost + remaining_minor_cost + remaining_major_cost + remaining_final_cost

    # A bucket is reachable when at least one of its still-unresearched nodes has
    # its tree prerequisites satisfied (the game's own per-node state). When the
    # client cannot report node states, reachability_known is False and every
    # bucket is treated as reachable, preserving the plain cost-only behavior.
    reachable_buckets = field_mods.get('t11_bucket_unresearched_reachable') or {}
    reachability_known = bool(field_mods.get('t11_reachability_known'))
    minor_reachable = (not reachability_known) or (_to_int(reachable_buckets.get('small_10k')) or 0) > 0
    major_reachable = (not reachability_known) or (_to_int(reachable_buckets.get('big_20k')) or 0) > 0

    return {
        'completed_minor_count': completed_minor_count,
        'completed_major_count': completed_major_count,
        'completed_minor_nodes': completed_minor_nodes,
        'completed_major_nodes': completed_major_nodes,
        'remaining_minor_nodes': remaining_minor_nodes,
        'remaining_major_nodes': remaining_major_nodes,
        'remaining_final_nodes': remaining_final_nodes,
        'remaining_minor_count': remaining_minor_count,
        'remaining_major_count': remaining_major_count,
        'remaining_final_count': remaining_final_count,
        'completed_minor_cost': completed_minor_cost,
        'completed_major_cost': completed_major_cost,
        'completed_cost': completed_cost,
        'remaining_minor_cost': remaining_minor_cost,
        'remaining_major_cost': remaining_major_cost,
        'remaining_final_cost': remaining_final_cost,
        'remaining_cost': remaining_minor_cost + remaining_major_cost + remaining_final_cost,
        'total_cost': total_cost,
        'minor_reachable': minor_reachable,
        'major_reachable': major_reachable,
    }


def _make_t11_marker(
    marker_id,
    position_value,
    cost_xp,
    name,
    remaining_cost,
    vehicle_xp,
    total_xp,
    action_node=None,
    show_bar_icon=True,
):
    marker = {
        'id': marker_id,
        'positionValue': position_value,
        'costXp': cost_xp,
        'itemType': 'unknown',
        'isAvailable': True,
        'name': name,
        'label': '',
        'hideTooltipIcon': True,
        'markerState': _resolve_remaining_cost_marker_state(remaining_cost, vehicle_xp, total_xp),
        'progressLabel': _loc('CAPTION_VEHICLE_XP'),
        'totalProgressLabel': _loc('CAPTION_TOTAL_XP'),
        'progressReadyText': _loc('STATUS_READY_FOR_RESEARCH'),
        'progressXpLeftFormat': _loc('STATUS_XP_LEFT_FORMAT'),
        'completedLabel': _loc('CAPTION_UNLOCKED'),
    }
    marker = _apply_t11_action_metadata(marker, action_node)
    return _apply_t11_bar_icon(marker, show_bar_icon)


def _make_t11_completed_marker(marker_id, position_value, cost_xp, name, action_node=None, show_bar_icon=True):
    marker = {
        'id': marker_id,
        'positionValue': position_value,
        'costXp': cost_xp,
        'itemType': 'unknown',
        'isAvailable': True,
        'name': name,
        'label': '',
        'hideTooltipIcon': True,
        'markerState': 'completed',
        'progressReadyText': _loc('STATUS_READY_FOR_RESEARCH'),
        'progressXpLeftFormat': _loc('STATUS_XP_LEFT_FORMAT'),
        'completedLabel': _loc('CAPTION_UNLOCKED'),
    }
    marker = _apply_t11_action_metadata(marker, action_node)
    marker = _apply_t11_action_tooltip_details(marker, action_node)
    return _apply_t11_bar_icon(marker, show_bar_icon)


def _filter_t11_action_nodes(nodes, xp_cost):
    filtered = []
    for node in nodes:
        if _to_int((node or {}).get('xp_cost')) == xp_cost:
            filtered.append(node)
    return filtered


def _normalize_t11_category(category):
    if not category:
        return ''

    normalized = u'{0}'.format(category).strip().lower()
    if not normalized:
        return ''

    prefix = None
    for prefix in (
            '#tank_setup:categories/',
            'tank_setup:categories/',
            '#veh_post_progression:categories/',
            'veh_post_progression:categories/',
            'categories/'):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break

    if normalized in ('no category', 'no_category', 'none', 'null', 'undefined'):
        return ''

    if normalized == 'stealth':
        return 'scouting'
    if normalized == 'reconnaissance':
        return 'scouting'
    if normalized == 'mechanic':
        return 'mechanics'
    return normalized


def _normalize_field_mod_role_slot_category(category):
    normalized = _normalize_t11_category(category)
    if normalized in ('special', 'universal'):
        return ''
    if normalized and normalized not in FIELD_MOD_ROLE_SLOT_OPTION_CATEGORIES:
        return ''
    return normalized


def _sort_t11_action_nodes_by_category(nodes):
    if not nodes:
        return []

    def sort_key(node):
        normalized_category = _normalize_t11_category((node or {}).get('category'))
        return (
            T11_CATEGORY_SORT_ORDER.get(normalized_category, len(T11_CATEGORY_SORT_ORDER)),
            normalized_category,
            _resolve_t11_action_node_name(node, ''),
        )

    return sorted(nodes, key=sort_key)


def _pad_t11_action_nodes(nodes, expected_count, fallback_name):
    padded = list(nodes or [])
    expected = max(0, _to_int(expected_count) or 0)
    while len(padded) < expected:
        padded.append({'name': fallback_name})
    return padded[:expected]


def _first_t11_action_node(nodes):
    return nodes[0] if nodes else None


def _resolve_t11_action_node_name(action_node, fallback_name):
    if action_node is None:
        return fallback_name
    for key in ('tooltip_title', 'name', 'localized_name', 'ui_localized_name'):
        value = _clean_t11_action_stat_text(action_node.get(key))
        if value and not _looks_like_internal_t11_action_label(value):
            return value
    return fallback_name


def _build_t11_action_icon_paths(action_node):
    if action_node is None:
        return []

    bucket = action_node.get('bucket')
    category = action_node.get('category')
    image_name = action_node.get('image_name')
    if not image_name:
        return []

    ordered_branches = []
    if bucket == 'small_10k':
        ordered_branches.extend(['special'] if category == 'special' else [])
        ordered_branches.extend(['common', 'special'])
    elif bucket == 'big_20k':
        ordered_branches.append('major')
    elif bucket == 'big_25k':
        ordered_branches.append('final')

    for branch in ('common', 'major', 'final', 'special'):
        if branch not in ordered_branches:
            ordered_branches.append(branch)

    paths = []
    for branch in ordered_branches:
        for size in ('small', 'large'):
            paths.append(
                '../maps/icons/skillTree/tree/perks/{0}/skills/{1}/{2}.png'.format(
                    branch,
                    size,
                    image_name,
                )
            )
            paths.append(
                'img://gui/maps/icons/skillTree/tree/perks/{0}/skills/{1}/{2}.png'.format(
                    branch,
                    size,
                    image_name,
                )
            )

    for size in ('120x80', '192x120'):
        paths.append(
            '../maps/icons/vehPostProgression/actionItems/modificationWithFeature/{0}/{1}.png'.format(
                size,
                image_name,
            )
        )
        paths.append(
            'img://gui/maps/icons/vehPostProgression/actionItems/modificationWithFeature/{0}/{1}.png'.format(
                size,
                image_name,
            )
        )

    return paths


def _resolve_t11_action_display_item_type(action_node):
    if action_node is None:
        return ''

    kind = action_node.get('kind')
    if kind == 'feature':
        return 'loadout_switch'

    if kind == 'role_slot':
        if action_node.get('is_active'):
            active_category = _normalize_field_mod_role_slot_category(
                action_node.get('slot_category') or action_node.get('category')
            )
            if active_category in FIELD_MOD_BAR_ICON_CATEGORIES:
                return active_category
        return 'role_slot'

    return _normalize_t11_category(action_node.get('category'))


def _build_t11_action_role_slot_detail(action_node):
    if action_node is None or action_node.get('kind') != 'role_slot':
        return None

    return {
        'kind': 'role_slot',
        'category': action_node.get('slot_category') or action_node.get('category'),
        'categories': action_node.get('available_categories') or [],
        'is_active': bool(action_node.get('is_active')),
    }


def _build_t11_action_special_info_text(action_node):
    if action_node is None:
        return None

    kind = action_node.get('kind')
    if kind == 'feature':
        return _loc('FIELD_MOD_STATUS_ACTIVE') if action_node.get('is_active') else _loc('FIELD_MOD_STATUS_INACTIVE')

    role_slot_detail = _build_t11_action_role_slot_detail(action_node)
    if role_slot_detail is not None:
        return _build_field_mod_completed_tooltip_text(role_slot_detail)

    return None


def _build_t11_action_special_info_html(action_node):
    if action_node is None:
        return None

    kind = action_node.get('kind')
    if kind == 'feature':
        status_text = _build_t11_action_special_info_text(action_node)
        if not status_text:
            return None
        return _build_field_mod_marker_html_text(status_text, bool(action_node.get('is_active')), True)

    role_slot_detail = _build_t11_action_role_slot_detail(action_node)
    if role_slot_detail is not None:
        return _build_field_mod_completed_tooltip_html(role_slot_detail)

    return None


def _clean_t11_action_stat_text(text):
    if text is None:
        return None

    cleaned = re.sub(r'<[^>]+>', '', u'{0}'.format(text))
    cleaned = (
        cleaned.replace('&nbsp;', ' ')
        .replace('&lt;', '<')
        .replace('&gt;', '>')
        .replace('&amp;', '&')
    )
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned or None


def _looks_like_internal_t11_action_label(text):
    cleaned = _clean_t11_action_stat_text(text)
    if not cleaned:
        return True
    normalized = cleaned.strip()
    lowered = normalized.lower()
    if any(token in normalized for token in ('/', '\\', '#', ':')):
        return True
    if re.match(r'^[a-z0-9_]+$', lowered) is not None:
        return True
    if ' ' not in normalized and re.match(r'^[a-z][A-Za-z0-9_]+$', normalized) is not None:
        return True
    return False


def _normalize_t11_description_key(value):
    if value is None:
        return None

    key = u'{0}'.format(value).strip()
    if not key or ' ' in key:
        return None
    if any(token in key for token in ('/', '\\', '#', ':')):
        return None
    return key


def _looks_like_unresolved_t11_description_text(text, description_key=None):
    cleaned = _clean_t11_action_stat_text(text)
    if not cleaned:
        return True

    normalized = cleaned.replace('\\', '/').strip()
    lowered = normalized.lower()
    if lowered.startswith('tooltips/description/'):
        return True

    key = _normalize_t11_description_key(description_key)
    if key:
        if lowered in (
                'tooltips/description/{0}'.format(key.lower()),
                'veh_skill_tree/tooltips/description/{0}'.format(key.lower()),
                '#veh_skill_tree:tooltips/description/{0}'.format(key.lower())):
            return True

    return False


def _resolve_t11_action_description_template(action_node):
    if action_node is None:
        return None

    for field_name in ('ui_localized_name', 'loc_name'):
        key = _normalize_t11_description_key(action_node.get(field_name))
        if not key:
            continue
        resource_key = '#veh_skill_tree:tooltips/description/{0}'.format(key)
        text = _wg_loc(resource_key)
        if text and text not in (key, resource_key) and not _looks_like_unresolved_t11_description_text(text, key):
            return text
    return None


def _format_t11_description_binding_value(value, kpi_type):
    if value is None:
        return None

    try:
        numeric_value = float(value)
    except Exception:
        return None

    if kpi_type == 'mul':
        numeric_value = 100.0 * (numeric_value - 1.0)

    numeric_value = abs(numeric_value)
    if abs(numeric_value - round(numeric_value)) < 0.0001:
        return u'{0}'.format(int(round(numeric_value)))
    return u'{0}'.format('{0:.15g}'.format(numeric_value))


def _build_t11_action_description_bindings(action_node):
    if action_node is None:
        return {}

    bindings = {}
    lines = action_node.get('kpi_lines') or []
    index = None
    line = None
    for index, line in enumerate(lines):
        key = _normalize_t11_description_key(line.get('kpi_name'))
        if not key:
            continue

        value_text = _format_t11_description_binding_value(
            line.get('kpi_value'),
            line.get('kpi_type'),
        )
        if value_text is None:
            continue

        if key not in bindings:
            bindings[key] = value_text
        bindings[u'{0}{1}'.format(key, index)] = value_text
    return bindings


def _replace_t11_action_description_tag_tokens(template_text, use_html=False):
    if not template_text:
        return None

    def _replace(match):
        tag_name = match.group(1) or match.group(3) or ''
        token_kind = (match.group(2) or match.group(4) or '').lower()
        if not use_html:
            return ''
        if token_kind in ('open', 'start'):
            color = _T11_DESCRIPTION_TAG_COLORS.get(tag_name, _T11_DESCRIPTION_DEFAULT_TAG_COLOR)
            return '<font color="{0}">'.format(color)
        return '</font>'

    return _T11_DESCRIPTION_TAG_TOKEN_RE.sub(_replace, u'{0}'.format(template_text))


def _bind_t11_action_description_template(template_text, bindings, use_html=False):
    if not template_text:
        return None

    text = _replace_t11_action_description_tag_tokens(template_text, use_html=use_html)
    unresolved = []

    def _replace(match):
        placeholder = match.group(1) or match.group(2)
        value = bindings.get(placeholder)
        if value is None:
            unresolved.append(placeholder)
            return match.group(0)
        return _escape_html(value) if use_html else value

    text = _T11_DESCRIPTION_PLACEHOLDER_RE.sub(_replace, text)
    if unresolved:
        return None

    if use_html:
        return text.replace('\r\n', '\n').replace('\r', '\n').replace('\n', '<br/>')

    return _clean_t11_action_stat_text(text)


def _build_t11_action_description_text(action_node):
    template_text = _resolve_t11_action_description_template(action_node)
    if not template_text:
        return None
    return _bind_t11_action_description_template(
        template_text,
        _build_t11_action_description_bindings(action_node),
        use_html=False,
    )


def _build_t11_action_description_html(action_node):
    template_text = _resolve_t11_action_description_template(action_node)
    if not template_text:
        return None
    return _bind_t11_action_description_template(
        template_text,
        _build_t11_action_description_bindings(action_node),
        use_html=True,
    )


def _join_t11_tooltip_text_sections(*sections):
    return '\n\n'.join([section for section in sections if section])


def _join_t11_tooltip_html_sections(*sections):
    return '<br/><br/>'.join([section for section in sections if section])


def _apply_t11_action_tooltip_details(marker, action_node):
    if marker is None or action_node is None:
        return marker

    description_text = _build_t11_action_description_text(action_node)
    description_html = _build_t11_action_description_html(action_node)
    marker_state = marker.get('markerState')
    status_text = _resolve_t11_action_status_text(action_node, marker_state)
    status_html = _resolve_t11_action_status_html(action_node, marker_state)
    body_text = _join_t11_tooltip_text_sections(description_text, status_text)
    body_html = _join_t11_tooltip_html_sections(description_html, status_html)

    if marker_state == 'completed':
        if body_text:
            marker['completedTooltipText'] = body_text
        if body_html:
            marker['completedTooltipHtml'] = body_html
        return marker

    if body_text:
        marker['preProgressTooltipText'] = body_text
    if body_html:
        marker['preProgressTooltipHtml'] = body_html
    return marker


def _apply_t11_action_metadata(marker, action_node):
    if action_node is None:
        return marker

    image_name = action_node.get('image_name')
    category = _normalize_t11_category(action_node.get('category'))
    display_item_type = _resolve_t11_action_display_item_type(action_node)
    if display_item_type:
        marker['itemType'] = display_item_type
    elif category:
        marker['itemType'] = category
    icon_paths = _build_t11_action_icon_paths(action_node)
    if icon_paths:
        marker['iconPaths'] = icon_paths
        if category:
            marker['iconCacheKey'] = 't11:{0}:{1}'.format(category, image_name)
        else:
            marker['iconCacheKey'] = 't11:{0}'.format(image_name)
        marker['hideTooltipIcon'] = False
    elif display_item_type:
        marker['hideTooltipIcon'] = False
    return marker


def _resolve_t11_bar_item_type(marker):
    category = _normalize_t11_category(marker.get('itemType'))
    if category in ('firepower', 'survivability', 'mobility', 'scouting', 'stealth', 'role_slot', 'loadout_switch'):
        return category
    return ''


def _apply_t11_bar_icon(marker, show_bar_icon=True):
    bar_item_type = _resolve_t11_bar_item_type(marker)
    if not show_bar_icon:
        marker['hideBarIcon'] = True
        return marker

    if bar_item_type:
        marker['barItemType'] = bar_item_type

    return marker


def _resolve_field_mod_marker_state(level, current_level, remaining_cost, vehicle_xp, total_xp):
    if level <= current_level:
        return 'completed'
    return _resolve_remaining_cost_marker_state(remaining_cost, vehicle_xp, total_xp)


def _resolve_remaining_cost_marker_state(remaining_cost, vehicle_xp, total_xp):
    if remaining_cost <= max(0, vehicle_xp):
        return 'reachable_vehicle'
    if remaining_cost <= max(0, total_xp):
        return 'reachable_total'
    return 'locked'


def _make_mode(
        mode_id,
        button_label,
        bar_max_value,
        primary_value,
        secondary_value,
        left_counter_text,
        left_counter_caption,
        right_counter_text,
        right_counter_caption,
        markers=None,
        completed_value=0.0,
        side_counter_text='',
        side_counter_caption='',
        counter_layout='',
        bar_fill_mode=''):
    bar_max = max(1.0, float(bar_max_value or 0))
    completed = _clamp(float(completed_value or 0), 0.0, bar_max)
    primary = _clamp(float(primary_value or 0), 0.0, bar_max - completed)
    secondary = _clamp(float(secondary_value or 0), 0.0, bar_max - completed - primary)

    return {
        'id': mode_id,
        'buttonLabel': button_label,
        'barMaxValue': bar_max,
        'completedValue': completed,
        'primaryValue': primary,
        'secondaryValue': secondary,
        'leftCounterText': left_counter_text,
        'leftCounterCaption': left_counter_caption,
        'rightCounterText': right_counter_text,
        'rightCounterCaption': right_counter_caption,
        'sideCounterText': side_counter_text,
        'sideCounterCaption': side_counter_caption,
        'markers': markers or [],
        'counterLayout': counter_layout,
        'barFillMode': bar_fill_mode,
    }


def _stamp_tooltip_indices(modes):
    """Give every marker a name that is unique across the whole context.

    The tooltip is drawn by a second view now, on a band of its own, so the bar has
    to say which markers the cursor is over rather than hand their data back. The index is that
    name: the bar reads it off the marker it hit, and Python looks the marker up in the context
    it last sent. Anything derived from the marker's own fields would have to be unique across
    every kind of marker, which none of them is.

    Numbered across modes rather than within one. Every mode starts its own marker list at zero,
    so a per-mode index names a different marker in each of them.

    Each marker also carries the XP figures of the mode it belongs to. The tooltip measures a
    marker's progress against them, and once the markers are flattened for lookup there is
    nothing left to say which mode a marker came from.
    """
    index = 0
    for mode in modes:
        combat_xp = mode.get('primaryValue') or 0
        free_xp = mode.get('secondaryValue') or 0
        for marker in mode.get('markers') or []:
            marker['tooltipIndex'] = index
            marker['tooltipCombatXp'] = combat_xp
            marker['tooltipFreeXp'] = free_xp
            index += 1


def _build_fractional_fill(base_units, max_units, step_cost, vehicle_xp, total_xp):
    if max_units <= 0:
        return 0.0, 0.0

    primary_value = float(max(0, min(base_units, max_units)))
    secondary_value = 0.0

    if step_cost is None or step_cost <= 0 or primary_value >= float(max_units):
        return primary_value, secondary_value

    vehicle_fraction = min(1.0, float(max(0, vehicle_xp)) / float(step_cost))
    total_fraction = min(1.0, float(max(0, total_xp)) / float(step_cost))
    secondary_fraction = max(0.0, total_fraction - vehicle_fraction)

    primary_value = min(float(max_units), primary_value + vehicle_fraction)
    secondary_value = min(float(max_units) - primary_value, secondary_fraction)
    return primary_value, secondary_value


def _is_field_mods_mode_enabled(field_mods, tier_plan, tech_tree, field_mods_mode=FIELD_MODS_MODE_ALWAYS):
    if field_mods_mode == FIELD_MODS_MODE_OFF:
        return False
    if not tech_tree.get('is_elite'):
        return False
    if not field_mods.get('exists'):
        return False
    if field_mods.get('is_veh_skill_tree'):
        return False

    if tier_plan.get('enabled'):
        if field_mods_mode == FIELD_MODS_MODE_ALWAYS:
            return (_to_int(tier_plan.get('max_level')) or 0) > 0
        return tier_plan.get('next_level') is not None

    unique_level_count = _to_int(field_mods.get('unique_level_count')) or 0
    unique_unlocked_level_count = _to_int(field_mods.get('unique_unlocked_level_count')) or 0
    if unique_level_count <= 0:
        return False
    if field_mods_mode == FIELD_MODS_MODE_ALWAYS:
        return True
    return unique_unlocked_level_count < unique_level_count


def _is_tier11_mode_enabled(field_mods, tech_tree):
    if not field_mods.get('is_veh_skill_tree'):
        return False
    total_steps = _to_int(field_mods.get('total_steps')) or 0
    return total_steps > 0


def _is_elite_progression_mode_enabled(tech_tree, elite_progression):
    vehicle_tier = _to_int(tech_tree.get('vehicle_tier'))
    if not tech_tree.get('is_elite'):
        return False
    if vehicle_tier is not None and vehicle_tier < 5:
        return False
    if not elite_progression.get('available'):
        return False
    return _to_int(elite_progression.get('current_level')) is not None


def _format_percent(current_value, target_value):
    target = _to_int(target_value)
    if target is None or target <= 0:
        return '0%'
    current = max(0, _to_int(current_value) or 0)
    return '{0}%'.format(int(min(100, current * 100 / target)))


def _to_roman(value):
    number = _to_int(value)
    if number is None or number <= 0:
        return str(value)

    parts = []
    numerals = (
        (1000, 'M'),
        (900, 'CM'),
        (500, 'D'),
        (400, 'CD'),
        (100, 'C'),
        (90, 'XC'),
        (50, 'L'),
        (40, 'XL'),
        (10, 'X'),
        (9, 'IX'),
        (5, 'V'),
        (4, 'IV'),
        (1, 'I'),
    )

    for numeral_value, numeral_text in numerals:
        while number >= numeral_value:
            parts.append(numeral_text)
            number -= numeral_value

    return ''.join(parts)


def _to_int(value):
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _clamp(value, min_value, max_value):
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value
