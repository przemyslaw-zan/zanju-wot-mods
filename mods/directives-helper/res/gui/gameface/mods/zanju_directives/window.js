// Zanju Directives Helper — movable garage window listing the player's directives.
//
// Loaded into the persistent `mono/hangar/main` document by net.openwg.gameface (see
// src/zanju_dh/gameface/window_inject.py), which also attaches the `zanjuDhWindow` data
// model this reads: a JSON snapshot of the depot plus the remembered window position and
// folded state.
//
// The window is our own DOM subtree appended to the document body. It never modifies any
// element the game renders — sharing a node with the game's React tree means React keeps
// its own reference and either overwrites us or strands our markup on screen.
//
// Pointer events are the important constraint here: the root stays `pointer-events: none`
// so the window can never swallow the garage's drag-to-rotate, and exactly one child (the
// header bar) re-enables them. In this Coherent build, elements nested under a
// pointer-events:none root do not reliably receive events even when they set
// pointer-events:auto themselves, so all interaction is routed through that one element.
//
// See docs/reference/gameface-mod-widgets.md.

const ROOT_ID = 'zanju-dh-root';
const DATA_PROPERTY = 'zanjuDhWindow';
// The snapshot normally arrives by push (see bindModelPush): this is the backstop for the
// case where that channel could not be established, and the rate it drops to then.
const POLL_INTERVAL_MS = 1000;
const UNPUSHED_POLL_INTERVAL_MS = 250;
// Flag on the document so the document-level drag listener is registered once, even if this
// module is evaluated again for another sub-view.
const DRAG_BOUND_FLAG = '__zanjuDhDragBound';
const CLICK_BOUND_FLAG = '__zanjuDhClickBound';
const PUSH_BOUND_FLAG = '__zanjuDhPushBound';
const DEFAULT_MARGIN_PX = 24;
// Pointer travel before a press counts as a drag rather than a click on the header.
const DRAG_THRESHOLD_PX = 4;

let lastSnapshotJson = null;
// Which sub-view turned out to carry our data model, so the push subscription can name it.
let dataResId = null;
let pollTimer = null;

function log(message) {
    // console.log is not forwarded to python.log by the Gameface host; console.error is.
    console.error('[zanju.directiveshelper] ' + message);
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
    // Python writes the snapshot the moment the depot or the selected tank changes, but a
    // property write is not an event on this side: without this the window would only notice
    // on its next poll, which is a visible lag on something as ordinary as switching tanks.
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

function parseSnapshot(raw) {
    if (!raw) {
        return null;
    }
    try {
        return JSON.parse(raw);
    } catch (e) {
        log('could not parse the snapshot: ' + e);
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

function buildRoot() {
    const root = el('div', 'zanju-dh-root');
    root.id = ROOT_ID;

    // The only element with pointer events: dragging and folding both happen here.
    const header = el('div', 'zanju-dh-header zanju-dh-hot');
    header.appendChild(el('span', 'zanju-dh-fold', '−'));
    // Placeholder only: replaced by the localized title on the first snapshot.
    header.appendChild(el('span', 'zanju-dh-title', 'Directives Helper'));
    // Only ever shown while folded, when the title bar is all there is to see: without it a
    // folded window would hide the fact that the next battle is about to cost something.
    header.appendChild(buildWarnMark('zanju-dh-header-warn'));
    root.appendChild(header);

    root.appendChild(el('div', 'zanju-dh-body'));
    // Width only: the tiles are a wrapping grid, so widening the window is what changes the
    // layout (more icons per row) while the height simply follows the content. A height handle
    // would have nothing to give.
    root.appendChild(el('div', 'zanju-dh-resize zanju-dh-hot'));
    document.body.appendChild(root);
    return root;
}

function clampWidth(width) {
    // As a fraction of the viewport rather than in pixels: WoT's UI scale is quantized per
    // resolution bucket, so a pixel floor that is sensible at 1080p is tiny at 4K.
    const viewport = window.innerWidth || 0;
    if (!viewport) {
        return Math.max(1, Math.round(width));
    }
    return Math.max(Math.round(viewport * 0.10),
        Math.min(Math.round(viewport * 0.60), Math.round(width)));
}

function applyWidth(root, state) {
    const stored = Number(unwrap(state.width)) || 0;
    if (stored <= 0) {
        return; // never resized: let the stylesheet size it
    }
    const capturedW = Number(unwrap(state.viewportWidth)) || 0;
    const viewport = window.innerWidth || 0;
    let width = stored;
    if (capturedW > 0 && viewport > 0) {
        width = (stored / capturedW) * viewport;
    }
    root.style.width = clampWidth(width) + 'px';
}

function getRoot() {
    return document.getElementById(ROOT_ID);
}

function iconUrl(iconName) {
    // Gameface resolves the game's own resource paths in a url(), which is how the client's
    // stylesheets reference its images. Directive icons live under the artefact folder.
    return iconName ? "url('R.images.gui.maps.icons.artefact." + iconName + "')" : '';
}

// A number on a tile, built the way the client builds its own.
//
// The client's `Counter` component is an absolutely positioned box whose value sits in a
// `display: flex` child. It never puts text directly on the box that positions it, and that
// shape is what stopped the overlays on a tile painting in the wrong place. See "An Overlay
// That Carries Its Own Text Can Shift Its Siblings" in docs/reference/gameface-mod-widgets.md.
//
// Placement is the stylesheet's: `.zanju-dh-gain` pins itself top-right, `.zanju-dh-badge`
// bottom-left, `.zanju-dh-tip` above the tile.
function mark(className, text) {
    const box = el('div', className);
    box.appendChild(el('div', 'zanju-dh-mark-value', text));
    return box;
}


function buildTile(directive, texts) {
    // Only directives that fit the selected tank reach this point, so every tile is shown at
    // full strength; the fitted one is outlined, and one the player owns none of is dimmed and
    // offers to buy it instead of fitting.
    const unowned = directive.owned === false;
    // Reward-only directives cannot be bought. They are still listed — a tile that quietly
    // vanished would be more confusing than one that says why — but nothing happens on click.
    const buyable = unowned && directive.purchasable !== false;
    let className = 'zanju-dh-tile';
    if (directive.equipped) {
        className += ' zanju-dh-tile-equipped';
    }
    if (unowned) {
        className += ' zanju-dh-tile-unowned';
    }
    if (unowned && !buyable) {
        className += ' zanju-dh-tile-inert';
    }
    const tile = el('div', className);

    const icon = el('div', 'zanju-dh-icon');
    icon.style.backgroundImage = iconUrl(directive.icon);
    tile.appendChild(icon);

    // Both numbers sit over the icon, in opposite corners so they can never meet however many
    // digits either grows to: the gain top-right, the depot count bottom-left.
    if (typeof directive.gain === 'number' && directive.gain > 0) {
        tile.appendChild(mark('zanju-dh-gain', '+' + directive.gain + '%'));
    }
    tile.appendChild(mark('zanju-dh-badge', String(directive.count)));
    // The name only shows on hover, so a full depot stays a compact grid of icons. An unowned
    // one also says what a click will do, since it is the one tile that does not fit anything.
    let tip = directive.name;
    if (unowned && texts) {
        tip += ' — ' + (buyable ? texts.buyHint : texts.buyUnavailable);
    }
    tile.appendChild(mark('zanju-dh-tip', tip));
    // Read back by the click handler; the event may land on any child of the tile. Left unset
    // on a tile with nothing to do, which is what makes the click walk up, find no marker and
    // fall through — rather than reaching the fit path with a directive that cannot be fitted.
    if (!unowned || buyable) {
        tile._zanjuDhIntCD = directive.intCD;
    }
    tile._zanjuDhBuy = buyable;
    return tile;
}


function buildWarnMark(extraClass) {
    // Drawn from two boxes rather than typed as a `!`. This renderer ignores `text-indent`
    // outright and did not move the glyph for `letter-spacing` either, so there is no reliable
    // way to correct for the font's side bearings and centre a character in the circle. Two
    // positioned boxes are centred by arithmetic, come out identical in both badges, and make
    // the stroke weight ours to pick instead of the font's.
    const mark = el('div', 'zanju-dh-warn-mark' + (extraClass ? ' ' + extraClass : ''));
    mark.appendChild(el('div', 'zanju-dh-warn-stem'));
    mark.appendChild(el('div', 'zanju-dh-warn-dot'));
    return mark;
}

function buildAutoResupplyRow(snapshot, texts) {
    const row = el('div', 'zanju-dh-auto');
    if (typeof snapshot.autoResupply !== 'boolean') {
        // No tank in the garage, or the setting could not be read. Python hides the whole
        // window in that case and logs why, so this is only ever the frame or so before that
        // reaches us: leave the row empty rather than offer a toggle over a guessed state.
        return row;
    }

    // The tick is a box that fills when checked rather than a check glyph: the game's font is
    // not guaranteed to carry one, and a missing glyph renders as an empty box — which reads
    // as exactly the opposite state.
    row.appendChild(el('div', 'zanju-dh-check' + (snapshot.autoResupply ? ' zanju-dh-check-on' : '')));
    row.appendChild(el('span', 'zanju-dh-check-label', texts.autoResupply));

    if (snapshot.resupplyWarning) {
        // Lives inside this row, which is present whatever the state, so the warning coming
        // and going never moves the sections below it.
        const warning = el('div', 'zanju-dh-warning');
        warning.appendChild(buildWarnMark());
        warning.appendChild(el('span', 'zanju-dh-warn-tip', texts.resupplyWarning));
        row.appendChild(warning);
    }

    // Read back by the click handler, the same way a tile carries its intCD. Clicking the
    // warning marker toggles too, which is the fix it is pointing at.
    row._zanjuDhAutoToggle = true;
    row.className = 'zanju-dh-auto zanju-dh-clickable';
    return row;
}


function buildShowUnownedRow(snapshot, texts) {
    const row = el('div', 'zanju-dh-option zanju-dh-clickable');
    const on = Boolean(snapshot.showUnowned);
    row.appendChild(el('div', 'zanju-dh-check' + (on ? ' zanju-dh-check-on' : '')));
    row.appendChild(el('span', 'zanju-dh-check-label', texts.showUnowned));
    row._zanjuDhShowUnowned = !on;
    return row;
}


function fmtRect(rect) {
    return Math.round(rect.left) + ',' + Math.round(rect.top)
        + ' ' + Math.round(rect.width) + 'x' + Math.round(rect.height);
}

// One line per number that is not on its own tile, so a garbled grid can be read back out of
// python.log instead of a screenshot. Kept as a standing guard: it is silent when the layout is
// right, and it is what proved the elements were never the problem. `console.error` is the level that reaches that log;
// `console.log` does not. Silent when everything is where it should be.
function reportMisplaced(grids) {
    if (typeof console === 'undefined' || typeof console.error !== 'function') {
        return;
    }
    for (const grid of grids) {
        const tiles = grid.children || [];
        if (typeof grid._zanjuDhExpected === 'number' && tiles.length !== grid._zanjuDhExpected) {
            console.error('zanju-dh: grid holds ' + tiles.length + ' tiles, built '
                + grid._zanjuDhExpected + ' -- the previous render was not torn down');
        }
        for (let index = 0; index < tiles.length; index += 1) {
            const tile = tiles[index];
            if (typeof tile.getBoundingClientRect !== 'function' || !tile.querySelectorAll) {
                return;
            }
            const box = tile.getBoundingClientRect();
            const marks = tile.querySelectorAll('.zanju-dh-gain, .zanju-dh-badge');
            for (let mark = 0; mark < marks.length; mark += 1) {
                const spot = marks[mark].getBoundingClientRect();
                const inside = spot.left >= box.left - 1 && spot.right <= box.right + 1
                    && spot.top >= box.top - 1 && spot.bottom <= box.bottom + 1;
                if (!inside) {
                    console.error('zanju-dh: ' + marks[mark].className + ' is off tile ' + index
                        + ' -- tile ' + fmtRect(box) + ', mark ' + fmtRect(spot));
                }
            }
        }
    }
}

// The check runs after layout, never in the frame that built the DOM: rectangles read in the
// same frame describe the layout as it stood before. Two frames is what the campaign tracker
// card needed for the same reason.
function scheduleCheck(grids) {
    if (!grids.length || typeof requestAnimationFrame !== 'function') {
        return;
    }
    requestAnimationFrame(function () {
        requestAnimationFrame(function () { reportMisplaced(grids); });
    });
}


// `textContent = ''` is the obvious way to empty a node, and it is what this used to do. It is
// also one operation the renderer has to interpret, and old text sitting on screen beside the new
// text -- each cleared only by hovering its own tile -- is what a subtree that was not fully torn
// down looks like. Removing the children one at a time says the same thing in the most ordinary
// way there is, and leaves the renderer nothing to interpret.
function clearChildren(node) {
    if (typeof node.removeChild !== 'function') {
        node.textContent = '';
        return;
    }
    while (node.children.length) {
        node.removeChild(node.children[node.children.length - 1]);
    }
}


function renderBody(body, snapshot, texts) {
    clearChildren(body);

    body.appendChild(buildAutoResupplyRow(snapshot, texts));
    body.appendChild(buildShowUnownedRow(snapshot, texts));

    const groups = snapshot.categories || [];
    const grids = [];
    for (const group of groups) {
        const directives = group.directives || [];
        const heading = el('div', 'zanju-dh-category');
        heading.appendChild(el('span', 'zanju-dh-category-name', texts.categories[group.category] || group.category));
        body.appendChild(heading);

        if (!directives.length) {
            // Kept visible so the three sections stay in the same order and place, whatever
            // the selected tank can take.
            body.appendChild(el('div', 'zanju-dh-empty', texts.sectionEmpty));
            continue;
        }

        const grid = el('div', 'zanju-dh-grid');
        // Recorded so the check can say whether the grid holds the tiles it was given, or is
        // still carrying tiles from the render before.
        grid._zanjuDhExpected = directives.length;
        grids.push(grid);
        for (const directive of directives) {
            grid.appendChild(buildTile(directive, texts));
        }
        body.appendChild(grid);
    }

    if (!groups.length) {
        // A real snapshot always carries all three categories, empty ones included, so this is
        // only reached when the payload has none at all: Python failed to build it and logged
        // why. Deliberately not localised — that same failure drops the labels too, so a
        // translated string here could never be the one displayed.
        body.appendChild(el('div', 'zanju-dh-muted', 'Directives unavailable'));
    }

    scheduleCheck(grids);
}

function applyPosition(root, state) {
    if (root._zanjuDhDragging) {
        return; // never fight an in-progress drag
    }
    // Applied once, when the window is first built. The stored position is pushed to Python
    // on release but the view model keeps its original values, so re-applying every tick
    // would drag the window back to where it started a moment after each drop.
    if (root._zanjuDhPositioned) {
        return;
    }
    root._zanjuDhPositioned = true;
    const x = Number(unwrap(state.x));
    const y = Number(unwrap(state.y));
    if (!(x >= 0) || !(y >= 0)) {
        // Never positioned: park it in the top-left corner, clear of the header strip.
        root.style.left = DEFAULT_MARGIN_PX + 'px';
        root.style.top = (DEFAULT_MARGIN_PX * 4) + 'px';
        return;
    }

    // Rescale a position captured at a different resolution: WoT's UI scale is quantized per
    // resolution bucket, so raw pixels would strand the window off-screen otherwise.
    const capturedW = Number(unwrap(state.viewportWidth)) || 0;
    const capturedH = Number(unwrap(state.viewportHeight)) || 0;
    const w = window.innerWidth || 0;
    const h = window.innerHeight || 0;
    let left = x;
    let top = y;
    if (capturedW > 0 && capturedH > 0 && w > 0 && h > 0) {
        left = Math.round((x / capturedW) * w);
        top = Math.round((y / capturedH) * h);
    }
    if (w) {
        left = Math.max(0, Math.min(w - 40, left));
    }
    if (h) {
        top = Math.max(0, Math.min(h - 20, top));
    }
    root.style.left = left + 'px';
    root.style.top = top + 'px';
}

function applyHeaderWarning(root, warn) {
    // Marks the element; the stylesheet decides it is only actually shown while folded, so
    // the unfolded window is not carrying the same warning twice.
    const mark = root.querySelector('.zanju-dh-header-warn');
    if (mark) {
        mark.className = 'zanju-dh-warn-mark zanju-dh-header-warn'
            + (warn ? ' zanju-dh-header-warn-on' : '');
    }
}

function applyFolded(root, folded) {
    if (folded) {
        root.className = 'zanju-dh-root zanju-dh-folded';
    } else {
        root.className = 'zanju-dh-root';
    }
    const toggle = root.querySelector('.zanju-dh-fold');
    if (toggle) {
        toggle.textContent = folded ? '+' : '−';
    }
}

function clickTargetFrom(node) {
    // A click lands on whatever is under the cursor — a tile's icon, its badge or its
    // tooltip, or one of the spans in an option row — so walk up to the element that says
    // what the click means.
    let current = node;
    for (let depth = 0; current && depth < 4; depth += 1) {
        if (current._zanjuDhIntCD !== undefined
            || current._zanjuDhAutoToggle
            || current._zanjuDhShowUnowned !== undefined) {
            return current;
        }
        current = current.parentNode;
    }
    return null;
}

function bindTileClicks(data) {
    // Bound at document level in the capture phase, the same path the drag uses. A plain
    // `click` listener on our own element did not fire in this renderer, whereas the
    // document-capture mouse events demonstrably reach us.
    if (document[CLICK_BOUND_FLAG]) {
        return;
    }
    document[CLICK_BOUND_FLAG] = true;

    document.addEventListener('mouseup', function (event) {
        const root = getRoot();
        if (!root || root._zanjuDhDidDrag) {
            return; // the press that ended a drag is not a click on a tile
        }
        const target = clickTargetFrom(event.target);
        if (!target || !isWithin(root, target)) {
            return;
        }
        // Every action goes through the game's own processors on the Python side, which push a
        // fresh snapshot when they finish; the window renders that rather than guessing here.
        if (target._zanjuDhAutoToggle) {
            invokeCommand(data, 'toggleAutoResupply', {});
            return;
        }
        if (target._zanjuDhShowUnowned !== undefined) {
            invokeCommand(data, 'setShowUnowned', { showUnowned: target._zanjuDhShowUnowned });
            return;
        }
        if (target._zanjuDhBuy) {
            // Owning none of it, so there is nothing to fit: open the game's buy dialog.
            invokeCommand(data, 'buy', { intCD: target._zanjuDhIntCD });
            return;
        }
        invokeCommand(data, 'equip', { intCD: target._zanjuDhIntCD });
    }, true);
}

function bindHeader(root, data) {
    const header = root.querySelector('.zanju-dh-header');
    if (!header || header._zanjuDhBound) {
        return;
    }
    header._zanjuDhBound = true;

    header.addEventListener('click', function (event) {
        // A click that ended a drag must not also toggle the fold.
        if (root._zanjuDhDidDrag) {
            return;
        }
        const folded = root.className.indexOf('zanju-dh-folded') === -1;
        applyFolded(root, folded);
        invokeCommand(data, 'setFolded', { folded: folded });
        event.stopPropagation();
    });
}

function isWithin(ancestor, node) {
    // Walks up checking identity first, rather than using `ancestor.contains(node)`. The
    // resize grip is the only interactive element here with no children, so a press on it
    // targets the grip itself — and this renderer's `contains` does not report a node as
    // containing itself, which silently made the grip inert. The header never showed the bug
    // because its fold and title spans are always the real target. Same reason
    // `clickTargetFrom` checks the node before walking up.
    let current = node;
    for (let depth = 0; ancestor && current && depth < 8; depth += 1) {
        if (current === ancestor) {
            return true;
        }
        current = current.parentNode;
    }
    return false;
}

function inRect(element, event) {
    // Only ever consulted for a press already known to be inside this window, as a fallback
    // for a renderer that reports an unexpected target: rectangles are not safe for deciding
    // ownership between mods, but they are exact for deciding which of our own parts was hit.
    try {
        const rect = element.getBoundingClientRect();
        return event.clientX >= rect.left && event.clientX <= rect.right
            && event.clientY >= rect.top && event.clientY <= rect.bottom;
    } catch (e) {
        return false;
    }
}

function startResize(root, data, event) {
    const startX = event.clientX;
    const startWidth = root.getBoundingClientRect().width;
    // Suppresses the fold-on-click, exactly as a move does: a resize that ends over the
    // header must not also collapse the window.
    root._zanjuDhDragging = true;
    root._zanjuDhDidDrag = true;

    const onMove = function (moveEvent) {
        root.style.width = clampWidth(startWidth + (moveEvent.clientX - startX)) + 'px';
    };

    const onUp = function () {
        document.removeEventListener('mousemove', onMove, true);
        document.removeEventListener('mouseup', onUp, true);
        root._zanjuDhDragging = false;
        invokeCommand(data, 'setSize', {
            width: Math.round(root.getBoundingClientRect().width),
            // Recorded so a later resolution change can rescale proportionally.
            w: window.innerWidth || 0,
            h: window.innerHeight || 0,
        });
        setTimeout(function () {
            root._zanjuDhDidDrag = false;
        }, 0);
    };

    document.addEventListener('mousemove', onMove, true);
    document.addEventListener('mouseup', onUp, true);
}

function bindDrag(data) {
    if (document[DRAG_BOUND_FLAG]) {
        return;
    }
    document[DRAG_BOUND_FLAG] = true;

    // The listener sits at document level in the CAPTURE phase and claims the drag only when
    // the press landed
    // inside our own subtree: OpenWG drops several mods into this document as body siblings
    // at similar z-index, any of which may also be draggable. Deciding ownership by subtree
    // rather than by hit-testing rectangles is what lets us coexist with them — two
    // overlapping widgets' rectangles can both contain the point, and then whichever
    // listener registered first wins nondeterministically.
    const onDragStart = function (event) {
        const root = getRoot();
        if (!root) {
            return;
        }
        // Ownership stays a subtree question; only which of our own parts was pressed is
        // decided by geometry, and only once the press is known to be ours.
        const ours = isWithin(root, event.target);
        // Checked before the title bar: the two do not overlap, but deciding in one place
        // keeps a press from ever being read as both.
        const grip = root.querySelector('.zanju-dh-resize');
        if (grip && (isWithin(grip, event.target) || (ours && inRect(grip, event)))) {
            event.stopImmediatePropagation();
            event.preventDefault();
            startResize(root, data, event);
            return;
        }
        // Only the title bar is a drag handle; a press on the body is for the tiles.
        const header = root.querySelector('.zanju-dh-header');
        if (!isWithin(header, event.target)) {
            return; // not ours: never stop an event belonging to another mod
        }
        event.stopImmediatePropagation();
        event.preventDefault();

        const rect = root.getBoundingClientRect();
        const offsetX = event.clientX - rect.left;
        const offsetY = event.clientY - rect.top;
        root._zanjuDhDragging = true;
        // Only counts as a drag once the pointer actually travels: a press that never moves
        // is a click, and must still fold the window.
        root._zanjuDhDidDrag = false;
        const startX = event.clientX;
        const startY = event.clientY;

        const onMove = function (moveEvent) {
            if (!root._zanjuDhDidDrag) {
                const travelled = Math.abs(moveEvent.clientX - startX) + Math.abs(moveEvent.clientY - startY);
                if (travelled < DRAG_THRESHOLD_PX) {
                    return;
                }
                root._zanjuDhDidDrag = true;
            }
            const w = window.innerWidth || 0;
            const h = window.innerHeight || 0;
            let left = moveEvent.clientX - offsetX;
            let top = moveEvent.clientY - offsetY;
            if (w) {
                left = Math.max(0, Math.min(w - 40, left));
            }
            if (h) {
                top = Math.max(0, Math.min(h - 20, top));
            }
            root.style.left = Math.round(left) + 'px';
            root.style.top = Math.round(top) + 'px';
        };

        const onUp = function () {
            document.removeEventListener('mousemove', onMove, true);
            document.removeEventListener('mouseup', onUp, true);
            root._zanjuDhDragging = false;
            if (!root._zanjuDhDidDrag) {
                return; // a click, not a drag: leave the position alone and let it fold
            }
            const finalRect = root.getBoundingClientRect();
            invokeCommand(data, 'setPosition', {
                x: Math.round(finalRect.left),
                y: Math.round(finalRect.top),
                // Recorded so a later resolution change can rescale proportionally.
                w: window.innerWidth || 0,
                h: window.innerHeight || 0,
            });
            // Let the click that follows this mouseup see the flag, then clear it.
            setTimeout(function () {
                root._zanjuDhDidDrag = false;
            }, 0);
        };

        document.addEventListener('mousemove', onMove, true);
        document.addEventListener('mouseup', onUp, true);
    };

    document.addEventListener('mousedown', onDragStart, true);
}

function texts(snapshot) {
    // Labels ride along in the snapshot so the Python side owns translation.
    const labels = (snapshot && snapshot.labels) || {};
    return {
        title: labels.title || 'Directives Helper',
        autoResupply: labels.autoResupply || 'Auto-resupply',
        resupplyWarning: labels.resupplyWarning
            || 'Your last one. Auto-resupply will buy another after the battle.',
        showUnowned: labels.showUnowned || 'Show unowned',
        buyHint: labels.buyHint || 'click to buy',
        buyUnavailable: labels.buyUnavailable || 'purchase not available',
        sectionEmpty: labels.sectionEmpty || 'No directives meeting criteria',
        categories: {
            equipment: labels.equipment || 'Equipment',
            crewImprove: labels.crewImprove || 'Improve perk effect',
            crewGrant: labels.crewGrant || 'Boost perk to 100%',
        },
    };
}

function tick() {
    const data = findDataModel();
    if (!data) {
        return;
    }

    let root = getRoot();
    if (!root) {
        root = buildRoot();
        applyFolded(root, Boolean(unwrap(data.folded)));
        applyWidth(root, data);
        bindHeader(root, data);
        bindTileClicks(data);
        bindDrag(data);
    }

    bindModelPush();

    applyPosition(root, data);

    // Three conditions decide this, all on the Python side; see window_inject.py.
    const visible = unwrap(data.visible);
    root.style.display = visible === false ? 'none' : 'flex';

    const raw = unwrap(data.snapshot);
    if (raw === lastSnapshotJson) {
        return; // nothing changed since the last render
    }
    lastSnapshotJson = raw;

    const snapshot = parseSnapshot(raw);
    if (!snapshot) {
        return;
    }
    const labels = texts(snapshot);
    const title = root.querySelector('.zanju-dh-title');
    if (title) {
        title.textContent = labels.title;
    }
    applyHeaderWarning(root, Boolean(snapshot.resupplyWarning));
    renderBody(root.querySelector('.zanju-dh-body'), snapshot, labels);
}

function setPollRate(intervalMs) {
    if (pollTimer !== null) {
        clearInterval(pollTimer);
    }
    pollTimer = setInterval(tick, intervalMs);
}

function start() {
    log('window.js loaded');
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

// Exported for the test suite only: the game loads this module for its side effect,
// via the auto-start above. Anything not imported by window.test.js stays internal.
export {
    applyFolded,
    applyHeaderWarning,
    applyWidth,
    clampWidth,
    isWithin,
    applyPosition,
    buildRoot,
    findDataModel,
    parseSnapshot,
    renderBody,
    texts,
    tick,
    ROOT_ID,
};
