import asyncio
import json
from backend.services.flight_search_service import flight_search_service
from backend.services.flight_data_service import flight_data_service

async def trace_search():
    print("=== STEP 1: Calling flight_data_service.search_flights() ===")
    try:
        raw_res = await flight_data_service.search_flights(
            origin="DEL",
            destination="BOM",
            target_date="2026-08-15",
            adults=1,
            cabin_class="ECONOMY"
        )
        print(f"Raw MCP result keys: {list(raw_res.keys())}")
        raw_flights = raw_res.get("data", [])
        print(f"Raw MCP flights count: {len(raw_flights)}")
        if raw_flights:
            print("Sample raw flight:", json.dumps(raw_flights[0], indent=2))
    except Exception as e:
        print(f"Raw search exception: {e}")

    print("\n=== STEP 2: Calling flight_search_service.search() ===")
    try:
        presentation = await flight_search_service.search(
            origin_iata="DEL",
            destination_iata="BOM",
            departure_date="2026-08-15"
        )
        print(f"Presentation status: data_source={getattr(presentation, 'data_source', 'N/A')}")
        flights = getattr(presentation, "flights", [])
        print(f"Presentation flights count: {len(flights)}")
        if flights:
            sample = flights[0].model_dump() if hasattr(flights[0], "model_dump") else flights[0]
            print("Sample presentation flight:", json.dumps(sample, indent=2))
    except Exception as e:
        print(f"Flight search service exception: {e}")

if __name__ == "__main__":
    asyncio.run(trace_search())
