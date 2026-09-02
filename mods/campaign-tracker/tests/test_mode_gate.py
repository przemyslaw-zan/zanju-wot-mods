# -*- coding: utf-8 -*-
"""Tests for the battle-mode half of the widgets' visibility.

The banners belong to random battles and to no other mode. The client answers that through the
prebattle dispatcher, so the dispatcher, its functional state and the listener interface it
accepts are all stood in for here.

The stubs answer the way the client does: `isQueueSelected` is True for the queue the player
picked, and `addListener` refuses anything that is not an `IGlobalListener`.
"""
from __future__ import absolute_import, print_function, unicode_literals

import sys
import types
import unittest

from zanju_ct import mode_gate

# The client's own value for the random battles queue.
QUEUE_RANDOMS = 1
QUEUE_COMP7 = 29


class _Logger(object):
    def __init__(self):
        self.failures = []

    def info(self, message, *args):
        pass

    def exception(self, message, *args):
        self.failures.append(message)


class _IGlobalListener(object):
    """The half of the interface this mod uses."""

    @property
    def prbDispatcher(self):
        return _ModeTest.dispatcher

    def startGlobalListening(self):
        if self.prbDispatcher:
            self.prbDispatcher.addListener(self)

    def stopGlobalListening(self):
        if self.prbDispatcher:
            self.prbDispatcher.removeListener(self)

    def onPrbEntitySwitched(self):
        pass


class _State(object):
    def __init__(self, queue):
        self._queue = queue

    def isQueueSelected(self, queue_type):
        return self._queue == queue_type


class _Dispatcher(object):
    def __init__(self, queue=QUEUE_RANDOMS):
        self.queue = queue
        self.listeners = []

    def getFunctionalState(self):
        return _State(self.queue)

    def addListener(self, listener):
        # The client refuses a listener of the wrong class, and refuses a repeat.
        assert isinstance(listener, _IGlobalListener)
        assert listener not in self.listeners
        self.listeners.append(listener)

    def removeListener(self, listener):
        if listener in self.listeners:
            self.listeners.remove(listener)

    def hasListener(self, listener):
        return listener in self.listeners

    def switch(self, queue):
        """Change the mode the way the client does: set it, then notify."""
        self.queue = queue
        for listener in list(self.listeners):
            listener.onPrbEntitySwitched()


class _ModeTest(unittest.TestCase):
    """Stands in for the client modules `mode_gate` reads."""

    dispatcher = None

    def setUp(self):
        self._saved = {}
        _ModeTest.dispatcher = _Dispatcher()
        self.seen = []

        constants = types.ModuleType(str('constants'))

        class _QUEUE_TYPE(object):
            RANDOMS = QUEUE_RANDOMS

        constants.QUEUE_TYPE = _QUEUE_TYPE

        prb_dispatcher = types.ModuleType(str('gui.prb_control.dispatcher'))

        class _Loader(object):
            def getDispatcher(self):
                return _ModeTest.dispatcher

        prb_dispatcher.g_prbLoader = _Loader()

        listener = types.ModuleType(str('gui.prb_control.entities.listener'))
        listener.IGlobalListener = _IGlobalListener

        gui = types.ModuleType(str('gui'))
        prb_control = types.ModuleType(str('gui.prb_control'))
        entities = types.ModuleType(str('gui.prb_control.entities'))
        gui.prb_control = prb_control
        prb_control.dispatcher = prb_dispatcher
        prb_control.entities = entities
        entities.listener = listener

        for name, module in (
            ('constants', constants),
            ('gui', gui),
            ('gui.prb_control', prb_control),
            ('gui.prb_control.dispatcher', prb_dispatcher),
            ('gui.prb_control.entities', entities),
            ('gui.prb_control.entities.listener', listener),
        ):
            self._saved[name] = sys.modules.get(name)
            sys.modules[str(name)] = module

    def tearDown(self):
        mode_gate.uninstall(_Logger())
        _ModeTest.dispatcher = None
        for name, module in self._saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[str(name)] = module

    def _install(self, logger=None):
        mode_gate.install(logger or _Logger(), self.seen.append)


class ModeGateTest(_ModeTest):

    def test_random_battles_shows_the_widgets(self):
        self._install()
        self.assertTrue(mode_gate.is_visible())

    def test_every_other_mode_hides_them(self):
        self.dispatcher.queue = QUEUE_COMP7
        self._install()
        self.assertFalse(mode_gate.is_visible())

    def test_a_squad_still_counts_as_random_battles(self):
        # The client answers this itself: `isQueueSelected` maps the randoms queue to the squad
        # prebattle, so a platoon in random battles answers True without a test of its own here.
        self._install()
        self.assertTrue(mode_gate.is_visible())

    def test_switching_mode_reports_the_change_once(self):
        self._install()
        self.dispatcher.switch(QUEUE_COMP7)
        self.assertEqual(self.seen, [False])
        self.dispatcher.switch(QUEUE_COMP7)
        self.assertEqual(self.seen, [False])
        self.dispatcher.switch(QUEUE_RANDOMS)
        self.assertEqual(self.seen, [False, True])

    def test_installing_again_does_not_subscribe_twice(self):
        self._install()
        self._install()
        self.assertEqual(len(self.dispatcher.listeners), 1)

    def test_a_new_dispatcher_gets_its_own_subscription(self):
        # A lobby teardown replaces the dispatcher, and the old subscription goes with it.
        self._install()
        _ModeTest.dispatcher = _Dispatcher(QUEUE_COMP7)
        self._install()
        self.assertEqual(len(self.dispatcher.listeners), 1)
        self.assertFalse(mode_gate.is_visible())

    def test_no_dispatcher_yet_shows_the_widgets(self):
        _ModeTest.dispatcher = None
        logger = _Logger()
        self._install(logger)
        self.assertTrue(mode_gate.is_visible())
        self.assertEqual(logger.failures, [])

    def test_an_unreadable_mode_shows_the_widgets_and_is_logged(self):
        def _boom():
            raise ValueError('the client changed this call')

        self.dispatcher.getFunctionalState = _boom
        logger = _Logger()
        self._install(logger)
        self.assertTrue(mode_gate.is_visible())
        self.assertEqual(len(logger.failures), 1)

    def test_uninstalling_drops_the_subscription(self):
        self._install()
        mode_gate.uninstall(_Logger())
        self.assertEqual(self.dispatcher.listeners, [])
        self.assertTrue(mode_gate.is_visible())


if __name__ == '__main__':
    unittest.main()
