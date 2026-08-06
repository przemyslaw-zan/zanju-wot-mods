// Tests for the garage directives window.
//
// Run via `zwm test directives-helper`. The module auto-starts only when a Gameface view
// registry is present, so importing it here neither builds a window nor starts a timer.

import { test, describe, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

import {
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
} from '../res/gui/gameface/mods/zanju_directives/window.js';

class FakeNode {
    constructor(tag = 'div', className = '') {
        this.tag = tag;
        this.className = className;
        this.id = '';
        this.children = [];
        this._text = '';
        this.parentNode = null;
        this.style = new Proxy({}, {
            get: (target, key) => (key in target ? target[key] : ''),
            set: (target, key, value) => {
                target[key] = value;
                return true;
            },
        });
    }

    get textContent() {
        return this.children.length ? this.children.map((c) => c.textContent).join('') : this._text;
    }

    set textContent(value) {
        this.children = [];
        this._text = value;
    }

    appendChild(child) {
        this.children.push(child);
        child.parentNode = this;
        return child;
    }

    contains(node) {
        if (node === this) {
            return true;
        }
        return this.children.some((child) => child.contains(node));
    }

    querySelectorAll(selector) {
        const wanted = selector.replace(/^\./, '');
        const found = [];
        for (const child of this.children) {
            if (child.className.split(' ').includes(wanted)) {
                found.push(child);
            }
            found.push(...child.querySelectorAll(selector));
        }
        return found;
    }

    querySelector(selector) {
        return this.querySelectorAll(selector)[0] || null;
    }
}

function snapshotFixture(overrides = {}) {
    return Object.assign(
        {
            vehicleName: 'Object 260',
            hasVehicle: true,
            autoResupply: true,
            resupplyWarning: false,
            showUnowned: false,
            labels: {
                title: 'Directives',
                equipment: 'Equipment',
                crewImprove: 'Improve perk effect',
                crewGrant: 'Boost perk to 100%',
                sectionEmpty: 'No directives meeting criteria',
                autoResupply: 'Auto-resupply',
                resupplyWarning: 'Your last one. Auto-resupply will buy another after the battle.',
                showUnowned: 'Show unowned',
                buyHint: 'click to buy',
                buyUnavailable: 'purchase not available',
            },
            categories: [
                {
                    category: 'equipment',
                    total: 6,
                    directives: [
                        { intCD: 2, name: 'Improved Aiming', icon: 'improvedSights', count: 6, equipped: true },
                    ],
                },
                {
                    category: 'crewImprove',
                    total: 75,
                    directives: [
                        { intCD: 1, name: 'Repairs', icon: 'repairs', count: 75, equipped: false },
                    ],
                },
                {
                    category: 'crewGrant',
                    total: 9,
                    directives: [
                        { intCD: 3, name: 'Adrenaline', icon: 'adrenaline', count: 9, equipped: false },
                    ],
                },
            ],
        },
        overrides
    );
}

describe('parseSnapshot', () => {
    const realConsoleError = console.error;

    beforeEach(() => {
        console.error = () => {};
    });

    afterEach(() => {
        console.error = realConsoleError;
    });

    test('reads a JSON payload', () => {
        assert.deepEqual(parseSnapshot('{"hasVehicle":true}'), { hasVehicle: true });
    });

    test('returns null for an empty payload', () => {
        assert.equal(parseSnapshot(''), null);
    });

    test('survives malformed JSON', () => {
        assert.equal(parseSnapshot('{oops'), null);
    });
});

describe('texts', () => {
    test('uses the labels the Python side supplied', () => {
        const labels = texts(snapshotFixture());
        assert.equal(labels.categories.crewImprove, 'Improve perk effect');
        assert.equal(labels.categories.crewGrant, 'Boost perk to 100%');
        assert.equal(labels.autoResupply, 'Auto-resupply');
    });

    test('falls back to English when labels are missing', () => {
        // Translation lives on the Python side; if the payload arrives without labels the
        // window still has to render something readable.
        const labels = texts({});
        assert.equal(labels.title, 'Directives Helper');
        assert.equal(labels.categories.equipment, 'Equipment');
    });
});

describe('renderBody', () => {
    beforeEach(() => {
        globalThis.document = { createElement: (tag) => new FakeNode(tag) };
    });

    afterEach(() => {
        delete globalThis.document;
    });

    function render(snapshot) {
        const body = new FakeNode();
        renderBody(body, snapshot, texts(snapshot));
        return body;
    }

    test('gives every directive a tile with its count and name', () => {
        const body = render(snapshotFixture());
        const names = body.querySelectorAll('.zanju-dh-tip').map((n) => n.textContent);
        const counts = body.querySelectorAll('.zanju-dh-badge').map((n) => n.textContent);
        assert.deepEqual(names, ['Improved Aiming', 'Repairs', 'Adrenaline']);
        assert.deepEqual(counts, ['6', '75', '9']);
    });

    test('points each tile at the game\'s own artefact icon', () => {
        const body = render(snapshotFixture());
        const icon = body.querySelector('.zanju-dh-icon');
        assert.match(icon.style.backgroundImage, /R\.images\.gui\.maps\.icons\.artefact\.improvedSights/);
    });

    test('shows every category heading', () => {
        const body = render(snapshotFixture());
        const headings = body.querySelectorAll('.zanju-dh-category-name').map((n) => n.textContent);
        assert.deepEqual(headings, ['Equipment', 'Improve perk effect', 'Boost perk to 100%']);
        assert.equal(body.querySelectorAll('.zanju-dh-category-total').length, 0,
            'the per-category sum was dropped');
    });

    test('ticks the checkbox when auto-resupply is on', () => {
        const body = render(snapshotFixture());
        const row = body.querySelector('.zanju-dh-auto');
        assert.match(row.textContent, /Auto-resupply/);
        assert.match(row.querySelector('.zanju-dh-check').className, /zanju-dh-check-on/);
    });

    test('leaves the checkbox empty when auto-resupply is off', () => {
        const body = render(snapshotFixture({ autoResupply: false }));
        const row = body.querySelector('.zanju-dh-auto');
        assert.doesNotMatch(row.querySelector('.zanju-dh-check').className, /zanju-dh-check-on/);
    });

    test('warns when resupply would buy a replacement', () => {
        const body = render(snapshotFixture({ resupplyWarning: true }));
        const warning = body.querySelector('.zanju-dh-warning');
        assert.ok(warning, 'the warning should be shown');
        assert.match(warning.querySelector('.zanju-dh-warn-tip').textContent, /buy another/);
    });

    test('the warning mark is drawn, not typed', () => {
        // A `!` character could not be centred in the circle: this renderer ignores
        // text-indent, letter-spacing did not move it, and text-align behaved differently in
        // the two badges. Two positioned boxes are centred by arithmetic instead.
        const mark = render(snapshotFixture({ resupplyWarning: true }))
            .querySelector('.zanju-dh-warn-mark');
        assert.ok(mark.querySelector('.zanju-dh-warn-stem'), 'the stem should be drawn');
        assert.ok(mark.querySelector('.zanju-dh-warn-dot'), 'the dot should be drawn');
        assert.equal(mark.textContent, '', 'no glyph should be relied on');
    });

    test('no warning when there is nothing to warn about', () => {
        const body = render(snapshotFixture());
        assert.equal(body.querySelector('.zanju-dh-warning'), null);
    });

    test('the warning shares the checkbox row so nothing below it moves', () => {
        // The row exists in both states; only its contents differ. If the warning ever became
        // a row of its own, every section under it would jump as it came and went.
        const quiet = render(snapshotFixture());
        const warned = render(snapshotFixture({ resupplyWarning: true }));
        const rowIndex = (body) => body.children.findIndex((c) => /zanju-dh-auto/.test(c.className));
        assert.equal(rowIndex(quiet), rowIndex(warned));
        assert.equal(quiet.children.length, warned.children.length);
        assert.ok(warned.querySelector('.zanju-dh-auto').contains(
            warned.querySelector('.zanju-dh-warning')), 'the warning belongs to the row');
    });

    test('offers a checkbox for listing directives you do not own', () => {
        const row = render(snapshotFixture()).querySelector('.zanju-dh-option');
        assert.match(row.textContent, /Show unowned/);
        assert.doesNotMatch(row.querySelector('.zanju-dh-check').className, /zanju-dh-check-on/);
        assert.equal(row._zanjuDhShowUnowned, true, 'clicking it should turn the option on');
    });

    test('the unowned checkbox reports the opposite of its current state', () => {
        const row = render(snapshotFixture({ showUnowned: true })).querySelector('.zanju-dh-option');
        assert.match(row.querySelector('.zanju-dh-check').className, /zanju-dh-check-on/);
        assert.equal(row._zanjuDhShowUnowned, false, 'clicking it should turn the option off');
    });

    test('a directive you own none of routes its click to the store', () => {
        const snapshot = snapshotFixture();
        snapshot.categories[1].directives[0].owned = false;
        snapshot.categories[1].directives[0].count = 0;
        const tile = render(snapshot).querySelectorAll('.zanju-dh-tile')[1];
        assert.match(tile.className, /zanju-dh-tile-unowned/);
        assert.equal(tile._zanjuDhBuy, true);
        assert.match(tile.querySelector('.zanju-dh-tip').textContent, /click to buy/);
    });

    test('a directive that cannot be bought says so and does nothing', () => {
        // Reward-only ones stay visible rather than vanishing, but a click must not reach the
        // buy dialog (it would divide by their zero price) nor the fit path (nothing to fit).
        const snapshot = snapshotFixture();
        Object.assign(snapshot.categories[1].directives[0],
            { owned: false, count: 0, purchasable: false });
        const tile = render(snapshot).querySelectorAll('.zanju-dh-tile')[1];
        assert.match(tile.className, /zanju-dh-tile-inert/);
        assert.match(tile.querySelector('.zanju-dh-tip').textContent, /purchase not available/);
        assert.equal(tile._zanjuDhBuy, false);
        assert.equal(tile._zanjuDhIntCD, undefined, 'nothing for the click handler to act on');
    });

    test('an owned directive is never routed to the store', () => {
        // `owned` is absent from older payloads, so the default must be "fit it", never "buy".
        const tile = render(snapshotFixture()).querySelectorAll('.zanju-dh-tile')[0];
        assert.doesNotMatch(tile.className, /zanju-dh-tile-unowned/);
        assert.equal(tile._zanjuDhBuy, false);
    });

    test('clicking the warning toggles the setting too', () => {
        // It marks the row, so a click anywhere in it — marker included — reaches the toggle,
        // which is the fix the warning is pointing at.
        const row = render(snapshotFixture({ resupplyWarning: true })).querySelector('.zanju-dh-auto');
        assert.equal(row._zanjuDhAutoToggle, true);
    });

    test('the auto-resupply row can be clicked to toggle it', () => {
        const row = render(snapshotFixture()).querySelector('.zanju-dh-auto');
        assert.equal(row._zanjuDhAutoToggle, true);
        assert.match(row.className, /zanju-dh-clickable/);
    });

    test('offers no toggle when the setting could not be read', () => {
        // A failed read must not render as "disabled": the click would then act on a guess.
        const row = render(snapshotFixture({ autoResupply: null })).querySelector('.zanju-dh-auto');
        assert.equal(row._zanjuDhAutoToggle, undefined);
        assert.doesNotMatch(row.className, /zanju-dh-clickable/);
        assert.equal(row.textContent, '');
    });

    test('keeps an empty section visible with a placeholder', () => {
        // The three sections stay in the same order and place whatever the tank can take.
        const snapshot = snapshotFixture();
        snapshot.categories[2].directives = [];
        snapshot.categories[2].total = 0;
        const body = render(snapshot);
        assert.equal(body.querySelectorAll('.zanju-dh-category-name').length, 3);
        assert.match(body.querySelector('.zanju-dh-empty').textContent, /No directives meeting criteria/);
    });

    test('tiles carry the id needed to fit them', () => {
        const body = render(snapshotFixture());
        const tile = body.querySelectorAll('.zanju-dh-tile')[0];
        assert.equal(tile._zanjuDhIntCD, 2);
    });

    test('shows how much a grant-perk directive would add', () => {
        const snapshot = snapshotFixture();
        snapshot.categories[2].directives[0].gain = 70;
        const tile = render(snapshot).querySelectorAll('.zanju-dh-tile')[2];
        assert.equal(tile.querySelector('.zanju-dh-gain').textContent, '+70%');
    });

    test('no gain badge where there is nothing to gain', () => {
        // Equipment and already-trained perks carry gain: null, and a perk at 100% would be
        // in the other section anyway — a "+0%" badge would be noise.
        const snapshot = snapshotFixture();
        snapshot.categories[2].directives[0].gain = 0;
        const body = render(snapshot);
        assert.equal(body.querySelectorAll('.zanju-dh-gain').length, 0);
    });

    test('no gain badge when the level could not be read', () => {
        const body = render(snapshotFixture());
        assert.equal(body.querySelectorAll('.zanju-dh-gain').length, 0);
    });

    test('both numbers overlay the icon in opposite corners', () => {
        // Diagonally opposite so they can never meet, however many digits either grows to.
        const snapshot = snapshotFixture();
        snapshot.categories[2].directives[0].gain = 70;
        const tile = render(snapshot).querySelectorAll('.zanju-dh-tile')[2];
        assert.ok(tile.querySelector('.zanju-dh-gain'), 'gain belongs to the tile');
        assert.ok(tile.querySelector('.zanju-dh-badge'), 'count belongs to the tile');
        assert.equal(tile.querySelector('.zanju-dh-icon').children.length, 0,
            'neither is nested inside the icon');
    });

    test('marks the fitted directive', () => {
        const body = render(snapshotFixture());
        const tile = body.querySelectorAll('.zanju-dh-tile').find((t) => t.textContent.includes('Improved Aiming'));
        assert.match(tile.className, /zanju-dh-tile-equipped/);
    });

    test('draws no auto-resupply state when no vehicle is selected', () => {
        // Python hides the window outright in this case, so the row only has to stay silent
        // rather than say anything: it is on screen for at most one frame.
        const body = render(snapshotFixture({ hasVehicle: false, autoResupply: null }));
        assert.equal(body.querySelector('.zanju-dh-auto').textContent, '');
    });

    test('says so when the snapshot could not be built', () => {
        const body = render(snapshotFixture({ categories: [] }));
        assert.match(body.textContent, /Directives unavailable/);
    });

    test('re-rendering replaces the previous rows', () => {
        const body = new FakeNode();
        const snapshot = snapshotFixture();
        renderBody(body, snapshot, texts(snapshot));
        renderBody(body, snapshot, texts(snapshot));
        assert.equal(body.querySelectorAll('.zanju-dh-tile').length, 3, 'tiles must not accumulate');
    });
});

describe('window chrome', () => {
    let root;

    beforeEach(() => {
        const body = new FakeNode('body');
        globalThis.document = {
            body,
            createElement: (tag) => new FakeNode(tag),
            getElementById: (id) => body.children.find((child) => child.id === id) || null,
        };
        root = buildRoot();
    });

    afterEach(() => {
        delete globalThis.document;
    });

    test('shows and hides with the garage view', () => {
        // The window belongs to the default garage view only, the same rule the research
        // progress bar follows.
        const data = { snapshot: '{}', visible: false, x: -1, y: -1 };
        globalThis.window = {
            innerWidth: 1920,
            innerHeight: 1080,
            subViews: { ids: () => [1], get: () => ({ model: { zanjuDhWindow: data } }) },
        };
        tick();
        assert.equal(document.getElementById('zanju-dh-root').style.display, 'none');

        data.visible = true;
        tick();
        assert.equal(document.getElementById('zanju-dh-root').style.display, 'flex');
        delete globalThis.window;
    });

    test('does not re-apply a stored position once placed', () => {
        // The drag is reported to Python but the view model keeps its original coordinates,
        // so re-applying would yank the window back a moment after each drop.
        globalThis.window = { innerWidth: 1920, innerHeight: 1080 };
        applyPosition(root, { x: 300, y: 400, viewportWidth: 1920, viewportHeight: 1080 });
        root.style.left = '800px';
        applyPosition(root, { x: 300, y: 400, viewportWidth: 1920, viewportHeight: 1080 });
        assert.equal(root.style.left, '800px', 'the dragged position must survive');
        delete globalThis.window;
    });

    test('the root never takes pointer events, the header does', () => {
        // The garage listens for drag-to-rotate; a root that accepted input everywhere
        // would swallow it and the player could no longer turn the tank.
        assert.equal(root.className, 'zanju-dh-root');
        assert.match(root.querySelector('.zanju-dh-header').className, /zanju-dh-hot/);
    });

    test('marks the title bar so a folded window still warns', () => {
        // Folded, the title bar is all that is left; the stylesheet shows the mark only then,
        // so the flag is set here regardless and CSS decides when it is visible.
        applyHeaderWarning(root, true);
        assert.match(root.querySelector('.zanju-dh-header-warn').className,
            /zanju-dh-header-warn-on/);

        applyHeaderWarning(root, false);
        assert.doesNotMatch(root.querySelector('.zanju-dh-header-warn').className,
            /zanju-dh-header-warn-on/);
    });

    test('folding hides the body and flips the toggle', () => {
        applyFolded(root, true);
        assert.match(root.className, /zanju-dh-folded/);
        assert.equal(root.querySelector('.zanju-dh-fold').textContent, '+');

        applyFolded(root, false);
        assert.doesNotMatch(root.className, /zanju-dh-folded/);
        assert.equal(root.querySelector('.zanju-dh-fold').textContent, '−');
    });

    test('parks the window in a default corner when never positioned', () => {
        applyPosition(root, { x: -1, y: -1, viewportWidth: 0, viewportHeight: 0 });
        assert.equal(root.style.left, '24px');
        assert.ok(parseInt(root.style.top, 10) > 0);
    });

    test('restores a stored position', () => {
        globalThis.window = { innerWidth: 1920, innerHeight: 1080 };
        applyPosition(root, { x: 300, y: 400, viewportWidth: 1920, viewportHeight: 1080 });
        assert.equal(root.style.left, '300px');
        assert.equal(root.style.top, '400px');
        delete globalThis.window;
    });

    test('rescales a position captured at another resolution', () => {
        // WoT's UI scale is quantized per resolution bucket, so raw pixels from a 4K session
        // would strand the window off-screen at 1080p.
        globalThis.window = { innerWidth: 1920, innerHeight: 1080 };
        applyPosition(root, { x: 3000, y: 2000, viewportWidth: 3840, viewportHeight: 2160 });
        assert.equal(root.style.left, '1500px');
        assert.equal(root.style.top, '1000px');
        delete globalThis.window;
    });

    test('clamps a stored position inside the viewport', () => {
        globalThis.window = { innerWidth: 1920, innerHeight: 1080 };
        applyPosition(root, { x: 5000, y: 5000, viewportWidth: 1920, viewportHeight: 1080 });
        assert.ok(parseInt(root.style.left, 10) <= 1920);
        assert.ok(parseInt(root.style.top, 10) <= 1080);
        delete globalThis.window;
    });

    test('offers a resize grip, hidden while folded by the stylesheet', () => {
        // Width only: the tiles wrap, so widening changes how many fit per row while the
        // height just follows the content.
        assert.ok(root.querySelector('.zanju-dh-resize'), 'the grip should exist');
        assert.match(root.querySelector('.zanju-dh-resize').className, /zanju-dh-hot/);
    });

    test('leaves the width alone until the player resizes it', () => {
        globalThis.window = { innerWidth: 1920, innerHeight: 1080 };
        applyWidth(root, { width: 0, viewportWidth: 1920 });
        assert.equal(root.style.width, '', 'the stylesheet should decide the default');
        delete globalThis.window;
    });

    test('restores a stored width', () => {
        globalThis.window = { innerWidth: 1920, innerHeight: 1080 };
        applyWidth(root, { width: 400, viewportWidth: 1920 });
        assert.equal(root.style.width, '400px');
        delete globalThis.window;
    });

    test('rescales a width captured at another resolution', () => {
        globalThis.window = { innerWidth: 1920, innerHeight: 1080 };
        applyWidth(root, { width: 800, viewportWidth: 3840 });
        assert.equal(root.style.width, '400px');
        delete globalThis.window;
    });

    test('clamps the width to a share of the viewport, not a pixel floor', () => {
        // WoT's UI scale is quantized per resolution bucket, so a pixel minimum that is
        // sensible at 1080p is unusably small at 4K.
        globalThis.window = { innerWidth: 1000, innerHeight: 1080 };
        assert.equal(clampWidth(10), 100);
        assert.equal(clampWidth(99999), 600);
        delete globalThis.window;
    });

    test('never moves the window mid-drag', () => {
        root._zanjuDhDragging = true;
        root.style.left = '111px';
        applyPosition(root, { x: 900, y: 900, viewportWidth: 0, viewportHeight: 0 });
        assert.equal(root.style.left, '111px');
    });
});

describe('isWithin', () => {
    // The resize grip is the only interactive element with no children, so a press on it
    // targets the grip itself. `grip.contains(grip)` returns false in the game's renderer,
    // which made the grip render, highlight on hover, and do nothing at all.
    test('an element is within itself', () => {
        const node = new FakeNode();
        assert.equal(isWithin(node, node), true);
    });

    test('finds an ancestor through nested children', () => {
        const root = new FakeNode();
        const mid = root.appendChild(new FakeNode());
        const leaf = mid.appendChild(new FakeNode());
        assert.equal(isWithin(root, leaf), true);
    });

    test('rejects a node from outside the tree', () => {
        assert.equal(isWithin(new FakeNode(), new FakeNode()), false);
    });

    test('survives a missing ancestor or node', () => {
        // Called against a querySelector result, which is null when the window is mid-rebuild.
        assert.equal(isWithin(null, new FakeNode()), false);
        assert.equal(isWithin(new FakeNode(), null), false);
    });
});

describe('model lookup', () => {
    afterEach(() => {
        delete globalThis.window;
    });

    test('finds our data on whichever sub-view was free', () => {
        // The inject lands on the first unclaimed hangar sub-view, so the window locates its
        // model by scanning rather than assuming a fixed one.
        const data = { snapshot: '{}' };
        globalThis.window = {
            subViews: {
                ids: () => [1, 2, 3],
                get: (id) => (id === 3 ? { model: { zanjuDhWindow: data } } : { model: {} }),
            },
        };
        assert.equal(findDataModel(), data);
    });

    test('returns null when no sub-view carries it', () => {
        globalThis.window = { subViews: { ids: () => [1], get: () => ({ model: {} }) } };
        assert.equal(findDataModel(), null);
    });

    test('tick does nothing without a model', () => {
        globalThis.window = { subViews: { ids: () => [], get: () => null } };
        assert.doesNotThrow(() => tick());
    });

    test('re-finding it does not rescan every sub-view', () => {
        // Once model pushes are wired up this runs on every write anywhere in the document,
        // so the repeat lookup has to stay a single get() rather than a full scan.
        const data = { snapshot: '{}' };
        let scans = 0;
        globalThis.window = {
            subViews: {
                ids: () => { scans += 1; return [1, 2, 3]; },
                get: (id) => (id === 3 ? { model: { zanjuDhWindow: data } } : { model: {} }),
            },
        };
        assert.equal(findDataModel(), data);
        assert.equal(scans, 1);
        assert.equal(findDataModel(), data);
        assert.equal(scans, 1, 'the second lookup must not enumerate the sub-views again');
    });

    test('falls back to a scan when the remembered sub-view loses it', () => {
        const data = { snapshot: '{}' };
        let carrier = 3;
        globalThis.window = {
            subViews: {
                ids: () => [1, 2, 3],
                get: (id) => (id === carrier ? { model: { zanjuDhWindow: data } } : { model: {} }),
            },
        };
        assert.equal(findDataModel(), data);
        carrier = 1;
        assert.equal(findDataModel(), data, 'a moved model must still be found');
    });
});
