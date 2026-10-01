-- Migration 003 — store the arrival time the scraper already reads.
--
-- GoogleFlightsProvider.js has always parsed each card's arrival clock time (and
-- moves an overnight arrival to the next calendar day), and stdio_server.js sends
-- it as `arrival_time`; nothing passed it on to price_history. With departure_time
-- and duration it pins down which flight a fare belongs to — the page does not
-- publish flight numbers — and gives the model red-eye / next-day arrivals.
--
-- Same type and convention as departure_time: TIMESTAMP WITHOUT TIME ZONE, the
-- local wall-clock time as the airline publishes it. No DEFAULT: rows written
-- before this column existed have no arrival time, and NULL says so.
--
-- Until this runs, inserts still succeed: HistoricalDataService drops a column
-- PostgREST reports missing and logs an ERROR naming this migration.
--
-- Run in Supabase -> SQL Editor. Safe to re-run.

ALTER TABLE public.price_history
  ADD COLUMN IF NOT EXISTS arrival_time TIMESTAMP;

COMMENT ON COLUMN public.price_history.arrival_time IS
  'Local arrival wall-clock time as scraped; overnight arrivals carry the next date. NULL before migration 003.';

NOTIFY pgrst, 'reload schema';
