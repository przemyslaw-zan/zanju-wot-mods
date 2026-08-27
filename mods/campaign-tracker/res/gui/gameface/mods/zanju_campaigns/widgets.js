// Zanju Campaign Tracker — one small garage widget per active personal missions campaign.
//
// Loaded into the persistent `mono/hangar/main` document by net.openwg.gameface (see
// src/zanju_ct/gameface/widgets_inject.py), which also attaches the `zanjuCtWidgets` data
// model this reads: a JSON snapshot of the active campaigns.
//
// The widgets are our own DOM subtree appended to the document body. They never modify any
// element the game renders — sharing a node with the game's React tree means React keeps its
// own reference and either overwrites us or strands our markup on screen.
//
// Pointer events are the important constraint here: the root stays `pointer-events: none` so
// the widgets can never swallow the garage's drag-to-rotate, and each widget is one direct
// child that re-enables them. Everything inside a widget inherits that, which is what lets the
// hover card open on `:hover` without any script. A badge does two things: it opens its hover
// card, and a badge with a mission behind it opens that mission's screen when clicked. Nothing
// here listens for a drag — the badges are fixed to the anchor.
//
// One input arrives the other way round. The card lights the line for the modifier keys held
// right now, and this document is not given key events until the player has clicked into it,
// so Python watches the keys and pushes them here like any other data (see held_keys.py). The
// click itself still reads its own event, which was always reliable.
//
// Widgets are reconciled rather than rebuilt. A snapshot arrives on every mission update and
// on every tank change, and rebuilding would close an open hover card each time.
//
// The badges are fixed to the garage's own vehicle name and experience block
// (`VehicleInfoWidget`, which renders the tier, the name and the XP total). That block lives in
// this same document and sits centred near the top, so the badges take the space to its right
// and follow it wherever the garage puts it. See findAnchor for why it is matched the way it
// is. There is no fallback position: without that block there is nothing to sit beside, so the
// badges stay hidden until it mounts.
//
// See docs/reference/gameface-mod-widgets.md.

const ROOT_ID = 'zanju-ct-root';
const DATA_PROPERTY = 'zanjuCtWidgets';
// The snapshot normally arrives by push (see bindModelPush): this is the backstop for the
// case where that channel could not be established, and the rate it drops to then.
const POLL_INTERVAL_MS = 1000;
// The unpushed rate only applies before the subscription is up, which is normally the first
// tick or two, so it is worth keeping short: it is the whole cost of the badges appearing late
// once the mission data is ready.
const UNPUSHED_POLL_INTERVAL_MS = 100;
// The held keys get their own timer, at a rate the main tick cannot afford. A player watching
// a line light up as they press a key notices a tenth of a second; a player switching tanks
// does not, which is why the two are paced separately. This one never stands down: the badges
// settle and stop needing attention, but a key can be pressed at any moment for as long as the
// garage is open.
const KEY_POLL_INTERVAL_MS = 100;
// Flag on the document so the engine-level handler is registered once, even if this module is
// evaluated again for another sub-view.
const PUSH_BOUND_FLAG = '__zanjuCtPushBound';
// Which sub-view the data-changed subscription currently names. Kept apart from the flag above
// because the two have different lifetimes: the handler is registered once for the document,
// while the subscription names one view and has to be renewed when that view is replaced.
const PUSH_RES_ID_FLAG = '__zanjuCtPushResId';
// Flag on the document recording that a push has actually ARRIVED, which is a different thing
// from having subscribed to them. The timer rate keys off this one: a subscription that never
// delivers used to leave the widgets on the slow backstop, where a modifier key took up to a
// second to reach the card.
const PUSH_SEEN_FLAG = '__zanjuCtPushSeen';
// Flag on the document so the click listener is registered once, even if this module is
// evaluated again for another sub-view.
const CLICK_BOUND_FLAG = '__zanjuCtClickBound';
// What a click asks Python for. The names match mission_actions.ACTION_*.
const ACTION_OPEN = 'open';
const ACTION_PAUSE = 'pause';
const ACTION_RESET = 'reset';
// Which modifier keys are held right now. Kept here rather than read from each event, because
// the hint lines have to answer while the pointer sits still over an open card.
const heldKeys = { shift: false, ctrl: false };
// The garage's own vehicle name and experience block, which the widgets sit beside. Matched on
// the component name rather than on a full class name: the game builds these with CSS modules,
// so every class carries a content hash (`VehicleInfoWidget_b24b193a`) that changes whenever
// Wargaming edits that stylesheet. The prefix comes from the component's file name and is the
// stable half.
const ANCHOR_SELECTOR = '[class*="VehicleInfoWidget_"]';
// The space a badge keeps clear of the badge beside it. Every badge fills its slot exactly, so
// this is the gap as it is seen, border to border.
const BADGE_GAP_PX = 12;
// Where the row starts, measured from the top-right corner of the block it hangs off. The
// horizontal value clears the role icon the game itself hangs off that corner.
const ANCHOR_OFFSET_X_PX = 25;
const ANCHOR_OFFSET_Y_PX = 10;
// Slot width used when a badge cannot be measured yet. Only a degraded path — the row spreads
// by measured width normally — but without it an unmeasurable pass would stack every badge on
// the same spot.
const NOMINAL_WIDGET_WIDTH_PX = 60;

let lastSnapshotJson = null;
// Which sub-view turned out to carry our data model, so the push subscription can name it.
let dataResId = null;
let pollTimer = null;
let keyPollTimer = null;
// The garage element the widgets hang off, kept between ticks. Looking it up is a document
// query, and `tick` runs on every model write anywhere in this document once pushes are wired
// up, so it must not repeat the search while the element it found is still good.
let anchorEl = null;
// The campaigns currently on screen, and the last origin they were laid out from, so a moved
// anchor can be noticed without re-running a render.
let liveBranches = [];
let lastOriginKey = '';
let hasDrawn = false;
// Placement waits for the block the badges hang off. The garage mounts it only once the
// selected vehicle's models are filled in, which is normally a tick or two after this document
// loads — so the first tick usually finds nothing to measure. `badgesPlaced` is what the root's
// visibility hangs on, so the badges appear beside the block rather than somewhere else first.
let badgesPlaced = false;
let currentPollMs = null;

function log(message) {
    // console.log is not forwarded to python.log by the Gameface host; console.error is.
    console.error('[zanju.campaigntracker] ' + message);
}

function unwrap(value) {
    return value && typeof value === 'object' && 'value' in value ? value.value : value;
}

function modelOn(id) {
    const view = window.subViews.get(id);
    const model = view && view.model;
    return model && model[DATA_PROPERTY] ? model[DATA_PROPERTY] : null;
}

function findDataModel() {
    // The inject lands on whichever hangar sub-view was free, so locate it by scanning
    // rather than assuming one.
    if (typeof window === 'undefined' || !window.subViews) {
        return null;
    }
    if (dataResId !== null) {
        // Once pushes are wired up this runs on every model write anywhere in the document,
        // not just ours, so it has to stay a single lookup rather than a scan of every
        // sub-view. Falls back to the scan the moment that view stops carrying our model.
        const known = modelOn(dataResId);
        if (known) {
            return known;
        }
    }
    const ids = window.subViews.ids();
    for (const id of ids) {
        const model = modelOn(id);
        if (model) {
            dataResId = id;
            return model;
        }
    }
    dataResId = null;
    return null;
}

function bindModelPush() {
    // Python writes the snapshot the moment the missions or the selected tank change, but a
    // property write is not an event on this side: without this the widgets would only notice
    // on their next poll, which is a visible lag on something as ordinary as switching tanks.
    // `viewEnv.onDataChanged` is the engine's own signal that a model in this document was
    // written, and it is what OpenWG's own ModelObserver subscribes to.
    //
    // The subscription names ONE sub-view, and the garage replaces the view our model rides on
    // whenever the player picks a different tank. `findDataModel` recovers from that on its own
    // by rescanning, so the data keeps arriving -- but the subscription is left naming a view
    // that no longer exists, and every push after the first tank change went nowhere. Renewing
    // it whenever the id moves is what keeps the channel alive for the rest of the session.
    if (dataResId === null || document[PUSH_RES_ID_FLAG] === dataResId) {
        return false;
    }
    if (typeof engine === 'undefined' || typeof viewEnv === 'undefined') {
        return false;
    }
    try {
        if (!document[PUSH_BOUND_FLAG]) {
            // The handler belongs to the document, not to a view, so it is registered once.
            // Registering it again per view would run the tick once per registration.
            engine.on('viewEnv.onDataChanged', onPush);
            document[PUSH_BOUND_FLAG] = true;
        }
        // Third argument asks for descendants too: the snapshot lives on our child model, not
        // on the sub-view's own model.
        viewEnv.addDataChangedCallback('model', dataResId, true);
        document[PUSH_RES_ID_FLAG] = dataResId;
        log('subscribed to model updates on sub-view ' + dataResId);
        return true;
    } catch (e) {
        // Never fatal: the poll below still gets there, just later.
        log('could not subscribe to model updates, falling back to polling (' + e + ')');
        return false;
    }
}

// Every push runs a tick, and the first one also tells the timer it can stand down.
function onPush() {
    document[PUSH_SEEN_FLAG] = true;
    tick();
}

function invokeCommand(data, name, arg) {
    // Wulf exposes a command as a callable on the model; which of the wrapped proxy or its
    // unwrapped value carries it differs across builds, so try both. The argument must be a
    // map — a bare scalar is rejected by Gameface as "not a map".
    try {
        let host = null;
        if (data && typeof data[name] === 'function') {
            host = data;
        } else {
            const inner = unwrap(data);
            if (inner && typeof inner[name] === 'function') {
                host = inner;
            }
        }
        if (!host) {
            log('command missing: ' + name);
            return;
        }
        host[name](arg || {});
    } catch (e) {
        log('command failed: ' + name + ' (' + e + ')');
    }
}

function parseJson(raw, what) {
    if (!raw) {
        return null;
    }
    try {
        return JSON.parse(raw);
    } catch (e) {
        log('could not parse the ' + what + ': ' + e);
        return null;
    }
}

function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) {
        node.className = className;
    }
    if (text !== undefined && text !== null) {
        node.textContent = text;
    }
    return node;
}

function getRoot() {
    return document.getElementById(ROOT_ID);
}

function buildRoot() {
    const root = el('div', 'zanju-ct-root');
    root.id = ROOT_ID;
    document.body.appendChild(root);
    return root;
}

function texts(snapshot) {
    // Labels ride along in the snapshot so the Python side owns translation.
    const labels = (snapshot && snapshot.labels) || {};
    return {
        noMission: labels.noMission || 'No mission for this vehicle',
        noVehicle: labels.noVehicle || 'No vehicle in the garage',
        disabled: labels.disabled || 'Campaign unavailable',
        paused: labels.paused || 'Mission on pause',
        // The game calls these groups primary and secondary wherever it shows them to a
        // player; main/add is only what its own key names say.
        primaryConditions: labels.primaryConditions || 'Primary conditions',
        secondaryConditions: labels.secondaryConditions || 'Secondary conditions',
        or: labels.or || 'OR',
        lockedVehicles: labels.lockedVehicles || 'Locked vehicles:',
        vehicleLocked: labels.vehicleLocked || 'Vehicle locked',
        noConditions: labels.noConditions || 'No conditions to show',
        hintOpen: labels.hintOpen || 'Click to open the mission',
        hintPause: labels.hintPause || 'Shift + Click to pause the mission',
        hintResume: labels.hintResume || 'Shift + Click to resume the mission',
        hintReset: labels.hintReset || 'Ctrl + Click to reset the mission',
    };
}

// The badge face carries the campaign numeral over the mission's short id — `LT-1`, `UN-15`.
// Python builds that id from the game's own translated short name; see campaigns.py. A
// campaign with no mission for this vehicle keeps the badge's shape and shows a dash, so the
// row does not reflow as the player switches tanks.
const IDLE_ID = '—';

function faceId(entry) {
    return entry.missionId || IDLE_ID;
}

// The badge's third row, for the missions that count their battles. Every shape reads the same
// way — what is in hand, out of what it takes, and how many battles are left to get there — but
// the numbers come from different places:
//
// - **battles** — a fixed run of battles, so many of which have to meet the condition.
//   Successes in hand, successes needed, battles still allowed. A battle that misses the
//   condition spends one of those without adding a success.
// - **score** — a fixed run of battles to reach a total. How far the total has come, what it
//   has to reach, and how many battles are left to do it in.
// - **count** — the objective met so many times, either in a row or in any order. How many are
//   in hand, and how many it takes. The "in a row" kind goes back to zero on a lost battle,
//   which is the whole point of showing it. The other only ever climbs. Nothing caps the
//   battles, so this one has no third number.
//
// The primary objective is the one worth watching, until it is finished -- then the secondary
// one is what the remaining battles are being spent on. `attempts` arrives primary-first, so
// the first unfinished one is exactly that rule.
//
// There is no case where every objective is finished: the game deselects a mission the moment
// it is, and only a selected mission reaches a badge. So "none unfinished" means the badge has
// nothing to count rather than something to fall back on. A requirement of any other shape
// gets nothing rather than the next objective's numbers, which would be numbers for a
// different objective than the badge is standing on.
function badgeTally(entry) {
    const attempts = (entry && entry.attempts) || [];
    const chosen = attempts.filter(function (attempt) { return !attempt.done; })[0];
    if (!chosen) {
        return null;
    }

    const battles = chosen.battles || [];
    if (battles.length) {
        return {
            kind: 'battles',
            // The requirement's own numbers are the successes in hand out of the successes
            // needed -- the three of "complete the condition in three battles out of five".
            // The five live in the marks, and a mark nobody played yet is a battle left.
            current: chosen.current,
            goal: chosen.goal,
            left: battles.filter(function (b) { return b === 'pending'; }).length,
        };
    }

    if (chosen.type === 'series' || chosen.type === 'counter') {
        // The requirement's own numbers are what is in hand out of what it takes. Both kinds
        // read the same way, and the card says which of the two it is.
        return { kind: 'count', current: chosen.current, goal: chosen.goal };
    }

    if (chosen.type === 'limited') {
        const score = scoreCondition((entry && entry.conditions) || [], chosen.main);
        if (score) {
            return {
                kind: 'score',
                current: score.current,
                goal: score.goal,
                // The requirement's own numbers are battles used out of battles allowed.
                left: Math.max(chosen.goal - chosen.current, 0),
                // Taken from the pace Python worked out for this same objective rather than
                // recomputed here, so the badge's colour and the card's line cannot disagree.
                ahead: paceFor(entry.paces, chosen.main),
            };
        }
    }
    return null;
}

// The pace reading belonging to one objective, as a plain ahead/behind, or null when that
// objective has no average to keep.
function paceFor(paces, isMain) {
    const pace = (paces || []).filter(function (row) {
        return Boolean(row.main) === Boolean(isMain);
    })[0];
    return pace ? Boolean(pace.ahead) : null;
}

// The running total the badge reports. Conditions arrive in the client's own order, which is
// its idea of which matters most, so the first counted one of the objective is the pick.
function scoreCondition(conditions, isMain) {
    return conditions.filter(function (condition) {
        return Boolean(condition.main) === Boolean(isMain) && condition.counted;
    })[0] || null;
}

// Grey means the badge has no mission to work on, which is the one thing a glance at it has to
// answer. A paused mission is still a mission, and the badge says it is paused with an icon of
// its own -- greying it as well would file it with "nothing here" and cost the icon its point.
function isActive(entry) {
    return entry.state === 'active' || entry.state === 'paused';
}

// Only a badge with a mission behind it has a screen to open. Derived rather than carried in
// the payload: the snapshot already says whether there is a mission.
function isClickable(entry) {
    return Boolean(entry && entry.mission);
}

// The notes above the conditions: what is true of this mission before the player reads what it
// asks for.
//
// A warning is one that costs the player battles if they miss it -- the mission is paused, or
// this tank is already spent on it, and either way nothing they play right now counts. The rest
// -- no mission for this tank, campaign unavailable -- are just the state of things, and
// reading them as warnings would cost the warning its meaning.
//
// A list rather than a single note, because the two warnings are separate facts. In this
// client's data they cannot both apply: pause belongs to campaign 2 and the vehicle lock to
// campaign 3, and those two are never active together. The card does not rely on that.
function cardNotes(entry, labels) {
    const notes = [];
    const state = stateNote(entry, labels);
    if (state) {
        notes.push({ text: state, warning: entry.state === 'paused' });
    }
    if (entry && entry.vehicles && entry.vehicles.currentLocked) {
        notes.push({ text: labels.vehicleLocked, warning: true });
    }
    return notes;
}

function noteClass(note) {
    const base = 'zanju-ct-note';
    return note && note.warning ? base + ' zanju-ct-note-warning' : base;
}

function stateNote(entry, labels) {
    if (entry.state === 'novehicle') {
        return labels.noVehicle;
    }
    if (entry.state === 'disabled') {
        return labels.disabled;
    }
    if (entry.state === 'paused') {
        return labels.paused;
    }
    if (entry.state !== 'active') {
        return labels.noMission;
    }
    return '';
}

function conditionCount(condition) {
    // A binary condition ("Survive the battle") carries no useful counter, so only a counted
    // one shows numbers; the tick alone says whether the other kind is done.
    if (!condition.counted) {
        return '';
    }
    return String(condition.current) + ' / ' + String(condition.goal);
}

function buildCondition(condition) {
    let className = 'zanju-ct-cond';
    if (condition.done) {
        className += ' zanju-ct-cond-done';
    } else if (condition.failed) {
        className += ' zanju-ct-cond-failed';
    }
    const row = el('div', className);
    row.appendChild(el('div', 'zanju-ct-mark'));
    row.appendChild(el('div', 'zanju-ct-cond-text', condition.text));

    const count = conditionCount(condition);
    if (count) {
        row.appendChild(el('div', 'zanju-ct-cond-count', count));
    }
    return row;
}

// An "or" group needs only one of its conditions met, which changes what the list means: an
// undone row in it is not an outstanding task. The client marks each member, and consecutive
// members are one group — so the break goes between neighbours that are both marked.
function appendGroup(card, conditions, labels) {
    for (let i = 0; i < conditions.length; i += 1) {
        if (i > 0 && conditions[i].alternative && conditions[i - 1].alternative) {
            card.appendChild(el('div', 'zanju-ct-or', labels.or));
        }
        card.appendChild(buildCondition(conditions[i]));
    }
}

// The requirement over a group of conditions: "complete the primary condition in 3 battles out
// of 5", and how far along that is. Missions without one carry no attempt row at all.
function buildAttempt(attempt) {
    let className = 'zanju-ct-attempt';
    if (attempt.done) {
        className += ' zanju-ct-attempt-done';
    } else if (attempt.failed) {
        className += ' zanju-ct-attempt-failed';
    }
    const row = el('div', className);

    const line = el('div', 'zanju-ct-attempt-line');
    line.appendChild(el('div', 'zanju-ct-attempt-text', attempt.text));
    line.appendChild(el('div', 'zanju-ct-attempt-count',
        String(attempt.current) + ' / ' + String(attempt.goal)));
    row.appendChild(line);

    // One mark per allowed battle, in the order they were played, the way the game's own
    // mission card shows it. Only the battle-capped requirements carry these.
    const battles = attempt.battles || [];
    if (battles.length) {
        const strip = el('div', 'zanju-ct-pips');
        for (const battle of battles) {
            strip.appendChild(el('div', 'zanju-ct-pip zanju-ct-pip-' + battle));
        }
        row.appendChild(strip);
    }
    return row;
}

// Campaign 3 asks for some missions to be completed in several different vehicles. A vehicle
// that completes one is locked out of it afterwards, so the list says which tanks are spent
// and the counter says how many are still wanted.
function buildVehicles(vehicles, labels) {
    const block = el('div', 'zanju-ct-vehicles');

    const line = el('div', 'zanju-ct-attempt-line');
    line.appendChild(el('div', 'zanju-ct-attempt-text', vehicles.text));
    line.appendChild(el('div', 'zanju-ct-attempt-count',
        String(vehicles.completed) + ' / ' + String(vehicles.required)));
    block.appendChild(line);

    const locked = vehicles.locked || [];
    if (locked.length) {
        block.appendChild(el('div', 'zanju-ct-locked-label', labels.lockedVehicles));
        // One row each rather than one comma-separated line: the list is read to check whether
        // a particular tank is on it, and a name is easier to find down a column than along a
        // sentence. Each carries the same lock the badge uses, so the two say the same thing.
        for (let i = 0; i < locked.length; i += 1) {
            const row = el('div', 'zanju-ct-locked-row');
            row.appendChild(el('div', 'zanju-ct-locked-icon'));
            row.appendChild(el('div', 'zanju-ct-locked-name', locked[i]));
            block.appendChild(row);
        }
    }
    return block;
}

// Where the running total stands against the average the mission asks for, as a percentage of
// it: 100 is exactly on the average, and the line is green above it and red below. Python
// composes the text so it stays translatable, and decides ahead or behind from the same reading
// the badge is tinted by. This side only tints the line to match.
function buildPace(pace) {
    const state = pace.ahead ? ' zanju-ct-pace-ahead' : ' zanju-ct-pace-behind';
    return el('div', 'zanju-ct-pace' + state, pace.text);
}

function appendAttempt(card, attempts, isMain, paces) {
    const attempt = (attempts || []).filter(function (row) { return Boolean(row.main) === isMain; })[0];
    if (!attempt) {
        return;
    }
    card.appendChild(buildAttempt(attempt));
    // Each objective carries its own pace: they share the battle allowance but not the total,
    // so the secondary usually asks for a steeper average than the primary.
    const pace = (paces || []).filter(function (row) { return Boolean(row.main) === isMain; })[0];
    if (pace) {
        card.appendChild(buildPace(pace));
    }
}

function appendConditions(card, conditions, labels, attempts, paces) {
    const main = conditions.filter(function (condition) { return condition.main; });
    const additional = conditions.filter(function (condition) { return !condition.main; });

    if (main.length) {
        // The heading only earns its place when there is a second group to tell it apart
        // from. On a mission with no secondary conditions it would label the only list on
        // the card, which says nothing and costs a line.
        if (additional.length) {
            card.appendChild(el('div', 'zanju-ct-group', labels.primaryConditions));
        }
        appendGroup(card, main, labels);
        // After the conditions it governs, not before: the conditions are what the player
        // reads first, and the counter is how those conditions are going.
        appendAttempt(card, attempts, true, paces);
    }
    if (additional.length) {
        // Kept even when it is the only group: "secondary" says these are optional, which is
        // worth knowing whether or not a primary list sits above it. The rule only goes on
        // when there is something above to be divided from.
        const className = 'zanju-ct-group' + (main.length ? ' zanju-ct-group-split' : '');
        card.appendChild(el('div', className, labels.secondaryConditions));
        appendGroup(card, additional, labels);
        appendAttempt(card, attempts, false, paces);
    }
}

// The card heads with the operation the mission belongs to — "Operation Excalibur", since the
// game names each operation after the vehicle it awards — over the mission's own full name.
// Python composes the title so the wording stays translatable; see collector.py.
function cardTitle(entry) {
    return entry.operationTitle || entry.campaign || '';
}

// The colour of the leading number, which is the only part that differs between the shapes.
// Things done read green, the green a completed condition gets everywhere else. A running
// total reads plain and takes the pace tint instead, because "ahead" and "behind" are what
// matter about a total, and a green one would claim to be finished.
function tallyLeadClass(tally) {
    if (tally.kind !== 'score') {
        return 'zanju-ct-tally-done';
    }
    if (tally.ahead === true) {
        return 'zanju-ct-tally-score zanju-ct-tally-ahead';
    }
    if (tally.ahead === false) {
        return 'zanju-ct-tally-score zanju-ct-tally-behind';
    }
    return 'zanju-ct-tally-score';
}

function renderTally(node, tally) {
    if (!node) {
        return;
    }
    node.textContent = '';
    if (!tally) {
        // Most missions have no battle limit, and an empty row would still cost the badge a
        // line of height.
        node.className = 'zanju-ct-tally zanju-ct-tally-empty';
        return;
    }
    node.className = 'zanju-ct-tally';
    node.appendChild(el('div', tallyLeadClass(tally), String(tally.current)));
    node.appendChild(el('div', 'zanju-ct-tally-sep', '/'));
    node.appendChild(el('div', 'zanju-ct-tally-target', String(tally.goal)));
    if (typeof tally.left === 'number') {
        // The battles the mission still allows, kept grey and behind a lighter separator: it
        // is the budget the first two numbers are spent out of, not a third score.
        node.appendChild(el('div', 'zanju-ct-tally-sep', '\u00b7'));
        node.appendChild(el('div', 'zanju-ct-tally-left', String(tally.left)));
    }
}

function renderCard(card, entry, labels) {
    card.textContent = '';

    // Everything that describes the mission itself rather than what it asks for: which
    // operation it belongs to, its name, and anything standing in its way. The rule under them
    // is carried by this block, so it stays put whichever of the three are present -- a card
    // with no mission has no subtitle, and most have no note.
    const head = el('div', 'zanju-ct-card-head');
    head.appendChild(el('div', 'zanju-ct-card-title', cardTitle(entry)));
    if (entry.mission) {
        head.appendChild(el('div', 'zanju-ct-card-subtitle', entry.mission));
    }
    const notes = cardNotes(entry, labels);
    for (let i = 0; i < notes.length; i += 1) {
        head.appendChild(el('div', noteClass(notes[i]), notes[i].text));
    }
    card.appendChild(head);

    if (!entry.mission) {
        return;
    }

    const conditions = entry.conditions || [];
    if (conditions.length) {
        appendConditions(card, conditions, labels, entry.attempts, entry.paces);
    } else {
        card.appendChild(el('div', 'zanju-ct-note', labels.noConditions));
    }

    // Last, because it is a rule about which tanks may be used rather than about what to do
    // in a battle. Missions without the requirement carry nothing here.
    if (entry.vehicles) {
        card.appendChild(buildVehicles(entry.vehicles, labels));
    }

    card.appendChild(buildHints(entry, labels));
}

// What a click on this badge does, and what the keys held with it would do instead. The line
// for the keys currently held is lit, so the card answers "what happens if I click now".
//
// Only campaign 2's last operation allows pause and reset -- the client permits them nowhere
// else -- so most badges carry the open line alone. That line still earns its place: a badge
// that opens a screen has no other way of saying so.
function buildHints(entry, labels) {
    const block = el('div', 'zanju-ct-hints');
    block.appendChild(buildHint(ACTION_OPEN, labels.hintOpen));
    if (entry.canPause) {
        // Paused missions offer the way back out, which is the same key.
        block.appendChild(buildHint(ACTION_PAUSE,
            entry.state === 'paused' ? labels.hintResume : labels.hintPause));
    }
    if (entry.canReset) {
        block.appendChild(buildHint(ACTION_RESET, labels.hintReset));
    }
    return block;
}

function buildHint(action, text) {
    const row = el('div', 'zanju-ct-hint', text);
    // Read back by applyHints, which lights the row matching the keys held right now.
    row._zanjuCtAction = action;
    return row;
}

// The badge's fourth row: the two states that change what the player should do with this tank,
// said with an icon rather than a word because the badge has no room for a word.
//
// - **paused** — the mission is on pause, so nothing played in it counts.
// - **locked** — this mission wants several different vehicles and this one is already spent
//   on it. The mission is still the tank's match, which is why the badge still names it, but
//   no battle in this tank will move it.
//
// Both can be true at once, and then both are drawn: they are separate facts and neither
// implies the other.
function badgeFlags(entry) {
    const flags = [];
    if (!entry || !entry.mission) {
        return flags;
    }
    if (entry.state === 'paused') {
        flags.push('paused');
    }
    if (entry.vehicles && entry.vehicles.currentLocked) {
        flags.push('locked');
    }
    return flags;
}

function renderFlags(node, flags) {
    if (!node) {
        return;
    }
    node.textContent = '';
    if (!flags.length) {
        // Most badges carry neither, and an empty row would still cost a line of height.
        node.className = 'zanju-ct-flags zanju-ct-flags-empty';
        return;
    }
    node.className = 'zanju-ct-flags';
    for (let i = 0; i < flags.length; i += 1) {
        node.appendChild(el('div', 'zanju-ct-flag zanju-ct-flag-' + flags[i]));
    }
}

function buildWidget(entry) {
    const widget = el('div', 'zanju-ct-widget');
    // Read back when reconciling, to spot a badge whose campaign is no longer active.
    widget._zanjuCtBranch = entry.branch;

    const face = el('div', 'zanju-ct-face');
    face.appendChild(el('div', 'zanju-ct-numeral', entry.numeral || ''));
    face.appendChild(el('div', 'zanju-ct-id', ''));
    face.appendChild(el('div', 'zanju-ct-tally'));
    face.appendChild(el('div', 'zanju-ct-flags'));
    widget.appendChild(face);

    // The point the banner hangs to, below the face and outside it. Two nested elements
    // because the shape is cut with `clip-path`, which takes the border with it -- see the
    // stylesheet. It carries no data, so nothing ever re-renders it.
    const tail = el('div', 'zanju-ct-tail');
    tail.appendChild(el('div', 'zanju-ct-tail-fill'));
    widget.appendChild(tail);

    widget.appendChild(el('div', 'zanju-ct-card'));
    return widget;
}

function renderWidget(widget, entry, labels) {
    widget.className = 'zanju-ct-widget'
        + (isActive(entry) ? '' : ' zanju-ct-widget-idle')
        + (isClickable(entry) ? ' zanju-ct-widget-clickable' : '');
    // Read back by the click handler, which walks up from whatever child was clicked.
    widget._zanjuCtClickable = isClickable(entry);
    // Read back when deciding what a click with keys held would do. The entry is kept whole
    // rather than copied field by field, so a new action costs nothing here.
    widget._zanjuCtEntry = entry;
    const numeral = widget.querySelector('.zanju-ct-numeral');
    if (numeral) {
        numeral.textContent = entry.numeral || '';
    }
    const id = widget.querySelector('.zanju-ct-id');
    if (id) {
        id.textContent = faceId(entry);
    }
    renderTally(widget.querySelector('.zanju-ct-tally'), badgeTally(entry));
    renderFlags(widget.querySelector('.zanju-ct-flags'), badgeFlags(entry));
    renderCard(widget.querySelector('.zanju-ct-card'), entry, labels);
    // The card was just rebuilt, so its hint lines start dim. Light the right one again for
    // whatever is held now, or a re-render under a held key would drop the highlight.
    applyHints(widget, heldKeys);
}

function clampToViewport(x, y) {
    const w = window.innerWidth || 0;
    const h = window.innerHeight || 0;
    let left = x;
    let top = y;
    if (w) {
        left = Math.max(0, Math.min(w - 40, left));
    }
    if (h) {
        top = Math.max(0, Math.min(h - 20, top));
    }
    return { x: Math.round(left), y: Math.round(top) };
}

// Whether a node is still part of the document. `isWithin` is not reused for this: its walk is
// capped at the few levels a press inside our own widget can travel, and the garage's own
// markup nests the anchor deeper than that, so it would answer "detached" for a live element
// and send findAnchor back to a full document query on every tick.
function isAttached(node) {
    let current = node;
    for (let depth = 0; current && depth < 64; depth += 1) {
        if (current === document.body) {
            return true;
        }
        current = current.parentNode;
    }
    return false;
}

function findAnchor() {
    // The cached element is kept only while it is still in the document. The garage rebuilds
    // this block whenever the selected vehicle changes, which detaches the old node — and a
    // detached node still answers getBoundingClientRect, with zeroes, so testing the cache by
    // reading its rect would silently place every widget in the top-left corner.
    if (anchorEl && isAttached(anchorEl)) {
        return anchorEl;
    }
    anchorEl = null;
    if (!document.querySelectorAll) {
        return null;
    }
    // The component's own class prefix matches its root and every descendant, so take the
    // outermost hit rather than the first: document order alone would be right today and
    // wrong the moment Wargaming reorders that markup.
    const matches = document.querySelectorAll(ANCHOR_SELECTOR);
    for (let i = 0; i < matches.length; i += 1) {
        let outermost = true;
        for (let j = 0; j < matches.length; j += 1) {
            if (i !== j && isWithin(matches[j], matches[i])) {
                outermost = false;
                break;
            }
        }
        if (outermost) {
            anchorEl = matches[i];
            return anchorEl;
        }
    }
    return null;
}

// Where the row of badges starts: down and right of the top-right corner of the garage's
// vehicle name block. Null while that block is not on stage, which is the badges' cue to stay
// hidden rather than to sit somewhere arbitrary.
function anchorOrigin() {
    const element = findAnchor();
    if (!element || !element.getBoundingClientRect) {
        return null;
    }
    const rect = element.getBoundingClientRect();
    if (!rect || (!rect.width && !rect.height)) {
        return null;
    }
    return {
        x: Math.round(rect.right + ANCHOR_OFFSET_X_PX),
        y: Math.round(rect.top + ANCHOR_OFFSET_Y_PX),
    };
}

function widgetWidth(widget) {
    try {
        const rect = widget.getBoundingClientRect();
        if (rect && rect.width > 0) {
            return rect.width;
        }
    } catch (e) {
        // Not measurable yet: the caller falls back to a nominal slot so the row still spreads.
    }
    return 0;
}

// Lay the badges out in a row from the origin, left to right. Slots advance by each badge's
// measured width plus the gap, so the row stays tight whatever a mission id happens to say.
function applyLayout(root, branches, origin) {
    let offset = 0;
    let measured = true;
    if (!origin) {
        return false;
    }
    for (let i = 0; i < branches.length; i += 1) {
        const widget = root.querySelector('[data-branch="' + branches[i] + '"]');
        if (!widget) {
            continue;
        }
        const point = clampToViewport(origin.x + offset, origin.y);
        widget.style.left = point.x + 'px';
        widget.style.top = point.y + 'px';
        const width = widgetWidth(widget);
        if (!width) {
            measured = false;
        }
        offset += (width || NOMINAL_WIDGET_WIDTH_PX) + BADGE_GAP_PX;
    }
    // Whether the row stands on real widths. False asks the caller to lay out again next tick.
    return measured;
}

function renderWidgets(root, snapshot) {
    const labels = texts(snapshot);
    const entries = (snapshot && snapshot.campaigns) || [];
    const wanted = {};
    const branches = [];

    for (let i = 0; i < entries.length; i += 1) {
        const entry = entries[i];
        wanted[entry.branch] = true;
        branches.push(entry.branch);
        let widget = root.querySelector('[data-branch="' + entry.branch + '"]');
        if (!widget) {
            widget = buildWidget(entry);
            widget.setAttribute('data-branch', entry.branch);
            root.appendChild(widget);
        }
        renderWidget(widget, entry, labels);
    }

    // A campaign that stopped being active loses its badge, and the row closes up behind it.
    //
    // Copied into an array first. The result of `querySelectorAll` is walked by index rather
    // than by iterator, because this renderer has already been caught not implementing a DOM
    // method the way the standard describes (see `isWithin`), and a live list would drop
    // entries as the loop removes from it.
    const existing = root.querySelectorAll('.zanju-ct-widget');
    const stale = [];
    for (let i = 0; i < existing.length; i += 1) {
        if (!wanted[existing[i]._zanjuCtBranch]) {
            stale.push(existing[i]);
        }
    }
    for (let i = 0; i < stale.length; i += 1) {
        root.removeChild(stale[i]);
    }
    return branches;
}

function widgetFrom(node) {
    // A click lands on whatever is under the cursor — the numeral or the id — so walk up to
    // the element that carries the campaign it belongs to.
    let current = node;
    for (let depth = 0; current && depth < 8; depth += 1) {
        if (current._zanjuCtBranch !== undefined) {
            return current;
        }
        current = current.parentNode;
    }
    return null;
}

// Which action the held keys ask for on this badge, or null for none.
//
// Holding both keys asks for nothing. A combination this mod does not define must not fall
// through to one of the two it does -- and falling through would land on reset, which is the
// one action that throws work away. Every line goes dim instead, which says plainly that the
// click will do nothing.
function keysOf(event) {
    return { shift: Boolean(event && event.shiftKey), ctrl: Boolean(event && event.ctrlKey) };
}

function actionFor(keys, entry) {
    if (keys.shift && keys.ctrl) {
        return null;
    }
    if (keys.shift) {
        return entry && entry.canPause ? ACTION_PAUSE : null;
    }
    if (keys.ctrl) {
        return entry && entry.canReset ? ACTION_RESET : null;
    }
    return ACTION_OPEN;
}

// Light the hint line for the action the held keys ask for, and dim the rest. Called on every
// key change and after every render, so an open card always describes the click about to
// happen. Class names are edited as strings because this renderer has no classList.
function applyHints(root, keys) {
    if (!root) {
        return;
    }
    const rows = root.querySelectorAll('.zanju-ct-hint');
    for (let i = 0; i < rows.length; i += 1) {
        const row = rows[i];
        const widget = widgetFrom(row);
        const wanted = actionFor(keys, widget && widget._zanjuCtEntry);
        const lit = row._zanjuCtAction === wanted;
        const base = 'zanju-ct-hint';
        row.className = lit ? base + ' zanju-ct-hint-active' : base;
    }
}

// Which keys are held arrives from Python, as one string on the data model — see held_keys.py
// for why it is not read from this document's own key events. Applied only on a change, so the
// usual case of nothing held costs nothing per tick.
function parseHeldKeys(text) {
    const held = typeof text === 'string' ? text.split(' ') : [];
    return { shift: held.indexOf('shift') >= 0, ctrl: held.indexOf('ctrl') >= 0 };
}

function updateKeys(text) {
    const keys = parseHeldKeys(text);
    if (keys.shift === heldKeys.shift && keys.ctrl === heldKeys.ctrl) {
        return;
    }
    heldKeys.shift = keys.shift;
    heldKeys.ctrl = keys.ctrl;
    applyHints(getRoot(), heldKeys);
}

function bindClicks(data) {
    if (document[CLICK_BOUND_FLAG]) {
        return;
    }
    document[CLICK_BOUND_FLAG] = true;

    // Bound at document level in the capture phase. A plain `click` listener on our own
    // element does not fire in this renderer, whereas document-capture mouse events
    // demonstrably reach us — the same path directives-helper settled on.
    document.addEventListener('mouseup', function (event) {
        const root = getRoot();
        if (!root || !isWithin(root, event.target)) {
            return; // not ours: never claim an event belonging to another mod
        }
        const widget = widgetFrom(event.target);
        if (!widget || !widget._zanjuCtClickable) {
            return; // a grey badge has no mission, so it has no action to take
        }
        // Read off the event rather than from the held state: the event is what the player
        // actually clicked with, and it cannot have gone stale between the two.
        const action = actionFor(keysOf(event), widget._zanjuCtEntry);
        // Still ours to swallow even when it asks for nothing, so an undefined combination
        // does not fall through to the garage behind the badge.
        event.stopPropagation();
        if (action) {
            invokeCommand(data, 'missionAction',
                { branch: widget._zanjuCtBranch, action: action });
        }
    }, true);
}

function isWithin(ancestor, node) {
    // Walks up checking identity first, rather than using `ancestor.contains(node)`: this
    // renderer does not report a node as containing itself, and a press can land on the
    // widget element itself rather than on one of its children.
    let current = node;
    for (let depth = 0; ancestor && current && depth < 8; depth += 1) {
        if (current === ancestor) {
            return true;
        }
        current = current.parentNode;
    }
    return false;
}

function tick() {
    const data = findDataModel();
    if (!data) {
        return;
    }

    let root = getRoot();
    if (!root) {
        root = buildRoot();
        bindClicks(data);
        // A fresh root holds no badges, and the snapshot behind them has not changed — so
        // without this the render below would be skipped and the root would stay empty.
        lastSnapshotJson = null;
        liveBranches = [];
        lastOriginKey = '';
        badgesPlaced = false;
    }

    bindModelPush();

    // Decided on the Python side by the lobby's visible route; see widgets_inject.py. Applied
    // at the end of the tick, once placement has had its say.
    const visible = unwrap(data.visible);

    // Cheap and first: a key change must reach the card without waiting on anything else,
    // and it never touches the badges themselves.
    updateKeys(unwrap(data.heldKeys));

    const raw = unwrap(data.snapshot);
    if (raw !== lastSnapshotJson) {
        lastSnapshotJson = raw;
        const snapshot = parseJson(raw, 'snapshot');
        if (snapshot) {
            liveBranches = renderWidgets(root, snapshot);
            lastOriginKey = '';
            if (!hasDrawn && liveBranches.length) {
                // Once per document. Pairs with the Python side's own line so a reader of
                // python.log can see whether a late badge was late data or a late draw.
                hasDrawn = true;
                log('drew ' + liveBranches.length + ' badge(s)');
            }
        }
    }

    // Re-laid out whenever the block the badges hang off has moved. The garage moves it on a
    // resolution change, on a UI-scale change, and whenever the vehicle name gets longer or
    // shorter — none of which arrive as a snapshot, so watching for it here is what keeps the
    // row beside it. One rect read on a cached element, because this runs on every model write
    // in the document.
    if (liveBranches.length) {
        updateLayout(root, liveBranches);
    }
    root.style.display = visible !== false && badgesPlaced ? 'block' : 'none';
    setPollRate(pollRateFor(Boolean(document[PUSH_SEEN_FLAG]), badgesPlaced));
}

function updateLayout(root, branches) {
    const origin = anchorOrigin();
    if (!origin) {
        // The block is not on stage: leave the badges where they are and keep them hidden.
        badgesPlaced = false;
        lastOriginKey = '';
        return;
    }
    if (!badgesPlaced) {
        log('anchored to the vehicle name block');
    }
    const key = origin.x + ':' + origin.y;
    if (key !== lastOriginKey) {
        // Only remembered when every badge could be measured. A badge appended this frame can
        // measure zero, and the row then spreads on the nominal slot instead of the real one --
        // right for one frame, wrong from then on, and frozen there because the origin has not
        // moved. Leaving the key unset costs one more layout on the next tick, which is where
        // the badge that used to jump on the next snapshot was jumping from.
        if (applyLayout(root, branches, origin)) {
            lastOriginKey = key;
        }
    }
    badgesPlaced = true;
}

// Fast while anything is still settling: the data model may not be found yet, pushes may not
// be arriving, and the anchor may not have mounted. Only once a push has actually been
// DELIVERED and the badges have a real position does the timer go back to being a backstop.
//
// Delivered, not subscribed. Subscribing always appears to succeed, so keying off that leaves
// the widgets on the one-second backstop when the channel turns out to be silent -- which is
// invisible for a snapshot but not for a modifier key, where a second of lag is the whole
// interaction.
function pollRateFor(pushSeen, placed) {
    return pushSeen && placed ? POLL_INTERVAL_MS : UNPUSHED_POLL_INTERVAL_MS;
}

// Everything the highlight needs, and nothing else: one cached model lookup, one property
// read, and a comparison that does no DOM work at all unless the answer changed. That is what
// makes this affordable ten times a second where the full tick -- which re-measures the anchor
// and compares the whole snapshot -- is not.
//
// It exists because the push channel cannot be relied on for this. Pushes are instant when they
// arrive, but on a first garage load they were not arriving in time, and a highlight that lags
// behind the key is worse than no highlight: it says the click will do something other than
// what it will do.
function keyTick() {
    if (dataResId === null) {
        return; // nothing found yet — going looking is the main tick's job, not this one's
    }
    const data = findDataModel();
    if (data) {
        updateKeys(unwrap(data.heldKeys));
    }
}

function setPollRate(intervalMs) {
    if (intervalMs === currentPollMs) {
        return; // called on every tick; only an actual change should reset the timer
    }
    currentPollMs = intervalMs;
    if (pollTimer !== null) {
        clearInterval(pollTimer);
    }
    pollTimer = setInterval(tick, intervalMs);
}

function start() {
    log('widgets.js loaded');
    // Starts at the faster rate and drops to the backstop rate the moment pushes are wired
    // up, which is usually on the first tick — but not if the sub-views are not up yet, and
    // that is exactly the case a rate fixed at start-up would get wrong.
    setPollRate(UNPUSHED_POLL_INTERVAL_MS);
    if (keyPollTimer === null) {
        keyPollTimer = setInterval(keyTick, KEY_POLL_INTERVAL_MS);
    }
    tick();
}

// Auto-start only inside the game document; under the test runner there is no Gameface view
// registry, so importing this module stays free of side effects.
if (typeof window !== 'undefined' && window.subViews) {
    start();
}

// Exported for the test suite only: the game loads this module for its side effect, via the
// auto-start above. Anything not imported by widgets.test.js stays internal.
export {
    ACTION_OPEN,
    ACTION_PAUSE,
    ACTION_RESET,
    ANCHOR_OFFSET_X_PX,
    ANCHOR_OFFSET_Y_PX,
    BADGE_GAP_PX,
    IDLE_ID,
    KEY_POLL_INTERVAL_MS,
    POLL_INTERVAL_MS,
    UNPUSHED_POLL_INTERVAL_MS,
    actionFor,
    anchorOrigin,
    applyHints,
    appendConditions,
    applyLayout,
    badgeFlags,
    badgeTally,
    buildAttempt,
    buildHints,
    buildPace,
    buildVehicles,
    buildWidget,
    cardNotes,
    cardTitle,
    clampToViewport,
    conditionCount,
    bindModelPush,
    faceId,
    findDataModel,
    isActive,
    isAttached,
    isClickable,
    isWithin,
    keyTick,
    noteClass,
    keysOf,
    updateKeys,
    paceFor,
    parseHeldKeys,
    parseJson,
    pollRateFor,
    renderCard,
    renderFlags,
    renderTally,
    renderWidget,
    renderWidgets,
    updateLayout,
    stateNote,
    texts,
    widgetFrom,
};
