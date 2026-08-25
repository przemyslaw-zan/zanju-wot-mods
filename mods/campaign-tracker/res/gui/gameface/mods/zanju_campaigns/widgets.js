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
// hover card open on `:hover` without any script. Hovering is the only thing a badge does —
// nothing here listens for a click or a drag.
//
// Widgets are reconciled rather than rebuilt. A snapshot arrives on every mission update and
// on every tank change, and rebuilding would close an open hover card each time.
//
// The badges are fixed to the garage's own vehicle name and experience block
// (`VehicleInfoWidget`, which renders the tier, the name and the XP total). That block lives in
// this same document and sits centred near the top, so the badges take the space to its right
// and follow it wherever the garage puts it. See findAnchor for why it is matched the way it
// is, and FALLBACK_* below for what happens without it.
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
// Flag on the document so the push subscription is registered once, even if this module is
// evaluated again for another sub-view.
const PUSH_BOUND_FLAG = '__zanjuCtPushBound';
// The garage's own vehicle name and experience block, which the widgets sit beside. Matched on
// the component name rather than on a full class name: the game builds these with CSS modules,
// so every class carries a content hash (`VehicleInfoWidget_b24b193a`) that changes whenever
// Wargaming edits that stylesheet. The prefix comes from the component's file name and is the
// stable half.
const ANCHOR_SELECTOR = '[class*="VehicleInfoWidget_"]';
// The space a badge keeps clear of the badge beside it.
const BADGE_GAP_PX = 10;
// Where the row starts, measured from the top-right corner of the block it hangs off. The
// horizontal value clears the role icon the game itself hangs off that corner.
const ANCHOR_OFFSET_X_PX = 25;
const ANCHOR_OFFSET_Y_PX = 10;
// Slot width used when a badge cannot be measured yet. Only a degraded path — the row spreads
// by measured width normally — but without it an unmeasurable pass would stack every badge on
// the same spot.
const NOMINAL_WIDGET_WIDTH_PX = 60;
// Where the row goes when the vehicle name block is not on stage: the middle of the screen,
// taken as a fraction because WoT's UI scale is quantized per resolution bucket.
const FALLBACK_LEFT_FRACTION = 0.5;
const FALLBACK_TOP_FRACTION = 0.5;

let lastSnapshotJson = null;
// Which sub-view turned out to carry our data model, so the push subscription can name it.
let dataResId = null;
let pollTimer = null;
// The garage element the widgets hang off, kept between ticks. Looking it up is a document
// query, and `tick` runs on every model write anywhere in this document once pushes are wired
// up, so it must not repeat the search while the element it found is still good.
let anchorEl = null;
// The campaigns currently on screen, and the last origin they were laid out from, so a moved
// anchor can be noticed without re-running a render.
let liveBranches = [];
let lastOriginKey = '';
let hasDrawn = false;

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
    if (document[PUSH_BOUND_FLAG] || dataResId === null) {
        return false;
    }
    if (typeof engine === 'undefined' || typeof viewEnv === 'undefined') {
        return false;
    }
    try {
        engine.on('viewEnv.onDataChanged', tick);
        // Third argument asks for descendants too: the snapshot lives on our child model, not
        // on the sub-view's own model.
        viewEnv.addDataChangedCallback('model', dataResId, true);
        document[PUSH_BOUND_FLAG] = true;
        // Pushes now carry the updates, so the timer drops back to being a safety net.
        setPollRate(POLL_INTERVAL_MS);
        log('subscribed to model updates on sub-view ' + dataResId);
        return true;
    } catch (e) {
        // Never fatal: the poll below still gets there, just later.
        log('could not subscribe to model updates, falling back to polling (' + e + ')');
        return false;
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
        mainConditions: labels.mainConditions || 'Main conditions',
        addConditions: labels.addConditions || 'Additional conditions',
        or: labels.or || 'OR',
        noConditions: labels.noConditions || 'No conditions to show',
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

// Grey covers every state except a mission actually running, which is the one thing the
// player is looking for.
function isActive(entry) {
    return entry.state === 'active';
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

function appendConditions(card, conditions, labels) {
    const main = conditions.filter(function (condition) { return condition.main; });
    const additional = conditions.filter(function (condition) { return !condition.main; });

    if (main.length) {
        // The heading only earns its place when there is a second group to tell it apart
        // from. On a mission with no additional conditions it would label the only list on
        // the card, which says nothing and costs a line.
        if (additional.length) {
            card.appendChild(el('div', 'zanju-ct-group', labels.mainConditions));
        }
        appendGroup(card, main, labels);
    }
    if (additional.length) {
        // Kept even when it is the only group: "additional" says these are optional, which
        // is worth knowing whether or not a main list sits above it.
        card.appendChild(el('div', 'zanju-ct-group', labels.addConditions));
        appendGroup(card, additional, labels);
    }
}

// The card heads with the operation the mission belongs to — "Operation Excalibur", since the
// game names each operation after the vehicle it awards — over the mission's own full name.
// Python composes the title so the wording stays translatable; see collector.py.
function cardTitle(entry) {
    return entry.operationTitle || entry.campaign || '';
}

function renderCard(card, entry, labels) {
    card.textContent = '';

    const subtitle = entry.mission || '';
    const title = el('div', 'zanju-ct-card-title' + (subtitle ? '' : ' zanju-ct-card-title-alone'));
    title.textContent = cardTitle(entry);
    card.appendChild(title);
    if (subtitle) {
        card.appendChild(el('div', 'zanju-ct-card-subtitle', subtitle));
    }

    const note = stateNote(entry, labels);
    if (note) {
        card.appendChild(el('div', 'zanju-ct-note', note));
    }
    if (!entry.mission) {
        return;
    }

    const conditions = entry.conditions || [];
    if (conditions.length) {
        appendConditions(card, conditions, labels);
    } else {
        card.appendChild(el('div', 'zanju-ct-note', labels.noConditions));
    }
}

function buildWidget(entry) {
    const widget = el('div', 'zanju-ct-widget');
    // Read back when reconciling, to spot a badge whose campaign is no longer active.
    widget._zanjuCtBranch = entry.branch;

    const face = el('div', 'zanju-ct-face');
    face.appendChild(el('div', 'zanju-ct-numeral', entry.numeral || ''));
    face.appendChild(el('div', 'zanju-ct-id', ''));
    widget.appendChild(face);
    widget.appendChild(el('div', 'zanju-ct-card'));
    return widget;
}

function renderWidget(widget, entry, labels) {
    widget.className = 'zanju-ct-widget' + (isActive(entry) ? '' : ' zanju-ct-widget-idle');
    const numeral = widget.querySelector('.zanju-ct-numeral');
    if (numeral) {
        numeral.textContent = entry.numeral || '';
    }
    const id = widget.querySelector('.zanju-ct-id');
    if (id) {
        id.textContent = faceId(entry);
    }
    renderCard(widget.querySelector('.zanju-ct-card'), entry, labels);
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
// vehicle name block, or the middle of the screen when that block is not on stage. Returns null
// only when there is no viewport to measure against either.
function anchorOrigin() {
    const element = findAnchor();
    if (element && element.getBoundingClientRect) {
        const rect = element.getBoundingClientRect();
        if (rect && (rect.width > 0 || rect.height > 0)) {
            return {
                x: Math.round(rect.right + ANCHOR_OFFSET_X_PX),
                y: Math.round(rect.top + ANCHOR_OFFSET_Y_PX),
            };
        }
    }
    const w = window.innerWidth || 0;
    const h = window.innerHeight || 0;
    if (!w || !h) {
        return null;
    }
    return {
        x: Math.round(w * FALLBACK_LEFT_FRACTION),
        y: Math.round(h * FALLBACK_TOP_FRACTION),
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
    for (let i = 0; i < branches.length; i += 1) {
        const widget = root.querySelector('[data-branch="' + branches[i] + '"]');
        if (!widget) {
            continue;
        }
        const point = origin
            ? clampToViewport(origin.x + offset, origin.y)
            : { x: offset, y: 0 };
        widget.style.left = point.x + 'px';
        widget.style.top = point.y + 'px';
        offset += (widgetWidth(widget) || NOMINAL_WIDGET_WIDTH_PX) + BADGE_GAP_PX;
    }
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
        // A fresh root holds no badges, and the snapshot behind them has not changed — so
        // without this the render below would be skipped and the root would stay empty.
        lastSnapshotJson = null;
        liveBranches = [];
        lastOriginKey = '';
    }

    bindModelPush();

    // Decided on the Python side by the lobby's visible route; see widgets_inject.py.
    const visible = unwrap(data.visible);
    root.style.display = visible === false ? 'none' : 'block';

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
        const origin = anchorOrigin();
        const key = origin ? origin.x + ':' + origin.y : 'none';
        if (key !== lastOriginKey) {
            lastOriginKey = key;
            applyLayout(root, liveBranches, origin);
        }
    }
}

function setPollRate(intervalMs) {
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
    ANCHOR_OFFSET_X_PX,
    ANCHOR_OFFSET_Y_PX,
    BADGE_GAP_PX,
    IDLE_ID,
    anchorOrigin,
    appendConditions,
    applyLayout,
    buildWidget,
    cardTitle,
    clampToViewport,
    conditionCount,
    faceId,
    isActive,
    isAttached,
    isWithin,
    parseJson,
    renderCard,
    renderWidget,
    renderWidgets,
    stateNote,
    texts,
};
