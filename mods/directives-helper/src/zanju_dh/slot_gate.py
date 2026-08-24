# -*- coding: utf-8 -*-
"""Whether the tank in the garage has a directives slot at all.

The third of the three questions that decide whether the window shows, and the only one about
the tank rather than about the mode or the screen. Neither of the other two can stand in for it:

* The loadout panel reports the sections its mode carries, and `battleBoosters` is one of them
  for every tank in the mode. `AmmunitionGroupsController`'s group definitions are a constant
  (`RANDOM_GROUPS`), so the panel lists the section for a tier II tank exactly as it does for a
  tier X one. What differs is how many slots the game then draws in it: `BaseBlock._createSlots`
  sizes the section by `len(vehicle.battleBoosters.installed)`, the number of battle-booster
  supply slots on the vehicle's descriptor (`vehDescr.type.supplySlots`, filtered by item type
  in `_EquipmentCollector._getCapacity`). Low-tier tanks have none, so the section is there and
  holds nothing.
* The route says which screen is on top. It does not change when the player picks another tank.

Getting this wrong is not cosmetic. Fitting a directive runs the client's own
`BuyAndInstallBattleBoostersProcessor`, which sends the tank's consumables and its directive
layout to the server as one array. On a tank with no directive slot that array does not line up
with what the server expects: in the report behind this gate, a **consumable** ended up recorded
as that tank's fitted directive (`boostersLayout: {349: [[1275]]}` in the client update diff,
where 1275 is an item the player never clicked), and the player could no longer take that tank
into battle. Selling it and buying it back was the only way out. See issue #18.

The processor does not refuse the request, and the game's own UI never makes it -- it draws no
slot to click. Guarding it is this mod's job, which is why `window_inject.equip_directive` asks
the same question again before it touches the layout: a window that is somehow on screen must
still not be able to corrupt a tank.

The client import stays inside `_current_vehicle()` so this module is importable outside the
game, and so a test can stand in for it.
"""
from __future__ import print_function, unicode_literals

import logging

_logger = logging.getLogger('zanju.directiveshelper')

# The last answer written to the log, so the line marks the changes rather than every refresh.
# Logging only. The decision itself is always read live, like the other two gates'.
_reported = None


def has_directive_slot(vehicle):
    """Whether this tank has a slot to put a directive in.

    Answers True for a tank it cannot read, and for no tank at all. Both are "not known to be
    slotless" rather than "slotless": a window that never shows is a broken mod, and whether
    there is a tank in the garage is the loadout panel's question -- its group controller is
    None until one arrives -- which this must not start answering as well.
    """
    if vehicle is None:
        return True
    try:
        return len(vehicle.battleBoosters.installed) > 0
    except Exception:
        # One attribute chain, so a failure here means the client changed shape rather than
        # that this tank is unusual. Worth reporting for that reason, and worth answering
        # True: the window belongs on screen unless the client says the slot is missing.
        _logger.exception('Failed to read the directive slots of the selected vehicle')
        return True


def is_visible():
    """Whether the window applies to the tank currently in the garage."""
    visible = has_directive_slot(_current_vehicle())
    _report(visible)
    return visible


def _report(visible):
    global _reported
    if visible == _reported:
        return
    _reported = visible
    _logger.info('Selected vehicle has a directives slot: %s', visible)


def _current_vehicle():
    """The tank in the garage, or None when there is none and when it cannot be read.

    A failure is not logged here: `collector` reads the same vehicle on every refresh and
    reports it there, and this runs on every visibility check.
    """
    try:
        from CurrentVehicle import g_currentVehicle
        if not g_currentVehicle.isPresent():
            return None
        return g_currentVehicle.item
    except Exception:
        return None
