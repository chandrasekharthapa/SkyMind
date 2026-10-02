'use strict';

/**
 * Pure helpers for reading a Google Flights result card's text lines.
 * Kept out of GoogleFlightsProvider so they can be tested without a browser.
 */

/**
 * The number of stops on a card, or null when the card does not say.
 *
 * Google writes the zero-stop label differently by locale: "Nonstop" in US
 * English, and "Non-stop" in Indian/British English. The search URL has asked
 * for hl=en-IN since 2026-09-30 (so fares come back in rupees), and the old
 * check — includes('nonstop') — matched only the US spelling. It also stopped
 * at the first line containing "stop", parsed or not. Every row stored since the
 * locale change has had stops = NULL, which left the model's direct_ratio /
 * connecting_ratio features empty in training while the live path filled them.
 *
 * Absence stays null: a card with no stops line is unknown, not non-stop.
 */
function parseStops(lines) {
    for (const raw of lines || []) {
        const line = String(raw).toLowerCase();
        // "nonstop", "non-stop", "non stop"
        if (/\bnon[\s-]?stop\b/.test(line)) return 0;
        // "1 stop", "2 stops", "1 stop in BLR"
        const m = line.match(/\b(\d+)\s*stops?\b/);
        if (m) return parseInt(m[1], 10);
    }
    return null;
}

// "2 hr 15 min", "2 hrs 15 mins", "1 hr", "55 min" — the whole duration and
// nothing else. en-IN pages pluralise ("2 hrs 15 mins") where en-US does not.
const DURATION = /^(\d+\s*hrs?(?:\s*\d+\s*mins?)?|\d+\s*mins?)$/i;
// The same shape at the start of a line, e.g. "5 hrs 40 mins DEL–BOM".
const DURATION_PREFIX = /^(\d+\s*hrs?(?:\s*\d+\s*mins?)?|\d+\s*mins?)\b/i;

/**
 * The card's total travel time ("2 hr 15 min", "2 hrs 15 mins", "55 min"), or
 * null.
 *
 * The whole-line match used to accept only the singular "hr"/"min". The en-IN
 * page writes "2 hrs 15 mins", so every flight of two hours or more had no
 * duration (measured on the 2026-10-02 export: 0% coverage at >= 120 min,
 * 100% below). A one-stop card then fell through to a loose "any line with
 * N hr" fallback that picked the LAYOVER line ("1 hr 30 min layover, BOM"),
 * so the duration stored for every connecting flight was its layover.
 *
 * The fallback now accepts only a line that starts with a duration and is not
 * a layover, and returns just the duration part.
 */
function parseDurationLine(lines) {
    for (const raw of lines || []) {
        const line = String(raw).trim();
        if (DURATION.test(line)) return line;
    }
    for (const raw of lines || []) {
        const line = String(raw).trim();
        if (/layover|connect/i.test(line)) continue;
        const m = line.match(DURATION_PREFIX);
        if (m) return m[1];
    }
    return null;
}

/**
 * Days between departure and arrival as the card states it ("11:50 PM+1",
 * or "+1" on its own line right after the arrival time), or null when the card
 * does not say. Without it, a connection that lands the next day at a later
 * clock time than it left (dep 08:15, arr 09:10 next day) was stored as a
 * 55-minute trip.
 */
function parseDayOffset(lines, arrivalIndex = 2) {
    const arrival = String((lines || [])[arrivalIndex] || '');
    let m = arrival.match(/\+\s*(\d)\b/);
    if (m) return parseInt(m[1], 10);
    const next = String((lines || [])[arrivalIndex + 1] || '').trim();
    m = next.match(/^\+\s*(\d)$/);
    if (m) return parseInt(m[1], 10);
    return null;
}

module.exports = { parseStops, parseDurationLine, parseDayOffset };
