"""Multi-Horizon Revisit Collection Strategy for SkyMind Dataset Pipeline.

Defines target booking curve collection horizons to systematically revisit flight itineraries
over time, accumulating historical price curves.
"""

from typing import List, Dict, Any
from datetime import datetime, date, timedelta, timezone

TARGET_COLLECTION_HORIZONS = [90, 75, 60, 45, 30, 21, 14, 10, 7, 5, 3, 2, 1, 0]


class CollectionStrategy:
    """Manages multi-horizon departure target generation for flight route collection."""

    def __init__(self, horizons: List[int] = None):
        self.horizons = horizons or TARGET_COLLECTION_HORIZONS

    def get_target_departure_dates(self, base_date: date = None) -> List[date]:
        """Calculates target departure dates based on collection horizons."""
        today = base_date or datetime.now(timezone.utc).date()
        return [today + timedelta(days=h) for h in self.horizons]

    def is_target_horizon(self, days_until_dep: int) -> bool:
        """Checks if a given lead time matches a target collection horizon."""
        return days_until_dep in self.horizons


collection_strategy = CollectionStrategy()
