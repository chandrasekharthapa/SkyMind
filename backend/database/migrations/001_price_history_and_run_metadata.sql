-- =====================================================================
-- SkyMind migration 001 — make the database match what the code writes
-- =====================================================================
--
-- STATUS: authored, NOT applied. No statement in this file has been run against
-- any database, live or local. Read it, then run it yourself.
--
-- WHY IT EXISTS
--   `database/skymind_complete.sql` defines `public.price_history` with 16 data
--   columns. The shipped ingest path writes 33: the allow-list in
--   `MarketDataController.get_db_payload` (services/ingestion_controller.py:169)
--   decides the column set, and `HistoricalDataService.insert_observations`
--   (services/historical_data_service.py:17) submits it verbatim. STEP 1 adds
--   exactly the 17-column difference — nothing invented, nothing anticipated.
--   Two whole tables the code writes, `snapshot_metadata` and `forecast_store`,
--   are absent from the schema; STEP 4 and STEP 5 create them from the payloads
--   the writers actually build.
--
-- PROPERTIES
--   Idempotent. Every statement is `IF NOT EXISTS`, a `DROP DEFAULT` (a no-op
--   when there is no default), or an UPDATE whose predicate stops matching once
--   it has run. Re-running the file changes nothing.
--   Additive. Nothing is dropped and no column is narrowed. The two exceptions
--   are in STEP 2 and are argued there.
--   Ordered. STEP 3 depends on STEP 1's columns existing. STEP 8 constrains data
--   rather than shape, so it can fail where the others cannot, and it is last and
--   gated for that reason — though not because of the rows already here; see 8a.
--
-- HOW TO RUN
--   BEFORE ANY STEP: confirm `booking_curve_definition._price_at_offset` gates on
--   `curve_identity_mask` (AUDIT-FIXES.md §45). STEP 1 adds `departure_time` with
--   no backfill, which turns "key column absent" into "key column NULL" on every
--   existing row, and only the §45 statement refuses to label a row in that state.
--   Without it this migration re-opens a cross-flight label leak. See STEP 1.
--
--   Run STEP 0 on its own first and keep the output — it is read-only, and it
--   tells you which of the following steps are no-ops on your database. Then run
--   STEP 1 through STEP 7 as one transaction. STEP 8 is deliberately separate.
--
-- =====================================================================
-- STEP 0 — pre-flight inventory (read-only)
-- =====================================================================

-- 0a. Which columns price_history already has, and what defaults they carry.
--     Look specifically at `data_source` and `is_synthetic`: a non-empty
--     column_default on either is the defect STEP 2 removes.
SELECT column_name, data_type, is_nullable, column_default
  FROM information_schema.columns
 WHERE table_schema = 'public' AND table_name = 'price_history'
 ORDER BY ordinal_position;

-- 0b. Which of the three tables this migration touches already exist.
SELECT table_name
  FROM information_schema.tables
 WHERE table_schema = 'public'
   AND table_name IN ('price_history', 'snapshot_metadata', 'forecast_store');

-- 0c. Row count. STEP 3 relabels rows; it must not change this number.
SELECT count(*) AS price_history_rows FROM public.price_history;

-- 0d. Whether STEP 7 is a no-op on your database. If this returns three rows,
--     someone has already added them by hand and STEP 7 changes nothing; if it
--     returns none, POST /booking/create is currently failing on every request.
SELECT column_name, data_type
  FROM information_schema.columns
 WHERE table_schema = 'public' AND table_name = 'bookings'
   AND column_name IN ('origin_code', 'destination_code', 'amadeus_booking_id');

-- =====================================================================
-- STEP 1 — the 17 columns the ingest path writes and the schema lacks
-- =====================================================================
--
-- No column here is given a DEFAULT, deliberately. `ADD COLUMN ... DEFAULT
-- <literal>` fills every pre-existing row with that literal, which is a
-- fabricated measurement applied retroactively to data nobody looked at. It is
-- also precisely how this table's provenance labels became wrong — see STEP 2.
-- NULL is the honest value for a row written before the column existed.
--
-- Types follow the writer, not a guess:
--   `duration` is TEXT because the writer passes the provider's value straight
--   through — an integer count of minutes from a `legs` payload, an ISO-8601
--   string like 'PT2H15M' from a normalised one. An INT column would reject half
--   of them at insert time.
--   `urgency` and `training_weight` are DOUBLE PRECISION. Both are written on
--   every row and neither is read back from this table: `database.py:257`
--   recomputes `urgency` during feature engineering, overwriting the stored
--   value, and `model_trainer.py:201` reads `training_weight` from the training
--   frame. They still have to exist, or the insert fails.
--   `search_session_id`, `search_id` and `snapshot_id` are TEXT holding UUID
--   strings, matching the `str(uuid.uuid4())` the writers produce.
--   `departure_time` is TIMESTAMP WITHOUT TIME ZONE. It is the local departure
--   instant as the airline publishes it — 06:15 at the origin airport is 06:15
--   regardless of what UTC says — so attaching an offset would be inventing one.
--   This is the single most load-bearing column in the file. Two separate things
--   need it. `hour_of_day` and `is_peak_hour` are declared model features computed
--   from it; without it they are NaN for 100% of the training corpus while the
--   serving path reads the hour off the provider's segment and supplies it, which
--   is a feature the model can only ever see in production. And since 2026-09-03
--   it is also the per-flight component of BOOKING_CURVE_KEYS, replacing
--   `flight_number`, which the provider does not publish and never will — so
--   while this column is *absent* `attach_future_target` raises on the missing key
--   and no model can be trained at any horizon. It is written by `format_payload`,
--   populated by `flight_search_service` from the provider's segment departure
--   timestamp, and read by database.py's feature loader, TemporalGenerator and
--   every curve-grouping call site. (An earlier draft of this comment also named
--   `backend/bash.py` as a populator; that second ingestion driver has since been
--   deleted — it wrote to this table directly, bypassing the persistence path.)
--
--   ORDERING REQUIREMENT — read this before running STEP 1. Absent column and
--   NULL value are two different failures, and this ALTER converts the first into
--   the second on every row already in the table. `attach_future_target` raises
--   only on the *missing* column; once it is present and NULL the guard goes
--   silent, and until 2026-09-03 the as-of join underneath both the label and the
--   `price_change_*` features did not consult `curve_identity_mask` either.
--   `pd.merge_asof(by=keys)` factorises its key columns and a null matches other
--   nulls, so one route/airline/date of NULL-`departure_time` rows was a single
--   booking curve and the earliest row was labelled with the latest row's fare —
--   another flight's. Measured on four rows: mask [False,False,False,False],
--   label still returned, price 9000 carrying target_price 5300. Applying this
--   migration was the trigger for that, not the cure for it. The fix is one
--   statement in `booking_curve_definition._price_at_offset` (AUDIT-FIXES.md §45,
--   regression test `backend/tests/test_curve_identity_gate.py`). Do not run
--   STEP 1 unless that statement is in your working tree.
ALTER TABLE public.price_history
  ADD COLUMN IF NOT EXISTS search_session_id TEXT,
  ADD COLUMN IF NOT EXISTS search_timestamp  TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS is_live           BOOLEAN,
  ADD COLUMN IF NOT EXISTS data_source       TEXT,
  ADD COLUMN IF NOT EXISTS is_synthetic      BOOLEAN,
  ADD COLUMN IF NOT EXISTS training_weight   DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS urgency           DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS provider          TEXT,
  ADD COLUMN IF NOT EXISTS search_id         TEXT,
  ADD COLUMN IF NOT EXISTS snapshot_id       TEXT,
  ADD COLUMN IF NOT EXISTS collector_version TEXT,
  ADD COLUMN IF NOT EXISTS booking_date      DATE,
  ADD COLUMN IF NOT EXISTS duration          TEXT,
  ADD COLUMN IF NOT EXISTS stops             INT,
  ADD COLUMN IF NOT EXISTS terminal          TEXT,
  ADD COLUMN IF NOT EXISTS route             TEXT,
  ADD COLUMN IF NOT EXISTS departure_time    TIMESTAMP;

COMMENT ON COLUMN public.price_history.is_synthetic IS
  'TRUE = fabricated, FALSE = observed from a provider, NULL = not recorded. '
  'NULL is excluded from training by database.py:101, so unknown fails closed.';
COMMENT ON COLUMN public.price_history.urgency IS
  'Written at ingest and recomputed at database.py:257; the stored value is '
  'never read. Kept because get_db_payload submits it.';
COMMENT ON COLUMN public.price_history.departure_time IS
  'Local scheduled departure instant, no timezone — 06:15 at the origin airport. '
  'Per-flight component of BOOKING_CURVE_KEYS (it replaced flight_number, which '
  'no wired provider publishes) and the source of the hour_of_day and '
  'is_peak_hour features. NULL for rows written before this column existed; '
  'those rows have no booking-curve identity, carry no label, and keep both '
  'features NaN rather than having an hour inferred from the date.';

-- =====================================================================
-- STEP 2 — undo two defaults that fabricate provenance
-- =====================================================================
--
-- `alter_price_history_provenance.py` added `data_source` with
-- `DEFAULT 'GOOGLE_FLIGHTS'` and `is_synthetic` with `DEFAULT FALSE`. That script
-- lived in `backend/scratch/`, which has since been archived to
-- `.archive/backend-scratch-2026-09-02.tar.gz` and removed from the tree;
-- the DDL it applied by hand is what this file replaces. Adding a
-- column with a non-volatile default fills every existing row with it, so the
-- moment that script ran, every row already in the table — the seeded block
-- included — began reading back as real Google Flights data. Its own corrective
-- UPDATE was guarded by `WHERE data_source IS NULL OR is_synthetic IS NULL`, and
-- the two defaults had just removed every NULL, so it matched zero rows. The
-- mislabelling was not a missed edge case; the default and the repair were in the
-- same file, four statements apart, and the default won.
--
-- Dropping the defaults means a future insert that omits these columns records
-- NULL — unknown — instead of claiming to be real. The training predicate
-- `is_synthetic IS FALSE AND is_live IS TRUE` (`domain.provenance.PROVENANCE_SQL`,
-- reached in the query builder as `database._PROVENANCE_SQL`) excludes NULL, so
-- unknown provenance is now excluded from training rather than silently trained
-- on.
ALTER TABLE public.price_history ALTER COLUMN data_source  DROP DEFAULT;
ALTER TABLE public.price_history ALTER COLUMN is_synthetic DROP DEFAULT;
ALTER TABLE public.price_history ALTER COLUMN is_live      DROP DEFAULT;

-- The same script created `data_source` as VARCHAR(32).
-- flight_search_service.py:296 builds labels like
-- 'DB_FALLBACK (PROVIDER ERROR: TransportError)' — 44 characters. No insert
-- carries that value today, because only the STATUS_OK branch persists, so this
-- is a latent 22001 rather than a live one. varchar(n) -> text is binary
-- coercible: no table rewrite, no data change, no way to lose a value.
ALTER TABLE public.price_history ALTER COLUMN data_source TYPE TEXT;

-- =====================================================================
-- STEP 3 — relabel the seeded block, without depending on NULLs
-- =====================================================================
--
-- 3a. Confirm the discriminator on THIS database before changing anything.
--     Measured on the corpus this project shipped (AUDIT-ADDENDUM.md §2.2): the
--     seeded block is 6,328 rows carrying exactly one flight_number, 'HIST-000',
--     against 223 distinct flight numbers across the 1,026 genuinely live rows.
--     If the shape below does not match that, stop — do not run 3b.
--
--     Re-measured 2026-09-03 on a 35,894-row export of this table: `HIST-000`
--     appears on **zero** rows. Every row reads `is_synthetic = false,
--     data_source = 'GOOGLE_FLIGHTS'`; 33,426 are `is_live = true` and 2,468 are
--     `is_live = false`, and those 2,468 are exactly the rows carrying no
--     flight_number. So on that snapshot 3b matches nothing and STEP 3 is a
--     no-op. Two readings are possible and this file cannot distinguish them: the
--     seeded block was deleted between the two measurements, or §2.2 measured a
--     seed artefact rather than this table. Run 3a and believe its output over
--     either. What the re-measurement does establish is that there is no
--     mislabelled synthetic block left here to relabel — the provenance problem
--     STEP 2 and STEP 3 exist for is about future inserts now, not these rows.
SELECT
  count(*) FILTER (WHERE flight_number =  'HIST-000')  AS hist000_rows,
  count(*) FILTER (WHERE flight_number <> 'HIST-000')  AS other_rows,
  count(*) FILTER (WHERE flight_number IS NULL)        AS unnumbered_rows,
  count(DISTINCT flight_number) FILTER (WHERE flight_number <> 'HIST-000')
                                                       AS other_distinct,
  count(*) FILTER (WHERE flight_number = 'HIST-000'
                     AND is_synthetic IS NOT TRUE)     AS mislabelled_rows
FROM public.price_history;

-- 3b. Relabel. The predicate tests a *value*, so it works on rows the earlier
--     script already stamped — which is the whole point, since there are no NULLs
--     left to find. `IS DISTINCT FROM` rather than `<>` on data_source: `<>`
--     yields NULL against a NULL column, and `FALSE OR FALSE OR NULL` is NULL,
--     which would skip exactly the rows that still need the label.
UPDATE public.price_history
   SET is_synthetic = TRUE,
       is_live      = FALSE,
       data_source  = 'SEEDED'
 WHERE flight_number = 'HIST-000'
   AND (is_synthetic IS NOT TRUE
     OR is_live      IS NOT FALSE
     OR data_source  IS DISTINCT FROM 'SEEDED');

-- 3c. A second, independent signature, for a database where 'HIST-000' is not
--     the marker. A real observation's stored horizon agrees with its own
--     timestamps: measured disagreement was 0.0% across the 1,026 live rows and
--     96.9% across the 6,328 seeded ones, where every row was recorded exactly 14
--     days before departure while `days_until_dep` ranged over 57 distinct values
--     from 1 to 59. Those two facts cannot both describe observed data.
--
--     This is a SELECT on purpose. It is a judgement about rows I have never
--     queried, and a mislabelled real row is silently deleted from the training
--     corpus by the very predicate that is supposed to protect it. Read the
--     output before acting on it.
SELECT count(*)                     AS horizon_contradicts_timestamps,
       count(DISTINCT flight_number) AS distinct_flight_numbers,
       min(recorded_at)             AS earliest,
       max(recorded_at)             AS latest
  FROM public.price_history
 WHERE is_synthetic  IS NOT TRUE
   AND days_until_dep IS NOT NULL
   AND recorded_at    IS NOT NULL
   AND departure_date IS NOT NULL
   AND days_until_dep <> (departure_date - recorded_at::date);

-- If, and only if, you have satisfied yourself that every row that query returns
-- is fabricated, relabel them with 3b's SET clause and 3c's WHERE clause. It is
-- left uncommented-out nowhere in this file on purpose: it must not run unread.

-- 3d. Re-check. `mislabelled_rows` must now be 0 and the row count from 0c
--     unchanged.
SELECT count(*)                                            AS total_rows,
       count(*) FILTER (WHERE is_synthetic IS TRUE)        AS labelled_synthetic,
       count(*) FILTER (WHERE is_synthetic IS FALSE)       AS labelled_real,
       count(*) FILTER (WHERE is_synthetic IS NULL)        AS unlabelled,
       count(*) FILTER (WHERE is_synthetic IS FALSE
                          AND is_live      IS TRUE)        AS eligible_for_training
FROM public.price_history;

-- =====================================================================
-- STEP 4 — snapshot_metadata: the ingestion run record
-- =====================================================================
--
-- `HistoricalDataService.insert_snapshot_metadata` (historical_data_service.py:58)
-- writes this table on every scheduled run. It does not exist, so the call raised
-- every time. Until recently the call site was unguarded, which meant a
-- successful ingestion — rows written, corpus grown — was reported as a failed
-- job because recording the run failed. That guard now exists
-- (services/scheduler.py:319), so the run survives; the record is still lost.
--
-- Columns are the exact keys of the payload assembled at scheduler.py:290-314.
-- Nothing is added speculatively.
--
-- On the eight run-outcome counters: `rows_inserted` counts rows the database
-- confirmed, `rows_submitted` counts rows offered to it, and the four `routes_*`
-- counters partition every search attempted. A run where rows_submitted is high
-- and rows_inserted is 0 is the failure this schema exists to make visible — the
-- old summary could not express it, because it reported the number of flights
-- *displayed*, which for a route served from cache is a count of rows read rather
-- than written.
CREATE TABLE IF NOT EXISTS public.snapshot_metadata (
  id                      UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  snapshot_id             TEXT NOT NULL UNIQUE,
  search_id               TEXT,
  provider                TEXT,
  provider_version        TEXT,
  collector_version       TEXT,
  schema_version          TEXT,
  collection_timestamp    TIMESTAMPTZ,
  execution_duration      DOUBLE PRECISION,
  provider_latency        DOUBLE PRECISION,
  route_count             INT,
  rows_inserted           INT,
  search_success          BOOLEAN,
  search_count            INT,
  searches_planned        INT,
  searches_skipped        INT,
  rows_submitted          INT,
  routes_live             INT,
  routes_empty            INT,
  routes_provider_error   INT,
  routes_persistence_error INT,
  created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_snapshot_meta_collected
  ON public.snapshot_metadata(collection_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_snapshot_meta_success
  ON public.snapshot_metadata(search_success, collection_timestamp DESC);

-- No foreign key from price_history.snapshot_id to this table, and it would fail
-- if you added one. `flight_search_service.search()` mints its own snapshot_id at
-- line 209 on every call and the scheduler never passes its own (scheduler.py:122
-- generates one, scheduler.py:149 does not forward it), so the id on the rows and
-- the id on the run record are unrelated UUIDs. The run record is currently not
-- joinable to the observations it describes. Fixing that is a code change —
-- thread the scheduler's snapshot_id through `search()` — not a schema change.
COMMENT ON COLUMN public.snapshot_metadata.snapshot_id IS
  'Generated by the scheduler. Does NOT match price_history.snapshot_id, which '
  'flight_search_service mints per search call; see the note in migration 001.';

-- =====================================================================
-- STEP 5 — forecast_store: predictions, and their later evaluation
-- =====================================================================
--
-- `ForecastStore.save_forecast` (services/forecast_store.py:17) writes here on
-- every prediction; `ForecastEvaluationScheduler` (forecast_evaluation_scheduler.py)
-- reads pending rows back and updates them with the realised price. The table does
-- not exist, so `save_forecast` raises, and prediction_service.py:373 catches it at
-- warning level — the forecast is dropped and the request still returns 200. That
-- is why there is no record of a single prediction this system has ever made, and
-- therefore no measured out-of-sample error anywhere in the project.
--
-- Insert columns are the payload at forecast_store.py:28-37; update columns are the
-- four written at forecast_evaluation_scheduler.py:103-108.
--
-- `dataset_version` is nullable on purpose: model_registry now reports NULL rather
-- than the invented 'DATASET_2026_Q3_V1' when no dataset provenance was recorded.
CREATE TABLE IF NOT EXISTS public.forecast_store (
  id                  UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  forecast_id         TEXT NOT NULL UNIQUE,
  forecast_timestamp  TIMESTAMPTZ NOT NULL,
  prediction_horizon  INT NOT NULL,
  forecast_price      DECIMAL(10,2) NOT NULL,
  model_version       TEXT,
  dataset_version     TEXT,
  recommendation      JSONB,
  status              TEXT NOT NULL DEFAULT 'PENDING',
  actual_price        DECIMAL(10,2),
  evaluated_at        TIMESTAMPTZ,
  evaluation_metrics  JSONB,
  created_at          TIMESTAMPTZ DEFAULT NOW(),
  -- Three states, all three written by code.
  --   'PENDING'     forecast_store.py:36, on insert.
  --   'COMPLETED'   forecast_evaluation_scheduler._evaluate_one, when a realised
  --                 fare was found on the forecast's own booking curve inside the
  --                 outcome window. `actual_price` and `evaluation_metrics` are
  --                 both populated.
  --   'UNEVALUABLE' the same function, when the outcome window has closed and no
  --                 such observation exists — or when the row itself cannot be
  --                 scored (unparseable timestamp, no horizon, no positive
  --                 forecast price, incomplete booking-curve identity).
  --                 `actual_price` stays NULL; `evaluation_metrics` carries only
  --                 `unevaluable_reason`. Writing a placeholder error here is
  --                 exactly how a fabricated figure would enter the table.
  --
  -- 'UNEVALUABLE' exists because the previous evaluator `continue`d in both of
  -- those cases, leaving the row PENDING for ever: the queue was re-scanned in
  -- full on every run and grew without bound. A terminal state is what makes the
  -- partial index below stay small.
  CONSTRAINT forecast_store_status_chk
    CHECK (status IN ('PENDING', 'COMPLETED', 'UNEVALUABLE'))
);

-- The evaluator's hot query is "pending forecasts", so index that alone.
CREATE INDEX IF NOT EXISTS idx_forecast_store_pending
  ON public.forecast_store(forecast_timestamp)
  WHERE status = 'PENDING';

-- WHAT THIS TABLE TURNS ON.
-- Creating it makes both halves work. The *recording* half persists every
-- prediction with its model version, horizon, timestamp and — as of the same pass
-- that rewrote the evaluator — the booking-curve identity of the flight it was
-- about, all five components of it (prediction_service.py, `rec_payload`). That
-- last part is the precondition for the second half: without a departure date and
-- a flight number there is nothing to match an outcome against, which is why the
-- old evaluator matched on `departure_date = forecast_timestamp + horizon` (a
-- flight *departing* the day the horizon elapsed) and then fell back to a query
-- with no date predicate at all.
--
-- The *evaluation* half is now live and measures the quantity the model was
-- trained on. `forecast_evaluation_scheduler._resolve_outcome` takes the earliest
-- observation on the forecast's own curve at or after `forecast_timestamp +
-- horizon`, within `lag_tolerance_days(horizon)` — the rule
-- `booking_curve_definition.price_at_horizon` uses for the training label — and
-- filters on the same `is_synthetic IS FALSE AND is_live IS TRUE` provenance the
-- training corpus requires, because a synthesised row is not an outcome. Four
-- things it deliberately does not do: no `min()` over candidates (the cheapest
-- fare in the window is a different quantity from the fare that was there when the
-- horizon elapsed), no route-wide fallback, no percentage error against a
-- non-positive actual, and no row retired as unevaluable before its window closes.
--
-- The figure this produces is a realised out-of-sample error and is the only one
-- in the project that will be. It requires observations to exist on both sides,
-- so on a corpus with no repeat observation of a curve every forecast retires
-- UNEVALUABLE with a reason — which is the honest report, and readable in
-- `evaluation_metrics->>'unevaluable_reason'`.

-- =====================================================================
-- STEP 6 — indexes for the queries that exist, and RLS on the new tables
-- =====================================================================
--
-- price_history already carries idx_ph_route, idx_ph_date and idx_ph_price
-- (skymind_complete.sql:382-384). The three below cover the reads the code
-- performs on the columns STEP 1 added, and nothing else — an index for a query
-- nobody issues is write amplification with no reader.
--
--   idx_ph_provenance is a partial index on the training predicate itself
--   (`is_synthetic IS FALSE AND is_live IS TRUE`, database/database.py:101). It is
--   the selective one: on the shipped corpus it admits 1,026 of 7,354 rows.
--   idx_ph_recorded serves `.order("recorded_at", desc=True).limit(n)`, which is
--   how _load_from_supabase pages the corpus.
--   idx_ph_session serves the session-aware dedupe's grouping key.
CREATE INDEX IF NOT EXISTS idx_ph_provenance
  ON public.price_history(recorded_at DESC)
  WHERE is_synthetic IS FALSE AND is_live IS TRUE;
CREATE INDEX IF NOT EXISTS idx_ph_recorded
  ON public.price_history(recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_ph_session
  ON public.price_history(search_session_id)
  WHERE search_session_id IS NOT NULL;

-- RLS. Both new tables get it enabled and get NO policy, which is deliberate.
-- Enabling RLS without a policy denies every ordinary role and is invisible to
-- `service_role`, which bypasses RLS entirely — and service_role is the key the
-- backend holds (config.py reads SUPABASE_SERVICE_KEY). So the writers keep
-- working and the anon key sees nothing.
--
-- Compare price_history, which has `CREATE POLICY "pub_ph" … FOR SELECT USING
-- (TRUE)` at skymind_complete.sql:606: the entire price corpus is readable by
-- anyone holding the anon key, which ships in the frontend bundle. That is a
-- deliberate-looking choice for a public fare table and a bad one for a training
-- corpus; it is recorded in AUDIT-FIXES.md §9 rather than changed here, because
-- revoking it may break a frontend read path I have not traced.
ALTER TABLE public.snapshot_metadata ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.forecast_store    ENABLE ROW LEVEL SECURITY;

-- =====================================================================
-- STEP 7 — the three columns POST /booking/create writes and bookings lacks
-- =====================================================================
--
-- `create_booking` (routers/booking.py:174-198) builds `booking_payload` with 18
-- unconditional keys plus `user_id` and `coupon_code` when the request carries
-- them: 20 at most. `public.bookings` (skymind_complete.sql) declares 39 columns.
-- Exactly three written keys have no column:
--
--   origin_code          from _extract_route(), the first segment's origin
--   destination_code     from _extract_route(), the last segment's destination
--   amadeus_booking_id   the request's flight_offer_id, verbatim
--
-- PostgREST rejects an insert naming a column that does not exist, so
-- `POST /booking/create` fails with a 500 for every request, on the first
-- statement, before a passenger row is ever attempted. This is not a degraded
-- path: booking creation cannot succeed against the shipped schema at all. The
-- 17 remaining keys are all declared, and every UPDATE on this table
-- (payment.py:156, payment.py:228, booking.py:339) writes only declared columns,
-- so the insert is the whole of the gap.
--
-- Derived, not designed. The set above is the difference between the payload
-- keys and `information_schema.columns` for this table, computed both ways: no
-- column here is absent a writer, and no written key is left without a column.
-- `passengers` was checked the same way and is clean — 19 written keys against
-- 21 columns.
--
-- Types follow the writer:
--   `origin_code` and `destination_code` are TEXT and, unlike their namesakes on
--   price_history (skymind_complete.sql:364-365), carry NO foreign key into
--   public.airports. That is deliberate. The FK on price_history is the reason an
--   unseeded airport can fail a whole ingest batch; on a booking it would mean
--   refusing a customer's purchase because a reference table is incomplete.
--   A booking must record what was bought even when the vocabulary is behind.
--   Both are nullable: `_extract_route` returns (None, None) when the offer's
--   itinerary cannot be read, and NULL is the honest record of that.
--   `amadeus_booking_id` is TEXT. The name is inherited from an Amadeus-era
--   integration; what it now holds is whatever `flight_offer_id` the client sent,
--   which for a scraper-sourced offer is not an Amadeus record locator. Renaming
--   it is a code change and is not attempted here — see the note at the end.
--
-- No DEFAULT on any of the three, for the reason given in STEP 1: a default
-- back-fills every pre-existing booking with a literal nobody measured.

-- 7a. The columns.
ALTER TABLE public.bookings
  ADD COLUMN IF NOT EXISTS origin_code        TEXT,
  ADD COLUMN IF NOT EXISTS destination_code   TEXT,
  ADD COLUMN IF NOT EXISTS amadeus_booking_id TEXT;

COMMENT ON COLUMN public.bookings.origin_code IS
  'First segment origin as read from the offer at booking time. No FK to '
  'airports: a booking must not be refused because a reference table lags. '
  'NULL = the offer itinerary could not be read (routers/booking.py:131-152).';
COMMENT ON COLUMN public.bookings.destination_code IS
  'Last segment destination as read from the offer at booking time. Same '
  'nullability and same absence of an FK as origin_code.';
COMMENT ON COLUMN public.bookings.amadeus_booking_id IS
  'The client-supplied flight_offer_id, stored verbatim. Historically an '
  'Amadeus locator; today it is whatever identifier the offer carried, which '
  'for a scraped offer is not an Amadeus id. Name kept to match the writer.';

-- 7b. Verification (read-only). Both queries must return zero rows.
--     The first proves no written key is missing a column; the second proves the
--     three additions are actually present rather than silently skipped by
--     IF NOT EXISTS against a differently-typed pre-existing column.
SELECT k AS written_key_with_no_column
  FROM unnest(ARRAY[
        'id','booking_reference','status','payment_status','origin_code',
        'destination_code','amadeus_booking_id','flight_offer_data',
        'num_passengers','contact_email','contact_phone','cabin_class',
        'total_price','base_fare','taxes','currency','created_at','updated_at',
        'user_id','coupon_code'
       ]) AS k
 WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns c
         WHERE c.table_schema = 'public' AND c.table_name = 'bookings'
           AND c.column_name = k);

SELECT k AS added_column_missing_or_wrong_type
  FROM unnest(ARRAY['origin_code','destination_code','amadeus_booking_id']) AS k
 WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns c
         WHERE c.table_schema = 'public' AND c.table_name = 'bookings'
           AND c.column_name = k AND c.data_type = 'text');

-- =====================================================================
-- STEP 8 — the observation-identity guard. GATED. Read 8a first.
-- =====================================================================
--
-- Nothing in the database stops the same observation being stored twice. The only
-- de-duplication is in pandas, at read time (`deduplicate_session_aware`,
-- services/booking_curve_definition.py), so a re-run that re-scrapes the same
-- session writes the rows again and the corpus grows without gaining information.
-- A unique index moves that invariant into the one place that cannot be bypassed.
--
-- Why this step is separate from STEP 1-7, and why it is gated:
--
--   1. It can fail. Unlike every other statement in this file, this one is a
--      constraint on data, so a collision makes the CREATE fail and — inside a
--      transaction with STEP 1-7 — would roll back the columns and tables those
--      steps added. On *today's* rows it cannot fail: the partial predicate below
--      requires `departure_time IS NOT NULL` and every row now in the table
--      predates that column. So an empty table buys nothing here. What can
--      collide is what the writer inserts after the migration, which is point 2,
--      and that is the only real gate on this step.
--   2. Applying it before the writer is fixed loses data. PostgREST executes
--      `insert(list)` as a single statement, `flight_search_service.py:321-361`
--      builds `db_payloads` with no in-batch de-duplication, and
--      `insert_observations` passes no `on_conflict`. So one duplicated row from
--      the provider makes the whole route's batch fail, not just that row. Today
--      that batch is silently accepted with the duplicate; after this index it is
--      silently discarded entirely. That is a worse failure, not a better one.
--   3. CREATE UNIQUE INDEX takes ACCESS EXCLUSIVE on the table. The CONCURRENTLY
--      form does not, but it cannot run inside a transaction block — another
--      reason this is its own step.
--
-- PRECONDITION, in code, before you run 8b:
--   either dedupe `db_payloads` in `flight_search_service.py` on the same key
--   before submitting, or make `insert_observations` upsert
--   (`.upsert(rows, on_conflict="…", ignore_duplicates=True)`). Until one of
--   those lands, leave 8b unrun.
--   STATUS 2026-09-05: the first option has landed and is in the working tree
--   (AUDIT-FIXES.md §47). `deduplicate_observation_batch` in
--   `backend/services/booking_curve_definition.py` collapses a batch on exactly
--   the seven columns indexed below, and it is called both at the sole writer
--   (`historical_data_service.insert_observations`) and at the one call site
--   (`flight_search_service.search`, so a collapsed duplicate is not reported as a
--   database fault). `backend/tests/test_observation_dedup.py::test_key_matches_
--   the_migrations_index` parses the column list out of THIS statement and fails
--   if the two ever disagree, so editing the index below without editing the code
--   is caught.
--   The second option — the upsert — is still not in the tree, and must not be
--   added before this index exists: `on_conflict` names an index, so PostgREST
--   rejects every insert while it is absent. Add it in the same change as 8b, not
--   before.
--
-- On the key itself. It is BOOKING_CURVE_KEYS (origin, destination, airline,
-- departure_time, departure_date) plus `search_session_id` and `cabin_class`.
--   `search_session_id` is what makes it a booking *curve*: the same flight
--   observed in a later session is a new, wanted data point, not a duplicate.
--   `departure_time` is the per-flight component, and it was `flight_number`
--   until 2026-09-03. That substitution is what makes this index safe to create
--   rather than destructive. The provider does not publish a flight number — a
--   live 65-flight DEL-BOM fetch contained none — so `COALESCE(flight_number,'')`
--   evaluates to the empty string on every row, and the key would have collapsed
--   every one of a carrier's departures on a route, date, cabin and session into
--   a single permitted row. On that fetch it would have admitted 5 rows (one per
--   airline code) and rejected 60 legitimate observations. `departure_time`
--   separates 64 of the 65.
--   `cabin_class` is present here and absent from BOOKING_CURVE_KEYS — that
--   omission is a live defect (AUDIT-FIXES.md §9): the pandas dedupe collapses
--   Economy and Business on one flight into a single row and keeps whichever
--   sorted last. Including it here means the database will not repeat that.
--   `COALESCE(cabin_class, '')` because NULL <> NULL in a unique index: without
--   it, a row with no cabin recorded could be stored without limit.
--   `departure_time` needs no COALESCE — it is a NOT-NULL requirement of the
--   curve identity, and the partial predicate below restricts this index to rows
--   the current writer produces, which always populate it. A row that reached
--   this table without one has no curve and the index declining to police it is
--   the right outcome; `curve_identity_mask` refuses it downstream.
--   No observation timestamp column: `recorded_at::text` is STABLE, not
--   IMMUTABLE, so Postgres rejects it in an index expression — and a bare
--   timestamp would make every row unique and the index pointless. Note that
--   `departure_time` is not that: it is the published schedule, constant across
--   observations of one flight, which is exactly why it can key an index.
--   `WHERE search_session_id IS NOT NULL` restricts the guard to rows the current
--   writer produces. The 6,328 seeded rows and the pre-provenance live rows have
--   no session id, are not unique under this key, and would otherwise make the
--   CREATE fail on legacy data the guard was never meant to police.

-- 8a. Collision census (read-only), under 8b's own predicate.
--
--     Read `indexable_rows` first. `colliding_groups = 0` with
--     `indexable_rows = 0` is not evidence that 8b is safe; it is evidence that
--     the index has nothing to police yet, which is this database's state until a
--     collection run writes rows that populate `departure_time`. A census that
--     can only return zero is not a check.
--
--     This census used to filter on `search_session_id IS NOT NULL` alone, while
--     8b's index also requires `departure_time IS NOT NULL`. Every row now in the
--     table predates that column, and GROUP BY treats NULLs as equal, so each
--     session's whole route/date collapsed into one group and the census reported
--     collisions among rows the index would never have seen — it said 8b would
--     fail where 8b would have succeeded. A census that does not share its
--     index's predicate is not a census of that index.
--
--     A non-zero `colliding_groups` with a non-zero `indexable_rows` is real:
--     `rows_that_would_be_rejected` is how many rows you would have to delete or
--     relabel first, and you should look at a sample of them before concluding
--     they are duplicates rather than a key too narrow for this data. Note what
--     this means for the gate: legacy rows are not what holds 8b back, and
--     emptying the table does not release it. The writer-side de-duplication in
--     the PRECONDITION above does, and as of 2026-09-05 that code is in the tree.
SELECT (SELECT count(*) FROM public.price_history
         WHERE search_session_id IS NOT NULL
           AND departure_time    IS NOT NULL)  AS indexable_rows,
       count(*)                                AS colliding_groups,
       coalesce(sum(n), 0) - count(*)          AS rows_that_would_be_rejected,
       coalesce(max(n), 0)                     AS largest_group
  FROM (
        SELECT count(*) AS n
          FROM public.price_history
         WHERE search_session_id IS NOT NULL
           AND departure_time    IS NOT NULL
         GROUP BY search_session_id, origin_code, destination_code, airline_code,
                  departure_time, departure_date,
                  COALESCE(cabin_class, '')
        HAVING count(*) > 1
       ) g;

-- 8b. The guard. Run only when 8a reports 0 and the writer-side de-duplication
--     named in the PRECONDITION above is in place.
CREATE UNIQUE INDEX IF NOT EXISTS ux_price_history_observation
    ON public.price_history (
        search_session_id, origin_code, destination_code, airline_code,
        departure_time, departure_date, COALESCE(cabin_class, '')
    )
 WHERE search_session_id IS NOT NULL
   AND departure_time IS NOT NULL;

-- =====================================================================
-- NOT IN THIS FILE — three things that need code, not DDL
-- =====================================================================
--
-- 1. price_history.origin_code, destination_code and airline_code are foreign
--    keys into public.airports(iata_code) and public.airlines(iata_code)
--    (skymind_complete.sql:364-366). An observation for a carrier or airport that
--    was never seeded fails with 23503 and, because the batch is one statement,
--    takes the whole route's rows with it. Whether the right answer is to seed the
--    reference tables from the provider's vocabulary or to drop the constraints is
--    a data-model decision, so it is left to you. Diagnose with:
--      SELECT DISTINCT airline_code FROM public.price_history p
--       WHERE NOT EXISTS (SELECT 1 FROM public.airlines a
--                          WHERE a.iata_code = p.airline_code);
--    which returns nothing today only because such rows never got inserted.
-- 2. The scheduler's snapshot_id never reaches the rows (see the note in STEP 4),
--    so no run record can be joined to its observations.
-- 3. cabin_class is missing from BOOKING_CURVE_KEYS, and the scheduler only ever
--    searches ECONOMY (scheduler.py:149), so the defect is currently latent.
