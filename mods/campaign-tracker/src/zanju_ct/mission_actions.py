# -*- coding: utf-8 -*-
"""Pauses, resumes and resets a campaign's active mission.

The client already has a processor for each of these, and each one carries its own validators
and its own confirmation dialog. This module builds the processor and asks it to run. Nothing
here talks to the server, and nothing here decides whether the player may do the thing: the
processor refuses on its own and says why, in the game's own system message.

That is also why a reset needs no confirmation of ours. `PMDiscard` carries
`PMDiscardConfirmator`, so the game raises its own dialog and the reset only happens if the
player accepts it.

Only one operation allows either action. The client keeps the list in
`gui.server_events.pm_constants`, where `PAUSABLE_OPERATIONS_IDS` and
`DISCARDABLE_OPERATIONS_IDS` both hold operation 7 alone -- Object 279 (e), the last operation
of campaign 2. The lists are read from the client rather than copied here, so a client that
opens this up to more operations opens this mod up with it.

Every client import stays inside a function, so this module is importable outside the game.
"""
from __future__ import absolute_import, print_function, unicode_literals

# What a badge click asks for. `OPEN` is the plain click and is handled by `navigation`; the
# other two are handled here.
ACTION_OPEN = 'open'
ACTION_PAUSE = 'pause'
ACTION_RESET = 'reset'


def read_actions(quest, has_progress, logger):
    """Which of the two actions this mission accepts, as the widget's own flags.

    Mirrors the rules the client uses for its own pause and reset buttons
    (`missions_helper.__getBtnStates`): the mission has to be unlocked, running and available,
    its operation has to allow the action, and campaign 3 must not be the active campaign.
    Reset asks one thing more, which is that there is progress to throw away.

    Any failure to answer counts as "not allowed": offering an action the game would refuse is
    worse than offering nothing.
    """
    blank = {'canPause': False, 'canReset': False, 'paused': False}
    try:
        from gui.server_events.pm_constants import (
            DISCARDABLE_OPERATIONS_IDS, PAUSABLE_OPERATIONS_IDS)

        if not _is_running(quest) or _is_campaign_3_active(logger):
            return blank

        operation_id = quest.getOperationID()
        return {
            'canPause': operation_id in PAUSABLE_OPERATIONS_IDS,
            'canReset': operation_id in DISCARDABLE_OPERATIONS_IDS and bool(has_progress),
            'paused': bool(quest.isOnPause),
        }
    except Exception:
        logger.exception('Failed to read which actions mission %s accepts',
                         _mission_id(quest, logger))
        return blank


def _is_running(quest):
    """Unlocked, selected, and with nothing standing in the way of playing it."""
    if not quest.isUnlocked() or not quest.isInProgress():
        return False
    # `isAvailable` answers with a result that is both truthy-testable and carries the reason.
    # Only the answer matters here, because the reason is for a message this mod does not show.
    available = quest.isAvailable()
    return bool(available[0] if isinstance(available, tuple) else available)


def _is_campaign_3_active(logger):
    """Campaign 3 being the active one blocks both actions, the way the client blocks them.

    Campaigns 1 and 2 have no badge while campaign 3 runs, so this is close to unreachable. It
    is kept because it is the client's own condition, and because the two campaign styles have
    swapped over before.
    """
    try:
        from helpers import dependency
        from personal_missions import PM_BRANCH
        from skeletons.gui.server_events import IEventsCache
        missions = dependency.instance(IEventsCache).getPersonalMissions()
        name = PM_BRANCH.TYPE_TO_NAME[PM_BRANCH.PERSONAL_MISSION_3]
        return name in (missions.getActiveCampaigns() or ())
    except Exception:
        logger.exception('Failed to read which campaign is active; actions stay hidden')
        return True


def perform(quest, action, logger):
    """Hand this mission to the processor for `action`. Returns True when the request went.

    Takes the mission rather than the campaign behind the badge, which keeps this module free
    of `collector` -- `collector` asks this one which actions a mission accepts, and two
    modules that import each other cannot both be imported first.
    """
    if action not in (ACTION_PAUSE, ACTION_RESET):
        logger.warning('No such mission action: %s', action)
        return False

    try:
        from gui.shared.gui_items.processors import quests as quests_proc
        # The branch comes off the mission rather than from the badge: this call wants the
        # branch number, while the badge carries the branch name, and the two are easy to
        # confuse. The mission knows its own.
        branch = quest.getQuestBranch()
        if action == ACTION_PAUSE:
            processor = quests_proc.PMPause(quest, not quest.isOnPause, branch)
        else:
            processor = quests_proc.PMDiscard(quest, branch)
        _request(processor, action, logger)
        return True
    except Exception:
        logger.exception('Failed to %s mission %s', action, _mission_id(quest, logger))
        return False


def _request(processor, action, logger):
    """Run a processor and show its answer, the way the game's own mission screen does.

    The request is asynchronous, and `adisp_process` is what the client wraps these in: it
    drives the generator and puts the lobby into its updating state while the server answers.

    The processor's own message is shown unchanged, so a refusal reads the same here as it
    does on the mission screen. The one message held back is the "wrong operation" refusal,
    which is what the client holds back too -- it means the mod offered something this
    operation does not allow, which is a fault to log rather than to show a player.
    """
    from gui import SystemMessages
    from gui.server_events.pm_constants import PM_SUIT_OP_PLUGIN_ERR_RESPONSE
    from gui.shared.utils import decorators

    @decorators.adisp_process('updating')
    def run():
        result = yield processor.request()
        message = getattr(result, 'userMsg', None)
        if not message:
            return
        if PM_SUIT_OP_PLUGIN_ERR_RESPONSE in message:
            logger.warning('The client refused to %s this mission: wrong operation', action)
            return
        SystemMessages.pushMessage(message, type=result.sysMsgType)

    run()


def _mission_id(quest, logger):
    try:
        return quest.getID()
    except Exception:
        logger.exception('Failed to read a mission id')
        return '?'
