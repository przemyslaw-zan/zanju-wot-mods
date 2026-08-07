# -*- coding: utf-8 -*-
"""Diagnostic probe for the hangar loadout bar, to catch it blanking as it happens.

The bar disappearing after a post-progression change made from this mod's overlay is a known
failure (see docs/reference/events-and-callbacks.md, "Refreshing The Hangar Bottom Bar"). It
produces no exception: the panel's view model is simply left describing nothing, so a log read
afterwards can only ever confirm that the repair ran. This samples what the panel actually
holds, brackets the repair with it, and logs the moment the answer changes.

What is sampled, and why each field earns its place:

* `section.getSlots()` per section is the array that empties when the bar blanks -- the
  symptom itself, rather than a proxy for it.
* the panel's own groups controller gives the sections that are *supposed* to be there, so a
  missing one is detectable without hardcoding what a mode's panel looks like.
* the panel renders from an `InteractingItem` holding a vehicle COPY, and the documented root
  cause is that copy's post-progression state drifting from the real vehicle's. Comparing the
  two says outright whether this is that bug or a new one.

Read-only throughout, and every read is guarded individually: this runs inside the client's own
view lifecycle, where raising would break the very panel it is watching.

The probe ships **off**: it is a diagnostic for a bug that has not been reproduced with it
running, and a release should not carry a timer and a log stream for something nobody is
watching.

It is armed without touching this file, by creating an empty marker file in the mod's AppData
directory (see `MARKER_NAME`). That keeps the developer's build byte-identical to the one users
get -- the difference lives entirely on the machine doing the hunting -- and, unlike editing
`ENABLED` here, leaves nothing in the working tree to forget about and commit by accident.

No client module is imported at import time, so this stays importable under the test runner.
"""
from __future__ import print_function, unicode_literals

import weakref

# Off in shipped builds; see the module docstring. Everything below is gated on it, so this
# single flag takes the timer, the gc discovery and the logging out together. `start` raises it
# when the marker file is present -- the source default stays False either way, which is what
# `ShippedStateTest` pins.
ENABLED = False

# Empty file in %APPDATA%/zanju_wot_mods_cache/research-progress-bar/. That directory already
# holds the config and the mode cache, so it survives a modpack reinstall and is nowhere near
# the source tree.
MARKER_NAME = 'probe.on'

# The panel can be rewritten from paths that do not run through this mod at all
# (`LoadoutPresenter.__onCacheResync` calls its private `__updateModel` directly), so
# bracketing the repair is not enough on its own to catch the moment it empties. The probe only
# logs when its reading changes, which makes a poll this slow effectively free.
POLL_SECONDS = 1.0

_PRESENTER_MODULE = 'gui.impl.lobby.hangar.presenters.loadout_presenter'
_PRESENTER_CLASS = 'LoadoutPresenter'

# Last logged description per panel, so a stable panel logs nothing at all.
_last = weakref.WeakKeyDictionary()
# Live presenters, cached like the InteractingItem wrappers are: the gc scan only reruns when
# the cache holds nothing live, which happens when the hangar view was rebuilt.
_presenter_cache = []
_poll_id = None


def _data_dir():
    """The mod's AppData directory, imported late.

    `storage` reaches `constants`, which imports a client module, so pulling it in at module
    scope would break the promise in the docstring above that this file stays importable
    outside the game. Kept as its own function so a test can stand in for it without having to
    import `storage` at all.
    """
    from .storage import resolve_mod_data_dir
    return resolve_mod_data_dir()


def marker_path():
    """Where the arming marker is looked for, or None without a resolvable AppData."""
    import os
    data_dir = _data_dir()
    return os.path.join(data_dir, MARKER_NAME) if data_dir else None


def is_armed():
    """Whether a developer has asked for the probe on this machine.

    Existence only -- the file's contents are never read, so `type nul > probe.on` arms it and
    deleting the file disarms it. Any failure answers no: a probe that cannot tell must stay
    off, since the shipped default is the safe one.
    """
    try:
        import os
        path = marker_path()
        return bool(path) and os.path.isfile(path)
    except Exception:
        return False


def start(logger):
    """Begin polling the panel. Safe to call more than once."""
    global _poll_id, ENABLED
    if not ENABLED and is_armed():
        # Checked once per session rather than per sample: this runs at mod init, and a probe
        # that re-stats a file on a 1s timer would be its own small version of the cost the
        # whole thing is meant to avoid.
        ENABLED = True
        logger.info('Loadout bar probe armed by %s', MARKER_NAME)
    if not ENABLED or _poll_id is not None:
        return

    try:
        import BigWorld
    except Exception:
        logger.info('No BigWorld timer; the loadout bar probe will only run around a repair')
        return

    def tick():
        global _poll_id
        _poll_id = None
        # discover=False: the timer only ever re-reads panels a repair already found.
        note_all('poll', logger)
        _poll_id = BigWorld.callback(POLL_SECONDS, tick)

    _poll_id = BigWorld.callback(POLL_SECONDS, tick)
    logger.info('Loadout bar probe running')


def stop():
    global _poll_id
    if _poll_id is None:
        return
    try:
        import BigWorld
        BigWorld.cancelCallback(_poll_id)
    except Exception:
        pass
    _poll_id = None
    del _presenter_cache[:]


def note_all(when, logger, discover=False):
    """Sample every live panel, logging the ones whose state changed.

    `discover` allows a one-off gc scan to find the panels, and belongs only where this mod is
    already doing click-frequency work. The timer must never ask for it -- see
    `_live_presenters`. Until a scan has happened this is a no-op, which is what makes the probe
    free at the login screen and in battle.
    """
    if not ENABLED:
        return
    try:
        for presenter in _live_presenters(logger, discover):
            note(presenter, when, logger)
    except Exception:
        logger.exception('Loadout bar probe failed')


def note(presenter, when, logger):
    """Sample one panel and log it if anything changed since the last look."""
    if not ENABLED:
        return
    try:
        reading = sample(presenter)
        text = describe(reading)
        if _last.get(presenter) == text:
            return
        _last[presenter] = text
        broken = looks_broken(reading)
        if broken:
            logger.warning('Loadout bar looks broken [%s]: %s -- %s', when, broken, text)
        else:
            logger.info('Loadout bar [%s]: %s', when, text)
    except Exception:
        # Never let the probe be the thing that breaks the panel.
        try:
            logger.exception('Loadout bar probe failed')
        except Exception:
            pass


def sample(presenter):
    """Everything worth knowing about the panel's current state, as plain values."""
    return {
        'disabled': _read(lambda: bool(presenter.getViewModel().getIsDisabled())),
        'vehicleId': _read(lambda: '{0}'.format(presenter.getViewModel().getVehicleId())),
        'sections': _sections(presenter),
        'expected': _expected(presenter),
        'copyIntCD': _read(lambda: presenter._vehInteractingItem.getItem().intCD),
        'copyAlive': _read(lambda: bool(presenter._vehInteractingItem.getItem().isAlive)),
        'liveIntCD': _read(_live_int_cd),
        'staleCopy': _stale_copy(presenter),
    }


def describe(reading):
    sections = reading['sections']
    shown = ','.join('{0}:{1}'.format(name, count) for name, count in sections) if sections else '-'
    return (
        'veh={0} copy={1} alive={2} live={3} disabled={4} stale={5} sections={6} expected={7}'
    ).format(
        reading['vehicleId'], reading['copyIntCD'], reading['copyAlive'], reading['liveIntCD'],
        reading['disabled'], reading['staleCopy'], shown,
        ','.join(reading['expected']) if reading['expected'] else '-')


def looks_broken(reading):
    """A short reason the panel is not describing what it should, or None when it is fine.

    Deliberately quiet unless the controller says there should be sections: a panel with
    nothing expected of it is a garage without a tank, not a fault.
    """
    expected = reading['expected']
    sections = reading['sections']
    if reading['staleCopy'] is True:
        return 'the panel is rendering from a stale vehicle copy'
    if not expected:
        return None
    if not sections:
        return 'the model carries no sections'
    names = [name for name, _ in sections]
    missing = [name for name in expected if name not in names]
    if missing:
        return 'sections missing from the model: {0}'.format(','.join(missing))
    if all(count == 0 for _, count in sections):
        return 'every section is empty'
    return None


def _sections(presenter):
    """(name, slot count) for every section the panel's view model currently holds."""
    found = []
    try:
        for group in presenter.getViewModel().getGroups():
            for section in group.getSections():
                found.append((_read(lambda s=section: '{0}'.format(s.getName())),
                              _read(lambda s=section: len(s.getSlots()))))
    except Exception:
        pass
    return found


def _expected(presenter):
    """Section names the panel's own controller says belong on it."""
    names = []
    try:
        controller = presenter._getGroupController
        if controller is None:
            return names
        for group in controller._getGroups():
            for name in tuple(group.sections):
                names.append('{0}'.format(name))
    except Exception:
        pass
    return names


def _stale_copy(presenter):
    """Whether the panel's vehicle copy disagrees with the real vehicle's post-progression.

    None when either side cannot be read, so "unknown" is never reported as "fine".
    """
    try:
        from CurrentVehicle import g_currentVehicle
        if not g_currentVehicle.isPresent():
            return None
        live = g_currentVehicle.item
        copy = presenter._vehInteractingItem.getItem()
        if copy is None or live is None or copy.intCD != live.intCD:
            return None
        return copy.postProgression.getState(True) != live.postProgression.getState(True)
    except Exception:
        return None


def _live_presenters(logger, discover):
    """Live LoadoutPresenter instances, cached.

    A presenter is live while it still holds its interacting item (`_finalize` drops it).

    `discover` decides whether a gc scan may run when nothing cached is live, and it must stay
    False on the timer. "Nothing cached is live" is the *permanent* state outside a garage --
    the login screen, a battle -- so a scan on the miss path is not an occasional cost that
    lands when the hangar is rebuilt, it is a scan of every tracked object in the client on
    every single tick. The scan is only affordable at click frequency, which is exactly where
    actions.py uses the same technique for the InteractingItem wrappers.
    """
    live = [p for p in _presenter_cache if _is_live(p)]
    if not live and discover:
        try:
            import gc
            module = __import__(_PRESENTER_MODULE, globals(), locals(), [str(_PRESENTER_CLASS)])
            presenter_class = getattr(module, _PRESENTER_CLASS)
            live = [obj for obj in gc.get_objects()
                    if isinstance(obj, presenter_class) and _is_live(obj)]
            if live:
                logger.info('Loadout bar probe: found %s live panel(s)', len(live))
        except Exception:
            logger.exception('Failed to scan for loadout panels')
            live = []

    _presenter_cache[:] = live
    return live


def _is_live(presenter):
    try:
        return presenter._vehInteractingItem is not None
    except Exception:
        return False


def _live_int_cd():
    from CurrentVehicle import g_currentVehicle
    if not g_currentVehicle.isPresent():
        return None
    return g_currentVehicle.item.intCD


def _read(getter):
    try:
        return getter()
    except Exception:
        return None
