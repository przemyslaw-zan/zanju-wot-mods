// Tests for the campaign widgets' rendering, run by `node --test`.
//
// The module under test auto-starts only when a Gameface view registry is present, so
// importing it here is free of side effects. A minimal DOM stands in for the renderer:
// only the calls the widgets make are implemented.

import assert from 'node:assert/strict';
import test from 'node:test';

class FakeNode {
    constructor(tag) {
        this.tagName = tag;
        this.className = '';
        this.children = [];
        this.parentNode = null;
        this.style = {};
        this.attributes = {};
        this._text = '';
    }

    get textContent() {
        if (this._text) {
            return this._text;
        }
        return this.children.map((child) => child.textContent).join('');
    }

    set textContent(value) {
        this._text = value;
        this.children = [];
    }

    appendChild(child) {
        child.parentNode = this;
        this.children.push(child);
        return child;
    }

    removeChild(child) {
        this.children = this.children.filter((node) => node !== child);
        child.parentNode = null;
    }

    setAttribute(name, value) {
        this.attributes[name] = value;
    }

    getBoundingClientRect() {
        return this._rect || { left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 };
    }

    _walk(out) {
        for (const child of this.children) {
            out.push(child);
            child._walk(out);
        }
        return out;
    }

    _matches(selector) {
        if (selector.startsWith('.')) {
            return this.className.split(' ').includes(selector.slice(1));
        }
        // `[attr="value"]` and the substring form `[attr*="value"]`, which is how the widgets
        // match the game's content-hashed class names.
        const attribute = selector.match(/^\[([a-z-]+)(\*?)="(.*)"\]$/);
        if (attribute) {
            const [, name, operator, value] = attribute;
            const actual = name === 'class' ? this.className : this.attributes[name];
            if (actual === undefined || actual === null) {
                return false;
            }
            return operator === '*' ? String(actual).includes(value) : actual === value;
        }
        return false;
    }

    querySelector(selector) {
        return this._walk([]).find((node) => node._matches(selector)) || null;
    }

    querySelectorAll(selector) {
        return this._walk([]).filter((node) => node._matches(selector));
    }
}

const body = new FakeNode('body');
global.document = {
    createElement: (tag) => new FakeNode(tag),
    body,
    querySelectorAll: (selector) => body.querySelectorAll(selector),
};
global.window = { innerWidth: 1920, innerHeight: 1080 };
global.console = console;

// Stands in for the garage's own vehicle name and experience block. Its class carries the
// component prefix the widgets match on, plus a content hash like the game's real one.
function addAnchor(rect) {
    const anchor = new FakeNode('div');
    anchor.className = 'VehicleInfoWidget_b24b193a';
    anchor._rect = rect;
    body.appendChild(anchor);
    return anchor;
}

// Detaches through removeChild rather than emptying the list, so a removed node's parentNode
// is cleared exactly as a real DOM would clear it. Anything that tests whether an element is
// still on stage depends on that.
function clearBody() {
    body.children.slice().forEach((child) => body.removeChild(child));
}

const widgets = await import('../res/gui/gameface/mods/zanju_campaigns/widgets.js');

const LABELS = widgets.texts({});

function entry(overrides) {
    return Object.assign({
        branch: 'pm2',
        numeral: 'II',
        campaign: 'The Second Campaign',
        state: 'active',
        mission: 'Union-10. Raise the Flag!',
        missionId: 'UN-10',
        missionShortName: 'Union-10',
        missionNumber: 10,
        line: 'Alliance',
        operation: 'Excalibur',
        operationTitle: 'Operation Excalibur',
        conditions: [],
    }, overrides);
}

test('the badge carries the short mission id, not the mission name', () => {
    assert.equal(widgets.faceId(entry({})), 'UN-10');
});

test('the badge keeps its shape when no mission matches', () => {
    const idle = entry({ mission: null, missionId: '', state: 'nomatch' });
    assert.equal(widgets.faceId(idle), widgets.IDLE_ID);
});

test('only a running mission counts as active', () => {
    assert.equal(widgets.isActive(entry({})), true);
    for (const state of ['nomatch', 'novehicle', 'disabled', 'paused']) {
        assert.equal(widgets.isActive(entry({ state })), false, state);
    }
});

test('each idle state gets its own note, and a running one gets none', () => {
    assert.equal(widgets.stateNote(entry({ state: 'active' }), LABELS), '');
    assert.equal(widgets.stateNote(entry({ state: 'paused' }), LABELS), LABELS.paused);
    assert.equal(widgets.stateNote(entry({ state: 'disabled' }), LABELS), LABELS.disabled);
    assert.equal(widgets.stateNote(entry({ state: 'novehicle' }), LABELS), LABELS.noVehicle);
    assert.equal(widgets.stateNote(entry({ state: 'nomatch' }), LABELS), LABELS.noMission);
});

test('a counted condition shows numbers and a binary one does not', () => {
    assert.equal(widgets.conditionCount({ counted: true, current: 2, goal: 5 }), '2 / 5');
    assert.equal(widgets.conditionCount({ counted: false, current: 0, goal: 1 }), '');
});

test('an idle widget is marked so the stylesheet can grey it', () => {
    const widget = widgets.buildWidget(entry({}));
    widgets.renderWidget(widget, entry({ mission: null, missionId: '', state: 'nomatch' }), LABELS);
    assert.ok(widget.className.includes('zanju-ct-widget-idle'));
    widgets.renderWidget(widget, entry({}), LABELS);
    assert.ok(!widget.className.includes('zanju-ct-widget-idle'));
});

test('the badge stacks the campaign numeral over the mission id', () => {
    const widget = widgets.buildWidget(entry({}));
    widgets.renderWidget(widget, entry({}), LABELS);
    assert.equal(widget.querySelector('.zanju-ct-numeral').textContent, 'II');
    assert.equal(widget.querySelector('.zanju-ct-id').textContent, 'UN-10');
});

test('the hover card heads with the operation over the full mission name', () => {
    const card = document.createElement('div');
    widgets.renderCard(card, entry({}), LABELS);
    assert.equal(card.querySelector('.zanju-ct-card-title').textContent, 'Operation Excalibur');
    assert.equal(
        card.querySelector('.zanju-ct-card-subtitle').textContent, 'Union-10. Raise the Flag!');
});

test('the hover card carries no label-and-value table any more', () => {
    const card = document.createElement('div');
    widgets.renderCard(card, entry({}), LABELS);
    assert.equal(card.querySelectorAll('.zanju-ct-row').length, 0);
    // The line the vehicle falls in is collected for the badge id, never shown on the card.
    assert.ok(!card.textContent.includes('Alliance'));
});

test('the card title falls back to the campaign when there is no operation', () => {
    assert.equal(widgets.cardTitle(entry({ operationTitle: '' })), 'The Second Campaign');
});

function condition(text, overrides) {
    return Object.assign({
        text, counted: false, current: 0, goal: 1,
        done: false, failed: false, main: true, alternative: false,
    }, overrides);
}

test('the hover card splits main conditions from additional ones', () => {
    const card = document.createElement('div');
    widgets.renderCard(card, entry({
        conditions: [
            condition('Destroy 3 vehicles', { counted: true, current: 1, goal: 3 }),
            condition('Survive the battle', { done: true, main: false }),
        ],
    }), LABELS);
    const groups = card.querySelectorAll('.zanju-ct-group').map((node) => node.textContent);
    assert.deepEqual(groups, [LABELS.mainConditions, LABELS.addConditions]);
    assert.equal(card.querySelectorAll('.zanju-ct-cond-done').length, 1);
});

test('the main heading is dropped when there are no additional conditions', () => {
    const card = document.createElement('div');
    widgets.appendConditions(card, [condition('One'), condition('Two')], LABELS);
    assert.equal(card.querySelectorAll('.zanju-ct-group').length, 0);
    assert.equal(card.querySelectorAll('.zanju-ct-cond').length, 2);
});

test('the additional heading is kept even when it is the only group', () => {
    const card = document.createElement('div');
    widgets.appendConditions(card, [condition('Bonus', { main: false })], LABELS);
    const groups = card.querySelectorAll('.zanju-ct-group').map((node) => node.textContent);
    assert.deepEqual(groups, [LABELS.addConditions]);
});

test('an OR goes between two conditions of the same or-group', () => {
    const card = document.createElement('div');
    widgets.appendConditions(card, [
        condition('Block 1000 damage', { alternative: true }),
        condition('Survive the battle', { alternative: true }),
    ], LABELS);
    const rows = card.children.map((node) => node.className);
    assert.deepEqual(rows, ['zanju-ct-cond', 'zanju-ct-or', 'zanju-ct-cond']);
    assert.equal(card.querySelector('.zanju-ct-or').textContent, LABELS.or);
});

test('three or-group conditions get an OR between each pair', () => {
    const card = document.createElement('div');
    widgets.appendConditions(card, [
        condition('One', { alternative: true }),
        condition('Two', { alternative: true }),
        condition('Three', { alternative: true }),
    ], LABELS);
    assert.equal(card.querySelectorAll('.zanju-ct-or').length, 2);
});

test('no OR appears between conditions that all have to be met', () => {
    const card = document.createElement('div');
    widgets.appendConditions(card, [condition('One'), condition('Two')], LABELS);
    assert.equal(card.querySelectorAll('.zanju-ct-or').length, 0);
});

test('no OR is placed against a neighbour outside the or-group', () => {
    const card = document.createElement('div');
    widgets.appendConditions(card, [
        condition('Required'),
        condition('Either this', { alternative: true }),
        condition('Or this', { alternative: true }),
    ], LABELS);
    const rows = card.children.map((node) => node.className);
    assert.deepEqual(rows, [
        'zanju-ct-cond', 'zanju-ct-cond', 'zanju-ct-or', 'zanju-ct-cond',
    ]);
});

test('the hover card says so when a running mission reports no conditions', () => {
    const card = document.createElement('div');
    widgets.renderCard(card, entry({ conditions: [] }), LABELS);
    assert.ok(card.textContent.includes(LABELS.noConditions));
});

test('the hover card of an idle campaign carries the state and nothing else', () => {
    const card = document.createElement('div');
    const idle = entry({ mission: null, missionId: '', operationTitle: '', state: 'nomatch' });
    widgets.renderCard(card, idle, LABELS);
    assert.ok(card.textContent.includes(LABELS.noMission));
    assert.equal(card.querySelectorAll('.zanju-ct-card-subtitle').length, 0);
    // With no subtitle to carry the rule, the title takes it, so the card keeps its shape.
    assert.ok(card.querySelector('.zanju-ct-card-title').className.includes('title-alone'));
});

test('badges are reconciled, so a campaign that stays keeps its element', () => {
    const root = document.createElement('div');
    const snapshot = { campaigns: [entry({}), entry({ branch: 'regular', numeral: 'I' })], labels: {} };
    assert.deepEqual(widgets.renderWidgets(root, snapshot), ['pm2', 'regular']);
    assert.equal(root.querySelectorAll('.zanju-ct-widget').length, 2);

    const kept = root.querySelector('[data-branch="pm2"]');
    widgets.renderWidgets(root, { campaigns: [entry({})], labels: {} });
    assert.equal(root.querySelectorAll('.zanju-ct-widget').length, 1);
    assert.equal(root.querySelector('[data-branch="pm2"]'), kept);
});

test('a position is clamped so a badge can never sit off-screen', () => {
    assert.deepEqual(widgets.clampToViewport(-50, -50), { x: 0, y: 0 });
    assert.deepEqual(widgets.clampToViewport(99999, 99999), { x: 1880, y: 1060 });
});

test('badges are laid out in a row from the origin, one margin apart', () => {
    const root = document.createElement('div');
    const branches = widgets.renderWidgets(root, {
        campaigns: [entry({ branch: 'regular', numeral: 'I' }), entry({})], labels: {},
    });
    widgets.applyLayout(root, branches, { x: 1030, y: 100 });

    const first = root.querySelector('[data-branch="regular"]');
    const second = root.querySelector('[data-branch="pm2"]');
    assert.equal(first.style.left, '1030px');
    assert.equal(first.style.top, '100px');
    // Widths are not measurable in this DOM, so the slot advances by the nominal width plus
    // one margin. The badges share a baseline either way.
    const step = parseInt(second.style.left, 10) - parseInt(first.style.left, 10);
    assert.equal(step - 60, widgets.BADGE_GAP_PX);
    assert.equal(second.style.top, '100px');
});

test('the row starts down and right of the anchor top-right corner', () => {
    clearBody();
    addAnchor({ left: 900, top: 100, right: 1020, bottom: 160, width: 120, height: 60 });
    assert.deepEqual(widgets.anchorOrigin(), {
        x: 1020 + widgets.ANCHOR_OFFSET_X_PX,
        y: 100 + widgets.ANCHOR_OFFSET_Y_PX,
    });
    clearBody();
});

test('the row falls back to the middle of the screen with no anchor on stage', () => {
    clearBody();
    assert.deepEqual(widgets.anchorOrigin(), { x: 960, y: 540 });
});

test('the layout falls back to the top-left corner with no origin to measure from', () => {
    const root = document.createElement('div');
    const branches = widgets.renderWidgets(root, { campaigns: [entry({})], labels: {} });
    widgets.applyLayout(root, branches, null);
    const widget = root.querySelector('[data-branch="pm2"]');
    assert.equal(widget.style.left, '0px');
    assert.equal(widget.style.top, '0px');
});

test('a detached anchor is not mistaken for one still on stage', () => {
    clearBody();
    const anchor = addAnchor({ left: 0, top: 0, right: 10, bottom: 10, width: 10, height: 10 });
    assert.equal(widgets.isAttached(anchor), true);
    body.removeChild(anchor);
    assert.equal(widgets.isAttached(anchor), false);
});

test('the anchor search can tell an element inside another from a stray one', () => {
    const root = document.createElement('div');
    const widget = root.appendChild(widgets.buildWidget(entry({})));
    assert.equal(widgets.isWithin(root, widget.querySelector('.zanju-ct-numeral')), true);
    assert.equal(widgets.isWithin(root, root), true);
    assert.equal(widgets.isWithin(root, document.createElement('div')), false);
});

test('an unparsable payload is reported as absent rather than thrown', () => {
    assert.equal(widgets.parseJson('{oops', 'snapshot'), null);
    assert.equal(widgets.parseJson('', 'snapshot'), null);
    assert.deepEqual(widgets.parseJson('{"a":1}', 'snapshot'), { a: 1 });
});
