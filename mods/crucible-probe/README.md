# Crucible Probe

A throwaway probe, not a mod to keep. Delete this directory after it answers its question.

## What it asks

The Crucible tracker by Poliroid (`crusable_progress_tracker`) shows Crucible mission progress in battle. It draws that progress only while the full-stats tab bar selects its own tab. The mod itself tracks progress for the whole battle. Only the drawing is gated.

Run 1 settled the mechanism. The GFx value proxy is real: reads return true values, and a method call runs inside ActionScript. Run 1 also showed that the tracker component holds no children of its own. The widget goes somewhere else:

```actionscript
_challenges = App.utils.classFactory.getComponent("ChallengesTrackerView", ChallengesTrackerView);
_challenges.visible = false;
_update_layout();
tabScreen.addChild(_challenges);
```

The parent is the client's own `TabScreen`. That screen draws only while the player holds Tab, so visibility was never the whole gate. The widget must change parent to stay on screen.

Run 2 walks the children of the tab screen, names the widget, and then tries to re-parent it onto the battle page:

- The move works. A small Python-only companion mod can then hold the widget on the battle page. The tracker stays as it is, and the UI stays verbatim.
- The move fails. The bridge refuses a `DisplayObject` as an argument, so an always-visible widget needs a rebuilt or a patched SWF.

## How to run it

1. Make sure `crusable_progress_tracker_1.0.3.wotmod` is in the game mods folder.
2. Start a Crucible challenge in the garage. The tracker then has an active mission to draw.
3. Close the game.
4. Run `zwm cycle crucible-probe --fresh-log`.
5. Start the game and enter one random battle.
6. Push Tab once and release it, so the tab screen builds its children.
7. Stay in the battle for at least one minute.
8. Close the game.
9. Read `game.log`.

## How to read the result

Search `game.log` for `zanju.crucibleprobe`. The probe tries four times: at 6, 14, 28 and 45 seconds after battle entry. It needs several tries because the tracker builds its widget on its own schedule.

Each attempt logs one `child N` line for every child of the tab screen. The widget carries `titleTF`, `shields` and `condition`, which no other child has, so its line ends with `<-- TRACKER WIDGET`.

Only the last attempt tries the move. The lines under `re-parent attempt:` hold the answer, and the line that starts with `VERDICT:` states it. If the move works, the probe also re-applies it every second and parks the widget near the top left corner. The screen then confirms the log.

Early attempts often report that a component is not registered yet. That is normal.

## Notes

The probe writes to a component owned by another mod, and it moves that component between parents. It never restores the original state. A re-parent can also leave the tab screen short of a child for the rest of the battle. This is safe for one test battle and wrong for anything else, which is the second reason not to keep it.

The probe imports no `_mod_meta`, and it keeps no config, no settings entry and no tests. One file is deliberate. The build still generates a `_mod_meta` module into the package, as it does for every mod here.
