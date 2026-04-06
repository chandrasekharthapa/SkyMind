import asyncio
import sys
import logging
from datetime import datetime, timedelta, timezone
from services.amadeus import amadeus_service

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
    ("BBI", "BLR"), ("BLR", "BBI")
]

# Teaching SkyMind the 2026 Price-Velocity curve
# 1, 2, 3 days out are critical for "High Urgency" learning
DATE_INTERVALS = [1, 2, 3, 5, 7, 10, 14, 21, 28, 30]

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("SkyMind-Manual")

# ==========================================
# 🚀 THE SCRAPER ENGINE
# ==========================================

async def run_meaningful_fetch():
    from database.database import database as db
    
    today = datetime.now(timezone.utc)
    total_segments = len(STRATEGIC_ROUTES) * len(DATE_INTERVALS)
    
    logger.info(f"🚀 [SkyMind] Starting Manual Ingestion...")
    logger.info(f"📊 Targets: {total_segments} segments | Training Weight: 2.0")
    logger.info("-" * 60)

    count = 0
    for origin, destination in STRATEGIC_ROUTES:
        for days_out in DATE_INTERVALS:
            count += 1
            dep_date_obj = today + timedelta(days=days_out)
            target_date = dep_date_obj.strftime("%Y-%m-%d")
            
            try:
                logger.info(f"🔍 [{count}/{total_segments}] {origin} ➔ {destination} | {target_date}")
                
                # Call Amadeus
                raw_data = await amadeus_service.search_flights(
                    origin=origin, 
                    destination=destination, 
                    departure_date=target_date, 
                    max_results=5
                )
                
                flights = raw_data.get("data", [])
                if not flights:
                    continue

                insert_batch = []
                for flight in flights:
                    try:
                        price = float(flight["price"]["total"])
                        if price < 1000: continue

                        itinerary = flight["itineraries"][0]["segments"][0]

                        # 🎯 DYNAMIC URGENCY CALCULATION
                        # This matches the logic in PricePredictor.train()
                        # Formula: 1 / (days_until_dep + 1)
                        calculated_urgency = round(1 / (days_out + 1), 4)

                        record = {
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
                            "training_weight": 2.0,
                            "urgency": calculated_urgency  # ✅ Now properly engineered
                        }
                        insert_batch.append(record)
                    except (KeyError, IndexError):
                        continue
                
                if insert_batch:
                    db.supabase.table("price_history").insert(insert_batch).execute()
                    logger.info(f"   ✅ Success: {len(insert_batch)} flights synced (Urgency: {calculated_urgency})")
                
                await asyncio.sleep(2.2) 
                
            except Exception as e:
                logger.error(f"   ❌ Failed: {e}")
                await asyncio.sleep(5)

    logger.info("-" * 60)
    logger.info("✨ MANUAL BATCH COMPLETE: Proper urgency signals are now in Supabase.")

if __name__ == "__main__":
    try:
        asyncio.run(run_meaningful_fetch())
    except KeyboardInterrupt:
        logger.info("\n🛑 User stopped the process.")
        sys.exit(0)