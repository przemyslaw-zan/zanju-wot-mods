// The few things both documents need: the banners in the garage document, and the card in the
// mod's own window.
//
// Kept deliberately small. Anything only one side uses stays on that side, so this file never
// becomes the place where the two documents quietly grow shared state.

const IDLE_ID = '—';

// The stages a mission can be in once its primary objective is settled, in the order Python
// reports them. Listed rather than trusted, because the value is used as a label key and as a
// CSS class suffix, and neither should take whatever string arrives.
const STAGES = ['improving', 'pawned'];

const ACTION_OPEN = 'open';
const ACTION_PAUSE = 'pause';
const ACTION_RESET = 'reset';

function log(message) {
    // console.error reaches game.log, tagged [UI] [Gameface]. console.log is untested here.
    console.error('[zanju.campaigntracker] ' + message);
}

function unwrap(value) {
    return value && typeof value === 'object' && 'value' in value ? value.value : value;
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

// Which action a click carries, given the keys held with it. The card lights the matching hint
// line and the banner runs it, so the rule has to be one rule. Holding both keys names no
// action, and so does a key whose action this mission cannot take: falling through would land
// on reset, which is the one action that throws work away.
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

// Which keys are held arrives from Python, as one string on the data model — see held_keys.py
// for why it is not read from either document's own key events.
function parseHeldKeys(text) {
    const held = typeof text === 'string' ? text.split(' ') : [];
    return { shift: held.indexOf('shift') >= 0, ctrl: held.indexOf('ctrl') >= 0 };
}

export {
    ACTION_OPEN,
    ACTION_PAUSE,
    ACTION_RESET,
    IDLE_ID,
    STAGES,
    actionFor,
    el,
    log,
    parseHeldKeys,
    parseJson,
    unwrap,
};
