# Zanju's Better Vehicle Stats

Status: feasibility spike. Not released.

The stat lists show a row for a dispersion factor or a terrain resistance only when something modifies it, and that row states the modifier rather than the value. The values themselves differ per vehicle and per module, and no screen prints them. This mod hides those modifier rows and shows the values in their place.

## Stats Added

| Row | Read from |
| --- | --- |
| Dispersion During Movement | `chassis/shotDispersionFactors/movement` |
| Dispersion During Hull Traverse | `chassis/shotDispersionFactors/rotation` |
| Dispersion During Gun Traverse | `gun/shotDispersionFactors/turretRotation` |
| Dispersion After Firing | `gun/shotDispersionFactors/afterShot` |
| Hard / Medium / Soft Terrain Resistance | `physics['terrainResistance']` |

Each value combines the descriptor attribute with the matching vehicle attribute factor, so field modifications, equipment and crew perks are all included. The numbers use the units the vehicle files state, which are the units every reference site prints.

## Surfaces

Four screens show these lists and none of them share a renderer. The crew screen, the equipment loadout and the vehicle characteristics tab are Gameface, each a separate bundle. The field modifications screen is Scaleform. All four read one data path, so the mod registers the stats once and every screen picks them up.

The Scaleform screen and the tooltips take their text and icons from Python, so they are complete. The three Gameface screens resolve the row label and the row icon in the frontend, which Python cannot reach. Those two items are open.

## Translations

Reference language `en` defines 21 strings. Translations are community-maintained and may lag behind; see [Translating](../../docs/translating.md) to add or update one, then regenerate this table with `zwm lint i18n`.

| Language | Coverage | Missing |
| --- | --- | --- |
| _none yet_ | — | — |
