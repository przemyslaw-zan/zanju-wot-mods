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

import re

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
        return {'conditions': [], 'attempts': [], 'vehicles': None, 'hasProgress': False,
                'stage': ''}
    return {
        'conditions': _read_conditions(storage, quest, logger),
        'attempts': _read_attempts(storage, quest, logger),
        'vehicles': _read_vehicles(storage, quest, vehicle_cd, logger),
        'hasProgress': _has_progress(storage, quest, logger),
        'stage': _mission_stage(storage, quest, logger),
    }


# What a mission is still worth playing for once its primary objective is settled. Both are
# states the client names itself, and both are empty for a mission still working on its primary
# objective. The widget uses the value as an icon name and as a label key, so these two strings
# are also CSS class suffixes and i18n keys.
STAGE_IMPROVING = 'improving'
STAGE_PAWNED = 'pawned'


def _mission_stage(storage, quest, logger):
    """`STAGE_PAWNED`, `STAGE_IMPROVING`, or an empty string for every other mission.

    The two differ in what the remaining battles buy, which is why the client keeps them apart:

    - **pawned** -- an order was committed to fulfil the primary condition. The mission counts
      as complete and its main reward is paid, but the condition itself was never met. Meeting
      both conditions in one battle returns the order.
    - **improving** -- the player met the primary condition in a battle. Meeting both in one
      battle completes the mission with honors and pays the secondary reward.

    Pawned is tested first, the way the client's own status panel tests it. `areTokensPawned`
    is defined as `isMainCompleted` and a pawned progress, so a pawned mission answers yes to
    the improving test as well.

    `isMainCompleted` is asked rather than `isCompleted`. The client defines that one as main
    OR full, so it cannot tell the two states apart. A mission with no secondary objective is
    never improving: nothing is left to improve once the primary objective is met.
    """
    try:
        if quest.isFullCompleted():
            # Both objectives are met, so there is nothing left to play this mission for.
            return ''
        if quest.areTokensPawned():
            return STAGE_PAWNED
        if not quest.isMainCompleted():
            return ''
        if not _has_conditions(storage, True) or not _has_conditions(storage, False):
            return ''
        return STAGE_IMPROVING
    except Exception:
        logger.exception('Failed to read what mission %s is still played for',
                         _mission_id(quest))
        return ''


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
    """One row per objective, saying how many battles it has to be met in. Main first.

    An objective with no limit has no header progress at all, and the client fills that gap
    itself with an "over any number of battles" line. This does the same, in the client's own
    words, because the absence of a limit is worth saying: it is the difference between a
    mission to work at and one that fails if it is not done in time.

    It also keeps the objectives in step. Without a row of its own an unlimited primary was
    skipped, and everything that reads "the first unfinished objective" -- the banner's counter
    most visibly -- silently answered with the secondary one instead.
    """
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

    for is_main in (True, False):
        if any(row['main'] is is_main for row in rows):
            continue
        row = _unlimited_attempt(storage, quest, is_main, logger)
        if row is not None:
            rows.append(row)
    # Main first again, now that the unlimited rows have joined them.
    rows.sort(key=(lambda row: not row['main']))
    return rows


def _unlimited_attempt(storage, quest, is_main, logger):
    """A row for an objective the client gives no header progress of its own, or None.

    Two missions arrive here and they want different things said:

    - **No battle limit.** The client fills the gap with its own "over any number of battles"
      line, and so does this.
    - **One battle.** There is no budget to describe at all, and the client draws nothing. The
      row is still built, with no text of its own.

    The row is built either way because it does a second job. The banner reads the objectives
    to know which one it is counting, and an objective with no row sends the counter to the
    other half of the mission.

    A mission need not have a secondary objective at all, and one that does not should say
    nothing about it rather than claim it is unlimited.
    """
    try:
        if not _has_conditions(storage, is_main):
            return None
        return {
            'text': _unlimited_label(quest, is_main),
            # No shape, no numbers: there is no limit here to count against. Every reader
            # tests for these before using them.
            'type': None,
            'current': None,
            'goal': None,
            'battles': [],
            'done': bool(quest.isFullCompleted() if not is_main else quest.isCompleted()),
            'failed': False,
            'main': bool(is_main),
        }
    except Exception:
        logger.exception('Failed to read the unlimited-battles line of mission %s',
                         _mission_id(quest))
        return None


def _unlimited_label(quest, is_main):
    """The client's "over any number of battles" line, or nothing for a one-battle mission.

    `isOneBattleQuest` is the client's own test, and the same one it gates this line with:
    `getDummyHeaderType` answers `DISPLAY_TYPE.NONE` for exactly these missions, and a header
    typed NONE draws nothing.
    """
    if quest.isOneBattleQuest():
        return ''
    from gui.Scaleform.locale.PERSONAL_MISSIONS import PERSONAL_MISSIONS
    from helpers import i18n
    key = (PERSONAL_MISSIONS.CONDITIONS_UNLIMITED_LABEL_MAIN if is_main
           else PERSONAL_MISSIONS.CONDITIONS_UNLIMITED_LABEL_ADD)
    return i18n.makeString(key)


def _has_conditions(storage, is_main):
    """Whether this objective has any condition at all."""
    for progress in storage.getBodyProgresses().itervalues():
        if bool(progress.isMain()) is bool(is_main):
            return True
    return False


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


def _format_count(value, logger):
    """A condition's number, grouped the way the client groups numbers in its own screens.

    Left to the client rather than done here, because the separator belongs to the language:
    a space, a comma or a dot depending on where the player is.
    """
    if value is None:
        return ''
    try:
        from gui.impl import backport
        return backport.getNiceNumberFormat(value)
    except Exception:
        logger.exception('Failed to format a condition number; showing it plain')
        return '{0}'.format(value)


def _read_row(progress, logger):
    try:
        state = progress.getState()
        current = progress.getCurrent()
        goal = progress.getGoal()
        text, restriction_label, restriction = _split_restriction(progress, logger)
        return {
            'text': text,
            # The extra rule this condition carries, if it carries one, split off the
            # description and given a line of its own by the widget.
            'restrictionLabel': restriction_label,
            'restriction': restriction,
            # A binary condition ("Survive the battle") has a goal of 1 and no useful counter,
            # so the widget shows a tick for it instead of "0 / 1". Which of the two it is comes
            # from the client's own cumulative flag rather than from the numbers.
            'counted': bool(progress.isCumulative()),
            'current': current,
            'goal': goal,
            # The same numbers written out, because a mission asking for 15000 assistance
            # damage reads as a wall of digits without grouping. Both are kept: the widget
            # renders the text, and the pace maths needs the numbers.
            'currentText': _format_count(current, logger),
            'goalText': _format_count(goal, logger),
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


# The client's own markup, which is Scaleform HTML the widget document cannot render. It comes
# out of the restriction, which is the one place the client puts any.
_MARKUP = re.compile(r'<[^>]+>')

# `&amp;` last, or it would undo the escaping of the ones replaced before it.
_ENTITIES = (('&lt;', '<'), ('&gt;', '>'), ('&quot;', '"'), ('&apos;', "'"),
             ('&nbsp;', ' '), ('&amp;', '&'))


def _split_restriction(progress, logger):
    """`(the condition, the restriction label, the restriction)`, the last two often empty.

    Some conditions carry a limiter: a second rule that has to hold before the first one counts
    at all. "Be the top player by vehicles destroyed" is a race against your own team, so it
    comes with "Destroy 2 enemy vehicles" to stop an empty scoreboard from meeting it.

    The client composes the two into one description, as `condition`, a newline, the word
    "Restriction!" in Scaleform markup, then the limiter. They are split back apart here
    because the widget cannot render that markup, and because two rules on one line read as one
    sentence.

    `getLimiter` decides whether there is a second part, rather than the newline alone: the
    client's own answer costs nothing and a description may hold a newline for its own reasons.
    The split itself takes the last newline, which is the one the client put there.

    Only the restriction is cleaned of markup. The condition above it carries none, and reading
    every description for markup the client does not put there buys nothing.
    """
    description = progress.getDescription() or ''
    try:
        limited = progress.getLimiter() is not None
    except Exception:
        # Worth keeping the row for: the description carries both parts either way, which is
        # what the client itself would draw.
        logger.exception('Failed to read whether a condition carries a restriction')
        limited = False

    if not limited or '\n' not in description:
        return description, '', ''

    text, restriction = description.rsplit('\n', 1)
    restriction = _plain(restriction)
    label = _restriction_label(logger)
    if label and restriction.startswith(label):
        # Carried apart so the widget can give the label its own colour, the way the client
        # colours it. A label that does not lead the line is left in place rather than cut out
        # of the middle of it.
        return text, label, restriction[len(label):].strip()
    return text, '', restriction


def _restriction_label(logger):
    """The client's own word for a limiter, which it writes in front of the limiter's text."""
    try:
        from gui.Scaleform.locale.PERSONAL_MISSIONS import PERSONAL_MISSIONS
        from helpers import i18n
        return i18n.makeString(PERSONAL_MISSIONS.CONDITIONS_LIMITER_LABEL)
    except Exception:
        logger.exception('Failed to read the label the client puts on a restriction')
        return ''


def _plain(text):
    """A restriction with the client's markup taken out, leaving the words it wrapped."""
    text = _MARKUP.sub('', text or '')
    for entity, character in _ENTITIES:
        text = text.replace(entity, character)
    return text.strip()


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
