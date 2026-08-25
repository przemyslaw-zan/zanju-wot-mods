# -*- coding: utf-8 -*-
"""Reads the active campaigns and the mission each one has running for the selected vehicle.

Everything here comes from `IEventsCache.getPersonalMissions()`, the client's own personal
missions cache. The mod asks it questions rather than reproducing what it knows: which
campaigns the server has active, which mission the player selected in each line, and whether
a line accepts the vehicle in the garage.

**One trap in that API.** It names a campaign two ways. `getActiveCampaigns()` answers with
branch *names* (`'regular'`, `'pm2'`, `'pm3'`), while every other call takes a branch *number*
(`PM_BRANCH.REGULAR` and friends). Passing one where the other belongs returns an empty
result instead of an error, so the two are converted at one point below and never mixed.

Every client import stays inside a function, so this module is importable outside the game.
"""
from __future__ import absolute_import, print_function, unicode_literals

from . import campaigns, mission_progress
from .localization import get_text as _loc

# What the widget face and its hover card show for one campaign.
STATE_ACTIVE = 'active'
STATE_PAUSED = 'paused'
STATE_NO_MATCH = 'nomatch'
STATE_NO_VEHICLE = 'novehicle'
STATE_DISABLED = 'disabled'


def collect(logger):
    """A snapshot of every active campaign, in campaign order. Never raises."""
    # `hasVehicle` is read by the log line that times the badges' arrival, not by the widget.
    snapshot = {'hasVehicle': False, 'campaigns': []}
    try:
        missions = _personal_missions(logger)
        if missions is None:
            return snapshot

        vehicle = _current_vehicle(logger)
        snapshot['hasVehicle'] = vehicle is not None

        for branch_name in campaigns.order_branches(missions.getActiveCampaigns()):
            entry = _read_campaign(missions, branch_name, vehicle, logger)
            if entry is not None:
                snapshot['campaigns'].append(entry)
    except Exception:
        logger.exception('Failed to read the active campaigns')
    return snapshot


def _read_campaign(missions, branch_name, vehicle, logger):
    """One campaign's widget data, or None when the campaign cannot be read at all."""
    from personal_missions import PM_BRANCH
    branch_id = PM_BRANCH.NAME_TO_TYPE.get(branch_name)
    if branch_id is None:
        return None

    # Exactly what the widget renders, and nothing else. Anything needed only to work one of
    # these out stays a local in _describe_mission -- this dict is serialised and shipped on
    # every refresh, so a field no reader wants is weight for nobody.
    entry = {
        'branch': branch_name,
        'numeral': campaigns.numeral(branch_name),
        'campaign': _campaign_name(missions, branch_id, None, logger),
        'state': STATE_NO_MATCH,
        'mission': None,
        'missionId': '',
        'operationTitle': '',
        'conditions': [],
    }

    if not _is_enabled(missions, branch_id, logger):
        entry['state'] = STATE_DISABLED
        return entry
    if vehicle is None:
        entry['state'] = STATE_NO_VEHICLE
        return entry

    quest = campaigns.find_matching_mission(
        _selected_missions(missions, branch_id, logger), vehicle['type'], vehicle['level'])
    if quest is None:
        return entry

    _describe_mission(entry, missions, branch_id, quest, logger)
    return entry


def _describe_mission(entry, missions, branch_id, quest, logger):
    """Fill in the matched mission: its name, where it sits, and how far it has come.

    The three values the badge id is built from are locals rather than entry fields. Only the
    finished id is rendered, so shipping its ingredients would send the widget three strings
    it never reads.
    """
    # The game's own short name: "Union-10" where the full name is "Union-10. Raise the
    # Flag!". It is translated, which is what keeps the badge label out of this mod's
    # localization files.
    short_name = ''
    internal_id = None
    # The chain's own label -- the vehicle class, the alliance or the common role, depending
    # on the campaign. The card stopped showing it, but it is still the fallback the badge id
    # falls back on when the client has no short name for a mission.
    line = ''

    try:
        entry['state'] = STATE_PAUSED if quest.isOnPause else STATE_ACTIVE
        entry['mission'] = quest.getUserName()
        entry['campaign'] = _campaign_name(missions, branch_id, quest.getCampaignID(), logger)
        short_name = _safe_text(quest.getShortUserName, logger=logger)
        internal_id = quest.getInternalID()
    except Exception:
        logger.exception('Failed to read the name of the active mission')

    operation = _operation_of(missions, branch_id, quest, logger)
    if operation is not None:
        # The operation knows which of the three classifiers its campaign uses, so it is asked
        # rather than the branch being tested here.
        line = _chain_name(operation, quest, logger)
        # Already display text: the client resolves this one itself. It answers with the
        # vehicle the operation awards -- "Excalibur", "StuG IV" -- which is what the game
        # names its operations after.
        name = _safe_text(operation.getShortUserName, logger=logger)
        if name:
            # Composed here rather than in the widget, so the wording stays translatable and
            # a language that puts the name first can say so in its own file.
            entry['operationTitle'] = _loc('LABEL_OPERATION_TITLE', name=name)
        if _is_disabled(operation, quest):
            entry['state'] = STATE_DISABLED

    entry['missionId'] = campaigns.build_mission_id(short_name, line, internal_id)
    entry['conditions'] = mission_progress.read_conditions(quest, logger)


def _chain_name(operation, quest, logger):
    """The line's display name -- the vehicle class, the alliance or the common role.

    Two steps, because `getChainName` answers with a resource id rather than the text behind
    it: `#personal_missions:sidebar/vehicles/heavyTank` for a campaign 1 line, and the
    equivalent for the other two. Inside the client that is not a bug -- Scaleform resolves the
    id on its way to the UI, so nothing there has to. This mod renders its own text, so it has
    to do that step itself.

    `makeString` returns anything that is not a resource id unchanged, so a client that starts
    resolving these itself keeps working.
    """
    name = _safe_text(operation.getChainName, quest.getChainID(), logger=logger)
    if not name:
        return ''
    try:
        from helpers import i18n
        return i18n.makeString(name)
    except Exception:
        logger.exception('Failed to resolve the name of line %s', name)
        return name


def _selected_missions(missions, branch_id, logger):
    """The missions the player has running in this campaign, one per line at most.

    Sorted by mission id so the order is the same on every read. It only matters when a
    campaign somehow offers two matches for one vehicle, which the lines are built to prevent.
    """
    try:
        selected = missions.getSelectedQuestsForBranch(branch_id)
        return [selected[key] for key in sorted(selected.keys())]
    except Exception:
        logger.exception('Failed to read the selected missions of campaign %s', branch_id)
        return []


def _operation_of(missions, branch_id, quest, logger):
    try:
        return missions.getOperationsForBranch(branch_id).get(quest.getOperationID())
    except Exception:
        logger.exception('Failed to find the operation holding mission %s', _quest_id(quest))
        return None


def _campaign_name(missions, branch_id, campaign_id, logger):
    """The campaign's own display name.

    A branch normally carries exactly one campaign. `campaign_id` names it exactly when a
    matched mission supplied one; otherwise the branch's lowest id is taken, which is stable
    across reads where iterating a dict is not.
    """
    try:
        available = missions.getCampaignsForBranch(branch_id)
        if not available:
            return ''
        campaign = available.get(campaign_id)
        if campaign is None:
            campaign = available[sorted(available.keys())[0]]
        return campaign.getUserName()
    except Exception:
        logger.exception('Failed to read the name of campaign %s', branch_id)
        return ''


def _is_enabled(missions, branch_id, logger):
    """Whether the server currently offers this campaign.

    Degrades to enabled: a campaign wrongly shown as running is a smaller fault than one that
    disappears because a settings read failed.
    """
    try:
        return bool(missions.isEnabled(branch_id))
    except Exception:
        logger.exception('Failed to read whether campaign %s is enabled', branch_id)
        return True


def _is_disabled(operation, quest):
    try:
        return bool(operation.isDisabled() or quest.isDisabled())
    except Exception:
        return False


def _personal_missions(logger):
    try:
        from helpers import dependency
        from skeletons.gui.server_events import IEventsCache
        return dependency.instance(IEventsCache).getPersonalMissions()
    except Exception:
        logger.exception('The personal missions cache is unavailable')
        return None


def _current_vehicle(logger):
    """The tank in the garage, as the two facts a mission is matched against, or None.

    `type` is the vehicle descriptor's type, which is what the client's own line classifiers
    read, and `level` is its tier. Vehicles restricted to one battle mode are reported as no vehicle at all, because
    personal missions do not accept them -- the same test the client's own vehicle search makes.
    """
    try:
        from CurrentVehicle import g_currentVehicle
        if not g_currentVehicle.isPresent():
            return None
        item = g_currentVehicle.item
        vehicle_type = item.descriptor.type
        if _is_mode_locked(vehicle_type, logger):
            return None
        return {'type': vehicle_type, 'level': item.level}
    except Exception:
        logger.exception('Failed to read the vehicle in the garage')
        return None


def _is_mode_locked(vehicle_type, logger):
    """Whether this vehicle is restricted to one battle mode, which bars it from missions.

    The same test the client's own vehicle search makes. `constants` here is the client's
    global module, not the `constants` sitting next to this file -- which is why every module
    in this package opts into absolute imports. Without that, Python 2 resolves the bare name
    to the sibling and the read fails on every snapshot.
    """
    try:
        from constants import BATTLE_MODE_VEHICLE_TAGS
        from gui.shared.gui_items import checkForTags
        return bool(checkForTags(vehicle_type.tags, BATTLE_MODE_VEHICLE_TAGS))
    except Exception:
        logger.exception('Failed to read the battle-mode tags of the vehicle')
        return False


def _safe_text(getter, *args, **kwargs):
    logger = kwargs.get('logger')
    try:
        return getter(*args) or ''
    except Exception:
        if logger is not None:
            logger.exception('Failed to read a campaign label')
        return ''


def _quest_id(quest):
    try:
        return quest.getID()
    except Exception:
        return '?'
