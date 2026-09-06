# India Flight Search MCP Server

One provider, three entry points. This server relays flight cards scraped from
Google Flights. SkyMind's backend uses exactly one of the entry points below.

## What it searches

Google Flights, and nothing else: `src/providers/GoogleFlightsProvider.js` drives
Puppeteer over `https://www.google.com/travel/flights`.

Six other providers were once named here. Five of them — Cleartrip, EaseMyTrip,
Yatra, Goibibo, HappyFares — were listed as "coming soon" and were `require`d by
`FlightAggregator.js` despite never having been written, so that `require` threw
`MODULE_NOT_FOUND` and every module downstream of the aggregator failed to load,
including the one `npm start` runs. The sixth, `MakeMyTripProvider.js`, was
written and did exist, but it was imported by nothing and had never returned a
flight: its search drove a form whose widget does not render into the DOM, and
the results URL that needs no form returns a six-character body. That was
measured on 2026-09-03 and the file was deleted the same day, along with its
captured debug HTML and screenshots — see §42 and §44 of `../../AUDIT-FIXES.md`.
The aggregator now requires only the provider that exists, and Google Flights is
the only source of a fare in this package.

Bank offers and deals are not implemented: `GoogleFlightsProvider.getOffers()`
returns `[]`. `BaseProvider.calculateBestPrice` does contain offer logic, but with
no offers to iterate it returns `bestPrice === basePrice`, so nothing SkyMind
calls reaches it.

## Entry points

| File | Transport | Used by SkyMind |
| :--- | :--- | :--- |
| `src/mcp/stdio_server.js` | JSON-RPC over stdin/stdout; one tool, `search_flights` | **Yes** — spawned as a child process by `backend/services/mcp_client.py` |
| `src/mcp/server.js` | HTTP `POST /mcp/invoke`, `GET /mcp/discover`, port 3000 | No |
| `src/server.js` | HTTP `POST /api/search-flights`, port 3000 | No |

`npm start` runs `src/mcp/server.js`, which the backend never contacts. The two
HTTP servers go through `FlightAggregator`; the stdio server requires
`GoogleFlightsProvider` directly.

## Missing values are null

The card mapping in `stdio_server.js` used to substitute constants for anything it
could not read: an unrecognised carrier became IndiGo / `6E`, an unparseable
duration became exactly 135 minutes, an unparseable clock time became midnight,
and a card with no stops line was reported nonstop. Those values were persisted to
`price_history` and trained on, indistinguishable from observed ones.

Each of them is now `null`. `backend/services/flight_normalizer.py` decides how
absence is rendered; it does not refill it.

## Prerequisites

- Node.js 18 or higher (checked against v22)
- A Chrome or Chromium binary Puppeteer can launch. The path is read from
  `PUPPETEER_EXECUTABLE_PATH` and falls back to Puppeteer's own download, so no
  machine-specific path is hardcoded.

## Install

```bash
npm install
```

To exercise the tool the backend actually calls, without the backend:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | node src/mcp/stdio_server.js
```

## Adding a provider

1. Create the class in `src/providers/`, extending `BaseProvider`.
2. Implement `searchFlights(from, to, departDate, returnDate)`. Implement
   `getOffers()` only if the site has offers you are really parsing — returning
   `[]` from it is what makes the offers feature above untrue.
3. `require` it in `FlightAggregator.js`.

Do not add a name to any list in this file before the file exists and is required
somewhere. That is how five providers came to be documented and zero of them
existed.

## License

MIT
