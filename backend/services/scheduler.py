"""
SkyMind — Background Scheduler
Updated for self-contained data pipeline (no external APIs).
Handles: price alert checking, model retraining, synthetic data ingestion.
"""

import logging
import asyncio
import random
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

# Route batches for synthetic data ingestion
ROUTE_BATCHES = [
    [("BBI", "DEL"), ("DEL", "BBI"), ("BBI", "BOM"), ("BOM", "BBI"), ("DEL", "BOM"), ("BOM", "DEL")],
    [("DEL", "BLR"), ("BLR", "DEL"), ("DEL", "HYD"), ("HYD", "DEL"), ("BOM", "BLR"), ("BLR", "BOM")],
    [("DEL", "MAA"), ("MAA", "DEL"), ("DEL", "CCU"), ("CCU", "DEL"), ("BOM", "HYD"), ("HYD", "BOM")],
    [("BOM", "MAA"), ("MAA", "BOM"), ("BLR", "HYD"), ("HYD", "BLR"), ("BLR", "MAA"), ("MAA", "BLR")],
    [("DEL", "DXB"), ("DXB", "DEL"), ("BOM", "DXB"), ("DXB", "BOM"), ("DEL", "SIN"), ("SIN", "DEL")],
    [("DEL", "DOH"), ("DOH", "DEL"), ("DEL", "LHR"), ("LHR", "DEL"), ("BOM", "SIN"), ("SIN", "BOM")],
]

DATE_BUCKETS = [1, 2, 3, 5, 7, 10, 14, 21, 28, 30]


# ── SYNTHETIC DATA INGESTION ──────────────────────────────────────────

def _ingest_synthetic_batch(batch_index: int) -> None:
    """
    Generate synthetic price data and persist to Supabase price_history.
    Replaces the former Amadeus/MMT scraper jobs.
    Uses the internal FlightDataService — always succeeds.
    """
    logger.info(f"[Scheduler] Ingesting synthetic data batch {batch_index}...")

    try:
        from services.flight_data_service import flight_data_service
        from database.database import database as db

        routes = ROUTE_BATCHES[batch_index % len(ROUTE_BATCHES)]
        today = datetime.now(timezone.utc)

        random.shuffle(routes)

        for origin, destination in routes:
            for days_out in DATE_BUCKETS:
                target_date = (today + timedelta(days=days_out)).strftime("%Y-%m-%d")

                try:
                    # Generate training records for this route+date
                    records = flight_data_service.format_for_training(
                        origin=origin,
                        destination=destination,
                        departure_date=target_date,
                    )

                    if records:
                        db.supabase.table("price_history").insert(records).execute()
                        logger.debug(
                            f"   Ingested {len(records)} records: {origin}→{destination} on {target_date}"
                        )

                except Exception as route_err:
                    logger.warning(
                        f"   Batch {batch_index} route {origin}→{destination}: {route_err}"
                    )

        logger.info(f"[Scheduler] Batch {batch_index} complete.")

    except Exception as exc:
        logger.error(f"[Scheduler] Batch {batch_index} failed: {exc}")


# ── PRICE ALERT CHECKER ───────────────────────────────────────────────

def _check_price_alerts() -> None:
    """
    Check active price alerts against latest synthetic prices.
    Sends notifications when target price is reached.
    """
    logger.info("[Scheduler] Checking price alerts...")
    try:
        from services.notifications import dispatcher
        from services.flight_data_service import flight_data_service, ROUTE_BASE_PRICES
        from database.database import database as db
        from datetime import date

        res = (
            db.supabase.table("price_alerts")
            .select("*, profiles(email, phone, full_name, notify_email, notify_sms, notify_whatsapp)")
            .eq("is_active", True)
            .execute()
        )

        today = date.today()

        for alert in res.data or []:
            try:
                origin = alert.get("origin_code", "")
                destination = alert.get("destination_code", "")
                dep_date = alert.get("departure_date")

                if not origin or not destination:
                    continue

                # Get estimated current price from synthetic engine
                if dep_date:
                    try:
                        dep_date_obj = datetime.strptime(str(dep_date), "%Y-%m-%d").date()
                        days_until = max(0, (dep_date_obj - today).days)
                    except Exception:
                        days_until = 30
                else:
                    days_until = 30

                # Use base price with urgency factor as current price estimate
                base = ROUTE_BASE_PRICES.get((origin, destination), 5000)
                urgency_factor = 1.0 + max(0, (7 - days_until) / 7) * 0.35
                current_price = round(base * urgency_factor / 50) * 50

                target_price = float(alert.get("target_price", 0))

                # Update last known price
                db.supabase.table("price_alerts").update(
                    {"last_price": current_price}
                ).eq("id", alert["id"]).execute()

                # Trigger notification if target met
                if current_price <= target_price:
                    dispatcher.send_price_alert(alert, current_price)
                    db.supabase.table("price_alerts").update(
                        {"triggered_count": (alert.get("triggered_count") or 0) + 1}
                    ).eq("id", alert["id"]).execute()

            except Exception as alert_err:
                logger.debug(f"Alert processing error: {alert_err}")
                continue

    except Exception as exc:
        logger.error(f"Alert check failed: {exc}")


# ── MODEL RETRAINING ──────────────────────────────────────────────────

def _retrain_models() -> None:
    """Retrain XGBoost model on latest price history data."""
    logger.info("[Scheduler] Starting daily XGBoost retraining...")
    try:
        from ml.price_model import get_predictor
        predictor = get_predictor()
        predictor.train()
        predictor.load()
        logger.info("[Scheduler] Model retrained successfully.")
    except Exception as exc:
        logger.error(f"[Scheduler] Retraining failed: {exc}")


# ── SCHEDULER STARTUP ─────────────────────────────────────────────────

def start_scheduler() -> None:
    if _scheduler.running:
        logger.info("Scheduler already running.")
        return

    # Synthetic data ingestion — staggered across the day
    for i in range(len(ROUTE_BATCHES)):
        _scheduler.add_job(
            _ingest_synthetic_batch,
            CronTrigger(hour=2 + i, minute=15),
            args=[i],
            id=f"ingest_batch_{i}",
            replace_existing=True,
        )

    # Price alert checks every 30 minutes
    _scheduler.add_job(
        _check_price_alerts,
        IntervalTrigger(minutes=30),
        id="check_alerts",
        replace_existing=True,
    )

    # Daily model retraining at 5am IST
    _scheduler.add_job(
        _retrain_models,
        CronTrigger(hour=5, minute=0),
        id="retrain_models",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("[Scheduler] SkyMind background scheduler active.")
