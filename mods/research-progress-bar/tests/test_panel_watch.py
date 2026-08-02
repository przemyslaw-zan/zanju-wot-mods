# -*- coding: utf-8 -*-
"""Tests for the loadout bar probe.

The probe exists to catch the bar blanking, a failure that raises nothing and leaves no trace
of its own. If its detection rule is wrong we get silence and conclude the bug did not happen,
so the rule is worth pinning harder than the reading it works from.

`panel_watch` keeps every client import inside a function, which is what makes it testable
here at all -- the rest of this mod reaches BigWorld at import time.
"""
from __future__ import unicode_literals

import logging
import unittest

from zanju_rpb import panel_watch


class SilentLogger(logging.Logger):

    def __init__(self):
        logging.Logger.__init__(self, 'test')
        self.infos = []
        self.warnings = []
        self.exceptions = []
        self.addHandler(logging.NullHandler())

    def info(self, message, *args, **kwargs):
        self.infos.append(message % args if args else message)

    def warning(self, message, *args, **kwargs):
        self.warnings.append(message % args if args else message)

    def exception(self, message, *args, **kwargs):
        self.exceptions.append(message)


def reading(sections=None, expected=None, stale=False, disabled=False):
    return {
        'disabled': disabled,
        'vehicleId': '49169',
        'sections': sections if sections is not None else [('optDevices', 3), ('battleBoosters', 1)],
        'expected': expected if expected is not None else ['optDevices', 'battleBoosters'],
        'copyIntCD': 49169,
        'copyAlive': True,
        'liveIntCD': 49169,
        'staleCopy': stale,
    }


class LooksBrokenTest(unittest.TestCase):

    def test_a_healthy_panel_is_quiet(self):
        self.assertIsNone(panel_watch.looks_broken(reading()))

    def test_catches_the_model_losing_its_sections(self):
        # The blanking symptom: the bar is on screen with nothing in it.
        self.assertIn('no sections', panel_watch.looks_broken(reading(sections=[])))

    def test_catches_every_section_going_empty(self):
        emptied = [('optDevices', 0), ('battleBoosters', 0)]
        self.assertIn('every section is empty', panel_watch.looks_broken(reading(sections=emptied)))

    def test_catches_one_section_disappearing(self):
        # Whichever mode is running, the panel's controller says what belongs there, so a
        # missing section is detectable without hardcoding any mode's layout.
        broken = panel_watch.looks_broken(reading(sections=[('optDevices', 3)]))
        self.assertIn('battleBoosters', broken)

    def test_reports_a_stale_vehicle_copy_first(self):
        # The documented root cause. Naming it outright is the difference between confirming
        # the known bug and starting the investigation over.
        self.assertIn('stale vehicle copy', panel_watch.looks_broken(reading(stale=True)))

    def test_an_empty_panel_with_nothing_expected_is_not_a_fault(self):
        # A garage with no tank selected, not a broken bar.
        self.assertIsNone(panel_watch.looks_broken(reading(sections=[], expected=[])))

    def test_an_unknown_copy_state_is_not_reported_as_stale(self):
        # None means "could not read", which must never read as "fine" or as "broken".
        self.assertIsNone(panel_watch.looks_broken(reading(stale=None)))

    def test_a_populated_section_alongside_an_empty_one_is_fine(self):
        self.assertIsNone(panel_watch.looks_broken(
            reading(sections=[('optDevices', 3), ('battleBoosters', 0)])))


class DescribeTest(unittest.TestCase):

    def test_names_every_section_with_its_slot_count(self):
        text = panel_watch.describe(reading())
        self.assertIn('optDevices:3', text)
        self.assertIn('battleBoosters:1', text)

    def test_survives_a_reading_with_nothing_in_it(self):
        text = panel_watch.describe(reading(sections=[], expected=[]))
        self.assertIn('sections=-', text)
        self.assertIn('expected=-', text)


class FakeModel(object):

    def __init__(self, groups, disabled=False, vehicle_id='49169'):
        self._groups = groups
        self._disabled = disabled
        self._vehicle_id = vehicle_id

    def getGroups(self):
        return self._groups

    def getIsDisabled(self):
        return self._disabled

    def getVehicleId(self):
        return self._vehicle_id


class FakeSection(object):

    def __init__(self, name, slots):
        self._name = name
        self._slots = slots

    def getName(self):
        return self._name

    def getSlots(self):
        return [None] * self._slots


class FakeGroup(object):

    def __init__(self, sections):
        self._sections = sections

    def getSections(self):
        return self._sections


class FakeControllerGroup(object):

    def __init__(self, *sections):
        self.sections = sections


class FakeController(object):

    def __init__(self, groups):
        self._groups = groups

    def _getGroups(self):
        return self._groups


class FakeWrapper(object):
    """The InteractingItem a live panel renders from; `_finalize` drops it, which is how
    liveness is decided."""

    def getItem(self):
        return None


class FakePresenter(object):

    def __init__(self, model, controller, live=True):
        self._model = model
        self._getGroupController = controller
        self._vehInteractingItem = FakeWrapper() if live else None

    def getViewModel(self):
        return self._model


class SampleTest(unittest.TestCase):

    def presenter(self):
        model = FakeModel([
            FakeGroup([FakeSection('optDevices', 3), FakeSection('battleBoosters', 1)]),
            FakeGroup([FakeSection('shells', 3)]),
        ])
        controller = FakeController([
            FakeControllerGroup('optDevices', 'battleBoosters'),
            FakeControllerGroup('shells'),
        ])
        return FakePresenter(model, controller)

    def test_flattens_every_section_across_groups(self):
        found = panel_watch.sample(self.presenter())['sections']
        self.assertEqual(found, [('optDevices', 3), ('battleBoosters', 1), ('shells', 3)])

    def test_reads_what_the_controller_expects(self):
        found = panel_watch.sample(self.presenter())['expected']
        self.assertEqual(found, ['optDevices', 'battleBoosters', 'shells'])

    def test_a_presenter_that_answers_nothing_still_samples(self):
        # This runs inside the client's view lifecycle; a half-built panel must not raise.
        found = panel_watch.sample(object())
        self.assertEqual(found['sections'], [])
        self.assertIsNone(found['disabled'])


class NoteTest(unittest.TestCase):

    def setUp(self):
        self.logger = SilentLogger()
        model = FakeModel([FakeGroup([FakeSection('battleBoosters', 1)])])
        controller = FakeController([FakeControllerGroup('battleBoosters')])
        self.panel = FakePresenter(model, controller)

    def test_logs_the_first_reading(self):
        panel_watch.note(self.panel, 'poll', self.logger)
        self.assertEqual(len(self.logger.infos), 1)

    def test_a_stable_panel_stops_logging(self):
        # A once-per-second poll must not fill the log while nothing is happening.
        for _ in range(5):
            panel_watch.note(self.panel, 'poll', self.logger)
        self.assertEqual(len(self.logger.infos), 1)

    def test_warns_the_moment_the_panel_empties(self):
        panel_watch.note(self.panel, 'before loadout bar repair', self.logger)
        self.panel._model = FakeModel([])
        panel_watch.note(self.panel, 'after loadout bar repair', self.logger)
        self.assertEqual(len(self.logger.warnings), 1)
        self.assertIn('no sections', self.logger.warnings[0])
        self.assertIn('after loadout bar repair', self.logger.warnings[0],
                      'the line has to say which side of the repair it came from')

    def test_the_timer_never_scans_for_panels(self):
        # The regression that made the login screen unplayable: "nothing cached is live" is the
        # permanent state outside a garage, so a scan on the cache-miss path meant walking every
        # tracked object in the client once a second. With no panel discovered, a poll must do
        # nothing at all and say nothing.
        del panel_watch._presenter_cache[:]
        panel_watch.note_all('poll', self.logger)
        self.assertEqual(panel_watch._presenter_cache, [])
        self.assertEqual(self.logger.infos, [])
        self.assertEqual(self.logger.warnings, [])
        self.assertEqual(self.logger.exceptions, [])

    def test_the_timer_reads_panels_a_repair_already_found(self):
        panel_watch._presenter_cache[:] = [self.panel]
        try:
            panel_watch.note_all('poll', self.logger)
            self.assertEqual(len(self.logger.infos), 1)
        finally:
            del panel_watch._presenter_cache[:]

    def test_a_torn_down_panel_drops_out_of_the_cache(self):
        # Leaving the garage finalizes the panel, which drops its interacting item.
        self.panel._vehInteractingItem = None
        panel_watch._presenter_cache[:] = [self.panel]
        try:
            panel_watch.note_all('poll', self.logger)
            self.assertEqual(panel_watch._presenter_cache, [])
            self.assertEqual(self.logger.infos, [])
        finally:
            del panel_watch._presenter_cache[:]

    def test_disabling_the_probe_silences_it(self):
        panel_watch.ENABLED = False
        try:
            panel_watch.note(self.panel, 'poll', self.logger)
            self.assertEqual(self.logger.infos, [])
            self.assertEqual(self.logger.warnings, [])
        finally:
            panel_watch.ENABLED = True


if __name__ == '__main__':
    unittest.main()
