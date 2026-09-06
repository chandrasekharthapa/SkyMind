import asyncio
import json
from collections import Counter
from backend.services.flight_data_service import flight_data_service
from backend.services.flight_search_service import flight_search_service
from backend.services.flight_normalizer import FlightNormalizer

async def run_full_verification():
    print("=================================================================")
    print("STEP 1: RAW PROVIDER LAYER (Google Flights MCP Scraper)")
    print("=================================================================")
    mcp_res = await flight_data_service.search_flights(
        origin="DEL",
        destination="BOM",
        target_date="2026-08-15",
        adults=1
    )
    raw_flights = mcp_res.get("data", [])
    raw_count = len(raw_flights)
    raw_airlines = Counter([f.get("airline_name") or f.get("primary_airline") for f in raw_flights])
    raw_stops = Counter([f.get("stops") for f in raw_flights])
    raw_fl_nums = Counter([f.get("flight_number") for f in raw_flights])
    
    print(f"Raw Provider Flights Count: {raw_count}")
    print(f"Raw Airlines: {dict(raw_airlines)}")
    print(f"Raw Stops: {dict(raw_stops)}")
    print(f"Raw Flight Numbers Sample: {list(raw_fl_nums.keys())[:10]}")

    print("\n=================================================================")
    print("STEP 2: NORMALIZATION LAYER (FlightNormalizer.normalize_mcp_flight)")
    print("=================================================================")
    normalized_list = []
    for f in raw_flights:
        norm = FlightNormalizer.normalize_mcp_flight(f, "DEL", "BOM", "2026-08-15")
        if norm:
            normalized_list.append(norm)
            
    norm_count = len(normalized_list)
    norm_airlines = Counter([f.primary_airline_name for f in normalized_list])
    norm_stops = Counter([f.itineraries[0].segments[0].stops for f in normalized_list])
    norm_durations = Counter([f.itineraries[0].duration for f in normalized_list])
    
    print(f"Normalized Flights Count: {norm_count}")
    print(f"Normalized Airlines: {dict(norm_airlines)}")
    print(f"Normalized Stops: {dict(norm_stops)}")
    print(f"Normalized Durations: {dict(norm_durations)}")

    print("\n=================================================================")
    print("STEP 3: DEDUPLICATION LAYER (FlightNormalizer.deduplicate_flights)")
    print("=================================================================")
    deduped_list = FlightNormalizer.deduplicate_flights(normalized_list)
    dedup_count = len(deduped_list)
    dedup_airlines = Counter([f.primary_airline_name for f in deduped_list])
    print(f"Deduplicated Flights Count: {dedup_count}")
    print(f"Deduplicated Airlines: {dict(dedup_airlines)}")

    print("\n=================================================================")
    print("STEP 4: SEARCH SERVICE & API RESPONSE LAYER (FlightSearchPresentation)")
    print("=================================================================")
    presentation = await flight_search_service.search(
        origin_iata="DEL",
        destination_iata="BOM",
        departure_date="2026-08-15",
        max_results=60
    )
    api_flights = presentation.flights
    api_count = len(api_flights)
    api_airlines = Counter([f.primary_airline_name for f in api_flights])
    api_stops = Counter([f.itineraries[0].segments[0].stops for f in api_flights])
    api_durations = Counter([f.itineraries[0].duration for f in api_flights])
    
    print(f"API Flights Count: {api_count}")
    print(f"API Airlines: {dict(api_airlines)}")
    print(f"API Stops: {dict(api_stops)}")
    print(f"API Durations: {dict(api_durations)}")

    # Verification Assertions
    print("\n=================================================================")
    print("STEP 5: LAYER COMPARISON & INTEGRITY VERIFICATION SUMMARY")
    print("=================================================================")
    print(f"Provider -> Parser:     {raw_count} -> {norm_count} (Loss: {raw_count - norm_count})")
    print(f"Parser -> Deduplication: {norm_count} -> {dedup_count} (Loss: {norm_count - dedup_count})")
    print(f"Deduplication -> API:   {dedup_count} -> {api_count} (Loss: {dedup_count - api_count})")

if __name__ == "__main__":
    asyncio.run(run_full_verification())
