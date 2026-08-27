# -*- coding: utf-8 -*-
"""Progress for one mission, as plain rows the widget can render.

The client keeps a mission's progress in a `LobbyProgressStorage`, built from the mission's
condition config and the player's saved progress. This is the same object the game's own
mission card and mission tooltip build, so the numbers here are the numbers the game shows.

It holds two kinds of row, and both are read here:

- **conditions** (the storage's *body* progresses) -- one per condition: its text, how far the
  player is, and whether it is done.
- **vehicles** -- the "complete it in N different vehicles" requirement campaign 3 uses, and
  which vehicles have already been spent on it. A vehicle that completes such a mission is
  locked out of it afterwards, so the list is what tells a player which tanks are still worth
  taking out.
- **attempts** (the storage's *header* progresses) -- the requirement over the conditions as a
  whole, which is where "complete the primary condition in 3 battles out of 5" lives. Campaign
  2 uses this most. A mission with no such requirement has no header progress at all, and then
  there is nothing to show: the game fills that gap with an "over any number of battles" line,
  which says nothing a player needs.

The whole read is optional. A mission with unreadable progress still gives its name, which is
the part the widget cannot do without, so a failure here empties the rows and keeps the rest.
"""
from __future__ import absolute_import, print_function, unicode_literals

# `constants.QUEST_PROGRESS_STATE`. Held as plain numbers because the row only needs to know
# "done" and "failed"; the constant is read in `_states()` to report a renumbering rather than
# to silently compare against the wrong value.
_STATE_FAILED = 3
_STATE_COMPLETED = 5
_STATE_PRELIMINARY_COMPLETED = 6

_states_checked = False


def read_progress(quest, logger, vehicle_cd=None):
    """Both row kinds for this mission. Either list is empty when it cannot be read.

    `vehicle_cd` is the compact descriptor of the tank in the garage, which is what says
    whether that tank is one of the ones this mission has already been completed in.
    """
    storage = _build_storage(quest, logger)
    if storage is None:
        return {'conditions': [], 'attempts': [], 'vehicles': None, 'hasProgress': False}
    return {
        'conditions': _read_conditions(storage, quest, logger),
        'attempts': _read_attempts(storage, quest, logger),
        'vehicles': _read_vehicles(storage, quest, vehicle_cd, logger),
        'hasProgress': _has_progress(storage, quest, logger),
    }


def _has_progress(storage, quest, logger):
    """Whether this mission has progress a reset would throw away.

    The client greys its own reset button out when there is none, and this is the same test:
    any progress that has started and is not already finished. Reading it here rather than
    from the mission is deliberate -- the answer lives in the progress objects, and the
    storage is the only place holding all of them.
    """
    try:
        progresses = storage.getProgresses() or {}
        return any(progress.hasProgressForReset() for progress in progresses.itervalues())
    except Exception:
        logger.exception('Failed to read whether mission %s has progress to reset',
                         _mission_id(quest))
        return False


def _read_conditions(storage, quest, logger):
    """One row per condition, main conditions first."""
    try:
        ordered = storage.sortProgresses(storage.getBodyProgresses().itervalues())
    except Exception:
        logger.exception('Failed to read the conditions of mission %s', _mission_id(quest))
        return []

    rows = []
    for progress in ordered:
        row = _read_row(progress, logger)
        if row is not None:
            rows.append(row)
    return rows


def _read_attempts(storage, quest, logger):
    """One row per repetition requirement, main first. Empty when the mission has none."""
    try:
        progresses = list(storage.getHeaderProgresses().itervalues())
    except Exception:
        logger.exception('Failed to read the attempts of mission %s', _mission_id(quest))
        return []

    rows = []
    # Main before additional. The client sorts body rows for us but leaves these to the caller.
    for progress in sorted(progresses, key=(lambda p: not _is_main(p))):
        row = _read_attempt(progress, logger)
        if row is not None:
            rows.append(row)
    return rows


def _read_vehicles(storage, quest, vehicle_cd, logger):
    """The different-vehicles requirement and the vehicles already used up, or None.

    A mission without the requirement reports zero required vehicles, and gets nothing. The
    count and the list come from two different places, which is the client's own arrangement:
    the progress objects carry how many vehicles are wanted, while the mission carries which
    ones have been spent. It is what the game's own campaign 3 tooltip reads.
    """
    required = _required_vehicles(storage, logger)
    if required <= 0:
        return None

    descriptors = _used_descriptors(quest, logger)
    used = _vehicle_names(descriptors, logger)
    return {
        'text': _required_vehicles_label(required, logger),
        'completed': min(len(descriptors), required),
        'required': required,
        'locked': used,
        # Whether the tank in the garage is one of the spent ones. The banner says so on its
        # face, because it is the one thing here that changes what the player should do next:
        # the mission is still theirs to finish, but not in this tank.
        'currentLocked': vehicle_cd is not None and vehicle_cd in descriptors,
    }


def _required_vehicles(storage, logger):
    """How many different vehicles the mission wants. Zero when it does not care."""
    required = 0
    try:
        for progress in storage.getProgresses().itervalues():
            required = max(required, progress.getUniqueVehicles() or 0)
    except Exception:
        logger.exception('Failed to read how many vehicles a mission needs')
    return required


def _used_descriptors(quest, logger):
    """Compact descriptors of the vehicles that already completed this mission.

    Sorted, the way the game's own tooltip sorts them, so the list keeps one order between
    reads rather than a set's.
    """
    try:
        progress = quest.getConditionsProgress() or {}
        return sorted(progress.get('battlesUniqueVehicles') or ())
    except Exception:
        logger.exception('Failed to read which vehicles already completed the mission')
        return []


def _vehicle_names(descriptors, logger):
    """Short names for those descriptors, dropping any the client cannot name."""
    if not descriptors:
        return []
    try:
        from helpers import dependency
        from skeletons.gui.shared import IItemsCache
        items = dependency.instance(IItemsCache).items
        names = []
        for descriptor in descriptors:
            item = items.getItemByCD(descriptor)
            if item is not None:
                names.append(item.shortUserName)
        return names
    except Exception:
        logger.exception('Failed to name the vehicles that already completed the mission')
        return []


def _required_vehicles_label(required, logger):
    """The client's own wording for the requirement, already translated."""
    try:
        from gui.Scaleform.locale.PERSONAL_MISSIONS_30 import PERSONAL_MISSIONS_30
        from helpers import i18n
        return i18n.makeString(
            PERSONAL_MISSIONS_30.CONDITIONS_REQUIREDVEHICLE_BOTTOMLABEL, count=required)
    except Exception:
        logger.exception('Failed to read the different-vehicles label')
        return ''


def _read_attempt(progress, logger):
    try:
        state = progress.getState()
        return {
            # Already translated, and free of the markup the matching bottom label carries.
            'text': progress.getHeaderLabel(),
            # Which shape the requirement takes: `biathlon` counts how many of a fixed run of
            # battles went well, `limited` allows a fixed run of battles to reach a total. The
            # numbers below mean different things in each, so the banner has to be told which.
            'type': progress.getDisplayType(),
            'current': progress.getCurrent(),
            'goal': progress.getGoal(),
            'battles': _read_battles(progress, state),
            'done': state in (_STATE_COMPLETED, _STATE_PRELIMINARY_COMPLETED),
            'failed': state == _STATE_FAILED,
            'main': bool(progress.isMain()),
        }
    except Exception:
        logger.exception('Failed to read a mission attempt requirement')
        return None


def _read_battles(progress, state):
    """One mark per allowed battle, for the requirements that cap how many there are.

    Only the "in N battles out of M" kind carries this -- the others have a count and no
    per-battle history, and get an empty list. The finished states paint every mark rather
    than the battles actually played, which is what the game's own card does.
    """
    limit_getter = getattr(progress, 'getBattlesLimit', None)
    if not callable(limit_getter):
        return []
    limit = limit_getter() or 0
    if limit <= 0:
        return []
    if state == _STATE_FAILED:
        return ['failed'] * limit
    if state in (_STATE_COMPLETED, _STATE_PRELIMINARY_COMPLETED):
        return ['done'] * limit

    played = progress.getProgress().get('battles') or []
    marks = []
    for index in range(limit):
        if index < len(played):
            marks.append('done' if played[index] else 'failed')
        else:
            marks.append('pending')
    return marks


def _is_main(progress):
    try:
        return bool(progress.isMain())
    except Exception:
        return False


def _build_storage(quest, logger):
    try:
        from gui.server_events.personal_progress.storage import LobbyProgressStorage
    except Exception:
        logger.exception('The client has no lobby progress storage; conditions stay hidden')
        return None

    _check_states(logger)
    try:
        storage = LobbyProgressStorage(
            quest.getGeneralQuestID(),
            quest.getConditionsConfig(),
            quest.getConditionsProgress(),
            quest.isOneBattleQuest(),
        )
    except Exception:
        logger.exception('Failed to build the progress storage for mission %s', _mission_id(quest))
        return None

    _mark_finished(storage, quest, logger)
    return storage


def _mark_finished(storage, quest, logger):
    """Tick the conditions of an objective the player has already met.

    A mission with a battle limit starts its conditions over every battle, so the storage only
    ever knows about the battle in progress. Read raw, a primary objective finished three
    battles ago still shows all of its conditions undone, which is the opposite of the truth.

    `markAsCompleted` is the client's own answer to this, and it takes the mission's completion
    flags rather than the storage's: the primary conditions are ticked once the mission counts
    as completed, the secondary ones once it counts as completed with honors.

    The client wraps that call in two further guards. One is kept and one is not:

    - **Kept:** a mission finished with an order never had its conditions met, so ticking them
      would credit the player with something they did not do.
    - **Dropped:** the client also skips one-battle missions that are still in progress. That
      guard suits a card describing the battle you are about to enter. It does not suit a banner
      describing where the mission stands, and a one-battle mission whose primary objective is
      met really did meet those conditions.
    """
    try:
        if quest.areTokensPawned():
            return
        storage.markAsCompleted(quest.isCompleted(), quest.isFullCompleted())
    except Exception:
        logger.exception('Failed to mark the finished conditions of mission %s',
                         _mission_id(quest))


def _read_row(progress, logger):
    try:
        state = progress.getState()
        current = progress.getCurrent()
        goal = progress.getGoal()
        return {
            'text': progress.getDescription(),
            # A binary condition ("Survive the battle") has a goal of 1 and no useful counter,
            # so the widget shows a tick for it instead of "0 / 1". Which of the two it is comes
            # from the client's own cumulative flag rather than from the numbers.
            'counted': bool(progress.isCumulative()),
            'current': current,
            'goal': goal,
            'done': state in (_STATE_COMPLETED, _STATE_PRELIMINARY_COMPLETED),
            'failed': state == _STATE_FAILED,
            'main': bool(progress.isMain()),
            # Conditions in an "or" group need only one of them done, which changes what the
            # list means; the widget marks them so an undone row does not read as outstanding.
            'alternative': bool(progress.isInOrGroup()),
        }
    except Exception:
        logger.exception('Failed to read a mission condition')
        return None


def _check_states(logger):
    """Report a renumbered progress state once, rather than comparing against a stale number."""
    global _states_checked
    if _states_checked:
        return
    _states_checked = True
    try:
        from constants import QUEST_PROGRESS_STATE
        actual = (
            QUEST_PROGRESS_STATE.FAILED,
            QUEST_PROGRESS_STATE.COMPLETED,
            QUEST_PROGRESS_STATE.PRELIMINARY_COMPLETED,
        )
    except Exception:
        return
    expected = (_STATE_FAILED, _STATE_COMPLETED, _STATE_PRELIMINARY_COMPLETED)
    if actual != expected:
        logger.warning(
            'The client renumbered the condition states to %s, not %s; '
            'conditions will show the wrong state', actual, expected)


def _mission_id(quest):
    try:
        return quest.getID()
    except Exception:
        return '?'
