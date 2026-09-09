# -*- coding: utf-8 -*-
"""The stats this mod adds, and how to read each one from the vehicle.

Each entry becomes a real client parameter. ``integration`` installs a ``property`` of the
same name on ``VehicleParams``, and from that point the client treats it like any
parameter it ships: ``ParamsDictProxy`` finds it, the comparator rates it against the
stock vehicle, and the tooltip extractor re-reads it with each bonus removed to get that
bonus's contribution.

A reader takes the ``VehicleParams`` instance and returns a number, or None when the
vehicle cannot supply the value. A reader must be cheap and must never raise: the client
calls every property each time it builds a parameter dictionary, so one exception here
breaks every stat screen at once.

BigWorld scripting uses Python 2.7. Avoid Python-3-only syntax.
"""
from __future__ import print_function, unicode_literals

import math

from .localization import get_text

_TERRAIN_FACTOR_KEY = 'chassis/terrainResistance'
_FACTORS_ATTR = '_VehicleParams__factors'
_VEHICLE_ATTR = '_VehicleParams__vehicle'
_BAD_ROADS_KING = 'driver_badRoadsKing'

# The client stores the dispersion factors pre-divided, so battle code can multiply by a
# speed in km/h and a rotation in degrees per second without converting first. The vehicle
# files, and every reference site, state the undivided numbers, so the readers divide back.
_DISPERSION_KEYS = {
    'movement': 'chassis/shotDispersionFactors/movement',
    'hullTraverse': 'chassis/shotDispersionFactors/rotation',
    'gunTraverse': 'gun/shotDispersionFactors/turretRotation',
    'afterShot': 'gun/shotDispersionFactors/afterShot',
}


def _kmh_to_ms():
    try:
        from items.components import component_constants

        return float(component_constants.KMH_TO_MS)
    except Exception:
        return 0.27778


def _misc_attr(vehicleParams, key):
    descr = getattr(vehicleParams, '_itemDescr', None)
    misc = getattr(descr, 'miscAttrs', None)
    if not misc or key not in misc:
        return None
    return float(misc[key])


def _factor(vehicleParams, key, default=1.0):
    factors = getattr(vehicleParams, _FACTORS_ATTR, None)
    if not factors:
        return default
    found = factors.get(key)
    try:
        return float(found)
    except (TypeError, ValueError):
        return default


def _dispersion_reader(key, convert):
    """Read one dispersion factor, with everything that changes it folded in.

    Two channels reach these numbers and each carries different sources.
    ``miscAttrs`` holds field modifications and the equipment that rewrites the
    descriptor. The attribute factors hold crew perks and the equipment that declares a
    factor instead. The client multiplies the two at the point of use, so a reader that
    takes only ``miscAttrs`` reports a number that no crew perk can move.
    """

    def read(vehicleParams):
        attrKey = _DISPERSION_KEYS[key]
        value = _misc_attr(vehicleParams, attrKey)
        if value is None:
            return None
        return round(convert(value) * _factor(vehicleParams, attrKey), 4)

    return read


def _skill_factor(vehicleParams, skillName, argName):
    """Return the multiplier one crew skill contributes, or 1.0 when nobody has it.

    Some skills never reach the vehicle attribute factors. The client applies them by
    hand at the point of use, and ``VehicleParams.softGroundFactor`` is the example this
    mirrors. A reader that only multiplies the factor triple therefore misses them.
    """
    try:
        from gui.shared.gui_items.Tankman import crewMemberRealSkillLevel
        from items import tankmen

        vehicle = getattr(vehicleParams, _VEHICLE_ATTR, None)
        if vehicle is None:
            return 1.0
        param = tankmen.getSkillsConfig().getSkill(skillName).params.get(argName)
        perLevel = param.value if param else 0.0
        level = crewMemberRealSkillLevel(vehicle, skillName)
        if level == tankmen.NO_SKILL:
            return 1.0
        return 1.0 + perLevel * level
    except Exception:
        return 1.0


def _terrain_base(vehicleParams, index):
    """Return the resistance for one ground type, before any hand-applied skill."""
    descr = getattr(vehicleParams, '_itemDescr', None)
    if descr is None:
        return None
    # Prefer the chassis component over the physics dictionary. The two hold the same
    # numbers on a settled descriptor, because the physics dictionary is built from the
    # chassis. They part company after a field modification changes: that rewrites the
    # chassis, while the physics dictionary can still hold the tuple it captured earlier.
    # Reading the chassis is what lets the tooltip see a field modification move the value.
    raw = getattr(getattr(descr, 'chassis', None), 'terrainResistance', None)
    if not raw:
        physics = getattr(descr, 'physics', None) or {}
        raw = physics.get('terrainResistance')
    if not raw or len(raw) <= index:
        return None
    # Field modifications are already in the raw triple. Equipment and most crew effects
    # arrive as a separate factor triple, which the client multiplies in when it is used.
    factor = 1.0
    factors = getattr(vehicleParams, _FACTORS_ATTR, None)
    if factors:
        found = factors.get(_TERRAIN_FACTOR_KEY)
        if found and len(found) > index:
            factor = float(found[index])
    return float(raw[index]) * factor


def _terrain_reader(index):
    """Read one ground resistance, following the client's own Off-Road Driving model.

    That skill divides the medium resistance by its factor, then pulls the soft
    resistance toward the improved medium one. ``VehicleParams.softGroundFactor`` is
    where the client states this, and these readers repeat it.
    """

    def read(vehicleParams):
        base = _terrain_base(vehicleParams, index)
        if base is None:
            return None
        if index == 0:
            return round(base, 4)
        medium = _terrain_base(vehicleParams, 1)
        if medium is None:
            return round(base, 4)
        medium = medium / _skill_factor(vehicleParams, _BAD_ROADS_KING, 'mediumGroundFactor')
        if index == 1:
            return round(medium, 4)
        pull = min(_skill_factor(vehicleParams, _BAD_ROADS_KING, 'softGroundFactor') - 1.0, 1.0)
        return round(base - (base - medium) * pull, 4)

    return read


class StatDef(object):
    """One added stat: its client parameter name, where it goes, and how to read it."""

    __slots__ = ('name', 'group', 'key', 'digits', 'iconFrom', 'bonusesFrom', 'read')

    def __init__(self, name, group, key, digits, iconFrom, bonusesFrom, read):
        self.name = name
        self.group = group
        # Text is looked up on each call, so a language change needs no reinstall.
        self.key = key
        self.digits = digits
        # The row icon is looked up by parameter name, so a new name has no art. Each stat
        # names an existing parameter whose icon suits it. The icon of a hidden row is the
        # natural choice, because that row measured the same thing.
        self.iconFrom = iconFrom
        # Bonus lists are copied from the parameters the client already maps, rather than
        # written by hand. The modifiers that produced the hidden row are the modifiers
        # that move the value.
        self.bonusesFrom = bonusesFrom
        self.read = read

    @property
    def label(self):
        return get_text('LABEL_' + self.key)

    @property
    def title(self):
        return get_text('TITLE_' + self.key)

    @property
    def description(self):
        return get_text('DESC_' + self.key)


_POWER = 'relativePower'
_MOBILITY = 'relativeMobility'

STATS = (
    StatDef(
        'zanjuDispMovement', _POWER, 'DISP_MOVEMENT', 3,
        'vehicleGunShotDispersionChassisMovement',
        ('vehicleGunShotDispersionChassisMovement', 'vehicleGunShotDispersion', 'shotDispersionAngle'),
        _dispersion_reader('movement', lambda v: v * _kmh_to_ms())),
    StatDef(
        'zanjuDispHullTraverse', _POWER, 'DISP_HULL_TRAVERSE', 3,
        'vehicleGunShotDispersionChassisRotation',
        ('vehicleGunShotDispersionChassisRotation', 'vehicleGunShotDispersion', 'shotDispersionAngle'),
        _dispersion_reader('hullTraverse', math.radians)),
    StatDef(
        'zanjuDispGunTraverse', _POWER, 'DISP_GUN_TRAVERSE', 3,
        'vehicleGunShotDispersionTurretRotation',
        ('vehicleGunShotDispersionTurretRotation', 'vehicleGunShotDispersion', 'shotDispersionAngle'),
        _dispersion_reader('gunTraverse', math.radians)),
    StatDef(
        'zanjuDispAfterShot', _POWER, 'DISP_AFTER_SHOT', 2,
        'vehicleGunShotDispersionAfterShot',
        ('vehicleGunShotDispersionAfterShot', 'vehicleGunShotDispersion', 'shotDispersionAngle'),
        _dispersion_reader('afterShot', lambda v: v)),
    StatDef(
        'zanjuTerrainHard', _MOBILITY, 'TERRAIN_HARD', 2,
        'vehicleSpeedGain', ('vehicleSpeedGain', 'chassisRotationSpeed'), _terrain_reader(0)),
    StatDef(
        'zanjuTerrainMedium', _MOBILITY, 'TERRAIN_MEDIUM', 2,
        'mediumGroundFactor', ('mediumGroundFactor', 'vehicleSpeedGain', 'chassisRotationSpeed'), _terrain_reader(1)),
    StatDef(
        'zanjuTerrainSoft', _MOBILITY, 'TERRAIN_SOFT', 2,
        'softGroundFactor', ('softGroundFactor', 'vehicleSpeedGain', 'chassisRotationSpeed'), _terrain_reader(2)),
)

# The rows these values replace. Each states a percentage change and appears only when a
# modifier exists. The combined dispersion row goes too: it exists because one modifier can
# hit several factors, and that ambiguity ends once every factor prints its own number.
HIDDEN_PARAMS = (
    'vehicleGunShotDispersion',
    'vehicleGunShotDispersionChassisMovement',
    'vehicleGunShotDispersionChassisRotation',
    'vehicleGunShotDispersionTurretRotation',
    'vehicleGunShotDispersionAfterShot',
    'vehicleSpeedGain',
    'mediumGroundFactor',
    'softGroundFactor',
)

# For every stat here a smaller number is better, which is the opposite of the client's
# default. Without this the comparator paints an improvement red.
BACKWARD_STATS = frozenset(stat.name for stat in STATS)


def describe(vehicle):
    """Return one dictionary of every channel these readers use, for the log.

    Reading the client's code has settled the terrain path but not the dispersion one, so
    this dumps both raw inputs beside the result. Whichever channel a modifier travels
    through, the numbers here say so.
    """
    from gui.shared.items_parameters.params import VehicleParams

    params = VehicleParams(vehicle)
    factors = getattr(params, _FACTORS_ATTR, None) or {}
    descr = getattr(params, '_itemDescr', None)
    misc = getattr(descr, 'miscAttrs', None) or {}
    physics = getattr(descr, 'physics', None) or {}
    report = {
        'terrainRaw': list(physics.get('terrainResistance', ())),
        'terrainFactor': list(factors.get(_TERRAIN_FACTOR_KEY, ())),
        'badRoadsKingMedium': _skill_factor(params, _BAD_ROADS_KING, 'mediumGroundFactor'),
        'badRoadsKingSoft': _skill_factor(params, _BAD_ROADS_KING, 'softGroundFactor'),
        'shotDispersionAggregate': factors.get('shotDispersion'),
    }
    for name, key in _DISPERSION_KEYS.items():
        report[name] = {'misc': misc.get(key), 'factor': factors.get(key)}

    for stat in STATS:
        report[stat.name] = stat.read(params)

    return report


def describe_bonuses(vehicle, statName):
    """Run the client's own bonus extractor for one stat and report what it produces.

    The tooltip gets its per-bonus number from this exact path, so whatever comes back
    here is what the tooltip shows. It separates two possibilities that look identical on
    screen: a value that does not move when the bonus is removed, and a value that moves
    but is then rounded away by the formatter.
    """
    from gui.shared.items_parameters import params_cache
    from gui.shared.items_parameters.bonus_helper import BonusExtractor
    from gui.shared.items_parameters.params_helper import similarCrewComparator

    comparator = similarCrewComparator(vehicle)
    extended = comparator.getExtendedData(statName)
    listed = list(params_cache.g_paramsCache.getBonuses().get(statName, ()))
    rows = []
    for bnsGroup, bnsId, pInfo in BonusExtractor(vehicle, extended.bonuses, statName).getBonusInfo():
        rows.append({'id': bnsId, 'group': bnsGroup, 'value': pInfo.value, 'state': pInfo.state})

    return {
        'stat': statName,
        'mapped': len(listed),
        'active': [(bnsId, grp) for bnsId, grp in extended.bonuses],
        'possible': len(extended.possibleBonuses),
        'rows': rows,
    }
