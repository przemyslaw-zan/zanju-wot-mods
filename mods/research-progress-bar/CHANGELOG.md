Changelog
=========

## 1.3.1 (4 August 2026)

- Updated Russian translations. Thank you [@AVPromo](https://github.com/AVPromo)!

## 1.3.0 (26 July 2026)

- New **"Click to research or purchase"** setting (on by default) makes the bar interactive: clicking a marker performs the matching action for that item.
  - Nothing is spent or bought without confirming it in the game's own windows first, so a misclick costs nothing.
  - Actions are performed via mouse click. When several options are available, keyboard is used instead.
  - In Research mode, vehicles are researched; modules are researched and then offered for purchase and mounting.
  - In Field Mods mode, levels are unlocked, essentials / auxiliary loadout switches are toggled on or off, one of two modifications is picked, an already-picked modification is swapped to the other, and the second slot category is opened for selection.
  - In Tier 11 Upgrades mode, a reachable node opens the game's own upgrades menu.
- Marker icons are now coloured to match their state.
- Overlapping icons above markers are spread sideways so they no longer draw on top of each other, while the markers stay on their exact XP positions.
- When a tooltip stacks more than one item, the sections are divided by a horizontal line.
- The final Tier 11 upgrade node's tooltip now shows the combined "Cost with prerequisites" for the whole remaining tree.
- Minor and major Tier 11 upgrade nodes are greyed out with a "Requires other upgrades" note when every remaining upgrade of their tier is still blocked behind other nodes, and their tooltip shows an "Upgrades remaining: N" count.
- Loadout-switch tooltips now name what each switch controls and show its state as "Enabled" (green) or "Disabled" (red) instead of a plain "Active" / "Not active".
- The bar now refreshes as soon as a research, purchase, or loadout toggle is confirmed by the game, instead of waiting until the vehicle is switched away and back.
- Fixed the first vehicle research of a session failing with an "unlocks/vehicle/required_locked" error when the Research screen had not been opened yet.

## 1.2.0 (4 July 2026)

- New "Show Total XP" setting (enabled by default). Turning it off hides the Total XP calculation everywhere: the Free XP (yellow) segment of the bar, the yellow highlight of markers reachable with Free XP, the Total XP counter next to the bar, and the Total XP row in tooltips — leaving only Vehicle XP progress.
- Research tooltips for items that have prerequisites now show the combined cost of the item plus its prerequisites, and the Vehicle XP / Total XP progress is measured against that combined total — so a module that looks cheaper on its own no longer understates what it actually takes to unlock. [[#6](https://github.com/przemyslaw-zan/zanju-wot-mods/issues/6)]
- New Russian translation. Thank you [@AVPromo](https://github.com/AVPromo)!
- Fixed untranslated text in the tooltips: the field modifications and upgrades progress now shows "Vehicle XP" / "Total XP", along with the "Prerequisites" heading and completed-item text, in the client language instead of always in English. [[#8](https://github.com/przemyslaw-zan/zanju-wot-mods/issues/8)]
- The Vehicle XP / Total XP rows in tooltips are now laid out as a real table with right-aligned columns. They were previously aligned by padding with spaces, which only lined up in the mod's monospace font — translations rendered in the fallback font (e.g. Russian) drifted apart as label lengths diverged.
- Russian and other Cyrillic text now renders in the mod's own font, matching English and Polish, instead of the system fallback font.
- Elite tooltips now show the reward name on its own line below the title, so the icon lines up with the title instead of floating between two lines.
- Translations now ship inside the mod package itself, so installing leaves no loose language files in the modpack's `mods/configs` folder. The `language` override in the config file is gone as part of this — the mod now always follows the game client's language.

## 1.1.0 (26 June 2026)

- Settings now survive a modpack reinstall instead of being reset to defaults.
- In-game settings now use Aslain's ModsSettings menu, with search, collapsible mods, and a reset-to-defaults button.

## 1.0.1 (17 June 2026)

- The progress bar now lays out correctly at non-default interface scaling (e.g. x2) instead of stretching off both edges of the screen. [[#2](https://github.com/przemyslaw-zan/zanju-wot-mods/issues/2)]
- Korean and other non-Latin characters now display correctly in the mod's tooltips — module names, upgrade names and descriptions, and field-modification stats — instead of appearing as empty boxes. [[#3](https://github.com/przemyslaw-zan/zanju-wot-mods/issues/3)]

## 1.0.0 (3 June 2026)

- Initial release of the mod.
