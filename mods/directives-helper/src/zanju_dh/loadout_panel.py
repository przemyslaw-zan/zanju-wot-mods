# -*- coding: utf-8 -*-
"""Follows the garage's loadout panel: is it on screen, and does it offer directives.

The loadout panel is the bar along the bottom of the garage holding shells, consumables,
optional devices and directives. It is the right thing to key the window's visibility on,
because it answers both questions at once and answers them per game mode:

* **On screen** — the panel's presenter is loaded exactly while the panel is being shown, so
  its lifecycle is the visibility signal. Leaving the garage for another lobby screen tears it
  down; coming back builds a new one.
* **Offers directives** — the panel is built from `GroupData(groupID, sections)` records, and
  the directives slot exists precisely when `battleBoosters` is one of those sections. Every
  mode decides this the same way, through `AmmunitionGroupsController._getGroups()`:
  Onslaught reuses the random-battle groups (so directives apply), Fun Random builds its
  groups from the active sub-mode's configuration flag, Last Stand from the player's chosen
  panel preset. Asking the panel therefore covers modes that did not exist when this was
  written, and modes that change their mind while the player is standing in them.

The alternative — matching the lobby's route against a list of known garage routes — cannot
do this. Routes are mode-prefixed (`subScope/subLayer/comp7Light/hangar/{root}` rather than
`subScope/subLayer/hangar/{root}`), so every mode needs its own entry, and a route says
nothing about whether that mode's panel actually carries directives.

Every client import stays inside `install()` so this module is importable outside the game.
"""
from __future__ import print_function, unicode_literals

import weakref

# `TankSetupConstants.BATTLE_BOOSTERS`. Compared as a plain string because the panel's own
# section lists hold strings; the constant is imported in install() only to check it still
# matches, so a rename in a future client is reported rather than silently ignored.
BATTLE_BOOSTERS_SECTION = 'battleBoosters'

_PRESENTER_MODULE = 'gui.impl.lobby.hangar.presenters.loadout_presenter'
_PRESENTER_CLASS = 'LoadoutPresenter'
# Patched on the base class, which every mode's panel subclasses without overriding these.
_HOOKS = ('_onLoading', '_updateAmmunitionGroupsController', '_finalize')

_patched = []
# Live panels -> whether that panel offers directives. Weak so a panel that somehow skipped
# its teardown hook still drops out when the client collects it, rather than pinning the
# window open forever.
_panels = weakref.WeakKeyDictionary()
_callback = None
_update_callback = None
_reported = None


def install(logger, on_change, on_update=None):
    """Start following the loadout panel.

    `on_change(visible)` fires when the answer to "should the window be shown" flips.
    `on_update()` fires whenever the panel re-reads the vehicle, which is the client telling
    us the loadout it is describing has changed -- a different tank, a different setup, an
    item installed. It is worth listening to because it belongs to the panel's own lifetime:
    unlike a subscription on `g_currentVehicle`, whose event manager the client clears on
    every lobby teardown, this hook cannot go stale while the panel exists.
    """
    global _callback, _update_callback
    _callback = on_change
    _update_callback = on_update

    if _patched:
        return True

    presenter_class = _import_presenter(logger)
    if presenter_class is None:
        return False

    _check_section_name(logger)

    for name in _HOOKS:
        _patch(presenter_class, name, logger)
    logger.info('Following the loadout panel for directives availability')
    return True


def uninstall(logger):
    global _callback, _update_callback, _reported
    while _patched:
        owner, name, original = _patched.pop()
        try:
            setattr(owner, name, original)
        except Exception:
            logger.exception('Failed to restore %s.%s', getattr(owner, '__name__', owner), name)
    _panels.clear()
    _callback = None
    _update_callback = None
    _reported = None


def is_visible():
    """True while a loadout panel offering directives is on screen.

    Degrades to True when the panel could not be followed at all: a window that shows in the
    wrong place is a nuisance, one that never shows is a broken mod.
    """
    if not _patched:
        return True
    return any(_panels.values())


def offers_directives(presenter, logger):
    """Whether this panel carries the directives slot.

    Reads the panel's own group definitions rather than reproducing the decision. Each mode
    answers differently and some answer differently over time, so the only reliable source is
    the object that just built the panel.
    """
    try:
        controller = presenter._getGroupController
        if controller is None:
            # No vehicle in the garage yet: the panel exists but has nothing to describe.
            return False
        for group in controller._getGroups():
            if BATTLE_BOOSTERS_SECTION in tuple(group.sections):
                return True
        return False
    except Exception:
        logger.exception('Failed to read the loadout panel sections')
        return False


def _track(presenter, logger):
    _panels[presenter] = offers_directives(presenter, logger)
    _notify(logger)
    if _update_callback is not None:
        try:
            _update_callback()
        except Exception:
            logger.exception('Failed to refresh from the loadout panel')


def _forget(presenter, logger):
    try:
        del _panels[presenter]
    except KeyError:
        pass
    _notify(logger)


def _notify(logger):
    global _reported
    visible = is_visible()
    if visible == _reported:
        return
    _reported = visible
    logger.info('Loadout panel offers directives: %s (%d panel(s) on screen)',
                visible, len(_panels))
    if _callback is not None:
        try:
            _callback(visible)
        except Exception:
            logger.exception('Failed to apply the loadout panel visibility')


def _patch(presenter_class, name, logger):
    original = getattr(presenter_class, name)
    teardown = name == '_finalize'

    def hooked(self, *args, **kwargs):
        if teardown:
            # Read the panel before the client tears it down; afterwards it has no controller.
            _forget(self, logger)
            return original(self, *args, **kwargs)
        result = original(self, *args, **kwargs)
        try:
            _track(self, logger)
        except Exception:
            logger.exception('Failed to follow the loadout panel')
        return result

    setattr(presenter_class, name, hooked)
    _patched.append((presenter_class, name, original))


def _import_presenter(logger):
    try:
        module = __import__(_PRESENTER_MODULE, globals(), locals(), [str(_PRESENTER_CLASS)])
        return getattr(module, _PRESENTER_CLASS)
    except Exception:
        logger.exception(
            'Could not follow the garage loadout panel; the window will always be visible')
        return None


def _check_section_name(logger):
    """Report a renamed section constant instead of silently never matching it."""
    try:
        from gui.impl.gen.view_models.views.lobby.tank_setup.tank_setup_constants import (
            TankSetupConstants)
        actual = TankSetupConstants.BATTLE_BOOSTERS
    except Exception:
        return
    if actual != BATTLE_BOOSTERS_SECTION:
        logger.warning(
            'The directives section is now named %r, not %r; the window will stay hidden',
            actual, BATTLE_BOOSTERS_SECTION)
