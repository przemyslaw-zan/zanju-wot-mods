# -*- coding: utf-8 -*-
"""Tests for the stat readers.

The readers take a ``VehicleParams`` instance, which does not exist outside the game, so
each test builds a stand-in carrying the three things a reader touches: the descriptor,
the vehicle attribute factors, and the vehicle item. Every reader reads those lazily, so
a plain object is enough.

The numbers in ``ST_II`` and ``TE_KE`` came out of a running client and were checked
against an external calculator. They are here to hold the arithmetic still: a change that
moves them is either a fix that needs a new reference number, or a regression.

BigWorld scripting uses Python 2.7. Avoid Python-3-only syntax.
"""
from __future__ import print_function, unicode_literals

import unittest

from zanju_bvs import stats

# Read out of client 2.4.0.0 and matched against an external calculator.
# ST-II with All-Terrain Suspension, Brothers in Arms and Off-Road Driving.
ST_II = {
    'terrain': (1.2000000476837158, 1.600000023841858, 2.700000047683716),
    'terrainFactor': (0.8790436005625879, ) * 3,
    'badRoadsKingMedium': 1.0660000031348318,
    'badRoadsKingSoft': 2.319999970495701,
    'expected': (1.0549, 1.3194, 1.3194),
}

# TE-KE, stock, no equipment and no relevant perks. The dispersion factors here are the
# numbers every reference site prints, which is what the readers must reproduce.
TE_KE = {
    'misc': {
        'chassis/shotDispersionFactors/movement': 0.24 / 0.27778,
        'chassis/shotDispersionFactors/rotation': 13.75098708,
        'gun/shotDispersionFactors/turretRotation': 6.87549354,
        'gun/shotDispersionFactors/afterShot': 3.5,
    },
    'expected': {
        'zanjuDispMovement': 0.24,
        'zanjuDispHullTraverse': 0.24,
        'zanjuDispGunTraverse': 0.12,
        'zanjuDispAfterShot': 3.5,
    },
}


class FakeChassis(object):

    def __init__(self, terrainResistance):
        self.terrainResistance = terrainResistance


class FakeDescr(object):

    def __init__(self, misc=None, terrainResistance=None, physicsTerrain=None):
        self.miscAttrs = misc or {}
        self.chassis = FakeChassis(terrainResistance)
        self.physics = {'terrainResistance': physicsTerrain}


class FakeParams(object):
    """Stands in for VehicleParams. The mangled names are what the readers look up."""

    def __init__(self, descr, factors=None):
        self._itemDescr = descr
        setattr(self, stats._FACTORS_ATTR, factors or {})
        setattr(self, stats._VEHICLE_ATTR, object())


def statByName(name):
    for stat in stats.STATS:
        if stat.name == name:
            return stat
    raise AssertionError('no stat named {0}'.format(name))


class DispersionReaderTest(unittest.TestCase):
    """The client stores these pre-divided; the readers must divide back."""

    def setUp(self):
        self.params = FakeParams(FakeDescr(misc=TE_KE['misc']))

    def test_matches_the_vehicle_file_units(self):
        for name, expected in TE_KE['expected'].items():
            value = statByName(name).read(self.params)
            self.assertAlmostEqual(expected, value, places=3, msg=name)

    def test_missing_attribute_reads_as_no_value(self):
        params = FakeParams(FakeDescr(misc={}))
        self.assertIsNone(statByName('zanjuDispMovement').read(params))


class TerrainReaderTest(unittest.TestCase):

    def setUp(self):
        self._realSkillFactor = stats._skill_factor
        factors = {stats._TERRAIN_FACTOR_KEY: ST_II['terrainFactor']}
        self.params = FakeParams(FakeDescr(terrainResistance=ST_II['terrain']), factors)

        def skillFactor(_params, _skillName, argName):
            if argName == 'mediumGroundFactor':
                return ST_II['badRoadsKingMedium']
            return ST_II['badRoadsKingSoft']

        stats._skill_factor = skillFactor

    def tearDown(self):
        stats._skill_factor = self._realSkillFactor

    def test_matches_the_external_calculator(self):
        names = ('zanjuTerrainHard', 'zanjuTerrainMedium', 'zanjuTerrainSoft')
        for name, expected in zip(names, ST_II['expected']):
            self.assertAlmostEqual(expected, statByName(name).read(self.params), places=3, msg=name)

    def test_off_road_driving_pulls_soft_down_to_medium(self):
        # At full effect the client's formula brings soft ground up to the medium value,
        # so the two rows read the same. This is the rule, not a rounding accident.
        medium = statByName('zanjuTerrainMedium').read(self.params)
        soft = statByName('zanjuTerrainSoft').read(self.params)
        self.assertAlmostEqual(medium, soft, places=4)

    def test_hard_ground_ignores_off_road_driving(self):
        # The skill declares a medium and a soft parameter and nothing for hard ground.
        expected = ST_II['terrain'][0] * ST_II['terrainFactor'][0]
        self.assertAlmostEqual(expected, statByName('zanjuTerrainHard').read(self.params), places=4)

    def test_reads_the_chassis_before_the_physics_dictionary(self):
        # A field modification rewrites the chassis. The physics dictionary can still hold
        # the tuple it captured earlier, and reading it would hide the change.
        descr = FakeDescr(terrainResistance=(1.0, 1.0, 1.0), physicsTerrain=(9.0, 9.0, 9.0))
        params = FakeParams(descr, {stats._TERRAIN_FACTOR_KEY: (1.0, 1.0, 1.0)})
        self.assertAlmostEqual(1.0, statByName('zanjuTerrainHard').read(params), places=4)

    def test_falls_back_to_the_physics_dictionary(self):
        descr = FakeDescr(terrainResistance=None, physicsTerrain=(2.0, 2.0, 2.0))
        params = FakeParams(descr, {stats._TERRAIN_FACTOR_KEY: (1.0, 1.0, 1.0)})
        self.assertAlmostEqual(2.0, statByName('zanjuTerrainHard').read(params), places=4)

    def test_no_terrain_data_reads_as_no_value(self):
        params = FakeParams(FakeDescr())
        self.assertIsNone(statByName('zanjuTerrainHard').read(params))


class RegistrationTest(unittest.TestCase):
    """Guards the shape the client registration depends on."""

    def test_every_stat_replaces_a_row_whose_icon_it_borrows(self):
        for stat in stats.STATS:
            self.assertTrue(stat.iconFrom, stat.name)

    def test_every_stat_names_a_group_the_client_has(self):
        for stat in stats.STATS:
            self.assertIn(stat.group, ('relativePower', 'relativeMobility'))

    def test_backward_stats_covers_every_stat(self):
        # A smaller number is better for all of these. If one is missing the comparator
        # paints an improvement red.
        self.assertEqual(set(stat.name for stat in stats.STATS), set(stats.BACKWARD_STATS))

    def test_stat_names_do_not_collide_with_the_rows_they_hide(self):
        self.assertFalse(set(stat.name for stat in stats.STATS) & set(stats.HIDDEN_PARAMS))


if __name__ == '__main__':
    unittest.main()
