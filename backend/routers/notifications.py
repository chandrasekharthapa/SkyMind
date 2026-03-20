"""
Notifications router — test send, preferences, notification history.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional
from services.notifications import dispatcher, generate_otp, hash_otp, verify_otp

router = APIRouter()


class TestEmailRequest(BaseModel):
    to_email: EmailStr
    type: str = "welcome"  # welcome|otp|booking|price_alert|checkin|cancel|refund|status|promo

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

# In-memory OTP store (use Redis in production)
_otp_store: dict = {}


@router.post("/test/email")
async def test_email(req: TestEmailRequest):
    """Send a test email to verify Gmail credentials."""
    ok = False
    t = req.type

    if t == "welcome":
        ok = dispatcher.email.send_welcome(req.to_email, "Test User")

    elif t == "otp":
        ok = dispatcher.email.send_otp(req.to_email, "123456", "test")

    elif t == "booking":
        ok = dispatcher.email.send_booking_confirmation(req.to_email, {
            "name":"Rahul Sharma","booking_ref":"SKY20241234",
            "origin":"DEL","origin_city":"New Delhi",
            "destination":"BOM","dest_city":"Mumbai",
            "flight_number":"6E 201","airline":"IndiGo",
            "departure_date":"25 Dec 2024","departure_time":"06:00",
            "arrival_time":"08:15","terminal":"T2","cabin":"Economy",
            "passengers":"2 Adults","baggage":"15 kg each",
            "amount":"8,499","payment_method":"UPI","pnr":"ABCD12",
            "payment_id":"pay_QWE123","booking_id":"bkg-001"})

    elif t == "price_alert":
        ok = dispatcher.email.send_price_alert(req.to_email, {
            "name":"Priya Patel","origin":"BLR","destination":"MAA",
            "origin_city":"Bengaluru","dest_city":"Chennai",
            "departure_date":"15 Jan 2025",
            "target_price":3000,"current_price":2199,"cabin":"Economy"})

    elif t == "checkin":
        ok = dispatcher.email.send_checkin_reminder(req.to_email, {
            "name":"Amit Kumar","flight_number":"AI 504",
            "origin":"DEL","destination":"BLR",
            "departure_date":"26 Dec 2024","departure_time":"08:30",
            "terminal":"T3","booking_ref":"SKY20241234",
            "passengers":"1 Adult","baggage":"15 kg","booking_id":"bkg-001"})

    elif t == "cancel":
        ok = dispatcher.email.send_cancellation(req.to_email, {
            "name":"Sunita Rao","booking_ref":"SKY20241234",
            "origin":"HYD","destination":"CCU",
            "departure_date":"20 Dec 2024",
            "refund_amount":"4,250","refund_to":"HDFC Credit Card",
            "refund_eta":"5–7 business days"})

    elif t == "refund":
        ok = dispatcher.email.send_refund_processed(req.to_email, {
            "name":"Sunita Rao","booking_ref":"SKY20241234",
            "amount":"4,250","refund_id":"rfnd_XYZ789",
            "refund_to":"HDFC Credit Card","eta":"3–5 business days"})

    elif t == "status":
        ok = dispatcher.email.send_flight_status(req.to_email, {
            "name":"Vikram Singh","flight_number":"SG 8169",
            "origin":"BOM","destination":"GOI",
            "original_time":"14:00","new_time":"16:30",
            "delay_minutes":"2 hours 30 minutes","status":"DELAYED",
            "reason":"Air traffic congestion"})

    elif t == "promo":
        ok = dispatcher.email.send_promotion(req.to_email, {
            "name":"Test User","offer_title":"Monsoon Sale!",
            "offer_subtitle":"Up to 40% off on domestic flights",
            "intro_text":"Exclusive deals just for SkyMind members!",
            "discount_text":"40% OFF","offer_description":"On all domestic routes",
            "coupon_code":"MONSOON40","valid_until":"31 Aug 2025",
            "min_booking":"2000","subject":"🌧️ Monsoon Sale — Up to 40% Off Flights!"})
    else:
        raise HTTPException(400, f"Unknown type '{t}'. Valid: welcome|otp|booking|price_alert|checkin|cancel|refund|status|promo")

    return {"success": ok, "type": t, "recipient": req.to_email,
            "message": "Email sent!" if ok else "Email failed — check GMAIL_USER and GMAIL_APP_PASSWORD in .env"}


@router.post("/test/sms")
async def test_sms(req: TestSMSRequest):
    """Send a test SMS to verify Fast2SMS / Twilio credentials."""
    ok = False
    t  = req.type
    phone = req.phone

    if t == "otp":
        ok = dispatcher.sms.send_otp(phone, "456789")
    elif t == "booking":
        ok = dispatcher.sms.send_booking_confirmation(phone, {
            "booking_ref":"SKY20241234","origin":"DEL","destination":"BOM",
            "departure_date":"25 Dec 2024","departure_time":"06:00",
            "amount":"8,499","pnr":"ABCD12"})
    elif t == "alert":
        ok = dispatcher.sms.send_price_alert(phone, {
            "origin":"BLR","destination":"MAA",
            "current_price":2199,"target_price":3000})
    elif t == "checkin":
        ok = dispatcher.sms.send_checkin_reminder(phone, {
            "flight_number":"AI 504","origin":"DEL","destination":"BLR",
            "departure_time":"08:30","terminal":"T3","booking_ref":"SKY20241234"})
    elif t == "cancel":
        ok = dispatcher.sms.send_cancellation(phone, {
            "booking_ref":"SKY20241234","refund_amount":"4,250","refund_eta":"5-7 days"})
    else:
        ok = dispatcher.sms.send(phone, f"SkyMind test SMS from scheduler. Type: {t}")

    return {"success": ok, "type": t, "recipient": phone,
            "message": "SMS sent!" if ok else "SMS failed — check FAST2SMS_API_KEY or Twilio credentials"}


@router.post("/send-otp")
async def send_otp(req: OTPSendRequest):
    """Generate and send OTP via email and/or SMS."""
    otp = dispatcher.send_otp(
        email=req.email, phone=req.phone, purpose=req.purpose)
    otp_hash = hash_otp(otp)
    # In production: store otp_hash in DB with user_id + expiry
    return {
        "success": True,
        "otp_hash": otp_hash,  # client sends this back for verification
        "expires_in": 600,
        "message": f"OTP sent to {'email' if req.email else ''} {'& phone' if req.phone else ''}".strip()
    }


@router.post("/verify-otp")
async def verify_otp_route(req: OTPVerifyRequest):
    """Verify an OTP against its stored hash."""
    if not verify_otp(req.otp, req.otp_hash):
        raise HTTPException(400, "Invalid or expired OTP")
    return {"success": True, "message": "OTP verified!"}


@router.get("/channels")
async def get_channels():
    """Returns which notification channels are configured."""
    from config import get_settings
    s = get_settings()
    email_ok = bool(s.gmail_user and s.gmail_app_password)
    sms_ok   = bool(s.fast2sms_api_key or s.twilio_account_sid)
    wa_ok    = bool(s.twilio_whatsapp_number)
    return {
        "email":    {"enabled": email_ok, "provider": "Gmail SMTP", "user": s.gmail_user if email_ok else ""},
        "sms":      {"enabled": sms_ok,   "provider": "Fast2SMS" if s.fast2sms_api_key else "Twilio"},
        "whatsapp": {"enabled": wa_ok,    "provider": "Twilio WhatsApp"},
    }