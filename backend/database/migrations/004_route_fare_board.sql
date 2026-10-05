-- Today's lowest fare per route, for the home page's fare board.
--
-- The home page used to show hard-coded "starting at" fares (DEL-BOM ₹4,299,
-- "18 flights") that no search had ever returned. This view serves the real
-- cheapest fare per route from the last 36 hours of collection.
--
-- Run once in the Supabase SQL Editor. Safe to re-run.

CREATE OR REPLACE VIEW public.route_fare_board AS
SELECT DISTINCT ON (origin_code, destination_code)
       origin_code,
       destination_code,
       departure_date,
       airline_code,
       price,
       currency,
       stops,
       recorded_at
FROM public.price_history
WHERE is_live IS TRUE
  AND is_synthetic IS NOT TRUE
  AND currency = 'INR'
  AND recorded_at > now() - interval '36 hours'
  AND departure_date >= current_date + 1
ORDER BY origin_code, destination_code, price ASC, recorded_at DESC;

-- Speeds the recorded_at filter above and the training loader's ordering.
CREATE INDEX IF NOT EXISTS price_history_recorded_at_idx
    ON public.price_history (recorded_at);

NOTIFY pgrst, 'reload schema';
