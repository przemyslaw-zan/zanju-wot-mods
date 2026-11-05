// The battle panel of the Crucible: the conditions of the current mission and their progress.
//
// Python sends the whole panel as one payload (see battle_session.py): the series, the client
// text of each condition, and for each condition that the panel can count, the figures, the
// state and the time limit. This module only draws it. battle_panel.js runs the window.
//
// The payload says if the panel shows its full information (see show_full in battle_panel.py).
// Without it, the panel has no head, and a condition that the panel counts shows its icon, bar
// and figures on one line, with no text. A condition with nothing to count keeps its text, the
// only thing it has to show.
//
// The payload also gives the style of the progress and the figures to show (see config.py). The
// round style draws a dial for each condition, with the time limit on top, the figures below and
// the text on the right. A condition with nothing to count has an empty ring and no figures.
// Without the full information, the round style shows no text at all.

import { SHIELD_IMAGE, clientImage, conditionImage, el, fill, serverNow, startsSet } from './common.js';

const STATE_CLASSES = {
    met: ' zanju-crt-prow-met',
    closed: ' zanju-crt-prow-closed',
};
// The part of the circle that a dial draws: three quarters, with the bottom quarter cut out.
const DIAL_SHARE = 0.75;
// A time limit that runs has the warning color from this number on the clock: 1:00 and less.
const CLOCK_WARNING_SECONDS = 60;

function two(n) {
    return n < 10 ? '0' + n : '' + n;
}

// The time left of a time limit, as M:SS. Rounded down, as the battle clock of the client is, so
// both clocks change on the same second.
function formatClock(seconds) {
    const total = Math.max(0, Math.floor(seconds));
    return Math.floor(total / 60) + ':' + two(total % 60);
}

function icon(className, resource) {
    const node = el('div', className);
    if (resource) {
        node.style.backgroundImage = clientImage(resource);
    }
    return node;
}

function buildHead(payload) {
    const series = payload.series || {};
    const labels = payload.labels || {};
    const head = el('div', 'zanju-crt-panel-head' + (payload.done ? ' zanju-crt-panel-done' : ''));
    // A payload with no shield count shows no shield, rather than an empty or a wrong count. The
    // shields left stand out of all shields, as on the garage banner. A payload without the number
    // of all shields shows the shields left alone.
    if (typeof series.shields === 'number') {
        const limit = series.shieldsLimit > 0 ? '/' + String(series.shieldsLimit) : '';
        head.appendChild(icon('zanju-crt-panel-shield', SHIELD_IMAGE));
        head.appendChild(el('div', 'zanju-crt-panel-shields', String(series.shields) + limit));
    }
    head.appendChild(el('div', 'zanju-crt-panel-name', series.name || ''));
    if (series.stage && series.total) {
        head.appendChild(el('div', 'zanju-crt-panel-stage',
            fill(labels.mission, { stage: series.stage, total: series.total })));
    }
    return head;
}

function ratioOf(row) {
    return Math.max(0, Math.min(1, Number(row.ratio) || 0));
}

function stateClass(row) {
    return row.live ? (STATE_CLASSES[row.state] || '') : '';
}

// The figures of a condition: the current value and, if the setting asks for it, the required
// value. The value keeps counting past the required value.
function buildFigures(row, options) {
    const value = row.valueText || '0';
    if (!options.target) {
        return el('div', 'zanju-crt-prow-figures', value);
    }
    const target = row.targetText || '';
    if (!options.round) {
        return el('div', 'zanju-crt-prow-figures', value + ' / ' + target);
    }
    // Under a dial, the cells keep the slash on the axis of the circle, whatever the value is.
    const figures = el('div', 'zanju-crt-prow-figures zanju-crt-prow-figures-cells');
    figures.appendChild(el('div', 'zanju-crt-prow-figures-value', value));
    figures.appendChild(el('div', 'zanju-crt-prow-figures-slash', '/'));
    figures.appendChild(el('div', 'zanju-crt-prow-figures-target', target));
    return figures;
}

function buildClock(row, rowNode) {
    const clock = el('div', 'zanju-crt-prow-clock');
    clock._zanjuDeadline = row.deadline || null;
    clock._zanjuLimit = row.timeLimit;
    // Only a counted condition can close: with no figures, nobody knows if it was met.
    clock._zanjuCloses = Boolean(row.live) && row.state !== 'met';
    clock._zanjuRow = rowNode;
    return clock;
}

// The bar and the figures of a condition that the panel counts, and the clock of a time limit.
// After a reconnect, a row has no figures, but its time limit still counts down. `lead` is the
// icon of the condition, at the start of the line when the row has no text. A row with no time
// limit keeps an empty clock column when another row has a time limit, so all bars end together.
function buildMeter(row, lead, options, rowNode) {
    const meter = el('div', 'zanju-crt-prow-meter' + (lead ? ' zanju-crt-prow-meter-bare' : ''));
    if (lead) {
        meter.appendChild(lead);
    }
    if (row.live) {
        const bar = el('div', 'zanju-crt-prow-bar');
        const level = el('div', 'zanju-crt-prow-fill');
        level.style.width = (ratioOf(row) * 100).toFixed(1) + '%';
        bar.appendChild(level);
        meter.appendChild(bar);
        meter.appendChild(buildFigures(row, options));
    } else {
        // The space of the missing bar keeps the clock in the clock column.
        meter.appendChild(el('div', 'zanju-crt-prow-gap'));
    }
    if (row.timeLimit) {
        meter.appendChild(buildClock(row, rowNode));
    } else if (options.clockColumn) {
        meter.appendChild(el('div', 'zanju-crt-prow-noclock'));
    }
    return meter;
}

// The round form of the progress: the time limit, the dial with the icon of the condition in its
// middle, and the figures. A condition with nothing to count has only the empty ring: a dial at 0
// of 1, with no figures to say so.
function buildGauge(row, options, rowNode) {
    const gauge = el('div', 'zanju-crt-gauge');
    if (row.timeLimit) {
        gauge.appendChild(buildClock(row, rowNode));
    }
    const dial = el('div', 'zanju-crt-dial');
    dial.appendChild(el('div', 'zanju-crt-dial-track'));
    if (row.live) {
        // A stop of the gradient in battle.css reads this, as the arc of the client's pet screen does.
        dial.style.setProperty('--zanju-crt-arc', (ratioOf(row) * DIAL_SHARE * 100).toFixed(1) + '%');
        dial.appendChild(el('div', 'zanju-crt-dial-fill'));
    }
    dial.appendChild(icon('zanju-crt-dial-icon', row.icon ? conditionImage(row.icon) : ''));
    gauge.appendChild(dial);
    if (row.live) {
        gauge.appendChild(buildFigures(row, options));
    }
    return gauge;
}

// A rule of the condition that the figures cannot show, such as "no direct shot on an ally" of
// High Caliber, above the figures. Red once the rule is broken.
function buildRule(rule, labels) {
    return el('div', 'zanju-crt-prow-rule' + (rule.broken ? ' zanju-crt-prow-rule-broken' : ''),
        labels[rule.key] || '');
}

function appendRules(parent, row, labels) {
    const rules = row.rules || [];
    for (let i = 0; i < rules.length; i += 1) {
        parent.appendChild(buildRule(rules[i], labels || {}));
    }
}

function buildRoundRow(row, labels, options) {
    const node = el('div', 'zanju-crt-prow zanju-crt-prow-round' + stateClass(row));
    node.appendChild(buildGauge(row, options, node));
    if (options.full) {
        const side = el('div', 'zanju-crt-prow-side');
        side.appendChild(el('div', 'zanju-crt-prow-text', row.text || ''));
        appendRules(side, row, labels);
        node.appendChild(side);
    }
    return node;
}

function buildRow(row, labels, options) {
    if (options.round) {
        return buildRoundRow(row, labels, options);
    }
    const node = el('div', 'zanju-crt-prow' + stateClass(row));
    const rowIcon = icon('zanju-crt-prow-icon', row.icon ? conditionImage(row.icon) : '');
    if (!options.full && row.live) {
        node.appendChild(buildMeter(row, rowIcon, options, node));
        return node;
    }
    const line = el('div', 'zanju-crt-prow-line');
    line.appendChild(rowIcon);
    line.appendChild(el('div', 'zanju-crt-prow-text', row.text || ''));
    node.appendChild(line);
    appendRules(node, row, labels);
    if (row.live || row.timeLimit) {
        node.appendChild(buildMeter(row, null, options, node));
    }
    return node;
}

function panelOptions(payload) {
    const round = payload.style === 'round';
    const rows = payload.rows || [];
    return {
        // A payload from before the setting has no `full`, and shows everything, as it did then.
        full: payload.full !== false,
        round: round,
        target: payload.figures !== 'value',
        clockColumn: !round && rows.some(function (row) { return Boolean(row.timeLimit); }),
    };
}

function panelClass(options) {
    let name = 'zanju-crt-panel';
    if (!options.target) {
        name += ' zanju-crt-panel-value';
    }
    if (options.round) {
        name += ' zanju-crt-panel-round';
        if (!options.full) {
            name += ' zanju-crt-panel-dials';
        }
    }
    return name;
}

// The text that gives the dials their width, for the probe of battle_panel.js: the longest figure
// of the panel, with 8 for each digit, because no digit of the client's fonts is wider. It stands on
// both sides of the slash, as the cells of a dial are equal. The text stays the same while the panel
// counts, until a value has more digits than the required value.
function widestFigures(payload) {
    const rows = (payload && payload.rows) || [];
    let longest = '';
    for (let i = 0; i < rows.length; i += 1) {
        if (rows[i].live) {
            [rows[i].valueText || '', rows[i].targetText || ''].forEach(function (text) {
                longest = text.length > longest.length ? text : longest;
            });
        }
    }
    if (!longest) {
        return '';
    }
    const digits = longest.replace(/\d/g, '8');
    return payload.figures === 'value' ? digits : digits + ' / ' + digits;
}

function renderPanel(node, payload) {
    while (node.firstChild) {
        node.removeChild(node.firstChild);
    }
    if (!payload) {
        return;
    }
    const options = panelOptions(payload);
    node.className = panelClass(options);
    if (options.full) {
        node.appendChild(buildHead(payload));
    }
    const rows = payload.rows || [];
    const list = el('div', 'zanju-crt-panel-rows' + (options.full ? '' : ' zanju-crt-panel-rows-bare'));
    // The separators follow the sets, as on the hover card.
    const mission = { group: payload.group, rows: rows };
    for (let i = 0; i < rows.length; i += 1) {
        if (startsSet(mission, i)) {
            list.appendChild(el('div', 'zanju-crt-panel-or', (payload.labels || {}).or || ''));
        }
        list.appendChild(buildRow(rows[i], payload.labels, options));
    }
    node.appendChild(list);
    refreshClocks(node, payload);
}

// Rewrite each time limit from the clock. Before the battle starts, the limit has no deadline yet
// and shows its whole length. A limit that runs out before its condition is met closes the row,
// a second before Python has a reason to say so.
function refreshClocks(node, payload) {
    const clocks = node.querySelectorAll('.zanju-crt-prow-clock');
    const now = serverNow(payload);
    for (let i = 0; i < clocks.length; i += 1) {
        const clock = clocks[i];
        const left = clock._zanjuDeadline ? clock._zanjuDeadline - now : clock._zanjuLimit;
        clock.textContent = formatClock(left);
        const warning = clock._zanjuDeadline && Math.floor(left) <= CLOCK_WARNING_SECONDS;
        clock.className = 'zanju-crt-prow-clock' + (warning ? ' zanju-crt-prow-clock-warning' : '');
        if (clock._zanjuDeadline && left <= 0 && clock._zanjuCloses) {
            const row = clock._zanjuRow;
            if (row && row.className.indexOf('zanju-crt-prow-closed') < 0) {
                row.className += STATE_CLASSES.closed;
            }
        }
    }
}

export { formatClock, refreshClocks, renderPanel, widestFigures };
