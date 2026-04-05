"""
SkyMind — Price Alerts Router
Endpoints:
  POST   /alerts/subscribe          → create alert
  GET    /alerts/user/{user_id}     → list user's alerts
  DELETE /alerts/{alert_id}         → soft-delete alert
"""

import traceback
from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional

from database import database as db

router = APIRouter()


# ══════════════════════════════════════════════════════════════════════
# Request model  (Pydantic V2)
# ══════════════════════════════════════════════════════════════════════

class AlertRequest(BaseModel):
    # Accept both naming conventions from the frontend
    user_id: Optional[str] = None

    # Route — accept origin / origin_code
    origin_code: Optional[str] = Field(None, min_length=3, max_length=3)
    origin: Optional[str] = Field(None)

    destination_code: Optional[str] = Field(None, min_length=3, max_length=3)
    destination: Optional[str] = Field(None)

    departure_date: Optional[date] = None
    target_price: float = Field(..., gt=0)
    currency: str = "INR"
    cabin_class: str = "ECONOMY"

    # Notification prefs
    email: Optional[str] = None
    notify_email: Optional[str] = None  # alternate field from lib/api.ts
    phone: Optional[str] = None
    notify_phone: Optional[str] = None  # alternate field
    notify_sms: bool = False
    notify_whatsapp: bool = False

    user_label: Optional[str] = None

    @field_validator("origin_code", "destination_code", mode="before")
    @classmethod
    def upper_code(cls, v):
        if v:
            return str(v).upper().strip()
        return v

    def resolved_origin(self) -> str:
        return (self.origin_code or self.origin or "").upper().strip()

    def resolved_destination(self) -> str:
        return (self.destination_code or self.destination or "").upper().strip()

    def resolved_email(self) -> str | None:
        return self.email or self.notify_email or None

    def resolved_phone(self) -> str | None:
        return self.phone or self.notify_phone or None


# ══════════════════════════════════════════════════════════════════════
# POST /alerts/subscribe
# ══════════════════════════════════════════════════════════════════════

@router.post("/subscribe")
async def subscribe_alert(req: AlertRequest):
    """Subscribe to a price alert. Prevents duplicate (origin, dest, date) per user."""
    try:
        origin = req.resolved_origin()
        destination = req.resolved_destination()

        if not origin or not destination:
            raise HTTPException(422, detail="origin and destination are required")
        if origin == destination:
            raise HTTPException(422, detail="Origin and destination must differ")

        email_val = req.resolved_email()
        phone_val = req.resolved_phone()

        # ── Duplicate check ──────────────────────────────────────────
        if req.user_id and req.departure_date:
            existing = (
                db.supabase.table("price_alerts")
                .select("id")
                .eq("user_id", req.user_id)
                .eq("origin_code", origin)
                .eq("destination_code", destination)
                .eq("departure_date", str(req.departure_date))
                .eq("is_active", True)
                .execute()
            )
            if existing.data:
                return {
                    "success": False,
                    "alert_id": existing.data[0]["id"],
                    "message": f"Active alert already exists for {origin}→{destination} on {req.departure_date}.",
                }

        # ── Insert ───────────────────────────────────────────────────
        payload: dict = {
            "origin_code": origin,
            "destination_code": destination,
            "target_price": req.target_price,
            "currency": req.currency,
            "cabin_class": req.cabin_class,
            "notify_email": bool(email_val),
            "notify_sms": req.notify_sms or bool(phone_val),
            "notify_whatsapp": req.notify_whatsapp,
            "is_active": True,
        }
        if req.user_id:
            payload["user_id"] = req.user_id
        if req.departure_date:
            payload["departure_date"] = str(req.departure_date)
        if email_val:
            payload["email"] = email_val
        if phone_val:
            payload["phone"] = phone_val

        res = db.supabase.table("price_alerts").insert(payload).execute()
        if not res.data:
            raise HTTPException(500, detail="Failed to create alert in database")

        alert_id = res.data[0]["id"]

        return {
            "success": True,
            "alert_id": alert_id,
            "message": (
                f"Alert set! We'll notify you when "
                f"{origin}→{destination} drops below "
                f"₹{req.target_price:,.0f}"
            ),
        }

    except HTTPException:
        raise
    except Exception:
        traceback.print_exc()
        raise HTTPException(500, detail="Error creating alert")


# ══════════════════════════════════════════════════════════════════════
# GET /alerts/user/{user_id}
# ══════════════════════════════════════════════════════════════════════

@router.get("/user/{user_id}")
async def get_user_alerts(user_id: str):
    """Return all active alerts for a user, normalised to AlertRecord shape."""
    try:
        res = (
            db.supabase.table("price_alerts")
            .select("*")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .order("departure_date", desc=False)
            .execute()
        )

        raw = res.data or []

        # Normalise to AlertRecord shape expected by frontend useAlerts hook
        alerts = [
            {
                "id": a["id"],
                "origin": a.get("origin_code", ""),
                "destination": a.get("destination_code", ""),
                "target_price": float(a.get("target_price", 0)),
                "departure_date": str(a.get("departure_date", "")),
                "created_at": str(a.get("created_at", "")),
                "triggered": bool(a.get("triggered_count", 0)),
                "current_price": a.get("last_price"),
                "savings": (
                    float(a.get("target_price", 0)) - float(a.get("last_price", 0))
                    if a.get("last_price")
                    else None
                ),
            }
            for a in raw
        ]

        triggered = [a for a in alerts if a["triggered"]]

        return {
            "alerts": alerts,
            "triggered": triggered,
            "triggered_count": len(triggered),
            "count": len(alerts),
        }

    except Exception:
        traceback.print_exc()
        raise HTTPException(500, detail="Error fetching alerts")


# ══════════════════════════════════════════════════════════════════════
# DELETE /alerts/{alert_id}
# ══════════════════════════════════════════════════════════════════════

@router.delete("/{alert_id}")
async def delete_alert(alert_id: str):
    """Soft-delete a price alert."""
    try:
        check = (
            db.supabase.table("price_alerts")
            .select("id")
            .eq("id", alert_id)
            .execute()
        )
        if not check.data:
            raise HTTPException(404, detail="Alert not found")

        db.supabase.table("price_alerts").update({"is_active": False}).eq(
            "id", alert_id
        ).execute()

        return {"success": True, "message": "Alert deactivated"}

    except HTTPException:
        raise
    except Exception:
        traceback.print_exc()
        raise HTTPException(500, detail="Error deleting alert")
