"""
SkyMind — Background Scheduler
Updated to support 2026 Weighted AI Retraining and Live Data Ingestion.
"""

import logging
import time
import asyncio
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# Initialize scheduler with IST timezone for consistent 2026 operations
_scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

# ── Route batches for nightly price scraping ─────────────────────────
# These are grouped to spread the API load across the early morning hours
ROUTE_BATCHES = [
    [("BBI", "DEL"), ("DEL", "BBI"), ("DEL", "BLR")],
    [("BLR", "DEL"), ("DEL", "CCU"), ("CCU", "DEL")],
    [("BBI", "BOM"), ("BOM", "BBI"), ("BOM", "BLR")],
    [("BLR", "BOM"), ("DEL", "HYD"), ("HYD", "DEL")],
    [("COK", "DEL"), ("DEL", "COK"), ("BBI", "BLR"), ("BLR", "BBI")],
]

# Teaching the AI the 2026 Price-Velocity curve
DATE_BUCKETS = [1, 2, 3, 5, 7, 10, 14, 21, 28, 30]

# ── Tasks ─────────────────────────────────────────────────────────────

def _collect_batch(batch_index: int) -> None:
    """Scrape Amadeus for one batch with Dynamic Urgency & 2.0x Weight"""
    logger.info(f"📋 Scraping batch {batch_index}...")
    try:
        from services.amadeus import amadeus_service
        from database.database import database as db

        routes = ROUTE_BATCHES[batch_index % len(ROUTE_BATCHES)]
        today = datetime.now(timezone.utc)

        # 💡 CRITICAL: New event loop for the background thread to handle async calls
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        for origin, destination in routes:
            for days_out in DATE_BUCKETS:
                target_date = (today + timedelta(days=days_out)).strftime("%Y-%m-%d")
                
                try:
                    # Fetch raw data using the async service
                    raw = loop.run_until_complete(
                        amadeus_service.search_flights(origin, destination, target_date, max_results=5)
                    )
                    
                    flights = raw.get("data", [])
                    if not flights:
                        continue

                    insert_batch = []
                    for flight in flights:
                        try:
                            price = float(flight["price"]["total"])
                            if price < 1000: continue # 2026 Safety Check

                            itinerary = flight["itineraries"][0]["segments"][0]
                            dep_date_obj = today + timedelta(days=days_out)

                            # 🎯 DYNAMIC URGENCY: 1 / (days_until_dep + 1)
                            # Matches the logic in PricePredictor.train()
                            calc_urgency = round(1 / (days_out + 1), 4)

                            insert_batch.append({
                                "origin_code": origin,
                                "destination_code": destination,
                                "airline_code": itinerary["carrierCode"],
                                "flight_number": f"{itinerary['carrierCode']}{itinerary['number']}",
                                "cabin_class": "Economy",
                                "price": price,
                                "currency": "INR",
                                "departure_date": target_date,
                                "days_until_dep": days_out,
                                "day_of_week": dep_date_obj.weekday(),
                                "month": dep_date_obj.month,
                                "week_of_year": dep_date_obj.isocalendar()[1],
                                "is_holiday": False,
                                "is_weekend": dep_date_obj.weekday() >= 5,
                                "seats_available": int(flight.get("numberOfBookableSeats", 9)),
                                "recorded_at": datetime.now(timezone.utc).isoformat(),
                                "is_live": True,
                                "training_weight": 2.0,  # 🔥 Priority weighting for 2026 AI
                                "urgency": calc_urgency  # ✅ Engineered feature for ML
                            })
                        except (KeyError, IndexError):
                            continue

                    if insert_batch:
                        db.supabase.table("price_history").insert(insert_batch).execute()
                        logger.info(f"   ✅ Saved {len(insert_batch)} flights for {origin}-{destination}")
                    
                    # Respect Amadeus Rate Limits (especially for Test environment)
                    time.sleep(2.2)
                    
                except Exception as route_err:
                    logger.warning(f"Route {origin}→{destination} failed: {route_err}")

        loop.close()
    except Exception as exc:
        logger.error(f"Batch {batch_index} failed: {exc}")


def _check_price_alerts() -> None:
    """Check all active price alerts and fire notifications if triggered."""
    logger.info("⏰ Checking price alerts...")
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

                # Update last_price in the alert record for UI feedback
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
    """🤖 DAILY AI EVOLUTION: Retrains XGBoost with latest weighted data."""
    logger.info("🤖 Starting Daily XGBoost Retraining...")
    try:
        from ml.price_model import get_predictor
        predictor = get_predictor()
        
        # Train and Reload
        predictor.train()
        predictor.load()
        
        logger.info("✅ SkyMind AI updated with the latest market data.")
    except Exception as exc:
        logger.error(f"Retraining failed: {exc}")


# ── Startup ───────────────────────────────────────────────────────────

def start_scheduler() -> None:
    if _scheduler.running:
        logger.info("Scheduler already running.")
        return

    # 1. Staggered batch scraping (Nightly starting at 01:00 AM IST)
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

    # 3. Daily AI Retraining (05:00 AM IST)
    # This ensures your AI stays sharp on 2026 trends.
    _scheduler.add_job(
        _retrain_models,
        CronTrigger(hour=5, minute=0),
        id="retrain_models",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("🚀 SkyMind Background Scheduler active.")