# -*- coding: utf-8 -*-
"""Which campaigns exist, and which mission in one accepts a given vehicle.

The client's vocabulary, the three campaigns and how each one classifies vehicles are in
docs/reference/personal-missions.md. What matters here is that the classifiers never overlap
inside a campaign, so one vehicle matches at most one line and therefore at most one active
mission per campaign.

This module holds no client imports at module scope, so its logic can be tested outside the
game. The objects it is given are the client's own -- it asks them questions instead of
reproducing what they know.
"""
from __future__ import absolute_import, print_function, unicode_literals

# Client branch names, in the order the campaigns are numbered in game.
BRANCH_REGULAR = 'regular'
BRANCH_PM2 = 'pm2'
BRANCH_PM3 = 'pm3'

BRANCH_ORDER = (BRANCH_REGULAR, BRANCH_PM2, BRANCH_PM3)

# Shown on the widget face, because "campaign 2" is how players name these, and a numeral
# stays readable at the size a minimal widget gives it.
BRANCH_NUMERALS = {
    BRANCH_REGULAR: 'I',
    BRANCH_PM2: 'II',
    BRANCH_PM3: 'III',
}

# Separators the game puts between a mission's line name and its number. A plain hyphen is
# what every language shipped with client 2.3.1.3 uses; the rest are the dashes a later
# translation could reasonably substitute, listed so one does not defeat the split.
_ID_SEPARATORS = ('-', '‑', '–', '—', '−')

# A line name at or below this length is already an abbreviation and is left alone. Campaign 1
# ships as LT / MT / HT / TD / SPG, which is exactly the form the other two get shortened to.
_KEEP_STEM_LENGTH = 3
_ABBREVIATED_LENGTH = 2


def order_branches(active_names):
    """Sort the server's active-campaign report into campaign order, dropping what we cannot name.

    The report is a plain list of branch names and its order is not guaranteed, while the
    widgets have to stack in a stable order across garage visits. A name this module does not
    know is a campaign added after this version, which is skipped rather than guessed at.
    """
    known = set()
    for name in active_names or ():
        text = _as_text(name)
        if text in BRANCH_NUMERALS:
            known.add(text)
    return [name for name in BRANCH_ORDER if name in known]


def numeral(branch_name):
    return BRANCH_NUMERALS.get(branch_name, '')


def level_fits(level, min_level, max_level):
    """Whether a vehicle tier is inside a mission's tier range.

    The client's own vehicle search tests the minimum only, but a mission carries a maximum as
    well, so both are tested here. An unreadable bound is treated as no bound: a mission is
    better reported with one limit unchecked than dropped from the widget.
    """
    if level is None:
        return False
    if min_level is not None and level < min_level:
        return False
    if max_level is not None and level > max_level:
        return False
    return True


def accepts_vehicle(quest, vehicle_type, level):
    """Whether this mission accepts the vehicle: the right line, and inside the tier range.

    `vehicle_type` is the vehicle descriptor's type, which is what the client's own
    classifiers read. Any failure to answer counts as "does not accept": a widget that names
    the wrong mission is worse than one that names none.
    """
    try:
        classifier = quest.getQuestClassifier()
        if classifier is None or not classifier.matchVehicle(vehicle_type):
            return False
        return level_fits(level, quest.getVehMinLevel(), quest.getVehMaxLevel())
    except Exception:
        return False


def find_matching_mission(quests, vehicle_type, level):
    """The first mission in `quests` that accepts this vehicle, or None.

    At most one can match, because the lines of one campaign never overlap. The loop still
    stops at the first hit rather than asserting that, so a future campaign with overlapping
    lines gives a mission instead of an error.
    """
    for quest in quests or ():
        if accepts_vehicle(quest, vehicle_type, level):
            return quest
    return None


def build_mission_id(short_name, line_name=None, internal_id=None):
    """The compact mission label the widget face carries, such as `LT-1` or `UN-15`.

    The game already names a mission twice: a full name ("Union-10. Raise the Flag!") and a
    short one ("Union-10"). The short one comes from `PersonalMission.getShortUserName()` and
    it is translated, so it is the right thing to start from -- and the reason nothing here
    hardcodes a line name.

    Campaign 1 already ships short enough (`LT-1`, `SPG-13`). Campaigns 2 and 3 spell their
    line out (`Union-10`, `Vanguard-1`), which is too wide for a small banner, so the line part
    is cut to two letters and the number is kept whole.

    Falls back to the line name and the mission's number in the chain when the short name is
    missing, so a translation that has not shipped one still gives the banner something to say.
    """
    shortened = _shorten_mission_id(_as_text(short_name))
    if shortened:
        return shortened

    number = _as_text(internal_id).strip()
    stem = _abbreviate_stem(_as_text(line_name).strip())
    if stem and number:
        return '{0}-{1}'.format(stem, number)
    return stem or number


def _shorten_mission_id(text):
    """Cut the line part of a short mission name to two letters, keeping the number.

    Returns '' for anything that is not of the "line, separator, number" shape -- an empty
    string, or a reference the client failed to translate (which comes back starting with the
    `#domain:key` marker it was asked to resolve). A name with no separator in it is returned
    whole rather than cut: the shape is not what this expects, and the game's own short name
    is a better guess than two letters of it.
    """
    text = text.strip()
    if not text or text.startswith('#'):
        return ''

    index = max(text.rfind(separator) for separator in _ID_SEPARATORS)
    if index <= 0:
        return text

    stem = _abbreviate_stem(text[:index])
    return stem + text[index:] if stem else text


def _abbreviate_stem(stem):
    """Two uppercase letters, unless the name is already an abbreviation.

    "Already an abbreviation" is either short enough to keep whole, or written without
    lowercase letters. Both tests are needed: `SPG` passes on length, and a translation that
    spells a line in capitals passes on case.
    """
    stem = stem.strip()
    if not stem:
        return ''
    if len(stem) <= _KEEP_STEM_LENGTH or stem == stem.upper():
        return stem
    return stem[:_ABBREVIATED_LENGTH].upper()


def pace(current, goal, battles_used, battles_allowed):
    """Where the running total stands against the average the mission asks for, as a percentage.

    Missions of the "reach a total inside N battles" kind carry one constant average: 25 hits in
    10 battles is 2.5 a battle, and it stays 2.5 whatever the player does. That average expects 5
    hits by the second battle, so a player with 6 stands at 120 percent of it and one with 4
    stands at 80.

    The percentage is the whole reading. 100 is exactly on the average, and one number answers
    what the raw totals cannot: 6 of 25 says nothing about whether 6 is enough by now.

    Returns `percent` and `ahead` (whether the total is at or above the average). None when there
    is no useful answer: nothing played yet, the total is already reached, or no battles are
    left to reach it in.
    """
    if None in (current, goal, battles_used, battles_allowed):
        return None
    if goal <= 0 or battles_allowed <= 0 or current >= goal:
        return None
    # Nothing played yet, so there is nothing to measure against the average.
    if battles_used <= 0:
        return None
    if battles_allowed - battles_used <= 0:
        return None

    return {
        # Cross-multiplied rather than divided twice, so the percentage is exact. Rounded down
        # rather than to the nearest, which keeps it and `ahead` from ever disagreeing: the
        # reading reaches 100 exactly when the total is on the average, and not a step earlier.
        'percent': int(current * battles_allowed * 100 // (goal * battles_used)),
        'ahead': current * battles_allowed >= goal * battles_used,
    }


def _as_text(value):
    if value is None:
        return u''
    try:
        return value if isinstance(value, type(u'')) else u'{0}'.format(value)
    except Exception:
        return u''
