import asyncio
import json
from collections import Counter
from backend.services.flight_data_service import flight_data_service

async def analyze():
    res = await flight_data_service.search_flights(
        origin="DEL",
        destination="BOM",
        target_date="2026-08-15",
        adults=1
    )
    raw_flights = res.get("data", [])
    print(f"Total raw flights returned from Google Flights MCP: {len(raw_flights)}")
    
    airlines = Counter([f.get("airline_name") or f.get("primary_airline") for f in raw_flights])
    stops = Counter([f.get("stops") for f in raw_flights])
    fl_numbers = Counter([f.get("flight_number") for f in raw_flights])
    durations = Counter([f.get("duration_minutes") or f.get("duration") for f in raw_flights])
    
    print("\nAirlines distribution:", dict(airlines))
    print("Stops distribution:", dict(stops))
    print("Flight numbers distribution:", dict(fl_numbers))
    print("Durations distribution (mins):", dict(durations))

if __name__ == "__main__":
    asyncio.run(analyze())
