"""
Authentication router — signup, login, OTP, phone verify.
Uses Supabase Auth + custom OTP via SMS/Email.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timedelta
import uuid

from services.notifications import dispatcher, generate_otp, hash_otp, verify_otp

router = APIRouter()


class SignUpRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    phone: Optional[str] = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class OTPRequest(BaseModel):
    user_id: str
    phone: Optional[str] = None
    email: Optional[str] = None
    purpose: str = "PHONE_VERIFY"

class VerifyOTPRequest(BaseModel):
    user_id: str
    otp: str
    purpose: str = "PHONE_VERIFY"

class UpdateProfileRequest(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    preferred_cabin: Optional[str] = None
    notify_email: Optional[bool] = None
    notify_sms: Optional[bool] = None
    notify_whatsapp: Optional[bool] = None
    meal_preference: Optional[str] = None
    preferred_seats: Optional[str] = None


# In-memory OTP store (use Redis in production)
_otp_store: dict[str, dict] = {}


@router.post("/signup")
async def signup(req: SignUpRequest):
    """
    Register a new user.
    In production: call Supabase Auth API.
    Trigger sends welcome email automatically via DB trigger.
    """
    # Supabase signup (call their REST API)
    # The DB trigger handle_new_user() auto-creates profile + sends welcome email
    user_id = str(uuid.uuid4())  # In production: use Supabase returned ID

    # Send welcome notification
    try:
        dispatcher.send_welcome(req.email, req.full_name)
    except Exception as e:
        pass  # Non-critical

    return {
        "success": True,
        "message": "Account created! Check your email to verify.",
        "user_id": user_id,
    }


@router.post("/send-otp")
async def send_otp(req: OTPRequest):
    """Send OTP for phone/email verification."""
    otp = generate_otp(6)
    otp_hash = hash_otp(otp)
    expires_at = datetime.now() + timedelta(minutes=10)

    # Store OTP
    _otp_store[f"{req.user_id}:{req.purpose}"] = {
        "hash": otp_hash,
        "expires_at": expires_at,
        "attempts": 0,
    }

    # Send via chosen channel
    sent = dispatcher.send_otp(
        email=req.email,
        phone=req.phone,
    )

    return {
        "success": True,
        "message": f"OTP sent to {'email' if req.email else 'phone'}",
        "expires_in": 600,  # 10 minutes
    }


@router.post("/verify-otp")
async def verify_otp_endpoint(req: VerifyOTPRequest):
    """Verify OTP and mark phone/email as verified."""
    key = f"{req.user_id}:{req.purpose}"
    stored = _otp_store.get(key)

    if not stored:
        raise HTTPException(400, "OTP not found or expired. Request a new one.")

    if datetime.now() > stored["expires_at"]:
        _otp_store.pop(key, None)
        raise HTTPException(400, "OTP has expired. Please request a new one.")

    stored["attempts"] += 1
    if stored["attempts"] > 5:
        _otp_store.pop(key, None)
        raise HTTPException(429, "Too many attempts. Request a new OTP.")

    if not verify_otp(req.otp, stored["hash"]):
        raise HTTPException(400, f"Invalid OTP. {5 - stored['attempts']} attempts remaining.")

    # Mark verified
    _otp_store.pop(key, None)
    # In production: UPDATE profiles SET phone_verified=TRUE WHERE id=req.user_id

    return {"success": True, "message": "Verified successfully!"}


@router.put("/profile/{user_id}")
async def update_profile(user_id: str, req: UpdateProfileRequest):
    """Update user profile and notification preferences."""
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    # In production: supabase.table("profiles").update(updates).eq("id", user_id).execute()
    return {"success": True, "updated": updates}


@router.get("/profile/{user_id}")
async def get_profile(user_id: str):
    """Get user profile with notification settings."""
    # In production: query Supabase profiles table
    return {
        "id": user_id,
        "full_name": "Demo User",
        "email": "user@example.com",
        "notify_email": True,
        "notify_sms": True,
        "notify_whatsapp": False,
        "skymind_points": 0,
        "tier": "BLUE",
    }
