"""
SkyMind — Authentication Router
Endpoints:
  POST /auth/signup
  POST /auth/send-otp
  POST /auth/verify-otp
  GET  /auth/profile/{user_id}
  PUT  /auth/profile/{user_id}
"""

import traceback
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, status, Depends, Header
from pydantic import BaseModel, EmailStr, Field
from jose import jwt, JWTError

from config import settings
from database import database as db
from services.notifications import dispatcher, generate_otp, hash_otp, verify_otp as verify_otp_hash

router = APIRouter()

# ── Authentication Dependency ───────────────────────────────────────
async def get_current_user(authorization: str = Header(...)) -> str:
    """Verify Supabase JWT and return user_id."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(
            token, 
            settings.supabase_jwt_secret, 
            algorithms=["HS256"], 
            options={"verify_aud": False}
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        return user_id
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

# ── OTP Logic (Database Backed) ─────────────────────────────────────
def _save_otp_to_db(user_id: str, identifier: str, otp_hash: str, purpose: str, channel: str):
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    db.supabase.table("otp_verifications").insert({
        "user_id": user_id,
        "identifier": identifier,
        "otp_hash": otp_hash,
        "purpose": purpose,
        "channel": channel,
        "expires_at": expires_at
    }).execute()

def _verify_otp_from_db(user_id: str, otp: str, purpose: str) -> bool:
    res = db.supabase.table("otp_verifications") \
        .select("*") \
        .eq("user_id", user_id) \
        .eq("purpose", purpose) \
        .eq("is_used", False) \
        .order("created_at", desc=True) \
        .limit(1) \
        .execute()
    
    if not res.data:
        return False
    
    stored = res.data[0]
    if datetime.fromisoformat(stored["expires_at"].replace("Z", "+00:00")) < datetime.now(timezone.utc):
        return False
    
    if stored["attempts"] >= stored["max_attempts"]:
        return False

    # Increment attempts
    db.supabase.table("otp_verifications") \
        .update({"attempts": stored["attempts"] + 1}) \
        .eq("id", stored["id"]) \
        .execute()

    if verify_otp_hash(otp, stored["otp_hash"]):
        db.supabase.table("otp_verifications") \
            .update({"is_used": True, "used_at": datetime.now(timezone.utc).isoformat()}) \
            .eq("id", stored["id"]) \
            .execute()
        return True
    
    return False



# ══════════════════════════════════════════════════════════════════════
# Models (Pydantic V2)
# ══════════════════════════════════════════════════════════════════════

class SignUpRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
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
    preferred_seat: Optional[str] = None


# ══════════════════════════════════════════════════════════════════════
# POST /auth/signup
# ══════════════════════════════════════════════════════════════════════

@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(req: SignUpRequest):
    try:
        response = db.supabase.auth.sign_up(
            {"email": req.email, "password": req.password}
        )
        if not response.user:
            raise HTTPException(400, detail="Signup failed: no user returned")

        user_id = response.user.id

        # Upsert profile
        db.supabase.table("profiles").upsert(
            {
                "id": user_id,
                "auth_user_id": user_id,
                "email": req.email,
                "full_name": req.full_name,
                "display_name": req.full_name,
                "phone": req.phone,
                "phone_verified": False,
                "email_verified": False,
                "notify_email": True,
                "notify_sms": False,
                "notify_whatsapp": False,
            },
            on_conflict="auth_user_id",
        ).execute()

        # Welcome email (non-blocking)
        try:
            dispatcher.send_welcome(req.email, req.full_name)
        except Exception:
            pass

        return {
            "success": True,
            "message": "Account created! Check your email to verify.",
            "user_id": user_id,
        }

    except HTTPException:
        raise
    except Exception:
        traceback.print_exc()
        raise HTTPException(500, detail=f"Signup error")


# ══════════════════════════════════════════════════════════════════════
# POST /auth/send-otp
# ══════════════════════════════════════════════════════════════════════

@router.post("/send-otp")
async def send_otp(req: OTPRequest):
    if not req.email and not req.phone:
        raise HTTPException(400, detail="Must provide email or phone")

    otp = generate_otp(6)
    otp_hash_val = hash_otp(otp)
    
    channel = "EMAIL" if req.email else "SMS"
    identifier = req.email or req.phone or ""
    
    try:
        _save_otp_to_db(req.user_id, identifier, otp_hash_val, req.purpose, channel)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(500, detail="Failed to store OTP verification")

    sent = False
    if req.email:
        try:
            sent = dispatcher.email.send_otp(req.email, otp, req.purpose)
        except Exception:
            sent = False

    if not sent and req.phone:
        try:
            sent = dispatcher.sms.send_otp(req.phone, otp)
        except Exception:
            sent = False

    if not sent:
        raise HTTPException(500, detail="Failed to deliver OTP via any channel")

    return {
        "success": True,
        "message": f"OTP sent to {'email' if req.email else 'phone'}",
        "expires_in": 600,
    }


# ══════════════════════════════════════════════════════════════════════
# POST /auth/verify-otp
# ══════════════════════════════════════════════════════════════════════

@router.post("/verify-otp")
async def verify_otp_endpoint(req: VerifyOTPRequest):
    if not _verify_otp_from_db(req.user_id, req.otp, req.purpose):
        raise HTTPException(401, detail="Invalid or expired OTP")

    try:
        db.supabase.table("profiles").update({"phone_verified": True}).eq(
            "id", req.user_id
        ).execute()
    except Exception as exc:
        raise HTTPException(500, detail=f"Verified, but profile update failed: {exc}")

    return {"success": True, "message": "Verification successful"}


# ══════════════════════════════════════════════════════════════════════
# GET /auth/profile/{user_id}
# ══════════════════════════════════════════════════════════════════════

@router.get("/profile/{user_id}")
async def get_profile(user_id: str, authenticated_user_id: str = Depends(get_current_user)):
    # ── IDOR Prevention ───────────────────────────────────────────
    if user_id != authenticated_user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access denied")

    try:
        res = (
            db.supabase.table("profiles").select("*").eq("id", user_id).execute()
        )
        if not res.data:
            raise HTTPException(404, detail="Profile not found")
        return res.data[0]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Profile fetch error: {exc}")
        raise HTTPException(500, detail="Database fetch error")


# ══════════════════════════════════════════════════════════════════════
# PUT /auth/profile/{user_id}
# ══════════════════════════════════════════════════════════════════════

@router.put("/profile/{user_id}")
async def update_profile(
    user_id: str, 
    req: UpdateProfileRequest, 
    authenticated_user_id: str = Depends(get_current_user)
):
    # ── IDOR Prevention ───────────────────────────────────────────
    if user_id != authenticated_user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access denied")

    updates = req.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(400, detail="No valid update fields provided")

    try:
        db.supabase.table("profiles").update(updates).eq("id", user_id).execute()
        return {"success": True, "updated_fields": list(updates.keys())}
    except Exception as exc:
        logger.error(f"Profile update error: {exc}")
        raise HTTPException(500, detail="Update failed")
