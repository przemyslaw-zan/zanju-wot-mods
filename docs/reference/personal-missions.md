# Personal Missions

Reference notes for `campaign-tracker`. How the client models the three campaigns, how it answers "which mission is this tank on", and where it keeps a mission's progress. Most of the traps here are places the client says one thing two ways. Picking the wrong one returns an empty answer rather than an error.

Verified by decompiling the shipped scripts of WoT client **2.3.1.3**.

## Vocabulary

The client's names and the player's names differ, and the code uses the client's.

- A campaign is a **branch**. There are three, named `regular`, `pm2` and `pm3` in `PM_BRANCH`. Players call them campaigns 1, 2 and 3.
- A campaign is divided into **chains**, which the UI calls lines, and into **operations**. Each operation awards a vehicle at its end.
- A mission is a **quest**, of class `PersonalMission` in `gui.server_events.event_items`.

Campaigns 1 and 2 run together. Campaign 3 is exclusive, so the server reports either the first two or the third as active, never all three.

Each campaign classifies vehicles a different way, and the classifiers never overlap inside one campaign. So a vehicle matches at most one line, and at most one active mission per campaign.

| Campaign | Branch | Lines | Classified by |
| --- | --- | --- | --- |
| 1 | `regular` | 5 | vehicle class — light, medium, heavy, destroyer, artillery |
| 2 | `pm2` | 4 | alliance — a group of nations |
| 3 | `pm3` | 3 | common role — Assault, Sniper, Support |

Campaign 3 reads as a matrix of class and role, but the client collapses it into one classifier. Each common role maps to a set of `ROLE_TYPE` values that already carry both (`HT_ASSAULT`, `MT_SNIPER`, `LT_WHEELED`, …). The map is `COMMON_ROLE_TO_ROLE_TYPE` in `constants`.

## The names-and-numbers trap

`IEventsCache.getPersonalMissions()` gives the cache everything below starts from. It names a campaign two ways:

- `getActiveCampaigns()` answers with branch **names** — `'regular'`, `'pm2'`, `'pm3'`.
- Every other call takes a branch **number** — `PM_BRANCH.REGULAR` and friends.

Passing one where the other belongs returns an empty result instead of raising. A mod that mixes them looks like a mod with nothing to show. Convert once, at the edge, with `PM_BRANCH.NAME_TO_TYPE` and `PM_BRANCH.TYPE_TO_NAME`.

`getActiveCampaigns()` replays the player's own progress cache and is **not** filtered by whether the server currently offers the campaign. `isEnabled(branch)` is that separate question, and it reads `getServerSettings().isPersonalMissionsEnabled(branch)`. A branch can therefore be active for the player and switched off on the server at the same time.

## Which mission a tank is on

1. `getSelectedQuestsForBranch(branch_id)` gives the missions the player has running in that campaign, at most one per line.
2. For each, `quest.getQuestClassifier().matchVehicle(vehicle_type)` answers whether the line accepts the vehicle. `vehicle_type` is the descriptor's type, not the item.
3. `quest.getVehMinLevel()` and `getVehMaxLevel()` bound the tier.
4. `missions.getOperationsForBranch(branch_id).get(quest.getOperationID())` gives the operation the mission belongs to.

Two naming calls are worth knowing. `quest.getUserName()` is the full name ("Union-10. Raise the Flag!") and `getShortUserName()` is the short one ("Union-10"); both are translated. `operation.getChainName(chainID)` is **not** — it answers with a resource id such as `#personal_missions:sidebar/vehicles/heavyTank`, because Scaleform resolves ids on their way to the UI. Anything drawing its own text has to call `i18n.makeString` on the result, which returns a non-id unchanged.

Vehicles tagged `BATTLE_MODE_VEHICLE_TAGS` — event tanks, Comp7, Frontline and the rest — are barred from personal missions entirely. `gui.shared.gui_items.checkForTags` is the client's own test.

## Progress

A mission's progress lives in a `LobbyProgressStorage`, built from the mission's own config and the player's saved progress:

```python
LobbyProgressStorage(quest.getGeneralQuestID(), quest.getConditionsConfig(),
                     quest.getConditionsProgress(), quest.isOneBattleQuest())
```

This is the object the game's own mission card and tooltip build, so its numbers are the numbers the game shows. It holds two kinds of row:

- **body progresses** (`getBodyProgresses()`) — one per condition. `getDescription()`, `getCurrent()`, `getGoal()`, `getState()`, `isMain()`, `isCumulative()` (whether a counter is worth showing at all), `isInOrGroup()`.
- **header progresses** (`getHeaderProgresses()`) — the requirement over a whole objective. "Complete the primary condition in 3 battles out of 5" lives here. A mission with no battle limit has **no header progress at all**.

`getState()` returns `constants.QUEST_PROGRESS_STATE`: 3 is failed, 5 completed, 6 preliminary-completed. `sortProgresses()` puts body rows in the client's own order. `hasProgressForReset()` on any progress is the same test the client's reset button is greyed out by.

**A battle-limited mission starts its conditions over every battle**, so the storage only ever describes the battle in progress. Read raw, a primary objective finished three battles ago shows all of its conditions undone. `storage.markAsCompleted(quest.isCompleted(), quest.isFullCompleted())` is the client's own correction, and it takes the mission's completion flags rather than the storage's.

## Completion flags, and what an order actually buys

`PersonalMission` carries three tests, and the middle one is the trap:

- `isMainCompleted()` — the primary objective is met.
- `isCompleted()` — defined as `isMainCompleted() or isFullCompleted()`. It **cannot** tell the two states apart, so it is the wrong one to ask when the difference matters.
- `isFullCompleted()` — completed with honors, both objectives met.

A player can buy the primary objective with an **order** rather than playing it. `areTokensPawned()` is `isMainCompleted()` and a pawned progress, so a pawned mission answers yes to `isMainCompleted()` too. Test pawned first where the two states need separating, which is what the client's own status panel does.

The order buys the *reward*, never the condition. The client says so itself, in `personal_missions:freeSheetPopover/pawnedSheetsInfo/descr`. "To retrieve a committed order, re-complete the mission with honors." So the game leaves the condition ticks empty on a pawned mission still in progress. `PMCardConditionsFormatter` skips `markAsCompleted` for exactly that case.

Pawn cost is 1 for an ordinary mission. The last mission of an operation takes `PM_BRANCH_TO_FINAL_PAWN_COST` — 4 for campaign 1, 3 for campaign 2.

The two in-progress states have their own wording, and the client keeps them apart:

| State | Status string | Reads |
| --- | --- | --- |
| primary met, secondary open | `quests:personalMission/status/addInProgress` | "Result improvement: complete the primary and secondary conditions" |
| order committed | `quests:personalMission/status/sheetRecoveryInProgress` | "Retrieving an order: complete the primary and secondary conditions" |

## Battle limits and one-battle missions

Some operations run their missions in a single battle. `quest.isOneBattleQuest()` is the test, and `getDummyHeaderType()` is the same test wearing a different hat:

```python
def getDummyHeaderType(self):
    if self.getOperationID() in self.ONE_BATTLE_OPERATIONS_IDS:
        return DISPLAY_TYPE.NONE
    return DISPLAY_TYPE.SIMPLE
```

It matters because a mission with no header progress gets a placeholder row built for it. That row carries `PERSONAL_MISSIONS.CONDITIONS_UNLIMITED_LABEL_MAIN` — "Complete the primary condition over any number of battles". A one-battle mission has no battle budget to describe at all, and the client suppresses that line by typing the placeholder `NONE`. Anything reproducing the placeholder has to reproduce the suppression, or it tells the player a single-battle mission may be played at leisure.

## Restrictions

A condition can carry a **limiter**: a second rule that must hold before the first one counts. "Be the top player by vehicles destroyed" is a race against your own team. It therefore comes with "Destroy 2 enemy vehicles", to stop an empty scoreboard from meeting it.

`BodyProgress.getLimiter()` returns the limiter as another `BodyProgress`, so the two are separable. `getDescription()` does **not** separate them — it composes them into one string:

```python
description = '%s\n%s %s' % (description, text_styles.alert(warningText), limiterDescription)
```

That is the condition, a newline, the word "Restriction!" (`PERSONAL_MISSIONS.CONDITIONS_LIMITER_LABEL`) wrapped in Scaleform font markup, then the limiter. A Gameface widget renders none of that markup. Split on the last newline, the one the client put there, and strip the tags. Let `getLimiter()` decide whether there is a second part, rather than the newline alone, since a description may hold newlines of its own.

## Missions asking for several vehicles

Campaign 3 has missions that must be completed in N different vehicles. The count and the list come from two different places, which is the client's own arrangement:

- **How many** — `progress.getUniqueVehicles()` on any of the storage's progresses.
- **Which are spent** — `quest.getConditionsProgress()['battlesUniqueVehicles']`, a collection of compact descriptors.

A vehicle that completes such a mission is locked out of it until the mission is finished. `PERSONAL_MISSIONS_30.CONDITIONS_REQUIREDVEHICLE_BOTTOMLABEL` is the client's own wording for the requirement, and it takes a `count`.

## Pausing, resetting and opening

`quests_proc` carries a processor for each action, and each one brings its own validators and its own dialog:

- **Pause and resume** — `PMPause(quest, enable, branch)`.
- **Reset** — `PMDiscard(quest, branch)`, which carries `PMDiscardConfirmator`, so the game raises its own confirmation and the reset only happens if the player accepts. A mod needs no dialog of its own.

Both must be run inside `decorators.adisp_process('updating')`. Neither needs a permission check of its own: the processor refuses and explains itself in the game's own system message.

**Only one operation allows either action.** `gui.server_events.pm_constants` holds `PAUSABLE_OPERATIONS_IDS` and `DISCARDABLE_OPERATIONS_IDS`. At 2.3.1.3 both contain operation 7 alone — Object 279 (e), the last operation of campaign 2. Read the lists rather than copying the number, so a client that opens this up opens the mod up with it. `missions_helper.__getBtnStates` is the full rule the client's own buttons follow, including that campaign 3 must not be the active campaign.

Opening a mission's screen differs by campaign, because campaign 3 has no per-mission screen:

- **Campaigns 1 and 2** — `events_dispatcher.showPersonalMission(missionID=...)`.
- **Campaign 3** — `events_dispatcher.showPersonalMissionsChain(operationID, chainID, category)`, which opens the filtered list. The chain id is accepted and ignored for this campaign.

Both refuse the navigation themselves when the page cannot be opened (`canOpenPMPage`), so that check does not need reproducing.
