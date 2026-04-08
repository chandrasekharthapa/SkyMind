"""
SkyMind — Background Scheduler
Updated to support 2026 Weighted AI Retraining and Live Data Ingestion.
"""

import logging
import time
import asyncio
import random
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# Initialize scheduler with IST timezone
_scheduler = BackgroundScheduler(timezone="Asia/Kolkata")


# ── Route batches ─────────────────────────────────────────

ROUTE_BATCHES = [

    # 🔥 Batch 1
    [
        ("DEL", "BOM"), ("BOM", "DEL"),
        ("DEL", "BLR"), ("BLR", "DEL"),
        ("DEL", "HYD"), ("HYD", "DEL"),
    ],

    # 🔥 Batch 2
    [
        ("DEL", "CCU"), ("CCU", "DEL"),
        ("DEL", "MAA"), ("MAA", "DEL"),
        ("BOM", "BLR"), ("BLR", "BOM"),
    ],

    # 🔥 Batch 3
    [
        ("BOM", "HYD"), ("HYD", "BOM"),
        ("BLR", "HYD"), ("HYD", "BLR"),
        ("BLR", "MAA"), ("MAA", "BLR"),
    ],

    # 🔥 Batch 4
    [
        ("BOM", "MAA"), ("MAA", "BOM"),
        ("BBI", "DEL"), ("DEL", "BBI"),
        ("BBI", "BOM"), ("BOM", "BBI"),
    ],

    # 🔥 Batch 5
    [
        ("BBI", "BLR"), ("BLR", "BBI"),
        ("BBI", "HYD"), ("HYD", "BBI"),
        ("CCU", "BOM"), ("BOM", "CCU"),
    ],

    # 🔥 Batch 6
    [
        ("CCU", "BLR"), ("BLR", "CCU"),
        ("MAA", "HYD"), ("HYD", "MAA"),
    ],
]

# ✅ unchanged (as requested)
DATE_BUCKETS = [1, 2, 3, 4, 5, 6, 7, 9, 10, 14, 17, 20, 21, 25, 28, 30]


# ── 🔥 MMT SCRAPER TASK ───────────────────────────────────

def _collect_batch(batch_index: int) -> None:
    """🔥 Scrape MakeMyTrip for one batch (REAL DATA PIPELINE)"""
    logger.info(f"🛫 [MMT] Scraping batch {batch_index}...")

    try:
        from services.mmt_scraper import scrape_mmt
        from database.database import database as db

        routes = ROUTE_BATCHES[batch_index % len(ROUTE_BATCHES)]
        today = datetime.now(timezone.utc)

        # 🔥 Shuffle routes (anti-detection)
        random.shuffle(routes)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        for origin, destination in routes:
            for days_out in DATE_BUCKETS:

                target_date = (today + timedelta(days=days_out)).strftime("%Y-%m-%d")

                try:
                    data = loop.run_until_complete(
                        scrape_mmt(origin, destination, target_date)
                    )

                    if not data:
                        logger.warning(f"[MMT] No data for {origin}-{destination}")
                        continue

                    insert_batch = []

                    for row in data:
                        try:
                            price = float(row["price"])
                            if price < 1000:
                                continue

                            dep_date_obj = today + timedelta(days=days_out)
                            calc_urgency = round(1 / (days_out + 1), 4)

                            insert_batch.append({
                                "origin_code": origin,
                                "destination_code": destination,
                                "airline_code": row.get("airline_code", "AI"),
                                "flight_number": "UNK",
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
                                "seats_available": 50,
                                "recorded_at": datetime.now(timezone.utc).isoformat(),
                                "is_live": True,
                                "training_weight": 2.0,
                                "urgency": calc_urgency
                            })

                        except Exception:
                            continue

                    if insert_batch:
                        db.supabase.table("price_history").insert(insert_batch).execute()
                        logger.info(f"   ✅ [MMT] Saved {len(insert_batch)} rows for {origin}-{destination}")

                    # 🔥 Random delay (anti-block)
                    time.sleep(random.uniform(4, 7))

                except Exception as route_err:
                    logger.warning(f"[MMT] Route {origin}→{destination} failed: {route_err}")

        loop.close()

    except Exception as exc:
        logger.error(f"[MMT] Batch {batch_index} failed: {exc}")


# ── EXISTING TASKS (UNCHANGED) ───────────────────────────

def _check_price_alerts() -> None:
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

                db.supabase.table("price_alerts").update(
                    {"last_price": current_price}
                ).eq("id", alert["id"]).execute()

                if current_price <= target_price:
                    dispatcher.send_price_alert(alert, current_price)
                    db.supabase.table("price_alerts").update(
                        {"triggered_count": (alert.get("triggered_count") or 0) + 1}
                    ).eq("id", alert["id"]).execute()

            except Exception:
                continue

    except Exception as exc:
        logger.error(f"Alert check failed: {exc}")


def _retrain_models() -> None:
    logger.info("🤖 Starting Daily XGBoost Retraining...")
    try:
        from ml.price_model import get_predictor
        predictor = get_predictor()

        predictor.train()
        predictor.load()

        logger.info("✅ SkyMind AI updated with latest data.")
    except Exception as exc:
        logger.error(f"Retraining failed: {exc}")


# ── STARTUP ─────────────────────────────────────────────

def start_scheduler() -> None:
    if _scheduler.running:
        logger.info("Scheduler already running.")
        return

    for i in range(len(ROUTE_BATCHES)):
        _scheduler.add_job(
            _collect_batch,
            CronTrigger(hour=1 + i // 3, minute=(i * 20) % 60),
            args=[i],
            id=f"collect_batch_{i}",
            replace_existing=True,
        )

    _scheduler.add_job(
        _check_price_alerts,
        IntervalTrigger(minutes=30),
        id="check_alerts",
        replace_existing=True,
    )

    _scheduler.add_job(
        _retrain_models,
        CronTrigger(hour=5, minute=0),
        id="retrain_models",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("🚀 SkyMind Background Scheduler active.")