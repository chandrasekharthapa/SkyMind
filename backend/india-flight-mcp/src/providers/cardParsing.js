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

/**
 * The card's duration line ("2 hr 15 min", "55 min"), or null.
 * Matched as a duration shape rather than any line containing "hr", which also
 * matches words like "through".
 */
function parseDurationLine(lines) {
    for (const raw of lines || []) {
        const line = String(raw).trim();
        if (/^\d+\s*hr(\s*\d+\s*min)?$/i.test(line) || /^\d+\s*min$/i.test(line)) return line;
    }
    for (const raw of lines || []) {
        const line = String(raw);
        if (/\b\d+\s*hr\b/i.test(line)) return line.trim();
    }
    return null;
}

module.exports = { parseStops, parseDurationLine };
