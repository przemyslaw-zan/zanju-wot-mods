// The Crucible battle panel, as its own Gameface document, in a window the mod owns.
//
// Three jobs: draw the payload, publish the real size so Python can place and clamp the window,
// and report the press and the release of a drag. Python moves the window between the two by the
// cursor position, because mouse events stop when the pointer leaves this small window. See
// gameface/battle_panel.py.

import { refreshClocks, renderPanel, widestFigures } from './battle.js';
import { applyLanguage, callCommand, nextFrame, readModel, waitForDomBuilt } from './card_host.js';
import { log, parseJson, unwrap } from './common.js';

// A standalone view owns its whole document, so its model is the root one.
const ROOT_RES_ID = 0;
const CLOCK_INTERVAL_MS = 1000;
let lastSize = '';
let lastPayload = '';
let currentPayload = null;
let dragging = false;

function panelNode() {
    return document.getElementById('zanju-crt-panel');
}

function probeNode() {
    return document.getElementById('zanju-crt-panel-probe');
}

function command(name, arg) {
    callCommand(readModel(), name, arg, log);
}

function render() {
    const model = readModel();
    const node = panelNode();
    if (!model || !node) {
        return;
    }
    const raw = String(unwrap(model.payload) || '');
    if (raw === lastPayload) {
        return;
    }
    lastPayload = raw;
    const payload = parseJson(raw, 'panel payload');
    currentPayload = payload;
    // battle.css reads `lang` to select the font, as the card does. See card_host.js.
    applyLanguage(payload && payload.lang);
    renderPanel(node, payload);
    probeNode().textContent = widestFigures(payload);
}

// The width of the column of the dials. The renderer cannot size a box from its content, so this
// reads the hidden probe, and battle.css gives the column that width. The observer also calls back
// for a new font or a new interface scale. The value stays on the panel through a new render and
// through a change of form, so the column has its width before the first layout of that form.
function followFigures() {
    const probe = probeNode();
    new ResizeObserver(function () {
        const width = Math.ceil(probe.getBoundingClientRect().width);
        panelNode().style.setProperty('--zanju-crt-figures-width', width + 'px');
    }).observe(probe);
}

// The client's own views that follow their content do it this way: a ResizeObserver on the root,
// which calls back after each layout that changes its size, and the view resized from there. A new
// render, a new interface scale and a late first layout all reach it. Waiting frames after a
// render, as card_host.js does, missed the first layout of a new window: on 25 October 2026 the
// panel first measured 300x22, its padding without its one row, and kept that height until the
// next payload.
function followSize() {
    new ResizeObserver(publishSize).observe(panelNode());
}

function publishSize() {
    const node = panelNode();
    if (!node) {
        return;
    }
    const rect = node.getBoundingClientRect();
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
    const key = width + 'x' + height;
    if (key !== lastSize) {
        lastSize = key;
        command('onSized', { width: width, height: height });
    }
}

// The panel gets mouse events only while the player holds Ctrl, because the battle shows the
// cursor only then. A press of the left button starts a drag, and its release ends it.
function bindDrag() {
    document.addEventListener('mousedown', function (event) {
        if (event.button === 0) {
            dragging = true;
            command('onDrag', { phase: 'start' });
        }
    }, true);
    document.addEventListener('mouseup', function () {
        if (dragging) {
            dragging = false;
            command('onDrag', { phase: 'end' });
        }
    }, true);
}

engine.whenReady
    .then(waitForDomBuilt)
    .then(nextFrame)
    .then(nextFrame)
    .then(function () {
        bindDrag();
        followSize();
        followFigures();
        render();
        engine.on('viewEnv.onDataChanged', render);
        viewEnv.addDataChangedCallback('model', ROOT_RES_ID, true);
        setInterval(function () {
            const node = panelNode();
            if (node && currentPayload) {
                refreshClocks(node, currentPayload);
            }
        }, CLOCK_INTERVAL_MS);
    })
    .catch(function (error) { log('panel startup failed: ' + error); });
