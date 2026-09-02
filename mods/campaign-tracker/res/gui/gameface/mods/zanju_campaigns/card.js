// Campaign card rendering, shared by the injected banners' host document and the standalone
// card window.
//
// The card is pure DOM construction: it is handed one campaign entry plus the label bundle and
// returns nothing. Nothing here reads the document it is building into, which is what lets the
// same code render inside the garage document and inside a window of the mod's own.
//
// See docs/reference/gameface-mod-widgets.md for the renderer's limits that shape this markup,
// in particular that text wraps by flex line rather than by inline flow.

import {
    ACTION_OPEN,
    ACTION_PAUSE,
    ACTION_RESET,
    STAGES,
    actionFor,
    el,
    log,
} from './common.js';

// The notes above the conditions: what is true of this mission before the player reads what it
// asks for.
//
// A warning is one that costs the player battles if they miss it -- the mission is paused, or
// this tank is already spent on it, and either way nothing they play right now counts. Having
// no mission at all is just the state of things, and reading that as a warning would cost the
// warning its meaning.
//
// A list rather than a single note, because the two warnings are separate facts. In this
// client's data they cannot both apply: pause belongs to campaign 2 and the vehicle lock to
// campaign 3. The card does not rely on that.
//
// The stage note is the one piece of good news, and it comes last in every sense. What the
// battles now buy is worth nothing next to a note saying they buy nothing at all, so anything
// already said wins the line.
function cardNotes(entry, labels) {
    const notes = [];
    const state = stateNote(entry, labels);
    if (state) {
        notes.push({ text: state, warning: entry.state === 'paused' });
    }
    if (entry && entry.vehicles && entry.vehicles.currentLocked) {
        notes.push({ text: labels.vehicleLocked, warning: true });
    }
    const stage = stageNote(entry, labels);
    if (!notes.length && stage) {
        notes.push(stage);
    }
    return notes;
}

// What the mission is still worth playing for once its primary objective is settled. Python
// names the stage and the name doubles as the label key, so an unknown one is dropped rather
// than looked up: any other key in `labels` would render as a note that makes no sense here.
function stageNote(entry, labels) {
    if (!entry || STAGES.indexOf(entry.stage) < 0) {
        return null;
    }
    const text = labels[entry.stage];
    return text ? { text: text, good: true } : null;
}

function noteClass(note) {
    const base = 'zanju-ct-note';
    if (note && note.warning) {
        return base + ' zanju-ct-note-warning';
    }
    if (note && note.good) {
        return base + ' zanju-ct-note-good';
    }
    return base;
}

function stateNote(entry, labels) {
    if (entry.state === 'paused') {
        return labels.paused;
    }
    if (entry.state !== 'active') {
        return labels.noMission;
    }
    return '';
}

function conditionCount(condition) {
    // A binary condition ("Survive the battle") carries no useful counter, so only a counted
    // one shows numbers; the tick alone says whether the other kind is done.
    if (!condition.counted) {
        return '';
    }
    return condition.currentText + ' / ' + condition.goalText;
}

// A condition, and under it the extra rule it carries if it carries one. Two levels rather than
// one flex row, the shape the requirement below already uses: the rule belongs to the condition
// and has to sit under it, not beside the tick.
function buildCondition(condition) {
    let className = 'zanju-ct-cond';
    if (condition.done) {
        className += ' zanju-ct-cond-done';
    } else if (condition.failed) {
        className += ' zanju-ct-cond-failed';
    }
    const block = el('div', className);

    const row = el('div', 'zanju-ct-cond-line');
    row.appendChild(el('div', 'zanju-ct-mark'));
    row.appendChild(el('div', 'zanju-ct-cond-text', condition.text));

    const count = conditionCount(condition);
    if (count) {
        row.appendChild(el('div', 'zanju-ct-cond-count', count));
    }
    block.appendChild(row);

    if (condition.restriction) {
        block.appendChild(buildRestriction(condition));
    }
    return block;
}

// The extra rule, under the condition it gates. The client leads it with a word of its own --
// "Restriction!" -- and colours that word, so the word is carried apart and drawn apart. A
// client that gives no such word leaves the line as the rule alone.
//
// One box per word, laid out as a wrapping flex row. The label and the rule are one paragraph,
// so a rule long enough to wrap has to come back to the left edge under the word that
// introduces it -- and this renderer gives no other way to get that. See `appendWords`.
function buildRestriction(condition) {
    const line = el('div', 'zanju-ct-cond-limit');
    appendWords(line, condition.restrictionLabel, 'zanju-ct-cond-limit-label');
    appendWords(line, condition.restriction, 'zanju-ct-cond-limit-text');
    return line;
}

// One box per word, because this renderer wraps flex lines and not text: a sentence in a single
// box is one column, and every line after the first would hang under it rather than under the
// coloured word beside it. This is the game's own answer, not a way around it -- its
// formatted-text component splits on spaces the same way. See the reference doc.
//
// The label is split too: it is one word in English and need not be in every language.
function appendWords(line, text, className) {
    const words = String(text || '').split(' ');
    for (let i = 0; i < words.length; i += 1) {
        if (words[i]) {
            line.appendChild(el('div', className, words[i]));
        }
    }
}

// An "or" group needs only one of its conditions met, which changes what the list means: an
// undone row in it is not an outstanding task. The client marks each member, and consecutive
// members are one group — so the break goes between neighbours that are both marked.
function appendGroup(card, conditions, labels) {
    for (let i = 0; i < conditions.length; i += 1) {
        if (i > 0 && conditions[i].alternative && conditions[i - 1].alternative) {
            card.appendChild(el('div', 'zanju-ct-or', labels.or));
        }
        card.appendChild(buildCondition(conditions[i]));
    }
}

// The requirement over a group of conditions: "complete the primary condition in 3 battles out
// of 5", and how far along that is. Missions without one carry no attempt row at all.
function buildAttempt(attempt) {
    let className = 'zanju-ct-attempt';
    if (attempt.done) {
        className += ' zanju-ct-attempt-done';
    } else if (attempt.failed) {
        className += ' zanju-ct-attempt-failed';
    }
    const row = el('div', className);

    const line = el('div', 'zanju-ct-attempt-line');
    line.appendChild(el('div', 'zanju-ct-attempt-text', attempt.text));
    // An objective with no battle limit carries no numbers: there is nothing to count against.
    if (typeof attempt.goal === 'number') {
        line.appendChild(el('div', 'zanju-ct-attempt-count',
            String(attempt.current) + ' / ' + String(attempt.goal)));
    }
    row.appendChild(line);

    // One mark per allowed battle, in the order they were played, the way the game's own
    // mission card shows it. Only the battle-capped requirements carry these.
    const battles = attempt.battles || [];
    if (battles.length) {
        const strip = el('div', 'zanju-ct-pips');
        for (const battle of battles) {
            strip.appendChild(el('div', 'zanju-ct-pip zanju-ct-pip-' + battle));
        }
        row.appendChild(strip);
    }
    return row;
}

// Campaign 3 asks for some missions to be completed in several different vehicles. A vehicle
// that completes one is locked out of it afterwards, so the list says which tanks are spent
// and the counter says how many are still wanted.
function buildVehicles(vehicles, labels) {
    const block = el('div', 'zanju-ct-vehicles');

    const line = el('div', 'zanju-ct-attempt-line');
    line.appendChild(el('div', 'zanju-ct-attempt-text', vehicles.text));
    line.appendChild(el('div', 'zanju-ct-attempt-count',
        String(vehicles.completed) + ' / ' + String(vehicles.required)));
    block.appendChild(line);

    const locked = vehicles.locked || [];
    if (locked.length) {
        block.appendChild(el('div', 'zanju-ct-locked-label', labels.lockedVehicles));
        // One row each rather than one comma-separated line: the list is read to check whether
        // a particular tank is on it, and a name is easier to find down a column than along a
        // sentence. Each carries the same lock the banner uses, so the two say the same thing.
        for (let i = 0; i < locked.length; i += 1) {
            const row = el('div', 'zanju-ct-locked-row');
            row.appendChild(el('div', 'zanju-ct-locked-icon'));
            row.appendChild(el('div', 'zanju-ct-locked-name', locked[i]));
            block.appendChild(row);
        }
    }
    return block;
}

// Where the running total stands against the average the mission asks for, as a percentage of
// it: 100 is exactly on the average, and the line is green above it and red below. Python
// composes the text so it stays translatable, and decides ahead or behind from the same reading
// the banner is tinted by. This side only tints the line to match.
function buildPace(pace) {
    const state = pace.ahead ? ' zanju-ct-pace-ahead' : ' zanju-ct-pace-behind';
    return el('div', 'zanju-ct-pace' + state, pace.text);
}

function appendAttempt(card, attempts, isMain, paces) {
    const attempt = (attempts || []).filter(function (row) { return Boolean(row.main) === isMain; })[0];
    if (!attempt) {
        return;
    }
    // A one-battle mission has an objective but nothing to say about how long it has: there is
    // no battle budget to describe, and the game says nothing there either. The row still has
    // to exist for the banner to know which objective it counts, so it is skipped here rather
    // than dropped where the banner would miss it.
    if (attempt.text) {
        card.appendChild(buildAttempt(attempt));
    }
    // Each objective carries its own pace: they share the battle allowance but not the total,
    // so the secondary usually asks for a steeper average than the primary.
    const pace = (paces || []).filter(function (row) { return Boolean(row.main) === isMain; })[0];
    if (pace) {
        card.appendChild(buildPace(pace));
    }
}

function appendConditions(card, conditions, labels, attempts, paces) {
    const main = conditions.filter(function (condition) { return condition.main; });
    const additional = conditions.filter(function (condition) { return !condition.main; });

    if (main.length) {
        // The heading only earns its place when there is a second group to tell it apart
        // from. On a mission with no secondary conditions it would label the only list on
        // the card, which says nothing and costs a line.
        if (additional.length) {
            card.appendChild(el('div', 'zanju-ct-group', labels.primaryConditions));
        }
        appendGroup(card, main, labels);
        // After the conditions it governs, not before: the conditions are what the player
        // reads first, and the counter is how those conditions are going.
        appendAttempt(card, attempts, true, paces);
    }
    if (additional.length) {
        // Kept even when it is the only group: "secondary" says these are optional, which is
        // worth knowing whether or not a primary list sits above it. The rule only goes on
        // when there is something above to be divided from.
        const className = 'zanju-ct-group' + (main.length ? ' zanju-ct-group-split' : '');
        card.appendChild(el('div', className, labels.secondaryConditions));
        appendGroup(card, additional, labels);
        appendAttempt(card, attempts, false, paces);
    }
}

// The card heads with the operation the mission belongs to — "Operation Excalibur", since the
// game names each operation after the vehicle it awards — over the mission's own full name.
// Python composes the title so the wording stays translatable; see collector.py.
function cardTitle(entry) {
    return entry.operationTitle || entry.campaign || '';
}

function renderCard(card, entry, labels) {
    card.textContent = '';

    // Everything that describes the mission itself rather than what it asks for: which
    // operation it belongs to, its name, and anything standing in its way. The rule under them
    // is carried by this block, so it stays put whichever of the three are present -- a card
    // with no mission has no subtitle, and most have no note.
    const head = el('div', 'zanju-ct-card-head');
    head.appendChild(el('div', 'zanju-ct-card-title', cardTitle(entry)));
    if (entry.mission) {
        head.appendChild(el('div', 'zanju-ct-card-subtitle', entry.mission));
    }
    const notes = cardNotes(entry, labels);
    for (let i = 0; i < notes.length; i += 1) {
        head.appendChild(el('div', noteClass(notes[i]), notes[i].text));
    }
    card.appendChild(head);

    if (!entry.mission) {
        // This return is what leaves the head alone on the card, so the rule it carries would
        // divide the head from nothing at all. Drop the rule rather than the block: the head
        // is still the head, and every card keeps building it the same way.
        head.className += ' zanju-ct-card-head-alone';
        return;
    }

    // Unguarded, because an empty list appends nothing on its own. A running mission always
    // has a primary condition, so the list is empty only when the progress read failed -- and
    // that already wrote the reason to python.log, which says far more than a card could.
    appendConditions(card, entry.conditions || [], labels, entry.attempts, entry.paces);

    // Last, because it is a rule about which tanks may be used rather than about what to do
    // in a battle. Missions without the requirement carry nothing here.
    if (entry.vehicles) {
        card.appendChild(buildVehicles(entry.vehicles, labels));
    }

    card.appendChild(buildHints(entry, labels));
}

// What a click on this banner does, and what the keys held with it would do instead. The line
// for the keys currently held is lit, so the card answers "what happens if I click now".
//
// Only campaign 2's last operation allows pause and reset -- the client permits them nowhere
// else -- so most banners carry the open line alone. That line still earns its place: a banner
// that opens a screen has no other way of saying so.
function buildHints(entry, labels) {
    const block = el('div', 'zanju-ct-hints');
    block.appendChild(buildHint(ACTION_OPEN, labels.hintOpen));
    if (entry.canPause) {
        // Paused missions offer the way back out, which is the same key.
        block.appendChild(buildHint(ACTION_PAUSE,
            entry.state === 'paused' ? labels.hintResume : labels.hintPause));
    }
    if (entry.canReset) {
        block.appendChild(buildHint(ACTION_RESET, labels.hintReset));
    }
    return block;
}

function buildHint(action, text) {
    const row = el('div', 'zanju-ct-hint', text);
    // Read back by applyHints, which lights the row matching the keys held right now.
    row._zanjuCtAction = action;
    return row;
}

// Light the hint line for the action the held keys ask for, and dim the rest. Called on every
// key change and after every render, so an open card always describes the click about to
// happen. Class names are edited as strings because this renderer has no classList.
// Light the hint line matching the keys held right now. The entry is passed in rather than read
// back off a wrapper element: this card is the whole document, so there is no banner above it to
// walk up to.
function applyHints(root, keys, entry) {
    if (!root) {
        return;
    }
    const wanted = actionFor(keys, entry);
    const rows = root.querySelectorAll('.zanju-ct-hint');
    for (let i = 0; i < rows.length; i += 1) {
        const row = rows[i];
        const lit = row._zanjuCtAction === wanted;
        row.className = lit ? 'zanju-ct-hint zanju-ct-hint-active' : 'zanju-ct-hint';
    }
}

export {
    appendAttempt,
    appendConditions,
    appendGroup,
    appendWords,
    applyHints,
    buildAttempt,
    buildCondition,
    buildHint,
    buildHints,
    buildPace,
    buildRestriction,
    buildVehicles,
    cardNotes,
    cardTitle,
    conditionCount,
    noteClass,
    renderCard,
    stageNote,
    stateNote,
};
