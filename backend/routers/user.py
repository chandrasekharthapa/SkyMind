"""
User profile and trips endpoints.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


@router.get("/trips")
async def get_user_trips(user_id: str):
    """Get all trips for a user."""
    # In production: query Supabase
    return {
        "trips": [],
        "count": 0,
        "message": "Connect Supabase to see real data",
    }


@router.get("/profile/{user_id}")
async def get_profile(user_id: str):
    """Get user profile."""
    return {"user_id": user_id, "status": "Connect Supabase Auth"}
