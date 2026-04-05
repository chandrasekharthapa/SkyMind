"""
SkyMind — Booking Router
Endpoints:
  POST   /booking/create        → create booking
  GET    /booking/{booking_id}  → get booking
  POST   /booking/{booking_id}/cancel → cancel booking
"""

import traceback
import uuid
import string
import random
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, field_validator

from database import database as db
from services.notifications import dispatcher

router = APIRouter()


# ══════════════════════════════════════════════════════════════════════
# Pydantic models  (Pydantic V2)
# ══════════════════════════════════════════════════════════════════════

class PassengerData(BaseModel):
    type: str = "ADULT"
    title: Optional[str] = None
    first_name: str
    last_name: str
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    nationality: Optional[str] = "Indian"
    passport_number: Optional[str] = None
    passport_expiry: Optional[str] = None
    passport_country: Optional[str] = "India"
    aadhaar_number: Optional[str] = None
    seat_number: Optional[str] = None
    seat_preference: Optional[str] = "WINDOW"
    meal_preference: Optional[str] = "VEG"
    baggage_allowance: int = 15
    ff_number: Optional[str] = None
    ff_airline: Optional[str] = None
    special_request: Optional[str] = None

    @field_validator("first_name", "last_name")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Name must not be empty")
        return v.strip()


class CreateBookingRequest(BaseModel):
    flight_offer_id: str
    flight_data: dict                     # raw FlightOffer JSON
    passengers: List[PassengerData]       # list of objects — never a flat string
    contact_email: EmailStr
    contact_phone: str
    cabin_class: str = "ECONOMY"
    currency: str = "INR"
    user_id: Optional[str] = None
    coupon_code: Optional[str] = None

    @field_validator("passengers")
    @classmethod
    def at_least_one(cls, v: list) -> list:
        if not v:
            raise ValueError("At least one passenger is required")
        return v


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _generate_booking_ref() -> str:
    chars = string.ascii_uppercase + string.digits
    return "SKY" + "".join(random.choices(chars, k=6))


def _extract_price(flight_data: dict) -> float:
    try:
        price_info = flight_data.get("price", {})
        val = (
            price_info.get("grandTotal")
            or price_info.get("grand_total")
            or price_info.get("total")
            or 0
        )
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _extract_route(flight_data: dict) -> tuple[str, str]:
    """Return (origin_code, destination_code) from flight_data."""
    try:
        itins = flight_data.get("itineraries", [{}])
        segs = itins[0].get("segments", [{}]) if itins else [{}]
        origin = segs[0].get("origin", segs[0].get("departure", {}).get("iataCode", ""))
        last_seg = segs[-1] if segs else {}
        destination = last_seg.get("destination", last_seg.get("arrival", {}).get("iataCode", ""))
        return origin, destination
    except Exception:
        return "", ""


# ══════════════════════════════════════════════════════════════════════
# POST /booking/create
# ══════════════════════════════════════════════════════════════════════

@router.post("/create", status_code=status.HTTP_201_CREATED)
async def create_booking(req: CreateBookingRequest):
    try:
        booking_ref = _generate_booking_ref()
        total_price = _extract_price(req.flight_data)

        if total_price <= 0:
            raise HTTPException(
                400,
                detail="Could not determine flight price. Please refresh the offer.",
            )

        booking_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        origin_code, destination_code = _extract_route(req.flight_data)

        # Serialise passengers as list of dicts
        passenger_list = [p.model_dump() for p in req.passengers]

        booking_payload = {
            "id": booking_id,
            "booking_reference": booking_ref,
            "status": "PENDING",
            "payment_status": "UNPAID",
            "flight_offer_id": req.flight_offer_id,
            "flight_offer_data": req.flight_data,
            "passengers": passenger_list,
            "num_passengers": len(passenger_list),
            "contact_email": str(req.contact_email),
            "contact_phone": req.contact_phone,
            "cabin_class": req.cabin_class,
            "total_price": total_price,
            "currency": req.currency,
            "origin_code": origin_code or None,
            "destination_code": destination_code or None,
            "created_at": now,
            "updated_at": now,
        }
        if req.user_id:
            booking_payload["user_id"] = req.user_id
        if req.coupon_code:
            booking_payload["coupon_code"] = req.coupon_code

        # ── Persist to Supabase ───────────────────────────────────────
        res = db.supabase.table("bookings").insert(booking_payload).execute()
        if not res.data:
            raise HTTPException(500, detail="Database insert failed")

        # ── Non-blocking confirmation email ──────────────────────────
        try:
            itinerary = req.flight_data.get("itineraries", [{}])[0]
            segments = itinerary.get("segments", [{}])
            first_seg = segments[0]
            last_seg = segments[-1]

            dispatcher.email.send_booking_confirmation(
                str(req.contact_email),
                {
                    "name": req.passengers[0].first_name,
                    "booking_ref": booking_ref,
                    "origin": first_seg.get("origin", first_seg.get("departure", {}).get("iataCode", "")),
                    "destination": last_seg.get("destination", last_seg.get("arrival", {}).get("iataCode", "")),
                    "departure_date": first_seg.get("departure_time", first_seg.get("departure", {}).get("at", "")),
                    "amount": f"{req.currency} {total_price:,.2f}",
                },
            )
        except Exception as email_err:
            print(f"[Non-critical] Confirmation email failed: {email_err}")

        return {
            "success": True,
            "booking_id": booking_id,
            "booking_reference": booking_ref,
            "total_price": total_price,
            "message": "Booking initiated. Please complete payment within 15 minutes.",
        }

    except HTTPException:
        raise
    except Exception:
        traceback.print_exc()
        raise HTTPException(500, detail="Booking creation failed")


# ══════════════════════════════════════════════════════════════════════
# GET /booking/{booking_id}
# ══════════════════════════════════════════════════════════════════════

@router.get("/{booking_id}")
async def get_booking(booking_id: str):
    try:
        res = (
            db.supabase.table("bookings")
            .select("*")
            .eq("id", booking_id)
            .execute()
        )
        if not res.data:
            raise HTTPException(404, detail="Booking not found")
        return res.data[0]
    except HTTPException:
        raise
    except Exception:
        traceback.print_exc()
        raise HTTPException(500, detail="Fetch error")


# ══════════════════════════════════════════════════════════════════════
# POST /booking/{booking_id}/cancel
# ══════════════════════════════════════════════════════════════════════

@router.post("/{booking_id}/cancel")
async def cancel_booking(booking_id: str):
    try:
        check = (
            db.supabase.table("bookings")
            .select("status, payment_status")
            .eq("id", booking_id)
            .execute()
        )
        if not check.data:
            raise HTTPException(404, detail="Booking not found")

        row = check.data[0]
        if row["status"] == "CANCELLED":
            return {"success": True, "message": "Booking already cancelled"}

        new_payment_status = (
            "REFUND_PENDING" if row.get("payment_status") == "PAID" else "VOID"
        )

        db.supabase.table("bookings").update(
            {
                "status": "CANCELLED",
                "payment_status": new_payment_status,
                "cancelled_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", booking_id).execute()

        return {
            "success": True,
            "message": "Booking cancelled successfully",
            "refund_status": "PROCESSING" if new_payment_status == "REFUND_PENDING" else "NONE",
        }

    except HTTPException:
        raise
    except Exception:
        traceback.print_exc()
        raise HTTPException(500, detail="Cancellation failed")
