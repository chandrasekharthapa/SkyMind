"""
Price alert subscription endpoints.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class AlertRequest(BaseModel):
    user_id: str
    origin_code: str
    destination_code: str
    departure_date: str
    target_price: float
    currency: str = "INR"
    cabin_class: str = "ECONOMY"


@router.post("/subscribe")
async def subscribe_alert(req: AlertRequest):
    """Subscribe to a price alert."""
    # In production: save to Supabase price_alerts table
    return {
        "success": True,
        "alert_id": "alert_demo_123",
        "message": f"Alert set! We'll notify you when {req.origin_code}→{req.destination_code} drops below ₹{req.target_price:,.0f}",
    }


@router.get("/user/{user_id}")
async def get_user_alerts(user_id: str):
    """Get all active alerts for a user."""
    return {"alerts": [], "count": 0}


@router.delete("/{alert_id}")
async def delete_alert(alert_id: str):
    """Delete a price alert."""
    return {"success": True, "message": "Alert deleted"}
