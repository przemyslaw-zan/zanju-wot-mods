# -*- coding: utf-8 -*-
"""Reads the active campaigns and the mission each one has running for the selected vehicle.

Everything here comes from `IEventsCache.getPersonalMissions()`, the client's own personal
missions cache. The mod asks it questions rather than reproducing what it knows: which
campaigns the server has active, which mission the player selected in each line, and whether
a line accepts the vehicle in the garage.

That API names a campaign two ways, and mixing them returns an empty result instead of an
error. The two are converted at one point below and never mixed -- see
docs/reference/personal-missions.md.

Every client import stays inside a function, so this module is importable outside the game.
"""
from __future__ import absolute_import, print_function, unicode_literals

from . import campaigns, mission_actions, mission_progress
from .localization import get_text as _loc

# What the widget face and its hover card show for one campaign.
STATE_ACTIVE = 'active'
STATE_PAUSED = 'paused'
# Everything that is not a mission to work on. The four ways of arriving here -- no vehicle, a
# vehicle no mission accepts, a campaign switched off, a disabled operation -- all leave the
# player with the same nothing, and the banner says so once. They are told apart in the log
# rather than on the card, because a player cannot act on the difference and a reader of
# python.log chasing a missing banner can.
STATE_NO_MATCH = 'nomatch'


# Why a banner came out with no mission on it. Reported when the set of reasons changes, not on
# every snapshot: a snapshot is built many times over the life of a garage.
_idle_reasons = set()
_last_idle_reasons = frozenset()


def _note_idle(reason):
    _idle_reasons.add(reason)


def _log_idle_reasons(logger):
    global _last_idle_reasons
    current = frozenset(_idle_reasons)
    if current == _last_idle_reasons:
        return
    for reason in sorted(current - _last_idle_reasons):
        logger.info('No mission to show: %s', reason)
    _last_idle_reasons = current


def collect(logger):
    """A snapshot of every active campaign, in campaign order. Never raises."""
    # `hasVehicle` is read by the log line that times the banners' arrival, not by the widget.
    snapshot = {'hasVehicle': False, 'campaigns': []}
    _idle_reasons.clear()
    try:
        missions = _personal_missions(logger)
        if missions is not None:
            vehicle = _current_vehicle(logger)
            snapshot['hasVehicle'] = vehicle is not None

            for branch_name in campaigns.order_branches(missions.getActiveCampaigns()):
                entry = _read_campaign(missions, branch_name, vehicle, logger)
                if entry is not None:
                    snapshot['campaigns'].append(entry)
    except Exception:
        logger.exception('Failed to read the active campaigns')
    _log_idle_reasons(logger)
    return snapshot


def find_active_mission(branch_name, logger):
    """The mission this campaign is running for the tank in the garage, or None.

    The same answer the snapshot's banner is built from, resolved again on demand. Clicking a
    banner reads it fresh rather than trusting a mission id carried in the payload: the player
    can pick a different mission, or a different tank, between the snapshot and the click.
    """
    try:
        from personal_missions import PM_BRANCH
        missions = _personal_missions(logger)
        vehicle = _current_vehicle(logger)
        branch_id = PM_BRANCH.NAME_TO_TYPE.get(branch_name)
        if missions is None or vehicle is None or branch_id is None:
            return None
        return campaigns.find_matching_mission(
            _selected_missions(missions, branch_id, logger), vehicle['type'], vehicle['level'])
    except Exception:
        logger.exception('Failed to find the active mission of campaign %s', branch_name)
        return None


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
        'attempts': [],
        'vehicles': None,
        'paces': [],
        'canPause': False,
        'canReset': False,
        'stage': '',
    }

    if not _is_enabled(missions, branch_id, logger):
        _note_idle('campaign %s is switched off on the server' % branch_name)
        return entry
    if vehicle is None:
        # Already reported by `_current_vehicle`, which knows which of its two answers it gave.
        return entry

    quest = campaigns.find_matching_mission(
        _selected_missions(missions, branch_id, logger), vehicle['type'], vehicle['level'])
    if quest is None:
        return entry

    _describe_mission(entry, missions, branch_id, quest, vehicle, logger)
    return entry


def _describe_mission(entry, missions, branch_id, quest, vehicle, logger):
    """Fill in the matched mission: its name, where it sits, and how far it has come.

    The three values the banner id is built from are locals rather than entry fields. Only the
    finished id is rendered, so shipping its ingredients would send the widget three strings
    it never reads.
    """
    # The game's own short name: "Union-10" where the full name is "Union-10. Raise the
    # Flag!". It is translated, which is what keeps the banner label out of this mod's
    # localization files.
    short_name = ''
    internal_id = None
    # The chain's own label -- the vehicle class, the alliance or the common role, depending
    # on the campaign. The card stopped showing it, but it is still the fallback the banner id
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
            # The client's own heading for an operation, which already carries the name in
            # the place the language wants it. Reading it saves this mod a string of its own.
            entry['operationTitle'] = _operation_title(name, logger)
        if _is_disabled(operation, quest):
            # The client is not offering this mission, so the banner offers nothing either. The
            # name goes with it: a banner naming a mission and saying there is none reads as a
            # contradiction, and the operation heading names something equally unavailable.
            _note_idle('an operation or mission is disabled in campaign %s' % branch_id)
            entry['state'] = STATE_NO_MATCH
            entry['mission'] = None
            entry['operationTitle'] = ''
            return

    entry['missionId'] = campaigns.build_mission_id(short_name, line, internal_id)
    progress = mission_progress.read_progress(quest, logger, vehicle.get('intCD'))
    entry['conditions'] = progress['conditions']
    entry['attempts'] = progress['attempts']
    entry['vehicles'] = progress['vehicles']
    entry['paces'] = _read_paces(progress['conditions'], progress['attempts'], logger)
    # What the mission is still worth playing for once its primary objective is settled: the
    # secondary reward, or an order committed to buy the primary one back. The banner says which
    # with an icon, and the card with a line of its own.
    entry['stage'] = progress['stage']

    # Which of the two mission actions the card may offer. `paused` is dropped rather than
    # carried: the entry already says so in `state`, and one answer in two places goes stale
    # in two ways.
    actions = mission_actions.read_actions(quest, progress['hasProgress'], logger)
    entry['canPause'] = actions['canPause']
    entry['canReset'] = actions['canReset']


# The requirement shape that carries an average: a total to reach in a fixed run of battles.
_LIMITED = 'limited'


def _operation_title(name, logger):
    """The client's own "Operation <name>" heading, or the bare name.

    Falling back to the name alone rather than to nothing: the name is the half a player reads,
    and a card headed "Excalibur" still says which operation the mission belongs to.
    """
    try:
        from helpers import i18n
        return i18n.makeString('#quests:tileChainsView/title', name=name)
    except Exception:
        logger.exception('Failed to read the operation heading')
        return name


def _read_paces(conditions, attempts, logger):
    """One pace reading per objective that has an average to keep up with.

    Both objectives get their own: they share the battle allowance but not the total, so the
    secondary usually asks for a steeper average than the primary. An objective already at its
    total drops out on its own, because there is no longer a pace to keep.
    """
    rows = []
    for attempt in attempts or ():
        row = _read_pace(conditions, attempt, logger)
        if row is not None:
            rows.append(row)
    return rows


def _read_pace(conditions, attempt, logger):
    """Where one objective's running total stands against the average the mission asks for."""
    try:
        if attempt.get('type') != _LIMITED:
            return None

        score = _score_condition(conditions, attempt.get('main'))
        if score is None:
            return None

        reading = campaigns.pace(
            score.get('current'), score.get('goal'),
            attempt.get('current'), attempt.get('goal'))
        if reading is None:
            return None

        return {
            # Composed here rather than in the widget, so the line stays translatable and a
            # language can order it its own way.
            'text': _loc('LABEL_PACE', percent=_format_number(reading['percent'], logger)),
            'ahead': reading['ahead'],
            'main': bool(attempt.get('main')),
        }
    except Exception:
        logger.exception('Failed to work out the pace of a mission')
        return None


def _score_condition(conditions, is_main):
    """The running total an objective is building, or None when it has no counted condition."""
    for condition in conditions:
        if bool(condition.get('main')) == bool(is_main) and condition.get('counted'):
            return condition
    return None


def _format_number(value, logger):
    """A whole number as the client would write it, so its grouping suits the language."""
    try:
        from gui.impl import backport
        return backport.getNiceNumberFormat(value)
    except Exception:
        logger.exception('Failed to format a number; falling back to a plain one')
        return '{0}'.format(value)


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
    read, and `level` is its tier. `intCD` is the compact descriptor, which is how the client
    records the vehicles a mission has already been completed in.

    Vehicles restricted to one battle mode are reported as no vehicle at all, because personal
    missions do not accept them -- the same test the client's own vehicle search makes.
    """
    try:
        from CurrentVehicle import g_currentVehicle
        if not g_currentVehicle.isPresent():
            _note_idle('there is no vehicle in the garage')
            return None
        item = g_currentVehicle.item
        vehicle_type = item.descriptor.type
        if _is_mode_locked(vehicle_type, logger):
            _note_idle('the vehicle in the garage is locked to one battle mode')
            return None
        return {'type': vehicle_type, 'level': item.level, 'intCD': item.intCD}
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
