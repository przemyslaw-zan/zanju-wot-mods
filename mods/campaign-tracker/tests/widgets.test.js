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

    // The banners bind hover handlers to report which one the pointer is on. Recorded rather
    // than dispatched: no test drives a pointer, and a missing method would fail the render.
    addEventListener(type, handler) {
        this.listeners = this.listeners || {};
        this.listeners[type] = handler;
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
    getElementById: (id) => body._walk([]).find((node) => node.id === id) || null,
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

// The three modules under test, merged into one namespace so every assertion below names the
// function rather than the file it happens to live in. The card moved to its own document when
// it moved to its own window band; the split is an implementation detail of where it draws.
const widgets = {
    ...await import('../res/gui/gameface/mods/zanju_campaigns/common.js'),
    ...await import('../res/gui/gameface/mods/zanju_campaigns/card.js'),
    ...await import('../res/gui/gameface/mods/zanju_campaigns/widgets.js'),
};

// The labels the Python side ships in every snapshot. A fixture, not a copy of `en.yml`: no
// test compares the two, and nothing here depends on the wording. Assert against `LABELS.x`
// rather than against the string, so a copy edit never breaks a test.
const LABELS = {
    noMission: 'No mission for this vehicle',
    paused: 'Mission on pause',
    primaryConditions: 'Primary condition',
    secondaryConditions: 'For completion with honors',
    or: 'or',
    lockedVehicles: 'Locked vehicles:',
    vehicleLocked: 'Vehicle locked',
    improving: 'Result Improvement',
    pawned: 'Retrieving an order',
    hintOpen: 'Click to open the mission',
    hintPause: 'Shift + Click to pause the mission',
    hintResume: 'Shift + Click to resume the mission',
    hintReset: 'Ctrl + Click to reset the mission',
};

function entry(overrides) {
    return Object.assign({
        branch: 'pm2',
        numeral: 'II',
        campaign: 'The Second Campaign',
        state: 'active',
        mission: 'Union-10. Raise the Flag!',
        missionId: 'UN-10',
        operationTitle: 'Operation Excalibur',
        canPause: false,
        canReset: false,
        conditions: [],
        attempts: [],
        paces: [],
    }, overrides);
}

test('the banner carries the short mission id, not the mission name', () => {
    assert.equal(widgets.faceId(entry({})), 'UN-10');
});

test('the banner keeps its shape when no mission matches', () => {
    const idle = entry({ mission: null, missionId: '', state: 'nomatch' });
    assert.equal(widgets.faceId(idle), widgets.IDLE_ID);
});

test('a banner with a mission to work on is not greyed, paused or not', () => {
    assert.equal(widgets.isActive(entry({})), true);
    // Paused counts: the banner flags that with an icon, and greying it too would file it with
    // the states that have no mission at all.
    assert.equal(widgets.isActive(entry({ state: 'paused' })), true);
    assert.equal(widgets.isActive(entry({ state: 'nomatch' })), false);
});

test('a mission running says nothing, and everything else says what it is', () => {
    assert.equal(widgets.stateNote(entry({ state: 'active' }), LABELS), '');
    assert.equal(widgets.stateNote(entry({ state: 'paused' }), LABELS), LABELS.paused);
    // Every way of having no mission reads the same on the card. Python tells them apart in
    // the log, because a player cannot act on the difference.
    assert.equal(widgets.stateNote(entry({ state: 'nomatch' }), LABELS), LABELS.noMission);
});

test('a counted condition shows numbers and a binary one does not', () => {
    assert.equal(widgets.conditionCount(condition('x', { counted: true, current: 2, goal: 5 })),
        '2 / 5');
    assert.equal(widgets.conditionCount(condition('x', { counted: false })), '');
});

test('a big number is shown as the client grouped it, not rebuilt from the digits', () => {
    // 15000 assistance damage is a real mission goal, and the separator belongs to the
    // language -- a space, a comma or a dot -- so the client is what decides it.
    assert.equal(widgets.conditionCount(condition('Assist', {
        counted: true, current: 2400, goal: 15000,
        currentText: '2 400', goalText: '15 000',
    })), '2 400 / 15 000');
});

test('only a banner with a mission behind it is clickable', () => {
    assert.equal(widgets.isClickable(entry({})), true);
    assert.equal(widgets.isClickable(entry({ mission: null })), false);
    assert.equal(widgets.isClickable(null), false);
});

test('the clickable banner is marked for the stylesheet and the click handler', () => {
    const widget = widgets.buildWidget(entry({}));
    widgets.renderWidget(widget, entry({}), LABELS);
    assert.ok(widget.className.includes('zanju-ct-widget-clickable'));
    assert.equal(widget._zanjuCtClickable, true);

    widgets.renderWidget(widget, entry({ mission: null, missionId: '' }), LABELS);
    assert.ok(!widget.className.includes('zanju-ct-widget-clickable'));
    assert.equal(widget._zanjuCtClickable, false);
});

test('the click handler finds the banner from any node inside it', () => {
    const widget = widgets.buildWidget(entry({}));
    const id = widget.querySelector('.zanju-ct-id');
    assert.equal(widgets.widgetFrom(id), widget);
    assert.equal(widgets.widgetFrom(widget), widget);
    assert.equal(widgets.widgetFrom(document.createElement('div')), null);
});

test('the banner tally shows the successes, the number needed and the battles left', () => {
    // Two successes of the three needed. One battle missed the condition and spent one of the
    // five anyway, so two battles are left rather than three.
    const tally = widgets.bannerTally(entry({
        attempts: [attempt({
            current: 2,
            goal: 3,
            battles: ['done', 'failed', 'done', 'pending', 'pending'],
        })],
    }));
    assert.deepEqual(tally, { kind: 'battles', current: 2, goal: 3, used: 3, allowed: 5 });
});

test('an unlimited objective says so, and carries no numbers beside it', () => {
    const row = widgets.buildAttempt(attempt({
        text: 'Complete the primary condition over any number of battles',
        type: null, current: null, goal: null, battles: [],
    }));
    assert.equal(row.querySelector('.zanju-ct-attempt-text').textContent,
        'Complete the primary condition over any number of battles');
    // Nothing to count against, so no counter is drawn rather than one reading "null / null".
    assert.equal(row.querySelectorAll('.zanju-ct-attempt-count').length, 0);
});

test('an unlimited primary reports its own total, not the secondary objective', () => {
    // The regression: an unlimited primary had no row of its own, so "the first unfinished
    // objective" answered with the secondary one and the banner counted the wrong half.
    const tally = widgets.bannerTally(entry({
        attempts: [
            attempt({ text: 'over any number of battles', type: null, current: null, goal: null }),
            attempt({ type: 'limited', battles: [], current: 1, goal: 4, main: false }),
        ],
        conditions: [
            condition('Assist', { counted: true, current: 2400, goal: 15000,
                currentText: '2 400', goalText: '15 000' }),
            condition('Secondary total', { counted: true, current: 2, goal: 8, main: false }),
        ],
    }));
    assert.deepEqual(tally, { kind: 'count', current: '2 400', goal: '15 000' });
});

test('an unlimited objective with nothing to count shows no tally', () => {
    // Its conditions are all binary, so there is no total to report.
    assert.equal(widgets.bannerTally(entry({
        attempts: [attempt({ type: null, current: null, goal: null })],
        conditions: [condition('Survive the battle')],
    })), null);
});

test('a mission with no battle limit has no banner tally', () => {
    assert.equal(widgets.bannerTally(entry({ attempts: [attempt({ battles: [] })] })), null);
    assert.equal(widgets.bannerTally(entry({ attempts: [] })), null);
    assert.equal(widgets.bannerTally(null), null);
});

test('the banner tally follows the primary objective', () => {
    const tally = widgets.bannerTally(entry({
        attempts: [
            attempt({ battles: ['done', 'pending'] }),
            attempt({ battles: ['failed', 'failed'], main: false, current: 0, goal: 2 }),
        ],
    }));
    assert.deepEqual(tally, { kind: 'battles', current: 1, goal: 3, used: 1, allowed: 2 });
});

test('the banner tally moves to the secondary objective once the primary is done', () => {
    const tally = widgets.bannerTally(entry({
        attempts: [
            attempt({ battles: ['done', 'done'], done: true }),
            attempt({ battles: ['failed', 'pending'], main: false, current: 0, goal: 2 }),
        ],
    }));
    assert.deepEqual(tally, { kind: 'battles', current: 0, goal: 2, used: 1, allowed: 2 });
});

test('the banner tally shows nothing once every objective is finished', () => {
    // Not reachable in game -- a finished mission is deselected, and only a selected one gets
    // a banner -- so there is nothing to fall back to.
    assert.equal(widgets.bannerTally(entry({
        attempts: [attempt({ battles: ['done', 'done'], done: true })],
    })), null);
});

test('the tally row is emptied and hidden when there is nothing to count', () => {
    const node = document.createElement('div');
    widgets.renderTally(node, { kind: 'battles', current: 2, goal: 3, used: 3, allowed: 5 });
    // The score and its target, and nothing else: the battles have a row of their own.
    assert.deepEqual(node.children.map((child) => child.textContent), ['2', '/', '3']);
    assert.equal(node.querySelector('.zanju-ct-tally-done').textContent, '2');
    assert.equal(node.querySelector('.zanju-ct-tally-target').textContent, '3');

    widgets.renderTally(node, null);
    assert.ok(node.className.includes('zanju-ct-tally-empty'));
    assert.equal(node.children.length, 0);
});

test('a running-total mission reports score, target and battles left', () => {
    // "Earn a total of 15 rewards" inside a run of 5 battles, 2 of them spent.
    const tally = widgets.bannerTally(entry({
        attempts: [attempt({ type: 'limited', battles: [], current: 2, goal: 5 })],
        conditions: [condition('Earn rewards', { counted: true, current: 6, goal: 15 })],
    }));
    assert.deepEqual(tally, { kind: 'score', current: '6', goal: '15', used: 2, allowed: 5, ahead: null });
});

test('a running-total mission with no counted condition reports nothing', () => {
    const tally = widgets.bannerTally(entry({
        attempts: [attempt({ type: 'limited', battles: [], current: 2, goal: 5 })],
        conditions: [condition('Survive the battle')],
    }));
    assert.equal(tally, null);
});

test('the running total is taken from the objective the banner is standing on', () => {
    const tally = widgets.bannerTally(entry({
        attempts: [
            attempt({ type: 'limited', battles: [], current: 1, goal: 4, done: true }),
            attempt({ type: 'limited', battles: [], current: 1, goal: 4, main: false }),
        ],
        conditions: [
            condition('Primary total', { counted: true, current: 9, goal: 10 }),
            condition('Secondary total', { counted: true, current: 2, goal: 8, main: false }),
        ],
    }));
    assert.deepEqual(tally, { kind: 'score', current: '2', goal: '8', used: 1, allowed: 4, ahead: null });
});

test('the score row shows the total and its target, and nothing more', () => {
    const node = document.createElement('div');
    widgets.renderTally(node, { kind: 'score', current: 6, goal: 15, used: 2, allowed: 5, ahead: null });
    assert.equal(node.querySelector('.zanju-ct-tally-score').textContent, '6');
    assert.equal(node.querySelector('.zanju-ct-tally-target').textContent, '15');
    assert.equal(node.children.length, 3);
});

test('both number rows are built to hang off their slash', () => {
    // The two halves each take half of what the slash leaves, so the slash lands at the same
    // place on both rows however long the numbers are. Centring the rows instead left the two
    // slashes visibly out of step.
    const score = document.createElement('div');
    widgets.renderTally(score, { kind: 'score', current: '10,000', goal: '20,000', used: 2, allowed: 5, ahead: null });
    const battles = document.createElement('div');
    widgets.renderBattles(battles, { kind: 'score', current: '10,000', goal: '20,000', used: 2, allowed: 5 });

    for (const row of [score, battles]) {
        const halves = row.children.map((child) => child.className);
        assert.ok(halves[0].includes('zanju-ct-half zanju-ct-half-left'), halves[0]);
        assert.ok(halves[2].includes('zanju-ct-half zanju-ct-half-right'), halves[2]);
        assert.equal(row.children[1].textContent, '/');
    }
    // The colour classes ride along with the halves rather than being replaced by them.
    assert.ok(score.children[0].className.includes('zanju-ct-tally-score'));
    assert.ok(battles.children[0].className.includes('zanju-ct-battles-used'));
});

test('the battles get a row of their own, spent out of allowed', () => {
    const node = document.createElement('div');
    widgets.renderBattles(node, { kind: 'score', current: 6, goal: 15, used: 2, allowed: 5 });
    assert.deepEqual(node.children.map((child) => child.textContent), ['2', '/', '5']);
    assert.equal(node.querySelector('.zanju-ct-battles-used').textContent, '2');
    assert.equal(node.querySelector('.zanju-ct-battles-total').textContent, '5');
});

test('a mission with no battle limit draws no battles row at all', () => {
    const node = document.createElement('div');
    widgets.renderBattles(node, { kind: 'count', current: 3, goal: 5 });
    assert.ok(node.className.includes('zanju-ct-battles-empty'));
    assert.equal(node.children.length, 0);

    widgets.renderBattles(node, null);
    assert.ok(node.className.includes('zanju-ct-battles-empty'));
});

test('the banner score is tinted from the pace Python worked out', () => {
    const behind = widgets.bannerTally(entry({
        attempts: [attempt({ type: 'limited', battles: [], current: 3, goal: 10 })],
        conditions: [condition('Modules', { counted: true, current: 7, goal: 25 })],
        paces: [pace({})],
    }));
    assert.equal(behind.ahead, false);

    const node = document.createElement('div');
    widgets.renderTally(node, behind);
    assert.ok(node.querySelector('.zanju-ct-tally-score').className.includes('tally-behind'));
});

test('the pace line reads as a percentage of the average the mission asks for', () => {
    const row = widgets.buildPace(pace({}));
    assert.equal(row.textContent, '80% of the target average per battle');
    assert.ok(row.className.includes('zanju-ct-pace-behind'));
});

test('being ahead colours the pace line the other way', () => {
    const row = widgets.buildPace(pace({ ahead: true, text: '120% of the target average per battle' }));
    assert.ok(row.className.includes('zanju-ct-pace-ahead'));
});

test('each objective gets its own pace line, under its own requirement', () => {
    const card = document.createElement('div');
    widgets.appendConditions(card,
        [condition('Required'), condition('Bonus', { main: false })],
        LABELS,
        [attempt({ type: 'limited' }), attempt({ type: 'limited', main: false })],
        [pace({}), pace({ main: false, text: '140% of the target average per battle' })]);
    const rows = card.children.map((node) => node.className);
    assert.deepEqual(rows, [
        'zanju-ct-group', 'zanju-ct-cond', 'zanju-ct-attempt', 'zanju-ct-pace zanju-ct-pace-behind',
        'zanju-ct-group zanju-ct-group-split', 'zanju-ct-cond', 'zanju-ct-attempt',
        'zanju-ct-pace zanju-ct-pace-behind',
    ]);
    assert.deepEqual(card.querySelectorAll('.zanju-ct-pace').map((row) => row.textContent),
        ['80% of the target average per battle', '140% of the target average per battle']);
});

test('an objective already at its total shows no pace line', () => {
    const card = document.createElement('div');
    widgets.appendConditions(card,
        [condition('Required'), condition('Bonus', { main: false })],
        LABELS,
        [attempt({ type: 'limited' }), attempt({ type: 'limited', main: false })],
        [pace({ main: false })]);
    assert.equal(card.querySelectorAll('.zanju-ct-pace').length, 1);
});

test('the push subscription follows the sub-view when the garage replaces it', () => {
    // The regression: the garage rebuilds the sub-view our model rides on whenever the player
    // picks another tank. The subscription kept naming the destroyed one, so every push after
    // the first tank change went nowhere and everything fell back to the slow poll.
    const subscribed = [];
    const saved = {
        engine: global.engine, viewEnv: global.viewEnv, subViews: global.window.subViews,
    };
    let model = { zanjuCtWidgets: { snapshot: '{}', visible: true, heldKeys: '' } };
    let handlers = 0;
    global.engine = { on: () => { handlers += 1; } };
    global.viewEnv = { addDataChangedCallback: (_kind, id) => subscribed.push(id) };
    global.window.subViews = { ids: () => [7], get: (id) => (id === 7 ? { model } : null) };

    try {
        widgets.findDataModel();
        assert.equal(widgets.bindModelPush(), true);
        assert.deepEqual(subscribed, [7]);
        // Nothing moved, so nothing is renewed — this runs on every tick.
        assert.equal(widgets.bindModelPush(), false);
        assert.deepEqual(subscribed, [7]);

        // The tank changes: the old view is gone and our model rides a new one.
        global.window.subViews = { ids: () => [9], get: (id) => (id === 9 ? { model } : null) };
        widgets.findDataModel();
        assert.equal(widgets.bindModelPush(), true);
        assert.deepEqual(subscribed, [7, 9]);
        // The engine-level handler belongs to the document and is registered only once, or the
        // tick would run once per registration.
        assert.equal(handlers, 1);
    } finally {
        global.engine = saved.engine;
        global.viewEnv = saved.viewEnv;
        global.window.subViews = saved.subViews;
    }
});

test('the key poll runs faster than the snapshot is ever rebuilt', () => {
    // The regression this guards: the highlight used to ride the main tick, which stands down
    // to a one-second backstop once the banners have settled, so a key took up to a second to
    // reach the card.
    assert.ok(widgets.KEY_POLL_INTERVAL_MS < widgets.POLL_INTERVAL_MS);
});

test('the key poll does nothing before the data model has been found', () => {
    // Going looking is the main tick's job; this one must not turn into a sub-view scan ten
    // times a second while the garage is still starting up.
    assert.doesNotThrow(() => widgets.keyTick());
});

test('the banner hangs to a point, drawn as an outline with a fill inside it', () => {
    const widget = widgets.buildWidget(entry({}));
    const tail = widget.querySelector('.zanju-ct-tail');
    assert.ok(tail, 'the point is part of every banner');
    // Two layers: clip-path takes an element's border with it, so the outline has to be a
    // filled shape with a smaller filled shape on top.
    assert.equal(tail.children.length, 1);
    assert.ok(tail.querySelector('.zanju-ct-tail-fill'));
});

test('a banner reports the hover once, however many snapshots reconcile it', () => {
    // The banners are reconciled rather than rebuilt, so a banner outlives every snapshot after
    // the first. Binding on each render would stack a second pair of handlers on the same node
    // and report every hover twice.
    const data = entry({});
    const widget = widgets.buildWidget(data);
    widgets.renderWidget(widget, data, LABELS);
    const first = widget.listeners.mouseenter;
    widgets.renderWidget(widget, data, LABELS);
    assert.equal(widget.listeners.mouseenter, first);
    assert.ok(typeof widget.listeners.mouseleave === 'function');
});

test('the banner is a face and a point, and carries no card', () => {
    const widget = widgets.buildWidget(entry({}));
    const order = widget.children.map((node) => node.className);
    assert.deepEqual(order, ['zanju-ct-face', 'zanju-ct-tail']);
    // The card draws in a window of the mod's own, so that it can sit above native windows.
    // A card inside this document could never do that, whatever z-index it carried.
    assert.equal(widget.querySelector('.zanju-ct-card'), null);
});

test('only the notes that cost the player battles are drawn as warnings', () => {
    assert.ok(widgets.noteClass({ warning: true }).includes('zanju-ct-note-warning'));
    assert.equal(widgets.noteClass({ warning: false }), 'zanju-ct-note');
    assert.equal(widgets.noteClass(null), 'zanju-ct-note');
});

test('the note that is good news gets a class of its own', () => {
    assert.ok(widgets.noteClass({ good: true }).includes('zanju-ct-note-good'));
    // A warning outranks it, so a note that somehow claimed both still reads as the warning.
    assert.ok(widgets.noteClass({ warning: true, good: true }).includes('zanju-ct-note-warning'));
});

test('a paused mission warns, and the states that are merely true do not', () => {
    const warns = (state) => widgets.cardNotes(entry({ state }), LABELS)[0].warning;
    assert.equal(warns('paused'), true);
    assert.equal(warns('nomatch'), false);
    // A running mission has nothing to say at all.
    assert.deepEqual(widgets.cardNotes(entry({ state: 'active' }), LABELS), []);
});

test('a restriction is drawn under the condition it gates, not beside it', () => {
    const row = widgets.buildCondition({
        text: 'Be the top player in the battle by number of vehicles destroyed.',
        restrictionLabel: 'Restriction!',
        restriction: 'Destroy 2 enemy vehicles.',
        counted: false,
    });
    // The condition keeps its own class on the outside, so "done" and "failed" still reach the
    // tick and the text through it.
    assert.equal(row.className, 'zanju-ct-cond');
    assert.deepEqual(row.children.map((node) => node.className),
        ['zanju-ct-cond-line', 'zanju-ct-cond-limit']);
    // The tick and the text stay on the first line, and the rule goes under both.
    assert.deepEqual(row.children[0].children.map((node) => node.className),
        ['zanju-ct-mark', 'zanju-ct-cond-text']);
    // One box per word, so the flex row wraps like a paragraph and a wrapped rule comes back
    // under the label rather than hanging in a column beside it.
    const limit = row.children[1];
    assert.deepEqual(limit.children.map((node) => node.className), [
        'zanju-ct-cond-limit-label',
        'zanju-ct-cond-limit-text', 'zanju-ct-cond-limit-text',
        'zanju-ct-cond-limit-text', 'zanju-ct-cond-limit-text',
    ]);
    // Split apart and read back, the line is the sentence it started as.
    assert.equal(limit.children.map((node) => node.textContent).join(' '),
        'Restriction! Destroy 2 enemy vehicles.');
});

test('a condition with no restriction is the line and nothing else', () => {
    const row = widgets.buildCondition({ text: 'Survive the battle.', counted: false });
    assert.deepEqual(row.children.map((node) => node.className), ['zanju-ct-cond-line']);
});

test('a restriction with no label of its own is drawn as the rule alone', () => {
    // The label comes from the client. Without it the line still has to carry the rule.
    const line = widgets.buildRestriction({ restrictionLabel: '', restriction: 'Deal 500 damage.' });
    assert.ok(line.children.every((node) => node.className === 'zanju-ct-cond-limit-text'));
    assert.equal(line.children.map((node) => node.textContent).join(' '), 'Deal 500 damage.');
});

test('every word of the label is highlighted, not only the first', () => {
    // "Restriction!" is one word in English and need not be in the language being read.
    const line = widgets.buildRestriction({ restrictionLabel: 'Restriction !', restriction: 'Go.' });
    assert.deepEqual(line.children.map((node) => node.className), [
        'zanju-ct-cond-limit-label', 'zanju-ct-cond-limit-label', 'zanju-ct-cond-limit-text',
    ]);
});

test('the word split drops the gaps rather than drawing empty boxes for them', () => {
    // Runs of spaces and a trailing one are what a translated string tends to arrive with.
    const line = document.createElement('div');
    widgets.appendWords(line, '  two   words ', 'w');
    assert.deepEqual(line.children.map((node) => node.textContent), ['two', 'words']);
    widgets.appendWords(line, null, 'w');
    assert.equal(line.children.length, 2);
});

test('the divider is dropped when there is nothing under it to divide', () => {
    // A card with no mission is the head and nothing else.
    const empty = document.createElement('div');
    widgets.renderCard(empty, entry({ state: 'nomatch', mission: null }), LABELS);
    assert.equal(empty.children.length, 1);
    assert.ok(empty.querySelector('.zanju-ct-card-head').className
        .includes('zanju-ct-card-head-alone'));

    // A card with a mission has conditions and hints under the head, so the rule earns its
    // place and stays.
    const full = document.createElement('div');
    widgets.renderCard(full, entry({}), LABELS);
    assert.ok(full.children.length > 1);
    assert.equal(full.querySelector('.zanju-ct-card-head').className, 'zanju-ct-card-head');
});

test('a warning sits with the mission it describes, above the divider', () => {
    const card = document.createElement('div');
    widgets.renderCard(card, entry({ state: 'paused' }), LABELS);
    const head = card.querySelector('.zanju-ct-card-head');
    // Title, mission name, then the warning -- all inside the block that carries the rule, so
    // the warning reads as part of the mission rather than as the first of its conditions.
    assert.deepEqual(head.children.map((node) => node.className), [
        'zanju-ct-card-title',
        'zanju-ct-card-subtitle',
        'zanju-ct-note zanju-ct-note-warning',
    ]);
    assert.equal(card.querySelector('.zanju-ct-note').parentNode, head);
});

test('a tank already spent on the mission warns alongside the conditions', () => {
    const notes = widgets.cardNotes(
        entry({ vehicles: { completed: 2, required: 5, locked: [], currentLocked: true } }),
        LABELS);
    assert.deepEqual(notes, [{ text: LABELS.vehicleLocked, warning: true }]);
});

test('a tank that can still be used on the mission says nothing', () => {
    assert.deepEqual(widgets.cardNotes(
        entry({ vehicles: { completed: 2, required: 5, locked: [], currentLocked: false } }),
        LABELS), []);
});

test('both warnings would be drawn if the game ever allowed both at once', () => {
    // It does not today -- pause belongs to campaign 2 and the lock to campaign 3, and the two
    // are never active together -- so this pins the card as not relying on that.
    const notes = widgets.cardNotes(entry({
        state: 'paused',
        vehicles: { completed: 2, required: 5, locked: [], currentLocked: true },
    }), LABELS);
    assert.deepEqual(notes.map((note) => note.text), [LABELS.paused, LABELS.vehicleLocked]);
    assert.ok(notes.every((note) => note.warning));
});

test('a warning note reaches the card carrying its warning class', () => {
    const card = document.createElement('div');
    widgets.renderCard(card, entry({ state: 'paused' }), LABELS);
    const note = card.querySelector('.zanju-ct-note');
    assert.ok(note.className.includes('zanju-ct-note-warning'));
    assert.equal(note.textContent, LABELS.paused);

    // The locked warning sits in the same place, in the same style.
    const locked = document.createElement('div');
    widgets.renderCard(locked,
        entry({ vehicles: { completed: 2, required: 5, locked: ['Foch B'], currentLocked: true } }),
        LABELS);
    const lockedNote = locked.querySelector('.zanju-ct-note');
    assert.ok(lockedNote.className.includes('zanju-ct-note-warning'));
    assert.equal(lockedNote.textContent, LABELS.vehicleLocked);
});

test('a mission past its primary objective says so, and not as a warning', () => {
    assert.deepEqual(widgets.cardNotes(entry({ stage: 'improving' }), LABELS),
        [{ text: LABELS.improving, good: true }]);
    // An order committed to buy the primary objective is a different fact, and says so.
    assert.deepEqual(widgets.cardNotes(entry({ stage: 'pawned' }), LABELS),
        [{ text: LABELS.pawned, good: true }]);
});

test('a stage the widget does not know is dropped rather than looked up', () => {
    // The value is a key into the labels, so an unknown one must not reach that lookup: every
    // other key in there would render as a note that makes no sense on this card.
    assert.equal(widgets.stageNote(entry({ stage: 'hintOpen' }), LABELS), null);
    assert.equal(widgets.stageNote(entry({ stage: '' }), LABELS), null);
    assert.equal(widgets.stageNote(null, LABELS), null);
});

test('the stage note yields to anything that costs the player battles', () => {
    // Nothing played counts while the mission is paused, so what the battles would buy is not
    // worth a line.
    assert.deepEqual(
        widgets.cardNotes(entry({ state: 'paused', stage: 'improving' }), LABELS)
            .map((note) => note.text),
        [LABELS.paused]);
    // Same for a tank already spent on the mission, and the same for the other stage.
    assert.deepEqual(
        widgets.cardNotes(entry({
            stage: 'pawned',
            vehicles: { completed: 2, required: 5, locked: [], currentLocked: true },
        }), LABELS).map((note) => note.text),
        [LABELS.vehicleLocked]);
});

test('the stage note reaches the card in green, above the divider', () => {
    const card = document.createElement('div');
    widgets.renderCard(card, entry({ stage: 'improving' }), LABELS);
    const head = card.querySelector('.zanju-ct-card-head');
    assert.deepEqual(head.children.map((node) => node.className), [
        'zanju-ct-card-title',
        'zanju-ct-card-subtitle',
        'zanju-ct-note zanju-ct-note-good',
    ]);
    assert.equal(card.querySelector('.zanju-ct-note').textContent, LABELS.improving);
});

test('a paused mission flags itself on the banner face', () => {
    assert.deepEqual(widgets.bannerFlags(entry({ state: 'paused' })), ['paused']);
});

test('a tank already spent on the mission is flagged as locked', () => {
    const locked = entry({ vehicles: { completed: 2, required: 5, locked: ['T-54'], currentLocked: true } });
    assert.deepEqual(widgets.bannerFlags(locked), ['locked']);
    // The same mission in a tank that has not been spent on it flags nothing.
    const free = entry({ vehicles: { completed: 2, required: 5, locked: ['T-54'], currentLocked: false } });
    assert.deepEqual(widgets.bannerFlags(free), []);
});

test('both states are flagged when both are true', () => {
    const both = entry({
        state: 'paused',
        vehicles: { completed: 2, required: 5, locked: [], currentLocked: true },
    });
    assert.deepEqual(widgets.bannerFlags(both), ['paused', 'locked']);
});

test('each stage carries its own icon, named by the stage itself', () => {
    assert.deepEqual(widgets.bannerFlags(entry({ stage: 'improving' })), ['improving']);
    assert.deepEqual(widgets.bannerFlags(entry({ stage: 'pawned' })), ['pawned']);
    // A stage the widget does not know draws nothing, rather than a missing image.
    assert.deepEqual(widgets.bannerFlags(entry({ stage: 'whatever' })), []);
});

test('the stage icon is dropped whenever a warning icon is drawn', () => {
    assert.deepEqual(
        widgets.bannerFlags(entry({ state: 'paused', stage: 'improving' })), ['paused']);
    assert.deepEqual(widgets.bannerFlags(entry({
        stage: 'pawned',
        vehicles: { completed: 2, required: 5, locked: [], currentLocked: true },
    })), ['locked']);
    // And it never joins them as a third icon, which the banner has no width for.
    assert.deepEqual(widgets.bannerFlags(entry({
        state: 'paused',
        stage: 'improving',
        vehicles: { completed: 2, required: 5, locked: [], currentLocked: true },
    })), ['paused', 'locked']);
});

test('a banner with no mission flags nothing, whatever its state says', () => {
    // A grey banner is already saying it has nothing running; a pause icon on it would be noise.
    assert.deepEqual(widgets.bannerFlags(entry({ state: 'paused', mission: null })), []);
    assert.deepEqual(widgets.bannerFlags(entry({ stage: 'improving', mission: null })), []);
    assert.deepEqual(widgets.bannerFlags(entry({})), []);
    assert.deepEqual(widgets.bannerFlags(null), []);
});

test('the flag row is emptied and hidden when there is nothing to flag', () => {
    const node = document.createElement('div');
    widgets.renderFlags(node, ['paused', 'locked']);
    assert.equal(node.querySelectorAll('.zanju-ct-flag').length, 2);
    assert.ok(node.querySelector('.zanju-ct-flag-paused'));
    assert.ok(node.querySelector('.zanju-ct-flag-locked'));

    widgets.renderFlags(node, []);
    assert.ok(node.className.includes('zanju-ct-flags-empty'));
    assert.equal(node.children.length, 0);
});

test('the banner grows a fourth row for a paused mission', () => {
    const data = entry({ state: 'paused' });
    const widget = widgets.buildWidget(data);
    widgets.renderWidget(widget, data, LABELS);
    const flags = widget.querySelector('.zanju-ct-flags');
    assert.ok(!flags.className.includes('flags-empty'));
    assert.equal(flags.children.length, 1);
});

test('a banner with a mission running keeps its fourth row out of the way', () => {
    const data = entry({});
    const widget = widgets.buildWidget(data);
    widgets.renderWidget(widget, data, LABELS);
    assert.ok(widget.querySelector('.zanju-ct-flags').className.includes('flags-empty'));
});

test('a banner with no pause or reset offers the plain click alone', () => {
    const block = widgets.buildHints(entry({}), LABELS);
    assert.deepEqual(block.children.map((row) => row.textContent), [LABELS.hintOpen]);
});

test('a mission that accepts both actions lists all three lines', () => {
    const block = widgets.buildHints(entry({ canPause: true, canReset: true }), LABELS);
    assert.deepEqual(block.children.map((row) => row.textContent),
        [LABELS.hintOpen, LABELS.hintPause, LABELS.hintReset]);
});

test('a paused mission offers the way back out on the same key', () => {
    const block = widgets.buildHints(entry({ canPause: true, state: 'paused' }), LABELS);
    assert.equal(block.children[1].textContent, LABELS.hintResume);
});

test('a mission with nothing to throw away lists no reset', () => {
    const block = widgets.buildHints(entry({ canPause: true, canReset: false }), LABELS);
    assert.deepEqual(block.children.map((row) => row.textContent),
        [LABELS.hintOpen, LABELS.hintPause]);
});

test('the keys held decide which action a click asks for', () => {
    const both = entry({ canPause: true, canReset: true });
    assert.equal(widgets.actionFor({ shift: false, ctrl: false }, both), 'open');
    assert.equal(widgets.actionFor({ shift: true, ctrl: false }, both), 'pause');
    assert.equal(widgets.actionFor({ shift: false, ctrl: true }, both), 'reset');
});

test('holding both keys asks for nothing rather than falling through to reset', () => {
    const both = entry({ canPause: true, canReset: true });
    assert.equal(widgets.actionFor({ shift: true, ctrl: true }, both), null);
});

test('a key the mission does not accept asks for nothing, not for the plain click', () => {
    const plain = entry({});
    assert.equal(widgets.actionFor({ shift: true, ctrl: false }, plain), null);
    assert.equal(widgets.actionFor({ shift: false, ctrl: true }, plain), null);
    // The unmodified click still opens it.
    assert.equal(widgets.actionFor({ shift: false, ctrl: false }, plain), 'open');
});

test('a click reads the keys off its own event', () => {
    assert.deepEqual(widgets.keysOf({ shiftKey: true, ctrlKey: false }),
        { shift: true, ctrl: false });
    // A click carrying neither flag, and no event at all, both read as nothing held.
    assert.deepEqual(widgets.keysOf({}), { shift: false, ctrl: false });
    assert.deepEqual(widgets.keysOf(null), { shift: false, ctrl: false });
});

test('the card reads the keys off what Python pushed', () => {
    assert.deepEqual(widgets.parseHeldKeys('shift'), { shift: true, ctrl: false });
    assert.deepEqual(widgets.parseHeldKeys('ctrl'), { shift: false, ctrl: true });
    assert.deepEqual(widgets.parseHeldKeys('shift ctrl'), { shift: true, ctrl: true });
    // Nothing held, and a model that has not answered yet, both read as nothing held.
    assert.deepEqual(widgets.parseHeldKeys(''), { shift: false, ctrl: false });
    assert.deepEqual(widgets.parseHeldKeys(undefined), { shift: false, ctrl: false });
});

test('the hint line for the keys held is the lit one', () => {
    // Lighting the hints belongs to the card document now: it is the document that draws them,
    // and Python pushes the held keys to it. The entry is passed in rather than read off a
    // wrapper element, because the card is the whole document and has no banner above it.
    const data = entry({ canPause: true, canReset: true });
    const card = new FakeNode('div');
    widgets.renderCard(card, data, LABELS);

    const lit = () => card.querySelectorAll('.zanju-ct-hint')
        .filter((row) => row.className.includes('zanju-ct-hint-active'))
        .map((row) => row.textContent);

    widgets.applyHints(card, { shift: false, ctrl: false }, data);
    assert.deepEqual(lit(), [LABELS.hintOpen]);

    widgets.applyHints(card, { shift: true, ctrl: false }, data);
    assert.deepEqual(lit(), [LABELS.hintPause]);

    widgets.applyHints(card, { shift: false, ctrl: true }, data);
    assert.deepEqual(lit(), [LABELS.hintReset]);

    // Both keys light nothing, which is what says the click will do nothing.
    widgets.applyHints(card, { shift: true, ctrl: true }, data);
    assert.deepEqual(lit(), []);
});

test('a card rebuilt under a held key keeps its highlight', () => {
    // renderCard clears the card, so the lit line has to be restored after every render. The
    // card is rebuilt whenever the pointer moves to another banner or the snapshot changes,
    // and losing the highlight to one would look like the key had been let go.
    const data = entry({ canPause: true });
    const card = new FakeNode('div');
    widgets.renderCard(card, data, LABELS);
    widgets.applyHints(card, { shift: true, ctrl: false }, data);
    const rows = card.querySelectorAll('.zanju-ct-hint');
    assert.ok(!rows[0].className.includes('hint-active'));
    assert.ok(rows[1].className.includes('hint-active'));
});

test('the banner takes the pace of the objective it is reporting', () => {
    const paces = [pace({ ahead: true }), pace({ ahead: false, main: false })];
    assert.equal(widgets.paceFor(paces, true), true);
    assert.equal(widgets.paceFor(paces, false), false);
    assert.equal(widgets.paceFor([], true), null);
    assert.equal(widgets.paceFor(null, true), null);
});

test('a run-of-battles mission reports the run so far and the run required', () => {
    const tally = widgets.bannerTally(entry({
        attempts: [attempt({ type: 'series', battles: [], current: 3, goal: 5 })],
    }));
    assert.deepEqual(tally, { kind: 'count', current: 3, goal: 5 });
});

test('a repeat-it-N-times mission reports the same way', () => {
    // The commonest requirement of all: 60 of the 120 missions that have one.
    const tally = widgets.bannerTally(entry({
        attempts: [attempt({ type: 'counter', battles: [], current: 2, goal: 4 })],
    }));
    assert.deepEqual(tally, { kind: 'count', current: 2, goal: 4 });
});

test('the count row puts what is in hand in green, against its target', () => {
    const node = document.createElement('div');
    widgets.renderTally(node, { kind: 'count', current: 3, goal: 5 });
    assert.equal(node.querySelector('.zanju-ct-tally-done').textContent, '3');
    assert.equal(node.querySelector('.zanju-ct-tally-target').textContent, '5');
    assert.equal(node.children.length, 3);
});

test('a requirement of some other shape gets no banner row', () => {
    const tally = widgets.bannerTally(entry({
        attempts: [attempt({ type: 'simple', battles: [] })],
        conditions: [condition('Earn rewards', { counted: true, current: 1, goal: 5 })],
    }));
    assert.equal(tally, null);
});

test('a requirement carried only by the secondary objective still reaches the banner', () => {
    // 42 missions put the requirement on the secondary objective alone.
    const tally = widgets.bannerTally(entry({
        attempts: [attempt({ type: 'counter', battles: [], current: 1, goal: 3, main: false })],
    }));
    assert.deepEqual(tally, { kind: 'count', current: 1, goal: 3 });
});

test('an idle widget is marked so the stylesheet can grey it', () => {
    const widget = widgets.buildWidget(entry({}));
    widgets.renderWidget(widget, entry({ mission: null, missionId: '', state: 'nomatch' }), LABELS);
    assert.ok(widget.className.includes('zanju-ct-widget-idle'));
    widgets.renderWidget(widget, entry({}), LABELS);
    assert.ok(!widget.className.includes('zanju-ct-widget-idle'));
});

test('the banner stacks the campaign numeral over the mission id', () => {
    const widget = widgets.buildWidget(entry({}));
    widgets.renderWidget(widget, entry({}), LABELS);
    assert.equal(widget.querySelector('.zanju-ct-numeral').textContent, 'II');
    assert.equal(widget.querySelector('.zanju-ct-id').textContent, 'UN-10');
    // No battle limit on this mission, so the third row stays out of the way.
    assert.ok(widget.querySelector('.zanju-ct-tally').className.includes('tally-empty'));
});

test('the banner grows a score row and a battles row for a mission with a limit', () => {
    const widget = widgets.buildWidget(entry({}));
    widgets.renderWidget(widget, entry({
        attempts: [attempt({ battles: ['done', 'failed', 'pending'] })],
    }), LABELS);
    const tally = widget.querySelector('.zanju-ct-tally');
    assert.ok(!tally.className.includes('tally-empty'));
    // The score alone. Two battles of the three allowed are spent, and they read below it.
    assert.equal(tally.textContent, '1/3');
    const battles = widget.querySelector('.zanju-ct-battles');
    assert.ok(!battles.className.includes('battles-empty'));
    assert.equal(battles.textContent, '2/3');
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
    // The line the vehicle falls in is collected for the banner id, never shown on the card.
    assert.ok(!card.textContent.includes('Alliance'));
});

test('the card title falls back to the campaign when there is no operation', () => {
    assert.equal(widgets.cardTitle(entry({ operationTitle: '' })), 'The Second Campaign');
});

test('the hover card splits primary conditions from secondary ones', () => {
    const card = document.createElement('div');
    widgets.renderCard(card, entry({
        conditions: [
            condition('Destroy 3 vehicles', { counted: true, current: 1, goal: 3 }),
            condition('Survive the battle', { done: true, main: false }),
        ],
    }), LABELS);
    const groups = card.querySelectorAll('.zanju-ct-group').map((node) => node.textContent);
    assert.deepEqual(groups, [LABELS.primaryConditions, LABELS.secondaryConditions]);
    assert.equal(card.querySelectorAll('.zanju-ct-cond-done').length, 1);
});

test('the main heading is dropped when there are no additional conditions', () => {
    const card = document.createElement('div');
    widgets.appendConditions(card, [condition('One'), condition('Two')], LABELS);
    assert.equal(card.querySelectorAll('.zanju-ct-group').length, 0);
    assert.equal(card.querySelectorAll('.zanju-ct-cond').length, 2);
});

test('the secondary heading is kept even when it is the only group', () => {
    const card = document.createElement('div');
    widgets.appendConditions(card, [condition('Bonus', { main: false })], LABELS);
    const groups = card.querySelectorAll('.zanju-ct-group').map((node) => node.textContent);
    assert.deepEqual(groups, [LABELS.secondaryConditions]);
});

test('the dividing rule is only drawn when a primary group sits above', () => {
    const both = document.createElement('div');
    widgets.appendConditions(both,
        [condition('Required'), condition('Bonus', { main: false })], LABELS);
    assert.equal(both.querySelectorAll('.zanju-ct-group-split').length, 1);

    const alone = document.createElement('div');
    widgets.appendConditions(alone, [condition('Bonus', { main: false })], LABELS);
    assert.equal(alone.querySelectorAll('.zanju-ct-group-split').length, 0);
});

function condition(text, overrides) {
    const row = Object.assign({
        text, counted: false, current: 0, goal: 1,
        done: false, failed: false, main: true, alternative: false,
    }, overrides);
    // Python sends both: the numbers, which the pace maths needs, and the text the card
    // renders, which the client has already grouped for the player's language. Defaulted to
    // the plain number here so only the tests that care about grouping have to say so.
    if (row.currentText === undefined) { row.currentText = String(row.current); }
    if (row.goalText === undefined) { row.goalText = String(row.goal); }
    return row;
}

function pace(overrides) {
    return Object.assign({
        text: '80% of the target average per battle',
        ahead: false,
        main: true,
    }, overrides);
}

function attempt(overrides) {
    return Object.assign({
        text: 'Complete the primary condition in 3 battles out of 5',
        type: 'biathlon',
        current: 1, goal: 3, battles: [], done: false, failed: false, main: true,
    }, overrides);
}

test('an attempt row shows the requirement and how far along it is', () => {
    const row = widgets.buildAttempt(attempt({}));
    assert.equal(row.querySelector('.zanju-ct-attempt-text').textContent,
        'Complete the primary condition in 3 battles out of 5');
    assert.equal(row.querySelector('.zanju-ct-attempt-count').textContent, '1 / 3');
});

test('a battle-capped attempt draws one mark per allowed battle', () => {
    const row = widgets.buildAttempt(attempt({
        battles: ['done', 'failed', 'pending', 'pending', 'pending'],
    }));
    const pips = row.querySelectorAll('.zanju-ct-pip').map((node) => node.className);
    assert.equal(pips.length, 5);
    assert.ok(pips[0].includes('zanju-ct-pip-done'));
    assert.ok(pips[1].includes('zanju-ct-pip-failed'));
    assert.ok(pips[2].includes('zanju-ct-pip-pending'));
});

test('an attempt with no battle cap draws no marks', () => {
    const row = widgets.buildAttempt(attempt({ battles: [] }));
    assert.equal(row.querySelectorAll('.zanju-ct-pip').length, 0);
});

test('a finished attempt is marked so the stylesheet can colour it', () => {
    assert.ok(widgets.buildAttempt(attempt({ done: true })).className.includes('attempt-done'));
    assert.ok(widgets.buildAttempt(attempt({ failed: true })).className.includes('attempt-failed'));
});

test('each group gets its own attempt row, below its conditions', () => {
    const card = document.createElement('div');
    widgets.appendConditions(card,
        [condition('Destroy 3 vehicles'), condition('Bonus', { main: false })],
        LABELS,
        [attempt({ text: 'main rule' }), attempt({ text: 'add rule', main: false })]);
    const rows = card.children.map((node) => node.className);
    assert.deepEqual(rows, [
        'zanju-ct-group', 'zanju-ct-cond', 'zanju-ct-attempt',
        'zanju-ct-group zanju-ct-group-split', 'zanju-ct-cond', 'zanju-ct-attempt',
    ]);
    const texts = card.querySelectorAll('.zanju-ct-attempt-text').map((n) => n.textContent);
    assert.deepEqual(texts, ['main rule', 'add rule']);
});

test('a mission with no attempt requirement gets no attempt row', () => {
    const card = document.createElement('div');
    widgets.appendConditions(card, [condition('Destroy 3 vehicles')], LABELS, []);
    assert.equal(card.querySelectorAll('.zanju-ct-attempt').length, 0);
});

function vehicles(overrides) {
    return Object.assign({
        text: 'Fulfill the condition in 5 different vehicles',
        completed: 2, required: 5, locked: ['T-62A', 'Object 140'],
    }, overrides);
}

test('the vehicle requirement shows a counter and the locked vehicles', () => {
    const block = widgets.buildVehicles(vehicles({}), LABELS);
    assert.equal(block.querySelector('.zanju-ct-attempt-text').textContent,
        'Fulfill the condition in 5 different vehicles');
    assert.equal(block.querySelector('.zanju-ct-attempt-count').textContent, '2 / 5');
    assert.equal(block.querySelector('.zanju-ct-locked-label').textContent, LABELS.lockedVehicles);
    // One row per tank, each with a lock of its own, rather than one comma-separated line.
    const rows = block.querySelectorAll('.zanju-ct-locked-row');
    assert.deepEqual(rows.map((row) => row.querySelector('.zanju-ct-locked-name').textContent),
        ['T-62A', 'Object 140']);
    assert.equal(rows.filter((row) => row.querySelector('.zanju-ct-locked-icon')).length, 2);
});

test('no vehicle is listed before one has been spent', () => {
    const block = widgets.buildVehicles(vehicles({ completed: 0, locked: [] }), LABELS);
    assert.equal(block.querySelector('.zanju-ct-attempt-count').textContent, '0 / 5');
    assert.equal(block.querySelectorAll('.zanju-ct-locked-row').length, 0);
    assert.equal(block.querySelectorAll('.zanju-ct-locked-label').length, 0);
});

test('the card carries the vehicle requirement only when the mission has one', () => {
    const withReq = document.createElement('div');
    widgets.renderCard(withReq, entry({ vehicles: vehicles({}) }), LABELS);
    assert.equal(withReq.querySelectorAll('.zanju-ct-vehicles').length, 1);

    const without = document.createElement('div');
    widgets.renderCard(without, entry({ vehicles: null }), LABELS);
    assert.equal(without.querySelectorAll('.zanju-ct-vehicles').length, 0);
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

test('a one-battle objective carries no line about how long it has', () => {
    // Python hands over the row with no text: the row is what tells the banner which objective
    // it counts, but a one-battle mission has no battle budget to describe.
    const card = document.createElement('div');
    const one = { text: '', type: null, current: null, goal: null, battles: [], main: true };
    widgets.appendConditions(card, [
        { text: 'Destroy 3 enemy vehicles.', counted: true, currentText: '0', goalText: '3', main: true },
    ], LABELS, [one], []);
    assert.deepEqual(card.children.map((node) => node.className), ['zanju-ct-cond']);
});

test('an objective with no battle limit keeps the line the client gives it', () => {
    const card = document.createElement('div');
    const unlimited = {
        text: 'Complete the primary condition over any number of battles',
        type: null, current: null, goal: null, battles: [], main: true,
    };
    widgets.appendConditions(card, [
        { text: 'Destroy 3 enemy vehicles.', counted: true, currentText: '0', goalText: '3', main: true },
    ], LABELS, [unlimited], []);
    assert.deepEqual(card.children.map((node) => node.className),
        ['zanju-ct-cond', 'zanju-ct-attempt']);
});

test('a mission whose conditions could not be read still builds a card', () => {
    // Only an already-logged failure empties the list, so the card drops the conditions and
    // keeps everything that does not depend on them.
    const card = document.createElement('div');
    widgets.renderCard(card, entry({ conditions: [] }), LABELS);
    assert.deepEqual(card.children.map((node) => node.className),
        ['zanju-ct-card-head', 'zanju-ct-hints']);
});

test('the hover card of an idle campaign carries the state and nothing else', () => {
    const card = document.createElement('div');
    const idle = entry({ mission: null, missionId: '', operationTitle: '', state: 'nomatch' });
    widgets.renderCard(card, idle, LABELS);
    assert.ok(card.textContent.includes(LABELS.noMission));
    assert.equal(card.querySelectorAll('.zanju-ct-card-subtitle').length, 0);
    // The rule belongs to the head block, so a card with no subtitle keeps the same shape.
    assert.ok(card.querySelector('.zanju-ct-card-head'));
});

test('banners are reconciled, so a campaign that stays keeps its element', () => {
    const root = document.createElement('div');
    const snapshot = { campaigns: [entry({}), entry({ branch: 'regular', numeral: 'I' })], labels: {} };
    assert.deepEqual(widgets.renderWidgets(root, snapshot), ['pm2', 'regular']);
    assert.equal(root.querySelectorAll('.zanju-ct-widget').length, 2);

    const kept = root.querySelector('[data-branch="pm2"]');
    widgets.renderWidgets(root, { campaigns: [entry({})], labels: {} });
    assert.equal(root.querySelectorAll('.zanju-ct-widget').length, 1);
    assert.equal(root.querySelector('[data-branch="pm2"]'), kept);
});

test('a position is clamped so a banner can never sit off-screen', () => {
    assert.deepEqual(widgets.clampToViewport(-50, -50), { x: 0, y: 0 });
    assert.deepEqual(widgets.clampToViewport(99999, 99999), { x: 1880, y: 1060 });
});

test('banners are laid out in a row from the origin, one margin apart', () => {
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
    // one margin. The banners share a baseline either way.
    const step = parseInt(second.style.left, 10) - parseInt(first.style.left, 10);
    assert.equal(step - 60, widgets.BANNER_GAP_PX);
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

test('there is no origin at all while the anchor is off stage', () => {
    // No fallback position: that is what keeps the banners hidden until the garage mounts the
    // block, rather than showing them somewhere else first and moving them across.
    clearBody();
    assert.equal(widgets.anchorOrigin(), null);
});

test('the poll stays fast until a push has arrived and the banners are placed', () => {
    const fast = widgets.UNPUSHED_POLL_INTERVAL_MS;
    const slow = widgets.POLL_INTERVAL_MS;
    assert.equal(widgets.pollRateFor(false, false), fast);
    // The regression: dropping to the backstop as soon as the push bound left the move onto
    // the anchor waiting a full second.
    assert.equal(widgets.pollRateFor(true, false), fast);
    // The second one: a subscription that never delivered still counted as "pushes are up",
    // which left a modifier key up to a second behind the card it was meant to light.
    assert.equal(widgets.pollRateFor(false, true), fast);
    assert.equal(widgets.pollRateFor(true, true), slow);
});

test('a row laid out on banners that cannot be measured yet asks to be laid out again', () => {
    const root = document.createElement('div');
    const widget = document.createElement('div');
    widget.setAttribute('data-branch', 'pm2');
    root.appendChild(widget);

    // No rect yet, which is what a banner appended this frame reports.
    assert.equal(widgets.applyLayout(root, ['pm2'], { x: 100, y: 50 }), false);
    // Placed anyway, so the banner is never left without a position.
    assert.equal(widget.style.left, '100px');

    widget._rect = { left: 0, top: 0, right: 84, bottom: 40, width: 84, height: 40 };
    assert.equal(widgets.applyLayout(root, ['pm2'], { x: 100, y: 50 }), true);
});

test('a provisional row is laid out again, even though the anchor has not moved', () => {
    // The regression the banner kept jumping from: the first layout ran before the banners could
    // be measured, spread the row on the nominal slot, then cached the origin as done. Nothing
    // moved it again until the next snapshot, which is where the jump came from.
    clearBody();
    addAnchor({ left: 800, top: 100, right: 1000, bottom: 160, width: 200, height: 60 });
    const root = document.createElement('div');
    document.body.appendChild(root);
    widgets.renderWidgets(root, {
        labels: {},
        campaigns: [entry({ branch: 'regular' }), entry({ branch: 'pm2' })],
    });

    // First pass: the banners have no rect, so the row stands on the nominal slot.
    widgets.updateLayout(root, ['regular', 'pm2']);
    const second = root.querySelector('[data-branch="pm2"]');
    const provisional = second.style.left;

    // The banners become measurable, and the anchor has not moved a pixel.
    for (const branch of ['regular', 'pm2']) {
        root.querySelector('[data-branch="' + branch + '"]')._rect =
            { left: 0, top: 0, right: 84, bottom: 40, width: 84, height: 40 };
    }
    widgets.updateLayout(root, ['regular', 'pm2']);
    assert.notEqual(second.style.left, provisional);

    // And now that it stands on real widths, it stays put.
    const settled = second.style.left;
    widgets.updateLayout(root, ['regular', 'pm2']);
    assert.equal(second.style.left, settled);
    clearBody();
});

test('the row spreads by the measured width once there is one', () => {
    const root = document.createElement('div');
    for (const branch of ['regular', 'pm2']) {
        const widget = document.createElement('div');
        widget.setAttribute('data-branch', branch);
        widget._rect = { left: 0, top: 0, right: 84, bottom: 40, width: 84, height: 40 };
        root.appendChild(widget);
    }
    widgets.applyLayout(root, ['regular', 'pm2'], { x: 100, y: 50 });
    assert.equal(root.querySelector('[data-branch="regular"]').style.left, '100px');
    assert.equal(root.querySelector('[data-branch="pm2"]').style.left,
        String(100 + 84 + widgets.BANNER_GAP_PX) + 'px');
});

test('the layout leaves the banners alone when there is no origin', () => {
    const root = document.createElement('div');
    const branches = widgets.renderWidgets(root, { campaigns: [entry({})], labels: {} });
    const widget = root.querySelector('[data-branch="pm2"]');
    widget.style.left = '500px';
    widgets.applyLayout(root, branches, null);
    assert.equal(widget.style.left, '500px');
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
