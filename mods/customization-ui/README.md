# Zanju's Customization UI

> **Status: foundation spike, version 0.1.0 — not released and not usable as a mod yet.**
> It replaces the customization screen with a diagnostic panel. Install it only to run the
> validation below.

The goal is a mod-owned replacement for the vehicle customization screen: our own interface,
talking to the game through the client's own customization API rather than through
Wargaming's Flash UI.

## Why This Is Possible

The client's model layer does not live in the customization view. `_MainState._onEntered`
(in `gui/Scaleform/daapi/view/lobby/customization/states.py`) sets up the camera and the tank
transform and calls `CustomizationService.createCtx(...)`; the view is only a presenter over
the resulting `CustomizationContext`. Replacing the view therefore leaves modes, seasons,
outfits, item data, the purchase flow and the exit confirmation untouched.

The swap itself uses a seam the client already supports but never uses: a package registered
via `g_overrideScaleFormViewsConfig.initExtensionLobbyPackages` claims a view alias, and
`PackageImporter._getHandlesWithoutExtensionOverride` then drops the base game's registration
for it. See [Customization Screen](../../docs/reference/customization-screen.md) for the full
mechanism and the pieces that would have to be rebuilt.

## What The Spike Answers

Deploy it, open customization on any vehicle, and check both the screen and `python.log`
(the probe logs everything it reads before drawing it, so a broken SWF still yields answers):

| Question | Expected |
| --- | --- |
| Did our view replace the client's? | The probe panel appears instead of the stock screen |
| Is the customization context alive? | `context: alive`, with season / mode / tab values |
| Is item data reachable? | Non-zero style, paint and camouflage counts for the vehicle |
| Does the 3D scene still work? | The tank renders and still rotates by dragging |
| Can the player always leave? | The **Leave customization** button returns to the hangar |
| Does Esc still reach the view? | Esc also returns to the hangar — this one may fail, and that is a finding |

Failure is a valid outcome and should be recorded in the reference page rather than patched
over.

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
