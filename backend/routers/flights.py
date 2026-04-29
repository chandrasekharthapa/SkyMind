"""
SkyMind — Flights Router
Endpoints:
  GET /flights/search   → search flights (internal simulated data)
  GET /flights/airports → airport autocomplete

All Amadeus API dependencies removed. Uses self-contained FlightDataService.
"""

import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Query, HTTPException

from services.flight_data_service import flight_data_service, ROUTE_DURATIONS
from ml.price_model import get_predictor

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Lazy-load ML model ────────────────────────────────────────────────
def _model():
    try:
        return get_predictor()
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════
# Static airport data
# ══════════════════════════════════════════════════════════════════════

STATIC_AIRPORTS = [
    {"iata": "DEL", "city": "New Delhi",       "name": "Indira Gandhi International",       "country": "India"},
    {"iata": "BOM", "city": "Mumbai",          "name": "Chhatrapati Shivaji Maharaj Intl",  "country": "India"},
    {"iata": "BLR", "city": "Bengaluru",       "name": "Kempegowda International",          "country": "India"},
    {"iata": "MAA", "city": "Chennai",         "name": "Chennai International",             "country": "India"},
    {"iata": "HYD", "city": "Hyderabad",       "name": "Rajiv Gandhi International",        "country": "India"},
    {"iata": "CCU", "city": "Kolkata",         "name": "Netaji Subhas Chandra Bose Intl",   "country": "India"},
    {"iata": "COK", "city": "Kochi",           "name": "Cochin International",              "country": "India"},
    {"iata": "GOI", "city": "Goa",             "name": "Goa International Airport",         "country": "India"},
    {"iata": "AMD", "city": "Ahmedabad",       "name": "Sardar Vallabhbhai Patel Intl",     "country": "India"},
    {"iata": "JAI", "city": "Jaipur",          "name": "Jaipur International",              "country": "India"},
    {"iata": "LKO", "city": "Lucknow",         "name": "Chaudhary Charan Singh Intl",       "country": "India"},
    {"iata": "PNQ", "city": "Pune",            "name": "Pune Airport",                      "country": "India"},
    {"iata": "ATQ", "city": "Amritsar",        "name": "Sri Guru Ram Dass Jee Intl",        "country": "India"},
    {"iata": "BBI", "city": "Bhubaneswar",     "name": "Biju Patnaik International",        "country": "India"},
    {"iata": "IXR", "city": "Ranchi",          "name": "Birsa Munda Airport",               "country": "India"},
    {"iata": "PAT", "city": "Patna",           "name": "Jay Prakash Narayan Intl",          "country": "India"},
    {"iata": "VNS", "city": "Varanasi",        "name": "Lal Bahadur Shastri Intl",          "country": "India"},
    {"iata": "IDR", "city": "Indore",          "name": "Devi Ahilyabai Holkar Airport",     "country": "India"},
    {"iata": "BHO", "city": "Bhopal",          "name": "Raja Bhoj Airport",                 "country": "India"},
    {"iata": "TRV", "city": "Thiruvananthapuram", "name": "Trivandrum International",       "country": "India"},
    {"iata": "CCJ", "city": "Kozhikode",       "name": "Calicut International",             "country": "India"},
    {"iata": "CJB", "city": "Coimbatore",      "name": "Coimbatore International",          "country": "India"},
    {"iata": "GAU", "city": "Guwahati",        "name": "Lokpriya Gopinath Bordoloi Intl",   "country": "India"},
    {"iata": "IXE", "city": "Mangalore",       "name": "Mangalore International",           "country": "India"},
    {"iata": "SXR", "city": "Srinagar",        "name": "Sheikh ul-Alam International",      "country": "India"},
    {"iata": "IXL", "city": "Leh",             "name": "Kushok Bakula Rimpochhe Airport",   "country": "India"},
    {"iata": "DXB", "city": "Dubai",           "name": "Dubai International",               "country": "UAE"},
    {"iata": "LHR", "city": "London",          "name": "Heathrow Airport",                  "country": "UK"},
    {"iata": "SIN", "city": "Singapore",       "name": "Changi Airport",                    "country": "Singapore"},
    {"iata": "DOH", "city": "Doha",            "name": "Hamad International",               "country": "Qatar"},
]

CITY_TO_IATA = {
    "delhi": "DEL", "new delhi": "DEL",
    "mumbai": "BOM", "bombay": "BOM",
    "bangalore": "BLR", "bengaluru": "BLR",
    "hyderabad": "HYD",
    "chennai": "MAA", "madras": "MAA",
    "kolkata": "CCU", "calcutta": "CCU",
    "kochi": "COK", "cochin": "COK",
    "goa": "GOI",
    "ahmedabad": "AMD",
    "jaipur": "JAI",
    "lucknow": "LKO",
    "pune": "PNQ",
    "amritsar": "ATQ",
    "bhubaneswar": "BBI",
    "ranchi": "IXR",
    "patna": "PAT",
    "varanasi": "VNS",
    "dubai": "DXB",
    "london": "LHR",
    "singapore": "SIN",
    "doha": "DOH",
}


def _resolve_iata(code: str) -> str:
    if not code:
        return code
    stripped = code.strip().lower()
    return CITY_TO_IATA.get(stripped, stripped.upper())


# ══════════════════════════════════════════════════════════════════════
# ML enrichment
# ══════════════════════════════════════════════════════════════════════

def _enrich_with_ml(flights: list, origin: str, destination: str, departure_date: str) -> list:
    """Add AI price prediction and recommendation to each flight."""
    model = _model()
    if not model or not model._trained:
        return flights

    try:
        dep_date_obj = datetime.strptime(departure_date, "%Y-%m-%d").date()
        days_until_dep = max(0, (dep_date_obj - date.today()).days)

        for f in flights:
            try:
                base_price = f["price"]["total"]
                airline = f.get("primary_airline", "AI")
                internal = f.pop("_internal", {})

                predicted = model.predict({
                    "origin_code": origin,
                    "destination_code": destination,
                    "airline_code": airline,
                    "days_until_dep": days_until_dep,
                    "day_of_week": dep_date_obj.weekday(),
                    "month": dep_date_obj.month,
                    "week_of_year": dep_date_obj.isocalendar()[1],
                    "hour_of_day": 12,
                    "is_peak_hour": 0,
                    "is_live": 1,
                    "seats_available": f.get("seats_available") or 30,
                    "price_change_1d": 0,
                    "price_change_3d": 0,
                    "demand_score": 0.85 if days_until_dep < 7 else 0.5,
                    "seasonality_factor": 1.25 if dep_date_obj.month in [4, 5, 10, 12] else 1.0,
                })

                predicted = max(2800.0, min(float(predicted), 55000.0))
                f["ai_price"] = round(predicted)

                if predicted > base_price * 1.12:
                    f["recommendation"] = "BOOK NOW"
                    f["trend"] = "INCREASING"
                    f["decision"] = "BUY NOW"
                    f["advice"] = "Prices expected to rise — lock in this fare."
                elif predicted < base_price * 0.88:
                    f["recommendation"] = "WAIT"
                    f["trend"] = "DECREASING"
                    f["decision"] = "WAIT"
                    f["advice"] = "Model predicts a price drop soon."
                else:
                    f["recommendation"] = "FAIR PRICE"
                    f["trend"] = "STABLE"
                    f["decision"] = "FAIR"
                    f["advice"] = "Current price is within normal range."

            except Exception as exc:
                logger.debug(f"ML enrichment error for flight: {exc}")
                f.pop("_internal", None)
                f.setdefault("ai_price", f["price"]["total"])
                f.setdefault("recommendation", "MONITOR")
                f.setdefault("trend", "STABLE")

    except Exception as exc:
        logger.warning(f"ML enrichment batch error: {exc}")
        for f in flights:
            f.pop("_internal", None)

    return flights


# ══════════════════════════════════════════════════════════════════════
# GET /flights/search
# ══════════════════════════════════════════════════════════════════════

@router.get("/search")
async def search_flights(
    origin: str = Query(...),
    destination: str = Query(...),
    departure_date: str = Query(...),
    adults: int = Query(1, ge=1, le=9),
    children: int = Query(0, ge=0, le=9),
    infants: int = Query(0, ge=0, le=9),
    cabin_class: str = Query("ECONOMY"),
    max_results: int = Query(20, ge=1, le=50),
    return_date: Optional[str] = Query(None),
):
    origin_iata = _resolve_iata(origin)
    destination_iata = _resolve_iata(destination)

    if origin_iata == destination_iata:
        raise HTTPException(400, detail="Origin and destination cannot be the same")

    # Use internal simulated data service — always succeeds
    result = await flight_data_service.search_flights(
        origin=origin_iata,
        destination=destination_iata,
        departure_date=departure_date,
        adults=adults,
        children=children,
        infants=infants,
        cabin_class=cabin_class,
        max_results=max_results,
        return_date=return_date,
    )

    flights = result.get("flights", [])

    # De-duplicate by flight number + departure time
    seen: set = set()
    unique: list = []
    for f in flights:
        try:
            seg = f["itineraries"][0]["segments"][0]
            key = (seg["flight_number"], seg["departure_time"])
            if key not in seen:
                seen.add(key)
                unique.append(f)
        except Exception:
            unique.append(f)

    # Sort by price
    unique = sorted(unique, key=lambda x: x["price"]["total"])[:max_results]

    # ML enrichment
    unique = _enrich_with_ml(unique, origin_iata, destination_iata, departure_date)

    return {
        "flights": unique,
        "count": len(unique),
        "origin_iata": origin_iata,
        "destination_iata": destination_iata,
        "data_source": "SKYMIND_INTELLIGENCE",
    }


# ══════════════════════════════════════════════════════════════════════
# GET /flights/airports
# ══════════════════════════════════════════════════════════════════════

@router.get("/airports")
async def search_airports_flights(q: str = Query(..., min_length=1)):
    q_lower = q.lower().strip()
    results = [
        a for a in STATIC_AIRPORTS
        if q_lower in a["city"].lower()
        or q_lower in a["iata"].lower()
        or q_lower in a["name"].lower()
    ]
    results.sort(key=lambda x: (x["country"] != "India", x["iata"].lower() != q_lower))
    return {"airports": results[:10]}
