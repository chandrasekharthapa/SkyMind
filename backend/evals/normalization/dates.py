"""Date Canonicalizer for SkyMind Evaluation Platform."""

import re
from datetime import datetime, timedelta, timezone
from typing import Optional


def normalize_date(date_text: Optional[str], base_date: Optional[datetime] = None) -> Optional[str]:
    """Canonicalizes relative date keywords ('tomorrow', 'in 7 days') or ISO strings to YYYY-MM-DD."""
    if not date_text:
        return None

    today = base_date or datetime.now(timezone.utc)
    lowered = str(date_text).strip().lower()

    if lowered in ("today",):
        return today.strftime("%Y-%m-%d")
    if lowered in ("tomorrow", "next day"):
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    if lowered in ("day after tomorrow",):
        return (today + timedelta(days=2)).strftime("%Y-%m-%d")

    match_days = re.search(r"in\s+(\d+)\s+days?", lowered)
    if match_days:
        num_days = int(match_days.group(1))
        return (today + timedelta(days=num_days)).strftime("%Y-%m-%d")

    match_iso = re.search(r"\b20\d{2}-\d{2}-\d{2}\b", str(date_text))
    if match_iso:
        return match_iso.group(0)

    return str(date_text).strip()
