# -*- coding: utf-8 -*-
"""Tests for the salvo gun marker patch.

The client module the patch targets does not exist outside the game, so each test
installs its own fake `AvatarInputHandler.gun_marker_ctrl` carrying a stand-in
controller class. `gun_marker` imports it lazily inside install()/uninstall(), which is
what makes that possible.
"""
from __future__ import print_function, unicode_literals

import collections
import logging
import sys
import types
import unittest

from zanju_srf import gun_marker

# Mirrors VehicleGunRotator.GunMarkerInfo in client 2.3.1.1.
GunMarkerInfo = collections.namedtuple('GunMarkerInfo', (
    'gunInstallationIndex', 'gunIndex', 'position', 'direction',
    'size', 'dualAccSize', 'sizeOffset', 'collData'))


def update_func(cls):
    """The plain function behind cls.update.

    Python 2 builds a fresh unbound-method wrapper on every attribute access, so two
    reads of the same class attribute are never the same object. Comparing the
    underlying function is what actually answers "is this still the same code?".
    """
    return getattr(cls.update, '__func__', cls.update)


def make_info(size=0.7, size_offset=0.0):
    return GunMarkerInfo(
        gunInstallationIndex=0,
        gunIndex=1,
        position=(10.0, 2.0, 30.0),
        direction=(0.0, 0.0, 1.0),
        size=size,
        dualAccSize=0.5,
        sizeOffset=size_offset,
        collData=None,
    )


class StripSizeOffsetTest(unittest.TestCase):

    def test_returns_the_same_object_when_offset_is_already_zero(self):
        info = make_info(size_offset=0.0)
        self.assertIs(gun_marker.strip_size_offset(info), info)

    def test_zeroes_a_non_zero_offset(self):
        stripped = gun_marker.strip_size_offset(make_info(size_offset=0.426))
        self.assertEqual(stripped.sizeOffset, 0.0)

    def test_leaves_every_other_field_untouched(self):
        info = make_info(size=0.7, size_offset=0.426)
        stripped = gun_marker.strip_size_offset(info)
        self.assertEqual(stripped._replace(sizeOffset=0.426), info)

    def test_tolerates_info_without_a_size_offset_field(self):
        info = object()
        self.assertIs(gun_marker.strip_size_offset(info), info)


class FakeController(object):
    """Stand-in for _DefaultGunMarkerController: records what update() received."""

    def __init__(self):
        self.calls = []

    def update(self, markerType, gunMarkerInfo, supportMarkersInfo, relaxTime):
        self.calls.append((markerType, gunMarkerInfo, supportMarkersInfo, relaxTime))
        return 'original-result'


class FakeDualAccController(FakeController):
    """Stand-in for _DualAccMarkerController, which inherits update() unchanged."""


class InstallTest(unittest.TestCase):

    def setUp(self):
        self.logger = logging.getLogger('zanju.salvoreticlefix.test')
        self.logger.addHandler(logging.NullHandler())
        self.logger.propagate = False

        self.controller_cls = type(str('_DefaultGunMarkerController'), (FakeController,), {})
        self.dual_acc_cls = type(str('_DualAccMarkerController'), (self.controller_cls,), {})
        self.pristine_update = update_func(self.controller_cls)

        module = types.ModuleType(str('AvatarInputHandler.gun_marker_ctrl'))
        module._DefaultGunMarkerController = self.controller_cls
        package = types.ModuleType(str('AvatarInputHandler'))
        package.gun_marker_ctrl = module
        package.__path__ = []

        self.saved = {name: sys.modules.get(name)
                      for name in ('AvatarInputHandler', 'AvatarInputHandler.gun_marker_ctrl')}
        sys.modules['AvatarInputHandler'] = package
        sys.modules['AvatarInputHandler.gun_marker_ctrl'] = module

        self.addCleanup(self._restore_modules)
        self.addCleanup(gun_marker.uninstall, self.logger)

    def _restore_modules(self):
        for name, module in self.saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def test_install_reports_success_and_replaces_update(self):
        self.assertTrue(gun_marker.install(self.logger))
        self.assertIsNot(update_func(self.controller_cls), self.pristine_update)

    def test_patched_update_forwards_a_zeroed_offset(self):
        gun_marker.install(self.logger)
        controller = self.controller_cls()

        result = controller.update(1, make_info(size=0.7, size_offset=0.426), (), 0.1)

        self.assertEqual(result, 'original-result')
        self.assertEqual(len(controller.calls), 1)
        markerType, info, supportMarkersInfo, relaxTime = controller.calls[0]
        self.assertEqual(markerType, 1)
        self.assertEqual(info.sizeOffset, 0.0)
        self.assertEqual(info.size, 0.7)
        self.assertEqual(supportMarkersInfo, ())
        self.assertEqual(relaxTime, 0.1)

    def test_patched_update_leaves_a_normal_vehicle_alone(self):
        gun_marker.install(self.logger)
        controller = self.controller_cls()
        info = make_info(size_offset=0.0)

        controller.update(1, info, (), 0.1)

        self.assertIs(controller.calls[0][1], info)

    def test_subclassed_controller_inherits_the_patch(self):
        gun_marker.install(self.logger)
        controller = self.dual_acc_cls()

        controller.update(3, make_info(size_offset=0.426), (), 0.1)

        self.assertEqual(controller.calls[0][1].sizeOffset, 0.0)

    def test_install_is_idempotent(self):
        gun_marker.install(self.logger)
        patched = update_func(self.controller_cls)

        self.assertTrue(gun_marker.install(self.logger))
        self.assertIs(update_func(self.controller_cls), patched)

    def test_uninstall_restores_the_original_update(self):
        gun_marker.install(self.logger)
        gun_marker.uninstall(self.logger)

        self.assertIs(update_func(self.controller_cls), self.pristine_update)

    def test_uninstall_without_install_is_a_no_op(self):
        gun_marker.uninstall(self.logger)
        self.assertIs(update_func(self.controller_cls), self.pristine_update)

    def test_update_still_runs_when_stripping_raises(self):
        gun_marker.install(self.logger)
        controller = self.controller_cls()

        class Exploding(object):
            @property
            def sizeOffset(self):
                raise ValueError('boom')

        info = Exploding()
        controller.update(1, info, (), 0.1)

        self.assertIs(controller.calls[0][1], info)


if __name__ == '__main__':
    unittest.main()
