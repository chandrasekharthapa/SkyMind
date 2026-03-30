"""
Flight search — Amadeus primary + AviationStack fallback + rich mock data.
Supports city name → IATA. Returns ALL airlines with correct logos.
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from datetime import datetime, date, timedelta
import logging
import os
import random

logger = logging.getLogger(__name__)
router = APIRouter()

AIRLINE_MAP = {
    "AI": "Air India", "6E": "IndiGo", "UK": "Vistara", "SG": "SpiceJet",
    "IX": "Air India Express", "QP": "Akasa Air", "G8": "Go First",
    "S5": "Star Air", "2T": "TruJet", "I7": "Alliance Air",
    "EK": "Emirates", "SQ": "Singapore Airlines", "QR": "Qatar Airways",
    "EY": "Etihad Airways", "BA": "British Airways", "TK": "Turkish Airlines",
    "MH": "Malaysia Airlines", "LH": "Lufthansa", "AF": "Air France",
    "KL": "KLM", "NH": "ANA", "JL": "Japan Airlines",
    "CX": "Cathay Pacific", "TG": "Thai Airways", "KE": "Korean Air",
    "FZ": "flydubai", "G9": "Air Arabia", "WY": "Oman Air",
    "UL": "SriLankan Airlines", "5J": "Cebu Pacific",
}

CITY_TO_IATA = {
    "delhi": "DEL", "new delhi": "DEL", "mumbai": "BOM", "bombay": "BOM",
    "bangalore": "BLR", "bengaluru": "BLR", "hyderabad": "HYD",
    "chennai": "MAA", "madras": "MAA", "kolkata": "CCU", "calcutta": "CCU",
    "kochi": "COK", "cochin": "COK", "goa": "GOI", "ahmedabad": "AMD",
    "jaipur": "JAI", "lucknow": "LKO", "pune": "PNQ", "amritsar": "ATQ",
    "guwahati": "GAU", "varanasi": "VNS", "patna": "PAT",
    "bhubaneswar": "BBI", "ranchi": "IXR", "chandigarh": "IXC",
    "srinagar": "SXR", "jammu": "IXJ", "leh": "IXL", "dehradun": "DED",
    "imphal": "IMF", "nagpur": "NAG", "indore": "IDR", "bhopal": "BHO",
    "raipur": "RPR", "vizag": "VTZ", "visakhapatnam": "VTZ",
    "coimbatore": "CJB", "madurai": "IXM", "trichy": "TRZ",
    "tiruchirappalli": "TRZ", "trivandrum": "TRV",
    "thiruvananthapuram": "TRV", "calicut": "CCJ", "kozhikode": "CCJ",
    "kannur": "CNN", "mangalore": "IXE", "mysore": "MYQ", "mysuru": "MYQ",
    "siliguri": "IXB", "udaipur": "UDR", "jodhpur": "JDH",
    "port blair": "IXZ", "andaman": "IXZ",
    "dubai": "DXB", "london": "LHR", "singapore": "SIN",
    "doha": "DOH", "abu dhabi": "AUH", "bangkok": "BKK",
    "kuala lumpur": "KUL", "new york": "JFK", "tokyo": "NRT",
    "istanbul": "IST", "paris": "CDG", "frankfurt": "FRA",
}

# ── Route-specific airline mapping ──────────────────────────────────────────
ROUTE_AIRLINES = {
    ("DEL", "BOM"): ["6E", "AI", "UK", "SG", "QP"],
    ("DEL", "BLR"): ["6E", "AI", "UK", "SG", "QP"],
    ("DEL", "MAA"): ["6E", "AI", "UK", "SG"],
    ("DEL", "HYD"): ["6E", "AI", "UK", "SG", "QP"],
    ("DEL", "CCU"): ["6E", "AI", "UK", "SG"],
    ("DEL", "COK"): ["6E", "AI", "SG"],
    ("DEL", "GOI"): ["6E", "AI", "UK", "SG"],
    ("DEL", "JAI"): ["6E", "AI", "UK", "SG", "QP"],
    ("DEL", "LKO"): ["6E", "AI", "UK", "SG"],
    ("DEL", "AMD"): ["6E", "AI", "UK", "SG"],
    ("DEL", "PNQ"): ["6E", "AI", "UK", "SG"],
    ("DEL", "ATQ"): ["6E", "AI", "SG"],
    ("DEL", "IXC"): ["6E", "AI", "SG"],
    ("DEL", "SXR"): ["6E", "AI", "SG"],
    ("DEL", "IXJ"): ["6E", "AI", "SG"],
    ("DEL", "IXL"): ["6E", "AI"],
    ("DEL", "GAU"): ["6E", "AI", "SG"],
    ("DEL", "BBI"): ["6E", "AI", "SG"],
    ("DEL", "VNS"): ["6E", "AI", "SG"],
    ("DEL", "PAT"): ["6E", "AI", "SG"],
    ("DEL", "IXR"): ["6E", "AI"],
    ("DEL", "BHO"): ["6E", "AI", "SG"],
    ("DEL", "IDR"): ["6E", "AI", "SG"],
    ("DEL", "NAG"): ["6E", "AI", "SG"],
    ("DEL", "VTZ"): ["6E", "AI", "SG"],
    ("DEL", "TRV"): ["6E", "AI"],
    ("DEL", "IXZ"): ["6E", "AI"],
    ("DEL", "IMF"): ["6E", "AI"],
    ("DEL", "DXB"): ["AI", "EK", "6E", "FZ", "G9"],
    ("DEL", "LHR"): ["AI", "BA", "UK"],
    ("DEL", "SIN"): ["AI", "SQ", "6E"],
    ("DEL", "DOH"): ["AI", "QR", "6E"],
    ("DEL", "BKK"): ["AI", "TG", "6E"],
    ("BOM", "BLR"): ["6E", "AI", "UK", "SG", "QP"],
    ("BOM", "MAA"): ["6E", "AI", "UK", "SG"],
    ("BOM", "HYD"): ["6E", "AI", "UK", "SG", "QP"],
    ("BOM", "CCU"): ["6E", "AI", "UK", "SG"],
    ("BOM", "COK"): ["6E", "AI", "UK", "IX"],
    ("BOM", "GOI"): ["6E", "AI", "UK", "SG", "QP"],
    ("BOM", "AMD"): ["6E", "AI", "UK", "SG", "QP"],
    ("BOM", "PNQ"): ["6E", "AI", "SG"],
    ("BOM", "JAI"): ["6E", "AI", "UK", "SG"],
    ("BOM", "NAG"): ["6E", "AI", "SG"],
    ("BOM", "LKO"): ["6E", "AI", "SG"],
    ("BOM", "DXB"): ["AI", "EK", "6E", "FZ"],
    ("BOM", "LHR"): ["AI", "BA", "UK"],
    ("BOM", "SIN"): ["AI", "SQ", "6E"],
    ("BLR", "MAA"): ["6E", "AI", "UK", "SG", "QP"],
    ("BLR", "HYD"): ["6E", "AI", "UK", "SG"],
    ("BLR", "COK"): ["6E", "AI", "UK", "IX"],
    ("BLR", "CCU"): ["6E", "AI", "SG"],
    ("BLR", "GOI"): ["6E", "AI", "SG"],
    ("BLR", "TRV"): ["6E", "AI", "IX"],
    ("BLR", "DXB"): ["AI", "EK", "6E"],
    ("MAA", "HYD"): ["6E", "AI", "UK", "SG"],
    ("MAA", "COK"): ["6E", "AI", "IX"],
    ("MAA", "CCU"): ["6E", "AI", "SG"],
    ("MAA", "DXB"): ["AI", "EK", "6E"],
    ("HYD", "CCU"): ["6E", "AI", "SG"],
    ("HYD", "COK"): ["6E", "AI", "SG"],
    ("CCU", "GAU"): ["6E", "AI", "SG"],
    ("COK", "TRV"): ["6E", "AI", "IX"],
    ("COK", "DXB"): ["AI", "EK", "IX", "G9"],
}

# Base prices per route (INR)
ROUTE_BASE_PRICES = {
    ("DEL", "BOM"): 3200, ("DEL", "BLR"): 3800, ("DEL", "MAA"): 4200,
    ("DEL", "HYD"): 3500, ("DEL", "CCU"): 3100, ("DEL", "COK"): 5200,
    ("DEL", "GOI"): 4800, ("DEL", "JAI"): 1800, ("DEL", "LKO"): 2200,
    ("DEL", "AMD"): 2800, ("DEL", "PNQ"): 3600, ("DEL", "ATQ"): 1900,
    ("DEL", "IXC"): 1600, ("DEL", "SXR"): 2900, ("DEL", "IXJ"): 2400,
    ("DEL", "IXL"): 3800, ("DEL", "GAU"): 4200, ("DEL", "BBI"): 3900,
    ("DEL", "VNS"): 2400, ("DEL", "PAT"): 2900, ("DEL", "IXR"): 3400,
    ("DEL", "BHO"): 2600, ("DEL", "IDR"): 2700, ("DEL", "NAG"): 3100,
    ("DEL", "VTZ"): 3600, ("DEL", "TRV"): 5800, ("DEL", "IXZ"): 5200,
    ("DEL", "IMF"): 4900, ("DEL", "DXB"): 6800, ("DEL", "LHR"): 28000,
    ("DEL", "SIN"): 12000, ("DEL", "DOH"): 14000, ("DEL", "BKK"): 9500,
    ("BOM", "BLR"): 2800, ("BOM", "MAA"): 3100, ("BOM", "HYD"): 2500,
    ("BOM", "CCU"): 4200, ("BOM", "COK"): 3400, ("BOM", "GOI"): 2100,
    ("BOM", "AMD"): 1900, ("BOM", "PNQ"): 1200, ("BOM", "JAI"): 2900,
    ("BOM", "NAG"): 2600, ("BOM", "LKO"): 3300, ("BOM", "DXB"): 5800,
    ("BOM", "LHR"): 26000, ("BOM", "SIN"): 10500,
    ("BLR", "MAA"): 1800, ("BLR", "HYD"): 2100, ("BLR", "COK"): 1900,
    ("BLR", "CCU"): 4100, ("BLR", "GOI"): 2400, ("BLR", "TRV"): 1700,
    ("BLR", "DXB"): 5500,
    ("MAA", "HYD"): 2000, ("MAA", "COK"): 2100, ("MAA", "CCU"): 3600,
    ("MAA", "DXB"): 5200,
    ("HYD", "CCU"): 3500, ("HYD", "COK"): 2800,
    ("CCU", "GAU"): 2100, ("COK", "TRV"): 1400, ("COK", "DXB"): 5400,
}

# Departure times pool
DEP_TIMES = ["05:30", "06:00", "06:30", "07:00", "07:30", "08:00",
             "09:15", "10:30", "11:00", "12:15", "13:00", "14:30",
             "15:00", "16:30", "17:00", "18:00", "19:30", "20:00",
             "21:00", "22:30"]

# Duration by distance bracket (minutes)
def estimate_duration(base_price: int) -> int:
    if base_price < 2000: return random.randint(55, 80)
    if base_price < 4000: return random.randint(90, 140)
    if base_price < 8000: return random.randint(150, 220)
    return random.randint(480, 660)  # international


def resolve_iata(code: str) -> str:
    if not code:
        return code
    stripped = code.strip()
    lower = stripped.lower()
    if lower in CITY_TO_IATA:
        return CITY_TO_IATA[lower]
    return stripped.upper()


def get_airline_logo_url(iata: str) -> str:
    """
    Returns a reliable airline logo URL.
    Uses airhex as primary; the frontend has a multi-source fallback chain.
    """
    return f"https://content.airhex.com/content/logos/airlines_{iata}_200_200_s.png"


def get_airline_logo_rect(iata: str) -> str:
    return f"https://content.airhex.com/content/logos/airlines_{iata}_100_25_r.png"


def parse_flight_offers_fixed(raw: dict) -> list[dict]:
    """Parse Amadeus response correctly for ALL airlines."""
    offers = []
    data = raw.get("data", [])
    dictionaries = raw.get("dictionaries", {})
    carriers = {**AIRLINE_MAP, **dictionaries.get("carriers", {})}
    aircraft_dict = dictionaries.get("aircraft", {})

    for offer in data:
        itineraries = offer.get("itineraries", [])
        price_info = offer.get("price", {})
        parsed_itineraries = []

        for itin in itineraries:
            segments = []
            for seg in itin.get("segments", []):
                dep = seg.get("departure", {})
                arr = seg.get("arrival", {})
                carrier_code = (
                    seg.get("operating", {}).get("carrierCode")
                    or seg.get("carrierCode", "")
                ).upper()
                airline_name = carriers.get(carrier_code, carrier_code)
                segments.append({
                    "flight_number": f"{carrier_code}{seg.get('number', '')}",
                    "airline_code": carrier_code,
                    "airline_name": airline_name,
                    "airline_logo": get_airline_logo_url(carrier_code),
                    "airline_logo_rect": get_airline_logo_rect(carrier_code),
                    "aircraft": aircraft_dict.get(
                        seg.get("aircraft", {}).get("code", ""), "Unknown"
                    ),
                    "origin": dep.get("iataCode", ""),
                    "destination": arr.get("iataCode", ""),
                    "departure_time": dep.get("at", ""),
                    "arrival_time": arr.get("at", ""),
                    "duration": seg.get("duration", ""),
                    "cabin": seg.get("cabin", "ECONOMY"),
                    "stops": seg.get("numberOfStops", 0),
                    "terminal_departure": dep.get("terminal", ""),
                    "terminal_arrival": arr.get("terminal", ""),
                })
            parsed_itineraries.append({
                "duration": itin.get("duration", ""),
                "segments": segments,
            })

        validating = offer.get("validatingAirlineCodes", [])
        primary = validating[0] if validating else (
            parsed_itineraries[0]["segments"][0]["airline_code"]
            if parsed_itineraries and parsed_itineraries[0]["segments"] else "??"
        )
        total_price = float(price_info.get("grandTotal", price_info.get("total", 0)))
        base_price = float(price_info.get("base", total_price * 0.85))

        offers.append({
            "id": offer.get("id", str(len(offers))),
            "source": "AMADEUS",
            "price": {
                "total": total_price, "base": base_price,
                "currency": price_info.get("currency", "INR"),
                "fees": price_info.get("fees", []),
                "grand_total": total_price,
            },
            "itineraries": parsed_itineraries,
            "validating_airlines": validating,
            "primary_airline": primary,
            "primary_airline_name": carriers.get(primary, primary),
            "primary_airline_logo": get_airline_logo_url(primary),
            "traveler_pricings": offer.get("travelerPricings", []),
            "last_ticketing_date": offer.get("lastTicketingDate"),
            "seats_available": offer.get("numberOfBookableSeats"),
            "instant_ticketing": offer.get("instantTicketingRequired", False),
        })

    return offers


async def search_aviationstack(
    origin: str, destination: str, departure_date: str,
    adults: int = 1, cabin_class: str = "ECONOMY"
) -> list[dict]:
    """
    AviationStack API fallback — fetches live flight schedules.
    Falls back to rich synthetic data if key not configured.
    """
    api_key = os.getenv("AVIATIONSTACK_API_KEY", "")

    if api_key:
        try:
            import httpx
            # AviationStack flights endpoint
            params = {
                "access_key": api_key,
                "dep_iata": origin,
                "arr_iata": destination,
                "flight_date": departure_date,
                "limit": 20,
            }
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "http://api.aviationstack.com/v1/flights", params=params
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    if data:
                        return _parse_aviationstack(data, departure_date, adults)
        except Exception as e:
            logger.warning("AviationStack error: %s — using synthetic data", e)

    # Synthetic rich flight data
    return _generate_synthetic_flights(origin, destination, departure_date, adults, cabin_class)


def _parse_aviationstack(data: list, departure_date: str, adults: int) -> list[dict]:
    """Convert AviationStack response to SkyMind format."""
    results = []
    for flight in data[:15]:
        dep = flight.get("departure", {})
        arr = flight.get("arrival", {})
        airline = flight.get("airline", {})
        fl = flight.get("flight", {})

        carrier_code = airline.get("iata", "AI").upper()
        airline_name = airline.get("name", AIRLINE_MAP.get(carrier_code, carrier_code))

        dep_time = dep.get("scheduled", f"{departure_date}T07:00:00+05:30")
        arr_time = arr.get("scheduled", f"{departure_date}T09:00:00+05:30")

        try:
            from datetime import datetime as dt
            d1 = dt.fromisoformat(dep_time.replace("Z", "+00:00"))
            d2 = dt.fromisoformat(arr_time.replace("Z", "+00:00"))
            dur_min = int((d2 - d1).total_seconds() / 60)
        except Exception:
            dur_min = 90

        h, m = dur_min // 60, dur_min % 60
        duration_iso = f"PT{h}H{m}M"

        key = (dep.get("iata", ""), arr.get("iata", ""))
        base_price = ROUTE_BASE_PRICES.get(key, ROUTE_BASE_PRICES.get(
            (arr.get("iata", ""), dep.get("iata", "")), 5000
        ))
        price_variation = random.uniform(0.85, 1.35)
        total_price = round(base_price * price_variation * adults)

        results.append({
            "id": f"AS-{fl.get('iata', carrier_code)}-{len(results)}",
            "source": "AVIATIONSTACK",
            "price": {
                "total": total_price,
                "base": round(total_price * 0.82),
                "currency": "INR",
                "fees": [],
                "grand_total": total_price,
            },
            "itineraries": [{
                "duration": duration_iso,
                "segments": [{
                    "flight_number": fl.get("iata", f"{carrier_code}000"),
                    "airline_code": carrier_code,
                    "airline_name": airline_name,
                    "airline_logo": get_airline_logo_url(carrier_code),
                    "airline_logo_rect": get_airline_logo_rect(carrier_code),
                    "aircraft": flight.get("aircraft", {}).get("iata", ""),
                    "origin": dep.get("iata", ""),
                    "destination": arr.get("iata", ""),
                    "departure_time": dep_time,
                    "arrival_time": arr_time,
                    "duration": duration_iso,
                    "cabin": "ECONOMY",
                    "stops": 0,
                    "terminal_departure": dep.get("terminal", ""),
                    "terminal_arrival": arr.get("terminal", ""),
                }]
            }],
            "validating_airlines": [carrier_code],
            "primary_airline": carrier_code,
            "primary_airline_name": airline_name,
            "primary_airline_logo": get_airline_logo_url(carrier_code),
            "traveler_pricings": [],
            "seats_available": random.randint(2, 30),
            "instant_ticketing": False,
        })

    return sorted(results, key=lambda x: x["price"]["total"])


def _generate_synthetic_flights(
    origin: str, destination: str, departure_date: str,
    adults: int = 1, cabin_class: str = "ECONOMY"
) -> list[dict]:
    """
    Rich deterministic synthetic flight data for any route.
    Seeded by route so same query returns same results.
    """
    key = (origin, destination)
    rev_key = (destination, origin)
    airlines = ROUTE_AIRLINES.get(key, ROUTE_AIRLINES.get(rev_key, ["6E", "AI", "SG"]))
    base = ROUTE_BASE_PRICES.get(key, ROUTE_BASE_PRICES.get(rev_key, 4500))

    # Seed random for determinism per route+date
    seed_val = hash(f"{origin}{destination}{departure_date}") % (2**31)
    rng = random.Random(seed_val)

    flights = []
    dep_times = rng.sample(DEP_TIMES, min(len(airlines) * 2, len(DEP_TIMES)))

    for i, airline_code in enumerate(airlines):
        num_flights = 3 if airline_code in ["6E", "AI"] else (2 if airline_code in ["UK", "SG"] else 1)
        for j in range(num_flights):
            idx = (i * 3 + j) % len(dep_times)
            dep_str = dep_times[idx]
            dep_hour, dep_min = map(int, dep_str.split(":"))

            dur_min = estimate_duration(base)
            arr_hour = dep_hour + dur_min // 60
            arr_min = dep_min + dur_min % 60
            if arr_min >= 60:
                arr_min -= 60
                arr_hour += 1
            arr_hour %= 24
            arr_str = f"{arr_hour:02d}:{arr_min:02d}"

            dep_dt = f"{departure_date}T{dep_str}:00+05:30"
            arr_dt = f"{departure_date}T{arr_str}:00+05:30"
            if arr_hour < dep_hour:  # overnight
                from datetime import datetime as dt, timedelta
                next_day = (dt.fromisoformat(departure_date) + timedelta(days=1)).strftime("%Y-%m-%d")
                arr_dt = f"{next_day}T{arr_str}:00+05:30"

            h, m = dur_min // 60, dur_min % 60
            duration_iso = f"PT{h}H{m}M"

            # Price variation per airline & time
            multipliers = {"AI": 1.08, "UK": 1.12, "6E": 0.92, "SG": 0.88, "QP": 0.85,
                           "IX": 0.82, "EK": 1.35, "QR": 1.28, "SQ": 1.25, "BA": 1.40,
                           "TK": 1.15, "MH": 1.10}
            peak_times = {"05:30", "06:00", "06:30", "07:00", "18:00", "19:30", "20:00"}
            time_mult = 1.08 if dep_str in peak_times else 1.0
            cabin_mult = {"ECONOMY": 1.0, "PREMIUM_ECONOMY": 1.6, "BUSINESS": 3.2, "FIRST": 5.5}.get(cabin_class, 1.0)

            price_var = rng.uniform(0.88, 1.22)
            total_price = round(base * multipliers.get(airline_code, 1.0) * time_mult * cabin_mult * price_var * adults)
            base_fare = round(total_price * 0.82)

            flight_num = f"{airline_code}{rng.randint(100, 999)}"
            seats = rng.randint(1, 35)
            airline_name = AIRLINE_MAP.get(airline_code, airline_code)

            flights.append({
                "id": f"SYN-{origin}-{destination}-{airline_code}-{i}-{j}",
                "source": "SKYMIND_SYNTHETIC",
                "price": {
                    "total": total_price,
                    "base": base_fare,
                    "currency": "INR",
                    "fees": [{"amount": str(round(total_price * 0.10)), "type": "SUPPLIER"}],
                    "grand_total": total_price,
                },
                "itineraries": [{
                    "duration": duration_iso,
                    "segments": [{
                        "flight_number": flight_num,
                        "airline_code": airline_code,
                        "airline_name": airline_name,
                        "airline_logo": get_airline_logo_url(airline_code),
                        "airline_logo_rect": get_airline_logo_rect(airline_code),
                        "aircraft": rng.choice(["A320", "B737", "A321", "B777", "A380", "ATR72"]),
                        "origin": origin,
                        "destination": destination,
                        "departure_time": dep_dt,
                        "arrival_time": arr_dt,
                        "duration": duration_iso,
                        "cabin": cabin_class,
                        "stops": 0,
                        "terminal_departure": rng.choice(["T1", "T2", "T3", ""]),
                        "terminal_arrival": rng.choice(["T1", "T2", ""]),
                    }]
                }],
                "validating_airlines": [airline_code],
                "primary_airline": airline_code,
                "primary_airline_name": airline_name,
                "primary_airline_logo": get_airline_logo_url(airline_code),
                "traveler_pricings": [],
                "seats_available": seats,
                "instant_ticketing": airline_code in ["6E", "SG", "QP"],
            })

    return sorted(flights, key=lambda x: x["price"]["total"])


def get_ai_insight(origin: str, destination: str, days_until: int) -> dict:
    try:
        from ml.price_predictor import predictor
        result = predictor.forecast_with_analysis(origin=origin, destination=destination)
        return {
            "recommendation": result["recommendation"],
            "reason": result["reason"],
            "probability_increase": result["probability_increase"],
            "trend": result["trend"],
            "predicted_price": result["predicted_price"],
        }
    except Exception:
        return {
            "recommendation": "MONITOR",
            "reason": "Monitor prices for this route.",
            "probability_increase": 0.5,
            "trend": "STABLE",
            "predicted_price": None,
        }


@router.get("/search")
async def search_flights(
    origin: str = Query(..., description="IATA code or city name"),
    destination: str = Query(..., description="IATA code or city name"),
    departure_date: str = Query(..., description="YYYY-MM-DD"),
    return_date: Optional[str] = Query(None),
    adults: int = Query(1, ge=1, le=9),
    cabin_class: str = Query("ECONOMY"),
    currency: str = Query("INR"),
    max_results: int = Query(20, ge=1, le=50),
):
    """
    Search flights.
    Priority: Amadeus GDS → AviationStack → Synthetic rich data.
    Supports city names.
    """
    origin_iata = resolve_iata(origin)
    destination_iata = resolve_iata(destination)

    if origin_iata == destination_iata:
        raise HTTPException(400, "Origin and destination cannot be the same")

    # Validate date
    try:
        dep_date_obj = datetime.strptime(departure_date, "%Y-%m-%d").date()
        if dep_date_obj < date.today():
            raise HTTPException(400, "Departure date cannot be in the past")
    except ValueError:
        raise HTTPException(400, "Invalid departure_date format. Use YYYY-MM-DD")

    days_until = (dep_date_obj - date.today()).days
    flights = []
    source_used = "SYNTHETIC"

    # 1. Try Amadeus
    amadeus_id = os.getenv("AMADEUS_CLIENT_ID", "")
    amadeus_secret = os.getenv("AMADEUS_CLIENT_SECRET", "")

    if amadeus_id and amadeus_secret:
        try:
            from services.amadeus import amadeus_service
            raw = await amadeus_service.search_flights(
                origin=origin_iata, destination=destination_iata,
                departure_date=departure_date, return_date=return_date,
                adults=adults, cabin_class=cabin_class,
                currency=currency, max_results=max_results,
            )
            flights = parse_flight_offers_fixed(raw)
            if flights:
                source_used = "AMADEUS"
                logger.info("Amadeus returned %d flights for %s→%s", len(flights), origin_iata, destination_iata)
        except Exception as e:
            logger.warning("Amadeus failed (%s) — trying AviationStack", e)

    # 2. Try AviationStack / synthetic
    if not flights:
        try:
            flights = await search_aviationstack(
                origin_iata, destination_iata,
                departure_date, adults, cabin_class
            )
            source_used = "AVIATIONSTACK" if os.getenv("AVIATIONSTACK_API_KEY") else "SYNTHETIC"
            logger.info("%s returned %d flights for %s→%s", source_used, len(flights), origin_iata, destination_iata)
        except Exception as e:
            logger.error("All flight sources failed: %s", e)
            raise HTTPException(503, "Flight search temporarily unavailable. Please try again.")

    # Attach AI insights
    ai = get_ai_insight(origin_iata, destination_iata, days_until)
    for f in flights:
        f["ai_insight"] = ai

    # Sort by price, cap results
    flights.sort(key=lambda x: x["price"]["total"])
    flights = flights[:max_results]

    return {
        "flights": flights,
        "count": len(flights),
        "origin_iata": origin_iata,
        "destination_iata": destination_iata,
        "data_source": source_used,
        "search_params": {
            "origin": origin_iata,
            "destination": destination_iata,
            "departure_date": departure_date,
            "return_date": return_date,
            "adults": adults,
            "cabin_class": cabin_class,
            "currency": currency,
        },
    }


@router.get("/airports")
async def search_airports(q: str = Query(..., min_length=1)):
    """Search airports by city / name / IATA."""
    AIRPORTS = [
        {"iata": "DEL", "city": "New Delhi", "name": "Indira Gandhi International", "country": "India", "state": "Delhi"},
        {"iata": "BOM", "city": "Mumbai", "name": "Chhatrapati Shivaji Maharaj International", "country": "India", "state": "Maharashtra"},
        {"iata": "BLR", "city": "Bengaluru", "name": "Kempegowda International", "country": "India", "state": "Karnataka"},
        {"iata": "MAA", "city": "Chennai", "name": "Chennai International", "country": "India", "state": "Tamil Nadu"},
        {"iata": "HYD", "city": "Hyderabad", "name": "Rajiv Gandhi International", "country": "India", "state": "Telangana"},
        {"iata": "CCU", "city": "Kolkata", "name": "Netaji Subhas Chandra Bose International", "country": "India", "state": "West Bengal"},
        {"iata": "COK", "city": "Kochi", "name": "Cochin International", "country": "India", "state": "Kerala"},
        {"iata": "GOI", "city": "Goa", "name": "Goa International (Dabolim)", "country": "India", "state": "Goa"},
        {"iata": "MYA", "city": "North Goa", "name": "Mopa International Airport", "country": "India", "state": "Goa"},
        {"iata": "AMD", "city": "Ahmedabad", "name": "Sardar Vallabhbhai Patel International", "country": "India", "state": "Gujarat"},
        {"iata": "JAI", "city": "Jaipur", "name": "Jaipur International", "country": "India", "state": "Rajasthan"},
        {"iata": "LKO", "city": "Lucknow", "name": "Chaudhary Charan Singh International", "country": "India", "state": "Uttar Pradesh"},
        {"iata": "PNQ", "city": "Pune", "name": "Pune Airport", "country": "India", "state": "Maharashtra"},
        {"iata": "ATQ", "city": "Amritsar", "name": "Sri Guru Ram Dass Jee International", "country": "India", "state": "Punjab"},
        {"iata": "NAG", "city": "Nagpur", "name": "Dr. Babasaheb Ambedkar International", "country": "India", "state": "Maharashtra"},
        {"iata": "IXC", "city": "Chandigarh", "name": "Chandigarh International", "country": "India", "state": "Punjab"},
        {"iata": "SXR", "city": "Srinagar", "name": "Sheikh ul-Alam International", "country": "India", "state": "J&K"},
        {"iata": "IXJ", "city": "Jammu", "name": "Jammu Airport", "country": "India", "state": "J&K"},
        {"iata": "IXL", "city": "Leh", "name": "Kushok Bakula Rimpochhe Airport", "country": "India", "state": "Ladakh"},
        {"iata": "GAU", "city": "Guwahati", "name": "Lokpriya Gopinath Bordoloi International", "country": "India", "state": "Assam"},
        {"iata": "IMF", "city": "Imphal", "name": "Imphal International", "country": "India", "state": "Manipur"},
        {"iata": "IXB", "city": "Siliguri", "name": "Bagdogra Airport", "country": "India", "state": "West Bengal"},
        {"iata": "BBI", "city": "Bhubaneswar", "name": "Biju Patnaik International", "country": "India", "state": "Odisha"},
        {"iata": "IXR", "city": "Ranchi", "name": "Birsa Munda Airport", "country": "India", "state": "Jharkhand"},
        {"iata": "PAT", "city": "Patna", "name": "Jay Prakash Narayan International", "country": "India", "state": "Bihar"},
        {"iata": "VNS", "city": "Varanasi", "name": "Lal Bahadur Shastri International", "country": "India", "state": "Uttar Pradesh"},
        {"iata": "IDR", "city": "Indore", "name": "Devi Ahilyabai Holkar Airport", "country": "India", "state": "Madhya Pradesh"},
        {"iata": "BHO", "city": "Bhopal", "name": "Raja Bhoj Airport", "country": "India", "state": "Madhya Pradesh"},
        {"iata": "RPR", "city": "Raipur", "name": "Swami Vivekananda Airport", "country": "India", "state": "Chhattisgarh"},
        {"iata": "VTZ", "city": "Visakhapatnam", "name": "Visakhapatnam Airport", "country": "India", "state": "Andhra Pradesh"},
        {"iata": "TRV", "city": "Thiruvananthapuram", "name": "Trivandrum International", "country": "India", "state": "Kerala"},
        {"iata": "CCJ", "city": "Kozhikode", "name": "Calicut International", "country": "India", "state": "Kerala"},
        {"iata": "CNN", "city": "Kannur", "name": "Kannur International", "country": "India", "state": "Kerala"},
        {"iata": "IXM", "city": "Madurai", "name": "Madurai Airport", "country": "India", "state": "Tamil Nadu"},
        {"iata": "TRZ", "city": "Tiruchirappalli", "name": "Tiruchirappalli International", "country": "India", "state": "Tamil Nadu"},
        {"iata": "CJB", "city": "Coimbatore", "name": "Coimbatore International", "country": "India", "state": "Tamil Nadu"},
        {"iata": "IXE", "city": "Mangalore", "name": "Mangalore International", "country": "India", "state": "Karnataka"},
        {"iata": "MYQ", "city": "Mysuru", "name": "Mysore Airport", "country": "India", "state": "Karnataka"},
        {"iata": "UDR", "city": "Udaipur", "name": "Maharana Pratap Airport", "country": "India", "state": "Rajasthan"},
        {"iata": "JDH", "city": "Jodhpur", "name": "Jodhpur Airport", "country": "India", "state": "Rajasthan"},
        {"iata": "IXZ", "city": "Port Blair", "name": "Veer Savarkar International", "country": "India", "state": "Andaman & Nicobar"},
        {"iata": "DED", "city": "Dehradun", "name": "Jolly Grant Airport", "country": "India", "state": "Uttarakhand"},
        {"iata": "DXB", "city": "Dubai", "name": "Dubai International", "country": "UAE", "state": "Dubai"},
        {"iata": "LHR", "city": "London", "name": "Heathrow Airport", "country": "UK", "state": "England"},
        {"iata": "CDG", "city": "Paris", "name": "Charles de Gaulle Airport", "country": "France", "state": "Île-de-France"},
        {"iata": "JFK", "city": "New York", "name": "John F. Kennedy International", "country": "USA", "state": "New York"},
        {"iata": "SIN", "city": "Singapore", "name": "Changi Airport", "country": "Singapore", "state": "Singapore"},
        {"iata": "BKK", "city": "Bangkok", "name": "Suvarnabhumi Airport", "country": "Thailand", "state": "Bangkok"},
        {"iata": "IST", "city": "Istanbul", "name": "Istanbul Airport", "country": "Turkey", "state": "Istanbul"},
        {"iata": "NRT", "city": "Tokyo", "name": "Narita International", "country": "Japan", "state": "Kanto"},
        {"iata": "DOH", "city": "Doha", "name": "Hamad International", "country": "Qatar", "state": "Qatar"},
        {"iata": "AUH", "city": "Abu Dhabi", "name": "Abu Dhabi International", "country": "UAE", "state": "Abu Dhabi"},
        {"iata": "KUL", "city": "Kuala Lumpur", "name": "KLIA", "country": "Malaysia", "state": "Selangor"},
    ]
    q_lower = q.lower().strip()
    results = [
        a for a in AIRPORTS
        if q_lower in a["city"].lower()
        or q_lower in a["iata"].lower()
        or q_lower in a["name"].lower()
        or q_lower in a.get("state", "").lower()
    ]
    for r in results:
        r["logo_url"] = get_airline_logo_url(r["iata"])
    return {"airports": results[:12]}


@router.get("/inspiration")
async def flight_inspiration(origin: str = Query(...), currency: str = Query("INR")):
    origin_iata = resolve_iata(origin)
    try:
        from services.amadeus import amadeus_service
        return await amadeus_service.get_flight_inspiration(origin=origin_iata, currency=currency)
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/cheapest-dates")
async def cheapest_dates(origin: str = Query(...), destination: str = Query(...)):
    origin_iata = resolve_iata(origin)
    destination_iata = resolve_iata(destination)
    try:
        from services.amadeus import amadeus_service
        return await amadeus_service.get_cheapest_dates(origin=origin_iata, destination=destination_iata)
    except Exception as e:
        raise HTTPException(500, str(e))
