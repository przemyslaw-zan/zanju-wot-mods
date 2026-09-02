# -*- coding: utf-8 -*-
"""Whether the battle mode the player has picked earns campaign progress.

Only a random battle counts towards a personal mission, so the banners belong to that mode and
to no other. This is one half of the widgets' visibility. The other half is whether the garage
is on screen at all -- see route_gate.

The garage cannot answer this, which is why the mode is not read off the lobby route. Onslaught,
Frontline, Steel Hunter and Last Stand each bring a garage of their own, but Ranked, Mapbox,
Maps Training and the training rooms all share the default one. A seasonal garage goes the other
way and changes the space while the mode stays Random Battles. Route and mode are two facts, and
neither stands in for the other.

`FunctionalState.isQueueSelected(QUEUE_TYPE.RANDOMS)` is the client's own question. It is the
call `_RandomQueueItem._update` makes to light the Random Battles entry in the mode selector, so
the banners follow that entry exactly. It answers True for a platoon as well, because
`QUEUE_TYPE_TO_PREBATTLE_TYPE` pairs the randoms queue with the squad prebattle.

The mode is followed with the client's own listener interface. `IGlobalListener` carries the
`onPrbEntitySwitched` the dispatcher calls once a mode switch has settled, and the dispatcher
refuses a listener that is not one of those, so the subclass is built at install time rather
than here.

Every client import stays inside a function, so this module is importable outside the game.
"""
from __future__ import absolute_import, print_function, unicode_literals

_callback = None
_listener = None
# Whether the selected mode is random battles. None means the question has not been answered
# yet -- before the lobby has a dispatcher, or after a read failed.
_is_random = None


def is_visible():
    """Whether the widgets belong to the mode the player has picked.

    Degrades to True while the answer is unknown, which is the same choice route_gate makes:
    banners shown in the wrong mode are a smaller fault than banners that never appear.
    """
    return True if _is_random is None else _is_random


def install(logger, on_change):
    """Read the mode and subscribe to mode changes, replacing any earlier subscription.

    Safe to call repeatedly, and it has to be. The dispatcher belongs to the lobby, so it is a
    different object after every teardown, and the subscription made to the last one is gone
    with it.
    """
    global _callback, _listener, _is_random
    _callback = on_change

    was_visible = is_visible()
    # Re-read every time, subscribed or not. The mode can change while the mod holds no
    # subscription, and no switch is coming to announce what it missed.
    _is_random = _read_mode(logger)

    if _listener is None:
        _listener = _build_listener(logger)
    if _listener is not None:
        _subscribe(logger)

    visible = is_visible()
    if visible != was_visible and _callback is not None:
        _callback(visible)


def uninstall(logger):
    global _callback, _listener, _is_random
    if _listener is not None:
        try:
            _listener.stopGlobalListening()
        except Exception:
            pass
    _callback = None
    _listener = None
    _is_random = None


def _read_mode(logger):
    """Whether the mode selector stands on Random Battles, or None when it cannot be read.

    None rather than a guess: the dispatcher does not exist until the lobby starts, and that is
    not a failure. `is_visible` turns both cases into the same answer.
    """
    try:
        from constants import QUEUE_TYPE
        from gui.prb_control.dispatcher import g_prbLoader
        dispatcher = g_prbLoader.getDispatcher()
        if dispatcher is None:
            return None
        return bool(dispatcher.getFunctionalState().isQueueSelected(QUEUE_TYPE.RANDOMS))
    except Exception:
        logger.exception('Failed to read the selected battle mode; the widgets stay visible')
        return None


def _build_listener(logger):
    """One listener object of the class the dispatcher accepts.

    `ListenersCollection.addListener` tests the class with `isinstance`, so an object carrying
    the right method is refused unless it is an `IGlobalListener`. The interface declares every
    callback the dispatcher may invoke, and it declares them as no-ops, so this overrides the
    one it wants and inherits the rest.
    """
    try:
        from gui.prb_control.entities.listener import IGlobalListener

        class _ModeListener(IGlobalListener):
            def onPrbEntitySwitched(self):
                _on_mode_switched(logger)

        return _ModeListener()
    except Exception:
        logger.exception('Failed to build the battle mode listener; the mode gate is off')
        return None


def _subscribe(logger):
    """Add the listener to the dispatcher, unless it is already on this one.

    The test is not optional. `addListener` logs an error over a listener it already holds, and
    a teardown leaves ours attached to a dispatcher that no longer exists -- so the answer
    differs between the two dispatchers and has to be asked of the current one.
    """
    try:
        dispatcher = _listener.prbDispatcher
        if dispatcher is None:
            # Called outside the lobby, or before it finished starting. The next hangar build
            # tries again, and until one succeeds `is_visible()` stays True.
            return
        if dispatcher.hasListener(_listener):
            return
        _listener.startGlobalListening()
        logger.info('Subscribed to battle mode changes (random battles: %s)', _is_random)
    except Exception:
        logger.exception('Failed to subscribe to battle mode changes; the mode gate is off')


def _on_mode_switched(logger):
    global _is_random
    mode = _read_mode(logger)
    if mode == _is_random:
        return
    was_visible = is_visible()
    _is_random = mode
    visible = is_visible()
    if visible != was_visible and _callback is not None:
        _callback(visible)
