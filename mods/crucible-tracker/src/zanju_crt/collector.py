# -*- coding: utf-8 -*-
"""Reads the Crucible from the client and hands crucible.py plain data.

The series come from `IChallengesController`, the same call the client's own Crucible screen
makes. `getSortedChallenges` gives the series the player can see now, in the client's own order:
the hardest first, then by priority. The active series and the progress come from the account
tokens, read the way the controller reads them (see crucible.read_tokens). The controller reads
them only when the lobby view has loaded, and fires no event then, so a garage that builds
before that saw no active series.

The text of each condition comes from the client's own condition packer, so it is translated
into every language the client ships. Only the post-battle conditions are packed. The full
mission packer also packs the rewards, and on the first garage build that made the client log
"Trying to create fitting item type 12 when requesters are not fully synced". The conditions of
a mission never change, so each mission is packed once per session. With an active series,
every mission of it is packed, for the list of missions on the card.

Every client import stays inside a function, so this module is importable outside the game.
"""
from __future__ import absolute_import, print_function, unicode_literals

import json

from . import battle_record, crucible

# Quest ID -> (mission, conditions). A mission is cached only once its quest was found, so a
# garage that builds before the quest cache has synced tries again on the next refresh.
_missions = {}
# Quest ID -> the battle types of that mission, for the first mission of each series.
_bonus_types = {}


def collect(logger):
    """Return (snapshot, conditions). `conditions` belongs to the current mission, or is None."""
    controller = _controller(logger)
    level = _vehicle_level(logger)
    if controller is None or not _is_enabled(controller, logger):
        return crucible.build_snapshot(False, [], None, level, min_level=_min_level()), None

    series = []
    active_item = None
    active_progress = None
    try:
        items = list(controller.getSortedChallenges())
    except Exception:
        logger.exception('Failed to list the Crucible series')
        items = []
    active_id, progress = _token_state(controller, items, logger)
    for item in items:
        raw = _series_raw(item, active_id, progress, logger)
        if raw is None:
            continue
        series.append(raw)
        if raw['isActive']:
            active_item, active_progress = item, raw['progress']

    mission, conditions, missions = (None, None, None)
    if active_item is not None:
        mission, conditions = _mission(active_item, active_progress, logger)
        missions = [_quest_mission(quest_id, logger)[0] for quest_id in (active_item.questsIDs or ())]
    in_battle = crucible.counted_in_battle(
        _vehicles_in_battle(logger), battle_record.bonus_types_by_vehicle(account_dbid(), logger),
        _counted_bonus_types(items, conditions, logger))
    snapshot = crucible.build_snapshot(True, series, mission, level, in_battle, _min_level(), missions)
    return snapshot, conditions


def _token_state(controller, items, logger):
    """(active series ID, {series ID: progress}) from the account tokens, or from the controller
    when the tokens cannot be read."""
    try:
        from challenges_common import ChallengeTokenType
        from helpers import dependency
        from skeletons.gui.shared import IItemsCache
        tokens = dependency.instance(IItemsCache).items.tokens.getTokens()
        series_tokens = [(item.challengeID, {
            'active': item.getTokenID(ChallengeTokenType.ACTIVE),
            'attempts': item.getTokenID(ChallengeTokenType.ATTEMPT),
            'quests': item.getTokenID(ChallengeTokenType.QUEST),
            'wins': item.getTokenID(ChallengeTokenType.WIN),
        }) for item in items]
        return crucible.read_tokens(series_tokens, tokens)
    except Exception:
        logger.exception('Failed to read the Crucible tokens; asking the controller')
    progress = {}
    for item in items:
        try:
            progress[item.challengeID] = dict(controller.getChallengeProgress(item.challengeID) or {})
        except Exception:
            logger.exception('Failed to read the progress of a Crucible series')
    return _read(controller, 'activeChallengeID', 0, logger), progress


def _counted_bonus_types(items, conditions, logger):
    """The battle types that count for a series: the current mission's, or with no active series,
    those of the first mission of each series the player can see."""
    if conditions:
        return crucible.pre_battle(conditions)['bonusTypes']
    found = set()
    for item in items:
        try:
            quest_id = list(item.questsIDs or ())[0]
        except (IndexError, TypeError):
            continue
        if quest_id not in _bonus_types:
            quest = _find_quest(quest_id, logger)
            if quest is None:
                continue
            try:
                conditions_of_first = quest.getData().get('conditions') or []
            except Exception:
                logger.exception('Failed to read the conditions of %s', quest_id)
                continue
            _bonus_types[quest_id] = crucible.pre_battle(conditions_of_first)['bonusTypes']
        found.update(_bonus_types[quest_id])
    return sorted(found)


def _min_level():
    try:
        from challenges_common import CHALLENGE_MIN_VEHICLE_LEVEL
        return int(CHALLENGE_MIN_VEHICLE_LEVEL)
    except Exception:
        return crucible.MIN_VEHICLE_LEVEL


def _vehicles_in_battle(logger):
    """(intCD, name) of each vehicle that can play the Crucible and is in a battle now.

    "Can play" is the client's own rule, `getSuitableVehicles`: vehicles in the garage, of the
    Crucible tiers, and not event vehicles. A player can leave a battle and play another vehicle
    while the first battle runs on. The items cache updates when a vehicle comes back, and the
    banner refreshes on that. Which kind of battle it is comes from battle_record.
    """
    try:
        from gui.impl.lobby.challenges.views_helpers import getSuitableVehicles
        vehicles = getSuitableVehicles().values()
        return [(vehicle.intCD, vehicle.shortUserName) for vehicle in vehicles if vehicle.isInBattle]
    except Exception:
        logger.exception('Failed to list the vehicles in battle')
        return []


def _controller(logger):
    try:
        from helpers import dependency
        from skeletons.gui.challenges import IChallengesController
        return dependency.instance(IChallengesController)
    except Exception:
        logger.exception('Failed to reach the Crucible controller')
        return None


def _is_enabled(controller, logger):
    try:
        return bool(controller.isEnabled)
    except Exception:
        # The server settings are not there before the lobby is.
        logger.debug('The Crucible state cannot be read yet')
        return False


def _read(owner, name, default, logger):
    try:
        return getattr(owner, name)
    except Exception:
        logger.exception('Failed to read %s', name)
        return default


def _series_raw(item, active_id, progress_by_id, logger):
    """One series as plain data, or None when it cannot be read."""
    try:
        challenge_id = item.challengeID
        progress = dict(progress_by_id.get(challenge_id) or {})
        difficulty = item.difficulty
        return {
            'id': challenge_id,
            'name': item.name,
            'difficulty': getattr(difficulty, 'value', difficulty),
            'attempts': item.attempts,
            'allowedCompletions': item.allowedCompletions,
            'questCount': len(item.questsIDs or ()),
            'progress': progress,
            'isActive': bool(active_id) and challenge_id == active_id,
            # The client's own end: its Crucible banner and screen add one minute to finishTime.
            'endTime': int(item.finishTime or 0) + 60 if item.finishTime else 0,
            'expiringSoon': bool(item.isExpiringSoon),
            'restartPrice': dict(item.restartPrice or {}),
            'restartCostText': _cost_text(item.restartPrice, logger),
            'freeRestarts': _free_restarts(item, logger),
        }
    except Exception:
        logger.exception('Failed to read a Crucible series')
        return None


def _cost_text(price, logger):
    """The restart price, with the digit grouping the client uses for money."""
    found = crucible.restart_price(dict(price or {}))
    if found is None:
        return ''
    try:
        from gui.impl import backport
        return backport.getIntegralFormat(found[1])
    except Exception:
        logger.exception('Failed to write the restart price')
        return str(found[1])


def _free_restarts(item, logger):
    """The free restarts left, as the client's own Crucible screen counts them."""
    try:
        return max(0, int(item.freeRestartsPerCompletion or 0) - int(item.usedFreeRestarts or 0))
    except Exception:
        logger.exception('Failed to read the free restarts')
        return 0


def server_time_offset():
    """Seconds to add to the client clock for the server time, as premium-time does it.

    The JavaScript counts the time left down against its own clock, and the end times are server
    times. `getServerUTCTime` is the clock the client's own Crucible screen counts against. A whole
    number, because a fraction makes no difference to a countdown in seconds.
    """
    import time
    try:
        from helpers import time_utils
        server_now = float(time_utils.getServerUTCTime())
    except Exception:
        return 0
    return int(round(server_now - time.time()))


def award_name(record_id):
    """The dossier record name of an award, the same in every language, or None.

    A Crucible mission names an award by its record ID. The client's own condition text reads
    the name the same way (ChallengeAchievementsFormatter).
    """
    try:
        from dossiers2.custom.records import DB_ID_TO_RECORD
        return DB_ID_TO_RECORD[int(record_id)][1]
    except Exception:
        return None


def _mission(item, progress, logger):
    """The current mission of the active series, as (mission, conditions), or (None, None)."""
    stage = int((progress or {}).get('quests') or 0)
    quest_ids = list(item.questsIDs or ())
    if not 1 <= stage <= len(quest_ids):
        return None, None
    return _quest_mission(quest_ids[stage - 1], logger)


def _quest_mission(quest_id, logger):
    """One mission as (mission, conditions), or (None, None) when its quest is not there yet."""
    cached = _missions.get(quest_id)
    if cached is not None:
        return cached
    quest = _find_quest(quest_id, logger)
    if quest is None:
        return None, None
    try:
        # Plain lists, also for the sets of the client: the battle transport goes to a JSON file.
        conditions = crucible.plain(quest.getData().get('conditions') or [])
    except Exception:
        logger.exception('Failed to read the conditions of %s', quest_id)
        return None, None
    group, shapes = crucible.post_battle(conditions, award_name)
    mission = {
        'questID': quest_id,
        'group': group,
        'rows': crucible.mission_rows(_packed_items(quest, logger), shapes),
        'levels': crucible.pre_battle(conditions)['levels'],
    }
    _missions[quest_id] = (mission, conditions)
    logger.info('Crucible mission %s: %s group of %d condition(s), live %s', quest_id, group,
                len(mission['rows']), [row['live'] for row in mission['rows']])
    return mission, conditions


def _find_quest(quest_id, logger):
    try:
        from helpers import dependency
        from skeletons.gui.server_events import IEventsCache
        quests = dependency.instance(IEventsCache).getHiddenQuests(lambda quest: quest.getID() == quest_id)
        return quests.get(quest_id)
    except Exception:
        logger.exception('Failed to find the quest %s', quest_id)
        return None


def _packed_items(quest, logger):
    """The client's own rows for the post-battle conditions: title, text and icon key."""
    try:
        from gui.impl.gen.view_models.common.missions.challenge_mission_model import ChallengeMissionModel
        from gui.shared.missions.packers.conditions import ChallengePostBattleConditionPacker
        model = ChallengeMissionModel()
        ChallengePostBattleConditionPacker().pack(quest, model.postBattleCondition)
        # The native model writes itself out as JSON.
        data = json.loads(str(model))
    except Exception:
        logger.exception('Failed to pack the conditions of %s', quest.getID())
        return []
    items = (data.get('postBattleCondition') or {}).get('items') or []
    return [item for item in items if isinstance(item, dict)]


def _vehicle_level(logger):
    try:
        from CurrentVehicle import g_currentVehicle
        if not g_currentVehicle.isPresent():
            return None
        return g_currentVehicle.item.level
    except Exception:
        logger.exception('Failed to read the tier of the vehicle in the garage')
        return None


def account_dbid():
    try:
        from gui.shared.utils import getPlayerDatabaseID
        return getPlayerDatabaseID()
    except Exception:
        return None
