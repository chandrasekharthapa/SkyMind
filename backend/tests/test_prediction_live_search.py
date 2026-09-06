import pytest
import sys
import os
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.services.prediction_service import PredictionService
from backend.services.market_snapshot_provider import MarketSnapshotProvider
from backend.services.flight_data_provider import FlightDataProvider
from backend.domain.market_snapshot import MarketSnapshot
from backend.tests.model_availability import requires_trained_model

# Dynamic future date so this test never fails due to date drift
FUTURE_DATE = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")

@pytest.mark.asyncio
async def test_prediction_service_invokes_snapshot_provider():
    """Verify PredictionService queries snapshot provider and never invokes search directly.

    Gated, and the reason is worth stating because the routing claim in that first
    line *sounds* model-independent. It is not, any more. `PredictionService.predict`
    checks `model_registry.supports_forecasting` at step 1b, deliberately ahead of
    the snapshot fetch at step 2, so that a request the active model cannot serve
    does not first pay for a scrape and an inference. With no loadable artifact the
    method therefore raises `PredictionUnavailable` before `get_market_snapshot` is
    ever called, and `mock_provider.get_market_snapshot.called` is False — not
    because routing broke, but because the run never got as far as routing.

    `assert res["predicted_price"] > 0` is model output regardless. Both assertions
    are inapplicable without an artifact, so the whole test is gated rather than
    split.
    """
    requires_trained_model()

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
    
    mock_provider = MagicMock(spec=MarketSnapshotProvider)
    mock_provider.get_market_snapshot = AsyncMock(return_value=mock_snapshot)
    
    service = PredictionService(market_snapshot_provider=mock_provider)
    
    res = await service.predict(
        origin="DEL",
        destination="BOM",
        departure_date=FUTURE_DATE
    )
    
    # 1. Assert snapshot provider was invoked
    assert mock_provider.get_market_snapshot.called
    assert res["predicted_price"] > 0
    assert res["current_market"]["lowest_fare"] == 5000.0
