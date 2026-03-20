"""
Razorpay payment integration endpoints.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import hmac
import hashlib
from config import settings

router = APIRouter()

# Razorpay client (lazy import)
def get_razorpay_client():
    import razorpay
    return razorpay.Client(auth=(settings.razorpay_key_id, settings.razorpay_key_secret))


class CreateOrderRequest(BaseModel):
    amount: float  # In INR
    currency: str = "INR"
    booking_id: str
    booking_reference: str


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    booking_id: str


@router.post("/create-order")
async def create_razorpay_order(req: CreateOrderRequest):
    """Create a Razorpay order for payment."""
    try:
        client = get_razorpay_client()
        # Razorpay expects paise (multiply INR by 100)
        amount_paise = int(req.amount * 100)

        order = client.order.create({
            "amount": amount_paise,
            "currency": req.currency,
            "receipt": req.booking_reference,
            "notes": {
                "booking_id": req.booking_id,
                "platform": "SkyMind",
            }
        })

        return {
            "order_id": order["id"],
            "amount": req.amount,
            "currency": req.currency,
            "key": settings.razorpay_key_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Payment order creation failed: {str(e)}")


@router.post("/verify")
async def verify_payment(req: VerifyPaymentRequest):
    """Verify Razorpay payment signature."""
    try:
        # Verify signature
        message = f"{req.razorpay_order_id}|{req.razorpay_payment_id}"
        generated_signature = hmac.new(
            settings.razorpay_key_secret.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()

        if generated_signature != req.razorpay_signature:
            raise HTTPException(status_code=400, detail="Invalid payment signature")

        # In production: update booking status in Supabase
        # supabase.table("bookings").update({"payment_status": "PAID", ...})

        return {
            "success": True,
            "payment_id": req.razorpay_payment_id,
            "booking_id": req.booking_id,
            "message": "Payment verified successfully. Booking confirmed!",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{payment_id}")
async def get_payment_status(payment_id: str):
    """Check payment status."""
    try:
        client = get_razorpay_client()
        payment = client.payment.fetch(payment_id)
        return {
            "payment_id": payment_id,
            "status": payment.get("status"),
            "amount": payment.get("amount", 0) / 100,
            "currency": payment.get("currency"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
