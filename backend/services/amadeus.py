"""
SkyMind — Amadeus Flight Search Service
Provides an async client that fetches live fares from the Amadeus GDS.
Falls back gracefully when credentials are absent.
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


amadeus_service = AmadeusService()
