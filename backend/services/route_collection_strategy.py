"""Route Collection Strategy.

Dynamically evaluates popular routes, active user price alerts, existing database coverage,
and cold start requirements to determine prioritized routes for continuous data ingestion.
"""

import logging
from typing import List, Tuple
from backend.database.database import database as db

logger = logging.getLogger(__name__)

from backend.route_catalog import route_catalog_config

class RouteCollectionStrategy:
    def __init__(self):
        self.config = route_catalog_config

    async def get_routes_to_collect(self) -> List[Tuple[str, str]]:
        """Determine active domestic routes requiring historical collections."""
        # 1. Load active routes from configuration catalog
        routes = self.config.get_active_routes()

        # 2. Extract additional routes from active price alerts
        try:
            res = db.supabase.table("price_alerts").select("origin_code, destination_code").eq("is_active", True).execute()
            if res.data:
                for r in res.data:
                    orig = r.get("origin_code")
                    dest = r.get("destination_code")
                    if orig and dest:
                        routes.append((orig.strip().upper(), dest.strip().upper()))
        except Exception as e:
            logger.warning(f"[RouteCollectionStrategy] Failed to query active price alert routes: {e}")

        # Deduplicate list preserving order
        unique_routes = []
        seen = set()
        for orig, dest in routes:
            orig_clean = orig.strip().upper()
            dest_clean = dest.strip().upper()
            if len(orig_clean) != 3 or len(dest_clean) != 3 or orig_clean == dest_clean:
                continue
            key = (orig_clean, dest_clean)
            if key not in seen:
                seen.add(key)
                unique_routes.append(key)

        logger.info(f"[RouteCollectionStrategy] Configured & active alert routes: {len(unique_routes)} unique pairs.")
        return unique_routes

    def get_route_batches(self, batch_size: int = None) -> List[List[Tuple[str, str]]]:
        """Returns active routes split into deterministic batches."""
        return self.config.create_route_batches(batch_size=batch_size)

route_collection_strategy = RouteCollectionStrategy()
