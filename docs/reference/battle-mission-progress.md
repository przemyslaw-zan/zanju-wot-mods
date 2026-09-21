# Battle Mission Progress

Reference notes for putting mission progress on screen during a battle: what the client's own quest-progress components expose, what data shape they take, and what the Scaleform value bridge does and does not let Python touch.

Verified against WoT client **2.4.0.0** (EU, build 944) on 2026-09-12. The sources were the shipped scripts, a disassembly of `gui/flash/battle.swf`, and a probe mod run through seven battles. The bridge limits in [What Python cannot do to a Flash object](#what-python-cannot-do-to-a-flash-object) are runtime measurements, not readings of code.

## Why this page exists

The client draws an always-on mission tracker in battle for the selected personal mission. Third-party mods draw similar panels for other mission systems. This page started from one question. Can a mod reuse the client's tracker, reuse another mod's panel, or must it build its own? The answer is the third. The reason is worth recording, because it comes from a bridge limit that costs a battle to find.

## The client's own tracker

Two components sit on the battle page for the whole battle:

| Child of the battle page | Position | Notes |
| --- | --- | --- |
| `questProgressTopView` | x=459, y=110 | the always-on tracker |
| `questProgressTopAnimContainer` | x=0, y=110 | its animation layer |

`QuestProgressTopView` is registered like any battle component, in `gui/Scaleform/daapi/view/battle/classic/__init__.py`:

```python
ComponentSettings(BATTLE_VIEW_ALIASES.QUEST_PROGRESS_TOP_VIEW, quest_progress_top_view.QuestProgressTopView, ScopeTemplates.DEFAULT_SCOPE)
```

**It takes no content from outside.** `QuestProgressTopViewMeta` holds three slots and none of them carry data:

```python
as_setVisibleS(isVisible)
as_setFlagVisibleS(isVisible)
as_showContentAnimationS()
```

The content comes from inside, through `sessionProvider.shared.questProgress.getSelectedQuest()`. That controller reads personal missions and nothing else. So a mod cannot show its own mission in the tracker that already exists. To use the client's look, a mod must host the client's renderers in a component of its own.

## The renderers are reusable

The client ships the whole quest-progress renderer set as named Scaleform linkages. `QUEST_PROGRESS_BASE` and `QUEST_PROGRESS_BATTLE` in `gui/Scaleform/genConsts/` hold the names. The symbols live in `gui/flash/battle.swf`, which the client loads for every battle. A mod's ActionScript can therefore instantiate them with `App.utils.classFactory.getComponent(linkage, Type)`.

The ones that matter for an always-on panel:

| Linkage | Class in `battle.swf` | Use |
| --- | --- | --- |
| `QuestProgressItemRendererTopViewUI` | `net.wg.gui.components.questProgress:ItemRendererTopView` | one condition row, always-on style |
| `QuestProgressItemRendererTabViewUI` | `net.wg.gui.components.questProgress:ItemRendererTabView` | the same row, Tab style |
| `QPMetricsRangeValuesCmpTopUI` | metric component | current against goal |
| `QPMetricsSimpleCmpTopUI` | metric component | no numbers |
| `QPMetricsTimerCmpTopUI` | metric component | a countdown |
| `QPMetricsLimiterCmpTopUI` | metric component | a remaining allowance |
| `QPMetricsVehiclesCmpTopUI` | metric component | vehicle class targets |
| `RadialBar54UI`, `HexagonBar94UI`, `RhombusBar42UI` | chart | the bar behind a row |

`QUEST_PROGRESS_BASE` also holds the state colors and the timer thresholds, so a panel does not have to guess them.

### The renderer contract

Every renderer implements one small interface, `net.wg.gui.components.questProgress.interfaces.components:IQPItemRenderer`:

```actionscript
function init(data:IQPInitData):void;
function initMetrics(metrics:Vector.<IQPMetrics>):void;
function update(data:IQPProgressData):void;
function unlock():void;
function get/set id(...);
function get orderType():String;      // 'main' or 'add'
function get progressType():String;   // 'regular' or 'cumulative'
function get isInOrGroup():Boolean;
function get isHidden():Boolean;
```

`ItemRenderer` adds a settable `viewType` (`'top'` or `'tab'`), plus `progressData` and `initData` accessors. So the order is: create, set `viewType`, `init`, `initMetrics`, then `update` for each change.

## The data shape

The VO classes (`QPProgressVO`, `QPMetricsSimpleVO`, `QPMetricsRangeVO`, `QPMetricsTimerVO`, `QPMetricsVehicleVO`, `QPMetricsLimiterVO`) all extend `net.wg.data.daapi.base:DAAPIDataClass`. A `DAAPIDataClass` builds itself from the plain object that DAAPI delivers. **So the whole contract is a dictionary, and a mod can build it by hand.** No mission object of any kind appears in the shape.

`QuestProgressController.getQuestFullData` and `DetailedProgressFormatter` produce it. One condition row:

```python
{'progressID': <str>,
 'initData': {'title': <str>,
              'description': <str>,
              'iconID': <str>,
              'orderType': 'main' | 'add',
              'multiplier': <str>,
              'progressType': 'regular' | 'cumulative',
              'topMetricIndex': <int>,
              'isInOrGroup': <bool>},
 'progressData': {'state': <1 to 5>,
                  'goal': <number>,
                  'current': <number>,
                  'metrics': [<metric>, ...],
                  'isLocked': <bool>}}
```

`state` uses the `QUEST_PROGRESS_BASE` values: 1 not started, 2 in progress, 3 failed, 4 preliminary failed, 5 completed. Add `uniqueVehicles` to `progressData` only when the condition has vehicle targets.

Each metric is a flat dictionary. `gui/server_events/personal_progress/metrics_wrappers.py` holds all six:

| `mType` | Other keys |
| --- | --- |
| `metricSimple` | none |
| `metricSimpleValue` | `title`, `value` |
| `metricRangeValues` | `title`, `value`, `goal` |
| `metricVehiclesValue` | `title`, `value`, `vehicleTypes` |
| `metricTimer` | `title`, `time` as `MM:SS`, `status` |
| `metricLimiter` | `value`, `isActive` |

`status` on a timer is `normal`, `warning` under one minute, `critical` under thirty seconds, or `wasCompleted`. Values go through `backport.getNiceNumberFormat`, so a panel that formats its own numbers will not match the client.

A condition with no measurable progress maps to `metricSimple`, which draws the text without numbers. This matters. A mission such as "be among the top three players by experience earned" cannot be tracked live. The client holds no experience figure for any player until the battle results arrive. The renderer already has a shape for that case.

## The battle page coordinate space

Measured by enumerating the 42 children of `page.flashObject` during a battle at 1920 by 1200:

- The origin is the top left corner. `battleTimer` sits at x=1724, y=0 and `damagePanel` at x=0, y=970.
- `tabScreen` is child 40, at x=960, y=0. Its own children therefore use a centered space, which is why they carry negative x values.
- A panel of your own can anchor against any of those children. Read the geometry at runtime rather than storing it, because interface scale changes it.

## What Python cannot do to a Flash object

A DAAPI component's `flashObject` is a `PyGFxValue` proxy. It is not a general ActionScript gateway, and it fails quietly. These are runtime results from the probe, not inferences.

**Reads work, and they are real.** `visible`, `x`, `y`, `width`, `height`, `alpha`, `scaleX`, `name` and `numChildren` all return true values.

**A method call runs inside ActionScript.** `getChildAt(index)` executes, and an out-of-range index raises a genuine `RangeError #2006` on the Scaleform side. A `SystemError: PyGFxValue - Failed to invoke method` in Python is therefore not proof that the call never ran.

**An object argument does not cross.** `page.flashObject.addChild(widget)` raises nothing, logs nothing, and does nothing. The child count of both containers stays the same. A `DisplayObject` read out of the display list cannot be passed back in, so **Python cannot re-parent a Flash object.**

**Only a subset of members crosses.** A child that is a `TextField` reads back. A child that is an instance of a custom class does not. Identify an object by a member you have seen cross, never by one you expect to.

### The rule this gives

Never treat the absence of an exception as a result. Write, then read back, and compare. Four probe runs reported success from a silent no-op. One read-back would have caught it on the first.

## Why a mod cannot borrow another mod's panel

One third-party mod (`crusable_progress_tracker`) draws its panel only while the full-stats tab bar selects its tab. The panel itself is not gated. The visibility rule is one compiled ActionScript method that sets `visible` from the selected tab alias.

Reusing that panel is closed for two reasons, both from the list above. The panel is a child of the client's own `TabScreen`. That screen draws only while the player holds Tab, so visibility alone is not the gate. And Python cannot change the parent. One option remains: show the tab screen and hide its other children. That leaves a modal surface on screen for the whole battle, and it fights the owning mod on every Tab press.

That mod is also a useful record of what reuse is worth. It carries its own artwork: 113 shapes, 19 sprites, nine bitmaps, and a nine-sliced bar. From the client it takes only four things. The fonts, because it embeds no `DefineFont` of its own, so `$TitleFont` and `$FieldFont` come from `gfxfontlib.swf`. The native `Image` component for the icons. The text, from `ChallengeMissionUIDataPacker`. And the framework base classes. It redrew a look that the client already ships as linkages.

## Related Reading

- [Choosing A UI Approach](choosing-a-ui-approach.md)
- [UI And Scaleform](ui-and-scaleform.md)
- [Personal Missions](personal-missions.md)
- [Reading The Client's Own Code](reading-the-clients-code.md)
