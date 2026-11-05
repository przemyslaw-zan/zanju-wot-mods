// Tests for the Crucible banner and card, run by `node --test`.
//
// The banner module auto-starts only when a Gameface view registry is present, so importing it
// here has no side effects. A minimal DOM stands in for the renderer: only the calls the banner,
// the card and the tray make are implemented.

import assert from 'node:assert/strict';
import test from 'node:test';

class FakeNode {
    constructor(tag) {
        this.tagName = tag;
        this.className = '';
        this.children = [];
        this.parentNode = null;
        this.style = {
            setProperty(name, value) {
                this[name] = value;
            },
        };
        this.attributes = {};
        this.id = '';
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

    addEventListener(type, handler) {
        this.listeners = this.listeners || {};
        this.listeners[type] = handler;
    }

    setAttribute(name, value) {
        this.attributes[name] = String(value);
    }

    getAttribute(name) {
        return Object.prototype.hasOwnProperty.call(this.attributes, name) ? this.attributes[name] : null;
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
        const attribute = selector.match(/^\[([a-z-]+)(\*?)(?:="(.*)")?\]$/);
        if (!attribute) {
            return false;
        }
        const [, name, operator, value] = attribute;
        const actual = name === 'class' ? this.className : this.getAttribute(name);
        if (actual === null || actual === undefined || actual === '') {
            return false;
        }
        if (value === undefined) {
            return true;
        }
        return operator === '*' ? String(actual).includes(value) : actual === value;
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

const banner = await import('../res/gui/gameface/mods/zanju_crucible/widgets.js');
const card = await import('../res/gui/gameface/mods/zanju_crucible/card.js');
const common = await import('../res/gui/gameface/mods/zanju_crucible/common.js');
const battle = await import('../res/gui/gameface/mods/zanju_crucible/battle.js');

function clearBody() {
    body.children.slice().forEach((child) => body.removeChild(child));
}

function addAnchor(rect) {
    const anchor = new FakeNode('div');
    anchor.className = 'VehicleInfoWidget_b24b193a';
    anchor._rect = rect;
    body.appendChild(anchor);
    return anchor;
}

// The labels the Python side ships in every snapshot. A fixture, not a copy of the client's
// strings: assert against `LABELS.x` rather than against the text.
const LABELS = {
    noActive: 'No active Crucible',
    mission: 'Mission {stage} of {total}',
    missionNumber: 'Mission {stage}',
    completions: 'Completions: {done} / {allowed}',
    available: 'Available',
    freeRestart: 'Free restart available',
    restartFor: 'Restart available for:',
    inBattle: 'Vehicles in battle:',
    inBattleWarning: 'The result of a battle that is still in progress completes or fails the current mission if a Crucible is active when the battle ends.',
    dayUnit: 'd',
    hourUnit: 'h',
    minuteUnit: 'm',
    secondUnit: 's',
    failed: 'Failed',
    hintOpen: 'Click to open the Crucible menu',
    header: 'CRUCIBLE',
    completed: 'Completed',
    or: 'OR',
    vehicleRestriction: 'Vehicle of Tier VI or higher required',
    hard: 'ACE',
    medium: 'ELITE',
    easy: 'FIGHTER',
};

function series(overrides) {
    return Object.assign({
        id: 57,
        name: 'Flash',
        difficulty: 'medium',
        state: 'inactive',
        stage: 0,
        total: 3,
        completed: 0,
        shields: 4,
        shieldsLimit: 4,
        wins: 0,
        allowedCompletions: 2,
        endTime: inSeconds(13 * 86400 + 5 * 3600 + 1800),
        expiringSoon: false,
        restartCurrency: 'gold',
        restartCost: 200,
        restartCostText: '200',
        freeRestarts: 0,
        availability: 'start',
        soonest: false,
    }, overrides);
}

// A server time this many seconds from now. The extra half hour in the callers keeps a test off
// the boundary of the second unit, where a slow run would round down.
function inSeconds(seconds) {
    return Math.floor(Date.now() / 1000) + seconds;
}

function snapshot(overrides) {
    return Object.assign({
        enabled: true, active: null, series: [series({})], labels: LABELS,
        soonestSet: { free: 1, paid: [] }, allCompleted: false,
        nearestEnd: inSeconds(5 * 86400 + 3 * 3600 + 1800), timeOffset: 0,
        vehicleFits: true, inBattle: [],
    }, overrides);
}

function activeSeries(overrides) {
    return series(Object.assign({
        state: 'active',
        stage: 2,
        completed: 1,
        shields: 3,
        mission: {
            questID: 'challenge:57:2',
            group: 'or',
            rows: [
                { title: 'Damage', text: 'Cause 3,500 HP of damage', icon: 'hurt_vehicles', live: true },
                { title: 'Top Player', text: 'Be among the top 5 players', icon: 'top', live: false },
            ],
        },
    }, overrides));
}

test('an active series shows its shields, its mission and its end', () => {
    const data = snapshot({ active: activeSeries({}) });
    const model = banner.bannerModel(data);
    assert.deepEqual(model, {
        idle: false, shields: 3, shieldsLimit: 4, value: '2/3', endTime: data.nearestEnd, inBattle: 0,
    });
});

test('a vehicle that cannot play greys the banner, with or without an active series', () => {
    assert.equal(banner.bannerModel(snapshot({ active: activeSeries({}), vehicleFits: false })).idle, true);
    assert.equal(banner.bannerModel(snapshot({ vehicleFits: false })).idle, true);
    assert.equal(banner.bannerModel(snapshot({ vehicleFits: null })).idle, false);
});

test('vehicles in battle show as crossed swords and a count', () => {
    const root = document.createElement('div');
    banner.renderWidgets(root, snapshot({ inBattle: ['IS-3A', 'LHMTV'] }));
    const battle = root.querySelector('.zanju-crt-battle');
    assert.equal(battle.className, 'zanju-crt-battle');
    assert.equal(root.querySelector('.zanju-crt-battle-count').textContent, '2');
    banner.renderWidgets(root, snapshot({}));
    assert.equal(battle.className.includes('zanju-crt-battle-empty'), true);
});

test('with no active series, the banner counts the series that end first and keeps its colour', () => {
    const data = snapshot({ soonestSet: { free: 2, paid: [] } });
    const model = banner.bannerModel(data);
    assert.deepEqual(model, {
        idle: false, shields: null, value: '', groups: [{ count: 2, currency: '' }], done: false,
        endTime: data.nearestEnd, inBattle: 0,
    });
});

test('the count reads free, then credits, then gold, and leaves a group of 0 out', () => {
    const paid = [{ currency: 'credits', count: 1 }, { currency: 'gold', count: 0 }];
    assert.deepEqual(banner.soonestGroups(snapshot({ soonestSet: { free: 2, paid: paid } })),
        [{ count: 2, currency: '' }, { count: 1, currency: 'credits' }]);
    assert.deepEqual(banner.soonestGroups(snapshot({ soonestSet: { free: 0, paid: [{ currency: 'gold', count: 3 }] } })),
        [{ count: 3, currency: 'gold' }]);
    assert.deepEqual(banner.soonestGroups(snapshot({ soonestSet: { free: 0, paid: [] } })), [{ count: 0, currency: '' }]);
});

test('the count draws its groups with slashes and the currency icons', () => {
    const node = document.createElement('div');
    banner.renderValue(node, { groups: [{ count: 2, currency: '' }, { count: 1, currency: 'credits' },
        { count: 1, currency: 'gold' }] });
    assert.deepEqual(node.children.map((child) => child.className), [
        'zanju-crt-value-count', 'zanju-crt-value-slash', 'zanju-crt-value-count', 'zanju-crt-value-currency',
        'zanju-crt-value-slash', 'zanju-crt-value-count', 'zanju-crt-value-currency',
    ]);
    assert.equal(node.children[3].style.backgroundImage,
        "url('R.images.gui.maps.icons.library.currency.credits_24x24')");
    // Three groups do not fit the width of a campaign banner at the normal size.
    assert.ok(parseInt(node.style.fontSize, 10) < 15);
});

test('one or two short groups keep the normal size', () => {
    assert.equal(banner.valueSize([{ count: 3, currency: '' }]), 15);
    assert.equal(banner.valueSize([{ count: 2, currency: '' }, { count: 1, currency: 'gold' }]), 15);
    assert.ok(banner.valueSize([{ count: 2, currency: '' }, { count: 1, currency: 'credits' },
        { count: 1, currency: 'gold' }]) >= 9);
});

test('with every series completed, a green check takes the place of the count and the time', () => {
    const root = document.createElement('div');
    const model = banner.bannerModel(snapshot({ allCompleted: true, nearestEnd: 0 }));
    assert.equal(model.done, true);
    assert.equal(model.endTime, 0);
    banner.renderWidgets(root, snapshot({ allCompleted: true, nearestEnd: 0 }));
    const value = root.querySelector('.zanju-crt-value');
    assert.deepEqual(value.children.map((child) => child.className), ['zanju-crt-done']);
    assert.equal(root.querySelector('.zanju-crt-time').className.includes('zanju-crt-time-empty'), true);
});

test('the banner counts down to the nearest end, in the two largest units', () => {
    const root = document.createElement('div');
    banner.renderWidgets(root, snapshot({}));
    assert.equal(root.querySelector('.zanju-crt-time').textContent, '5d 03h');
});

test('a banner with no end to count down to hides its time row', () => {
    const root = document.createElement('div');
    banner.renderWidgets(root, snapshot({ nearestEnd: 0 }));
    assert.equal(root.querySelector('.zanju-crt-time').className.includes('zanju-crt-time-empty'), true);
});

test('no Crucible on the server, or no series at all, means no banner', () => {
    assert.equal(banner.bannerModel(snapshot({ enabled: false })), null);
    assert.equal(banner.bannerModel(snapshot({ series: [] })), null);
    assert.equal(banner.bannerModel(null), null);
});

test('the banner is built once and removed when there is nothing to show', () => {
    const root = document.createElement('div');
    banner.renderWidgets(root, snapshot({ active: activeSeries({}) }));
    const widget = root.querySelector('.zanju-crt-widget');
    assert.ok(widget);
    banner.renderWidgets(root, snapshot({ active: activeSeries({}), vehicleFits: false }));
    assert.equal(root.querySelector('.zanju-crt-widget'), widget);
    assert.equal(widget.className.includes('zanju-crt-widget-idle'), true);
    banner.renderWidgets(root, snapshot({ enabled: false }));
    assert.equal(root.querySelector('.zanju-crt-widget'), null);
});

test('an active series puts its shields below the head as left out of all, red on the last one', () => {
    const root = document.createElement('div');
    banner.renderWidgets(root, snapshot({ active: activeSeries({ shields: 1 }) }));
    const shields = root.querySelector('.zanju-crt-shields');
    assert.equal(shields.className.includes('zanju-crt-shields-last'), true);
    assert.equal(root.querySelector('.zanju-crt-shields-count').textContent, '1/4');
    // The head holds the emblem alone.
    assert.equal(root.querySelector('.zanju-crt-head').children.length, 1);
    banner.renderWidgets(root, snapshot({}));
    assert.equal(shields.className.includes('zanju-crt-shields-empty'), true);
});

test('the emblem is the client shield, by its resource name', () => {
    const root = document.createElement('div');
    banner.renderWidgets(root, snapshot({}));
    assert.equal(root.querySelector('.zanju-crt-emblem').style.backgroundImage,
        "url('R.images.gui.maps.icons.userMissions.challenges.icons.shields.shield_32')");
});

test('the banner stands after a campaign-tracker row on the same side', () => {
    clearBody();
    addAnchor({ left: 900, top: 100, right: 1020, bottom: 160, width: 120, height: 60 });
    const list = document.createElement('div');
    list.id = 'zanju-banner-tray';
    const ct = document.createElement('i');
    ct.setAttribute('data-owner', 'zanju.campaigntracker');
    ct.setAttribute('data-rank', '10');
    ct.setAttribute('data-side', 'right');
    ct.setAttribute('data-width', '200');
    list.appendChild(ct);
    body.appendChild(list);
    const root = document.createElement('div');
    banner.renderWidgets(root, snapshot({ active: activeSeries({}) }));
    const widget = root.querySelector('.zanju-crt-widget');
    widget._rect = { left: 0, top: 0, right: 64, bottom: 60, width: 64, height: 60 };
    banner.updateLayout(root, 'right');
    assert.equal(widget.style.left, (1020 + 25 + 200 + 12) + 'px');
    const own = list.querySelector('[data-owner="zanju.crucibletracker"]');
    assert.equal(own.getAttribute('data-rank'), String(banner.TRAY_RANK));
    assert.equal(own.getAttribute('data-width'), '64');
    clearBody();
});

test('on the left side, the banner ends before the vehicle name', () => {
    clearBody();
    addAnchor({ left: 900, top: 100, right: 1020, bottom: 160, width: 120, height: 60 });
    const root = document.createElement('div');
    banner.renderWidgets(root, snapshot({ active: activeSeries({}) }));
    const widget = root.querySelector('.zanju-crt-widget');
    widget._rect = { left: 0, top: 0, right: 64, bottom: 60, width: 64, height: 60 };
    banner.updateLayout(root, 'left');
    assert.equal(widget.style.left, (900 - 25 - 64) + 'px');
    clearBody();
});

test('with no vehicle name on stage, the banner leaves the tray', () => {
    clearBody();
    const root = document.createElement('div');
    banner.renderWidgets(root, snapshot({ active: activeSeries({}) }));
    banner.updateLayout(root, 'right');
    const list = document.getElementById('zanju-banner-tray');
    assert.equal(list ? list.querySelector('[data-owner="zanju.crucibletracker"]') : null, null);
});

test('the time left follows the premium-time rules', () => {
    assert.equal(common.formatRemaining(5 * 86400 + 3 * 3600 + 59, LABELS), '5d 03h');
    assert.equal(common.formatRemaining(2 * 3600 + 11 * 60 + 5, LABELS), '2h 11m');
    assert.equal(common.formatRemaining(5 * 60 + 2, LABELS), '5m 02s');
    assert.equal(common.formatRemaining(45, LABELS), '45s');
    assert.equal(common.formatRemaining(-3, LABELS), '0s');
    assert.equal(common.formatRemaining(86400 + 59, LABELS), '1d 00h');
});

test('a condition icon takes the c_ prefix of a folder that starts with a digit', () => {
    assert.equal(common.conditionImage('hurt_vehicles'),
        'gui.maps.icons.userMissions.challenges.missionIcons.c_32.hurt_vehicles');
});

test('only a currency the client has an icon for gets one', () => {
    assert.equal(common.currencyImage('gold'), 'gui.maps.icons.library.currency.gold_24x24');
    assert.equal(common.currencyImage('credits'), 'gui.maps.icons.library.currency.credits_24x24');
    assert.equal(common.currencyImage('unknown'), '');
});

test('a template takes all three placeholder forms of the client', () => {
    assert.equal(common.fill('{{a}} / {b} %(c)s', { a: 1, b: 2, c: 'x' }), '1 / 2 x');
    assert.equal(common.fill(undefined, {}), '');
});

test('a series that can start says so in the regular white of the column', () => {
    const node = card.buildAvailability(series({}), LABELS);
    assert.equal(node.textContent, LABELS.available);
    assert.equal(node.className, 'zanju-crt-series-avail');
});

test('a free restart says so in the same white', () => {
    const node = card.buildAvailability(series({ availability: 'freeRestart' }), LABELS);
    assert.equal(node.textContent, LABELS.freeRestart);
    assert.equal(node.className, 'zanju-crt-series-avail');
});

test('a paid restart names its price, with the currency icon', () => {
    const node = card.buildAvailability(series({
        availability: 'paidRestart', restartCurrency: 'credits', restartCostText: '200,000',
    }), LABELS);
    assert.equal(node.textContent, LABELS.restartFor + '200,000');
    const price = node.querySelector('.zanju-crt-price');
    assert.equal(price.className.includes('zanju-crt-currency-credits'), true);
    assert.equal(price.querySelector('.zanju-crt-series-icon').style.backgroundImage,
        "url('R.images.gui.maps.icons.library.currency.credits_24x24')");
});

test('a completed series offers nothing', () => {
    assert.equal(card.buildAvailability(series({ availability: 'none' }), LABELS).textContent, '');
});

test('with an active series, the card shows that series alone: name, time, shields and missions', () => {
    const node = document.createElement('div');
    card.renderCard(node, snapshot({ active: activeSeries({}), series: [activeSeries({}), series({ id: 2 })] }));
    assert.equal(node.className, 'zanju-crt-card zanju-crt-card-focus');
    const top = node.querySelector('.zanju-crt-focus-top');
    assert.deepEqual(top.children.map((child) => child.textContent), ['Flash', '13d 05h']);
    assert.equal(node.querySelector('.zanju-crt-mission-title').textContent, 'Mission 2');
    assert.equal(node.querySelectorAll('.zanju-crt-cond').length, 2);
    assert.equal(node.querySelector('.zanju-crt-or').textContent, LABELS.or);
    // No category, and no list of the other series.
    assert.equal(node.textContent.includes(LABELS.medium), false);
    assert.equal(node.querySelector('.zanju-crt-list'), null);
    assert.equal(node.querySelector('.zanju-crt-hint').textContent, LABELS.hintOpen);
});

test('with no active series, the card takes the list mode again', () => {
    const node = document.createElement('div');
    card.renderCard(node, snapshot({ active: activeSeries({}) }));
    node.className += ' zanju-crt-card-shown';
    card.renderCard(node, snapshot({}));
    assert.equal(node.className, 'zanju-crt-card zanju-crt-card-shown');
    assert.equal(node.querySelectorAll('.zanju-crt-series').length, 1);
});

test('the active series shows one shield for each shield, the spent ones greyed, then the count', () => {
    const node = document.createElement('div');
    card.renderCard(node, snapshot({ active: activeSeries({ shields: 1 }) }));
    const shields = node.querySelectorAll('.zanju-crt-focus-shield');
    assert.deepEqual(shields.map((shield) => shield.className.includes('zanju-crt-focus-shield-spent')),
        [false, true, true, true]);
    assert.equal(shields[0].style.backgroundImage,
        "url('R.images.gui.maps.icons.userMissions.challenges.icons.shields.shield_s')");
    assert.equal(shields[3].style.backgroundImage,
        "url('R.images.gui.maps.icons.userMissions.challenges.icons.shields.loseShield_s')");
    assert.equal(node.querySelector('.zanju-crt-focus-shield-count').textContent, '1/4');
    assert.equal(node.querySelector('.zanju-crt-focus-shields').className.includes('last'), true);
});

test('every mission of the series is listed, the done ones marked completed', () => {
    const node = document.createElement('div');
    const missions = [
        { stage: 1, state: 'done', group: 'and', rows: [{ text: 'a' }] },
        { stage: 2, state: 'current', group: 'and', rows: [{ text: 'b' }] },
        { stage: 3, state: 'next', group: 'and', rows: [{ text: 'c' }] },
    ];
    card.renderCard(node, snapshot({ active: activeSeries({ missions: missions }) }));
    const list = node.querySelectorAll('.zanju-crt-mission');
    assert.deepEqual(list.map((mission) => mission.className.split(' ')[1]),
        ['zanju-crt-mission-done', 'zanju-crt-mission-current', 'zanju-crt-mission-next']);
    assert.deepEqual(list.map((mission) => mission.querySelector('.zanju-crt-cond-text').textContent), ['a', 'b', 'c']);
    assert.deepEqual(node.querySelectorAll('.zanju-crt-mission-completed').map((mark) => mark.textContent),
        [LABELS.completed]);
    // A rule between each two missions.
    assert.deepEqual(node.querySelector('.zanju-crt-missions').children.map((child) => child.className.split(' ')[0]),
        ['zanju-crt-mission', 'zanju-crt-mission-rule', 'zanju-crt-mission', 'zanju-crt-mission-rule',
            'zanju-crt-mission']);
});

test('a series row reads name, shields, completions, availability, then time', () => {
    const node = document.createElement('div');
    // Two shields lost in an earlier run: the list still shows the full set of the series.
    card.renderCard(node, snapshot({ series: [series({ shields: 2, shieldsLimit: 6, wins: 1, allowedCompletions: 2 })] }));
    const row = node.querySelector('.zanju-crt-series');
    assert.deepEqual(row.children.map((child) => child.className.split(' ')[0]), [
        'zanju-crt-series-name', 'zanju-crt-series-shields', 'zanju-crt-series-completions',
        'zanju-crt-series-avail', 'zanju-crt-series-time',
    ]);
    assert.equal(row.querySelector('.zanju-crt-series-shields').textContent, '6');
    assert.equal(row.querySelector('.zanju-crt-series-completions').textContent, 'Completions: 1 / 2');
    assert.equal(row.querySelector('.zanju-crt-series-completions').className, 'zanju-crt-series-completions');
    assert.equal(row.querySelector('.zanju-crt-series-time').textContent, '13d 05h');
});

test('a series completed as often as it allows reads green in its completions', () => {
    const node = document.createElement('div');
    card.renderCard(node, snapshot({ series: [series({ wins: 2, allowedCompletions: 2, availability: 'none' })] }));
    const completions = node.querySelector('.zanju-crt-series-completions');
    assert.equal(completions.textContent, 'Completions: 2 / 2');
    assert.equal(completions.className, 'zanju-crt-series-completions zanju-crt-series-complete');
});

test('the columns fit their widest cell, and the card fits the columns', () => {
    const node = document.createElement('div');
    card.renderCard(node, snapshot({ series: [series({ id: 1 }), series({ id: 2, availability: 'paidRestart' })] }));
    const rows = node.querySelectorAll('.zanju-crt-series');
    const sizes = [[60, 30, 100, 50, 40], [80, 28, 96, 150, 38]];
    rows.forEach((row, r) => {
        let left = 10;
        row.children.forEach((cell, c) => {
            cell._rect = { left: left, right: left + sizes[r][c], width: sizes[r][c] };
            left += sizes[r][c] + 16;
        });
        row._rect = { width: 620 };
    });
    node._rect = { width: 640 };
    const fitted = card.fitColumns(node);
    assert.deepEqual(fitted.widths, [80, 30, 100, 150, 40]);
    assert.equal(fitted.gap, 16);
    // The columns, four gaps, and the 20 pixels of padding and border around the list.
    assert.equal(node.style.width, (80 + 30 + 100 + 150 + 40 + 4 * 16 + 20) + 'px');
    // The availability column gets a floor and takes the spare width, so the time stays right.
    const avail = rows[0].querySelector('.zanju-crt-series-avail');
    assert.equal(avail.style.minWidth, '150px');
    assert.equal(avail.className.includes('zanju-crt-series-grow'), true);
    assert.equal(rows[0].querySelector('.zanju-crt-series-time').style.width, '40px');
    card.resetColumns(node);
    assert.equal(node.style.width, '');
    assert.equal(rows[1].querySelector('.zanju-crt-series-name').style.width, '');
    assert.equal(avail.style.minWidth, '');
    assert.equal(avail.className.includes('zanju-crt-series-grow'), false);
});

test('a card with no series list keeps its width', () => {
    const node = document.createElement('div');
    card.renderCard(node, snapshot({ series: [] }));
    assert.equal(card.fitColumns(node), null);
});

test('only the soonest countdown is highlighted', () => {
    const node = document.createElement('div');
    card.renderCard(node, snapshot({ series: [series({ id: 1, soonest: true }), series({ id: 2 })] }));
    const times = node.querySelectorAll('.zanju-crt-series-time');
    assert.equal(times[0].className.includes('zanju-crt-soonest'), true);
    assert.equal(times[1].className.includes('zanju-crt-soonest'), false);
});

test('a refresh rewrites every countdown from its own end', () => {
    const node = document.createElement('div');
    const data = snapshot({});
    card.renderCard(node, data);
    const time = node.querySelector('.zanju-crt-series-time');
    time._zanjuEnd = inSeconds(45);
    card.refreshTimes(node, data);
    assert.match(time.textContent, /^4[45]s$/);
});

test('a condition shows its text alone, whether or not the panel counts it', () => {
    const node = document.createElement('div');
    card.renderCard(node, snapshot({ active: activeSeries({}) }));
    assert.equal(node.querySelectorAll('.zanju-crt-cond').length, 2);
});

test('a choice of sets draws one or separator between the sets, not between their conditions', () => {
    const node = document.createElement('div');
    const active = activeSeries({});
    active.mission.rows = [{ text: 'a', set: 0 }, { text: 'b', set: 0 }, { text: 'c', set: 1 }, { text: 'd', set: 1 }];
    card.renderCard(node, snapshot({ active: active }));
    const block = node.querySelector('.zanju-crt-mission');
    assert.deepEqual(block.children.slice(1).map((child) => child.className === 'zanju-crt-or' ? 'OR' : child.textContent),
        ['a', 'b', 'OR', 'c', 'd']);
});

test('an and-group draws no or separator', () => {
    const node = document.createElement('div');
    const active = activeSeries({});
    active.mission.group = 'and';
    card.renderCard(node, snapshot({ active: active }));
    assert.equal(node.querySelector('.zanju-crt-or'), null);
});

test('the card warns when the vehicle cannot play, with or without an active series', () => {
    for (const data of [snapshot({ vehicleFits: false }), snapshot({ active: activeSeries({}), vehicleFits: false })]) {
        const node = document.createElement('div');
        card.renderCard(node, data);
        assert.equal(node.querySelector('.zanju-crt-note-warning').textContent, LABELS.vehicleRestriction);
    }
});

test('vehicles in battle bring a list of their names, headed by the warning', () => {
    const node = document.createElement('div');
    card.renderCard(node, snapshot({ inBattle: ['IS-3A', 'LHMTV'] }));
    // The warning belongs to the list, not to the warnings at the top of the card.
    assert.equal(node.querySelector('.zanju-crt-note-warning'), null);
    const block = node.querySelector('.zanju-crt-battles');
    assert.deepEqual(block.children.map((child) => child.className),
        ['zanju-crt-battles-warning', 'zanju-crt-battles-label', 'zanju-crt-battles-row', 'zanju-crt-battles-row']);
    assert.equal(block.children[0].textContent, LABELS.inBattleWarning);
    assert.equal(block.children[1].textContent, LABELS.inBattle);
    assert.deepEqual(node.querySelectorAll('.zanju-crt-battles-name').map((n) => n.textContent),
        ['IS-3A', 'LHMTV']);
    assert.equal(node.querySelectorAll('.zanju-crt-battles-icon').length, 2);
});

test('with an active series, the battle warning is the same', () => {
    const node = document.createElement('div');
    card.renderCard(node, snapshot({ active: activeSeries({}), inBattle: ['IS-3A'] }));
    assert.equal(node.querySelector('.zanju-crt-battles-warning').textContent, LABELS.inBattleWarning);
    assert.equal(node.querySelectorAll('.zanju-crt-battles-name').length, 1);
});

test('the warning about the vehicle in the garage stays at the top, apart from the list', () => {
    const node = document.createElement('div');
    card.renderCard(node, snapshot({ vehicleFits: false, inBattle: ['IS-3A'] }));
    assert.deepEqual(node.querySelectorAll('.zanju-crt-note-warning').map((n) => n.textContent),
        [LABELS.vehicleRestriction]);
    assert.equal(node.children[1].className, 'zanju-crt-note-warning');
});

test('no vehicle in battle means no warning and no list', () => {
    const node = document.createElement('div');
    card.renderCard(node, snapshot({}));
    assert.equal(node.querySelector('.zanju-crt-note-warning'), null);
    assert.equal(node.querySelector('.zanju-crt-battles'), null);
});

test('the series list is grouped by difficulty, the hardest first', () => {
    const node = document.createElement('div');
    card.renderCard(node, snapshot({
        series: [series({ id: 1, difficulty: 'easy' }), series({ id: 2, difficulty: 'hard' }),
            series({ id: 3, difficulty: 'easy' })],
    }));
    const groups = node.querySelectorAll('.zanju-crt-group').map((group) => group.textContent);
    assert.deepEqual(groups, [LABELS.hard, LABELS.easy]);
    assert.equal(node.querySelectorAll('.zanju-crt-series').length, 3);
    assert.equal(node.querySelector('.zanju-crt-note').textContent, LABELS.noActive);
});

// The battle panel. The payload has the shape that battle_session.py sends.
function panelPayload(overrides) {
    return Object.assign({
        lang: 'en',
        labels: { mission: LABELS.mission, or: LABELS.or },
        timeOffset: 0,
        series: { name: 'Spark', stage: 1, total: 3, shields: 3, shieldsLimit: 4 },
        group: 'and',
        rows: [{ text: 'Cause 2,500 HP of damage within the first 5 minutes of battle', icon: 'hurt_vehicles',
            set: 0, live: true, state: 'open', ratio: 0.5, valueText: '1,250', targetText: '2,500',
            deadline: null, timeLimit: 300 }],
        done: false,
    }, overrides);
}

test('the panel heads with the shields left out of all, the series and the mission', () => {
    const node = document.createElement('div');
    battle.renderPanel(node, panelPayload({}));
    assert.equal(node.querySelector('.zanju-crt-panel-shields').textContent, '3/4');
    assert.equal(node.querySelector('.zanju-crt-panel-name').textContent, 'Spark');
    assert.equal(node.querySelector('.zanju-crt-panel-stage').textContent, 'Mission 1 of 3');
});

test('a rule of a condition stands above its figures, and turns red once broken', () => {
    const node = document.createElement('div');
    const row = { text: 'Earn the High Caliber award', live: true, state: 'open', ratio: 0.2, valueText: '800',
        targetText: '4,000', rules: [{ key: 'noAllyHits', broken: false }] };
    const labels = { noAllyHits: 'The player must not hit any allies by direct shots.' };
    battle.renderPanel(node, panelPayload({ labels: labels, rows: [row] }));
    const prow = node.querySelector('.zanju-crt-prow');
    assert.deepEqual(prow.children.map((child) => child.className),
        ['zanju-crt-prow-line', 'zanju-crt-prow-rule', 'zanju-crt-prow-meter']);
    assert.equal(node.querySelector('.zanju-crt-prow-rule').textContent, labels.noAllyHits);
    const broken = document.createElement('div');
    battle.renderPanel(broken, panelPayload({ labels: labels, rows: [Object.assign({}, row, {
        state: 'closed', rules: [{ key: 'noAllyHits', broken: true }] })] }));
    assert.equal(broken.querySelector('.zanju-crt-prow-rule').className,
        'zanju-crt-prow-rule zanju-crt-prow-rule-broken');
});

test('a payload without the number of all shields shows the shields left alone', () => {
    const node = document.createElement('div');
    battle.renderPanel(node, panelPayload({ series: { name: 'Spark', stage: 1, total: 3, shields: 3 } }));
    assert.equal(node.querySelector('.zanju-crt-panel-shields').textContent, '3');
});

test('without the full information, a counted condition shows its icon, bar and figures on one line', () => {
    const node = document.createElement('div');
    battle.renderPanel(node, panelPayload({ full: false }));
    assert.equal(node.querySelector('.zanju-crt-panel-head'), null);
    assert.equal(node.querySelector('.zanju-crt-prow-text'), null);
    const meter = node.querySelector('.zanju-crt-prow-meter');
    assert.equal(meter.className, 'zanju-crt-prow-meter zanju-crt-prow-meter-bare');
    assert.deepEqual(meter.children.map((child) => child.className),
        ['zanju-crt-prow-icon', 'zanju-crt-prow-bar', 'zanju-crt-prow-figures', 'zanju-crt-prow-clock']);
    assert.equal(node.querySelector('.zanju-crt-prow-figures').textContent, '1,250 / 2,500');
});

test('without the full information, a condition with nothing to count keeps its text, and the sets their OR', () => {
    const counted = { text: 'Cause 3,000 HP of damage', icon: 'hurt_vehicles', set: 0, live: true, state: 'open',
        ratio: 0.1, valueText: '300', targetText: '3,000' };
    const top = { text: 'Be among the top 5 players of the team by damage', icon: 'top', set: 1, live: false };
    const node = document.createElement('div');
    battle.renderPanel(node, panelPayload({ full: false, group: 'or', rows: [counted, top] }));
    const list = node.querySelector('.zanju-crt-panel-rows');
    assert.deepEqual(list.children.map((child) => child.className),
        ['zanju-crt-prow', 'zanju-crt-panel-or', 'zanju-crt-prow']);
    assert.deepEqual(node.querySelectorAll('.zanju-crt-prow-text').map((n) => n.textContent), [top.text]);
});

test('without the full information, the rule of an award stays out', () => {
    const row = { text: 'Earn the High Caliber award', live: true, state: 'open', ratio: 0.2, valueText: '800',
        targetText: '4,000', rules: [{ key: 'noAllyHits', broken: false }] };
    const node = document.createElement('div');
    battle.renderPanel(node, panelPayload({ full: false, labels: { noAllyHits: 'No ally hits.' }, rows: [row] }));
    assert.equal(node.querySelector('.zanju-crt-prow-rule'), null);
});

test('a payload with no shield count shows no shield', () => {
    const node = document.createElement('div');
    battle.renderPanel(node, panelPayload({ series: { name: 'Test', stage: 1, total: 1, shields: null } }));
    assert.equal(node.querySelector('.zanju-crt-panel-shields'), null);
    assert.equal(node.querySelector('.zanju-crt-panel-shield'), null);
});

test('a counted condition has a bar filled to its ratio, and its figures', () => {
    const node = document.createElement('div');
    battle.renderPanel(node, panelPayload({}));
    assert.equal(node.querySelector('.zanju-crt-prow-fill').style.width, '50.0%');
    assert.equal(node.querySelector('.zanju-crt-prow-figures').textContent, '1,250 / 2,500');
});

test('a condition the panel cannot count shows its text alone', () => {
    const node = document.createElement('div');
    battle.renderPanel(node, panelPayload({ rows: [{ text: 'Be among the top 5 players', icon: 'top', live: false }] }));
    assert.equal(node.querySelector('.zanju-crt-prow-text').textContent, 'Be among the top 5 players');
    assert.equal(node.querySelector('.zanju-crt-prow-meter'), null);
});

test('before the battle starts, a time limit shows its whole length', () => {
    const node = document.createElement('div');
    battle.renderPanel(node, panelPayload({}));
    assert.equal(node.querySelector('.zanju-crt-prow-clock').textContent, '5:00');
});

test('a time limit counts down to its deadline as M:SS', () => {
    const node = document.createElement('div');
    const payload = panelPayload({});
    payload.rows[0].deadline = Date.now() / 1000 + 125.5;
    battle.renderPanel(node, payload);
    assert.match(node.querySelector('.zanju-crt-prow-clock').textContent, /^2:0[45]$/);
});

test('a time limit that runs has the warning color only from 1:00 on the clock', () => {
    const classAt = (secondsLeft) => {
        const node = document.createElement('div');
        const payload = panelPayload({});
        payload.rows[0].deadline = Date.now() / 1000 + secondsLeft;
        battle.renderPanel(node, payload);
        return node.querySelector('.zanju-crt-prow-clock').className;
    };
    const warning = 'zanju-crt-prow-clock zanju-crt-prow-clock-warning';
    assert.equal(classAt(125), 'zanju-crt-prow-clock');
    assert.equal(classAt(62), 'zanju-crt-prow-clock');
    assert.equal(classAt(60.5), warning);
    assert.equal(classAt(30), warning);
    assert.equal(classAt(-1), warning);
});

test('the clock takes the warning color while it counts, with no new render', () => {
    const node = document.createElement('div');
    const payload = panelPayload({});
    payload.rows[0].deadline = Date.now() / 1000 + 125;
    battle.renderPanel(node, payload);
    const clock = node.querySelector('.zanju-crt-prow-clock');
    assert.equal(clock.className, 'zanju-crt-prow-clock');
    clock._zanjuDeadline = Date.now() / 1000 + 30;
    battle.refreshClocks(node, payload);
    assert.equal(clock.className, 'zanju-crt-prow-clock zanju-crt-prow-clock-warning');
});

test('a time limit that does not run yet has no warning color, whatever its length', () => {
    const node = document.createElement('div');
    const payload = panelPayload({});
    payload.rows[0].timeLimit = 45;
    battle.renderPanel(node, payload);
    assert.equal(node.querySelector('.zanju-crt-prow-clock').className, 'zanju-crt-prow-clock');
});

test('a time limit that ran out closes a condition that is not met', () => {
    const node = document.createElement('div');
    const payload = panelPayload({});
    payload.rows[0].deadline = Date.now() / 1000 - 1;
    battle.renderPanel(node, payload);
    assert.equal(node.querySelector('.zanju-crt-prow-clock').textContent, '0:00');
    assert.equal(node.querySelectorAll('.zanju-crt-prow-closed').length, 1);
    const met = document.createElement('div');
    payload.rows[0].state = 'met';
    battle.renderPanel(met, payload);
    assert.equal(met.querySelectorAll('.zanju-crt-prow-closed').length, 0);
    assert.equal(met.querySelectorAll('.zanju-crt-prow-met').length, 1);
});

test('after a reconnect, a row has no figures, but its time limit runs and never closes it', () => {
    const node = document.createElement('div');
    const row = { text: 'Cause 2,500 HP within 5 minutes', set: 0, live: false, timeLimit: 300,
        deadline: Date.now() / 1000 - 1 };
    battle.renderPanel(node, panelPayload({ rows: [row] }));
    assert.equal(node.querySelector('.zanju-crt-prow-bar'), null);
    assert.equal(node.querySelector('.zanju-crt-prow-figures'), null);
    assert.equal(node.querySelector('.zanju-crt-prow-clock').textContent, '0:00');
    assert.equal(node.querySelectorAll('.zanju-crt-prow-closed').length, 0);
});

test('with a time limit in one row, every bar keeps a clock column, and the bars end together', () => {
    const counted = (extra) => Object.assign({ text: 'Cause damage', icon: 'hurt_vehicles', set: 0, live: true,
        state: 'open', ratio: 0.5, valueText: '10', targetText: '20' }, extra);
    const node = document.createElement('div');
    battle.renderPanel(node, panelPayload({ rows: [counted({ timeLimit: 300 }), counted({})] }));
    assert.deepEqual(node.querySelectorAll('.zanju-crt-prow-meter').map((meter) => meter.children.map(
        (child) => child.className)), [
        ['zanju-crt-prow-bar', 'zanju-crt-prow-figures', 'zanju-crt-prow-clock'],
        ['zanju-crt-prow-bar', 'zanju-crt-prow-figures', 'zanju-crt-prow-noclock'],
    ]);
    const none = document.createElement('div');
    battle.renderPanel(none, panelPayload({ rows: [counted({}), counted({})] }));
    assert.equal(none.querySelector('.zanju-crt-prow-noclock'), null);
});

test('a row with a clock and no bar keeps the clock in the clock column', () => {
    const node = document.createElement('div');
    const row = { text: 'Cause 2,500 HP within 5 minutes', set: 0, live: false, timeLimit: 300 };
    battle.renderPanel(node, panelPayload({ rows: [row] }));
    assert.deepEqual(node.querySelector('.zanju-crt-prow-meter').children.map((child) => child.className),
        ['zanju-crt-prow-gap', 'zanju-crt-prow-clock']);
});

test('the figures can show only the current value, and it counts past the required value', () => {
    const row = { text: 'Cause damage', live: true, state: 'met', ratio: 1, valueText: '3,500', targetText: '3,000' };
    const both = document.createElement('div');
    battle.renderPanel(both, panelPayload({ rows: [row] }));
    assert.equal(both.querySelector('.zanju-crt-prow-figures').textContent, '3,500 / 3,000');
    assert.equal(both.className, 'zanju-crt-panel');
    const value = document.createElement('div');
    battle.renderPanel(value, panelPayload({ figures: 'value', rows: [row] }));
    assert.equal(value.querySelector('.zanju-crt-prow-figures').textContent, '3,500');
    assert.equal(value.className, 'zanju-crt-panel zanju-crt-panel-value');
});

test('the round style has the clock on top of the dial, the figures below it and the text on its right', () => {
    const node = document.createElement('div');
    battle.renderPanel(node, panelPayload({ style: 'round' }));
    assert.equal(node.className, 'zanju-crt-panel zanju-crt-panel-round');
    assert.equal(node.querySelector('.zanju-crt-prow-bar'), null);
    const row = node.querySelector('.zanju-crt-prow');
    assert.equal(row.className, 'zanju-crt-prow zanju-crt-prow-round');
    assert.deepEqual(row.children.map((child) => child.className), ['zanju-crt-gauge', 'zanju-crt-prow-side']);
    assert.deepEqual(node.querySelector('.zanju-crt-gauge').children.map((child) => child.className),
        ['zanju-crt-prow-clock', 'zanju-crt-dial', 'zanju-crt-prow-figures zanju-crt-prow-figures-cells']);
    assert.deepEqual(node.querySelector('.zanju-crt-dial').children.map((child) => child.className),
        ['zanju-crt-dial-track', 'zanju-crt-dial-fill', 'zanju-crt-dial-icon']);
    assert.equal(node.querySelector('.zanju-crt-dial-icon').style.backgroundImage,
        "url('R.images.gui.maps.icons.userMissions.challenges.missionIcons.c_32.hurt_vehicles')");
    assert.deepEqual(node.querySelector('.zanju-crt-prow-figures').children.map((child) => child.textContent),
        ['1,250', '/', '2,500']);
    const text = node.querySelector('.zanju-crt-prow-side').children[0];
    assert.equal(text.className, 'zanju-crt-prow-text');
    assert.match(text.textContent, /^Cause 2,500 HP/);
});

test('the arc of a dial covers its ratio of three quarters of a circle, and never more', () => {
    const arcOf = (ratio) => {
        const node = document.createElement('div');
        const row = { text: 'x', icon: 'top', live: true, state: 'open', ratio: ratio, valueText: '1', targetText: '2' };
        battle.renderPanel(node, panelPayload({ style: 'round', rows: [row] }));
        return node.querySelector('.zanju-crt-dial').style['--zanju-crt-arc'];
    };
    assert.equal(arcOf(0), '0.0%');
    assert.equal(arcOf(0.5), '37.5%');
    assert.equal(arcOf(1), '75.0%');
    assert.equal(arcOf(1.4), '75.0%');
});

test('without the full information, the round style shows no text, also for a condition with nothing to count', () => {
    const counted = { text: 'Cause 3,000 HP of damage', icon: 'hurt_vehicles', set: 0, live: true, state: 'open',
        ratio: 0.1, valueText: '300', targetText: '3,000' };
    const top = { text: 'Be among the top 5 players of the team by damage', icon: 'top', set: 1, live: false };
    const node = document.createElement('div');
    battle.renderPanel(node, panelPayload({ style: 'round', full: false, group: 'or', rows: [counted, top] }));
    assert.equal(node.className, 'zanju-crt-panel zanju-crt-panel-round zanju-crt-panel-dials');
    assert.equal(node.querySelector('.zanju-crt-panel-head'), null);
    assert.equal(node.querySelector('.zanju-crt-prow-text'), null);
    assert.equal(node.querySelector('.zanju-crt-prow-side'), null);
    assert.equal(node.querySelectorAll('.zanju-crt-panel-or').length, 1);
});

test('a condition with nothing to count has an empty ring and no figures, with and without the full information', () => {
    const top = { text: 'Be among the top 5 players of the team by damage', icon: 'top', live: false };
    [true, false].forEach((full) => {
        const node = document.createElement('div');
        battle.renderPanel(node, panelPayload({ style: 'round', full: full, rows: [top] }));
        const gauge = node.querySelector('.zanju-crt-gauge');
        assert.deepEqual(gauge.children.map((child) => child.className), ['zanju-crt-dial']);
        assert.deepEqual(gauge.children[0].children.map((child) => child.className),
            ['zanju-crt-dial-track', 'zanju-crt-dial-icon']);
    });
});

test('the round style with only the current value is the narrowest form', () => {
    const node = document.createElement('div');
    battle.renderPanel(node, panelPayload({ style: 'round', figures: 'value', full: false }));
    assert.equal(node.className, ['zanju-crt-panel', 'zanju-crt-panel-value', 'zanju-crt-panel-round',
        'zanju-crt-panel-dials'].join(' '));
    assert.equal(node.querySelector('.zanju-crt-prow-figures').textContent, '1,250');
    assert.equal(node.querySelector('.zanju-crt-prow-figures').className, 'zanju-crt-prow-figures');
});

test('the widest figures come from the longest figure of the panel, with the widest digit', () => {
    const counted = (valueText, targetText) => ({ live: true, valueText: valueText, targetText: targetText });
    assert.equal(battle.widestFigures(panelPayload({ rows: [counted('0', '500'), counted('480', '1,000')] })),
        '8,888 / 8,888');
    assert.equal(battle.widestFigures(panelPayload({ figures: 'value', rows: [counted('446', '1,500')] })), '8,888');
});

test('the widest figures stay the same while the panel counts, until a value has more digits than the target', () => {
    const widest = (valueText) => battle.widestFigures(panelPayload({ rows: [
        { live: true, valueText: valueText, targetText: '1,500' }] }));
    assert.equal(widest('0'), '8,888 / 8,888');
    assert.equal(widest('9,999'), '8,888 / 8,888');
    assert.equal(widest('10,000'), '88,888 / 88,888');
});

test('the widest figures keep the separator of the language, and are empty with nothing to count', () => {
    assert.equal(battle.widestFigures(panelPayload({ rows: [
        { live: true, valueText: '0', targetText: '1 500' }] })), '8 888 / 8 888');
    assert.equal(battle.widestFigures(panelPayload({ rows: [{ text: 'x', icon: 'top', live: false }] })), '');
    assert.equal(battle.widestFigures(null), '');
});

test('a time limit that ran out closes the row of a dial too', () => {
    const node = document.createElement('div');
    const payload = panelPayload({ style: 'round' });
    payload.rows[0].deadline = Date.now() / 1000 - 1;
    battle.renderPanel(node, payload);
    assert.equal(node.querySelector('.zanju-crt-prow-clock').textContent, '0:00');
    assert.equal(node.querySelectorAll('.zanju-crt-prow-closed').length, 1);
});

test('the panel draws one or separator between two sets', () => {
    const node = document.createElement('div');
    const row = (text, set) => ({ text: text, set: set, live: false });
    battle.renderPanel(node, panelPayload({ group: 'or', rows: [row('a', 0), row('b', 0), row('c', 1)] }));
    const list = node.querySelector('.zanju-crt-panel-rows');
    assert.deepEqual(list.children.map((child) => child.className === 'zanju-crt-panel-or' ? 'OR' : child.textContent),
        ['a', 'b', 'OR', 'c']);
});

test('a met set marks the panel done', () => {
    const node = document.createElement('div');
    battle.renderPanel(node, panelPayload({ done: true }));
    assert.equal(node.querySelectorAll('.zanju-crt-panel-done').length, 1);
});

test('the clock rounds down, as the battle clock does', () => {
    assert.equal(battle.formatClock(300), '5:00');
    assert.equal(battle.formatClock(299.9), '4:59');
    assert.equal(battle.formatClock(9), '0:09');
    assert.equal(battle.formatClock(-3), '0:00');
});
