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

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, EmailStr, field_validator
import logging

# Bare top-level names resolve through main.py's sys.path.append and bind second
# copies of modules main.py already imported as backend.* — a second Supabase
# client, a second engine, a second dispatcher. Import them by their real names.
from backend.database.database import database as db
from backend.services.notifications import dispatcher
from backend.routers.auth import get_current_user, get_current_user_optional

logger = logging.getLogger(__name__)

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
    coupon_code: Optional[str] = None

    # `user_id: Optional[str] = None` used to live here and was written straight into
    # `bookings.user_id`. Ownership is not something a request body gets to assert:
    # the field let an unauthenticated caller file a booking — with passenger names,
    # passport and Aadhaar numbers — against any account id they cared to name, and
    # the ownership checks on the other four booking endpoints then compared the
    # session against that attacker-supplied value and let them through. The id now
    # comes from the bearer token via `get_current_user_optional`, or the column
    # stays NULL for a genuine guest booking. Removing the field rather than ignoring
    # it is deliberate: pydantic drops unknown keys, so an old client still sending
    # `user_id` is silently unaffected instead of receiving a validation error.

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


def _extract_price_details(
    flight_data: dict,
) -> tuple[float, Optional[float], Optional[float]]:
    """Return (total, base, taxes) as read from the offer.

    `base` and `taxes` are None when the provider did not send a base fare.
    They are NOT derived from `total`: a fare/tax split is a fact about the
    offer, and inventing one (the previous code assumed base == 85% of total)
    writes a fabricated number into bookings.base_fare and bookings.taxes,
    which are then shown to the user and used for refunds. Both columns are
    nullable, so NULL correctly records "the provider did not tell us".

    `total` of 0.0 means "could not determine" and the caller rejects it.
    """
    try:
        price_info = flight_data.get("price", {}) or {}
        raw_total = (
            price_info.get("grandTotal")
            or price_info.get("grand_total")
            or price_info.get("total")
        )
        if raw_total is None:
            logger.warning(
                "Offer carries no grandTotal/grand_total/total; price keys present: %s",
                sorted(price_info.keys()),
            )
            return 0.0, None, None
        total = float(raw_total)

        raw_base = price_info.get("base")
        if raw_base is None:
            return total, None, None
        base = float(raw_base)
        return total, base, float(total - base)
    except (ValueError, TypeError) as e:
        logger.warning(f"Unparseable price on offer ({e}); price block: {flight_data.get('price')!r}")
        return 0.0, None, None


def _extract_route(flight_data: dict) -> tuple[Optional[str], Optional[str]]:
    """Return (origin_code, destination_code) from flight_data, or (None, None).

    Returns None rather than "" on failure: an empty string is a value that
    would be stored as the route, whereas NULL records that the route could
    not be read. The failure is logged so it cannot pass unnoticed.
    """
    try:
        itins = flight_data.get("itineraries", [{}])
        segs = itins[0].get("segments", [{}]) if itins else [{}]
        origin = segs[0].get("origin", segs[0].get("departure", {}).get("iataCode", ""))
        last_seg = segs[-1] if segs else {}
        destination = last_seg.get("destination", last_seg.get("arrival", {}).get("iataCode", ""))
        if not origin or not destination:
            logger.warning(
                "Could not read route from offer (origin=%r, destination=%r)", origin, destination
            )
            return origin or None, destination or None
        return origin, destination
    except Exception as e:
        logger.warning(f"Could not read route from offer: {e}")
        return None, None


# ══════════════════════════════════════════════════════════════════════
# POST /booking/create
# ══════════════════════════════════════════════════════════════════════

@router.post("/create", status_code=status.HTTP_201_CREATED)
async def create_booking(
    req: CreateBookingRequest,
    current_user_id: Optional[str] = Depends(get_current_user_optional),
):
    """Create a booking. Anonymous callers are allowed; forged ownership is not.

    This endpoint deliberately does **not** use `Depends(get_current_user)`, and that
    is a measured decision rather than an oversight. `frontend/lib/api.ts` attaches a
    bearer token to every call as of this change, but the booking page does not gate
    on a session, so a hard dependency would turn guest checkout into a 401. What the
    hole actually was is narrower than "no auth": ownership arrived in the request
    body. That is closed — `user_id` is the token's subject or NULL — so the worst an
    anonymous caller can now do is create a booking belonging to nobody.

    **If you want booking to require an account**, the change is two lines: swap this
    dependency for `get_current_user` and have `app/booking/page.tsx` redirect to
    login when `supabase.auth.getSession()` returns no session. Do not do the first
    without the second.
    """
    try:
        booking_ref = _generate_booking_ref()
        total_price, base_fare, taxes = _extract_price_details(req.flight_data)

        if total_price <= 0:
            raise HTTPException(
                400,
                detail="Could not determine flight price. Please refresh the offer.",
            )

        booking_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        origin_code, destination_code = _extract_route(req.flight_data)
        booking_payload = {
            "id": booking_id,
            "booking_reference": booking_ref,
            "status": "PENDING",
            "payment_status": "UNPAID",
            "origin_code": origin_code,
            "destination_code": destination_code,
            "amadeus_booking_id": req.flight_offer_id,
            "flight_offer_data": req.flight_data,
            "num_passengers": len(req.passengers),
            "contact_email": str(req.contact_email),
            "contact_phone": req.contact_phone,
            "cabin_class": req.cabin_class,
            "total_price": total_price,
            "base_fare": base_fare,
            "taxes": taxes,
            "currency": req.currency,
            "created_at": now,
            "updated_at": now,
        }
        if current_user_id:
            # From the verified token only. A NULL here means a genuine guest booking,
            # which the ownership checks on the other endpoints correctly refuse to
            # hand to anyone — including, unavoidably, the guest who created it.
            booking_payload["user_id"] = current_user_id
        if req.coupon_code:
            booking_payload["coupon_code"] = req.coupon_code

        try:
            res = db.supabase.table("bookings").insert(booking_payload).execute()
        except Exception as db_err:
            logger.error(f"Bookings table insert failed: {db_err}")
            raise HTTPException(500, detail="Database error during booking creation")

        if not res.data:
            logger.error(f"Bookings insert returned no data. Payload: {booking_payload}")
            raise HTTPException(500, detail="Database insert failed (bookings) - No data returned")

        # ── 2. Create Passengers ──────────────────────────────────────
        passenger_payloads = []
        for p in req.passengers:
            p_data = p.model_dump()
            payload = {
                "booking_id": booking_id,
                "passenger_type": p_data.get("type", "ADULT"),
                "title": p_data.get("title"),
                "first_name": p_data.get("first_name"),
                "last_name": p_data.get("last_name"),
                "date_of_birth": p_data.get("date_of_birth"),
                "gender": p_data.get("gender"),
                "nationality": p_data.get("nationality", "Indian"),
                "passport_number": p_data.get("passport_number"),
                "passport_expiry": p_data.get("passport_expiry"),
                "passport_country": p_data.get("passport_country", "India"),
                "aadhaar_number": p_data.get("aadhaar_number"),
                "seat_number": p_data.get("seat_number"),
                "seat_preference": p_data.get("seat_preference", "WINDOW"),
                "meal_preference": p_data.get("meal_preference", "VEG"),
                "baggage_kg": p_data.get("baggage_allowance", 15),
                "ff_number": p_data.get("ff_number"),
                "ff_airline": p_data.get("ff_airline"),
                "special_request": p_data.get("special_request"),
            }
            passenger_payloads.append(payload)

        try:
            p_res = db.supabase.table("passengers").insert(passenger_payloads).execute()
        except Exception as p_err:
            logger.error(f"Passengers table insert failed: {p_err}")
            p_res = type('obj', (object,), {'data': None}) # mock object

        if not p_res.data:
            logger.warning(f"Passenger insert returned no data. Payloads: {passenger_payloads}")

        # ── 3. Notifications ──────────────────────────────────────────
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
            logger.warning(f"Confirmation email failed: {email_err}")

        return {
            "success": True,
            "booking_id": booking_id,
            "booking_reference": booking_ref,
            "total_price": total_price,
            "message": "Booking initiated. Please complete payment within 15 minutes.",
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Booking creation error: {exc}")
        raise HTTPException(500, detail="Booking creation failed")


# ══════════════════════════════════════════════════════════════════════
# GET /booking/{booking_id}
# ══════════════════════════════════════════════════════════════════════

@router.get("/{booking_id}")
async def get_booking(booking_id: str, current_user_id: str = Depends(get_current_user)):
    try:
        res = (
            db.supabase.table("bookings")
            .select("*")
            .eq("id", booking_id)
            .execute()
        )
        if not res.data:
            raise HTTPException(404, detail="Booking not found")
        
        booking = res.data[0]
        # ── IDOR Prevention ───────────────────────────────────────────
        if booking.get("user_id") != current_user_id:
             raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access denied")

        return booking
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Booking fetch error: {exc}")
        raise HTTPException(500, detail="Fetch error")


# ══════════════════════════════════════════════════════════════════════
# POST /booking/{booking_id}/cancel
# ══════════════════════════════════════════════════════════════════════

@router.post("/{booking_id}/cancel")
async def cancel_booking(booking_id: str, current_user_id: str = Depends(get_current_user)):
    try:
        check = (
            db.supabase.table("bookings")
            .select("user_id, status, payment_status")
            .eq("id", booking_id)
            .execute()
        )
        if not check.data:
            raise HTTPException(404, detail="Booking not found")

        row = check.data[0]
        # ── IDOR Prevention ───────────────────────────────────────────
        if row.get("user_id") != current_user_id:
             raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access denied")

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
    except Exception as exc:
        logger.error(f"Booking cancellation error: {exc}")
        raise HTTPException(500, detail="Cancellation failed")
# ══════════════════════════════════════════════════════════════════════
# GET /booking/{booking_id}/download
# ══════════════════════════════════════════════════════════════════════

@router.get("/{booking_id}/download")
async def download_ticket(booking_id: str, current_user_id: str = Depends(get_current_user)):
    """
    Generate and serve a PDF ticket for the given booking.
    """
    try:
        # 1. Fetch booking
        res = db.supabase.table("bookings").select("*").eq("id", booking_id).execute()
        if not res.data:
            raise HTTPException(404, detail="Booking not found")
        booking = res.data[0]
        
        # 2. IDOR Prevention
        if booking.get("user_id") != current_user_id:
             raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access denied")

        # 3. Fetch passengers for the name
        p_res = db.supabase.table("passengers").select("first_name").eq("booking_id", booking_id).execute()
        first_name = p_res.data[0].get("first_name", "Traveller") if p_res.data else "Traveller"

        # 4. Generate PDF
        from backend.services.pdf import generate_ticket_pdf
        pdf_data = {
            "name": first_name,
            "booking_ref": booking.get("booking_reference"),
            "origin": booking.get("origin_code"),
            "destination": booking.get("destination_code"),
            "departure_date": booking.get("departure_date"),
            "amount": f"{booking.get('currency', 'INR')} {float(booking.get('total_price', 0)):,.2f}",
            "cabin": booking.get("cabin_class", "ECONOMY")
        }
        
        pdf_bytes = generate_ticket_pdf(pdf_data)

        from fastapi.responses import Response
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=SkyMind_Ticket_{booking.get('booking_reference')}.pdf"
            }
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Ticket download error: {exc}")
        traceback.print_exc()
        raise HTTPException(500, detail="Ticket generation failed")
