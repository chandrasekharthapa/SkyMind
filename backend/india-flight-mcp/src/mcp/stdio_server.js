#!/usr/bin/env node

const readline = require('readline');

let gfProvider = null;
const providerModule = process.env.GOOGLE_FLIGHTS_PROVIDER_MODULE;

function getGoogleFlightsProvider() {
    // Loading the Puppeteer provider takes tens of seconds in a cold process.
    // Keep MCP discovery lightweight and load browser code only for an actual
    // flight search. Tests may inject a local provider module through the child
    // process environment; production never sets this variable.
    if (!gfProvider) {
        const GoogleFlightsProvider = require(
            providerModule || '../providers/GoogleFlightsProvider'
        );
        gfProvider = new GoogleFlightsProvider();
    }
    return gfProvider;
}

function setGoogleFlightsProviderForTests(provider) {
    gfProvider = provider;
}

const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: false
});

rl.on('line', async (line) => {
    let request;
    try {
        request = JSON.parse(line);
    } catch (e) {
        sendError(null, -32700, 'Parse error');
        return;
    }

    try {
        await handleRequest(request);
    } catch (e) {
        if (hasRequestId(request)) {
            sendError(request.id, -32600, 'Invalid request');
        }
    }
});

function send(message) {
    process.stdout.write(JSON.stringify(message) + '\n');
}

function hasRequestId(request) {
    return Boolean(
        request
        && typeof request === 'object'
        && !Array.isArray(request)
        && Object.prototype.hasOwnProperty.call(request, 'id')
        && request.id !== null
    );
}

function sendError(id, code, message) {
    send({
        jsonrpc: '2.0',
        id: id ?? null,
        error: { code, message }
    });
}

function validRequestEnvelope(request) {
    return Boolean(
        request
        && typeof request === 'object'
        && !Array.isArray(request)
        && request.jsonrpc === '2.0'
        && typeof request.method === 'string'
    );
}

function parseDate(value) {
    const date = typeof value === 'string' ? value.trim() : '';
    const parsed = /^\d{4}-(\d{2})-(\d{2})$/.exec(date);
    if (!parsed) return null;
    const month = Number(parsed[1]);
    const day = Number(parsed[2]);
    const check = new Date(`${date}T00:00:00Z`);
    if (
        Number.isNaN(check.getTime())
        || check.getUTCMonth() + 1 !== month
        || check.getUTCDate() !== day
    ) {
        return null;
    }
    return date;
}

function requiredSearchArguments(params) {
    if (!params || typeof params !== 'object' || Array.isArray(params)) {
        return null;
    }
    const args = params.arguments;
    if (!args || typeof args !== 'object' || Array.isArray(args)) {
        return null;
    }
    const allowedKeys = new Set([
        'from', 'to', 'departDate', 'returnDate', 'adults', 'children',
        'infants', 'cabin_class', 'max_results'
    ]);
    if (Object.keys(args).some((key) => !allowedKeys.has(key))) {
        return null;
    }

    const origin = typeof args.from === 'string' ? args.from.trim().toUpperCase() : '';
    const destination = typeof args.to === 'string' ? args.to.trim().toUpperCase() : '';
    const departDate = parseDate(args.departDate);
    if (!/^[A-Z]{3}$/.test(origin) || !/^[A-Z]{3}$/.test(destination) || !departDate) {
        return null;
    }

    const returnDate = args.returnDate == null || args.returnDate === ''
        ? null
        : parseDate(args.returnDate);
    if (args.returnDate != null && args.returnDate !== '' && !returnDate) {
        return null;
    }
    if (returnDate && returnDate < departDate) {
        return null;
    }

    const adults = args.adults == null ? 1 : args.adults;
    const children = args.children == null ? 0 : args.children;
    const infants = args.infants == null ? 0 : args.infants;
    if (
        !Number.isInteger(adults) || adults < 1 || adults > 9
        || !Number.isInteger(children) || children < 0 || children > 9
        || !Number.isInteger(infants) || infants < 0 || infants > adults
        || adults + children + infants > 9
    ) {
        return null;
    }

    const cabinClass = typeof args.cabin_class === 'string'
        ? args.cabin_class.trim().toLowerCase()
        : 'economy';
    const cabinClasses = new Set(['economy', 'premium_economy', 'business', 'first']);
    if (!cabinClasses.has(cabinClass)) return null;

    const maxResults = args.max_results == null ? 20 : args.max_results;
    if (!Number.isInteger(maxResults) || maxResults < 1 || maxResults > 50) {
        return null;
    }

    return {
        origin,
        destination,
        departDate,
        returnDate,
        adults,
        children,
        infants,
        cabinClass,
        maxResults
    };
}

function toolSchema() {
    return {
        type: 'object',
        additionalProperties: false,
        properties: {
            from: { type: 'string', pattern: '^[A-Za-z]{3}$', description: 'Origin IATA code' },
            to: { type: 'string', pattern: '^[A-Za-z]{3}$', description: 'Destination IATA code' },
            departDate: { type: 'string', format: 'date', description: 'Departure date YYYY-MM-DD' },
            returnDate: { type: ['string', 'null'], format: 'date', description: 'Optional return date YYYY-MM-DD' },
            adults: { type: 'integer', minimum: 1, maximum: 9, default: 1 },
            children: { type: 'integer', minimum: 0, maximum: 9, default: 0 },
            infants: { type: 'integer', minimum: 0, maximum: 9, default: 0 },
            cabin_class: {
                type: 'string',
                enum: ['economy', 'premium_economy', 'business', 'first'],
                default: 'economy'
            },
            max_results: { type: 'integer', minimum: 1, maximum: 50, default: 20 }
        },
        required: ['from', 'to', 'departDate']
    };
}

async function handleRequest(request) {
    if (!validRequestEnvelope(request)) {
        if (hasRequestId(request)) sendError(request.id, -32600, 'Invalid request');
        return;
    }

    const { id, method, params } = request;
    const notification = !hasRequestId(request);
    if (notification) {
        // JSON-RPC notifications never receive a response. The initialized
        // notification is the only one the current Python client sends, but
        // ignoring unknown notifications is equally required by the protocol.
        return;
    }
    if (!['string', 'number'].includes(typeof id)) {
        sendError(null, -32600, 'Invalid request');
        return;
    }

    if (method === 'initialize') {
        send({
            jsonrpc: '2.0',
            id,
            result: {
                protocolVersion: '2024-11-05',
                capabilities: { tools: {} },
                serverInfo: { name: 'india-flight-mcp-server', version: '1.0.0' }
            }
        });
        return;
    }

    if (method === 'tools/list') {
        send({
            jsonrpc: '2.0',
            id,
            result: {
                tools: [{
                    name: 'search_flights',
                    description: 'Search for flights via Google Flights',
                    inputSchema: toolSchema()
                }]
            }
        });
        return;
    }

    if (method !== 'tools/call') {
        sendError(id, -32601, `Method not found: ${method}`);
        return;
    }

    const name = params && params.name;
    if (name !== 'search_flights') {
        // tools/call is a valid JSON-RPC method. An unknown tool is an
        // application-level MCP error, not a missing JSON-RPC method.
        send({
            jsonrpc: '2.0',
            id,
            result: {
                isError: true,
                content: [{ type: 'text', text: `Tool not found: ${name}` }]
            }
        });
        return;
    }

    const call = requiredSearchArguments(params);
    if (!call) {
        sendError(
            id,
            -32602,
            'Invalid search_flights parameters: use the advertised schema.'
        );
        return;
    }

    const {
        origin,
        destination,
        departDate,
        returnDate,
        adults,
        children,
        infants,
        cabinClass,
        maxResults
    } = call;

    try {
        const rawFlightsResult = await getGoogleFlightsProvider().searchFlights(
            origin,
            destination,
            departDate,
            returnDate,
            { adults, children, infants },
            cabinClass
        );
        if (rawFlightsResult && rawFlightsResult.error) {
            throw new Error(String(rawFlightsResult.error));
        }
        const rawFlights = Array.isArray(rawFlightsResult)
            ? rawFlightsResult
            : (
                rawFlightsResult
                && typeof rawFlightsResult === 'object'
                && Array.isArray(rawFlightsResult.data)
                    ? rawFlightsResult.data
                    : null
            );
        if (rawFlights === null) {
            throw new Error('Provider returned an invalid result');
        }
        const flights = normalizeFlights(rawFlights).slice(0, maxResults);
        send({
            jsonrpc: '2.0',
            id,
            result: { content: [{ type: 'text', text: JSON.stringify(flights) }] }
        });
    } catch (err) {
        // Provider failures are valid tools/call results. JSON-RPC errors are
        // reserved for protocol/request failures and must not conflate a quiet
        // market with a broken transport.
        send({
            jsonrpc: '2.0',
            id,
            result: {
                isError: true,
                content: [{ type: 'text', text: `Crawl Error: ${err.message}` }]
            }
        });
    }
}

function normalizeFlights(rawFlights) {
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

    // Nothing here may invent a value the scrape did not produce. Missing
    // carrier, currency, duration, seats, number, and stops remain null.
    return rawFlights.map((f) => {
        const known = f.airline && f.airline !== 'Unknown' ? f.airline : null;
        const code = known ? (airlineCodes[known] || null) : null;
        const duration = typeof f.duration === 'string' ? f.duration : '';
        const hourMatch = duration.match(/(\d+)\s*hr/);
        const minuteMatch = duration.match(/(\d+)\s*min/);
        const durMinutes = duration && (hourMatch || minuteMatch)
            ? Number(hourMatch ? hourMatch[1] : 0) * 60
                + Number(minuteMatch ? minuteMatch[1] : 0)
            : null;
        return {
            flight_name: known
                ? `${known}${f.flightNumber ? ' ' + f.flightNumber : ''}`
                : (f.flightNumber || null),
            primary_airline: code,
            airline_name: known,
            flight_number: f.flightNumber || null,
            price: f.basePrice,
            currency: f.currency || null,
            seats: f.seats || null,
            departure_time: f.departureTime || null,
            arrival_time: f.arrivalTime || null,
            duration_minutes: durMinutes,
            airline: known,
            stops: typeof f.stops === 'number' ? f.stops : null
        };
    });
}

module.exports = {
    handleRequest,
    normalizeFlights,
    requiredSearchArguments,
    setGoogleFlightsProviderForTests,
    toolSchema
};
