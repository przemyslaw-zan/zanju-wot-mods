# -*- coding: utf-8 -*-
"""Whether the garage itself is on screen, or something is layered over it.

The loadout panel answers "does this mode offer directives"; it cannot answer this one. Opening
the playlist editor, the directives screen or the equipment screen does not tear the garage
down -- the loadout panel underneath stays alive and keeps reporting that it offers directives
-- so a window that follows only the panel stays up over all three.

What does change is the lobby's visible route, which is the client's own record of what the
player is actually looking at. `LobbyStateMachine.onVisibleRouteChanged` carries the state that
just became visible, and its `getStateID()` is the route path -- the same string the client
writes to `python.log` as "Visible route changed to: ...".

Read by route rather than by state class on purpose. The client's own consumers compare against
`getStateByCls(DefaultHangarState)`, but every mode's garage is a separately generated state
class, so that test answers False in Onslaught and in every other mode. The route string carries
the mode as a prefix and the screen as a suffix, which lets `is_bare_hangar_route` ignore the
first and read the second.
"""
from __future__ import print_function, unicode_literals

# The garage's own route ends here; anything after it is a screen drawn over the garage.
_HANGAR_SEGMENT = 'hangar'
# The leaf the state machine gives the garage when it is showing nothing in particular. Routes
# are reported both with and without it depending on whether the machine is mid-navigation.
_ROOT_LEAF = '{root}'

_callback = None
_machine = None
_route = None


def is_bare_hangar_route(route_path):
    """Whether this route is the garage with nothing layered over it.

    Examples, from a session that opened all three offenders:

        subScope/subLayer/hangar                          -> True
        subScope/subLayer/hangar/{root}                   -> True
        subScope/subLayer/comp7Light/hangar/{root}        -> True   (Onslaught)
        subScope/subLayer/hangar/editVehiclePlaylists     -> False
        subScope/subLayer/hangar/loadout/instructions     -> False
        subScope/subLayer/hangar/loadout/equipment        -> False

    A route with no `hangar` segment at all is not the garage either, so it answers False.
    """
    if not route_path:
        return False
    segments = route_path.split('/')
    if _HANGAR_SEGMENT not in segments:
        return False
    # The last one: a mode prefix could in principle repeat the word, and it is the deepest
    # occurrence that the screen hangs off.
    tail = segments[len(segments) - segments[::-1].index(_HANGAR_SEGMENT):]
    return not tail or tail == [_ROOT_LEAF]


def is_visible():
    """Whether the garage is what the player is looking at.

    Degrades to True until the first route arrives: the window is gated on the loadout panel as
    well, and a garage that was already up when the mod loaded would otherwise stay hidden until
    the player navigated somewhere and back.
    """
    return True if _route is None else is_bare_hangar_route(_route)


def install(logger, on_change):
    """Subscribe to the lobby's visible-route changes, replacing any earlier subscription.

    Safe to call repeatedly, and it has to be, for two reasons that need different handling.
    The state machine belongs to the lobby app, so after a teardown it may be a different
    object -- but it may also be the *same* object with our handler already gone, because the
    lobby clears the `EventManager` that owns this event. `Event` is a list subclass whose
    `__iadd__` refuses a delegate it already holds, so the reliable test is whether the event
    still carries our handler, not whether the machine changed. Comparing machine identity
    looks equivalent and silently stops delivering routes for the rest of the session.
    """
    global _callback, _machine, _route
    _callback = on_change
    try:
        machine = _get_machine()
    except Exception:
        logger.exception('Failed to reach the lobby state machine; route gating is off')
        return

    if machine is None:
        # Called outside the lobby, or before it finished starting. The next hangar build tries
        # again, and until one succeeds `is_visible()` stays True rather than hiding the window.
        return

    try:
        event = machine.onVisibleRouteChanged
    except Exception:
        logger.exception('Failed to reach the lobby route event; route gating is off')
        return

    # Re-read every time, subscribed or not. A teardown leaves `_route` naming the FINAL state
    # the lobby passes through on its way out, which is not a garage route -- so a stale copy
    # would keep the window hidden for the whole of the next session.
    was_visible = is_visible()
    _machine = machine
    _route = _read_route(machine, logger)

    if _on_route_changed not in event:
        try:
            machine.onVisibleRouteChanged += _on_route_changed
            logger.info('Subscribed to lobby route changes (at %s)', _route)
        except Exception:
            logger.exception('Failed to subscribe to lobby route changes; route gating is off')
            _machine = None
            return

    visible = is_visible()
    if visible != was_visible and _callback is not None:
        # Re-reading the route above can change the answer on its own, and no route change is
        # coming to announce it: the navigation that would have done so happened while the
        # subscription was dropped.
        _callback(visible)


def _get_machine():
    """The lobby's state machine, or None outside the lobby.

    Its own function so a test can stand in for it: `lobby_entry` is a client module, and this
    file is meant to stay importable under the test runner.
    """
    from gui.Scaleform.lobby_entry import getLobbyStateMachine
    return getLobbyStateMachine()


def uninstall(logger):
    global _callback, _machine, _route
    if _machine is not None:
        try:
            _machine.onVisibleRouteChanged -= _on_route_changed
        except Exception:
            pass
    _callback = None
    _machine = None
    _route = None


def _read_route(machine, logger):
    """The route showing right now, so a mid-session install does not start out blind."""
    try:
        info = machine.visibleRouteInfo
        state = info.state if info is not None else None
        return state.getStateID() if state is not None else None
    except Exception:
        logger.exception('Failed to read the current lobby route')
        return None


def _on_route_changed(route_info, *args):
    global _route
    try:
        state = getattr(route_info, 'state', None)
        route = state.getStateID() if state is not None else None
    except Exception:
        # A route we cannot read must not strand the window hidden.
        route = None
    if route == _route:
        return
    was_visible = is_visible()
    _route = route
    visible = is_visible()
    if visible != was_visible and _callback is not None:
        _callback(visible)
