-- Migration 002 — bring snapshot_metadata up to the payload the scheduler writes.
--
-- The ingestion run record failed on every run with
--   PGRST204 "Could not find the 'provider_version' column of 'snapshot_metadata'"
-- because the live table predates migration 001's STEP 4 shape, and five fields
-- (rows_identity_known, rows_identified, rows_unidentified, search_failure_rate,
-- search_failure_rate_ceiling) were added to the payload in scheduler.py after 001
-- was written. PostgREST rejects the whole insert if any key has no column, so one
-- missing column loses the entire record.
--
-- Every column the payload in `_collect_popular_routes_async` sends is listed. ADD
-- COLUMN IF NOT EXISTS makes this safe on a table that already has some of them and
-- a no-op on re-run. No DEFAULTs: a run recorded before a column existed has no
-- value for it, and NULL says so.
--
-- Run in Supabase -> SQL Editor. The final NOTIFY makes PostgREST reload its schema
-- cache immediately; without it the API can keep rejecting the new columns for a
-- while after they exist.

CREATE TABLE IF NOT EXISTS public.snapshot_metadata (
  id          UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
  snapshot_id TEXT NOT NULL UNIQUE,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.snapshot_metadata
  ADD COLUMN IF NOT EXISTS search_id                   TEXT,
  ADD COLUMN IF NOT EXISTS provider                    TEXT,
  ADD COLUMN IF NOT EXISTS provider_version            TEXT,
  ADD COLUMN IF NOT EXISTS collector_version           TEXT,
  ADD COLUMN IF NOT EXISTS schema_version              TEXT,
  ADD COLUMN IF NOT EXISTS collection_timestamp        TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS execution_duration          DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS provider_latency            DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS route_count                 INT,
  ADD COLUMN IF NOT EXISTS rows_inserted               INT,
  ADD COLUMN IF NOT EXISTS search_success              BOOLEAN,
  ADD COLUMN IF NOT EXISTS search_count                INT,
  ADD COLUMN IF NOT EXISTS searches_planned            INT,
  ADD COLUMN IF NOT EXISTS searches_skipped            INT,
  ADD COLUMN IF NOT EXISTS rows_submitted              INT,
  ADD COLUMN IF NOT EXISTS rows_identity_known         INT,
  ADD COLUMN IF NOT EXISTS rows_identified             INT,
  ADD COLUMN IF NOT EXISTS rows_unidentified           INT,
  ADD COLUMN IF NOT EXISTS routes_live                 INT,
  ADD COLUMN IF NOT EXISTS routes_empty                INT,
  ADD COLUMN IF NOT EXISTS routes_provider_error       INT,
  ADD COLUMN IF NOT EXISTS routes_persistence_error    INT,
  ADD COLUMN IF NOT EXISTS search_failure_rate         DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS search_failure_rate_ceiling DOUBLE PRECISION;

NOTIFY pgrst, 'reload schema';
