"""SkyMind — Background Scheduler.

Updated for MCP travel server pipeline and continuous historical price collection.
Handles price alert checking, model retraining, and popular route price ingestion.
Schedules price collection every 6 hours.
"""

import logging
import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone
import os

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from opentelemetry import metrics

# `json`, `typing` and `backend.services.mcp_client.mcp_gateway` used to be
# imported here and referenced nowhere. The last one is the one that mattered:
# importing this module pulled in the MCP gateway singleton — and through it the
# `mcp` package — purely as an import-time side effect of a name no line used.
# The jobs below import what they need inside the function body.

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

# OpenTelemetry Metrics setup
meter = metrics.get_meter("skymind.scheduler")

rows_inserted_counter = meter.create_counter(
    name="scheduler_rows_inserted_total",
    description="Total rows inserted by scheduler"
)
routes_collected_counter = meter.create_counter(
    name="scheduler_routes_collected_total",
    description="Total unique routes collected by scheduler"
)
snapshots_created_counter = meter.create_counter(
    name="scheduler_snapshots_created_total",
    description="Total snapshot metadata entries created"
)
provider_latency_hist = meter.create_histogram(
    name="scheduler_provider_latency_seconds",
    description="Latency of provider flight search inside scheduler"
)
collection_duration_hist = meter.create_histogram(
    name="scheduler_collection_duration_seconds",
    description="Duration of a scheduler collection run"
)
collection_success_rate_gauge = meter.create_gauge(
    name="scheduler_collection_success_rate",
    description="Success rate of routes collection"
)

# ── HELPER FOR EVENT LOOP ISOLATION ───────────────────────────────────

def run_in_new_loop(coro):
    """Run an async coroutine inside a thread-isolated event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# ── DYNAMIC BOOKING CURVE COLLECTION ───────────────────────────────────

async def _collect_popular_routes_async() -> None:
    """Collects prices for persistent departure dates repeatedly across route batches to build complete booking curves."""
    logger.info("[Scheduler] Starting domestic route collection job...")
    from backend.route_catalog import route_catalog_config
    from backend.services.flight_search_service import flight_search_service
    from backend.services.flight_data_service import STATUS_OK, STATUS_EMPTY, STATUS_ERROR
    from backend.services.booking_curve_definition import BOOKING_CURVE_KEYS

    start_run = time.time()

    # Load configuration
    batches = route_catalog_config.create_route_batches()
    departure_horizons = route_catalog_config.get_departure_buckets()
    max_retries = route_catalog_config.get_retry_attempts()
    backoff_seconds = route_catalog_config.get_retry_backoff_seconds()

    total_routes_count = sum(len(b) for b in batches)
    routes_collected_counter.add(total_routes_count)

    if not batches or total_routes_count == 0:
        logger.warning("[Scheduler] RouteCatalogConfig returned 0 routes to collect.")
        raise RuntimeError("Ingestion failed: no routes to collect.")

    # A wall-clock budget for the whole run. The retry loop below now honours the
    # configured retry_backoff_seconds (30) instead of a hardcoded 0.1 — the config
    # knob previously did nothing — and the transport it calls already retries with
    # its own exponential backoff and a 30s timeout per attempt. Against a provider
    # that is completely down, those two policies compose into minutes per route/date
    # pair, which for a full catalogue would outlast the 6-hour collection interval.
    # When the budget runs out the run stops and says how many searches it skipped,
    # rather than either running for hours or reporting a complete run.
    max_run_seconds = max(60.0, float(os.getenv("SCHEDULER_MAX_RUN_MINUTES", "240")) * 60.0)

    today = datetime.now(timezone.utc)

    # An ingestion run has one job: write observations. It therefore counts what the
    # database confirmed, not what the API displayed. `total_inserted` used to be
    # `+= len(pres.flights)`, the number of flights *shown* — which for a route the
    # provider could not scrape is the number of rows read back out of the cache. A
    # run that scraped nothing and wrote nothing could report thousands of
    # "inserted" observations, and the zero-rows gate below could never fire.
    total_rows_persisted = 0
    total_rows_submitted = 0
    # Of the rows stored, how many carry an incomplete booking-curve identity. A run
    # storing 700 such rows is indistinguishable, in every number this function used
    # to report, from a run storing 700 trainable ones — and the corpus it grows can
    # never be labelled. Counted here so the gate below can fire on it.
    #
    # Both counters advance only for a search the database fully confirmed. On a
    # partial write the split is genuinely unknowable: `unidentified_rows` is measured
    # over the rows submitted, `rows_persisted` says how many of them landed, and
    # nothing says which. Counting such a batch would let the gate fail a run that
    # did store labellable rows, so `total_rows_identity_known` is published as the
    # denominator and a partial write is left out of both.
    total_rows_identity_known = 0
    total_rows_unidentified = 0
    routes_live = 0                # provider answered with flights
    routes_empty = 0               # provider answered; this route genuinely has none
    routes_provider_error = 0      # provider broke; nothing was scraped
    routes_persistence_error = 0   # flights were scraped but not confirmed stored
    total_searches = 0
    total_retries = 0
    searches_skipped = 0
    provider_latencies = []

    snapshot_id = str(uuid.uuid4())
    search_id = str(uuid.uuid4())

    # Iterate over route batches -> routes -> departure buckets
    out_of_time = False
    for batch_idx, batch in enumerate(batches):
        if out_of_time:
            break
        logger.info(f"[Scheduler] Processing Batch {batch_idx + 1}/{len(batches)} ({len(batch)} routes)...")
        for origin, destination in batch:
            if out_of_time:
                break
            for days_out in departure_horizons:
                if time.time() - start_run > max_run_seconds:
                    out_of_time = True
                    break
                target_date = (today + timedelta(days=days_out)).strftime("%Y-%m-%d")
                total_searches += 1

                outcome = "provider_error"
                for attempt in range(1, max_retries + 1):
                    start_search = time.time()
                    try:
                        pres = await flight_search_service.search(
                            origin_iata=origin,
                            destination_iata=destination,
                            departure_date=target_date,
                            cabin_class="ECONOMY"
                        )

                        latency = time.time() - start_search
                        provider_latencies.append(latency)
                        provider_latency_hist.record(latency)

                        md = (pres.metadata if pres and pres.metadata else {}) or {}
                        provider_status = md.get("provider_status")
                        rows_submitted = md.get("rows_submitted") or 0
                        rows_persisted = md.get("rows_persisted")
                        persistence_error = md.get("persistence_error")
                        rows_unidentified = md.get("unidentified_rows") or 0

                        if provider_status == STATUS_ERROR:
                            # Nothing was scraped, so there is nothing to store. Retry
                            # — note the transport already retried internally, so this
                            # is a second-order retry over a genuinely broken provider.
                            logger.warning(
                                f"[Scheduler] Provider error [{md.get('provider_error_kind')}] for "
                                f"{origin}->{destination} on {target_date} "
                                f"(attempt {attempt}/{max_retries})"
                            )
                            if attempt < max_retries:
                                total_retries += 1
                                await asyncio.sleep(backoff_seconds)
                            continue

                        if provider_status == STATUS_EMPTY:
                            # A parseable answer of "no flights" is an answer. Retrying
                            # it just re-scrapes a quiet route; the old code did retry
                            # here, because it could not tell this apart from a failure.
                            outcome = "empty"
                            break

                        if provider_status != STATUS_OK:
                            # Not "error", not "empty", not "ok". Treat an unrecognised
                            # status as a failure rather than letting it fall through to
                            # the success path, which is how a new status value would
                            # otherwise start being counted as a live collection.
                            logger.error(
                                f"[Scheduler] Unrecognised provider status {provider_status!r} for "
                                f"{origin}->{destination} on {target_date}; not counting it as collected."
                            )
                            if attempt < max_retries:
                                total_retries += 1
                                await asyncio.sleep(backoff_seconds)
                            continue

                        # provider_status == STATUS_OK: flights were scraped.
                        total_rows_submitted += rows_submitted
                        if isinstance(rows_persisted, int) and rows_persisted > 0:
                            total_rows_persisted += rows_persisted
                            if rows_persisted == rows_submitted:
                                total_rows_identity_known += rows_persisted
                                # `min` only guards a malformed payload reporting more
                                # unidentified rows than it submitted; on this branch
                                # the two counts are over the same set of rows.
                                total_rows_unidentified += min(rows_unidentified, rows_persisted)
                        # -1 means "attempted but the database did not confirm" and
                        # None means "no insert was attempted". Neither is a written
                        # row, and neither may be added to the total.
                        if persistence_error or not isinstance(rows_persisted, int) or rows_persisted < rows_submitted:
                            routes_persistence_error += 1
                            logger.error(
                                f"[Scheduler] {origin}->{destination} on {target_date}: scraped "
                                f"{rows_submitted} observation(s), stored {rows_persisted}"
                                + (f" — {persistence_error}" if persistence_error else "")
                            )
                            outcome = "persistence_error"
                        else:
                            outcome = "live"
                        break
                    except Exception as route_err:
                        logger.warning(f"[Scheduler] Attempt {attempt}/{max_retries} failed for {origin}->{destination} on {target_date}: {route_err}")
                        if attempt < max_retries:
                            total_retries += 1
                            await asyncio.sleep(backoff_seconds)

                if outcome == "live":
                    routes_live += 1
                elif outcome == "empty":
                    routes_empty += 1
                elif outcome == "provider_error":
                    routes_provider_error += 1

    # Ingestion summary metrics
    duration = time.time() - start_run
    collection_duration_hist.record(duration)

    planned_searches = total_routes_count * len(departure_horizons)
    searches_skipped = max(0, planned_searches - total_searches)
    if out_of_time:
        logger.error(
            f"[Scheduler] Run budget of {max_run_seconds / 60.0:.0f} minute(s) exhausted after "
            f"{total_searches}/{planned_searches} search(es); {searches_skipped} skipped. "
            "Raise SCHEDULER_MAX_RUN_MINUTES or reduce the route catalogue."
        )

    # "Success" is a search that scraped live flights and stored them. A cache read
    # is not a collection, and a scrape whose rows never landed is not one either.
    successful_searches = routes_live
    failed_searches = routes_provider_error + routes_persistence_error
    success_rate = (successful_searches / total_searches) if total_searches > 0 else 0.0
    collection_success_rate_gauge.set(success_rate)
    rows_inserted_counter.add(total_rows_persisted)

    runtime_minutes = round(duration / 60.0, 1)
    total_rows_identified = total_rows_identity_known - total_rows_unidentified
    logger.info(
        f"[Scheduler] Ingestion Summary: Routes Processed: {total_routes_count} | "
        f"Searches: {total_searches}/{planned_searches} | Live+Stored: {routes_live} | "
        f"Empty: {routes_empty} | Provider errors: {routes_provider_error} | "
        f"Persistence errors: {routes_persistence_error} | Skipped: {searches_skipped} | "
        f"Retries: {total_retries} | Rows submitted: {total_rows_submitted} | "
        f"Rows stored: {total_rows_persisted} | With a curve identity: "
        f"{total_rows_identified}/{total_rows_identity_known} confirmed | "
        f"Runtime: {runtime_minutes}m"
    )

    # Pipeline failure checks. The gate now measures rows the database confirmed, so
    # it can actually fire — and it names which of the three failure modes happened
    # instead of reporting the same "zero observations" for all of them.
    if total_rows_persisted == 0:
        if routes_persistence_error:
            reason = (
                f"{total_rows_submitted} observation(s) were scraped from "
                f"{routes_persistence_error} route/date pair(s) but none were stored"
            )
        elif routes_provider_error == total_searches:
            reason = f"the provider failed on all {total_searches} search(es); nothing was scraped"
        elif routes_empty == total_searches:
            reason = f"the provider reported no flights on any of {total_searches} search(es)"
        else:
            reason = (
                f"no observations were stored ({routes_live} live, {routes_empty} empty, "
                f"{routes_provider_error} provider error(s))"
            )
        logger.error(f"[Scheduler] Ingestion completed with zero stored rows: {reason}.")
        raise RuntimeError(f"Ingestion failed: {reason}.")

    # The same gate, one step further in. Storing rows is not the job; storing rows
    # that can enter the label join is. Every observation without a complete
    # booking-curve identity is excluded from that join on both sides, so a run whose
    # entire confirmed output is unidentified grew the corpus by nothing that can ever
    # be trained on — which is a broken provider contract (no departure time on any
    # card), not a quiet market. Without this branch such a run passed the check
    # above, logged a healthy "Stored N observation(s)", and exited 0.
    if total_rows_identity_known > 0 and total_rows_identified <= 0:
        reason = (
            f"all {total_rows_identity_known} confirmed observation(s) carry an incomplete "
            f"booking-curve identity ({', '.join(BOOKING_CURVE_KEYS)}), so none of them "
            f"can ever be labelled; the provider returned no departure time on any card"
        )
        logger.error(f"[Scheduler] Ingestion stored no trainable observations: {reason}.")
        raise RuntimeError(f"Ingestion failed: {reason}.")

    if total_rows_unidentified:
        logger.error(
            "[Scheduler] %d of %d confirmed observation(s) (%.1f%%) have no complete "
            "booking-curve identity and can never be labelled.",
            total_rows_unidentified, total_rows_identity_known,
            100.0 * total_rows_unidentified / total_rows_identity_known,
        )

    if failed_searches:
        logger.error(
            f"[Scheduler] Ingestion run is incomplete: {routes_provider_error} provider "
            f"error(s) and {routes_persistence_error} persistence error(s) out of "
            f"{total_searches} search(es)."
        )

    # The last hole in this gate, and the reason it is a *rate* and not a count. The
    # two gates above fire on zero stored rows and on zero labellable rows. Neither
    # fires on a run that stored a handful: one live search out of 715 stores its rows,
    # clears both gates, and the block above logs an error that nothing acts on, so the
    # workflow still exits 0 and the day looks collected. A broken selector, an expired
    # session, a provider rate-limiting the scraper — all of them look like this.
    #
    # The rate is failures over searches, deliberately *not* live-over-searches. A
    # quiet market answers STATUS_EMPTY, which is a real answer and not a failure, so
    # gating on the live share would turn a genuinely quiet day red. Empty is excluded
    # from the numerator; a run that is empty all the way through stores nothing and is
    # already caught by the zero-rows gate above.
    max_failure_rate = min(1.0, max(0.0, float(os.getenv("SCHEDULER_MAX_SEARCH_FAILURE_RATE", "0.5"))))
    failure_rate = (failed_searches / total_searches) if total_searches > 0 else 0.0
    if total_searches > 0 and failure_rate > max_failure_rate:
        reason = (
            f"{failed_searches} of {total_searches} search(es) failed "
            f"({failure_rate:.1%}: {routes_provider_error} provider, "
            f"{routes_persistence_error} persistence), above the "
            f"{max_failure_rate:.0%} ceiling; the {total_rows_persisted} row(s) that "
            f"did store are not a representative day's collection"
        )
        logger.error(f"[Scheduler] Ingestion yield below threshold: {reason}.")
        raise RuntimeError(f"Ingestion failed: {reason}.")

    # Not a gate, because it cannot be told from a quiet market without duplicating the
    # judgement STATUS_EMPTY already encodes. Recorded because a parser that has started
    # returning "no flights" for pages that do list flights looks exactly like this, and
    # the shape is worth seeing in the log before it becomes a month of thin data.
    if total_searches > 0 and routes_empty > routes_live:
        logger.warning(
            "[Scheduler] %d of %d search(es) (%.1f%%) reported no flights, more than the "
            "%d that collected. Legitimate on a quiet day; if it persists, check the "
            "provider's parser against a page you can see flights on.",
            routes_empty, total_searches, 100.0 * routes_empty / total_searches, routes_live,
        )

    # 3. Snapshot Metadata
    from backend.services.historical_data_service import historical_data_service
    avg_latency = sum(provider_latencies) / len(provider_latencies) if provider_latencies else 0.0
    metadata = {
        "snapshot_id": snapshot_id,
        "search_id": search_id,
        # Names the transport actually used: the Google Flights scraper reached over
        # MCP. This said "LIVE_MAKEMYTRIP_MCP", which no code path can produce.
        "provider": "LIVE_GOOGLE_FLIGHTS_MCP",
        "provider_version": "1.0.0",
        "collector_version": "1.0.0",
        "schema_version": "2.0.0",
        "collection_timestamp": today.isoformat(),
        "execution_duration": duration,
        "provider_latency": avg_latency,
        "route_count": total_routes_count,
        "rows_inserted": total_rows_persisted,
        # This was the literal `True`, written next to a rows_inserted figure that
        # counted cache reads — a run that scraped nothing recorded itself as a
        # success. It is now derived from the run's own counters.
        "search_success": failed_searches == 0 and not out_of_time,
        "search_count": total_searches,
        "searches_planned": planned_searches,
        "searches_skipped": searches_skipped,
        "rows_submitted": total_rows_submitted,
        # Stored rows that can enter the label join, and those that cannot, out of the
        # rows whose split is known — a fully confirmed insert. Recorded so a later
        # reader can tell a run that grew the training corpus from one that only grew
        # the table, and `rows_identity_known` is published as the denominator so the
        # other two are never read against `rows_inserted` by mistake.
        "rows_identity_known": total_rows_identity_known,
        "rows_identified": total_rows_identified,
        "rows_unidentified": total_rows_unidentified,
        "routes_live": routes_live,
        "routes_empty": routes_empty,
        "routes_provider_error": routes_provider_error,
        "routes_persistence_error": routes_persistence_error,
        # The rate the yield gate measures, and the ceiling it was measured against,
        # stored together. Either one alone is unreadable later: the rate without the
        # ceiling cannot be judged, and the ceiling is an environment variable that may
        # have changed by the time anyone reads the row.
        "search_failure_rate": round(failure_rate, 4),
        "search_failure_rate_ceiling": max_failure_rate,
    }

    try:
        historical_data_service.insert_snapshot_metadata(metadata)
        snapshots_created_counter.add(1)
    except Exception as meta_err:
        # Recording the run is not the run. This call was unguarded, and because the
        # snapshot_metadata table does not exist yet it raised every time — turning a
        # successful ingestion into a failed job and skipping the summary below.
        logger.error(
            f"[Scheduler] Stored {total_rows_persisted} observation(s) but failed to record "
            f"snapshot metadata for {snapshot_id}: {meta_err}"
        )
    logger.info(
        f"[Scheduler] Ingestion batch complete. Stored {total_rows_persisted} observation(s) "
        f"from {routes_live} live search(es) across {total_routes_count} routes."
    )

def _collect_popular_routes() -> None:
    """Sync wrapper running in a thread-isolated event loop."""
    run_in_new_loop(_collect_popular_routes_async())

# ── PRICE ALERT CHECKER ───────────────────────────────────────────────

def _check_price_alerts() -> None:
    """Check active price alerts against latest prices. Runs inside an isolated event loop."""
    async def _check_price_alerts_async() -> None:
        logger.info("[Scheduler] Checking price alerts via live MCP search...")
        checked = failed = triggered = 0
        try:
            # These three imports read `services.`, `database.` and (in the retraining
            # job below) `ml.` — the bare top-level names, which only resolve because
            # main.py appends backend/ to sys.path. When they do resolve they import a
            # *second copy* of each module, with its own module-level singletons: a
            # second Supabase client, a second MCP gateway, and a circuit breaker whose
            # state the API path never sees. Import the same modules the rest of the
            # process imports.
            from backend.services.flight_data_service import (
                flight_data_service,
                STATUS_OK,
                STATUS_EMPTY,
            )
            from backend.services.notifications import dispatcher
            from backend.database.database import database as db

            res = (
                db.supabase.table("price_alerts")
                .select("*, profiles(email, phone, full_name, notify_email, notify_sms, notify_whatsapp)")
                .eq("is_active", True)
                .execute()
            )

            alerts = res.data or []
            if not alerts:
                logger.info("[Scheduler] No active price alerts found.")
                return

            for alert in alerts:
                try:
                    origin = alert.get("origin_code", "")
                    destination = alert.get("destination_code", "")
                    dep_date = alert.get("departure_date")

                    if not origin or not destination or not dep_date:
                        continue

                    raw_target = alert.get("target_price")
                    if raw_target is None:
                        # `float(alert.get("target_price", 0))` turned a missing target
                        # into 0, which no fare can undercut, so the alert silently
                        # never fired instead of being reported as unusable.
                        logger.error(f"Alert {alert.get('id')} has no target_price; skipping.")
                        failed += 1
                        continue
                    target_price = float(raw_target)
                    target_currency = (alert.get("currency") or "INR").upper()

                    # The alert's own parameters, which this call used to discard: it
                    # always searched a one-way ECONOMY fare for one adult and compared
                    # the result against a target the user had set for, say, a
                    # two-passenger BUSINESS round trip.
                    res_flights = await flight_data_service.search_flights(
                        origin=origin,
                        destination=destination,
                        target_date=str(dep_date),
                        adults=int(alert.get("adults") or 1),
                        children=int(alert.get("children") or 0),
                        cabin_class=(alert.get("cabin_class") or "ECONOMY"),
                        return_date=str(alert["return_date"]) if alert.get("return_date") else None,
                        currency=target_currency,
                    )

                    status = res_flights.get("status") if isinstance(res_flights, dict) else None
                    flights = res_flights.get("data") or [] if isinstance(res_flights, dict) else []

                    if status != STATUS_OK:
                        # "No flights returned" was logged for a broken scraper and for
                        # a quiet route alike, and in both cases the alert was skipped
                        # with the same warning. A failure is now reported as one.
                        if status == STATUS_EMPTY:
                            logger.info(
                                f"No flights on {origin}→{destination} for {dep_date}; "
                                "alert left unchanged."
                            )
                        else:
                            failed += 1
                            logger.error(
                                f"Alert {alert.get('id')} could not be checked: provider status "
                                f"{status!r} [{res_flights.get('error_kind') if isinstance(res_flights, dict) else None}] "
                                f"for {origin}→{destination} on {dep_date}."
                            )
                        continue

                    # Only fares actually quoted in the alert's currency may be compared
                    # against its target. A fare the transport could not convert (no FX
                    # rate configured) stays in the provider's currency, and comparing
                    # ~60 USD against a ~5000 INR target fires every alert at once.
                    prices = []
                    mismatched = 0
                    for f in flights:
                        if not isinstance(f, dict):
                            continue
                        raw_price = f.get("price")
                        if raw_price is None:
                            continue
                        if (f.get("currency") or target_currency).upper() != target_currency:
                            mismatched += 1
                            continue
                        try:
                            prices.append(float(raw_price))
                        except (TypeError, ValueError):
                            continue

                    if mismatched:
                        logger.error(
                            f"Alert {alert.get('id')}: {mismatched} fare(s) were not quoted in "
                            f"{target_currency} and were excluded from the comparison."
                        )

                    if not prices:
                        # `min(float(f.get("price", 99999)) for f in flights)` substituted
                        # 99999 for any flight without a price — a fabricated fare that
                        # was then written to price_alerts.last_price.
                        failed += 1
                        logger.error(
                            f"Alert {alert.get('id')}: provider returned {len(flights)} flight(s) "
                            f"but none carried a usable {target_currency} price."
                        )
                        continue

                    current_price = min(prices)
                    checked += 1

                    logger.info(
                        f"[Alert Checker] {origin}→{destination} on {dep_date}: live lowest="
                        f"{current_price} {target_currency}, target={target_price} {target_currency}"
                    )

                    lowest_seen = alert.get("lowest_seen")
                    update = {
                        "last_price": current_price,
                        "last_checked": datetime.now(timezone.utc).isoformat(),
                    }
                    if lowest_seen is None or current_price < float(lowest_seen):
                        update["lowest_seen"] = current_price
                    db.supabase.table("price_alerts").update(update).eq("id", alert.get("id")).execute()

                    if current_price <= target_price:
                        dispatcher.send_price_alert(alert, current_price)
                        triggered += 1
                        db.supabase.table("price_alerts").update({
                            "triggered_count": (alert.get("triggered_count") or 0) + 1,
                            "triggered_at": datetime.now(timezone.utc).isoformat(),
                        }).eq("id", alert.get("id")).execute()

                except Exception as alert_err:
                    failed += 1
                    logger.error(f"Error checking alert {alert.get('id')}: {alert_err}", exc_info=True)
                    continue

            logger.info(
                f"[Scheduler] Alert check complete: {checked} of {len(alerts)} priced, "
                f"{triggered} triggered, {failed} could not be checked."
            )

        except Exception as exc:
            logger.error(f"Alert check failed: {exc}", exc_info=True)

    run_in_new_loop(_check_price_alerts_async())

# ── MODEL RETRAINING ──────────────────────────────────────────────────

def _retrain_models() -> None:
    """Retrain XGBoost model on latest price history data. Runs inside an isolated event loop."""
    async def _retrain_models_async() -> None:
        logger.info("[Scheduler] Starting daily XGBoost retraining...")
        try:
            # `from ml.price_model import get_predictor` imported a *second copy* of the
            # module, with its own `_predictor` singleton. Retraining therefore trained
            # and loaded a model into an object the API never reads — the running app
            # kept serving whatever it had loaded at startup, and the log still said
            # the model had been retrained.
            from backend.ml.price_model import get_predictor
            predictor = get_predictor()
            report = predictor.train()
            if not (report or {}).get("trained"):
                # train() returns a report instead of None precisely so this cannot be
                # logged as a success. Every horizon can be rejected by the dataset
                # quality gate, in which case nothing was trained and nothing was written.
                logger.error(
                    "[Scheduler] Retraining trained no model — the dataset quality policy "
                    f"rejected every horizon: {(report or {}).get('rejected_horizons')}. "
                    "The previously loaded model is still in use."
                )
                return
            predictor.load()
            logger.info(
                "[Scheduler] Model retrained: horizons "
                f"{report.get('trained_horizons')} trained from {report.get('dataset_size')} "
                f"observation(s); rejected {report.get('rejected_horizons') or 'none'}."
            )
        except Exception as exc:
            logger.error(f"[Scheduler] Retraining failed: {exc}", exc_info=True)

    run_in_new_loop(_retrain_models_async())

# ── SCHEDULER STARTUP ─────────────────────────────────────────────────

def start_scheduler() -> None:
    if _scheduler.running:
        logger.info("Scheduler already running.")
        return

    _scheduler.start()
    
    is_prod = os.getenv("SERVER_ENV") == "production"
    
    if is_prod:
        logger.info("[Scheduler] Production mode: Daily jobs (Ingestion/Retraining) delegated to GitHub Actions.")
    else:
        # Schedule popular route collector every 6 hours
        _scheduler.add_job(
            _collect_popular_routes,
            IntervalTrigger(hours=6),
            id="popular_route_collector",
            replace_existing=True,
        )

        # Daily model retraining at 5am IST
        _scheduler.add_job(
            _retrain_models,
            CronTrigger(hour=5, minute=0),
            id="retrain_models",
            replace_existing=True,
        )

    # Price alert checks every 30 minutes
    _scheduler.add_job(
        _check_price_alerts,
        IntervalTrigger(minutes=30),
        id="check_alerts",
        replace_existing=True,
    )

    logger.info("[Scheduler] SkyMind background scheduler active.")
