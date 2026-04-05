"""
SkyMind — Background Scheduler
Updated to support 2026 Weighted AI Retraining and Live Data Ingestion.
"""

import logging
import time
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# Initialize scheduler with IST timezone for consistent 2026 operations
_scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

# ── Route batches for nightly price scraping ─────────────────────────
ROUTE_BATCHES = [
    [("DEL", "BOM"), ("BOM", "DEL"), ("DEL", "BLR")],
    [("BLR", "DEL"), ("DEL", "CCU"), ("CCU", "DEL")],
    [("BBI", "DEL"), ("DEL", "BBI"), ("BOM", "BLR")],
    [("BLR", "BOM"), ("DEL", "HYD"), ("HYD", "DEL")],
    [("COK", "DEL"), ("DEL", "COK"), ("BOM", "MAA")],
]

DATE_BUCKETS = [1, 2, 3, 5, 7, 10, 14, 21, 28, 30]


# ── Tasks ─────────────────────────────────────────────────────────────

def _collect_batch(batch_index: int) -> None:
    """Scrape Amadeus for one batch of routes + date buckets."""
    logger.info(f"📋 Scraping batch {batch_index}…")
    try:
        import asyncio
        from services.amadeus import amadeus_service
        from database.database import database as db

        routes = ROUTE_BATCHES[batch_index % len(ROUTE_BATCHES)]
        today = datetime.now(timezone.utc).date()

        # Using a fresh event loop for the background thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        for origin, destination in routes:
            for days_out in DATE_BUCKETS:
                target = (today + timedelta(days=days_out)).strftime("%Y-%m-%d")
                try:
                    raw = loop.run_until_complete(
                        amadeus_service.search_flights(origin, destination, target, max_results=5)
                    )
                    
                    # 🎯 INTEGRATED: Use the new amadeus_service formatter
                    # This ensures is_live=True and urgency are set correctly
                    formatted_flights = amadeus_service.format_for_skymind(raw)
                    
                    for flight in formatted_flights:
                        try:
                            # 2026 Safety Check: Ignore garbage data
                            if flight["price"] < 1000:
                                continue
                                
                            # Insert into price_history for ML training
                            db.supabase.table("price_history").insert({
                                "origin_code": flight["origin_code"],
                                "destination_code": flight["destination_code"],
                                "airline_code": flight["airline_code"],
                                "price": flight["price"],
                                "currency": "INR",
                                "departure_date": flight["departure_date"],
                                "days_until_dep": flight["days_until_dep"],
                                "urgency": flight["urgency"],
                                "is_live": True,  # ⚡ Crucial for weighted priority
                                "is_weekend": flight["days_until_dep"] % 7 >= 5, # Simple check
                                "recorded_at": datetime.now(timezone.utc).isoformat(),
                            }).execute()
                        except Exception as row_err:
                            logger.debug(f"Row skip: {row_err}")
                            
                    # Respect Amadeus Rate Limits
                    time.sleep(1.5)
                    
                except Exception as route_err:
                    logger.warning(f"Route {origin}→{destination}: {route_err}")

        loop.close()
    except Exception as exc:
        logger.error(f"Batch {batch_index} failed: {exc}")


def _check_price_alerts() -> None:
    """Check all active price alerts and fire notifications if triggered."""
    logger.info("⏰ Checking price alerts…")
    try:
        from services.notifications import dispatcher
        from database.database import database as db

        res = (
            db.supabase.table("price_alerts")
            .select("*, profiles(email, phone, full_name, notify_email, notify_sms, notify_whatsapp)")
            .eq("is_active", True)
            .execute()
        )

        for alert in res.data or []:
            try:
                # Get latest price from price_history
                ph = (
                    db.supabase.table("price_history")
                    .select("price")
                    .eq("origin_code", alert["origin_code"])
                    .eq("destination_code", alert["destination_code"])
                    .order("recorded_at", desc=True)
                    .limit(1)
                    .execute()
                )
                if not ph.data:
                    continue

                current_price = float(ph.data[0]["price"])
                target_price = float(alert["target_price"])

                # Update last_price in the alert record
                db.supabase.table("price_alerts").update(
                    {"last_price": current_price}
                ).eq("id", alert["id"]).execute()

                # Trigger notification if price dropped below target
                if current_price <= target_price:
                    dispatcher.send_price_alert(alert, current_price)
                    db.supabase.table("price_alerts").update(
                        {"triggered_count": (alert.get("triggered_count") or 0) + 1}
                    ).eq("id", alert["id"]).execute()

            except Exception as alert_err:
                logger.debug(f"Alert check error: {alert_err}")

    except Exception as exc:
        logger.error(f"Alert check failed: {exc}")


def _retrain_models() -> None:
    """
    🤖 DAILY AI EVOLUTION
    Retrains the XGBoost model using the new 'is_live' weighted logic.
    """
    logger.info("🤖 Starting Daily XGBoost Retraining...")
    try:
        from ml.price_model import get_predictor
        predictor = get_predictor()
        
        # 1. Run the training process with weighted 2026 data
        predictor.train()
        
        # 2. Reload the new .pkl file into memory
        predictor.load()
        
        logger.info("✅ SkyMind AI has been successfully updated with the latest market data.")
    except Exception as exc:
        logger.error(f"Retraining failed: {exc}")


# ── Startup ───────────────────────────────────────────────────────────

def start_scheduler() -> None:
    if _scheduler.running:
        logger.info("Scheduler already running.")
        return

    # 1. Staggered batch scraping (Nightly)
    for i in range(len(ROUTE_BATCHES)):
        _scheduler.add_job(
            _collect_batch,
            CronTrigger(hour=1 + i // 3, minute=(i * 20) % 60),
            args=[i],
            id=f"collect_batch_{i}",
            replace_existing=True,
        )

    # 2. Price alert polling (Every 30 minutes)
    _scheduler.add_job(
        _check_price_alerts,
        IntervalTrigger(minutes=30),
        id="check_alerts",
        replace_existing=True,
    )

    # 3. Daily AI Retraining (05:00 IST)
    # This ensures your AI 'wakes up' every morning smarter than it was yesterday.
    _scheduler.add_job(
        _retrain_models,
        CronTrigger(hour=5, minute=0),
        id="retrain_models",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("🚀 SkyMind Background Scheduler active.")