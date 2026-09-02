# Directives And Battle Boosters

Reference notes for `directives-helper`: where the client keeps directives, what a crew
directive is actually worth on a given crew, and the three questions that decide whether the
mod's garage window is on screen.

Verified by decompiling the shipped scripts: most of this page against WoT client **2.3.1.1**,
and the mode and slot questions under [When the window shows](#when-the-window-shows) against
**2.3.1.3**.

## Where the data comes from

"Directive" is the player-facing name; internally they are **battle boosters**
(`GUI_ITEM_TYPE.BATTLE_BOOSTER`) — equipment artefacts, which is why they share the account
inventory's equipment section rather than having one of their own.

- **Depot** — `itemsCache.items.getItems(GUI_ITEM_TYPE.BATTLE_BOOSTER, ...)`, filtered to what
  is actually owned unless the "show unowned" option is on.
- **Buying** — `event_dispatcher.showBattleBoosterBuyDialog(intCD)`, which opens the client's
  own `BoosterBuyWindowView`: price, quantity selector and auto-resupply toggle, buying through
  `ModuleBuyer` only once the player accepts. Deliberately not a silent buy-and-install — and
  the install processor's validators reject an unowned directive anyway, so fitting one was
  never an option. Falls back to the store page if the dialog cannot be opened.
  - A directive with no buy price never reaches that dialog: it divides by both the current and
    the default price, to size the quantity selector and to work out the discount, so a
    reward-only item would raise `ZeroDivisionError` inside the game's own view.
- **Crew vs equipment** — `item.isCrewBooster()`, the same test behind the game's own two
  directive tabs.
- **Fitted** — `vehicle.battleBoosters.installed`.
- **How many directives this tank can take** — the length of that same collection, which is
  the count of battle-booster supply slots on the vehicle descriptor. It is zero on a low-tier
  tank, which can therefore take no directive at all. See
  [When the window shows](#when-the-window-shows).
- **Fits this tank** — `item.isAffectsOnVehicle(vehicle)`, which validates crew directives
  against the crew's skills and equipment directives against the mounted optional devices.
- **What a grant-perk directive is worth** — how far short of a full perk the crew currently
  is, since fitting one takes it the rest of the way. See below; it is the one figure here the
  mod works out rather than reads.
- **Auto-resupply** — `vehicle.isAutoBattleBoosterEquip()`, a bit in the vehicle's inventory
  settings (`VEHICLE_SETTINGS_FLAG.AUTO_EQUIP_BOOSTER`), so it is per vehicle rather than
  account-wide. Toggling it runs `VehicleAutoBattleBoosterEquipProcessor`, the same processor
  behind the game's own checkbox on the tank setup screen.

## Working out the `+N%`

A perk does not belong to a tankman as far as the readout is concerned — it belongs to the
crew. `Tankman.crewMemberRealSkillLevel` averages the perk over every seat it applies to, and
a seat that has not trained it counts as a zero in that average rather than being left out.
Two loaders where one has Melee Master at 100% and the other has never touched it is a crew at
50%, not 100%.

That is the number the mod starts from, read with `shouldIncrease=False`. The flag matters:
the default folds a fitted booster's own contribution into the level, which would measure the
gain against a value that already includes the thing being offered.

Fitting the directive takes that average to a full 100%, so the gain is simply the remainder —
`MAX_SKILL_LEVEL` minus the current level, rounded up.

The tempting mistake is to think the directive only reaches the seats that could learn the perk
themselves, and so scales down on a crew where some tankmen are already carrying the maximum
number of perks. It does not: the effect is full whatever the crew looks like. The client's own
code says the same thing — follow `crewMemberRealSkillLevel` into `_boostSkill` with a booster
installed and it takes the branch `MAX_SKILL_LEVEL if skillLevel <= 0 else skillLevel`, which
promotes *every* seat sitting at zero to a full perk, gated only on at least one seat being able
to use the booster at all (`tankmansCantUseBoosterCnt != len(tankmenSkillLevels)`).

The perk cap does still decide whether a directive is worth anything on this tank, but that
question is asked and answered before the gain is: `isAffectsOnVehicle` is
`any(TankmanDescr.validateSkillEquipment(...))` across the crew, and `validateSkill` raises on
`len(self.skills) >= NPS.MAX_MAJOR_PERKS` — so a directive no tankman has room for is filtered
out of the window entirely rather than listed with a reduced figure.

## When the window shows

Three conditions, from three different sources, and the window needs all of them.

**Does this mode offer directives at all?** It follows the garage's loadout panel — the bar
holding shells, consumables, optional devices and directives — by patching `LoadoutPresenter`,
the class behind that bar. The presenter is alive exactly while the bar is on screen, and its
groups controller (`_getGroupController._getGroups()`) lists the sections the bar carries. The
answer is yes when a panel is up and `battleBoosters` is one of its sections.

The modes really do disagree, so this half of the gate carries weight. Each mode ships a
`LoadoutPresenter` subclass and, in three cases, a groups controller of its own:

| Mode | Presenter | Groups come from |
| --- | --- | --- |
| Random, and the default garage | `LoadoutPresenter` | the constant `RANDOM_GROUPS` |
| Onslaught | `Comp7LoadoutPresenter` | inherited, so `RANDOM_GROUPS` |
| Onslaught (light) | `Comp7LightLoadoutPresenter` | inherited, so `RANDOM_GROUPS` |
| Fun Random | `FunRandomLoadoutPresenter` | the active sub-mode's configuration flags |
| Last Stand | `LastStandLoadoutPresenter` | the player's chosen panel preset |
| Frontline | `FrontlineLoadoutPresenter` | its own `fl_hangar_ammunition_groups_controller` |

Fun Random is the one that can answer no. It builds the section list per sub-mode, and the
directives section appears only when that sub-mode allows directives:

```python
# FunRandomHangarAmmunitionGroupsController._getGroups
config = self.getDesiredSubMode().getConfigurationModel()
if config.common.regularBoosters:
    sections.append(TankSetupConstants.BATTLE_BOOSTERS)
```

Reading the panel is therefore not tidiness. It is the only thing that keeps the window right in
Fun Random, and reproducing the decision would mean reproducing five controllers.

Every one of those subclasses lives in a **feature extension package**, not in `scripts.pkg`. An
earlier version of this page claimed the opposite, that one controller and one presenter existed
client-wide, because the search stopped at `scripts.pkg`. See
[Reading The Client's Own Code](reading-the-clients-code.md#scriptspkg-is-not-all-of-the-python).

Battle Royale is the exception the hook does not reach. Its panel is
`BattleRoyaleLoadoutPresenter(ViewComponent[LoadoutViewModel])`, held by `LoadoutContainerPresenter`,
and neither one derives from `LoadoutPresenter`. A patch on the base class never fires there, so
the window stays hidden in the Battle Royale garage. That is the correct outcome, and it arrives
by accident rather than by decision, which matters if the hook is ever widened.

**Is the garage what the player is actually looking at?** The panel cannot answer this, and
that is not a flaw in it — opening the playlist editor, the directives screen or the equipment
screen does not tear the garage down, so the panel underneath stays alive and quite correctly
goes on reporting that this mode offers directives. What changes is the lobby's visible route,
which is the client's own record of the current screen:
`LobbyStateMachine.onVisibleRouteChanged` carries the state that just became visible, and its
`getStateID()` is the route path — the same string the client writes to `python.log` as
"Visible route changed to: …". The window shows when nothing is layered over the garage:

| Route | |
| --- | --- |
| `subScope/subLayer/hangar/{root}` | shown |
| `subScope/subLayer/comp7Light/hangar/{root}` | shown — Onslaught |
| `subScope/subLayer/frontline/hangar/{root}` | shown — Frontline |
| `subScope/subLayer/lastStand/hangar/{root}` | shown — Last Stand |
| `subScope/subLayer/funRandomHangar/{root}` | shown — Fun Random, name folded into the segment |
| `subScope/subLayer/legacyHangar` | shown — the legacy garage, name folded in |
| `subScope/subLayer/hangar/editVehiclePlaylists` | hidden |
| `subScope/subLayer/hangar/loadout/instructions` | hidden |
| `subScope/subLayer/hangar/loadout/equipment` | hidden |
| `subScope/subLayer/funRandomHangar/loadout/shells` | hidden |

The full route space is 58 registered states across six garage roots, enumerated from a running
client on 2.3.1.3 with every mode loaded. Three of those roots **fold the mode name
into the segment** rather than prefixing a path: `funRandomHangar`, `legacyHangar` and
`battleRoyaleHangar`. A suffix test that compares a segment to the word `hangar` misses all
three, which hid the window in the Fun Random and legacy garages until the probe found it. The
test now matches a segment that *ends with* `hangar`.

Read as a suffix rather than matched against a list. An allowlist would silently omit every
mode nobody thought to add, since each one prefixes the route with its own subtree; and the
client's own consumers of this event compare against `getStateByCls(DefaultHangarState)`, which
has the same problem from the other end — each mode's garage is a separately generated state
class, so that test answers False everywhere but the default hangar.

**Does this tank have a directives slot?** The other two cannot answer this, because it is a
property of the tank rather than of the mode or the screen. The panel's section list is a
constant — `RANDOM_GROUPS` in `ammunition_groups_controller` names `battleBoosters` for every
tank in the mode — and what differs per tank is how many slots the game then draws in that
section: `BaseBlock._createSlots` sizes it by `len(vehicle.battleBoosters.installed)`, which
counts the battle-booster supply slots on the vehicle descriptor
(`vehDescr.type.supplySlots`, filtered by item type in `_EquipmentCollector._getCapacity`).
Low-tier tanks have none, so the client draws the section with nothing in it. The mod reads the
same number the panel does.

This one is a safety gate rather than a tidiness one. `BuyAndInstallBattleBoostersProcessor`
sends the tank's consumables and its directive layout to the server as a single array, and on
a tank with no directive slot that array does not line up with what the server expects: a
consumable ends up recorded as the tank's fitted directive, and the player can no longer take
the tank into battle until they sell it and buy it back. The processor does not refuse the
request — the game's own UI never makes it, because it draws no slot to click — so
`equip_directive` asks the same question again before it touches the layout. A window that is
somehow on screen still must not be able to corrupt a tank. Reported as
[issue #18](https://github.com/przemyslaw-zan/zanju-wot-mods/issues/18), where the client
update diff reads `boostersLayout: {349: [[1275]]}` for a tier II tank and the client logs
`capacity: 0` for its battle-booster equipment alongside it.

There is deliberately no fourth test for "is there a vehicle". The panel already answers it —
`_getGroupController` is None until a tank is in the garage — and asking separately means
answering the same question twice from two places that can disagree. An earlier version did
exactly that, gating on whether the snapshot described a tank, and it could strand the window
hidden: the data model is built a second or two *before* the garage finishes assembling, so
that gate started out false on every entry and only cleared if some later event happened to
trigger a rebuild. The slot gate is careful not to reintroduce it: no tank, and a tank it
cannot read, both answer "shown".

For the same reason no answer is mirrored into a local flag. All three are read live at the
moment visibility is applied, so a callback firing from one source can never push a decision
made from a stale copy of another. The mod applies visibility on a vehicle change as well as on
a panel or route change, since the third question is the one whose answer a new tank can flip.
The lobby state machine belongs to the lobby app, so it is a different object after every
teardown and its subscription is re-made on each hangar build; until it has reported, the route
half answers "shown" rather than holding the window back.

## Repairing a tank the old version broke

Version 1.0.1 fitted directives to tanks with no slot for one, and the account came back
recording directives that such a tank cannot hold. It reaches both per-tank inventory keys:
`boosters`, which holds the fitted directive, and `boostersLayout`, which holds what the game
refills after a battle. On the tanks this hit, both keys hold the tank's *consumables* —
`(1275, 763, 2555)` on the tank behind this section.

Nothing in the client shows it. `_Equipment.__init__` truncates the parsed list to the tank's
capacity, which is zero, so the gui item reports nothing fitted and no screen can reach the
entries. The only marks are in `python.log`, once per rebuild of that tank:

```
WARNING: [gui.shared.gui_items.vehicle_equipment] Length of arguments is not valid,
args: (1275, 763, 2555) for equipment: _ExpendableEquipment, ..., capacity: 0
```

What the player sees is a tank that looks normal and cannot fight. It enters the queue, the
server declines to assemble an arena for it, and about 25 seconds later the client is back in
the garage with no message and the vehicle lock released (`vehsLock: {686: (2, 0)}` and then
`{686: None}` in the client update diffs).

`repair.py` reads the raw inventory — `items.inventory.getItems(GUI_ITEM_TYPE.VEHICLE)`, the
same per-tank dictionaries the update diffs carry — on every garage build, and again on any
client update carrying those keys. A tank counts as broken when its directive capacity is zero
and either key still names an item. The mod builds a gui item only for the tanks that name
one, because the gui item is also the thing that hides them.

The repair is one command:
`inventory.setAndFillLayouts(invID, None, [0, 0], EQUIPMENT_TYPES.battleBoosters)` — a
directive layout holding one empty slot. `(0, 0)` is how the client's own layout builders write
an empty slot: `item.defaultLayoutValue if item is not None else (0, 0)`.

This is a verified result rather than a deduction. On the tank behind this section the server
answered
`RES_SUCCESS` and sent the update that cleared it, and the tank took a battle immediately
afterwards (WoT 2.3.1.3, EU, 25 August 2026):

```
inventory: {1: {'boostersLayout': {686: [[0]]}, 'boosters': {686: []}},
            11: {763: 319, 2555: 1, 1275: 1}}
```

Section 11 is the depot, so the three items the server had been holding as that tank's
directives came back to it.

An **empty** array does not work, which is worth writing down because it is the obvious thing
to try. Version 1.0.3 sent `setAndFillLayouts(invID, None, [], battleBoosters)`, the server
answered `RES_SUCCESS`, and nothing happened: no inventory update followed and the tank read
back unchanged three seconds later. The wire format explains it —
`Inventory.__setAndFillLayoutsOnShopSynced` encodes `None` and `[]` identically, as a length of
zero, so an empty array is how the client says "this command does not carry that section"
rather than "make that section empty".

A repaired tank keeps a one-slot layout, `boostersLayout: [[0]]`, which the client still
truncates to a capacity of zero. It goes on logging `Length of arguments is not valid, args:
(None,)` for that tank once per rebuild. Nothing hangs on it, and the mod reads that slot as
empty, so the tank is never asked about again.

The mod tries nothing else. A second command that has never had to run would be a write to
somebody else's account that nobody has watched the server answer, which is worse than a log
line saying what is left. What keeps this one safe to send unasked:

- It names one section. Both of the client's own callers pass `None` for the section they do
  not touch, and the update diff after the player fits a directive carries only the `boosters`
  keys, so it cannot reach shells, consumables or optional devices.
- It carries no item, so the "fill" half has nothing to buy. No resource can be spent, with or
  without the processor's `MoneyValidator`.
- The mod addresses only a tank whose capacity is zero. It never writes to a healthy tank, and
  it asks once per session per tank.

Three seconds after the server answers, the mod reads the tank back out of the raw inventory
and writes the verdict: repaired, or still recorded with a sale the only fix left. It does not
wait for the next garage build to do it, because the outcome worth diagnosing — a request the
server accepts and does not act on — produces no inventory update, and so nothing that would
prompt another check. Every log line names the inventory id as well as the tank, which is the
key the update diffs use.

Scanning stops for the session once a populated garage comes back clean. Only a mod version
that cannot run beside this one writes the state, so a garage that is clean at login stays
clean, and a per-garage-build walk of the inventory after that is work for nothing.

What the server does with the array it receives is not readable from the client, and the
client's own callers do not pin it down: `BuyAndInstallBattleBoostersProcessor` sends
`consumables.installed + battleBoosters.layout` and `BuyAndInstallConsumablesProcessor` sends
`consumables.layout + battleBoosters.installed`, both with `equipmentType` naming the half the
server should apply. The payload above sidesteps the question: it clears the section under
every reading of that split.

## How the window is drawn

It is plain HTML/CSS injected into the garage's Gameface document by OpenWG, and it is
entirely the mod's own DOM subtree — it never modifies an element the game renders, because
the game's UI keeps its own references and would either overwrite the mod or strand its
markup on screen.

Two constraints shape the rest, both documented in
[Gameface Mod Widgets](gameface-mod-widgets.md):

- The window root takes **no pointer events**; only the header and body opt back in. A root
  that accepted input across its whole area — it is `position: fixed` and sized by its
  content — would swallow the garage's drag-to-rotate and the player could no longer turn
  their tank.
- Dragging claims a press only when it lands on this window's own title bar, so it coexists
  with any other draggable mod OpenWG has dropped into the same document. Deciding ownership
  by DOM subtree rather than by hit-testing rectangles is what makes that reliable — two
  overlapping widgets' rectangles can both contain the point.

Window position and folded state are reported back to Python through wulf view-model
commands and stored in AppData, so a modpack reinstall does not reset them. The stored
position records the viewport it was captured at and is rescaled if the resolution changes.
