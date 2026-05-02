"""
SkyMind — User Router
Endpoints:
  GET /user/trips       → upcoming + past trips
  GET /user/profile/{user_id}
"""

from fastapi import APIRouter, HTTPException, Query, Depends
import logging

from database import database as db
from routers.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


# ══════════════════════════════════════════════════════════════════════
# GET /user/trips
# ══════════════════════════════════════════════════════════════════════

@router.get("/trips")
async def get_user_trips(user_id: str = Query(...), current_user_id: str = Depends(get_current_user)):
    # ── IDOR Prevention ───────────────────────────────────────────
    if user_id != current_user_id:
        raise HTTPException(403, detail="Access denied")

    try:
        res = (
            db.supabase.table("bookings")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )

        raw_trips = res.data or []
        now = datetime.now(timezone.utc)
        upcoming, past = [], []

        for t in raw_trips:
            try:
                flight = t.get("flight_offer_data") or t.get("flight_data") or {}
                itin = (flight.get("itineraries") or [{}])[0]
                segs = itin.get("segments") or [{}]
                first_seg = segs[0]
                last_seg = segs[-1]

                dep_str = first_seg.get("departure_time") or (
                    first_seg.get("departure", {}).get("at", "")
                )

                trip_card = {
                    "id": t["id"],
                    "booking_reference": t.get("booking_reference"),
                    "status": t.get("status"),
                    "payment_status": t.get("payment_status"),
                    "origin": first_seg.get("origin") or first_seg.get("departure", {}).get("iataCode", t.get("origin_code", "")),
                    "destination": last_seg.get("destination") or last_seg.get("arrival", {}).get("iataCode", t.get("destination_code", "")),
                    "departure_time": dep_str,
                    "arrival_time": last_seg.get("arrival_time") or last_seg.get("arrival", {}).get("at", ""),
                    "airline": first_seg.get("airline_code") or first_seg.get("carrierCode", ""),
                    "price": t.get("total_price"),
                    "currency": t.get("currency", "INR"),
                }

                if dep_str:
                    dep_dt = datetime.fromisoformat(
                        dep_str.replace("Z", "+00:00")
                    )
                    if dep_dt > now:
                        upcoming.append(trip_card)
                    else:
                        past.append(trip_card)
                else:
                    past.append(trip_card)

            except Exception:
                past.append(t)

        return {
            "success": True,
            "upcoming": upcoming,
            "past": past,
            "total_count": len(raw_trips),
        }

    except Exception as exc:
        logger.error(f"Failed to fetch trips for {user_id}: {exc}")
        raise HTTPException(500, detail="Failed to fetch trips")


# ══════════════════════════════════════════════════════════════════════
# GET /user/profile/{user_id}
# ══════════════════════════════════════════════════════════════════════

@router.get("/profile/{user_id}")
async def get_profile(user_id: str, current_user_id: str = Depends(get_current_user)):
    # ── IDOR Prevention ───────────────────────────────────────────
    if user_id != current_user_id:
        raise HTTPException(403, detail="Access denied")

    try:
        res = (
            db.supabase.table("profiles")
            .select("*")
            .eq("id", user_id)
            .execute()
        )
        if not res.data:
            raise HTTPException(404, detail="Profile not found")

        p = res.data[0]
        return {
            "id": p.get("id"),
            "full_name": p.get("full_name"),
            "email": p.get("email"),
            "phone": p.get("phone"),
            "phone_verified": p.get("phone_verified", False),
            "preferences": {
                "notify_email": p.get("notify_email", True),
                "notify_sms": p.get("notify_sms", False),
                "notify_whatsapp": p.get("notify_whatsapp", False),
                "meal": p.get("meal_preference"),
                "seat": p.get("preferred_seat"),
                "cabin": p.get("preferred_cabin", "ECONOMY"),
            },
            "loyalty": {
                "points": p.get("skymind_points", 0),
                "tier": p.get("tier", "BLUE"),
                "member_since": p.get("created_at"),
            },
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Profile fetch error for {user_id}: {exc}")
        raise HTTPException(500, detail="Profile fetch error")
