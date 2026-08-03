# -*- coding: utf-8 -*-
"""Reads the player's directives from the running client.

"Directive" is the player-facing name; internally they are **battle boosters** — equipment
artefacts (`GUI_ITEM_TYPE.BATTLE_BOOSTER`), which is why they share the account inventory's
equipment section rather than having one of their own. The game's own hangar panel for them
is `InstructionsPresenter`.

Two things about the depot are worth knowing when reading the numbers:

* Fitting a directive **moves it out of the depot** — the inventory count drops by one and
  comes back when it is removed. The fitted directive is therefore not part of the depot
  totals reported here; its own row is flagged `equipped` instead.
* The crew/equipment split is the same test the game itself uses to fill its two directive
  tabs (`CrewBattleBoosterProvider` vs `OptDeviceBattleBoosterProvider`): a directive is a
  crew one when it carries the `crewSkillBattleBooster` tag.

Every client import is done lazily inside a try/except so this module stays importable
outside the game and degrades to an empty snapshot instead of breaking the view it feeds.
"""
from __future__ import print_function, unicode_literals

import math

# `tankmen.MAX_SKILL_LEVEL`. Kept as a plain number so the arithmetic below stays testable
# outside the game; the client constant is only read where the crew is.
MAX_SKILL_LEVEL = 100

CATEGORY_EQUIPMENT = 'equipment'
# A crew directive does one of two things depending on the crew currently in the tank: if the
# perk it targets is not trained to 100%, fitting it grants that perk outright; if the perk is
# already at 100%, it improves the perk's effect instead. The client decides this with
# `isAffectedSkillLearnt(vehicle)` — the same call behind its own two slot highlights
# (BATTLE_BOOSTER vs BATTLE_BOOSTER_CREW_REPLACE).
CATEGORY_CREW_IMPROVE = 'crewImprove'
CATEGORY_CREW_GRANT = 'crewGrant'

# Display order: equipment first, then the two crew effects.
CATEGORY_ORDER = (CATEGORY_EQUIPMENT, CATEGORY_CREW_IMPROVE, CATEGORY_CREW_GRANT)


def empty_snapshot():
    """The shape `collect()` returns, with nothing in it."""
    return {
        'vehicleName': '',
        'hasVehicle': False,
        'autoResupply': None,
        'resupplyWarning': False,
        'categories': [
            {'category': name, 'total': 0, 'directives': []} for name in CATEGORY_ORDER
        ],
    }


def collect(logger, show_unowned=False):
    """Snapshot of the depot's directives plus what is fitted to the selected vehicle.

    With `show_unowned` the listing also carries directives that fit the tank but that the
    player owns none of, so they can be bought from the window. They are flagged `owned:
    False` rather than kept in a separate section, because what a directive *does* is what the
    sections are for -- owning it is a property of the row.

    Returns the `empty_snapshot()` shape when the client is not available, so callers never
    have to special-case a missing garage.
    """
    items = _battle_booster_items(logger)
    if items is None:
        return empty_snapshot()

    vehicle = _current_vehicle(logger)
    equipped_int_cds = _equipped_int_cds(vehicle, logger)

    grouped = dict((name, []) for name in CATEGORY_ORDER)
    for item in items:
        entry = _describe(item, vehicle, equipped_int_cds, show_unowned, logger)
        if entry is None:
            continue
        grouped[entry['category']].append(entry)

    categories = [_category(name, grouped[name]) for name in CATEGORY_ORDER]
    auto = auto_resupply(vehicle, logger)
    return {
        'vehicleName': _vehicle_name(vehicle),
        'hasVehicle': vehicle is not None,
        'autoResupply': auto,
        'resupplyWarning': warns_about_resupply(auto, categories),
        'categories': categories,
    }


def warns_about_resupply(auto, categories):
    """Whether leaving auto-resupply on will cost the player money after the next battle.

    Fitting a directive moves it out of the depot, so a fitted directive whose depot count
    reads zero is the last one the player owns. Auto-resupply normally just refills from the
    depot; with nothing left to take it buys a replacement with in-game currency instead. That
    single combination is the one where the setting quietly spends something, which is what
    makes it worth warning about rather than describing.
    """
    if not auto:
        return False
    for group in categories:
        for entry in group['directives']:
            if entry['equipped'] and entry['count'] <= 0:
                return True
    return False


def auto_resupply(vehicle, logger):
    """Whether this vehicle refills its directive automatically after a battle.

    A per-vehicle setting, not an account-wide one: it is a bit in the vehicle's inventory
    settings (`VEHICLE_SETTINGS_FLAG.AUTO_EQUIP_BOOSTER`), which is why it is reported for the
    tank currently in the garage rather than once for the window. When it is on, the directive
    is taken from the depot after the battle, or bought if the depot has run out.

    Returns None when there is nothing to report — no vehicle, or a client that would not
    answer — so a failure never reads as "disabled" and never offers a toggle.
    """
    if vehicle is None:
        return None
    try:
        # A method here, unlike the sibling `isAutoLoad` / `isAutoEquip` properties on the
        # same class; accept either shape rather than depend on that staying true.
        value = getattr(vehicle, 'isAutoBattleBoosterEquip', None)
        if value is None:
            return None
        return bool(value() if callable(value) else value)
    except Exception:
        logger.exception('Failed to read the auto-resupply setting')
        return None


def _category(name, entries):
    # The total counts directives owned, not distinct types.
    if name == CATEGORY_CREW_GRANT:
        entries.sort(key=_by_gain)
    else:
        # By name, so the list does not reshuffle between refreshes.
        entries.sort(key=lambda entry: entry['name'].lower())
    return {
        'category': name,
        'total': sum(entry['count'] for entry in entries),
        'directives': entries,
    }


def _is_purchasable(item):
    """Whether the game's own buy dialog could actually price this directive.

    Some directives are reward or event only and answer with an all-zero price. That is not a
    cosmetic gap: `BoosterBuyWindowView` divides by the current price to size its quantity
    selector, and by the default price to work out the discount percentage, so opening it for
    an unpriced directive raises ZeroDivisionError inside the game's own view -- and being
    wg_async, that surfaces as a broken modal rather than something this mod can catch.

    The window still lists an unpurchasable directive -- a tile that quietly went missing would
    be more confusing than one that says why it cannot be clicked -- but it says "purchase not
    available" instead of offering the dialog, and does nothing when clicked.
    """
    try:
        price = item.getBuyPrice(preferred=False)
        currency = price.getCurrency(byWeight=True)
        return (price.price.getSignValue(currency) > 0
                and price.defPrice.getSignValue(currency) > 0)
    except Exception:
        return False


def _by_gain(entry):
    """Order for the "boost perk to 100%" section: biggest gain first.

    In this one section the figure is the whole point, so a directive worth +80% should not sit
    below one worth +5% because of its name. A row whose gain could not be read sorts last
    rather than as zero -- unknown is not the same as worthless -- and the name breaks ties so
    the order stays stable between refreshes.
    """
    gain = entry.get('gain')
    if gain is None:
        return (1, 0, entry['name'].lower())
    return (0, -gain, entry['name'].lower())


def _describe(item, vehicle, equipped_int_cds, show_unowned, logger):
    """One row for the window, or None for a directive it should not list."""
    try:
        count = int(getattr(item, 'inventoryCount', 0) or 0)
        int_cd = int(item.intCD)
    except Exception:
        logger.exception('Failed to read a directive from the inventory')
        return None

    equipped = int_cd in equipped_int_cds
    owned = count > 0 or equipped
    if not owned and not show_unowned:
        # The items cache lists every directive that exists, including ones never bought.
        return None

    if not equipped and not _is_usable_on(item, vehicle):
        # Directives that cannot go on this tank are left out entirely; the fitted one always
        # stays so the window never hides what is actually mounted.
        return None

    category = _category_of(item, vehicle)
    return {
        'intCD': int_cd,
        'name': _user_name(item),
        'icon': _icon_name(item),
        'count': count,
        'owned': owned,
        # Only asked about a directive the player owns none of, since that is the only case
        # where the window offers to buy one. Owned rows are always actionable: they fit.
        'purchasable': True if owned else _is_purchasable(item),
        'category': category,
        'equipped': equipped,
        # Only meaningful where fitting the directive takes the perk to 100%; in the other
        # two sections there is no "distance to full" to report.
        'gain': _skill_gain(item, vehicle) if category == CATEGORY_CREW_GRANT else None,
    }


def skill_gain_from_level(level):
    """Percent a "boost perk to 100%" directive would add, given the crew's current level.

    `tankmen.NO_SKILL` is -1, meaning the crew has none of the skill at all rather than zero
    percent of it; both give a full 100% gain, so a negative level is floored to zero rather
    than added to the total.

    The crew level is an average across the crew and so a float, while the badge reports whole
    percent. Fractions round **up**, so a perk that is a hair short of trained still reads as
    `+1%` rather than disappearing into `+0%` and looking like it does nothing.
    """
    if level is None:
        return None
    try:
        level = float(level)
    except (TypeError, ValueError):
        return None
    if level < 0:
        level = 0.0
    return max(0, min(MAX_SKILL_LEVEL, int(math.ceil(MAX_SKILL_LEVEL - level))))


def _skill_gain(item, vehicle):
    """How much of the targeted perk this directive would add, in percent.

    `crewMemberRealSkillLevel` is the same call the game uses for its own crew readouts: it
    averages the skill across the crew members it applies to. `shouldIncrease=False` asks for
    the crew as it stands, without any fitted booster's own contribution folded in -- otherwise
    the gain would be measured against a value that already includes the thing being offered.
    """
    if vehicle is None:
        return None
    try:
        from gui.shared.gui_items.Tankman import crewMemberRealSkillLevel
        skill_name = item.getAffectedSkillName()
        if not skill_name:
            return None
        return skill_gain_from_level(
            crewMemberRealSkillLevel(vehicle, skill_name, shouldIncrease=False))
    except Exception:
        # Reported as "no figure" rather than a wrong one; the tile still renders.
        return None


def _battle_booster_items(logger):
    """Every battle booster the client knows about, or None without a client."""
    try:
        from gui.shared.gui_items import GUI_ITEM_TYPE
        from gui.shared.utils.requesters.ItemsRequester import REQ_CRITERIA
        from helpers import dependency
        from skeletons.gui.shared import IItemsCache
        items_cache = dependency.instance(IItemsCache)
        criteria = REQ_CRITERIA.BATTLE_BOOSTER.ALL
        return list(items_cache.items.getItems(GUI_ITEM_TYPE.BATTLE_BOOSTER, criteria).values())
    except Exception:
        logger.exception('Failed to read directives from the items cache')
        return None


def _current_vehicle(logger):
    """The vehicle selected in the garage, or None when there is none."""
    try:
        from CurrentVehicle import g_currentVehicle
        if not g_currentVehicle.isPresent():
            return None
        return g_currentVehicle.item
    except Exception:
        logger.exception('Failed to read the current vehicle')
        return None


def _equipped_int_cds(vehicle, logger):
    if vehicle is None:
        return frozenset()
    try:
        installed = vehicle.battleBoosters.installed.getItems()
        return frozenset(int(item.intCD) for item in installed if item is not None)
    except Exception:
        logger.exception('Failed to read the fitted directive')
        return frozenset()


def _category_of(item, vehicle):
    """Which section a directive belongs in, given the crew currently in the tank."""
    if not _is_crew(item):
        return CATEGORY_EQUIPMENT
    return CATEGORY_CREW_IMPROVE if _is_skill_learnt(item, vehicle) else CATEGORY_CREW_GRANT


def _is_skill_learnt(item, vehicle):
    """Whether the perk this crew directive targets is already trained to 100%."""
    if vehicle is None:
        return False
    try:
        return bool(item.isAffectedSkillLearnt(vehicle))
    except Exception:
        return False


def _is_crew(item):
    try:
        return bool(item.isCrewBooster())
    except Exception:
        return False


def _is_usable_on(item, vehicle):
    """Whether this directive can go on the selected vehicle.

    Delegates to the client's own check, which validates crew directives against the crew's
    skills and equipment directives against the mounted optional devices.
    """
    if vehicle is None:
        return False
    try:
        return bool(item.isAffectsOnVehicle(vehicle))
    except Exception:
        return False


def _icon_name(item):
    """Bare icon name, e.g. "gunner_focus".

    The window turns it into `R.images.gui.maps.icons.artefact.<name>`, the resource form
    Gameface resolves; hyphens are not valid in a resource path, matching what the client's
    own icon lookup does.
    """
    try:
        name = getattr(item.descriptor, 'iconName', '') or ''
    except Exception:
        return ''
    return '{0}'.format(name).replace('-', '_')


def _user_name(item):
    for attribute in ('userName', 'shortUserName', 'name'):
        try:
            value = getattr(item, attribute, None)
            if value:
                return '{0}'.format(value)
        except Exception:
            continue
    return ''


def _vehicle_name(vehicle):
    if vehicle is None:
        return ''
    try:
        return '{0}'.format(vehicle.userName or '')
    except Exception:
        return ''
