#!/usr/bin/env node

const readline = require('readline');
const GoogleFlightsProvider = require('../providers/GoogleFlightsProvider');

const gfProvider = new GoogleFlightsProvider();

const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: false
});

rl.on('line', async (line) => {
    try {
        const request = JSON.parse(line);
        await handleRequest(request);
    } catch (e) {
        // ignore malformed lines
    }
});

function send(message) {
    process.stdout.write(JSON.stringify(message) + '\n');
}

async function handleRequest(request) {
    const { jsonrpc, id, method, params } = request;
    if (method === 'initialize') {
        send({
            jsonrpc: '2.0',
            id: id,
            result: {
                protocolVersion: '2024-11-05',
                capabilities: { tools: {} },
                serverInfo: { name: 'india-flight-mcp-server', version: '1.0.0' }
            }
        });
    } else if (method === 'tools/list') {
        send({
            jsonrpc: '2.0',
            id: id,
            result: {
                tools: [{
                    name: 'search_flights',
                    description: 'Search for flights via Google Flights',
                    inputSchema: {
                        type: 'object',
                        properties: {
                            from: { type: 'string', description: 'Origin IATA code' },
                            to: { type: 'string', description: 'Destination IATA code' },
                            departDate: { type: 'string', description: 'Date YYYY-MM-DD' }
                        },
                        required: ['from', 'to', 'departDate']
                    }
                }]
            }
        });
    } else if (method === 'tools/call') {
        const { name, arguments: args } = params;
        if (name === 'search_flights') {
            const origin = args.from || args.origin || 'DEL';
            const destination = args.to || args.destination || 'BOM';
            const date = args.departDate || args.departure_date || args.date || '2026-07-05';
            const adults = args.adults || 1;
            const cabinClass = args.cabin_class || "economy";
            try {
                const rawFlightsResult = await gfProvider.searchFlights(origin, destination, date, null, adults, cabinClass);
                // rawFlightsResult may be an array or an object with a 'data' field
                const rawFlights = Array.isArray(rawFlightsResult) ? rawFlightsResult : (rawFlightsResult && rawFlightsResult.data) || [];
                if (!rawFlights || rawFlights.length === 0) {
                    throw new Error('No live flight results retrieved from Google Flights.');
                }
                const airlineCodes = {
                    'IndiGo': '6E',
                    'SpiceJet': 'SG',
                    'Air India Express': 'IX',
                    'Air India': 'AI',
                    'Akasa Air': 'QP',
                    'Vistara': 'UK',
                    'Alliance Air': '9I',
                    'Emirates': 'EK',
                    'Qatar Airways': 'QR',
                    'British Airways': 'BA',
                    'Singapore Airlines': 'SQ',
                    'Lufthansa': 'LH'
                };
                
                // Nothing here may invent a value the scrape did not produce.
                //
                // `actualAirline` used to read
                //   (f.airline && f.airline !== "Unknown") ? f.airline : "IndiGo"
                // and `code` used to read `airlineCodes[actualAirline] || '6E'`.
                // The Google Flights card markup often carries no carrier name the
                // scraper recognises, and every one of those flights was reported to
                // the user, and written to price_history, as IndiGo/6E. Duration had
                // the same shape: an unparseable duration became exactly 135 minutes.
                //
                // The Python normalizer already handles absence — a missing carrier
                // becomes "UNKNOWN"/"Unknown Carrier" and a missing duration stays
                // None — so emitting null is honest and costs no crash.
                const flights = rawFlights.map((f) => {
                    const known = f.airline && f.airline !== "Unknown" ? f.airline : null;
                    const code = known ? (airlineCodes[known] || null) : null;
                    const durMinutes = f.duration
                        ? (parseInt((f.duration.match(/(\d+)\s*hr/) || [])[1] || 0) * 60
                           + parseInt((f.duration.match(/(\d+)\s*min/) || [])[1] || 0))
                        : null;
                    return {
                    flight_name: known
                        ? `${known}${f.flightNumber ? ' ' + f.flightNumber : ''}`
                        : (f.flightNumber || null),
                    primary_airline: code,
                    airline_name: known,
                    flight_number: f.flightNumber || null,
                    price: f.basePrice,
                    // The denomination travels with the number. Without this key the
                    // Python side receives a bare price and has to assume one, which
                    // is exactly the assumption that stored 156 dollar fares as
                    // rupees on 2026-07-19. `|| null` rather than a default: an
                    // absent currency is refused at ingest, not guessed.
                    currency: f.currency || null,
                    seats: f.seats || null,
                    departure_time: f.departureTime,
                    arrival_time: f.arrivalTime,
                    duration_minutes: durMinutes || null,
                    airline: known,
                    stops: (typeof f.stops === 'number') ? f.stops : null
                };
            });
                send({
                    jsonrpc: '2.0',
                    id: id,
                    result: { content: [{ type: 'text', text: JSON.stringify(flights) }] }
                });
            } catch (err) {
                send({
                    jsonrpc: '2.0',
                    id: id,
                    error: { code: -32000, message: `Crawl Error: ${err.message}` }
                });
            }
        } else {
            send({
                jsonrpc: '2.0',
                id: id,
                error: { code: -32601, message: `Method not found: ${name}` }
            });
        }
    }
}
