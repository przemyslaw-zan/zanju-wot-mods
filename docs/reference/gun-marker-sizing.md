# Gun Marker Sizing And Salvo Fire

Verified against client **2.3.1.1**. Everything here was read out of the shipped client
following [Reading The Client's Own Code](reading-the-clients-code.md); re-check it after a
patch rather than trusting it.

## The two terms behind every reticle

`VehicleGunRotator.__getGunMarkerInfo` (`scripts/client/VehicleGunRotator.py`) produces the
`GunMarkerInfo` namedtuple that every gun marker is drawn from:

```python
diameterOffset = 2.0 * vehDescr.gun.twinGun.gunMarkerOffset
doubleDistance = 2.0 * (vehDescr.shot.maxDistance if usedMaxDistance else (endPos - shotPos).length)
diameter, dualAccDiameter = doubleDistance * dispersionAngles[0], doubleDistance * dispersionAngles[2]
```

The fields that matter are `size` (`diameter`) and `sizeOffset` (`diameterOffset`). Both are
**world-space lengths at the aim point**, not screen sizes.

`_DefaultGunMarkerController.update`
(`scripts/client/AvatarInputHandler/gun_marker_ctrl.py`) projects them to screen:

```python
self.__currentSize = helperScale(worldMatrix, size) * self.__screenRatio
self.__currentSizeOffset = helperScale(worldMatrix, gunMarkerInfo.sizeOffset) * self.__screenRatio
self._dataProvider.updateSizes(self.__currentSize, self.__currentSizeOffset, relaxTime, self.__offsetInertness)
```

`helperScale` is `BigWorld.markerHelperScale`, the native form of the `_calcScale` helper
left in the same module — a perspective projection, so it divides a world length by the
distance to the point. That is what makes the two terms behave completely differently:

| Term | World size | On screen | Distance-dependent? |
| --- | --- | --- | --- |
| `size` | `2 · d · θ` | `∝ 2θ` | **No** — the `d` cancels |
| `sizeOffset` | `2 · gunMarkerOffset` | `∝ 2 · gunMarkerOffset / d` | **Yes** — grows as `d` shrinks |

So the familiar "circle = current dispersion" reading holds only because the dispersion term
is an *angle* scaled by distance before projection. `sizeOffset` is a fixed length, so it
survives projection as a `1 / d` term.

### The measured scale law

`markerHelperScale` is native, so the above was inference until it was measured in game. 66
logged ticks on 2.3.1.1 (an FV230 Canopener, both camera modes) give:

```
px = size × K / dCam        K ≈ 1051 arcade, ≈ 2241 sniper (TwinGunControlMode)
```

`K` held to about 1% within a camera mode, so the projection does divide by camera depth as
assumed. The correction the table above misses is that **the two distances are not the same
distance**: `size` is built from `dGun`, the *muzzle* to the aim point, while the projection
divides by `dCam`, the *camera* to the aim point. Expanded:

```
px = 2 · θ · K · (dGun / dCam)
```

Measured `dGun / dCam`:

| Camera mode | `dGun / dCam` | Consequence |
| --- | --- | --- |
| Sniper (`twinGun`) | **1.000**, every sample | `px` is a pure function of `θ`; distance cannot resize the circle |
| Arcade | 0.31 → 1.00 | the circle really is distance-dependent, shrinking hard at close range |

The arcade figure is not a twin-gun quirk — it applies to every vehicle, and it means an
arcade reticle at ~6 m is drawn at roughly a third of its true angular size.

### `K` is the zoom constant, not a per-mode constant

Early samples suggested one `K` per camera mode with sporadic violations, some as large as 29×.
A 700-tick trace resolved it: `K` is a projection constant, so it tracks **zoom**. Values
cluster on plateaus at roughly 1043 (arcade) and 2239 × {1, 2, 4, 8} — the sniper zoom steps —
and 81% of the off-plateau readings fall *between* two plateaus, which is the zoom animating
between them.

So a reticle reaching several hundred pixels is not a bug, it is high sniper zoom, and the
transient values seen while `ctrlModeName` still reports `arcade` are the arcade→sniper
transition with the FOV in flight. There is no scale-law violation, and
`checkAndRecalculateIfPositionInExtremeProjection` is not implicated. Any tool comparing `px`
across ticks must treat `K` as a live variable, not a per-mode constant.

### Camera modes on a twin-gun vehicle

`ctrlModeName` reports the **camera** mode, and on these vehicles sniper view is served by
`TwinGunControlMode` — a separate class from `SniperControlMode` — so it logs as `twinGun`
and a plain `sniper` never appears. It is not the fire mode: salvo is a toggle orthogonal to
the camera, driven through siege state.

That camera has a quirk worth knowing when reading marker data: with two barrels it aligns
with the currently active gun and swaps to the other after each shot, and engaging salvo
parks it midway between them. Each of those is a lateral camera translation, and `px` is
computed from the live camera position.

The two are combined inside the native `WGGunMarkerDataProvider`, which is C++ and not
readable here; `_SPGGunMarkerController` does the same combination in Python as
`self._size = gunMarkerInfo.size + gunMarkerInfo.sizeOffset`, so it is additive in world
space.

Both terms are divided by the same camera distance on the way to the screen, so it cancels
out of their ratio and the inflation reduces to two quantities:

```
stock circle / true circle  =  1 + gunMarkerOffset / (dGun · θ)
```

Validated against 94 logged ticks (FV229 Contender in Salvo Fire, client 2.3.1.1): predicted
4.00× at `dGun` 7.0 m against 3.98× observed, and 7.20× at 3.4 m against 7.1×. Note it is
independent of the camera, so it holds in arcade and sniper alike.

Salvo Fire also pins the dispersion factors near their `0.01` floor — measured minimum
`0.01009` — so `θ` stops responding to movement while the offset keeps responding to range.
At that floor the stock circle runs ~5.2× true size at 5 m, ~3.1× at 10 m, ~1.8× at 25 m and
~1.2× at 100 m.

## Where `gunMarkerOffset` comes from

`gunMarkerOffset` is a field of the `TwinGun` component
(`scripts/common/items/components/component_constants.py`):

```python
TwinGun = collections.namedtuple('TwinGun', ['afterShotDelay', 'gunMarkerOffset', 'shootImpulse', 'twinGunReloadTime'])
DEFAULT_GUN_TWINGUN = TwinGun(afterShotDelay=0.5, gunMarkerOffset=0.0, shootImpulse=0, twinGunReloadTime=0.0)
```

Every gun therefore carries a `twinGun` component — which is why
`VehicleGunRotator` can read `vehDescr.gun.twinGun.gunMarkerOffset` unconditionally — and for
all but a handful it is the default `0.0`, making `sizeOffset` a no-op.

Across the whole of `scripts/item_defs/`, a non-default value appears in exactly eight files,
all of the form `scripts/item_defs/vehicles/uk/<vehicle>_siege_mode.xml`, and all with the
same value:

| Vehicle | `gunMarkerOffset` |
| --- | --- |
| GB140 FV224 Chopper | 0.213 |
| GB130 FV225 Collector | 0.213 |
| GB139 FV226 Contradictious | 0.213 |
| GB143 FV229 Contender | 0.213 |
| GB142 FV230 Canopener (and `_CFE_G`) | 0.213 |
| GB148 FV227 Conceiver | 0.213 |
| GB147 FV4025 Contriver | 0.213 |

Two consequences follow from the file it lives in. Because it is in the **siege-mode
descriptor overlay**, it applies only while Salvo Fire mode is engaged — single fire mode
keeps the `0.0` default. And because `'twinGun/gunMarkerOffset'` appears in
`descr_modify_attrs_allowed.py`, battle modifiers can change it at runtime, so a mod should
read the live value rather than assume `0.213`.

These item-def XMLs are packed binary sections, not text (see [Reading The Client's Own
Code](reading-the-clients-code.md)). They start with the magic `0x62A14E45`, followed by a
version byte, a NUL-separated string table terminated by an empty string, and then nested
sections whose 32-bit descriptors pack an end offset in the low 28 bits and a type tag in the
top 4 (`0` section, `1` string, `2` int, `3` float, `4` bool). A short reader for that layout
is enough to dump any of them.

## `twinGun` is not `dualGun`

Both mechanics are called "Salvo Fire" in the localisation, and they are separate systems.
`VehicleMechanic` (`scripts/client/vehicles/mechanics/mechanic_constants.py`) lists
`DUAL_GUN = 'dualGun'` and `TWIN_GUN = 'twinGun'` as distinct entries.

| | `dualGun` | `twinGun` |
| --- | --- | --- |
| Localisation | `detailsHelp/dualGun/volley_fire/title` → "Salvo Fire" | `abilities/common/name/twinGun` → "Salvo Fire Mode" |
| Input | hold `keyChargeFire` to charge a salvo | toggles a persistent fire mode (via siege mode) |
| Vehicles | Object 703 II, E 65 Zwilling, Object 265-II, Black Prince II, Serpente, SDT-58 Vlkodav | the British FV salvo line above |
| `gunMarkerOffset` | none — always `0.0` | `0.213` while the mode is on |

Only `twinGun` inflates the marker. The separate `dualAccSize` / `dispersionAngles[2]` pair
seen in `__getGunMarkerInfo` belongs to the `DUAL_ACCURACY` mechanic and drives its own
marker through `_DualAccMarkerController`; being an angle term, it cancels with distance like
`size` does.

## Overriding the item defs instead

Tempting, and it does work — `paths.xml` puts `./res_mods/<version>` and
`./mods/<version>/*.wotmod` (mounted at `root="res"`) ahead of `./res/packages/scripts.pkg`,
so a `res/scripts/item_defs/vehicles/uk/<vehicle>_siege_mode.xml` inside a package shadows
the shipped one.

It is still the wrong tool here. `gunMarkerOffset` is declared *only* in the siege-mode file,
and that file is not a small delta — the Canopener's carries 22 top-level sections
(`crew`, `speedLimits`, `invisibility`, `hull`, `chassis`, `turrets0`, `engines`, `physics`,
`repairCost`, …). Overrides are whole-file, so changing one float means shipping a frozen
copy of the vehicle's entire siege-mode definition, and the next balance patch to any of
those values is silently reverted on the modded client while the server uses the new ones.
Eight files, every patch, plus any newly added twin-gun vehicle. There is also no
`gunMarkerOffset` in the base `guns.xml` to target instead, and these files are packed
binary sections, so authoring them needs a writer for that format.

A grep of the client scripts finds no CRC or checksum over `item_defs`, so this is not a
claim that such an override would be *detected* — the point is that it replaces
server-relevant vehicle data to achieve a client-side display change, which the in-memory
route below achieves without touching a single shipped file.

## Patching the descriptor in memory

`items.vehicles.VehicleDescr()` returns a plain `VehicleDescriptor` for an ordinary vehicle,
but for one with a siege mode it returns a `CompositeVehicleDescriptor` holding **two**
descriptors, the second built from the siege-mode overlay:

```python
def VehicleDescr(compactDescr=None, typeID=None, ...):
    defaultDescriptor = VehicleDescriptor(compactDescr, typeID, typeName, ...)
    if not defaultDescriptor.hasSiegeMode:
        return defaultDescriptor
    siegeDescriptor = VehicleDescriptor(compactDescr, typeID, typeName, VEHICLE_MODE.SIEGE, ...)
    return CompositeVehicleDescriptor(defaultDescriptor, siegeDescriptor)
```

`CompositeVehicleDescriptor.__getattr__` delegates to whichever descriptor matches the
current mode and `onSiegeStateChanged` only flips which one is live — **both are built once
in `__init__` and never rebuilt on a mode switch**. Normalising them at construction
therefore holds for the descriptor's whole life.

`Gun.__slots__` (`scripts/common/items/vehicle_items.py`) includes `twinGun`, so the field is
assignable, and `TwinGun` is a namedtuple, so `_replace(gunMarkerOffset=0.0)` preserves
`afterShotDelay`, `shootImpulse` and `twinGunReloadTime`. The gun's `twinGun` **tag** must be
left alone — `isTwinGunVehicle` is `property(lambda self: 'twinGun' in self.gun.tags)`, so
clearing it would disable the mechanic rather than just its marker term.

Patching `CompositeVehicleDescriptor.__init__` rather than the `VehicleDescr` factory matters:
it is a method on the class object, so it is immune to modules that already did
`from items.vehicles import VehicleDescr` before the mod loaded. `Vehicle.typeDescriptor`
builds through `vehicles.VehicleDescr(compactDescr, extData=self)`, so every battle vehicle
passes through it.

The gap: `installTurret` on an already-built descriptor can repoint `descr.gun` at a `Gun`
the hook never saw. That is a garage-only path with no gun marker on screen, and entering a
battle always constructs a fresh descriptor.

## Notes for modding this

- `GunMarkerState` (`scripts/client/aih_constants.py`) carries `size` but **not**
  `sizeOffset`, so changing the offset affects only what is drawn — no controller, plugin or
  crosshair panel reads it back out.
- `sizeOffset` is referenced in exactly two client modules: `VehicleGunRotator` (producer)
  and `gun_marker_ctrl` (consumer). Patching the consumer leaves `BattleReplay` recording and
  the shot pipeline on stock values; patching the producer or the descriptor changes both.
- `gunMarkerOffset` is not surfaced anywhere in `gui/shared/items_parameters/`, so zeroing it
  has no effect on the garage stat panels.
- Marker size is **not** where a dispersion readout should come from if you want a steady
  number. `size` derives from `getOwnVehicleShotDispersionAngle(self.__turretRotationSpeed)`,
  and that speed is a finite difference — `diff / timeDiff`, with `timeDiff` a real elapsed
  `BigWorld.time()` delta — so it carries per-tick noise by construction.
- `_DualAccMarkerController` inherits `update` from `_DefaultGunMarkerController`, so a patch
  on the base class covers it. `_SPGGunMarkerController` is a sibling, not a subclass — but no
  SPG has a twin gun, so its `sizeOffset` is always `0.0`.
- `_DefaultGunMarkerController.update` runs every marker tick. A patch in that path should do
  as little as possible and avoid allocating on the common (offset already `0.0`) path.

Used by [Zanju's Salvo Reticle Fix](../../mods/salvo-reticle-fix/README.md).
