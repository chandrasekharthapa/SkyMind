"""
SkyMind — Flights Router
Endpoints:
  GET /flights/search   → search flights (Amadeus → synthetic fallback)
  GET /flights/airports → airport autocomplete
"""

import logging
import os
import random
import traceback
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Query, HTTPException
from database.database import database as db
from ml.price_model import get_predictor

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Lazy-load model to avoid import-time crash ─────────────────────
def _model():
    try:
        return get_predictor()
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════
# Static data
# ══════════════════════════════════════════════════════════════════════

AIRLINE_MAP = {
    "AI": "Air India", "6E": "IndiGo", "UK": "Vistara", "SG": "SpiceJet",
    "IX": "Air India Express", "QP": "Akasa Air", "S5": "Star Air",
    "EK": "Emirates", "SQ": "Singapore Airlines", "QR": "Qatar Airways",
    "EY": "Etihad Airways", "BA": "British Airways", "FZ": "flydubai",
    "G9": "Air Arabia", "TK": "Turkish Airlines", "MH": "Malaysia Airlines",
}

CITY_TO_IATA: dict[str, str] = {
    "delhi": "DEL", "new delhi": "DEL", "mumbai": "BOM", "bombay": "BOM",
    "bangalore": "BLR", "bengaluru": "BLR", "hyderabad": "HYD",
    "chennai": "MAA", "madras": "MAA", "kolkata": "CCU", "calcutta": "CCU",
    "kochi": "COK", "goa": "GOI", "ahmedabad": "AMD", "jaipur": "JAI",
    "lucknow": "LKO", "pune": "PNQ", "amritsar": "ATQ", "guwahati": "GAU",
    "varanasi": "VNS", "patna": "PAT", "bhubaneswar": "BBI", "ranchi": "IXR",
    "chandigarh": "IXC", "srinagar": "SXR", "jammu": "IXJ", "leh": "IXL",
    "dubai": "DXB", "london": "LHR", "singapore": "SIN", "doha": "DOH",
}

ROUTE_AIRLINES: dict[tuple, list] = {
    ("DEL", "BOM"): ["6E", "AI", "UK", "SG", "QP"],
    ("DEL", "BLR"): ["6E", "AI", "UK", "SG", "QP"],
    ("DEL", "MAA"): ["6E", "AI", "UK", "SG"],
    ("DEL", "HYD"): ["6E", "AI", "UK", "SG"],
    ("DEL", "CCU"): ["6E", "AI", "UK"],
    ("BOM", "BLR"): ["6E", "AI", "UK", "SG"],
    ("BOM", "HYD"): ["6E", "AI", "UK", "SG"],
    ("DEL", "DXB"): ["AI", "EK", "6E", "FZ"],
    ("DEL", "LHR"): ["AI", "BA"],
    ("BOM", "DXB"): ["AI", "EK", "6E"],
}

ROUTE_BASE_PRICES: dict[tuple, int] = {
    ("DEL", "BOM"): 3200, ("DEL", "BLR"): 3800, ("BOM", "BLR"): 2800,
    ("DEL", "MAA"): 4000, ("DEL", "HYD"): 3300, ("DEL", "CCU"): 3100,
    ("BOM", "HYD"): 2500, ("DEL", "DXB"): 7800, ("DEL", "LHR"): 28000,
    ("BOM", "DXB"): 6800,
}

DEP_TIMES = ["06:00", "07:30", "09:15", "12:15", "15:00", "18:00", "21:00", "22:30"]


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _resolve_iata(code: str) -> str:
    if not code:
        return code
    stripped = code.strip().lower()
    return CITY_TO_IATA.get(stripped, stripped.upper())


def _airline_logo(iata: str) -> str:
    return f"https://content.airhex.com/content/logos/airlines_{iata}_200_200_s.png"


def _airline_logo_rect(iata: str) -> str:
    return f"https://content.airhex.com/content/logos/airlines_{iata}_100_25_r.png"


# ── ML enrichment ─────────────────────────────────────────────────────
def _enrich_with_ml(flights: list, origin: str, destination: str, departure_date: str) -> list:
    model = _model()
    if not model:
        return flights

    try:
        dep_date_obj = datetime.strptime(departure_date, "%Y-%m-%d").date()
        days_until_dep = max((dep_date_obj - date.today()).days, 0)

        for f in flights:
            try:
                base_price = f["price"]["total"]
                airline = f.get("primary_airline", "AI")

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
                    "is_weekend": 1 if dep_date_obj.weekday() >= 5 else 0,
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
                    f["recommendation"] = "BOOK NOW 🔥"
                    f["trend"] = "INCREASING"
                    f["decision"] = "BUY NOW"
                    f["advice"] = "Prices expected to rise — lock in this fare."
                elif predicted < base_price * 0.88:
                    f["recommendation"] = "WAIT ⏳"
                    f["trend"] = "DECREASING"
                    f["decision"] = "WAIT"
                    f["advice"] = "Model predicts a price drop soon."
                else:
                    f["recommendation"] = "FAIR PRICE ✅"
                    f["trend"] = "STABLE"
                    f["decision"] = "FAIR"
                    f["advice"] = "Current price is within normal range."

            except Exception:
                f.setdefault("ai_price", f["price"]["total"])
                f.setdefault("recommendation", "MONITOR")
                f.setdefault("trend", "STABLE")

    except Exception:
        pass

    return flights


# ── Synthetic flight generator ────────────────────────────────────────
def _generate_synthetic(
    origin: str,
    destination: str,
    departure_date: str,
    adults: int = 1,
    cabin_class: str = "ECONOMY",
) -> list:
    key = (origin, destination)
    airlines = ROUTE_AIRLINES.get(key, ROUTE_AIRLINES.get((destination, origin), ["6E", "AI", "SG"]))
    base = ROUTE_BASE_PRICES.get(key, ROUTE_BASE_PRICES.get((destination, origin), 4500))

    seed_val = hash(f"{origin}{destination}{departure_date}") % (2 ** 31)
    rng = random.Random(seed_val)
    flights = []

    for i, airline_code in enumerate(airlines):
        repeats = 2 if airline_code in ("6E", "AI") else 1
        for j in range(repeats):
            dep_str = rng.choice(DEP_TIMES)
            dur_min = rng.randint(75, 200)
            total_price = round(base * rng.uniform(0.88, 1.35) * adults)

            h, m = divmod(dur_min, 60)

            flights.append({
                "id": f"SYN-{origin}-{destination}-{airline_code}-{i}-{j}",
                "source": "SKYMIND_SYNTHETIC",
                "price": {"total": total_price, "base": round(total_price * 0.82), "currency": "INR"},
                "itineraries": [{
                    "duration": f"PT{h}H{m}M",
                    "segments": [{
                        "flight_number": f"{airline_code}{rng.randint(100, 999)}",
                        "airline_code": airline_code,
                        "airline_name": AIRLINE_MAP.get(airline_code, airline_code),
                        "airline_logo": _airline_logo(airline_code),
                        "airline_logo_rect": _airline_logo_rect(airline_code),
                        "origin": origin,
                        "destination": destination,
                        "departure_time": f"{departure_date}T{dep_str}:00",
                        "arrival_time": f"{departure_date}T23:59:00",
                        "duration": f"PT{h}H{m}M",
                        "cabin": cabin_class,
                        "stops": 0,
                    }],
                }],
                "primary_airline": airline_code,
                "primary_airline_name": AIRLINE_MAP.get(airline_code, airline_code),
                "primary_airline_logo": _airline_logo(airline_code),
                "seats_available": rng.randint(2, 12),
                "instant_ticketing": rng.choice([True, False]),
            })

    return flights


# ── Amadeus raw response parser ───────────────────────────────────────
def _parse_amadeus(raw: dict) -> list:
    offers = []
    data = raw.get("data", [])
    carriers = {**AIRLINE_MAP, **raw.get("dictionaries", {}).get("carriers", {})}

    for offer in data:
        itins = offer.get("itineraries", [])
        price_info = offer.get("price", {})
        parsed_itins = []

        for itin in itins:
            segments = []
            for seg in itin.get("segments", []):
                carrier = (
                    seg.get("operating", {}).get("carrierCode")
                    or seg.get("carrierCode", "")
                ).upper()
                dep = seg.get("departure", {})
                arr = seg.get("arrival", {})
                segments.append({
                    "flight_number": f"{carrier}{seg.get('number', '')}",
                    "airline_code": carrier,
                    "airline_name": carriers.get(carrier, carrier),
                    "airline_logo": _airline_logo(carrier),
                    "airline_logo_rect": _airline_logo_rect(carrier),
                    "origin": dep.get("iataCode", ""),
                    "destination": arr.get("iataCode", ""),
                    "departure_time": dep.get("at", ""),
                    "arrival_time": arr.get("at", ""),
                    "duration": seg.get("duration", ""),
                    "cabin": seg.get("cabin", "ECONOMY"),
                    "stops": seg.get("numberOfStops", 0),
                    "terminal_departure": dep.get("terminal"),
                    "terminal_arrival": arr.get("terminal"),
                })
            parsed_itins.append({"duration": itin.get("duration", ""), "segments": segments})

        validating = offer.get("validatingAirlineCodes", [])
        primary = validating[0] if validating else (segments[0]["airline_code"] if segments else "AI")
        total = float(price_info.get("grandTotal") or price_info.get("total") or 0)
        base = float(price_info.get("base") or round(total * 0.82, 2))

        offers.append({
            "id": offer.get("id", ""),
            "source": "AMADEUS",
            "price": {"total": total, "base": base, "currency": price_info.get("currency", "INR")},
            "itineraries": parsed_itins,
            "primary_airline": primary,
            "primary_airline_name": carriers.get(primary, primary),
            "primary_airline_logo": _airline_logo(primary),
            "seats_available": offer.get("numberOfBookableSeats", 9),
            "instant_ticketing": offer.get("instantTicketingRequired", False),
        })

    return offers


# ══════════════════════════════════════════════════════════════════════
# GET /flights/search
# ══════════════════════════════════════════════════════════════════════

@router.get("/search")
async def search_flights(
    origin: str = Query(...),
    destination: str = Query(...),
    departure_date: str = Query(...),
    adults: int = Query(1, ge=1, le=9),
    cabin_class: str = Query("ECONOMY"),
    max_results: int = Query(20, ge=1, le=50),
):
    origin_iata = _resolve_iata(origin)
    destination_iata = _resolve_iata(destination)

    if origin_iata == destination_iata:
        raise HTTPException(400, detail="Origin and destination cannot be the same")

    flights = []
    source_used = "SYNTHETIC"

    # ── Try Amadeus ───────────────────────────────────────────────────
    try:
        from services.amadeus import amadeus_service
        raw = await amadeus_service.search_flights(
            origin=origin_iata,
            destination=destination_iata,
            departure_date=departure_date,
            adults=adults,
            cabin_class=cabin_class,
            max_results=max_results,
        )
        parsed = _parse_amadeus(raw)
        if parsed:
            flights = parsed
            source_used = "AMADEUS"
    except Exception as exc:
        logger.warning(f"Amadeus failed ({exc}), falling back to synthetic")

    # ── Fallback to synthetic ─────────────────────────────────────────
    if not flights:
        flights = _generate_synthetic(
            origin_iata, destination_iata, departure_date, adults, cabin_class
        )
        source_used = "SKYMIND_SYNTHETIC"

    # ── De-duplicate ──────────────────────────────────────────────────
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

    # ── Sort by price, cap results ────────────────────────────────────
    unique = sorted(unique, key=lambda x: x["price"]["total"])[:max_results]

    # ── ML enrichment ─────────────────────────────────────────────────
    unique = _enrich_with_ml(unique, origin_iata, destination_iata, departure_date)

    return {
        "flights": unique,
        "count": len(unique),
        "origin_iata": origin_iata,
        "destination_iata": destination_iata,
        "data_source": source_used,
    }


# ══════════════════════════════════════════════════════════════════════
# GET /flights/airports
# ══════════════════════════════════════════════════════════════════════

STATIC_AIRPORTS = [
    {"iata": "DEL", "city": "New Delhi",    "name": "Indira Gandhi International",        "country": "India"},
    {"iata": "BOM", "city": "Mumbai",       "name": "Chhatrapati Shivaji Maharaj Intl",   "country": "India"},
    {"iata": "BLR", "city": "Bengaluru",    "name": "Kempegowda International",           "country": "India"},
    {"iata": "MAA", "city": "Chennai",      "name": "Chennai International",              "country": "India"},
    {"iata": "HYD", "city": "Hyderabad",    "name": "Rajiv Gandhi International",         "country": "India"},
    {"iata": "CCU", "city": "Kolkata",      "name": "Netaji Subhas Chandra Bose Intl",    "country": "India"},
    {"iata": "COK", "city": "Kochi",        "name": "Cochin International",               "country": "India"},
    {"iata": "GOI", "city": "Goa",          "name": "Goa International",                  "country": "India"},
    {"iata": "AMD", "city": "Ahmedabad",    "name": "Sardar Vallabhbhai Patel Intl",      "country": "India"},
    {"iata": "JAI", "city": "Jaipur",       "name": "Jaipur International",               "country": "India"},
    {"iata": "BBI", "city": "Bhubaneswar",  "name": "Biju Patnaik International",         "country": "India"},
    {"iata": "DXB", "city": "Dubai",        "name": "Dubai International",                "country": "UAE"},
    {"iata": "LHR", "city": "London",       "name": "Heathrow Airport",                   "country": "UK"},
    {"iata": "SIN", "city": "Singapore",    "name": "Changi Airport",                     "country": "Singapore"},
    {"iata": "DOH", "city": "Doha",         "name": "Hamad International",                "country": "Qatar"},
]


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
