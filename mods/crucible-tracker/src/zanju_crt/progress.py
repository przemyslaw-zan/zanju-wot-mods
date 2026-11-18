# -*- coding: utf-8 -*-
"""The progress of the current Crucible mission in one battle, from plain facts.

battle_session reads the client and hands this module plain numbers: a hit, a kill, the HP of the
player's vehicle, the start of the battle. The tracker turns them into the progress of each
condition, in the order of `crucible.condition_sets`. It has no client imports, so the tests run
it outside the game.

The server decides the mission from the battle results. The panel can only follow the events that
the client sees, so the figures here are an estimate. What each figure comes from, and where it
can differ from the result, is in docs/reference/crucible.md.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from . import crucible

# Ends of the progress of one condition.
OPEN = 'open'
MET = 'met'
# The condition can no longer be met in this battle: its time ran out, or the vehicle took
# damage before enough kills at full HP.
CLOSED = 'closed'


class Tracker(object):
    """The progress of every condition of one mission, for one battle."""

    def __init__(self, conditions, award_name=None):
        self.specs = []
        self.set_of = []
        for index, conditions_of_set in enumerate(crucible.condition_sets(conditions)):
            for name, value in conditions_of_set:
                self.specs.append(crucible.parse_condition(name, value, award_name))
                self.set_of.append(index)
        self.totals = dict((key, 0) for key in crucible.LIVE_RESULT_KEYS)
        # Not a result key: the kills of enemies that damaged the player's vehicle, for Duelist.
        self.totals['killsOfAttackers'] = 0
        self.killed = set()
        self.attackers = set()
        # What each damage or kill condition counted. Only those count each hit by its own rules.
        self.counted = [0] * len(self.specs)
        # The vehicle classes of the kills that each kill condition counted.
        self.kill_classes = [set() for _ in self.specs]
        self.health = None
        self.max_health = None
        self.full_health = True
        self.battle_start = None
        # The total HP of the enemy team at the start, for an award that asks for a share of it.
        self.enemy_health = None
        # Whether a direct shot of the player hit an ally, which ends an award with `noAllyHits`.
        self.ally_hit = False
        # The attack reason of the last hit of the player on each enemy, so a kill can be told
        # by its reason. The client kill event carries none.
        self.last_reason = {}
        # The enemies that the player spotted. Each one counts once.
        self.spotted = set()

    @property
    def set_count(self):
        return (self.set_of[-1] + 1) if self.set_of else 0

    # -- facts --------------------------------------------------------------------------------

    def add_result(self, key, amount):
        """Add to a result figure that the client reports per event, such as the assisted damage."""
        if key in self.totals and amount:
            self.totals[key] += amount

    def raise_results(self, values):
        """Take the totals of the client's battle summary where they are higher.

        The server sends the summary after a reconnect, so it restores what the events before the
        reconnect added. It is never lower than the events while the client was connected.
        """
        for key, value in values.items():
            if key in self.totals and value is not None and value > self.totals[key]:
                self.totals[key] = value

    def set_battle_start(self, server_time):
        self.battle_start = server_time

    def set_enemy_health(self, total):
        if total:
            self.enemy_health = total

    def set_health(self, health, max_health):
        """The HP of the player's vehicle now. The drop since the last reading is damage received."""
        if max_health:
            self.max_health = max_health
        if health is None:
            return
        health = max(0, health)
        if self.health is None:
            # The first reading: a reconnect can start with a vehicle that already lost HP.
            before = self.max_health if self.max_health else health
        else:
            before = self.health
        if health < before:
            self.totals['damageReceived'] += before - health
        self.health = health
        if self.max_health and health < self.max_health:
            self.full_health = False

    def on_damage(self, target_id, amount, reason, distance=None, view_range=None, server_time=None):
        """The player hit an enemy for `amount` HP, by fire and ramming too.

        `distance` is the distance to the target in metres, or None when the target is not in
        the client's world. `view_range` is the view range of the player's vehicle in metres.
        """
        self.last_reason[target_id] = reason
        self.totals['damageDealt'] += amount
        for index, spec in enumerate(self.specs):
            if spec['kind'] != crucible.KIND_DAMAGE or not spec['live'] or not _reason_counts(spec, reason):
                continue
            if not self._in_time(spec, server_time) or not _in_range(spec, distance, view_range):
                continue
            self.counted[index] += 1 if spec['eventCount'] else amount

    def on_spot(self, target_id):
        """The player spotted an enemy. The battle results count each enemy once, so a second
        event for the same enemy adds nothing."""
        if target_id in self.spotted:
            return False
        self.spotted.add(target_id)
        self.totals['spotted'] += 1
        return True

    def on_damaged_by(self, attacker_id):
        """A vehicle damaged the player's vehicle: its HP, or a module."""
        self.attackers.add(attacker_id)
        self._count_attackers_killed()

    def _count_attackers_killed(self):
        # The kills and the damage in any order: the server judges the award after the battle.
        self.totals['killsOfAttackers'] = len(self.killed & self.attackers)

    def on_ally_hit(self):
        """A direct shot of the player hit an ally, with or without damage."""
        self.ally_hit = True

    def on_kill(self, target_id, vehicle_class):
        """The player destroyed an enemy of this vehicle class, by any means.

        The kill event has no attack reason. A condition that names a reason takes the reason of
        the player's last hit on that enemy.
        """
        self.totals['kills'] += 1
        self.killed.add(target_id)
        self._count_attackers_killed()
        reason = self.last_reason.get(target_id)
        for index, spec in enumerate(self.specs):
            if spec['kind'] != crucible.KIND_KILLS or not spec['live'] or not _reason_counts(spec, reason):
                continue
            if spec['fullHealth'] and not self.full_health:
                continue
            if spec['classes'] and vehicle_class not in spec['classes']:
                continue
            self.counted[index] += 1
            if vehicle_class in crucible.VEHICLE_CLASSES:
                self.kill_classes[index].add(vehicle_class)

    # -- progress -----------------------------------------------------------------------------

    def _in_time(self, spec, server_time):
        limit = spec.get('timeLimit')
        if limit is None or self.battle_start is None or server_time is None:
            return True
        return server_time - self.battle_start <= limit

    def value(self, index):
        spec = self.specs[index]
        if spec.get('diversity'):
            return self._diverse_kills(index)
        if spec['kind'] in (crucible.KIND_DAMAGE, crucible.KIND_KILLS):
            return self.counted[index]
        return sum(self.totals.get(key, 0) for key in spec.get('keys') or ())

    def _diverse_kills(self, index):
        """The kills that bring a condition with different classes closer.

        The kills that the condition still needs must cover the classes that it still needs. Thus a
        kill of a class that the kills already have counts only while enough kills are left for the
        missing classes. For 2 kills of 2 classes, a second heavy tank does not count. For 3 kills
        of 2 classes, it does. When the kills cover enough classes, every kill counts, also past
        the target, as in the other kill conditions.
        """
        spec = self.specs[index]
        kills = self.counted[index]
        missing = spec['diversity'] - len(self.kill_classes[index])
        if missing <= 0:
            return kills
        return max(0, min(kills, int(spec['target']) - missing))

    def classes(self, index):
        """The vehicle classes of the counted kills, in the order of the client's class filters."""
        return [name for name in crucible.VEHICLE_CLASSES if name in self.kill_classes[index]]

    def target(self, index):
        spec = self.specs[index]
        if spec['kind'] == crucible.KIND_HEALTH_MULTIPLE:
            return spec['multiplier'] * self.max_health if self.max_health else None
        if spec.get('enemyHealthShare'):
            if not self.enemy_health:
                return None
            return max(spec.get('minimum') or 0, spec['enemyHealthShare'] * self.enemy_health)
        return spec.get('target')

    def deadline(self, index):
        """The server time that a time-limited condition stops counting at, or None."""
        limit = self.specs[index].get('timeLimit')
        if limit is None or self.battle_start is None:
            return None
        return self.battle_start + limit

    def condition(self, index, now):
        """The progress of one condition: value, target, state and the time limit."""
        spec = self.specs[index]
        target = self.target(index) if spec['live'] else None
        if target is None:
            return {'live': False, 'state': OPEN, 'set': self.set_of[index]}
        value = self.value(index)
        deadline = self.deadline(index)
        if spec.get('noAllyHits') and self.ally_hit:
            # Before the figure: the hit on the ally ends the award whatever the damage.
            state = CLOSED
        elif spec.get('maximum') is not None and value > spec['maximum']:
            # Fighter: a 6th kill ends the award.
            state = CLOSED
        elif value >= target:
            state = MET
        elif deadline is not None and now is not None and now >= deadline:
            state = CLOSED
        elif spec.get('fullHealth') and not self.full_health:
            state = CLOSED
        else:
            state = OPEN
        return {
            'live': True,
            'set': self.set_of[index],
            'allyHit': bool(spec.get('noAllyHits')) and self.ally_hit,
            'value': value,
            'target': target,
            'state': state,
            'deadline': deadline,
            'timeLimit': spec.get('timeLimit'),
        }

    def conditions(self, now):
        return [self.condition(index, now) for index in range(len(self.specs))]

    def set_states(self, now):
        """One state per set: MET when every condition of it is live and met, CLOSED when one of
        its conditions is closed, else OPEN. A condition that is not live stays open."""
        states = [MET] * self.set_count
        for item in self.conditions(now):
            index = item['set']
            if item['state'] == CLOSED:
                states[index] = CLOSED
            elif states[index] != CLOSED and (not item['live'] or item['state'] != MET):
                states[index] = OPEN
        return states


def _reason_counts(spec, reason):
    return spec.get('attackReason') is None or reason == spec['attackReason']


def _in_range(spec, distance, view_range):
    """Whether a hit at this distance counts for this condition.

    The client formatter reads `distance` this way: 0 is "within the view range of your
    vehicle", a positive value is "from N m or more", a negative one is "from N m or less".
    A hit on a target that is not in the client's world has no distance, and counts for no
    condition with a distance.
    """
    wanted = spec.get('distance')
    if wanted is None:
        return True
    if distance is None:
        return False
    if wanted == 0:
        return view_range is not None and distance <= view_range
    if wanted > 0:
        return distance >= wanted
    return distance <= -wanted


def summary(tracker, now):
    """One line for the log: the figure, the target and the state of each condition, in order,
    then the result totals that are not 0."""
    parts = []
    for index in range(len(tracker.specs)):
        item = tracker.condition(index, now)
        if item['live']:
            part = '{0}: {1}/{2} {3}'.format(
                index + 1, int(round(item['value'])), int(round(item['target'])), item['state'])
            if tracker.specs[index].get('diversity'):
                part += ' ({0} kills of {1})'.format(
                    tracker.counted[index], ', '.join(tracker.classes(index)) or 'no class')
            parts.append(part)
        else:
            parts.append('{0}: not counted'.format(index + 1))
    totals = ', '.join('{0} {1}'.format(key, int(round(value)))
                       for key, value in sorted(tracker.totals.items()) if value)
    line = '; '.join(parts) + ' | totals: ' + (totals or 'none')
    return line + (' | an ally was hit by a direct shot' if tracker.ally_hit else '')


def panel_rows(tracker, rows, now, number_format=None, counting=True):
    """The rows of the battle panel: the client text of each condition with its progress.

    `rows` are the mission rows of the transport, in the same order as the tracker conditions.
    When the two counts differ, the rows show their text and no progress, as a row that the
    panel cannot count does. With `counting` False, no row shows progress, but a time limit
    still counts down: the figures are not sure after a reconnect, and the clock is.
    """
    number_format = number_format or _plain_number
    matched = tracker is not None and len(rows) == len(tracker.specs)
    result = []
    for index, row in enumerate(rows):
        entry = {
            'text': row.get('text') or row.get('title') or '',
            'icon': row.get('icon') or '',
            'set': row.get('set', index),
            'live': False,
        }
        if matched:
            item = tracker.condition(index, now)
            entry['set'] = item['set']
            limit = tracker.specs[index].get('timeLimit')
            if limit is not None:
                entry.update({'deadline': tracker.deadline(index), 'timeLimit': limit})
            if item['live'] and counting:
                entry.update({
                    'live': True,
                    'state': item['state'],
                    'ratio': min(1.0, item['value'] / item['target']) if item['target'] else 1.0,
                    'valueText': number_format(item['value']),
                    'targetText': number_format(item['target']),
                })
                rules = _rules(tracker.specs[index], item)
                if rules:
                    entry['rules'] = rules
                if tracker.specs[index].get('diversity'):
                    # The icons of the classes destroyed show under the figures. The list is
                    # there, empty, before the first kill, so the row keeps its height.
                    entry['classes'] = tracker.classes(index)
        result.append(entry)
    return result


def _rules(spec, item):
    """The lines under the text of a condition, above the figures. A rule turns red once broken.

    - `noAllyHits`: the rule on allies of High Caliber, broken by a direct shot on an ally.
    - `<award>_descr`: the client's description of the award, which nothing breaks.
    - `<award>_maximum`: the line of the mod on the most that the award allows, broken above it.
    """
    rules = []
    if spec.get('noAllyHits'):
        rules.append({'key': 'noAllyHits', 'broken': item['allyHit']})
    if spec.get('description'):
        rules.append({'key': spec['award'] + '_descr', 'broken': False})
    if spec.get('maximum') is not None:
        rules.append({'key': spec['award'] + '_maximum', 'broken': item['value'] > spec['maximum']})
    return rules


def _plain_number(value):
    return '{0:,}'.format(int(round(value)))
