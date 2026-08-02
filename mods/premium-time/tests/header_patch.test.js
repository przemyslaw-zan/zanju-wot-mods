// Tests for the lobby-header countdown patch.
//
// Run via `zwm test premium-time` (Node's built-in runner, no npm dependencies).
// The module under test auto-starts only when a Gameface view registry is present, so
// importing it here is side-effect free and each test drives it against its own fakes.

import { test, describe, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

import {
    COUNTER_CLASS,
    formatRemaining,
    newState,
    overrides,
    tick,
} from '../res/gui/gameface/mods/zanju_premiumtime/header_patch.js';

const UNITS = { dayUnit: 'd', hourUnit: 'h', minuteUnit: 'm', secondUnit: 's' };
const HOUR = 3600;
const DAY = 86400;

describe('formatRemaining', () => {
    const cases = [
        ['days and hours only, minutes dropped', 3 * DAY + 5 * HOUR + 9 * 60 + 12, '3d 05h'],
        ['hours and minutes, seconds dropped', 2 * HOUR + 11 * 60 + 30, '2h 11m'],
        ['keeps padding on the second unit', 2 * HOUR + 5 * 60, '2h 05m'],
        ['seconds appear under an hour', 5 * 60 + 12, '5m 12s'],
        ['just under an hour', HOUR - 1, '59m 59s'],
        ['under a minute shows seconds alone', 45, '45s'],
        ['zero is a bare second value', 0, '0s'],
        ['negative clamps to zero', -30, '0s'],
        ['whole day keeps padded zeros', DAY, '1d 00h'],
        ['whole hour keeps padded minutes', HOUR, '1h 00m'],
        ['whole minute keeps padded seconds', 60, '1m 00s'],
        ['large day counts are not padded', 412 * DAY + 5 * HOUR, '412d 05h'],
        ['top unit stays unpadded', 10 * DAY + 23 * HOUR + 59 * 60, '10d 23h'],
    ];

    for (const [name, seconds, expected] of cases) {
        test(name, () => {
            assert.equal(formatRemaining(seconds, UNITS), expected);
        });
    }

    test('stays within a narrow width band as time runs down', () => {
        // Trailing units stay zero-padded so the label never grows while a unit ticks; a
        // label that grew would shove the header button's neighbours around. It does gain
        // one character where the leading unit rolls over and the next is two digits
        // ("1d 00h" -> "23h 59m"), which is inherent to dropping a unit.
        let widest = 0;
        let previousLength = Infinity;
        for (let seconds = 2 * DAY; seconds >= 0; seconds -= 1) {
            const label = formatRemaining(seconds, UNITS);
            widest = Math.max(widest, label.length);
            assert.ok(
                label.length <= previousLength + 1,
                'label jumped by more than one character at ' + seconds + 's: "' + label + '"'
            );
            previousLength = label.length;
        }
        assert.ok(widest <= 7, 'label should stay compact, widest was ' + widest);
    });

});

describe('subscription countdown and expiry', () => {
    let env;
    let nowMs;
    const realDateNow = Date.now;
    const realConsoleError = console.error;

    // Mirrors how the game's header bundle renders the Premium button: the label lives in
    // a <span> child of div.Premiums_text. Setting textContent on an element drops its
    // children, exactly like the real DOM, which is what made the span bug possible.
    class FakeNode {
        constructor(className = '', tag = 'div') {
            this.className = className;
            this.tag = tag;
            this.children = [];
            this._text = '';
            // Real CSSStyleDeclaration returns '' for properties that were never set,
            // not undefined — the production code compares against both.
            this.style = new Proxy({}, {
                get: (target, key) => (key in target ? target[key] : ''),
                set: (target, key, value) => {
                    target[key] = value;
                    return true;
                },
            });
        }

        get textContent() {
            return this.children.length
                ? this.children.map((child) => child.textContent).join('')
                : this._text;
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

        removeChild(child) {
            this.children = this.children.filter((c) => c !== child);
            child.parentNode = null;
            return child;
        }

        // Stand-in for a proportional font: "1" is narrow, "8" wide, letters in between.
        // Without this the digit measurement would find every digit equally wide and the
        // fixed-width cells would prove nothing.
        get offsetWidth() {
            const widths = { '1': 4, '8': 10, ' ': 3 };
            if (this.style.width) {
                return parseInt(this.style.width, 10);
            }
            return [...this.textContent].reduce((sum, ch) => sum + (widths[ch] ?? 7), 0);
        }

        matches(selector) {
            if (selector === 'span') {
                return this.tag === 'span';
            }
            if (selector.startsWith('.')) {
                return this.className.includes(selector.slice(1));
            }
            const attr = /\[class\*="([^"]+)"\]/.exec(selector);
            return attr ? this.className.includes(attr[1]) : false;
        }

        querySelectorAll(selector) {
            const found = [];
            for (const child of this.children) {
                if (child.matches(selector)) {
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

    function makeButton(withSpan) {
        const button = new FakeNode('Premiums_subscription');
        const label = new FakeNode('Premiums_text_82711911');
        button.children.push(new FakeNode('Premiums_premiumImg'), label);
        if (withSpan) {
            const span = new FakeNode('', 'span');
            label.children.push(span);
        }
        return button;
    }

    function makeEnv(premium) {
        const buttons = { premium: makeButton(true) };
        const labels = { premium: buttons.premium.querySelector('div[class*="Premiums_text"]') };
        const model = {
            zanjuPtHeader: Object.assign({ timeOffset: 0 }, UNITS),
            subscriptions: {
                premiumAccount: Object.assign({ state: 'Inactive', expiryTime: 0 }, premium),
            },
        };
        globalThis.window = { subViews: { ids: () => [1], get: () => ({ model }) } };
        const head = new FakeNode('head');
        globalThis.document = {
            head,
            createElement: () => new FakeNode(),
            querySelector(selector) {
                const match = /data-test-id="([^"]+)"/.exec(selector);
                return (match && buttons[match[1]]) || null;
            },
        };
        return { buttons, labels, model, head };
    }

    function nowSeconds() {
        return Math.floor(nowMs / 1000);
    }

    function advance(seconds) {
        nowMs += seconds * 1000;
    }

    beforeEach(() => {
        nowMs = 1_700_000_000_000;
        Date.now = () => nowMs;
        console.error = () => {};
        overrides.premium = newState();
        env = makeEnv();
    });

    afterEach(() => {
        Date.now = realDateNow;
        console.error = realConsoleError;
        delete globalThis.window;
        delete globalThis.document;
    });

    // Helpers mirroring how the two elements relate on screen.
    const counter = () => env.buttons.premium.querySelector('.' + COUNTER_CLASS);
    const gameLabel = () => env.labels.premium;
    const visibleText = () =>
        (counter() ? counter().textContent : gameLabel().style.display === 'none' ? '' : gameLabel().textContent);

    test('leaves an inactive subscription alone', () => {
        gameLabel().textContent = 'Upgrade';
        tick();
        assert.equal(counter(), null, 'nothing should be added while premium is off');
        assert.equal(gameLabel().style.display, '');
        assert.equal(visibleText(), 'Upgrade');
    });

    test('shows a countdown beside the hidden game label while running', () => {
        gameLabel().textContent = '3d';
        Object.assign(env.model.subscriptions.premiumAccount, {
            state: 'Active',
            expiryTime: nowSeconds() + 2 * DAY + 4 * HOUR + 30 * 60,
        });
        tick();

        assert.equal(counter().textContent, '2d 04h');
        assert.equal(gameLabel().style.display, 'none', "the game's label is hidden, not rewritten");
        assert.equal(gameLabel().textContent, '3d', "the game's own label must be left intact");
    });

    test('inherits the game label styling', () => {
        Object.assign(env.model.subscriptions.premiumAccount, {
            state: 'Active',
            expiryTime: nowSeconds() + HOUR,
        });
        tick();
        assert.match(counter().className, /Premiums_text/, 'must reuse the game class for styling');
        assert.match(counter().className, new RegExp(COUNTER_CLASS));
    });

    test('holds zero once expiry passes but the game still reports it running', () => {
        Object.assign(env.model.subscriptions.premiumAccount, {
            state: 'Active',
            expiryTime: nowSeconds() + 30,
        });
        tick();
        assert.equal(counter().textContent, '30s');

        advance(45);
        tick();
        assert.equal(counter().textContent, '0s');
        assert.equal(gameLabel().style.display, 'none');
    });

    test('removes the countdown and unhides the game label on expiry', () => {
        // Regression, seen live: the counter used to be written into React's own node, so
        // when the game finally repainted "Upgrade" our markup was still there underneath
        // and the stale "0s" came back and stuck. Our element is now separate, so handing
        // over is just a removal.
        Object.assign(env.model.subscriptions.premiumAccount, {
            state: 'Active',
            expiryTime: nowSeconds() + 10,
        });
        tick();
        advance(20);
        tick();
        assert.equal(counter().textContent, '0s');

        Object.assign(env.model.subscriptions.premiumAccount, { state: 'Inactive', expiryTime: 0 });
        gameLabel().textContent = 'Upgrade';
        tick();

        assert.equal(counter(), null, 'our element must be removed');
        assert.equal(gameLabel().style.display, '', 'the game label must be visible again');
        assert.equal(visibleText(), 'Upgrade');

        // And it must stay that way, however many ticks follow.
        for (let i = 0; i < 5; i += 1) {
            advance(1);
            tick();
        }
        assert.equal(counter(), null);
        assert.equal(visibleText(), 'Upgrade');
    });

    test('survives the game repainting its label mid-countdown', () => {
        Object.assign(env.model.subscriptions.premiumAccount, {
            state: 'Active',
            expiryTime: nowSeconds() + 5 * 60 + 18,
        });
        tick();
        assert.equal(counter().textContent, '5m 18s');

        // React re-renders its own label; ours is untouched because it is a separate node.
        gameLabel().textContent = '1 d';
        advance(1);
        tick();
        assert.equal(counter().textContent, '5m 17s');
        assert.equal(gameLabel().style.display, 'none');
    });

    test('resumes counting when a renewal extends the expiry mid-hold', () => {
        Object.assign(env.model.subscriptions.premiumAccount, {
            state: 'Active',
            expiryTime: nowSeconds() + 5,
        });
        tick();
        advance(10);
        tick();
        assert.equal(counter().textContent, '0s');

        env.model.subscriptions.premiumAccount.expiryTime = nowSeconds() + 3 * DAY + 2 * HOUR;
        tick();
        assert.equal(counter().textContent, '3d 02h');
    });

    test('applies the server clock offset', () => {
        env.model.zanjuPtHeader.timeOffset = 3600;
        Object.assign(env.model.subscriptions.premiumAccount, {
            state: 'Active',
            expiryTime: nowSeconds() + 2 * HOUR,
        });
        tick();
        assert.equal(counter().textContent, '1h 00m');
    });

    test('unwraps observable-style model values', () => {
        Object.assign(env.model.subscriptions.premiumAccount, {
            state: { value: 'Active' },
            expiryTime: { value: nowSeconds() + 90 * 60 },
        });
        tick();
        assert.equal(counter().textContent, '1h 30m');
    });

    test('lays every digit out in an equal-width cell', () => {
        // With a proportional font a ticking "1" and "8" are different widths, so the label
        // shimmies. Each digit gets a cell as wide as the widest digit.
        Object.assign(env.model.subscriptions.premiumAccount, {
            state: 'Active',
            expiryTime: nowSeconds() + 11 * 60 + 18,
        });
        tick();

        const cells = counter().children.filter((child) => /^[0-9]$/.test(child.textContent));
        assert.equal(cells.length, 4, 'every digit should get its own cell');
        const widths = new Set(cells.map((cell) => cell.style.width));
        assert.equal(widths.size, 1, 'all digit cells should share one width, got ' + [...widths]);

        const letters = counter().children.filter((child) => !/^[0-9]$/.test(child.textContent));
        assert.ok(letters.every((child) => !child.style.width), 'units keep their natural width');
    });

    test('uses a layout value the renderer accepts', () => {
        // Gameface rejects `align-items: baseline` outright; the game's own CSS only ever
        // uses center.
        Object.assign(env.model.subscriptions.premiumAccount, {
            state: 'Active',
            expiryTime: nowSeconds() + HOUR,
        });
        tick();
        assert.equal(counter().style.display, 'flex');
        assert.equal(counter().style.alignItems, 'center');
    });

    test('survives a missing button node', () => {
        globalThis.document.querySelector = () => null;
        Object.assign(env.model.subscriptions.premiumAccount, {
            state: 'Active',
            expiryTime: nowSeconds() + HOUR,
        });
        assert.doesNotThrow(() => tick());
    });
});
