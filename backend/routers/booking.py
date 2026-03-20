"""
Booking creation and management endpoints.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import uuid
import string
import random

router = APIRouter()


class PassengerData(BaseModel):
    type: str = "ADULT"
    first_name: str
    last_name: str
    date_of_birth: Optional[str] = None
    passport_number: Optional[str] = None
    passport_expiry: Optional[str] = None
    nationality: Optional[str] = None
    meal_preference: Optional[str] = None
    baggage_allowance: int = 15


class CreateBookingRequest(BaseModel):
    flight_offer_id: str
    flight_data: dict  # Full Amadeus offer object
    passengers: list[PassengerData]
    contact_email: str
    contact_phone: str
    cabin_class: str = "ECONOMY"
    currency: str = "INR"
    user_id: Optional[str] = None


def generate_booking_ref() -> str:
    """Generate a PNR-style booking reference."""
    chars = string.ascii_uppercase + string.digits
    return "SM" + "".join(random.choices(chars, k=6))


@router.post("/create")
async def create_booking(req: CreateBookingRequest):
    """Create a flight booking record (before payment)."""
    booking_ref = generate_booking_ref()

    # Calculate total
    total_price = float(req.flight_data.get("price", {}).get("grand_total", 0))
    if total_price == 0:
        total_price = float(req.flight_data.get("price", {}).get("total", 0))

    booking = {
        "id": str(uuid.uuid4()),
        "booking_reference": booking_ref,
        "status": "PENDING",
        "payment_status": "UNPAID",
        "flight_offer": req.flight_data,
        "passengers": [p.model_dump() for p in req.passengers],
        "contact_email": req.contact_email,
        "contact_phone": req.contact_phone,
        "cabin_class": req.cabin_class,
        "total_price": total_price,
        "currency": req.currency,
        "user_id": req.user_id,
    }

    # In production: save to Supabase here
    # supabase.table("bookings").insert({...}).execute()

    return {
        "success": True,
        "booking": booking,
        "message": "Booking created. Please proceed to payment.",
    }


@router.get("/{booking_id}")
async def get_booking(booking_id: str):
    """Get booking details by ID."""
    # In production: query Supabase
    return {"id": booking_id, "status": "PENDING"}


@router.post("/{booking_id}/cancel")
async def cancel_booking(booking_id: str):
    """Cancel a booking."""
    # In production: update Supabase + potentially call Amadeus cancel
    return {"success": True, "message": "Booking cancelled", "refund_status": "PROCESSING"}
