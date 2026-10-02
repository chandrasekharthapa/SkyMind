const BaseProvider = require('./BaseProvider');
const { parseStops, parseDurationLine, parseDayOffset } = require('./cardParsing');

function envMs(name, fallback) {
    const value = Number.parseInt(process.env[name] || '', 10);
    return Number.isFinite(value) && value > 0 ? value : fallback;
}

// The same test the extraction below applies to a card: an <li> showing a fare
// and a duration.
function countFareCards() {
    let n = 0;
    for (const item of document.querySelectorAll('li')) {
        const text = item.innerText || '';
        if ((text.includes('₹') || text.includes('$')) && text.includes('hr')) n++;
    }
    return n;
}

// Waits until fare cards appear, then until their number stops growing (Google
// renders results in batches). If none appear in time it returns anyway and
// the extraction reports zero cards, which the caller already treats as "no
// results" — better than throwing away a page that may be half-rendered.
async function waitForFareCards(page) {
    const appearTimeout = envMs('GFLIGHTS_RESULTS_TIMEOUT_MS', 30000);
    try {
        await page.waitForFunction(countFareCards, { timeout: appearTimeout, polling: 500 });
    } catch (error) {
        console.error(`No fare cards appeared within ${appearTimeout} ms; extracting whatever rendered.`);
        return;
    }
    const settleDeadline = Date.now() + envMs('GFLIGHTS_SETTLE_MAX_MS', 8000);
    let last = -1;
    let stableFor = 0;
    while (Date.now() < settleDeadline && stableFor < 3) {
        const count = await page.evaluate(countFareCards);
        stableFor = count === last ? stableFor + 1 : 0;
        last = count;
        await new Promise((resolve) => setTimeout(resolve, 500));
    }
}

class GoogleFlightsProvider extends BaseProvider {
    constructor() {
        super();
        this.name = 'GoogleFlights';
        this.baseUrl = 'https://www.google.com/travel/flights';
    }

    async searchFlights(
        from,
        to,
        departDate,
        returnDate = null,
        passengers = { adults: 1, children: 0, infants: 0 },
        cabinClass = "economy"
    ) {
        let browser, page;
        const counts = typeof passengers === 'number'
            ? { adults: passengers, children: 0, infants: 0 }
            : passengers;
        const adults = counts.adults || 1;
        const children = counts.children || 0;
        const infants = counts.infants || 0;

        try {
            console.error('Launching browser for Google Flights...');
            const initRes = await this.initBrowser();
            browser = initRes.browser;
            page = initRes.page;
            
            let queryStr = `Flights to ${to} from ${from} on ${departDate}`;
            if (adults > 1) queryStr += ` for ${adults} adults`;
            if (children > 0) queryStr += ` ${children} children`;
            if (infants > 0) queryStr += ` ${infants} infants`;
            if (cabinClass && cabinClass.toLowerCase() !== "economy") queryStr += ` in ${cabinClass.replace('_', ' ')} class`;
            if (returnDate) queryStr += ` through ${returnDate}`;
            else queryStr += ` oneway`;
            
            // Ask Google for rupees explicitly. Without `curr`/`gl`/`hl`, Google
            // quotes in the currency it infers from the caller's IP: on a US-hosted
            // runner (GitHub Actions) every fare came back in USD, and the ingest
            // currency screen then refused 100% of observations as foreign currency
            // ("Refused 50 of 50 ... Currencies seen: {'USD': 50}"). Requesting the
            // unit at the source keeps the fare AUTHENTIC — the alternative, an
            // FX_USD_INR rate, reintroduces the unsourced constant that `_fx_rate`
            // was written to eliminate. If Google ignores these and still quotes
            // USD, the screen refuses the batch exactly as before: this can cost
            // rows, it can never store a wrong number.
            const url = `https://www.google.com/travel/flights?q=${encodeURIComponent(queryStr)}&curr=INR&gl=IN&hl=en-IN`;

            console.error(`Navigating to ` + url);
            // Wait for the fare cards themselves, not for the network to go quiet.
            // `networkidle2` needs 500 ms with at most two open connections, and
            // Google Flights keeps polling in the background: on Render's
            // fractional CPU the page never got there and every search died with
            // "Navigation timeout of 60000 ms exceeded" even though the results
            // had rendered. `domcontentloaded` returns as soon as the HTML is in;
            // waitForFareCards then waits for what the parser actually reads.
            await page.goto(url, {
                waitUntil: 'domcontentloaded',
                timeout: envMs('GFLIGHTS_NAV_TIMEOUT_MS', 40000)
            });
            await waitForFareCards(page);
            
            console.error('Extracting flight information...');
            const flightsData = await page.evaluate(() => {
                const results = [];
                const items = document.querySelectorAll('li');
                for (const item of items) {
                    const text = item.innerText;
                    if (text && (text.includes('₹') || text.includes('$')) && text.includes('hr')) {
                        results.push({ text: text, html: item.innerHTML });
                    }
                }
                return results;
            });

            console.error(`Found ` + flightsData.length + ` flight cards`);
            
            const flights = [];
            for (const flightItem of flightsData) {
                try {
                    const text = flightItem.text;
                    const html = flightItem.html;
                    const lines = text.split('\n').map(l => l.trim()).filter(l => l);
                    // This guard does two jobs, and only one of them is obvious.
                    //
                    // Obvious job: a card with fewer than 6 lines cannot supply the
                    // positional fields below (lines[0], lines[2]).
                    //
                    // Load-bearing accident: Google renders every flight TWICE - once
                    // as a summary card and once as an expanded detail card - and the
                    // expanded card contains no newlines at all, so it lands here with
                    // exactly 1 line and is dropped. Measured 2026-09-03 on a live
                    // DEL->BOM fetch: 130 cards = 65 expanded (1 line) + 58 nonstop
                    // summaries (10 lines) + 7 one-stop summaries (11 lines, the extra
                    // line being the layover). If Google ever emits a newline inside
                    // the expanded card, this filter stops halving the list and every
                    // flight is counted twice. The explicit de-duplication after this
                    // loop is what actually protects against that; do not rely on this
                    // line for it.
                    if (lines.length < 6) continue;
                    
                    const departureTimeStr = lines[0];
                    const arrivalTimeStr = lines[2];

                    // Returns null when the card text does not contain a time.
                    //
                    // This used to `return date + "T00:00:00"`, so a card whose
                    // first line was not a clock time produced a flight departing
                    // at midnight. `departure_time` is persisted and is the source
                    // of the `hour_of_day` and `is_peak_hour` features, so those
                    // rows taught the model that unparseable cards depart at 00:00
                    // — and `ingestion_controller` cannot tell a guessed midnight
                    // from a real one, which is precisely what its "anything
                    // unparseable stays None" rule was written to prevent.
                    const formatTime = (timeStr, date) => {
                        const match = timeStr && timeStr.match(/(\d+):(\d+)\s*(AM|PM)/i);
                        if (!match) return null;
                        let [, h, m, ampm] = match;
                        h = parseInt(h);
                        if (ampm.toUpperCase() === 'PM' && h < 12) h += 12;
                        if (ampm.toUpperCase() === 'AM' && h === 12) h = 0;
                        return `${date}T${h.toString().padStart(2, '0')}:${m}:00`;
                    };
                    
                    const departureTime = formatTime(departureTimeStr, departDate);
                    const arrivalTime = formatTime(arrivalTimeStr, departDate);

                    // The price line is *located* by the currency symbol, so the
                    // currency is known exactly when the price is — and it used to be
                    // thrown away here. `replace(/[^0-9.]/g, '')` strips the very
                    // symbol `findIndex` just matched, so a page Google served in
                    // dollars arrived on the Python side as a bare number with no
                    // denomination, where two separate layers read "nobody said" as
                    // "rupees": `flight_data_service`'s FX loop
                    // (`(f.get("currency") or "INR").upper()`) and `format_payload`'s
                    // `currency: str = "INR"` default. The 156 rows stored on
                    // 2026-07-19 at Rs 58 - Rs 105 are US dollars. Capture the symbol
                    // instead of discarding it; see AUDIT-FIXES.md §48.
                    //
                    // '₹' is tested first because `findIndex` tests it first: a line
                    // carrying both symbols is a rupee line with a dollar figure
                    // somewhere in it, not the reverse. No price line means no
                    // currency — null, never a default.
                    const priceIndex = lines.findIndex(l => l.includes('₹') || l.includes('$'));
                    const priceStr = priceIndex >= 0 ? lines[priceIndex] : null;
                    const currency = priceStr
                        ? (priceStr.includes('₹') ? 'INR' : 'USD')
                        : null;
                    const basePrice = priceStr ? parseFloat(priceStr.replace(/[^0-9.]/g, '')) : 0;

                    
                    // The airline could be any line in the text or hidden in HTML
                    let airline = "Unknown";
                    const known = ['IndiGo', 'SpiceJet', 'Air India Express', 'Air India', 'Akasa Air', 'Vistara', 'Alliance Air', 'Emirates', 'Qatar Airways', 'British Airways', 'Singapore Airlines', 'Lufthansa'];
                    for (let i = 0; i < lines.length; i++) {
                        for (const k of known) {
                            if (lines[i].includes(k)) {
                                airline = k;
                                break;
                            }
                        }
                        if (airline !== "Unknown") break;
                    }
                    
                    // Fallback to searching the HTML for aria-labels or alt text
                    if (airline === "Unknown" && html) {
                        for (const k of known) {
                            if (html.includes(k)) {
                                airline = k;
                                break;
                            }
                        }
                    }

                    // Stops and duration: see cardParsing.js. `stops` used to
                    // initialise to 0, so a card with no stops line was reported as
                    // non-stop; absence is null. And the zero-stop check matched only
                    // the US "Nonstop", not the "Non-stop" an en-IN page shows.
                    const stops = parseStops(lines);
                    const duration = parseDurationLine(lines);
                    
                    // Flight number: Google Flights does not publish one on this
                    // page, so there is nothing to extract and this is null by
                    // measurement, not by omission.
                    //
                    // Measured 2026-09-03 on a live DEL->BOM fetch for 2026-09-24:
                    // 130 cards, 65 flights, zero occurrences of any carrier-coded
                    // number (/\b(6E|SG|IX|AI|QP|UK|9I|EK|QR|BA|SQ|LH)[- ]?\d{2,4}\b/)
                    // anywhere in the page text. A 2026-07-19 capture of DEL->BBI
                    // agrees. The datum is not on the page.
                    //
                    // What used to be here was a fabricator:
                    //     const flNumPattern = /\b([A-Z0-9]{2})[- ]?(\d{3,4})\b/;
                    //     if (m && known.some(k => l.includes(k) || airline !== "Unknown"))
                    // It never matched a flight number because there are none. On the
                    // expanded detail cards it matched the departure day glued to the
                    // carbon figure - "Sep 24" + "117 kg CO2e" -> "24117" - and would
                    // have emitted that on 41 of those 65 cards. Its guard could not
                    // stop it: the second disjunct ignores `k`, so `some()` is true for
                    // every line once the airline is identified. The only reason no
                    // fabricated number ever reached the database is the unrelated
                    // `lines.length < 6` filter below, which happens to skip those
                    // cards. Do not restore this loop; there is nothing to select.
                    const flightNumber = null;

                    // Overnight flights: an arrival clock time at or before the
                    // departure clock time means the next calendar day.
                    //
                    // Two defects here. `new Date(null)` is the epoch, not an
                    // invalid date, so once formatTime is allowed to return null
                    // the old comparison read 0 <= 0 as "overnight" and published
                    // an arrival of 1970-01-02. And `.toISOString()` re-emitted the
                    // timestamp in UTC while `departureTime` stayed naive local, so
                    // on an IST machine a successfully adjusted arrival came back
                    // 5h30m earlier than the wall clock it was scraped from. The
                    // day is now added to the date half of the string, which keeps
                    // both fields in the one naive-local convention the Python side
                    // parses.
                    //
                    // The card's own "+1"/"+2" marker wins when present: a connection
                    // landing the next day at a later clock time than it left would
                    // otherwise pass the clock test as a same-day arrival.
                    let finalArrivalTime = arrivalTime;
                    if (departureTime && arrivalTime) {
                        const depClock = departureTime.slice(11);
                        const arrClock = arrivalTime.slice(11);
                        const stated = parseDayOffset(lines);
                        const offset = stated !== null ? stated : (arrClock <= depClock ? 1 : 0);
                        if (offset > 0) {
                            const nextDay = new Date(`${arrivalTime.slice(0, 10)}T00:00:00Z`);
                            nextDay.setUTCDate(nextDay.getUTCDate() + offset);
                            finalArrivalTime =
                                `${nextDay.toISOString().slice(0, 10)}T${arrClock}`;
                        }
                    }

                    flights.push({
                        departureTime: departureTime,
                        arrivalTime: finalArrivalTime,
                        airline: airline,
                        flightNumber: flightNumber || '',
                        basePrice: basePrice,
                        // Emitted next to the price it belongs to, because a fare
                        // without its unit is not a fare. Null when no price line was
                        // found, which the Python write path refuses rather than
                        // labelling INR.
                        currency: currency,
                        duration: duration,
                        stops: stops
                    });
                } catch (err) {
                    console.error("Failed to parse flight text:", err);
                }
            }

            // De-duplicate on the identity the database keys observations by.
            //
            // Google lists some flights more than once - the same departure can
            // appear under a "Best" heading and again in the full list. Measured
            // 2026-09-03 on a live DEL->BOM fetch: 65 parsed cards contained one
            // exact repeat (Air India 21:00 -> 23:20, Rs 6,950, 140 min, nonstop),
            // identical in every field. Left in, each collection run writes two
            // observations for that flight at the same recorded_at, which
            // double-weights it in the booking curve and inflates the row count.
            //
            // Keyed on the fields that survive extraction. flightNumber is
            // deliberately absent - Google does not publish one, so including it
            // would add a constant to every key and de-duplicate nothing.
            const seen = new Set();
            const deduped = [];
            for (const f of flights) {
                const key = [f.airline, f.departureTime, f.arrivalTime,
                             f.basePrice, f.stops].join('|');
                if (seen.has(key)) continue;
                seen.add(key);
                deduped.push(f);
            }
            if (deduped.length !== flights.length) {
                console.error(`Dropped ` + (flights.length - deduped.length) +
                    ` duplicate card(s) listing a flight already captured`);
            }

            console.error(`Successfully parsed ` + deduped.length + ` flights`);

            if (this.debug) {
                console.error('Debug mode: keeping browser open for inspection');
                await page.waitForTimeout(30000);
            }

            return deduped;
            
        } catch (error) {
            return await this.handleError(error, page);
        } finally {
            await this.closeBrowser(browser, page);
        }
    }

    async getOffers() {
        return [];
    }
}

module.exports = GoogleFlightsProvider;
