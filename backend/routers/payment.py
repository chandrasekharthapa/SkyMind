"""
SkyMind — Razorpay Payment Router
Endpoints:
  POST /payment/create-order → create Razorpay order
  POST /payment/verify       → verify payment signature
  GET  /payment/status/{id}  → fetch payment from Razorpay
"""

import traceback
import hmac
import hashlib
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status, BackgroundTasks
from pydantic import BaseModel

from config import settings
from database import database as db
from services.notifications import dispatcher

router = APIRouter()


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _get_razorpay_client():
    import razorpay  # type: ignore
    return razorpay.Client(
        auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
    )


# ══════════════════════════════════════════════════════════════════════
# Request models  (Pydantic V2)
# ══════════════════════════════════════════════════════════════════════

class CreateOrderRequest(BaseModel):
    amount: float
    currency: str = "INR"
    booking_id: str
    booking_reference: str


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    booking_id: str


# ══════════════════════════════════════════════════════════════════════
# POST /payment/create-order
# ══════════════════════════════════════════════════════════════════════

@router.post("/create-order")
async def create_razorpay_order(req: CreateOrderRequest):
    try:
        # Verify booking exists and is PENDING
        booking_res = (
            db.supabase.table("bookings")
            .select("id, payment_status, total_price")
            .eq("id", req.booking_id)
            .execute()
        )
        if not booking_res.data:
            raise HTTPException(404, detail="Booking not found")

        booking = booking_res.data[0]

        if booking.get("payment_status") == "PAID":
            return {"message": "Booking already paid", "order_id": None}

        # Amount validation (prevent price tampering)
        db_price = float(booking.get("total_price", 0))
        if abs(db_price - req.amount) > 1:  # 1 rupee tolerance for rounding
            raise HTTPException(
                400,
                detail=f"Price mismatch: booking total is ₹{db_price:.2f}",
            )

        # Create Razorpay order
        client = _get_razorpay_client()
        amount_paise = int(round(req.amount * 100))

        order = client.order.create(
            {
                "amount": amount_paise,
                "currency": req.currency,
                "receipt": req.booking_reference,
                "notes": {
                    "booking_id": req.booking_id,
                    "env": "2026_PROD",
                },
            }
        )

        return {
            "order_id": order["id"],
            "amount": req.amount,
            "currency": req.currency,
            "key": settings.razorpay_key_id,
        }

    except HTTPException:
        raise
    except Exception:
        traceback.print_exc()
        raise HTTPException(500, detail="Order creation error")


# ══════════════════════════════════════════════════════════════════════
# POST /payment/verify
# ══════════════════════════════════════════════════════════════════════

@router.post("/verify")
async def verify_payment(
    req: VerifyPaymentRequest,
    background_tasks: BackgroundTasks,
):
    try:
        # ── HMAC-SHA256 signature verification ──────────────────────
        message = f"{req.razorpay_order_id}|{req.razorpay_payment_id}"
        expected = hmac.new(
            settings.razorpay_key_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected, req.razorpay_signature):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                detail="Security alert: Invalid payment signature",
            )

        # ── Idempotency check ────────────────────────────────────────
        booking_res = (
            db.supabase.table("bookings")
            .select("*")
            .eq("id", req.booking_id)
            .execute()
        )
        if not booking_res.data:
            raise HTTPException(404, detail="Booking not found")

        booking = booking_res.data[0]
        if booking.get("payment_status") == "PAID":
            return {"success": True, "message": "Already processed."}

        # ── Update booking ───────────────────────────────────────────
        from datetime import datetime, timezone
        db.supabase.table("bookings").update(
            {
                "payment_status": "PAID",
                "status": "CONFIRMED",
                "razorpay_payment_id": req.razorpay_payment_id,
                "razorpay_order_id": req.razorpay_order_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", req.booking_id).execute()

        # ── Post-payment notifications (background) ──────────────────
        background_tasks.add_task(
            _send_post_payment_comms, booking, req.razorpay_payment_id
        )

        return {
            "success": True,
            "payment_id": req.razorpay_payment_id,
            "message": "Payment successful. Tickets are being issued.",
        }

    except HTTPException:
        raise
    except Exception:
        traceback.print_exc()
        raise HTTPException(500, detail="Verification failed")


# ══════════════════════════════════════════════════════════════════════
# GET /payment/status/{payment_id}
# ══════════════════════════════════════════════════════════════════════

@router.get("/status/{payment_id}")
async def get_payment_status(payment_id: str):
    try:
        client = _get_razorpay_client()
        payment = client.payment.fetch(payment_id)
        return {
            "payment_id": payment_id,
            "status": payment.get("status"),
            "method": payment.get("method"),
            "amount": payment.get("amount", 0) / 100,
            "currency": payment.get("currency"),
            "email": payment.get("email"),
        }
    except Exception:
        traceback.print_exc()
        raise HTTPException(500, detail="Razorpay fetch error")


# ══════════════════════════════════════════════════════════════════════
# Background: post-payment communications
# ══════════════════════════════════════════════════════════════════════

def _send_post_payment_comms(booking: Dict[str, Any], payment_id: str) -> None:
    try:
        flight_data = booking.get("flight_offer_data") or booking.get("flight_data") or {}
        itin = flight_data.get("itineraries", [{}])[0] if flight_data else {}
        segs = itin.get("segments", [{}])
        first_seg = segs[0] if segs else {}
        last_seg = segs[-1] if segs else {}

        passengers = booking.get("passengers") or []
        first_name = (
            passengers[0].get("first_name", "Traveller")
            if passengers
            else "Traveller"
        )

        comms_data = {
            "name": first_name,
            "booking_ref": booking.get("booking_reference", ""),
            "origin": first_seg.get("origin", first_seg.get("departure", {}).get("iataCode", "")),
            "destination": last_seg.get("destination", last_seg.get("arrival", {}).get("iataCode", "")),
            "departure_date": first_seg.get("departure_time", first_seg.get("departure", {}).get("at", "")),
            "amount": f"{booking.get('currency', 'INR')} {booking.get('total_price', 0):,.2f}",
            "payment_id": payment_id,
        }

        contact_email = booking.get("contact_email")
        contact_phone = booking.get("contact_phone")

        if contact_email:
            dispatcher.email.send_booking_confirmation(contact_email, comms_data)
        if contact_phone:
            dispatcher.sms.send_booking_confirmation(contact_phone, comms_data)

    except Exception as exc:
        print(f"[Post-payment notifications] error: {exc}")
