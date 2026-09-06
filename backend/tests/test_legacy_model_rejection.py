import pytest
import sys
import os
from datetime import date, timedelta
from unittest.mock import MagicMock, AsyncMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.ml.feature_metadata import LEGACY_FEATURE_SET
from backend.services.prediction_service import PredictionService
from backend.utils.exceptions import PredictionUnavailable

# Dynamic future date so this test never fails due to date drift
FUTURE_DATE = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")

@pytest.mark.asyncio
async def test_legacy_model_forecasting_rejection():
    """Verify that PredictionService rejects forecast requests if model does not support forecasting."""
    mock_registry = MagicMock()
    mock_registry.supports_forecasting = False
    # Derived, not typed. This was a hand-written copy of the legacy 16 — one of
    # five that existed in the repository, and the last one a test still held. A
    # double that advertises a stale contract passes while the real registry no
    # longer would.
    mock_registry.expected_features = [f.name for f in LEGACY_FEATURE_SET]
    
    service = PredictionService(model_registry=mock_registry)
    
    # We construct a mock snapshot provider returning fresh snapshot
    from backend.domain.market_snapshot import MarketSnapshot
    mock_snapshot = MarketSnapshot(
        lowest_fare=5000.0,
        highest_fare=10000.0,
        average_fare=7500.0,
        median_fare=7500.0,
        fare_spread=5000.0,
        price_std_dev=2500.0,
        total_live_flights=2,
        direct_flight_count=2,
        connecting_flight_count=0,
        retrieval_timestamp="2026-07-19T12:00:00",
        provider="Test Provider",
        search_duration=0.1,
        search_success=True
    )
    
    mock_provider = MagicMock()
    mock_provider.get_market_snapshot = AsyncMock(return_value=mock_snapshot)
    service.market_snapshot_provider = mock_provider
    
    with pytest.raises(PredictionUnavailable, match="Active model does not support forecasting"):
        await service.predict("DEL", "BOM", FUTURE_DATE)
