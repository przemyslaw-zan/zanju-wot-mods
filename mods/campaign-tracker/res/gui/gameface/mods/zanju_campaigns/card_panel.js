// The campaign hover card, as its own Gameface document.
//
// The card used to be a child of the banner, inside the garage document. That pinned it to the
// garage's window band, so a native window such as the platoon window drew over it whatever
// z-index it carried. It now renders here, in a window the mod owns on a band of its own. See
// gameface/card_window.py for the Python half and docs/reference/choosing-a-ui-approach.md for
// why this route was taken.
//
// The rendering itself did not change: `renderCard` is the same function the banner used, moved
// to card.js so it can be shared. What changed is where it draws and how it is placed.
//
// The model API here is the client's own, not the one the upstream guide documents:
// `window.model` for a document's root model, `engine.on('viewEnv.onDataChanged', ...)` with
// `viewEnv.addDataChangedCallback` for updates. `viewEnv.getViewModel` does not exist.
//
// The card paints nothing until Python says it has placed the window. That is not a nicety: a
// hidden Wulf window runs no frames, so `requestAnimationFrame` never fires and the card can
// never measure itself. Python therefore shows the window first and moves it second, and the
// card stays transparent across the gap so nothing is seen at the previous card's position.

import { applyHints, renderCard } from './card.js';
import { log, parseHeldKeys, parseJson } from './common.js';

// A standalone view owns its whole document, so its model is the root one.
const ROOT_RES_ID = 0;

// The card is only ever as big as its content, and Python needs the real number to place the
// window under the banner. Measured after layout has settled, then published once per change.
let lastPublished = '';
// Bumped on every render so a measurement scheduled for a card the pointer has already left
// cannot publish over the current one.
let measureGeneration = 0;
// The token whose card is currently built. A payload arriving with the same token is Python
// changing one field -- the reveal flag or the held keys -- not a different card.
let renderedToken = '';
// The token of the card on screen. Python rejects a size carrying any other token, so a measure
// that was not triggered by a payload -- a scale change, say -- has to quote this one.
let currentToken = '';

function cardNode() {
    return document.getElementById('zanju-ct-card');
}

function readModel() {
    return window.model || null;
}

function render(model) {
    const card = cardNode();
    if (!card || !model) {
        return;
    }
    const payload = parseJson(model.payload, 'card payload');
    if (!payload || !payload.entry) {
        // Python hides the window rather than sending an empty card, so this is only reached
        // before the first hover. Leave the last card standing -- it is not on screen -- but
        // still publish a size, because the engine gives the view a limited window to report
        // one and falls back to a default size if nothing arrives.
        publishSize('');
        return;
    }
    const token = String(payload.token || '');
    const keys = parseHeldKeys(payload.heldKeys);

    if (token === renderedToken) {
        // Same card, one field changed. Rebuilding it would throw away a measurement that is
        // already correct and start the whole handshake again.
        applyHints(card, keys, payload.entry);
        setRevealed(card, payload.reveal);
        return;
    }

    renderCard(card, payload.entry, payload.labels || {});
    applyHints(card, keys, payload.entry);
    // A new card is never painted where the last one stood. Python reveals it once it has
    // moved the window, which it can only do once this render has been measured.
    setRevealed(card, false);
    renderedToken = token;
    currentToken = token;
    scheduleMeasure(token);
}

function setRevealed(card, revealed) {
    card.className = revealed ? 'zanju-ct-card zanju-ct-card-shown' : 'zanju-ct-card';
}

// Measure after layout, never in the frame that changed the DOM.
//
// This is what the bottom of the card was being cut off by. `getBoundingClientRect` right after
// building the card reports the layout as it stood before the new content, so the height came
// back short, `resizeViewPx` gave the native surface that short height, and the last rows -- the
// hint lines -- fell outside it. It read as random because whether the old layout was already
// close to the new one depends on which banner was hovered before.
//
// Measured twice: once two frames later, and once more after that. The second pass costs one
// comparison and catches a late settle, such as a font becoming available between the two.
function scheduleMeasure(token) {
    measureGeneration += 1;
    const generation = measureGeneration;
    nextFrame()
        .then(nextFrame)
        .then(function () {
            if (generation !== measureGeneration) {
                return null;
            }
            publishSize(token);
            return nextFrame();
        })
        .then(function () {
            if (generation === measureGeneration) {
                publishSize(token);
            }
        })
        .catch(function (error) { log('card measurement failed: ' + error); });
}

// Tell the native surface how big the card actually is, then tell Python, which cannot measure
// the DOM and must not place the window before it knows.
function publishSize(token) {
    const card = cardNode();
    if (!card) {
        return;
    }
    const rect = card.getBoundingClientRect();
    const width = Math.ceil(rect.width);
    const height = Math.ceil(rect.height);
    if (!(width > 0 && height > 0)) {
        return;
    }

    try {
        viewEnv.resizeViewPx(width, height);
    } catch (error) {
        log('resizeViewPx failed: ' + error);
    }

    // The token comes back with the size so Python can ignore a measurement for a card it has
    // already moved past -- the pointer can leave one banner and enter another between a push
    // and the frame that measures it.
    const key = token + ':' + width + 'x' + height;
    if (key === lastPublished) {
        return;
    }
    lastPublished = key;
    log('card measured ' + width + 'x' + height + ' (token ' + token + ')');
    const model = readModel();
    const sized = model && model.onSized;
    if (typeof sized === 'function') {
        sized.call(model, { token: String(token || ''), width: width, height: height });
    } else if (sized && typeof sized.value === 'function') {
        sized.value.call(sized, { token: String(token || ''), width: width, height: height });
    } else {
        log('the onSized command is missing on the card model');
    }
}

function waitForDomBuilt() {
    return new Promise(function (resolve) {
        if (window.isDomBuilt) {
            resolve();
            return;
        }
        engine.on('self.onDomBuilt', resolve);
    });
}

function nextFrame() {
    return new Promise(function (resolve) { requestAnimationFrame(resolve); });
}

engine.whenReady
    .then(waitForDomBuilt)
    // Two frames: the card is measured, and a measurement taken before layout settles reports
    // the wrapped width rather than the intended one.
    .then(nextFrame)
    .then(nextFrame)
    .then(function () {
        render(readModel());
        engine.on('viewEnv.onDataChanged', function () { render(readModel()); });
        // The surface follows the interface scale: every size here is in `rem`, so a scale
        // change re-lays the card out and the published size has to follow it.
        engine.on('self.onScaleUpdated', function () { scheduleMeasure(currentToken); });
        viewEnv.addDataChangedCallback('model', ROOT_RES_ID, true);
        log('card window ready');
    })
    .catch(function (error) { log('card startup failed: ' + error); });

export { publishSize, render, scheduleMeasure };
