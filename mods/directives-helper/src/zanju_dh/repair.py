# -*- coding: utf-8 -*-
"""Finds and clears the invalid directive state that version 1.0.1 could leave on a tank.

That version showed the window for tanks with no directives slot, and fitting a directive on
one of them made the account record directives the tank cannot hold. The tank then sits in the
garage looking normal, and the server refuses it a battle: the client sends it to the queue,
the server declines to assemble the arena, and the player lands back in the garage half a
minute later with no message. `slot_gate` stops this happening again. This module is for the
tanks it has already happened to. See issue #18.

**What the invalid state looks like.** The account's inventory records two keys per tank,
`boosters` (the fitted directive) and `boostersLayout` (what the game refills after a battle).
On the tanks this hit, both keys hold the tank's *consumables* -- `(1275, 763, 2555)` on the
tank behind this module, whose directive capacity is zero. The client says so itself on every
rebuild of that tank:

    WARNING: [gui.shared.gui_items.vehicle_equipment] Length of arguments is not valid,
    args: (1275, 763, 2555) for equipment: _ExpendableEquipment, ..., capacity: 0

`_Equipment.__init__` truncates the list to the capacity, so the gui item shows nothing fitted
and no client screen can reach the entries. Only the raw inventory still carries them, which is
what this module reads.

**What clears it.** One command:
`inventory.setAndFillLayouts(invID, None, [0, 0], EQUIPMENT_TYPES.battleBoosters)` -- a
directive layout holding one empty slot. `(0, 0)` is how the client's own layout builders write
an empty slot: `item.defaultLayoutValue if item is not None else (0, 0)`.

This is a verified result rather than a deduction. On the tank behind this module the server
answered `RES_SUCCESS` and sent the update that cleared it, and the tank took a battle
immediately afterwards (WoT 2.3.1.3, EU, 25 August 2026):

    inventory: {1: {'boostersLayout': {686: [[0]]}, 'boosters': {686: []}},
                11: {763: 319, 2555: 1, 1275: 1}}

Section 11 is the depot, so the three items the server had been holding as that tank's
directives came back to it.

An **empty** array does not work, which is worth writing down because it is the obvious thing
to try. Version 1.0.3 sent `setAndFillLayouts(invID, None, [], battleBoosters)`, the server
answered `RES_SUCCESS`, and nothing happened: no inventory update followed and the tank read
back unchanged. `Inventory.__setAndFillLayoutsOnShopSynced` encodes `None` and `[]`
identically, as a length of zero, so an empty array is how the client says "this command does
not carry that section" rather than "make that section empty".

The mod tries nothing else. A second command that has never had to run would be a write to
somebody else's account that nobody has watched the server answer, which is worse than a log
line saying what is left. If this one stops working, the log below says so and names the tank,
which is what a report needs.

What keeps the command safe to send unasked:

* It names one section. Both of the client's own callers pass `None` for the section they do
  not touch, and the update diff after the player fits a directive carries only the `boosters`
  keys, so it cannot reach shells, consumables or optional devices.
* It carries no item, so the "fill" half has nothing to buy. No resource can be spent.
* The mod sends it to a tank only when that tank's directive capacity is zero, and once per
  session per tank.

A repaired tank keeps a one-slot layout, `boostersLayout: [[0]]`, which the client goes on
truncating to a capacity of zero -- so it goes on logging `args: (None,)` for that tank once
per rebuild. Nothing hangs on it, and `recorded_directives` reads that slot as empty, so the
tank is never asked about again.
"""
from __future__ import print_function, unicode_literals

# An empty inventory slot reads as `items.vehicles.ZERO_COMP_DESCR`, which is 0. Kept as a
# plain number so the filtering below stays testable outside the game.
EMPTY_INT_CD = 0

# Seconds to wait after the server answers before reading the tank back. The answer and the
# inventory update that carries the change are separate messages, and this only reads local
# state, so it waits well past both rather than racing them.
_VERIFY_DELAY = 3.0

# invID -> name, for the tanks this session has asked the server to clear.
_asked = {}
# invIDs asked about whose verdict is not in the log yet.
_pending = set()
# invIDs whose verdict is in the log, so neither result repeats.
_reported = set()
# Set once a scan of a populated garage has nothing left to do, which ends the scanning. Only
# a version of this mod that cannot run beside this one writes the state this looks for, so a
# garage that is clean at login stays clean, and a tank the server would not repair stays
# broken however many times it is asked.
_scanning_done = False


def recorded_directives(vehicle_data):
    """Every directive intCD the inventory records for one tank, fitted or queued to refill.

    Empty slots read as 0 and stay out of the answer. This reads both keys because the client
    parses both, and either one costs the tank its battles.
    """
    found = []
    for int_cd in _items_in(vehicle_data.get('boosters')):
        if int_cd not in found:
            found.append(int_cd)
    for setup in _iterable(vehicle_data.get('boostersLayout')):
        for int_cd in _items_in(setup):
            if int_cd not in found:
                found.append(int_cd)
    return tuple(found)


def invalid_directives(int_cds, slots):
    """Which of these records the tank cannot hold, given how many directive slots it has.

    Answers nothing for a tank with a slot, however its layout looks. This module describes
    only the one state the client itself calls impossible. A tank with a real slot is the
    game's business rather than the mod's.
    """
    return () if slots > 0 else tuple(int_cds)


def check(logger):
    """Clear the invalid state on any tank that has it, with one request per tank."""
    global _scanning_done
    if _scanning_done:
        return
    try:
        vehicles_seen, invalid = _find_invalid(logger)
    except Exception:
        logger.exception('Failed to check the garage for invalid directives')
        return

    for inv_id, name, int_cds in invalid:
        if inv_id in _asked:
            # Asked already. The read-back writes the verdict. This branch is what writes it
            # when the timer that would have done so never started.
            if inv_id not in _pending:
                _report_failure(inv_id, name, int_cds, logger)
            continue
        _asked[inv_id] = name
        logger.warning(
            'Found %d directive(s) recorded on %s (inventory id %s), which has no directives '
            'slot: %s', len(int_cds), name, inv_id, _list(int_cds))
        _clear(inv_id, name, logger)

    if not vehicles_seen or _pending:
        # Nothing to read yet, or an answer is still on its way. Either way there is more to do
        # on the next garage build.
        return
    if any(inv_id not in _reported for inv_id, _, _ in invalid):
        return
    _scanning_done = True
    if not invalid:
        logger.info('No tank in the garage records a directive it cannot hold')


def _report_repair(inv_id, logger):
    _pending.discard(inv_id)
    if inv_id in _reported:
        return
    _reported.add(inv_id)
    logger.info(
        '%s (inventory id %s) is repaired: the invalid directives are gone',
        _asked[inv_id], inv_id)


def _report_failure(inv_id, name, int_cds, logger):
    _pending.discard(inv_id)
    if inv_id in _reported:
        return
    _reported.add(inv_id)
    logger.warning(
        'The invalid directives on %s (inventory id %s) are still recorded (%s). The server '
        'kept them, so selling the tank and buying it back stays the only known fix.',
        name, inv_id, _list(int_cds))


def _clear(inv_id, name, logger):
    """Write a directive layout of one empty slot, then read the tank back."""
    import BigWorld
    from items import EQUIPMENT_TYPES

    def on_response(code, error='', ext=None):
        # `AccountCommands.isCodeValid`: anything below zero is a refusal. This logs the code
        # either way, because a request the server accepts and does not act on looks exactly
        # like one it never received -- which an earlier version of this repair turned out to
        # be.
        if code >= 0:
            logger.info('The server accepted the repair for %s (code %s)', name, code)
        else:
            logger.warning(
                'The server refused the repair for %s (code %s, %s)', name, code, error)
        _verify_later(inv_id, name, logger)

    _pending.add(inv_id)
    logger.info('Clearing the invalid directives on %s (inventory id %s)', name, inv_id)
    try:
        BigWorld.player().inventory.setAndFillLayouts(
            inv_id, None, [EMPTY_INT_CD, 0], EQUIPMENT_TYPES.battleBoosters, on_response)
    except Exception:
        _pending.discard(inv_id)
        logger.exception('Failed to send the directives repair for %s', name)


def _verify_later(inv_id, name, logger):
    """Read the tank back once the client has had time to apply whatever the server sent.

    The verdict cannot wait for the next garage build. The outcome worth diagnosing -- a
    request the server accepts and does not act on -- produces no inventory update, and so
    nothing that would prompt another check.
    """
    import BigWorld

    def verify():
        try:
            int_cds = recorded_directives(_records_of(inv_id))
        except Exception:
            _pending.discard(inv_id)
            logger.exception('Failed to read %s back after the directives repair', name)
            return
        if int_cds:
            _report_failure(inv_id, name, int_cds, logger)
        else:
            _report_repair(inv_id, logger)

    try:
        BigWorld.callback(_VERIFY_DELAY, verify)
    except Exception:
        # Left pending it would get no verdict at all. Dropped, the next garage build reports
        # it instead.
        _pending.discard(inv_id)
        logger.exception('Failed to schedule the check that reads %s back', name)


def _records_of(inv_id):
    """The raw inventory entry for one tank, as a dict of the keys it carries."""
    from gui.shared.gui_items import GUI_ITEM_TYPE
    from helpers import dependency
    from skeletons.gui.shared import IItemsCache
    items = dependency.instance(IItemsCache).items
    return items.inventory.getItems(GUI_ITEM_TYPE.VEHICLE, inv_id) or {}


def _find_invalid(logger):
    """How many tanks this read, and which of them record a directive they cannot hold.

    Reads the raw inventory rather than the gui items: building one gui item per tank in the
    garage to ask about a state almost none of them are in is work for nothing, and the gui
    item is the thing that hides the entries anyway -- it truncates them to the tank's capacity
    as the client builds it. The mod builds a gui item only for the tanks that record a
    directive at all, which is the same call the garage makes for each of them.
    """
    from gui.shared.gui_items import GUI_ITEM_TYPE
    from helpers import dependency
    from skeletons.gui.shared import IItemsCache
    items = dependency.instance(IItemsCache).items
    inventory = items.inventory.getItems(GUI_ITEM_TYPE.VEHICLE) or {}

    invalid = []
    for inv_id, vehicle_data in inventory.items():
        if not isinstance(vehicle_data, dict):
            continue
        recorded = recorded_directives(vehicle_data)
        if not recorded:
            continue
        try:
            vehicle = items.getVehicle(inv_id)
            if vehicle is None:
                continue
            int_cds = invalid_directives(recorded, len(vehicle.battleBoosters.installed))
        except Exception:
            logger.exception('Failed to read the directive slots of inventory vehicle %s', inv_id)
            continue
        if int_cds:
            invalid.append((inv_id, _name(vehicle, inv_id), int_cds))
    return len(inventory), invalid


def _name(vehicle, inv_id):
    for attribute in ('userName', 'shortUserName', 'name'):
        try:
            value = getattr(vehicle, attribute, None)
            if value:
                return '{0}'.format(value)
        except Exception:
            continue
    return 'vehicle {0}'.format(inv_id)


def _list(int_cds):
    return ', '.join(str(int_cd) for int_cd in int_cds)


def _items_in(value):
    return [int(int_cd) for int_cd in _iterable(value) if _is_item(int_cd)]


def _is_item(value):
    try:
        return int(value) != EMPTY_INT_CD
    except (TypeError, ValueError):
        return False


def _iterable(value):
    return value if isinstance(value, (list, tuple)) else ()
