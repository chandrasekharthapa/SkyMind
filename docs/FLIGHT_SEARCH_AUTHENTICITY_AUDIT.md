# SkyMind — Flight Search Authenticity & Data Realism Audit

**Status: re-checked against the source on 2026-09-02.** This audit was written
against the pre-fix code. It is kept because its findings are the reason the
current code looks the way it does, but every claim has been re-verified and the
ones that were wrong when written are corrected in place rather than preserved.
Each finding is marked FIXED, with the location, or OPEN, with what remains.

## 1. Executive summary

Search results read as synthetic because **absent schedule metadata was filled
with constants**. When a scraped card could not be parsed, or when results were
served from the `price_history` cache, the code substituted a 12:00 departure, a
14:15 arrival, a 2 h 15 m duration, flight number `6E1000`, carrier `6E`/IndiGo,
and `stops = 0`. Several results on one route therefore rendered as the same
flight, and — the part that mattered more than the display — those values were
persisted and trained on, indistinguishable from observed ones.

**FIXED, on both sides of the boundary.** Absence is now `None` end to end:

- `backend/services/flight_normalizer.py:86-140` (`normalize_db_flight`) reads each
  schedule field straight off the record and passes `None` through. Every one of
  the five constants is gone, and `NormalizedSegment` declares `flight_number`,
  `departure_time`, `arrival_time`, `duration` and `stops` as `Optional`.
- Three of those constants originated *upstream of Python*, in the scraper layer,
  which no earlier sweep of this repository had read. `backend/india-flight-mcp/
  src/mcp/stdio_server.js` turned an unrecognised carrier into IndiGo/`6E` and an
  unreadable duration into exactly 135 minutes; `src/providers/GoogleFlightsProvider.js`
  turned an unparseable clock time into midnight and a card with no stops line into
  a nonstop. All four now emit `null`.

The consequence to design for: a cached result can legitimately render with no
departure time and no flight number. That is the honest output for a row that
never carried them, and the frontend has to show the absence rather than a
plausible-looking placeholder (§8).

## 2. Data sources

The original table in this section was wrong in three ways, all corrected below:
it named a provider the code has never called, quoted `data_source` strings that
appear nowhere in the source, and attached a "Confidence Score" to each row when
the search path publishes no confidence figure at all.

| Component | Source | `data_source` value written | `provenance` label |
| :--- | :--- | :--- | :--- |
| Live search | Google Flights, scraped by Puppeteer and relayed over MCP | `LIVE_GOOGLE_FLIGHTS_MCP` | `REAL_PROVIDER` |
| Cache fallback, quiet route | Supabase `price_history` | `DB_FALLBACK (NO LIVE RESULTS)` | `HISTORICAL_OBSERVATION` |
| Cache fallback, transport broke | Supabase `price_history` | `DB_FALLBACK (PROVIDER ERROR: <kind>)` | `HISTORICAL_OBSERVATION` |

Corrections, each verifiable in one grep:

1. **Provider name.** The transport is `flight_data_service` → `mcp_client` →
   `india-flight-mcp/src/mcp/stdio_server.js` → `GoogleFlightsProvider.js`, which
   navigates `google.com/travel/flights`. It has never been MakeMyTrip.
   `MakeMyTripProvider.js` sat on disk, required by nothing, until it was measured
   dead and deleted on 2026-09-03 (§42/§44 of `../AUDIT-FIXES.md`). The live label
   read `LIVE_MAKEMYTRIP_MCP` and was passed to `format_payload` as `provider`, so
   both provenance columns on every stored row named a provider the code cannot
   call. Renamed at `flight_search_service.py:448` and `scheduler.py:293`. Rows
   written earlier still carry the old string; no query filters on the column.
2. **Fallback labels.** `DB_FALLBACK (ZERO-BIAS CACHE)` and
   `DB_FALLBACK (ERROR RECOVERY)` do not exist anywhere in the source. The two real
   labels distinguish *why* the cache is being read — a quiet route from a broken
   transport — which the old pair inferred from control flow.
3. **Confidence.** `flight_search_service.py` contains the word "confidence" zero
   times, so 95.0% / 75.0% / 60.0% described nothing that runs. Those three figures
   are the shape of the defect that `backend/services/confidence_policy.py` was
   written to remove: a confidence must trace to a metric a training run recorded,
   and the module returns `None` — callers refuse — when it cannot find one.
   Confidence belongs to the prediction and forecast paths, not to search.
4. **TTL.** The 300 s TTL (`MARKET_SNAPSHOT_TTL`) belongs to
   `MarketSnapshotProvider`, which serves the prediction path. The search path does
   not touch it: its only cache is `repository.get_price_history_cache`, a Supabase
   read with no TTL.

Still true, and still the root constraint: `price_history` rows carry price and
timing but not baggage rules, aircraft type or fare conditions, so a fallback
result cannot be as rich as a live one no matter how it is rendered.

## 3. Flight diversity

The five patterns this section originally reported, with current status:

1. **Identical timestamps** — FIXED. `normalize_db_flight` no longer writes
   `{departure_date}T12:00:00` / `T14:15:00`; both fields pass through as `None`.
   Going forward the real value is available: `departure_time` is now captured at
   ingest and normalised to a full timestamp
   (`ingestion_controller.normalize_departure_time`).
2. **Identical durations** — FIXED. `PT2H15M` is gone from the normalizer, and the
   scraper's 135-minute substitute is gone from `stdio_server.js`. Note the
   coincidence that hid it: 135 minutes *is* "2 hr 15 min", so the fabricated value
   was numerically identical to the most common real one.
3. **Default flight numbers** — FIXED in two places. `f"{primary_airline}1000"` is
   gone from the normalizer, and `format_payload` no longer defaults
   `flight_number` to `f"{airline_code}1000"` — which is why the stored corpus has
   a single distinct `flight_number` across 6,328 rows.
4. **Default carrier** — FIXED. An unrecognised carrier is `null` from the scraper
   and `"UNKNOWN"` / `"Unknown Carrier"` after normalization, never `6E`/IndiGo.
5. **Identical stops and cabin** — PARTLY FIXED. `stops` is now `Optional` and
   `null` when the card had no stops line. `cabin` still defaults to `"ECONOMY"`,
   which is defensible: the search request specifies a cabin class and the result is
   a response to it. One gap remains, below.

**OPEN.** `normalize_mcp_flight`'s multi-leg branch still writes `stops=0` on every
segment (`flight_normalizer.py:191`). Per *segment* that is true by definition — a
leg is a nonstop hop — but `NormalizedItinerary` has no itinerary-level stop count,
so a two-leg itinerary read through `segments[0].stops` would render as Direct. The
branch is unreachable from the only wired provider, which returns flat cards with no
`legs` key, so this is latent rather than live. Fixing it means adding a stop count
to the itinerary, not editing the segment.

## 4. Payload and schema

Unchanged from the original audit except where noted:

| Field | In `NormalizedFlight` | In API response | Rendered on the card | Status |
| :--- | :---: | :---: | :---: | :--- |
| `price.total`, `primary_airline`, `flight_number` | Yes | Yes | Yes | Rendered |
| `departure_time`, `arrival_time`, `duration` | Yes | Yes | Yes | Rendered; now nullable |
| `seats_available` | Yes | Yes | Conditional | Hidden until expanded |
| `terminal` | Yes | Ingested | No | Stored, never shown |
| `stops` | Yes | Yes | Yes | Now nullable |
| `baggage_allowance`, `refundable_status`, `aircraft_type` | No | No | No | Not captured |
| `provider_attribution` | Yes | Yes | Partial | Toolbar only |

`departure_time` is the material change since the original audit. It was declared
as a feature source (`hour_of_day`, `is_peak_hour`) and never persisted, so both
features were NaN for 100% of the training corpus while the serving path read the
hour off the live card and supplied it — the largest train/serve skew in the
project. Ingest now captures it. **The column requires
`backend/database/migrations/001_price_history_and_run_metadata.sql` to be applied;
until it is, an insert carrying `departure_time` is rejected by Postgres.**

## 5-6. Frontend and user trust — OPEN

These were product findings, not fabrications, and all but one still stand: one
card template for every result, `seats_available` hidden in the collapsed view, no
live-versus-cached badge per card, no baggage or fare-condition detail, no
last-updated stamp. The one correction: a badge should read "Google Flights", not
MakeMyTrip.

With absent fields now rendering as absent, the badge is no longer cosmetic. A card
showing a price and no departure time needs to say why.

## 7. Root causes

1. **Static default filling in `FlightNormalizer`** — CLOSED. Was
   `flight_normalizer.py:98-106`; that block now passes `None` through.
2. **Schema truncation at ingest** — CLOSED IN CODE, PENDING MIGRATION.
   `get_db_payload` now carries `departure_time`, `duration`, `stops` and `terminal`
   through to the insert; the columns arrive with migration 001. Baggage, aircraft
   type and fare conditions are still not scraped, so they remain uncapturable.
3. **Card template uniformity** — OPEN, `frontend/app/flights/page.tsx`.
4. **NEW: provenance mislabelling** — CLOSED. The live path labelled itself
   `LIVE_MAKEMYTRIP_MCP` and wrote that label into `provider` and `data_source`. A
   provenance column that names the wrong provider is worse than an empty one,
   because it reads as evidence.

## 8. Recommendations

1. ~~Synthesize realistic, spread-out departure times based on flight index.~~
   **REJECTED, and it is the reason this document needed a status pass.** That is a
   recommendation to fabricate the exact field the audit was written to stop
   fabricating: index-based times would have been more convincing than
   `T12:00:00` and no less invented, and they would have been persisted and trained
   on. The correct move is the opposite: render absence. Show the price, the
   carrier, the provenance badge, and an explicit "schedule not recorded" where the
   time would be.
2. **Persist schedule metadata** — DONE in code, pending migration 001. Rows written
   before it stay incomplete; a backfill is impossible, because the values were
   never observed.
3. **Render inventory and provider badges** — OPEN and now higher priority, per §5-6.
4. **NEW: give the itinerary a stop count** so the latent `stops=0` in the multi-leg
   branch cannot become a live "Direct" claim if a provider that returns `legs` is
   ever wired in.
