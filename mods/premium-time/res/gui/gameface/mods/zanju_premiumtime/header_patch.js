// Zanju Premium Time — live remaining-time counter on the lobby header's Premium button.
//
// Injected into the lobby header's Gameface document by net.openwg.gameface (see
// src/zanju_pt/gameface/header_inject.py). The Premium Account button normally shows a
// coarse "N d" while premium is running and "Upgrade" when it is not; we replace the
// running label with a live countdown computed from the game's own view model (see
// formatRemaining for the format), and leave the inactive label alone.
//
// The state machine below is written per subscription rather than for this one button, so
// the WoT Plus button could be driven from the same code again; see
// docs/reference/wot-plus-subscriptions.md.
//
// React owns these nodes and rewrites them on its own re-renders, so we re-apply on a
// short interval and re-capture the original label whenever React has repainted it.
//
// Expiry handling: the client does not decide on its own that a subscription ended.
// `stats.isPremium` is derived from a server-pushed premium mask, so the view model can
// still report "Active" for a while after the expiry timestamp has passed. If we stop
// overriding the moment our own countdown reaches zero, we hand the button back while
// React's last render is still the running-subscription label ("1d"), which then sits
// there looking alive until the server push lands. Instead we hold a zeroed counter and
// only release once the game itself reports the subscription as no longer running.

const APPLY_INTERVAL_MS = 500;
// How many time units the label shows at once (see formatRemaining).
const MAX_UNITS = 2;

// A ticking seconds digit changes width in a proportional font, so the label shimmies
// several times a second. Two tidier fixes do not work here: swapping in a monospace face
// looks foreign next to the rest of the header, and the font's own tabular-figure feature
// (PFDINMax does ship `tnum`) is ignored — Gameface implements neither
// `font-variant-numeric` nor `font-feature-settings`, and the game's own CSS never uses
// them.
//
// So the digits are monospaced by layout instead: each one goes in a fixed-width cell as
// wide as the widest digit, in a flex row. Flex is what the game's own Timer component
// uses for its label, so it is known to work in this renderer. The cell width is measured
// from the live element rather than guessed, so it follows the font and the interface
// scale; if measuring fails the label falls back to plain text and merely keeps jittering.
// Our countdown lives in its own element next to the game's label rather than inside it.
// Writing into React's own node is what caused two separate bugs: replacing its <span>
// left React updating a detached node, and injecting child elements left our markup behind
// when React repainted, so the stale countdown reappeared after the label had already
// switched to "Upgrade". React now owns its label untouched, and we simply hide it while
// ours is on screen.
const COUNTER_CLASS = 'zanju-pt-counter';
const DIGIT_CELL_CACHE_KEY = '__zanjuPtDigitCell';
const COUNTDOWN_STYLES = {
    display: 'flex',
    alignItems: 'center',
};
const overrides = {
    premium: newState(),
};

function newState() {
    return {
        original: null,
        last: null,
        // Expiry passed but the game still reports the subscription as running.
        holding: false,
        // When the hold began, so releasing it can report how far behind the game was.
        holdStartedMs: 0,
        // Last state string seen in the view model, for transition logging.
        state: null,
    };
}

function log(message) {
    // console.error, not console.log: error-level output reaches game.log, tagged
    // [UI] [Gameface], and log-level output is untested there.
    // OpenWG's own debug helper (mods/libs/debug.js) writes plain debug output the same way.
    console.error('[zanju.premiumtime] ' + message);
}

function unwrap(value) {
    return value && typeof value === 'object' && 'value' in value ? value.value : value;
}

function findAccountModel() {
    const ids = window.subViews.ids();
    for (const id of ids) {
        const view = window.subViews.get(id);
        const model = view && view.model;
        if (model && model.zanjuPtHeader && model.subscriptions) {
            return model;
        }
    }
    return null;
}

function buttonOf(testId) {
    return document.querySelector('[data-test-id="' + testId + '"]');
}

function gameLabelOf(button) {
    // Our own counter carries the same styling class, so skip it when looking for the
    // game's label.
    if (!button) {
        return null;
    }
    const candidates = button.querySelectorAll('div[class*="Premiums_text"]');
    for (let i = 0; i < candidates.length; i += 1) {
        if (String(candidates[i].className).indexOf(COUNTER_CLASS) === -1) {
            return candidates[i];
        }
    }
    return null;
}

function counterOf(button) {
    return button ? button.querySelector('.' + COUNTER_CLASS) : null;
}

function two(n) {
    return n < 10 ? '0' + n : '' + n;
}


function formatRemaining(seconds, cfg) {
    const total = Math.max(0, Math.floor(seconds));
    const units = [
        [Math.floor(total / 86400), unwrap(cfg.dayUnit)],
        [Math.floor((total % 86400) / 3600), unwrap(cfg.hourUnit)],
        [Math.floor((total % 3600) / 60), unwrap(cfg.minuteUnit)],
        [total % 60, unwrap(cfg.secondUnit)],
    ];
    // Show the two most significant units that carry a value: "3d 05h", "2h 11m",
    // "5m 12s", "45s". Capping at two keeps the label short enough for the header button
    // and makes seconds appear exactly when under an hour is left, where they are the
    // only thing still moving. The first unit shown is unpadded, the second keeps two
    // digits ("2h 05m", never "2h 5m") so the label does not widen as it counts down.
    const first = units.findIndex(([value]) => value !== 0);
    if (first === -1) {
        return '0' + unwrap(cfg.secondUnit);
    }
    return units
        .slice(first, first + MAX_UNITS)
        .map(([value, unit], index) => (index === 0 ? String(value) : two(value)) + unit)
        .join(' ');
}

function digitCellWidth(el) {
    // Widest of the ten digits, measured once per document off a hidden probe that inherits
    // the label's own font and size.
    if (typeof document === 'undefined') {
        return 0;
    }
    if (document[DIGIT_CELL_CACHE_KEY] !== undefined) {
        return document[DIGIT_CELL_CACHE_KEY];
    }
    let widest = 0;
    try {
        const probe = document.createElement('span');
        probe.style.position = 'absolute';
        probe.style.visibility = 'hidden';
        probe.style.whiteSpace = 'pre';
        el.appendChild(probe);
        for (let digit = 0; digit <= 9; digit += 1) {
            probe.textContent = String(digit);
            widest = Math.max(widest, probe.offsetWidth || 0);
        }
        el.removeChild(probe);
    } catch (e) {
        widest = 0;
    }
    document[DIGIT_CELL_CACHE_KEY] = widest;
    return widest;
}

function writeDigits(el, text) {
    const cell = digitCellWidth(el);
    if (!cell) {
        // No usable measurement: plain text still shows the right value.
        el.textContent = text;
        return;
    }

    el.textContent = '';

    let run = '';
    const flushRun = () => {
        if (!run) {
            return;
        }
        const span = document.createElement('span');
        span.textContent = run;
        // Unit letters and the separating space keep their natural width; only digits are
        // forced into cells, so the label still reads as normal text.
        span.style.whiteSpace = 'pre';
        el.appendChild(span);
        run = '';
    };

    for (const character of text) {
        if (character >= '0' && character <= '9') {
            flushRun();
            const span = document.createElement('span');
            span.textContent = character;
            span.style.width = cell + 'px';
            span.style.textAlign = 'center';
            span.style.flex = '0 0 auto';
            el.appendChild(span);
        } else {
            run += character;
        }
    }
    flushRun();
}

function showCountdown(key, text) {
    const button = buttonOf(key);
    const gameLabel = gameLabelOf(button);
    if (!gameLabel) {
        return;
    }

    let counter = counterOf(button);
    if (!counter) {
        counter = document.createElement('div');
        // Same class as the game's label, so the counter inherits its size, colour,
        // padding and text shadow without copying any of them.
        counter.className = gameLabel.className + ' ' + COUNTER_CLASS;
        for (const property of Object.keys(COUNTDOWN_STYLES)) {
            counter.style[property] = COUNTDOWN_STYLES[property];
        }
        button.appendChild(counter);
    }

    if (gameLabel.style.display !== 'none') {
        gameLabel.style.display = 'none';
    }
    if (counter.textContent !== text) {
        writeDigits(counter, text);
    }
}

function hideCountdown(key) {
    const button = buttonOf(key);
    const counter = counterOf(button);
    if (counter && counter.parentNode) {
        counter.parentNode.removeChild(counter);
    }
    const gameLabel = gameLabelOf(button);
    if (gameLabel && gameLabel.style.display === 'none') {
        gameLabel.style.display = '';
    }
}

function updateSubscription(key, state, isRunningState, expiry, now, cfg) {
    const st = overrides[key];
    if (st.state !== state) {
        log(key + ': state ' + st.state + ' -> ' + state
            + ' (expiry=' + expiry + ' now=' + Math.floor(now) + ')');
        st.state = state;
    }

    const running = isRunningState && expiry > 0;
    const remaining = expiry - now;

    if (running && remaining > 0) {
        if (st.holding) {
            log(key + ': expiry moved into the future (renewed), resuming countdown');
            st.holding = false;
        }
        showCountdown(key, formatRemaining(remaining, cfg));
        return;
    }

    if (running) {
        // Expiry reached; the game has not caught up yet. Hold zero rather than handing
        // back a label that still advertises a live subscription.
        if (!st.holding) {
            st.holding = true;
            st.holdStartedMs = Date.now();
            log(key + ': expiry reached, holding zero until the game reports it inactive');
        }
        showCountdown(key, formatRemaining(0, cfg));
        return;
    }

    if (st.holding) {
        st.holding = false;
        log(key + ': game reports state=' + state + ' after '
            + Math.round((Date.now() - st.holdStartedMs) / 1000) + 's, releasing label');
        hideCountdown(key);
        return;
    }

    hideCountdown(key);
}

function tick() {
    const model = findAccountModel();
    if (!model) {
        return;
    }
    const cfg = model.zanjuPtHeader;
    const subs = model.subscriptions;
    if (!cfg || !subs || !subs.premiumAccount) {
        return;
    }
    const now = Date.now() / 1000 + (Number(unwrap(cfg.timeOffset)) || 0);

    const premiumState = unwrap(subs.premiumAccount.state);
    updateSubscription(
        'premium',
        premiumState,
        premiumState === 'Active',
        Number(unwrap(subs.premiumAccount.expiryTime)) || 0,
        now,
        cfg
    );
}

function start() {
    // No load banner: this runs on every hangar document, and the Python side already logs
    // "Lobby header integration installed" once when the inject is attached.
    tick();
    setInterval(tick, APPLY_INTERVAL_MS);
}

// Auto-start only inside the game document. Under the test runner there is no
// Gameface view registry, so importing this module stays free of side effects and
// the tests drive tick()/formatRemaining() directly against fakes they control.
if (typeof window !== 'undefined' && window.subViews) {
    start();
}

export {
    formatRemaining,
    overrides,
    newState,
    tick,
    start,
    showCountdown,
    hideCountdown,
    updateSubscription,
    COUNTER_CLASS,
};
