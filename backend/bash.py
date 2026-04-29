"""
SkyMind — Manual Data Ingestion Script
Generates and persists synthetic flight price data using the internal
FlightDataService. Replaces former Amadeus API scraper.
Run: python bash.py
"""

import asyncio
import sys
import logging
from datetime import datetime, timedelta, timezone

# ==========================================
# 📋 STRATEGIC CONFIGURATION
# ==========================================

STRATEGIC_ROUTES = [
    ("BBI", "DEL"), ("DEL", "BBI"),
    ("BBI", "BOM"), ("BOM", "BBI"),
    ("DEL", "BOM"), ("BOM", "DEL"),
    ("DEL", "BLR"), ("BLR", "DEL"),
    ("CCU", "DEL"), ("DEL", "CCU"),
    ("MAA", "DEL"), ("DEL", "MAA"),
    ("BBI", "BLR"), ("BLR", "BBI"),
    ("DEL", "DXB"), ("DXB", "DEL"),
    ("BOM", "DXB"), ("DXB", "BOM"),
]

# Days out to generate data for — matches real booking patterns
DATE_INTERVALS = [1, 2, 3, 5, 7, 10, 14, 21, 28, 30]

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("SkyMind-Ingest")


# ==========================================
# INGESTION ENGINE
# ==========================================

async def run_ingestion():
    from services.flight_data_service import flight_data_service
    from database.database import database as db

    today = datetime.now(timezone.utc)
    total_segments = len(STRATEGIC_ROUTES) * len(DATE_INTERVALS)

    logger.info("[SkyMind] Starting manual synthetic data ingestion...")
    logger.info(f"Targets: {total_segments} route-date combinations")
    logger.info("-" * 60)

    count = 0
    total_inserted = 0

    for origin, destination in STRATEGIC_ROUTES:
        for days_out in DATE_INTERVALS:
            count += 1
            target_date = (today + timedelta(days=days_out)).strftime("%Y-%m-%d")

            try:
                logger.info(
                    f"[{count}/{total_segments}] {origin} ➔ {destination} | "
                    f"{target_date} | {days_out}d out"
                )

                # Generate synthetic records
                records = flight_data_service.format_for_training(
                    origin=origin,
                    destination=destination,
                    departure_date=target_date,
                )

                if records:
                    db.supabase.table("price_history").insert(records).execute()
                    total_inserted += len(records)
                    logger.info(f"   Inserted {len(records)} records")
                else:
                    logger.warning(f"   No records generated")

            except Exception as e:
                logger.error(f"   Failed: {e}")

    logger.info("-" * 60)
    logger.info(f"INGESTION COMPLETE: {total_inserted} records persisted to Supabase.")


if __name__ == "__main__":
    try:
        asyncio.run(run_ingestion())
    except KeyboardInterrupt:
        logger.info("\nUser stopped the process.")
        sys.exit(0)
