# -*- coding: utf-8 -*-
"""Opens the client's own screen for a campaign's active mission.

The two campaign styles show a mission in different places, so a banner click lands in a
different screen depending on which campaign it belongs to:

- **Campaigns 1 and 2** (`regular`, `pm2`) give every mission its own screen. The mission is
  the thing to open, so this opens it by id. It is the same call the game makes when the
  player clicks a personal-missions flag in the garage header, which is the closest thing the
  client has to this widget.
- **Campaign 3** (`pm3`) has no per-mission screen. Its missions are a list, filtered by the
  category the line maps to, so the list is what opens.

Both entry points are the client's own dispatchers, and both refuse the navigation themselves
when the page cannot be opened (`canOpenPMPage`). That check is left to them rather than
reproduced here.

Every client import stays inside a function, so this module is importable outside the game.
"""
from __future__ import absolute_import, print_function, unicode_literals

from . import campaigns, collector


def open_mission(branch_name, logger):
    """Open the screen showing this campaign's active mission. Returns True when it went."""
    quest = collector.find_active_mission(branch_name, logger)
    if quest is None:
        # The banner is grey in this case and the JS does not offer the click, so this is only
        # reached when the mission went away between the render and the click.
        logger.info('Campaign %s has no active mission to open', branch_name)
        return False

    try:
        if branch_name == campaigns.BRANCH_PM3:
            return _open_mission_list(quest, logger)
        return _open_mission_page(quest, logger)
    except Exception:
        logger.exception('Failed to open the mission screen for campaign %s', branch_name)
        return False


def _open_mission_page(quest, logger):
    """Campaigns 1 and 2: the mission's own screen, addressed by mission id."""
    from gui.server_events.events_dispatcher import showPersonalMission
    mission_id = quest.getID()
    logger.info('Opening the screen for mission %s', mission_id)
    showPersonalMission(missionID=mission_id)
    return True


def _open_mission_list(quest, logger):
    """Campaign 3: the operation's mission list, filtered to this line's category.

    `showPersonalMissionsChain` takes a chain id as well, and ignores it for this campaign --
    the client's own caller passes 0 there. The real selector is the category, which the
    client maps from the same common role this mod already reads off the line's classifier.
    """
    from gui.impl.lobby.personal_missions_30.personal_mission_constants import (
        MISSIONS_ROLES_TO_CATEGORIES)
    from gui.server_events.events_dispatcher import showPersonalMissionsChain

    category = None
    classifier = quest.getQuestClassifier()
    if classifier is not None:
        category = MISSIONS_ROLES_TO_CATEGORIES.get(classifier.classificationAttr)
    if category is None:
        # Without a category the list opens unfiltered, which is still the right screen.
        logger.warning('No mission category for line %s; opening the list unfiltered',
                       getattr(classifier, 'classificationAttr', '?'))

    operation_id = quest.getOperationID()
    logger.info('Opening the mission list of operation %s, category %s',
                operation_id, category)
    showPersonalMissionsChain(operation_id, quest.getChainID(), category)
    return True
