# -*- coding: utf-8 -*-
"""Condition progress for one mission, as plain rows the widget can render.

The client keeps a mission's conditions in a `LobbyProgressStorage`, built from the mission's
condition config and the player's saved progress. This is the same object the game's own
mission card and mission tooltip build, so the numbers here are the numbers the game shows.

Each row is one condition: its text, how far the player is, and whether it is done. Rows come
back in the client's own order, which puts the main conditions first.

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


def read_conditions(quest, logger):
    """Condition rows for this mission, main conditions first. Empty when they cannot be read."""
    storage = _build_storage(quest, logger)
    if storage is None:
        return []

    try:
        progresses = storage.getBodyProgresses()
        ordered = storage.sortProgresses(progresses.itervalues())
    except Exception:
        logger.exception('Failed to read the conditions of mission %s', _mission_id(quest))
        return []

    rows = []
    for progress in ordered:
        row = _read_row(progress, logger)
        if row is not None:
            rows.append(row)
    return rows


def _build_storage(quest, logger):
    try:
        from gui.server_events.personal_progress.storage import LobbyProgressStorage
    except Exception:
        logger.exception('The client has no lobby progress storage; conditions stay hidden')
        return None

    _check_states(logger)
    try:
        return LobbyProgressStorage(
            quest.getGeneralQuestID(),
            quest.getConditionsConfig(),
            quest.getConditionsProgress(),
            quest.isOneBattleQuest(),
        )
    except Exception:
        logger.exception('Failed to build the progress storage for mission %s', _mission_id(quest))
        return None


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
