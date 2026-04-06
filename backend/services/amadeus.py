"""
SkyMind — Amadeus Flight Search Service
Provides an async client that fetches live fares from the Amadeus GDS.
Standardizes data for 2026 XGBoost Training.
"""

import os
import logging
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_BASE_URL = os.getenv("AMADEUS_BASE_URL", "https://test.api.amadeus.com")
_CLIENT_ID = os.getenv("AMADEUS_CLIENT_ID") or os.getenv("AMADEUS_API_KEY", "")
_CLIENT_SECRET = os.getenv("AMADEUS_CLIENT_SECRET") or os.getenv("AMADEUS_API_SECRET", "")

# ══════════════════════════════════════════════════════════════════════
# Token cache (simple in-process cache)
# ══════════════════════════════════════════════════════════════════════

_token_cache: dict = {"token": None, "expires_at": 0.0}

async def _get_token() -> str:
    now = datetime.now(timezone.utc).timestamp()
    if _token_cache["token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    if not _CLIENT_ID or not _CLIENT_SECRET:
        raise RuntimeError("Amadeus credentials not configured")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{_BASE_URL}/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": _CLIENT_ID,
                "client_secret": _CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        body = resp.json()
        _token_cache["token"] = body["access_token"]
        _token_cache["expires_at"] = now + body.get("expires_in", 1799)
        return _token_cache["token"]

# ══════════════════════════════════════════════════════════════════════
# Amadeus service (singleton-style object)
# ══════════════════════════════════════════════════════════════════════

class AmadeusService:
    async def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        adults: int = 1,
        cabin_class: str = "ECONOMY",
        max_results: int = 20,
    ) -> dict:
        token = await _get_token()

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{_BASE_URL}/v2/shopping/flight-offers",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "originLocationCode": origin.upper(),
                    "destinationLocationCode": destination.upper(),
                    "departureDate": departure_date,
                    "adults": adults,
                    "travelClass": cabin_class,
                    "max": max_results,
                    "currencyCode": "INR",
                },
            )

            if resp.status_code != 200:
                logger.warning(
                    f"Amadeus returned {resp.status_code}: {resp.text[:200]}"
                )
                return {"data": [], "dictionaries": {}}

            return resp.json()

    def format_for_skymind(self, raw_data: dict) -> list:
        """
        🎯 Standardizes raw Amadeus JSON into the 20-column SkyMind schema.
        Ensures is_live=True and training_weight=2.0 for all automated scrapes.
        """
        flights = raw_data.get("data", [])
        formatted_list = []
        today = datetime.now(timezone.utc)

        for flight in flights:
            try:
                # Basic Parsing
                itinerary = flight["itineraries"][0]["segments"][0]
                price = float(flight["price"]["total"])
                dep_date_str = itinerary["departure"]["at"].split("T")[0]
                dep_date_obj = datetime.strptime(dep_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                
                # Calculating lead time (days_until_dep)
                days_out = (dep_date_obj.date() - today.date()).days
                if days_out < 0: days_out = 0

                # 🚀 DYNAMIC URGENCY FEATURE
                # 1 / (days_until_dep + 1)
                calc_urgency = round(1 / (days_out + 1), 4)

                formatted_list.append({
                    "origin_code": itinerary["departure"]["iataCode"],
                    "destination_code": itinerary["arrival"]["iataCode"],
                    "airline_code": itinerary["carrierCode"],
                    "flight_number": f"{itinerary['carrierCode']}{itinerary['number']}",
                    "cabin_class": "Economy",
                    "price": price,
                    "currency": "INR",
                    "departure_date": dep_date_str,
                    "days_until_dep": days_out,
                    "day_of_week": dep_date_obj.weekday(),
                    "month": dep_date_obj.month,
                    "week_of_year": dep_date_obj.isocalendar()[1],
                    "is_holiday": False,
                    "is_weekend": dep_date_obj.weekday() >= 5,
                    "seats_available": int(flight.get("numberOfBookableSeats", 9)),
                    "recorded_at": today.isoformat(),
                    "is_live": True,
                    "training_weight": 2.0, # 🔥 High priority for 2026 AI
                    "urgency": calc_urgency  # ✅ Engineered feature
                })
            except Exception as e:
                logger.debug(f"Skipping malformed flight record: {e}")
                continue
                
        return formatted_list

amadeus_service = AmadeusService()