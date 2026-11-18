# -*- coding: utf-8 -*-
"""What the banner, the card and the battle panel show, worked out from plain data.

The client calls the Crucible "challenges". A challenge is one series of missions. The player
activates one series at a time, plays its missions in order, and loses a shield on each failed
battle. The account tokens hold the progress of each series:

    challenge:quest:<id>    the number of the current mission, from 1
    challenge:attempt:<id>  the shields left
    challenge:win:<id>      how many times the series was completed

collector reads the client and hands this module plain dictionaries, so everything here can be
tested outside the game.

The conditions of a mission arrive as the client stores them: a list of (name, value) pairs,
nested. A leaf is a list with one ("value", x) pair. For example, "cause 3,500 HP of damage or
destroy 3 vehicles" is:

    [('or', [('results', [('key', [('value', 'damageDealt')]), ('greaterOrEqual', [('value', 3500.0)])]),
             ('results', [('key', [('value', 'kills')]), ('greaterOrEqual', [('value', 3.0)])])])]
"""
from __future__ import absolute_import, print_function, unicode_literals

STATE_ACTIVE = 'active'
STATE_INACTIVE = 'inactive'
STATE_COMPLETED = 'completed'
STATE_FAILED = 'failed'

# What the player can do with a series now, by the buttons of the client's own Crucible screen:
# an inactive series offers "Activate", and a series with no shields left offers a restart, free
# while free restarts remain. A completed series offers nothing.
AVAILABLE_NONE = 'none'
AVAILABLE_ACTIVE = 'active'
AVAILABLE_START = 'start'
AVAILABLE_FREE_RESTART = 'freeRestart'
AVAILABLE_PAID_RESTART = 'paidRestart'

# ChallengeDifficulties in challenges_common: the value the client stores, and the key of its
# label under #user_missions:hub/challenge_missions/complexity/. The client sorts the hardest
# first, and so does the card.
DIFFICULTIES = {1: 'hard', 2: 'medium', 3: 'easy'}

# The result keys that the battle panel counts while the battle runs, each from a client event
# (see battle_session). The client has no figure for a key outside this set until the battle
# results arrive, so a condition on such a key shows its text and no progress.
LIVE_RESULT_KEYS = frozenset((
    'damageDealt',
    'kills',
    'damageAssistedRadio',
    'damageAssistedTrack',
    'damageAssistedStun',
    'damageBlockedByArmor',
    'damageReceived',
    'critsCount',
    'piercingEnemyHits',
    'spotted',
))


def penetrated(flags, hit_flags):
    """Whether one shot result of the player is a penetration of the armor of an enemy.

    `flags` are the hit flags of one vehicle in `PlayerAvatar.showShotResults`, and `hit_flags` is
    the client's `VEHICLE_HIT_FLAGS`. The client plays its "penetration" sound on the same flag.
    Damage from a high-explosive shell that does not penetrate has its own flag, and the splash
    of a shell is an external explosion. These do not count, and neither does a hit on a vehicle
    that was already destroyed.
    """
    if flags & (hit_flags.VEHICLE_WAS_DEAD_BEFORE_ATTACK | hit_flags.ATTACK_IS_EXTERNAL_EXPLOSION):
        return False
    return bool(flags & hit_flags.MATERIAL_WITH_POSITIVE_DF_PIERCED_BY_PROJECTILE)


# The shapes of a condition. Each one says what a battle panel counts for it.
KIND_TOTAL = 'total'                    # one result key at or above a target
KIND_SUM = 'sum'                        # several result keys added together
KIND_HEALTH_MULTIPLE = 'healthMultiple'  # damage dealt or blocked as a multiple of the vehicle's own HP
KIND_TOP = 'top'                        # among the best N players by a result
KIND_DAMAGE = 'damage'                  # damage to vehicles, with a distance or time limit
KIND_KILLS = 'kills'                    # vehicles destroyed, with a limit such as full health
KIND_ACHIEVEMENT = 'achievement'        # an award from the battle results

# The state of a mission of the active series against the current mission.
MISSION_DONE = 'done'
MISSION_CURRENT = 'current'
MISSION_NEXT = 'next'
KIND_UNKNOWN = 'unknown'


def pairs(value):
    """The (name, value) pairs of a condition node, or an empty list for anything else."""
    if not isinstance(value, (list, tuple)):
        return []
    result = []
    for item in value:
        if isinstance(item, (list, tuple)) and len(item) == 2 and _is_text(item[0]):
            result.append((item[0], item[1]))
        else:
            return []
    return result


def leaf(value, default=None):
    """The x of a [('value', x)] leaf, or `default`."""
    node = pairs(value)
    if len(node) == 1 and node[0][0] == 'value':
        return node[0][1]
    return default


def node_dict(value):
    """The pairs of a node as a dict. A name that comes twice keeps its last value."""
    return dict(pairs(value))


def _is_text(value):
    try:
        return isinstance(value, basestring)  # noqa: F821
    except NameError:
        return isinstance(value, str)


# The awards that the panel can count, by the name of their dossier record. A mission names an
# award by its record ID, and `DB_ID_TO_RECORD` of the client gives the name, which is the same in
# every language: 228 is `mainGun`. Each rule gives the result keys that add up to the figure, and
# a fixed target or a share of the total HP of the enemy team, with a floor. `noAllyHits` means
# that one direct shot on an ally ends the award, also with team damage off: the client's own
# text of the award says so (`#achievements:mainGun_condition`).
AWARD_RULES = {
    # High Caliber: damage of at least 20% of the total HP of the enemy team, and at least 1,000 HP,
    # with no direct shot on an ally.
    'mainGun': {'keys': ['damageDealt'], 'enemyHealthShare': 0.2, 'minimum': 1000.0, 'noAllyHits': True},
    # Top Gun: at least 6 kills.
    'warrior': {'keys': ['kills'], 'target': 6.0, 'description': True},
    # Fighter: 4 or 5 kills. A 6th kill ends the award, because Fighter is for 4 or 5 kills only.
    'fighter': {'keys': ['kills'], 'target': 4.0, 'maximum': 5.0, 'description': True},
    # Duelist: at least 2 kills of enemies that damaged the player's vehicle, its HP or its modules.
    # The server judges the award after the battle, from the kills and the damage, so the order of
    # the two does not matter.
    'duelist': {'keys': ['killsOfAttackers'], 'target': 2.0, 'description': True},
}
# `description` shows the client's description of the award (`#achievements:<award>_descr`) under
# the condition, in the language of the client. battle_session writes the text. A figure above
# `maximum` closes the condition, and a line of the mod under the description says why.

# The fields of a condition that the panel knows how to count. A condition with any other field
# shows its text and no progress, because the panel could count it wrong.
_DAMAGE_FIELDS = frozenset(('greaterOrEqual', 'distance', 'limittedTime', 'eventCount', 'attackReason'))
_KILL_FIELDS = frozenset(('greaterOrEqual', 'whileFullHealth', 'classes', 'classesDiversity', 'attackReason'))

# The vehicle classes as the arena names them, in the order of the client's class filters
# (VEHICLE_TYPES_ORDER): light, medium, heavy, tank destroyer and SPG.
VEHICLE_CLASSES = ('lightTank', 'mediumTank', 'heavyTank', 'AT-SPG', 'SPG')
_RESULT_FIELDS = frozenset(('key', 'plus', 'greaterOrEqual', 'compareWithMaxHealth'))


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_condition(name, value, award_name=None):
    """What one condition asks for, as the battle panel counts it.

    Always holds `kind` and `live`. A live condition also holds `target`, and what it counts:

    - total, sum: `keys`, the result keys added together.
    - healthMultiple: `keys` and `multiplier`, damage dealt or blocked against the vehicle's own HP.
    - damage: `distance` (0 is the view range, more is at least that far, less than 0 is at most
      that far, None is any), `timeLimit` (seconds from the battle start, or None), `eventCount`
      (count the hits, not the HP) and `attackReason`.
    - kills: `fullHealth` (only the kills while the vehicle has all its HP count), `classes` (the
      vehicle classes that count, empty for all), `diversity` (how many different classes the
      kills must cover, or None) and `attackReason`.
    - achievement: `award`, `keys`, `target` or `enemyHealthShare` with `minimum`, `maximum`,
      `noAllyHits` and `description`, from AWARD_RULES.

    `attackReason` is None when the condition names no reason, and then every reason counts.
    `award_name(record_id)` gives the dossier record name of an award, or None. Without it, no
    award is live.

    The client formatter reads the same fields (ChallengeVehicleListFormatter). A form that it
    names and the panel cannot count, such as damage to an enemy that the player cannot see,
    shows its text and no progress.
    """
    node = node_dict(value)
    target = _number(leaf(node.get('greaterOrEqual')))
    if name == 'results':
        return _parse_results(node, target)
    if name == 'vehicleDamage':
        if target is None or not set(node) <= _DAMAGE_FIELDS:
            return {'kind': KIND_DAMAGE, 'live': False}
        return {
            'kind': KIND_DAMAGE, 'live': True, 'target': target,
            'distance': _number(leaf(node.get('distance'))),
            'timeLimit': _number(leaf(node.get('limittedTime'))),
            'eventCount': bool(leaf(node.get('eventCount'), False)),
            'attackReason': _attack_reason(node),
        }
    if name == 'vehicleKills':
        if target is None or not set(node) <= _KILL_FIELDS:
            return {'kind': KIND_KILLS, 'live': False}
        return {
            'kind': KIND_KILLS, 'live': True, 'target': target,
            'fullHealth': bool(leaf(node.get('whileFullHealth'), False)),
            'classes': [_class_name(item) for item in (leaf(node.get('classes'), []) or [])],
            'diversity': _diversity(node),
            'attackReason': _attack_reason(node),
        }
    if name == 'achievements':
        return _parse_award(value, award_name)
    return {'kind': KIND_UNKNOWN, 'live': False}


def _attack_reason(node):
    # The index of the reason in the client's ATTACK_REASONS: 0 a shot, 1 fire, 2 ramming. A damage
    # or kill condition with no `attackReason` counts every reason: in the game, damage by fire and
    # by ramming counts, and so does a kill by either.
    reason = leaf(node.get('attackReason'), None)
    return None if reason is None else int(reason)


def _diversity(node):
    # "Destroy 2 enemy vehicles of 2 different types": the number of classes, or None.
    count = leaf(node.get('classesDiversity'), None)
    return None if count is None else int(count)


def _parse_award(value, award_name):
    """An award condition. Only one award with a rule in AWARD_RULES is live."""
    ids = leaf(value, None)
    if not isinstance(ids, (list, tuple)) or len(ids) != 1 or award_name is None:
        return {'kind': KIND_ACHIEVEMENT, 'live': False}
    record = award_name(ids[0])
    rule = AWARD_RULES.get(record)
    if rule is None:
        return {'kind': KIND_ACHIEVEMENT, 'live': False, 'award': record}
    spec = {'kind': KIND_ACHIEVEMENT, 'live': True, 'award': record, 'keys': list(rule['keys']),
            'target': rule.get('target')}
    for key in ('enemyHealthShare', 'minimum', 'maximum', 'noAllyHits', 'description'):
        if key in rule:
            spec[key] = rule[key]
    return spec


def _class_name(value):
    """A vehicle class as the arena names it: `AT-SPG`, not the `AT_SPG` of a text key."""
    return 'AT-SPG' if value in ('AT_SPG', 'at-spg', 'at_spg') else value


def _parse_results(node, target):
    if not set(node) <= _RESULT_FIELDS:
        # `max` is "among the top N players", and the client has no result figure for any other
        # player. `total` is a figure of the whole team.
        kind = KIND_TOP if 'max' in node else KIND_UNKNOWN
        return {'kind': kind, 'live': False}
    if 'plus' in node:
        keys = [leaf(item) for key, item in pairs(node['plus']) if key == 'key']
        live = bool(keys) and target is not None and all(key in LIVE_RESULT_KEYS for key in keys)
        return {'kind': KIND_SUM, 'live': live, 'target': target, 'keys': keys}
    key = leaf(node.get('key'))
    if leaf(node.get('compareWithMaxHealth'), False):
        # The client has a text for damage dealt and for damage blocked by armor.
        return {'kind': KIND_HEALTH_MULTIPLE, 'live': key in LIVE_RESULT_KEYS and target is not None,
                'keys': [key], 'multiplier': target, 'target': target}
    if target is not None:
        return {'kind': KIND_TOTAL, 'live': key in LIVE_RESULT_KEYS, 'target': target, 'keys': [key]}
    return {'kind': KIND_UNKNOWN, 'live': False}


def classify(name, value, award_name=None):
    """What one condition asks for, and whether the battle panel counts it live."""
    spec = parse_condition(name, value, award_name)
    return {'kind': spec['kind'], 'live': spec['live']}


def condition_sets(conditions):
    """The alternative sets of a mission's post-battle conditions.

    A list of sets, and each set is a list of (name, value) conditions. Every condition of a set
    must be met, and one met set completes the mission. Most missions have one set. A choice is
    an `or` of single conditions, or of `and` groups of several.
    """
    top = pairs(node_dict(conditions).get('postBattle'))
    if len(top) == 1 and top[0][0] == 'or':
        sets = []
        for name, value in pairs(top[0][1]):
            sets.append(pairs(value) if name == 'and' else [(name, value)])
        return sets
    if len(top) == 1 and top[0][0] == 'and':
        return [pairs(top[0][1])]
    return [top] if top else []


def post_battle(conditions, award_name=None):
    """The group of a mission's post-battle conditions and one shape per condition, in order.

    Returns ('or', shapes) when the mission offers several sets and ('and', shapes) otherwise. Each
    shape holds `kind`, `live` and `set`, the index of its set.
    """
    sets = condition_sets(conditions)
    shapes = []
    for index, conditions_of_set in enumerate(sets):
        for name, value in conditions_of_set:
            shape = classify(name, value, award_name)
            shape['set'] = index
            shapes.append(shape)
    return ('or' if len(sets) > 1 else 'and'), shapes


def flatten_packed(items):
    """The leaf rows of the client's packed conditions, depth first, as `condition_sets` reads
    the raw ones. A group in the packed form is an item with `items` of its own."""
    rows = []
    for item in items or ():
        if not isinstance(item, dict):
            continue
        if item.get('descrData') is None and item.get('items'):
            rows.extend(flatten_packed(item.get('items')))
        else:
            rows.append(item)
    return rows


def pre_battle(conditions):
    """The battle types and the vehicle tiers a mission accepts. An empty list accepts any."""
    pre = node_dict(node_dict(conditions).get('preBattle'))
    battle = node_dict(pre.get('battle'))
    vehicle = node_dict(node_dict(pre.get('vehicle')).get('vehicleDescr'))
    return {
        'bonusTypes': sorted(leaf(battle.get('bonusTypes'), []) or []),
        'levels': sorted(leaf(vehicle.get('levels'), []) or []),
    }


# `CHALLENGE_MIN_VEHICLE_LEVEL` in challenges_common: the client's own floor for the Crucible.
MIN_VEHICLE_LEVEL = 6

# The battle types of every Crucible mission on 2.4.1.0: REGULAR (1), WINBACK (44) and RANDOM_NP2
# (46), the random battles. Only the stand-in when no mission could be read.
RANDOM_BONUS_TYPES = (1, 44, 46)


def counted_in_battle(vehicles, battles, bonus_types):
    """The names of the vehicles in battle whose battle counts for the Crucible.

    `vehicles` are (intCD, name) pairs of eligible vehicles in a battle now. `battles` maps an
    intCD to the battle type the mod recorded when that vehicle entered its battle. A vehicle with
    no record counts: nothing says that its battle does not, and a warning too many costs less
    than a missing one.
    """
    allowed = set(bonus_types or RANDOM_BONUS_TYPES)
    names = []
    for int_cd, name in vehicles:
        bonus_type = battles.get(int_cd)
        if bonus_type is None or bonus_type in allowed:
            names.append(name)
    return names


def vehicle_fits(levels, level, min_level=MIN_VEHICLE_LEVEL):
    """Whether a vehicle of this tier can play. None when there is no vehicle.

    `levels` are the tiers of the current mission. With no mission, the Crucible floor decides.
    """
    if level is None:
        return None
    if levels:
        return level in levels
    return level >= min_level


def battle_mismatch(active, bonus_type, level):
    """Why this battle cannot count for the mission of the transport, or None when it can.

    `active` is the `active` entry of the transport. A mission counts only its own battle types
    and tiers. With no battle types in the transport, the random battles count.
    """
    if not active:
        return 'no active series'
    bonus_types = active.get('bonusTypes') or RANDOM_BONUS_TYPES
    if bonus_type not in bonus_types:
        return 'battle type {0} is not one of {1}'.format(bonus_type, sorted(bonus_types))
    if vehicle_fits(active.get('levels') or [], level) is False:
        return 'tier {0} is not one of {1}'.format(level, sorted(active.get('levels') or []))
    if not active.get('postBattle'):
        return 'the transport has no conditions'
    return None


def read_tokens(series_tokens, tokens):
    """The active series and the progress of each series, from the account tokens.

    This is what the client's controller does in `__updateChallengesProgress`, but the controller
    does it only when the lobby view has loaded, and the garage builds before that. After a
    battle, the controller also holds no active series until then. The tokens of the items cache
    are there before the garage builds.

    `series_tokens` is a list of (series ID, token IDs), and the token IDs are a dict with the keys
    active, attempts, quests and wins. `tokens` maps a token ID to (expiry time, count), the form
    of `itemsCache.items.tokens.getTokens()`. Returns (active ID or 0, {series ID: progress}).
    """
    def count(token_id):
        _, value = tokens.get(token_id) or (0, 0)
        return value or 0

    active_id = 0
    progress = {}
    for series_id, token_ids in series_tokens:
        if count(token_ids['active']):
            active_id = series_id
        progress[series_id] = dict((key, count(token_ids[key])) for key in ('attempts', 'quests', 'wins'))
    return active_id, progress


def series_state(is_active, progress, allowed_completions):
    """The state the client's own Crucible screen gives a series (`getChallengeState`).

    The client reads `progress['attempts']` with no default and raises on a series with no tokens
    yet, which happens before the lobby has synced. Missing counts read as 0 here.
    """
    if is_active:
        return STATE_ACTIVE
    attempts = _count(progress, 'attempts')
    quests = _count(progress, 'quests')
    if attempts == 0 and quests > 0:
        return STATE_FAILED
    if allowed_completions and _count(progress, 'wins') >= allowed_completions:
        return STATE_COMPLETED
    return STATE_INACTIVE


def _count(progress, key):
    try:
        return int((progress or {}).get(key) or 0)
    except (TypeError, ValueError):
        return 0


def restart_price(price):
    """The restart price as (currency, amount), from the client's `{currency: amount}` dict.

    A series is restarted for one currency, so the dict has one entry. None when there is none.
    """
    if not isinstance(price, dict) or not price:
        return None
    currency = sorted(price)[0]
    try:
        return currency, int(price[currency] or 0)
    except (TypeError, ValueError):
        return None


def series_entry(raw):
    """One series, in the form the banner and the card read.

    `raw` holds: id, name, difficulty (the client's number), priority, attempts (the shield
    limit), allowedCompletions, questCount, progress, isActive, endTime (server time in seconds),
    expiringSoon, restartPrice (`{currency: amount}`), restartCostText (the amount as the client
    writes it) and freeRestarts.
    """
    progress = raw.get('progress') or {}
    allowed = raw.get('allowedCompletions') or 0
    state = series_state(raw.get('isActive'), progress, allowed)
    stage = _count(progress, 'quests')
    shields = _count(progress, 'attempts')
    if state == STATE_INACTIVE and not shields:
        # The client shows a full set of shields on a series that never started.
        shields = raw.get('attempts') or 0
    price = restart_price(raw.get('restartPrice'))
    return {
        'id': raw.get('id'),
        'name': raw.get('name') or '',
        'difficulty': DIFFICULTIES.get(raw.get('difficulty'), 'easy'),
        'state': state,
        'stage': stage,
        'total': raw.get('questCount') or 0,
        # The client's own count: the current mission is not done yet.
        'completed': stage - 1 if stage else 0,
        'shields': shields,
        'shieldsLimit': raw.get('attempts') or 0,
        'wins': _count(progress, 'wins'),
        'allowedCompletions': allowed,
        'endTime': int(raw.get('endTime') or 0),
        'expiringSoon': bool(raw.get('expiringSoon')),
        'restartCurrency': price[0] if price else '',
        'restartCost': price[1] if price else 0,
        'restartCostText': raw.get('restartCostText') or (str(price[1]) if price else ''),
        'freeRestarts': max(0, int(raw.get('freeRestarts') or 0)),
    }


def availability(entry):
    """What the player can do with this series, as one of the AVAILABLE_ values."""
    state = entry['state']
    if state == STATE_COMPLETED:
        return AVAILABLE_NONE
    if state == STATE_ACTIVE:
        return AVAILABLE_ACTIVE
    if state == STATE_FAILED:
        return AVAILABLE_FREE_RESTART if entry['freeRestarts'] > 0 else AVAILABLE_PAID_RESTART
    return AVAILABLE_START


def nearest_end(series):
    """When the banner's countdown ends, by the rule of the client's own Crucible banner.

    With an active series, its end. Otherwise the nearest end of a series that is not completed:
    a completed series has nothing left to play before it ends. 0 when no series has an end.
    """
    for entry in series:
        if entry['state'] == STATE_ACTIVE:
            return entry['endTime']
    ends = [entry['endTime'] for entry in series if entry['state'] != STATE_COMPLETED and entry['endTime'] > 0]
    return min(ends) if ends else 0


# The order of the paid groups on the banner: credits, then gold, then any other currency.
_CURRENCY_ORDER = ('credits', 'gold')


def soonest_set(series, soonest):
    """What the banner counts with no active series: the series that end first and are not
    completed yet, the same ones that its countdown and the card's highlight follow.

    When every series of the earliest end is completed, `soonest` is already the next end, so the
    set moves on with it. Returns {'free': n, 'paid': [{'currency': c, 'count': n}, ...]}: how many
    of them start, or restart, for nothing, and how many restart for a price in each currency.
    """
    members = [entry for entry in series
               if entry['state'] != STATE_COMPLETED and (entry['endTime'] == soonest if soonest else True)]
    free = 0
    paid = {}
    for entry in members:
        if entry['availability'] in (AVAILABLE_START, AVAILABLE_FREE_RESTART):
            free += 1
        elif entry['availability'] == AVAILABLE_PAID_RESTART and entry.get('restartCurrency'):
            paid[entry['restartCurrency']] = paid.get(entry['restartCurrency'], 0) + 1

    def order(currency):
        return (_CURRENCY_ORDER.index(currency) if currency in _CURRENCY_ORDER else len(_CURRENCY_ORDER), currency)

    return {
        'free': free,
        'paid': [{'currency': currency, 'count': paid[currency]} for currency in sorted(paid, key=order)],
    }


def mission_rows(packed_items, shapes):
    """The rows of the current mission: the client's text, and whether a panel counts it live.

    The client's packer and the raw conditions list the rows in the same order. If the two lists
    disagree in length, no row is called live, because no row can be matched for sure.
    """
    packed_items = flatten_packed(packed_items)
    rows = []
    matched = len(packed_items) == len(shapes)
    for index, item in enumerate(packed_items):
        shape = shapes[index] if matched else {'kind': KIND_UNKNOWN, 'live': False, 'set': 0}
        rows.append({
            'title': item.get('titleData') or '',
            'text': item.get('descrData') or '',
            'icon': item.get('iconKey') or '',
            'kind': shape['kind'],
            'live': shape['live'],
            'set': shape.get('set', 0),
        })
    return rows


def series_missions(missions, stage):
    """Every mission of the active series, in order, for the card.

    `missions` holds the mission dict of each quest of the series, or None for a quest that the
    client has not synced yet. Each entry has its number, its state against the current mission
    (`done`, `current` or `next`), its group and its rows.
    """
    result = []
    for index, mission in enumerate(missions or ()):
        number = index + 1
        if number < stage:
            state = MISSION_DONE
        elif number == stage:
            state = MISSION_CURRENT
        else:
            state = MISSION_NEXT
        result.append({
            'stage': number,
            'state': state,
            'group': (mission or {}).get('group') or 'and',
            'rows': (mission or {}).get('rows') or [],
        })
    return result


def build_snapshot(enabled, series_raw, mission, vehicle_level, in_battle=None, min_level=MIN_VEHICLE_LEVEL,
                   missions=None):
    """Everything the banner and the card show.

    `series_raw` is in the client's own order. `mission` is None when no series is active, or a
    dict with questID, group, rows and levels for the current mission of the active series.
    `in_battle` names the vehicles that can play the Crucible and are in a battle now. `missions`
    holds the mission dict of each quest of the active series, in order (see series_missions).
    """
    series = [series_entry(raw) for raw in series_raw]
    soonest = nearest_end(series)
    for entry in series:
        entry['availability'] = availability(entry)
        # The countdown the banner shows. Two series can end at the same time, and then both are.
        entry['soonest'] = bool(soonest) and entry['endTime'] == soonest and entry['state'] != STATE_COMPLETED
    active = None
    for entry in series:
        if entry['state'] == STATE_ACTIVE:
            active = dict(entry)
            break
    levels = (mission or {}).get('levels') or []
    fits = vehicle_fits(levels, vehicle_level, min_level)
    if active is not None and mission is not None:
        active['mission'] = mission
    if active is not None and missions:
        active['missions'] = series_missions(missions, active.get('stage') or 0)
    return {
        'enabled': bool(enabled),
        'active': active,
        'series': series,
        # The client's own rule for its Crucible banner: a series is open until it is completed.
        'nearestEnd': soonest,
        # What the banner counts with no active series, and whether nothing is left to play.
        'soonestSet': soonest_set(series, soonest),
        'allCompleted': bool(series) and all(entry['state'] == STATE_COMPLETED for entry in series),
        # Whether the vehicle in the garage can play: the tiers of the current mission, or the
        # Crucible floor with no active series. None with no vehicle in the garage.
        'vehicleFits': fits,
        # A battle still in progress counts for the series that is active when the battle ends.
        'inBattle': sorted(in_battle or []),
    }


def transport(snapshot, conditions, account_dbid, saved_at):
    """The facts a battle needs about the active series, or None when there is none.

    A battle cannot ask the client: the client drops the active series when the account entity
    goes away. So the garage writes these facts to disk and the battle reads them back.
    """
    active = snapshot.get('active') if snapshot else None
    mission = active.get('mission') if active else None
    if not mission:
        return None
    pre = pre_battle(conditions or [])
    return {
        'version': 1,
        'accountDBID': account_dbid,
        'savedAt': saved_at,
        'active': {
            'id': active.get('id'),
            'name': active.get('name'),
            'stage': active.get('stage'),
            'total': active.get('total'),
            'shields': active.get('shields'),
            'shieldsLimit': active.get('shieldsLimit'),
            'questID': mission.get('questID'),
            'group': mission.get('group'),
            'rows': mission.get('rows') or [],
            'bonusTypes': pre['bonusTypes'],
            'levels': pre['levels'],
            'postBattle': node_dict(conditions or []).get('postBattle'),
        },
    }
