'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { parseStops, parseDurationLine } = require('../src/providers/cardParsing');

test('zero stops in every spelling Google uses', () => {
    for (const label of ['Nonstop', 'Non-stop', 'non stop', 'NON-STOP']) {
        assert.strictEqual(parseStops(['6:10 AM', '8:25 AM', 'IndiGo', '2 hr 15 min', label, '₹4,321']), 0, label);
    }
});

test('counted stops', () => {
    assert.strictEqual(parseStops(['1 stop', 'BLR']), 1);
    assert.strictEqual(parseStops(['2 stops']), 2);
    assert.strictEqual(parseStops(['1 stop in Bengaluru']), 1);
});

test('a line mentioning "stop" without a count does not end the search', () => {
    assert.strictEqual(parseStops(['Stops filter', '1 stop']), 1);
});

test('no stops line means unknown, not non-stop', () => {
    assert.strictEqual(parseStops(['6:10 AM', 'IndiGo', '₹4,321']), null);
    assert.strictEqual(parseStops([]), null);
});

test('duration line', () => {
    assert.strictEqual(parseDurationLine(['IndiGo', '2 hr 15 min', 'Non-stop']), '2 hr 15 min');
    assert.strictEqual(parseDurationLine(['55 min']), '55 min');
    assert.strictEqual(parseDurationLine(['through Mumbai', '1 hr 5 min']), '1 hr 5 min');
    assert.strictEqual(parseDurationLine(['IndiGo']), null);
});
