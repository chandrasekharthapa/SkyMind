"""Regression Tests for End-to-End Prediction Pipeline and Data Contracts.

Verifies:
1. GoogleFlightsProvider normalization returns List[NormalizedFlight]
2. MarketSnapshotProvider consumes List[NormalizedFlight] without AttributeError
3. RecommendationEngine confidence calculation is deterministic and documented
4. PredictionService correctly passes lowest_fare to prediction response
"""

import pytest
import math
from unittest.mock import AsyncMock, MagicMock

from backend.services.flight_normalizer import NormalizedFlight, NormalizedItinerary, NormalizedSegment
from backend.services.flight_data_provider import GoogleFlightsProvider
from backend.services.market_snapshot_provider import MarketSnapshotProvider
from backend.services.recommendation_engine import RecommendationEngine
from backend.services.prediction_service import prediction_service


def build_sample_normalized_flight(price: float = 7500.0) -> NormalizedFlight:
    """Helper to build a valid NormalizedFlight model."""
    segment = NormalizedSegment(
        flight_number="6E101",
        departure_time="2026-07-23T08:00:00",
        arrival_time="2026-07-23T10:15:00",
        airline_code="6E",
        airline_name="IndiGo",
        origin="DEL",
        destination="BOM",
        duration="PT2H15M",
        stops=0,
        cabin="ECONOMY"
    )
    itinerary = NormalizedItinerary(duration="PT2H15M", segments=[segment])
    return NormalizedFlight(
        id="6E-101-7500",
        primary_airline="6E",
        primary_airline_name="IndiGo",
        seats_available=15,
        flight_number="6E101",
        itineraries=[itinerary],
        price=price,
        currency="INR"
    )


@pytest.mark.asyncio
async def test_market_snapshot_consumes_normalized_flights_without_attribute_error():
    """Verify MarketSnapshotProvider handles NormalizedFlight objects cleanly without dict AttributeError."""
    sample_flights = [build_sample_normalized_flight(7107.0), build_sample_normalized_flight(8200.0)]
    
    mock_provider = MagicMock()
    mock_provider.provider_name = "Mock Normalized Provider"
    mock_provider.search = AsyncMock(return_value=sample_flights)
    
    snapshot_provider = MarketSnapshotProvider(provider=mock_provider)
    snapshot = await snapshot_provider.get_market_snapshot("DEL", "BOM", "2026-07-23")
    
    assert snapshot.search_success is True
    assert snapshot.total_live_flights == 2
    assert snapshot.lowest_fare == 7107.0
    assert snapshot.highest_fare == 8200.0
    assert snapshot.average_fare == 7653.5


def test_recommendation_engine_deterministic_confidence():
    """Verify confidence calculation is deterministic and reflects model accuracy + data quality."""
    engine = RecommendationEngine()

    # Live market available
    rec_live = engine.generate_recommendation(
        current_lowest=7000.0,
        formatted_forecast=[{"day": 3, "price": 8500.0}],
        prediction_horizon=3,
        predicted_price=8500.0,
        origin="DEL",
        destination="BOM",
        snapshot_quality=1.0,
        model_accuracy=95.0,
        is_live_market=True
    )
    assert rec_live["decision"] == "BOOK_NOW"
    assert rec_live["confidence"] == 95.0  # 95% model accuracy * 1.0 snapshot quality

    # Historical mode fallback. This assertion used to read `== 80.75`, which was
    # `95.0 * 0.85` — the multiplier the old code paid for having no live market,
    # against a floor of 0.5 for having one. The test therefore enshrined the
    # inversion: it asserted that losing the data source raised the published
    # figure. The historical multiplier is now NO_LIVE_MARKET_QUALITY, pinned at or
    # below the live floor by an import-time check in confidence_policy.
    rec_hist = engine.generate_recommendation(
        current_lowest=None,
        formatted_forecast=[{"day": 3, "price": 8500.0}],
        prediction_horizon=3,
        predicted_price=8500.0,
        origin="DEL",
        destination="BOM",
        snapshot_quality=0.0,
        model_accuracy=95.0,
        is_live_market=False
    )
    assert rec_hist["decision"] == "MONITOR"
    assert rec_hist["confidence"] == 47.5  # 95.0 * NO_LIVE_MARKET_QUALITY (0.5)
    assert rec_hist["confidence"] <= rec_live["confidence"], (
        "no live market must never publish a higher confidence than a live one"
    )


def test_recommendation_engine_refuses_to_invent_a_confidence():
    """With no recorded model metric the recommendation publishes null, not 95.0.

    `model_accuracy` and `snapshot_quality` used to default to 95.0 and 1.0, so
    this call — which passes neither — was the exact shape that published the
    pipeline's maximum score with nothing behind it.
    """
    engine = RecommendationEngine()
    rec = engine.generate_recommendation(
        current_lowest=7000.0,
        formatted_forecast=[{"day": 3, "price": 8500.0}],
        prediction_horizon=3,
        predicted_price=8500.0,
        origin="DEL",
        destination="BOM"
    )
    assert rec["confidence"] is None
    assert rec["decision"] in ("BOOK_NOW", "WAIT")


def test_recommendation_engine_does_not_score_history_as_live():
    """A fare recovered from history is not an observed market.

    `current_lowest` being present is not evidence the market was reached. The
    decision branch keys on having a fare; the confidence keys on where the fare
    came from, and the caller states that once.
    """
    engine = RecommendationEngine()
    kwargs = dict(
        current_lowest=7000.0,
        formatted_forecast=[{"day": 3, "price": 8500.0}],
        prediction_horizon=3,
        predicted_price=8500.0,
        origin="DEL",
        destination="BOM",
        snapshot_quality=1.0,
        model_accuracy=95.0
    )
    from_history = engine.generate_recommendation(is_live_market=False, **kwargs)
    from_market = engine.generate_recommendation(is_live_market=True, **kwargs)
    assert from_history["decision"] == from_market["decision"], (
        "liveness must not change the booking decision, only its confidence"
    )
    assert from_history["confidence"] == 47.5
    assert from_market["confidence"] == 95.0


@pytest.mark.asyncio
async def test_google_flights_provider_returns_normalized_flight_instances():
    """Verify GoogleFlightsProvider normalizes raw flights."""
    sample = build_sample_normalized_flight(6500.0)
    mock_presentation = MagicMock()
    mock_presentation.flights = [sample]
    
    with pytest.MonkeyPatch.context() as m:
        m.setattr("backend.services.flight_search_service.flight_search_service.search", AsyncMock(return_value=mock_presentation))
        provider = GoogleFlightsProvider()
        flights = await provider.search("DEL", "BOM", "2026-07-23")
        
        assert len(flights) == 1
        assert flights[0].price == 6500.0
