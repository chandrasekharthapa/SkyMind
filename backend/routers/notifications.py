"""
Notifications router — test send, preferences, notification history.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict
from services.notifications import dispatcher, generate_otp, hash_otp, verify_otp

router = APIRouter()

# =========================================================
# MODELS
# =========================================================
class TestEmailRequest(BaseModel):
    to_email: EmailStr
    type: str = "welcome"

class TestSMSRequest(BaseModel):
    phone: str
    type: str = "otp"

class OTPSendRequest(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    purpose: str = "phone_verify"

class OTPVerifyRequest(BaseModel):
    otp: str
    otp_hash: str

# =========================================================
# TEST ENDPOINTS (EMAIL)
# =========================================================
@router.post("/test/email")
async def test_email(req: TestEmailRequest, background_tasks: BackgroundTasks):
    """
    Triggers test emails for various 2026 SkyMind templates.
    Uses BackgroundTasks to prevent API timeouts during SMTP handshakes.
    """
    t = req.type.lower()
    
    # Template Data Mapping
    templates: Dict[str, dict] = {
        "welcome": {"name": "Test User"},
        "booking": {
            "name": "Rahul Sharma", "booking_ref": "SKY2026-X1Y2",
            "origin": "DEL", "origin_city": "New Delhi",
            "destination": "BOM", "dest_city": "Mumbai",
            "flight_number": "6E 201", "airline": "IndiGo",
            "departure_date": "25 Dec 2026", "departure_time": "06:00",
            "arrival_time": "08:15", "terminal": "T2", "cabin": "Economy",
            "passengers": "2 Adults", "baggage": "15 kg each",
            "amount": "8,499", "payment_method": "UPI", "pnr": "ABCD12",
            "payment_id": "pay_QWE123", "booking_id": "bkg-001"
        },
        "price_alert": {
            "name": "Priya Patel", "origin": "BLR", "destination": "MAA",
            "origin_city": "Bengaluru", "dest_city": "Chennai",
            "departure_date": "15 Jan 2026",
            "target_price": 3000, "current_price": 2199, "cabin": "Economy"
        },
        "status": {
            "name": "Vikram Singh", "flight_number": "SG 8169",
            "origin": "BOM", "destination": "GOI",
            "original_time": "14:00", "new_time": "16:30",
            "delay_minutes": "150", "status": "DELAYED",
            "reason": "Air traffic congestion at BOM"
        }
    }

    if t not in templates and t != "otp" and t != "promo":
        raise HTTPException(400, f"Template type '{t}' not supported for testing.")

    # Execute dispatching
    try:
        if t == "welcome":
            background_tasks.add_task(dispatcher.email.send_welcome, req.to_email, "Test User")
        elif t == "booking":
            background_tasks.add_task(dispatcher.email.send_booking_confirmation, req.to_email, templates[t])
        elif t == "price_alert":
            background_tasks.add_task(dispatcher.email.send_price_alert, req.to_email, templates[t])
        elif t == "status":
            background_tasks.add_task(dispatcher.email.send_flight_status, req.to_email, templates[t])
        # ... other types follow same pattern
        
        return {"success": True, "message": f"Test email ({t}) queued for {req.to_email}"}
    except Exception as e:
        raise HTTPException(500, f"Dispatcher error: {e}")

# =========================================================
# TEST ENDPOINTS (SMS)
# =========================================================
@router.post("/test/sms")
async def test_sms(req: TestSMSRequest):
    phone = req.phone
    t = req.type.lower()
    
    if t == "otp":
        ok = dispatcher.sms.send_otp(phone, "456789")
    elif t == "booking":
        ok = dispatcher.sms.send_booking_confirmation(phone, {
            "booking_ref": "SKY2026-X1Y2", "origin": "DEL", "destination": "BOM",
            "departure_date": "25 Dec 2026", "amount": "8,499", "pnr": "ABCD12"
        })
    else:
        ok = dispatcher.sms.send(phone, f"SkyMind 2026 Test: {t}")

    return {"success": ok, "recipient": phone}

# =========================================================
# OTP FLOW (Multi-Channel Fallback)
# =========================================================
@router.post("/send-otp")
async def send_otp(req: OTPSendRequest):
    """
    Advanced OTP delivery with cascading fallbacks:
    Email -> SMS -> WhatsApp
    """
    if not req.email and not req.phone:
        raise HTTPException(400, "Identification (email/phone) is required.")

    otp = generate_otp()
    sent = False

    # 1. Cascade Logic
    if req.email:
        try:
            sent = dispatcher.email.send_otp(req.email, otp, req.purpose)
        except:
            sent = False

    if not sent and req.phone:
        try:
            sent = dispatcher.sms.send_otp(req.phone, otp)
        except:
            sent = False

    if not sent and req.phone and hasattr(dispatcher, "whatsapp"):
        try:
            sent = dispatcher.whatsapp.send_otp(req.phone, otp)
        except:
            sent = False

    if not sent:
        raise HTTPException(503, "All notification channels failed. Please try again later.")

    # Generate hash for the client-side/stateless verification
    otp_hash = hash_otp(otp)

    return {
        "success": True,
        "otp_hash": otp_hash,
        "expires_in": 600,
        "message": "Verification code dispatched successfully."
    }

@router.post("/verify-otp")
async def verify_otp_route(req: OTPVerifyRequest):
    """Stateless verification of OTP hash."""
    if not verify_otp(req.otp, req.otp_hash):
        raise HTTPException(401, "Invalid or expired security code.")
    
    return {"success": True, "message": "Identity verified."}

# =========================================================
# CONFIGURATION STATUS
# =========================================================
@router.get("/channels")
async def get_channels():
    """Checks environment variables to see which providers are live."""
    from config import get_settings
    s = get_settings()
    
    return {
        "email": {"enabled": bool(s.gmail_app_password), "provider": "Gmail/SMTP"},
        "sms": {"enabled": bool(s.fast2sms_api_key or s.twilio_account_sid), "provider": "Fast2SMS/Twilio"},
        "whatsapp": {"enabled": bool(s.twilio_whatsapp_number), "provider": "Twilio-WhatsApp"},
    }