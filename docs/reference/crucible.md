# Crucible

Reference notes for `crucible-tracker`. How the client models the Crucible, where it keeps the progress of a series, what the conditions of a mission look like, why a battle has to read them from a file, and how the battle panel counts them.

Checked against WoT client **2.4.1.0** on 14 October 2026. The sources were the shipped scripts and a probe mod in the garage and in seven battles. No series was active during the probe runs. From 16 October 2026, battles with series 56 active, and with a test mission, measured the parts that the sections below date to those days. The parts on penetrations come from client **2.4.1.1**, on 15 November 2026.

## Vocabulary

The client calls the Crucible "challenges". The player-facing strings are under `#user_missions:hub/challenge_missions/`, and the header reads CRUCIBLE.

- A **challenge** is one series of missions. `ChallengeItem` in `gui/challenges/challenge_item.py` wraps its config.
- The player activates one series at a time. The client's own tooltip says so: "Only one series of missions can be active".
- A series has **missions**, played in order. Each mission is a hidden quest with the ID `challenge:<series>:<number>`, from 1.
- A failed battle costs a **shield**. A series with no shields left fails, and the player can restart it for a price.
- A series has a **difficulty**: `ChallengeDifficulties` HARD (1), MEDIUM (2) and EASY (3). The client labels them ACE, ELITE and FIGHTER, and sorts the hardest first.

## The progress is in tokens

`IChallengesController` (`gui/game_control/challenges_controller.py`) gives the series and their progress. Four account tokens per series hold the progress:

| Token | Count |
| --- | --- |
| `challenge:active:<id>` | 1 while the series is active |
| `challenge:quest:<id>` | the number of the current mission, from 1 |
| `challenge:attempt:<id>` | the shields left |
| `challenge:win:<id>` | how many times the series was completed |

`getChallengeProgress(id)` returns the last three as `{'quests', 'attempts', 'wins'}`. The controller fills it in `onLobbyInited`. Before that it returns `{}`, and the client's own `getChallengeState` raises `KeyError: 'attempts'` on it. Read every count with a default of 0.

Do not ask the controller for the active series in the garage. `onLobbyInited` runs on `GUICommonEvent.LOBBY_VIEW_LOADED`, and it sets the active ID with no event. The garage child view can build before that. On 16 October 2026, the first garage build came 0.2 s after the hangar window started to load, saw no active series, and kept it until the garage built again. After a battle, `__stop` also leaves the active ID at 0 until the lobby view loads. Thus `crucible-tracker` reads the tokens itself, from `itemsCache.items.tokens.getTokens()`, with `getTokenID` of each series. The items cache syncs before the garage builds. `crucible.read_tokens` does what the controller does in `__updateChallengesProgress`.

The state of a series follows `getChallengeState` in `gui/impl/lobby/challenges/views_helpers.py`, in this order: active if it is the active ID, failed if no shields are left after a start, completed if the wins reach `allowedCompletions`, else inactive. A series that never started has no shield tokens, and the client shows the full set, `attempts`, for it.

`getSortedChallenges()` gives the series the player can see now, in the client's own order. On the EU server on 14 October 2026 the controller held 14 series, and 7 of them were available.

The controller events are `onChallengesSettingsChanged`, `onActiveChallengeChanged` and `onChallengesClientUpdated`. A battle changes the tokens, and the client reports that through `itemsCache.onSyncCompleted`. That event fires often, and in a probe session it fired 53 times with no change to a Crucible token. Compare before acting on it.

## Mission conditions

`quest.getData()['conditions']` holds the conditions as nested `(name, value)` pairs. A leaf is a list with one `('value', x)` pair. Some leaves hold a set: the award IDs of `achievements` were `set([228])` on 24 November 2026. JSON has no set, so `collector` changes the conditions with `crucible.plain` before anything reads them. A set becomes a sorted list. Every mission on 14 October 2026 had the same pre-battle part: battle types 1 (`REGULAR`), 44 (`WINBACK`) and 46 (`RANDOM_NP2`), and vehicle tiers VI to XI.

The post-battle part of the 21 current missions used these shapes:

| Shape | Text from the client | Live in battle |
| --- | --- | --- |
| `results` `key` `greaterOrEqual` | Cause 2,500 HP of damage to enemy vehicles | yes |
| `results` `plus` of several keys `greaterOrEqual` | Cause and assist a total of 3,500 HP of damage | yes |
| `results` `damageDealt` `greaterOrEqual` `compareWithMaxHealth` | Cause 2 times more damage than the HP of your vehicle | yes |
| `vehicleDamage` `distance` 0 | Cause 3,000 HP of damage to enemy vehicles within the view range of your vehicle | yes, from positions |
| `vehicleDamage` `distance` 200 | Cause 2,500 HP of damage to enemy vehicles from a distance of 200 m or more | yes, from positions |
| `vehicleDamage` `limittedTime` 300 | Cause 2,500 HP of damage within the first 5 minutes of battle | yes, with the battle clock |
| `vehicleKills` `whileFullHealth` | Destroy 3 enemy vehicles without receiving any damage | yes |
| `results` `damageDealt` `max` N | Be among the top 5 players on your team by damage caused | no |
| `achievements` `set([228])` | Earn the High Caliber award | yes, by a rule for the award |
| `or` of the shapes above | each child is a row, and one row completes the mission | per row |

"Live" means that a battle panel can count the condition while the battle runs. The client has no damage figure for any other player during a battle, so "top N" waits for the results. An award is live only when the mod has a rule for it, see [Awards](#awards). `limittedTime` is spelled that way in the data. `crucible.py` in `crucible-tracker` holds the classification and its tests, with these conditions verbatim.

Mission 1 of series 73, on 15 November 2026, used one more shape: `results` `piercingEnemyHits` `greaterOrEqual` 10. Its text is "Penetrate enemy armor 10 times". The panel counts it from the shot results, see [Penetrations](#penetrations).

Mission 3 of "Flash", on 16 November 2026, used `vehicleKills` with `classesDiversity`. Its text is "Destroy 2 enemy vehicles of 2 different types". Nobody dumped its data, so the shape in the tests comes from the client formatter. The panel counts it from the class of each kill, see [Kills of different classes](#kills-of-different-classes).

A mission on 18 November 2026 asked to "Cause 5 critical hits to internal or external modules of enemy vehicles", with the title "Immobilize". The client writes that title only for `results` `critsCount`. The panel counts it from the crits count of each crit event, see [In battle](#in-battle).

### The conditions that the client can write

`res/text/lc_messages/challenges.mo` holds the text of every condition that the Crucible screen can show, under `condition/`. A condition without a text there shows "Finding the most suitable mission...". On 2.4.1.1, the file had these texts that no mission above used:

| Client text | Shape | Live in battle |
| --- | --- | --- |
| Block 2 times more damage than the HP of your vehicle | `results` `damageBlockedByArmor` `compareWithMaxHealth` | yes |
| Spot 5 enemy vehicles | `results` `spotted` | yes, each enemy once, see [In battle](#in-battle) |
| Spot 5 enemy vehicles while remaining unspotted | `results` `spottedBeforeWeBecameSpotted` | no |
| Destroy 3 enemy vehicles while remaining unspotted | `vehicleKills` `whileInvisible` | no |
| Cause 2,000 HP of damage to unspotted enemy vehicles | `vehicleDamage` `whileEnemyInvisible` | no |
| Cause 30% of the total amount of damage caused by your team | `results` `percentFromTotalTeamDamage` | no |
| Be among the top 3 players on both teams by damage caused | `results` `damageDealt` `max` with `total` | no |
| Be among the top 3 players on your team by experience earned | `results` `xp` `max` | no |

The "no" conditions need what only the server knows: whether it counts the player's vehicle or an enemy as spotted, and the damage or the experience of the other players. Thus the panel shows them as text only. The shapes come from the client formatter, because no mission with them was dumped.

### Sets of conditions

A child of `or` can also be an `and` group, so a mission can offer a choice of two sets of conditions. All conditions of one set must be met. In the dump of 14 October 2026, each child of an `or` was a single condition, but the client packer also handles a group. `crucible.condition_sets` reads the conditions as a list of sets: an `or` of single conditions is one set per condition, and everything else is one set. The card and the panel put the "OR" of the client between two sets, not between two conditions of one set.

### The fields that the client formatter reads

`ChallengeVehicleListFormatter` in `gui/server_events/cond_formatters/challenges/postbattle.py` writes the text of `vehicleDamage` and `vehicleKills`. It reads these fields:

| Field | Meaning |
| --- | --- |
| `distance` | 0 is "within the view range of your vehicle", a positive value is "from N m or more", a negative value is "from N m or less" |
| `limittedTime` | seconds from the start of the battle |
| `attackReason` | an index into `ATTACK_REASONS` in `scripts/common/constants.py`: 0 shot, 1 fire, 2 ramming, 3 world collision, 4 death zone, 5 drowning. The mod compares the numbers and has no names for them. |
| `eventCount` | count the hits, not the HP |
| `whileFullHealth`, `whileInvisible`, `whileEnemyInvisible` | conditions on the state of the player's vehicle or of the enemy |
| `classes`, `classesDiversity` | the vehicle classes that count, or how many classes the kills must cover |

The getter of the client gives `attackReason` 0 (shot) when the field is missing, but that is only for the text. In the game, damage by fire and by ramming counts towards a damage condition, and a kill by fire or by ramming counts towards a kill condition. The player confirmed this in battles. Thus the panel counts every reason when a condition names none, and only the named reason when it names one. The panel counts a condition only when it knows every field of it.

### Awards

An `achievements` condition names an award by its dossier record ID. `DB_ID_TO_RECORD` in `dossiers2/custom/records.py` gives the record name, which is the same in every language: 228 is `('achievements', 'mainGun')`. The client's own condition text reads the name the same way. Thus a rule for an award needs no translation.

`AWARD_RULES` in `crucible.py` turns an award into a figure that the panel can count. The rules come from the player:

| Award | Record | Rule in the panel |
| --- | --- | --- |
| High Caliber | `mainGun` (228) | damage dealt of at least 20% of the total HP of the enemy team, and at least 1,000 HP, with no direct shot on an ally |
| Top Gun | `warrior` (34) | at least 6 kills |
| Fighter | `fighter` (522) | 4 or 5 kills. A 6th kill closes the condition. |
| Duelist | `duelist` (523) | at least 2 kills of enemies that damaged the player's vehicle, its HP or its modules, in any order |

**Measured on 24 November 2026.** Before this date, no award mission was live in a real battle. The client gives the award IDs as a set, and the mod read only a list. The award mission showed as "not counted" in battle. While it was the current mission, the garage banner was also empty, because the battle transport failed with `TypeError: set([228]) is not JSON serializable`. The tests and the test mission of 16 October 2026 got their conditions from JSON, so they held lists only.

With the fix, mission 2 of series 70 ("Beacon"), High Caliber, was live in one random battle. The target was 2,296 HP, which is 20% of the total HP of the enemy team. The panel counted 1,801 HP of damage dealt. One direct shot on an ally turned the rule line red and closed the condition. The server did not complete the mission.

The client's text of Duelist is "Destroy at least 2 enemy vehicles that caused damage to your vehicle in the battle". Two terms follow it: "Damage to modules is included" and "Ricochets and non-penetrating hits are not included". A ricochet or a hit that does no damage sends no damage event, so the panel does not see it.

The player expects the server to judge the award after the battle, from the list of kills and the damage. Thus the panel takes no notice of the order. A kill counts also when the damage of that enemy comes after it. The panel shows the client's description of the award, `#achievements:duelist_descr`, in the line of a rule under the condition. The terms under it stay out.

The panel also shows the description of Top Gun, but that text ends before its value: "Destroy enemy vehicles:". The client adds one line for each game mode, from `warrior_standard_descr` and `warrior_ext_descr`. Each line holds the value and `warrior_condition_text`, " and more", as `RegularExtAchievement` in `gui/shared/gui_items/dossier/achievements/abstract/regular_ext.py` writes it. The game modes in these lines are out of date: "Standard Battle, Assault, Encounter" and "Grand Battle".

Thus the panel writes only the value after the description, from the target of the rule: "Destroy enemy vehicles: 6 and more". Every part of the text comes from the client, so the line needs no translation of the mod. Only the space between the description and the value is not from the client. The client starts a new line there.

The client's text of Fighter is "Destroy four or five enemy vehicles in one battle." The player says that a 6th kill loses the award. Thus the rule has a `maximum` of 5, and a figure above it closes the condition. The panel shows the client's description of the award. Under it, a line of the mod says "If you destroy more than 5 enemy vehicles, you do not get this award." That line is `LABEL_MAX_KILLS` in the string files of the mod, and it turns red at the 6th kill.

A mission of Fighter or Top Gun is met from the 4th kill on. At 4 or 5 kills, Fighter is met. At the 6th kill, Fighter closes and Top Gun is met.

High Caliber shows no description, because "Cause the highest damage in a battle" does not agree with the figure that the panel counts.

The terms of High Caliber are in the client's own text, `#achievements:mainGun_condition`. One direct shot on an ally ends the award, also with team damage off and a hit that does no damage. The panel shows the third line of that text, "The player must not hit any allies by direct shots", above the figures of the award, in the language of the client, and turns it red after such a hit. The condition then closes, whatever the damage.

The client calls `Vehicle.showDamageFromShot(attackerID, ...)` on each vehicle that a shell hits, to draw the hit. `battle_session` wraps it: a call on an ally, with the player's vehicle as the attacker, is a direct shot on an ally. A splash of high explosive arrives through `showDamageFromExplosion` instead, so it does not count. Measured on 17 October 2026, with the test mission of [In battle](#in-battle): one direct shot on an ally, with team damage off and no damage done, reached the wrapper, and the rule line turned red. High Caliber closed at 2,261 of 4,472 HP.

An award with no rule shows its text only. The panel counts the threshold, not every term of the award. High Caliber also asks for the most damage in the battle, for example, and the client has no damage figure for another player. To add an award, add its record name and its rule to `AWARD_RULES`. The other battle hero awards are in `BATTLE_HERO_MEDAL_SET` of the same client file.

## The client writes the text

`ChallengePostBattleConditionPacker` (`gui/shared/missions/packers/conditions.py`) turns the conditions into rows. Each row has a translated `descrData`, a `titleData` and an `iconKey`, in the same order as the raw conditions. The icons are in `gui/maps/icons/userMissions/challenges/missionIcons/32/<iconKey>.png`.

Pack only the conditions:

```python
model = ChallengeMissionModel()
ChallengePostBattleConditionPacker().pack(quest, model.postBattleCondition)
rows = json.loads(str(model))['postBattleCondition']['items']
```

`ChallengeMissionUIDataPacker`, the full packer, also packs the rewards. On the first garage build that made the client log "Trying to create fitting item type 12 when requesters are not fully synced", with a stack.

## A battle reads a file

The client cannot answer for the Crucible in battle. `ChallengesController.onAccountBecomeNonPlayer` runs `__stop`, which sets the active ID to 0 and clears the series. In the probe battles, with no series active, the controller still answered `isEnabled=True` and listed 14 series, so the series list comes back. The active ID does not. In the battle of 16 October 2026, with series 56 active, the controller answered active ID 0, but still held the progress from the garage: `{'wins': 0, 'attempts': 4, 'quests': 1}`. `__stop` does not clear the progress.

So the garage writes the facts a battle needs to `%APPDATA%\Wargaming.net\WorldOfTanks\mods\Zanju\crucible-tracker\battle_<account>.json`, and the battle reads them back. The battle first reads the copy that the garage of the same session kept in memory, and the file only when there is none. The third-party `crusable_progress_tracker` does the same. The file also covers a reconnect into a battle after a client restart, where no garage ran in between. In the probe, the copy in memory and the copy read back from disk were equal in every battle.

## A vehicle still in battle

A player can leave a battle and take another vehicle out while the first battle runs on. A series that the player starts then completes or fails with the result of that battle. The garage knows that such a vehicle is in a battle. Its inventory lock, `invData['lock']`, is `LOCK_REASON.ON_ARENA`, and `Vehicle.isInBattle` reads that. The lock says nothing about the kind of battle. There is one reason for every mode, and no client code reads its second value.

A Crucible mission counts only its own battle types, so `crucible-tracker` records the kind itself. `g_playerEvents.onAvatarReady` fires at the start of every battle, a reconnect too. The arena gives the battle type, `arena.bonusType`. Its entry for the player's vehicle gives the vehicle type, `vehicleType.type.compactDescr`, which is the `intCD` of the garage. The mod writes these per account to `battles_<account>.json` beside the transport. In the garage, a vehicle in battle counts only when its recorded battle type is one of the mission's. A vehicle with no record counts too.

The eligible vehicles are the client's own `getSuitableVehicles()` in `gui/impl/lobby/challenges/views_helpers.py`: vehicles in the garage, tier VI or higher (`CHALLENGE_MIN_VEHICLE_LEVEL`), and not event vehicles.

## In battle

The battle panel opens when the battle page populates (`SharedPage._populate`), and only when all of these are true:

- The settings allow it.
- The transport has an active series.
- The arena bonus type is one of the mission's.
- The tier of the player's vehicle is one of the mission's.

A replay never opens it, because the transport holds the series of the viewer now. The window and the drag are the route of [Choosing A UI Approach](choosing-a-ui-approach.md#in-battle-with-a-drag).

**Full information or bars only.** The setting `panelDetails` says when the panel shows its full information: the head with the shields, the name and the mission, and the text of each condition. The three choices are those of the client's own setting for the details of the damage log, and Mod Menu shows the client's labels for them, `#settings:feedback/tab/damageLogPanel/details/*`. Without the full information, a condition that the panel counts shows its icon, its bar and its figures on one line. A condition with nothing to count keeps its text, and the sets keep their "OR".

**The style and the figures.** The setting `panelStyle` selects the form of the progress: a flat bar or a round dial. The setting `panelFigures` selects the current and the required value, or only the current value. An open panel takes a new value of either setting at once. The dial has the time limit on top, the icon of the condition in its middle and the figures below it. The text stands on its right. A condition with nothing to count has an empty ring and no figures. A row that lost its figures after a reconnect looks the same. Without the full information, the round style shows no text, and the sets keep their "OR". The panel is then as wide as its content, in the font of the language: the widest figures that the mission can show, or the ring when these figures fit under it. A value with more digits than the required value makes the panel wider. The dial has the same column and the same side padding with and without the full information, so the full information moves the dial only down.

**Fixed columns.** The figures and the clock stand in columns of a fixed width. Thus a bar keeps its width while the text changes, and all bars of the panel have one width. A row with no time limit keeps an empty clock column when another row has a time limit. The columns hold 5 digits. The player set this limit, because the HP of a whole enemy team stays under 100,000. The value keeps counting past the required value after a condition is met. [Fixed text columns](gameface-mod-widgets.md#fixed-text-columns) gives the font widths behind the columns.

The choice "Press Alt to display" follows `GameEvent.SHOW_EXTENDED_INFO` on the battle bus. `Avatar.handleKey` sends it on each press and release of `CMD_VEHICLE_MARKERS_SHOW_INFO`, Alt by default, with `isDown` in the context. The players panel, the damage log, the minimap and the vehicle markers follow the same event, so the panel follows the key that the player set. `handleKey` sends nothing while the player cannot see the world, and the game gets no release when it loses the keyboard with the key down, for example on Alt+Tab. So while the key is down, the panel asks `CommandMapping.g_instance.isActive` again every 0.2 s. Expected Vehicle Values reads Alt from the key events of its own Flash stage instead, and those come only while that stage has the keyboard. In the battles of 25 October 2026, the panel started in its short form, showed the full information while Alt was held, and went back on release. After Alt+Tab out of the battle, the panel also went back to its short form. The log does not say if the event of the client or the check every 0.2 s caught that release.

The panel counts each condition from the battle controllers of `sessionProvider.shared`:

| Figure | Client source |
| --- | --- |
| damage dealt, each hit | feedback `PLAYER_DAMAGED_HP_ENEMY`: the target, the HP and the attack reason |
| kills | `PLAYER_KILLED_ENEMY`, with the class of the enemy from `arenaDP` |
| radio and track assist | `PLAYER_ASSIST_TO_KILL_ENEMY`, told apart by `getBattleEventType()` |
| stun assist | `PLAYER_ASSIST_TO_STUN_ENEMY` |
| damage blocked by armor | `PLAYER_USED_ARMOR` |
| crits | `PLAYER_DAMAGED_DEVICE_ENEMY`, the crits count of each event |
| damage received, full HP | the HP of the player's vehicle entity, read on each `VEHICLE_VIEW_STATE.HEALTH` |
| the start of the battle | `arena.periodEndTime - arena.periodLength` in the period `BATTLE` |
| the view range | `feedback.getVehicleAttrs()['circularVisionRadius']`, capped at `arenaVisitor.getVisibilityMaxRadius()`, as the minimap caps it |
| the total HP of the enemy team | the sum of `maxHealth` in `arena.vehicles` for the other team |
| penetrations of enemies | the trigger `PLAYER_SHOT_HIT` of `TriggersManager`, see [Penetrations](#penetrations) |
| spotted enemies | `PLAYER_SPOTTED_ENEMY`, each enemy once |
| the vehicles that damaged the player's vehicle | `ENEMY_DAMAGED_HP_PLAYER` and `ENEMY_DAMAGED_DEVICE_PLAYER`. Their target is the attacker, as in the client's damage log. |

`personalEfficiencyCtrl` is not a source. Its damage total also adds damage to destructible objects, and it has no split of radio and track assist.

The figures are an estimate, and the battle results decide the mission. These are the known gaps:

- **View range.** The client caps the view range at `VISIBILITY.MAX_RADIUS`, 445 m, and an arena modifier (`BattleParams.VISION_MAX_RADIUS`) can change that cap. The garage can show a higher view range, but the battle uses the capped one. The player expects the server to check "within the view range of your vehicle" against the capped range too, and the panel does the same. No battle has measured that yet.
- **Distance.** The panel reads the positions when the hit arrives, not when the shot leaves. A hit on an enemy that is not in the client's world has no distance, and it counts for no condition with a distance.
- **Kills by reason.** The kill event has no attack reason. For a condition that names a reason, a kill takes the reason of the player's last hit on that enemy.
- **Reconnect.** The client loses the events from before a reconnect, so no figure is sure after it. The panel then shows the conditions with no bars and no figures, and a time limit still counts down. A reconnect is an entry into an arena that the same vehicle first entered more than 30 s before. `battle_record` keeps the time of the first entry for this. In the battle of 16 October 2026, the battle page populated 4.3 s before `onAvatarReady` wrote the record. Thus at a first entry, the record of this arena is not there yet when the panel opens, and at a reconnect, the record of the first entry is.
- **Summary.** The server sends a battle summary (`onPlayerSummaryFeedbackReceived`) with the totals of damage, assist, blocked damage and stun. The panel takes a total from it when the total is higher, and logs the first summary beside its own totals. In two battles on 16 October 2026, the summary came once, about 1 s after `onAvatarReady` and before the battle started, with every total at 0, and never during the battle. In a normal battle it thus changes nothing. It can matter only after a reconnect, where the counters are off anyway.
- **Crits.** The panel adds the crits count of each event. No battle has compared that sum with `critsCount` in the results yet.
- **Spotting.** The client's "Spotted" ribbon counts each `PLAYER_SPOTTED_ENEMY` as one enemy, and reads none of the flags of the event: `isVisible`, `isDirect` and `isRoleAction`. The panel counts each enemy once, also if the server sends a second event for it. No battle has compared that figure with `spotted` in the results yet. The log has each spot with its flags.
- **Penetrations.** The rule comes from the client's sound code, and one battle measured it, see [Penetrations](#penetrations). Two cases are still open. A hit that pierces only a module, such as the tracks, does not count in the panel. Nothing shows yet whether the server counts it. Also, the server can send no result for a shot on an enemy that the player cannot see.

**Measured on 16 October 2026.** Series 56, mission 1 asked for 2,500 HP of damage dealt. The panel counted the damage while the battle ran, the server completed the mission, and the next garage showed mission 2 with no shield lost. The panel opened at the position that the player had dragged it to in an earlier session. Mission 2, among the top 5 players of the team by damage, then completed too. The panel showed its text only, as it does for every condition that it cannot count. Mission 3 asked for 3,000 HP of damage within the view range. The panel counted three hits of 527, 485 and 454 HP, at 22 to 26 m, against the capped view range of 445 m: 1,466 HP. The server failed the mission and took a shield, which agrees. No hit came from beyond the view range, so that battle did not test that case. The test mission below did, on the side of the panel.

**Measured with a test mission on 16 October 2026.** The server judges only the missions of a real series, so a temporary build put a mission of its own on the panel, armed by a file, with every form of condition that the panel counts. The build is gone, and the log lines that it used stay: each hit and kill with its distance, the view range and the time into the battle, and `Battle panel at the end:` with the figure of each condition and the totals. One random battle, in a vehicle with a view range of 393 m. The log listed five hits: 140, 119 and 764 HP at 473 to 550 m, beyond the view range, and 734 and 840 HP at 117 and 74 m. The panel counted 1,574 HP within the view range and 1,023 HP from 200 m or more, which is exactly the split of the hits. It counted all 2,597 HP for the first 5 minutes, because every hit came in the first 164 s. The kill at full HP closed when the vehicle took damage, and damage with assist read 2,840 HP: 2,597 dealt and 243 by radio. So the panel counts each hit by its rules in the game too. Whether the server checks the capped view range, as the player expects, is still open: only a real mission that the hits beyond the range decide can show it.

The battle results screen gives no figure for a Crucible condition. `ChallengesMissionsProgressPresenter` shows the mission number and the text of the conditions from the same packer, so the only answer from the server is whether the mission completed. A condition with a distance can thus be checked only by a battle where the hits beyond the range decide the result.

The time limit counts down in the panel's own JavaScript. Python sends the deadline in the clock of `BigWorld.serverTime()`, with the offset of that clock from the system clock. Before the battle starts, the panel shows the whole limit. The clock has the color of the figures. A limit that runs takes the warning color at 1:00. A met condition is green and a closed condition is red, and the clock follows these colors.

The mod logs the first 40 hits and kills of a battle when a condition has a distance, a time limit, a class, different classes or full HP, or counts penetrations, spotted enemies or Duelist. With spotted enemies, it logs each spot with the flags of the event. With Duelist, it logs each damage to the player's vehicle with its attacker. With penetrations, it also logs each shot result on an enemy: the flags, whether they are a penetration, and whether the target was in the client's world. Each line of a hit has the distance, the view range and the time into the battle. At the end of every battle with the panel, the line `Battle panel at the end:` gives the figure of each condition and the totals. Compare the log with the result of the mission to make sure that the panel counts right.

### Penetrations

The server sends the player the result of each shot, through `PlayerAvatar.showShotResults`. The result has one entry for each vehicle that the shot hit, with its hit flags from `VEHICLE_HIT_FLAGS` in `scripts/common/constants.py`. For each entry, the client fires the trigger `PLAYER_SHOT_HIT` of `TriggersManager`, with `targetId` and `flags`. The panel is a listener of the manager, so it needs no patch. The manager turns on at the start of every battle, in `Avatar.__onInitStepCompleted`. It sends its triggers to the listeners every 0.05 s, and only in the period `BATTLE`.

A penetration is an entry for an enemy with the flag `MATERIAL_WITH_POSITIVE_DF_PIERCED_BY_PROJECTILE`. The client plays its "penetration" sound on the same flag, in `gui/battle_control/controllers/sound_ctrls/common.py`. `crucible.penetrated` holds the rule. These entries do not count:

- Damage from a high-explosive shell without a penetration, with `MATERIAL_WITH_POSITIVE_DF_NOT_PIERCED_WITH_DAMAGE_BY_PROJECTILE`. The player says that this damage does not count for the mission.
- The splash of a shell, with `ATTACK_IS_EXTERNAL_EXPLOSION`.
- A hit on a vehicle that was already destroyed, with `VEHICLE_WAS_DEAD_BEFORE_ATTACK`.
- A hit on an ally, or on the player's own vehicle.

The manager drops its pending triggers only after it sent all of them to every listener. If a listener raises an exception, the manager sends the same triggers again 0.05 s later. Thus the listener of the panel catches every exception, or a shot could count twice.

**Measured on 15 November 2026.** Mission 1 of series 73 asked for 10 penetrations. The log listed 16 shot results on four enemies, and every target was in the client's world. 11 results had the flag of a penetration, and each of them came with a hit for HP damage. The panel ended at 11 of 10, and the server completed the mission with no shield lost. The shot that destroyed an enemy had `VEHICLE_KILLED` with the flag of a penetration, so the panel counts it. One hit pierced only a module, with `DEVICE_PIERCED_BY_PROJECTILE`. It did no damage and did not count. No result had the flag of high-explosive damage without a penetration.

### Kills of different classes

A kill condition with `classesDiversity` asks for kills of different vehicle classes, for example "Destroy 2 enemy vehicles of 2 different types". The client formatter only writes the text from `greaterOrEqual` and `classesDiversity`. The server decides the mission, and its rule is not in the client. The panel expects at least `greaterOrEqual` kills that cover at least `classesDiversity` classes. When the two numbers are equal, as in the mission of 16 November 2026, every reading of the text gives the same result. Only a mission with more kills than classes can show the difference.

The panel shows one figure: the kills that bring the condition closer. The kills that are still needed must cover the classes that are still needed. Thus a kill of a class that the kills already have counts only while enough kills are left for the missing classes. For 2 kills of 2 classes, a second heavy tank does not count. For 3 kills of 2 classes, it does. When the kills cover enough classes, every kill counts, also past the target. Thus heavy, heavy, medium for 2 kills of 2 classes reads 1/2, 1/2 and then 3/2. `Tracker._diverse_kills` in `progress.py` holds the rule.

Under the figures, the panel shows the icons of the classes destroyed. They come in the order of `VEHICLE_TYPES_ORDER` in `gui/shared/gui_items/Vehicle.py`: light, medium, heavy, tank destroyer, SPG. The icons are `gui/maps/icons/vehicleTypes/extraSmall/`, the set of the client's crew filters. Each file is 9×12 pixels, with its glyph in the middle. The resource name has an underscore for the hyphen of `AT-SPG`, as the client looks it up: `R.images.gui.maps.icons.vehicleTypes.extraSmall.dyn(vehicleType.replace('-', '_'))`. The line of icons keeps its height before the first kill, so the row does not grow at that kill. At the end of the battle, `Battle panel at the end:` gives the kills of such a condition and their classes beside its figure.

## Related Reading

- [Choosing A UI Approach](choosing-a-ui-approach.md), for the battle panel
- [Battle Mission Progress](battle-mission-progress.md), for the client's own tracker in battle, and why the panel does not reuse it
- [Personal Missions](personal-missions.md)
- [Gameface Mod Widgets](gameface-mod-widgets.md#sharing-the-row-beside-the-vehicle-name), for the garage banner
