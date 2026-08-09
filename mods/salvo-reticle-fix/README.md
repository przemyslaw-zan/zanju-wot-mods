# Zanju's Salvo Reticle Fix

### This mod makes the reticle of Salvo Fire vehicles mean what it means everywhere else.

On every vehicle in the game the aiming circle grows and shrinks with dispersion — the accuracy you lose to moving, traversing and firing, and regain as the gun settles. That is the one number the reticle is there to tell you.

Twin-gun vehicles in **Salvo Fire mode** add a second, unrelated term on top of it: a fixed `0.213 m` shell-spread offset that models the gap between where the two barrels land their shells. Because it is a fixed distance rather than an angle, it does not shrink with range the way the dispersion term does — it lands on screen scaled by `1 / distance`. The closer your aim point, the more it inflates the circle:

| Distance to aim point | Circle vs. dispersion alone |
| --- | --- |
| 5 m | 5.2x |
| 10 m | 3.1x |
| 25 m | 1.8x |
| 50 m | 1.4x |
| 100 m | 1.2x |

Which is precisely backwards for a line of assault heavies that does its fighting inside 100 m.

It gets worse, because Salvo Fire mode also pins the dispersion factors near their `0.01` floor — your accuracy stops degrading when you move. So the one term that *should* move is frozen, and the one that shouldn't is doing all the moving. The circle you are watching is mostly reporting how far away you happen to be aiming.

These are measured, not estimated: 94 logged ticks on an FV229 Contender in Salvo Fire (client 2.3.1.1) put the stock circle at **3.90x** true size across 0–10 m and **1.81x** across 10–25 m, peaking at **7.1x** on a 3.4 m aim point where the real dispersion circle was 2.2 px and the drawn one 15.7 px.

This mod drops that offset from the drawn marker. The circle goes back to showing dispersion and nothing else, exactly as it does on a single-gun tank.

## What It Affects

Only the **`twinGun` mechanic** — the British salvo line that toggles between single fire and Salvo Fire mode:

- FV224 Chopper
- FV225 Collector
- FV226 Contradictious
- FV229 Contender
- FV230 Canopener
- FV227 Conceiver
- FV4025 Contriver

The offset only exists while Salvo Fire mode is engaged, so single fire mode was never affected in the first place.

**Not** affected is the older `dualGun` "double-barrelled" mechanic — Object 703 II, E 65 Zwilling, Object 265-II, Black Prince II, Serpente, SDT-58 Vlkodav. Those are a different system: they hold-to-charge a salvo rather than toggling a fire mode, they carry no shell-spread offset, and their reticle already shows dispersion only.

Nothing else changes. Shell behaviour, real dispersion and the shots themselves are untouched — this is a display fix, and the shells still land where the game says they land. Only the circle you read them through changes.

There is nothing to configure, so the mod ships no config file and adds no settings entry.

## How It Works

The mod wraps `_DefaultGunMarkerController.update` in `AvatarInputHandler.gun_marker_ctrl` and zeroes the `sizeOffset` field of the marker info before the controller converts it to screen units. That is the last step before the circle is drawn, so replays, the shot pipeline and `GunMarkerState` all keep the stock values.

**Nothing is mutated and no game files are modified.** The shipped `item_defs` XML is left exactly as WG published it, and no vehicle descriptor is written to — the mod only edits the per-tick message in flight. Salvo timing, reload, recoil and the mechanic itself are untouched.

It is also self-disabling in the only sense that matters. `sizeOffset` is non-zero *only* on a twin-gun vehicle with Salvo Fire engaged, so on every other vehicle, and in single fire, the hook does one attribute lookup and hands back the identical object — no allocation, no change. Verified both ways in game: `0.4260` across 94 salvo ticks, `0.0000` across 700 single-fire and non-twin-gun ticks.

The full derivation — where each term comes from, why one cancels with distance and the other does not, and where the `0.213 m` is defined — is in [Gun Marker Sizing And Salvo Fire](../../docs/reference/gun-marker-sizing.md).

## Install And Use

If you already have the prepared mod zip file, follow the general install path in
[Installing Mods](../../docs/installing-mods.md).

## Build From Source

For the general build/toolchain workflow, see
[Building From Source](../../docs/building-from-source.md).

## Develop

For the wider repository workflow, see:

- [Developing Mods](../../docs/developing-mods.md)
- [Architecture](../../docs/architecture.md)
- [Technical Reference](../../docs/reference/README.md)
