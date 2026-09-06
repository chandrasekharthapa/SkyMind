"""Historical Data Service.

Handles persistence of append-only historical observations and snapshot metadata.
Performs no searching, forecasting, or machine learning operations.
"""

import logging
from typing import Dict, Any, List
from backend.database.database import database as db

logger = logging.getLogger(__name__)

class HistoricalDataService:
    def __init__(self):
        pass

    def insert_observations(self, records: List[Dict[str, Any]]) -> int:
        """Append observations to price_history; return the rows the DB acknowledged.

        This used to `return len(records)` — the number of rows *submitted*. That
        is not a measurement of anything: it is known before the call is made, it
        is identical whether the insert wrote 20 rows or the client silently
        dropped them, and callers were using it as a persisted-row count. The
        return value is now taken from the PostgREST response body, which lists
        the rows the database actually created.

        Returns -1 (not 0, and not len(records)) when the response carries no row
        representation, so "the DB did not tell us" stays distinguishable from
        "the DB wrote nothing". A caller must never be able to read a count it
        cannot trust as if it were confirmed.

        In-batch duplicates are collapsed before submission. This is the only code
        in the project that writes `price_history` — verified by grep for
        `table("price_history").insert` — which is why the guard lives here rather
        than at the one call site: a future caller gets it without having to know it
        exists. `deduplicate_observation_batch` is idempotent, so a caller that has
        already run it (as `FlightSearchService.search` does, in order to report an
        honest `rows_submitted`) loses nothing by the second pass. See that
        function for why the batch scope is sufficient and what it does not cover.

        Rows whose fare is not in the corpus currency, or falls outside the fare
        window the loaders apply, are refused here too — `screen_observation_fares`,
        for the same "sole writer" reason.
        """
        if not records:
            return 0

        from backend.domain.provenance import screen_observation_fares
        from backend.services.booking_curve_definition import deduplicate_observation_batch

        # Screen before collapsing, not after, and the order is load-bearing.
        # `deduplicate_observation_batch` keeps the *lowest* fare in an identity
        # group; a group holding the same flight quoted once in dollars (70) and
        # once in rupees (6,000) would collapse to the dollar row, which the screen
        # would then drop — losing the good observation to a bad one. Screening
        # first means the group the de-duplicator sees contains only storable fares.
        records, screen = screen_observation_fares(records)
        if screen["dropped"]:
            # ERROR rather than WARNING for a foreign fare: it means the provider
            # served a page in another currency and no FX rate was configured, so
            # collection is silently losing rows until someone acts.
            log = logger.error if screen["dropped_foreign_currency"] else logger.warning
            log(
                "[HistoricalDataService] Refused %d of %d observation row(s) before "
                "insert: %d in a foreign currency, %d with no readable currency, "
                "%d outside the fare window (worst fare %s). Currencies seen: %s.",
                screen["dropped"], screen["submitted"],
                screen["dropped_foreign_currency"],
                screen["dropped_unreadable_currency"],
                screen["dropped_implausible_fare"],
                screen["worst_dropped_fare"],
                screen["currencies_seen"] or "none readable",
            )
        if not records:
            logger.error(
                "[HistoricalDataService] Every row in this batch was refused; "
                "nothing was submitted."
            )
            return 0

        records, dedup = deduplicate_observation_batch(records)
        if dedup["dropped"]:
            # WARNING, not INFO: the provider returned the same flight twice, and
            # after migration 001 STEP 8b that batch would have been rejected whole.
            logger.warning(
                "[HistoricalDataService] Collapsed %d duplicate observation row(s) "
                "across %d identity group(s) before insert (%d group(s) disagreed on "
                "price, widest spread %.2f). Submitting %d of %d.",
                dedup["dropped"], dedup["groups_collapsed"],
                dedup["groups_disagreeing_on_price"], dedup["max_price_spread"],
                dedup["kept"], dedup["submitted"],
            )
        try:
            resp = db.supabase.table("price_history").insert(records).execute()
        except Exception as err:
            logger.error(f"[HistoricalDataService] Failed to insert observation rows: {err}")
            raise err

        returned = getattr(resp, "data", None)
        if isinstance(returned, list):
            n = len(returned)
            if n != len(records):
                logger.error(
                    f"[HistoricalDataService] Submitted {len(records)} observation row(s) "
                    f"but the database acknowledged {n}."
                )
            else:
                logger.info(f"[HistoricalDataService] Inserted {n} observation row(s), confirmed by the database.")
            return n

        logger.warning(
            f"[HistoricalDataService] Insert of {len(records)} observation row(s) raised no error but "
            "returned no row representation; treating the persisted count as unknown."
        )
        return -1

    def insert_snapshot_metadata(self, metadata: Dict[str, Any]) -> None:
        """Stores scheduled execution metadata metrics."""
        try:
            db.supabase.table("snapshot_metadata").insert(metadata).execute()
            logger.info(f"[HistoricalDataService] SnapshotMetadata successfully recorded for snapshot: {metadata.get('snapshot_id')}")
        except Exception as err:
            logger.error(f"[HistoricalDataService] Failed to store SnapshotMetadata: {err}")
            raise err

historical_data_service = HistoricalDataService()
