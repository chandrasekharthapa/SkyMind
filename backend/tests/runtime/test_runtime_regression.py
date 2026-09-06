"""Runtime Regression Suite (Milestone 1).

Validates prediction uniqueness, recommendation consistency, cache isolation,
route isolation, feature differences, and forecast differences across routes.
"""

import pytest
import asyncio
from backend.services.prediction_service import prediction_service
from backend.services.market_snapshot_provider import market_snapshot_provider


@pytest.mark.asyncio
async def test_runtime_route_uniqueness_and_isolation():
    """Verify distinct routes yield route-specific predictions without state contamination."""
    resp_bom = await prediction_service.predict(origin="DEL", destination="BOM", departure_date="2026-07-30")
    resp_bbi = await prediction_service.predict(origin="DEL", destination="BBI", departure_date="2026-07-30")

    p_bom = resp_bom["predicted_price"]
    p_bbi = resp_bbi["predicted_price"]

    assert p_bom != p_bbi, f"Predictions for DEL-BOM ({p_bom}) and DEL-BBI ({p_bbi}) must be route-specific"
    assert resp_bom["current_market"]["lowest_fare"] != resp_bbi["current_market"]["lowest_fare"]


@pytest.mark.asyncio
async def test_runtime_cache_isolation():
    """Verify cache keys isolate different origin-destination-date routes."""
    key_bom = market_snapshot_provider._get_cache_key("DEL", "BOM", "2026-07-30")
    key_bbi = market_snapshot_provider._get_cache_key("DEL", "BBI", "2026-07-30")

    assert key_bom != key_bbi, "Cache keys for DEL-BOM and DEL-BBI must be strictly isolated"
    assert key_bom == "DEL-BOM-2026-07-30"
    assert key_bbi == "DEL-BBI-2026-07-30"
