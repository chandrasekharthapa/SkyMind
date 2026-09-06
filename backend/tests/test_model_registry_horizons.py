import pytest
import sys
import os
from datetime import date, timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from unittest.mock import MagicMock, AsyncMock

from backend.services.model_registry import model_registry

# `PredictionService` and `PredictionUnavailable` are imported inside the async
# test rather than here. Importing `prediction_service` at module scope pulls in
# the flight-data service, the MCP transport client and the OpenTelemetry
# packages, so the two synchronous registry assertions below could not run
# without the entire serving stack installed — which is why they were never
# executed offline while the metadata they assert was wrong.

# Dynamic future date so this test never fails due to date drift
FUTURE_DATE = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")

def test_model_registry_horizons_metadata():
    """The registry metadata that does not depend on which artifacts are loaded.

    `assert model_registry.prediction_horizon == 3` and
    `assert model_registry.supports_forecasting is True` used to be here. Both
    passed with no model loaded at all, because both properties were literals: the
    first was `getattr(self._predictor, "prediction_horizon", 3)` against an
    attribute nothing assigns, and the second defaulted to `True`. They are now
    derived from the loaded artifacts, so they belong in the two tests below —
    which supply the artifact state they are asserting about.
    """
    # The registry reports the predictor's own statement of its target. It used
    # to fall back to the literal "Future Lowest Fare", which described no
    # production path: the label is the fare on the same booking curve at the
    # earliest observation on or after t + horizon days.
    assert "booking curve" in model_registry.target_definition
    assert model_registry.target_definition == model_registry.training_target
    assert model_registry.supported_horizons == [1, 3, 7]
    assert 0 not in model_registry.supported_horizons


class _Loaded:
    """A predictor stand-in that declares exactly the state each case is about."""

    supported_horizons = [1, 3, 7]
    supports_forecasting = True
    legacy_mode = False

    def __init__(self, models=None, routes=None, **over):
        self.models = dict(models or {})
        self.trained_routes = list(routes or [])
        self.__dict__.update(over)

    @property
    def primary_horizon(self):
        return min(self.models) if self.models else None


def _registry(predictor):
    from backend.services.model_registry import ModelRegistry
    return ModelRegistry(predictor=predictor)


def test_prediction_horizon_is_the_shortest_horizon_actually_loaded():
    """Not the literal 3.

    `prediction_service` uses this value twice — to select which forecast point
    becomes the published `predicted_price`, and to choose whose accuracy figure is
    published beside it. With a 1d-and-7d build it therefore looked for a 3d point
    that the curve does not contain, and published a 3d label over a number
    produced at a different horizon.
    """
    assert _registry(_Loaded(models={1: object(), 7: object()})).prediction_horizon == 1
    assert _registry(_Loaded(models={3: object(), 7: object()})).prediction_horizon == 3
    assert _registry(_Loaded(models={7: object()})).prediction_horizon == 7

    # Nothing loaded: there is no horizon to name, so none is reported. This
    # asserted `== 1`, the smallest *declared* horizon, which the property
    # substituted on the stated grounds that a response model needed an int —
    # `GET /api/v1/system/model/metadata` has no response model, and it published
    # `prediction_horizon: 1` next to `trained: false`.
    assert _registry(_Loaded(models={})).prediction_horizon is None


def test_predictor_primary_horizon_is_the_shortest_loaded_or_none():
    """The property the registry reads, asserted on the real class.

    `_Loaded` above supplies `primary_horizon` directly, because that is the whole
    of the registry's contract with the predictor. This test is the other half: that
    `PricePredictor` computes it from what it has actually loaded, and reports the
    legacy pickle's own recorded horizon when that is all there is.
    """
    from backend.ml.price_model import PricePredictor

    predictor = PricePredictor()
    assert predictor.primary_horizon is None, (
        "a predictor with nothing loaded must not name a horizon"
    )

    predictor.models = {7: object(), 3: object()}
    assert predictor.primary_horizon == 3, "shortest loaded, not dict insertion order"

    legacy = PricePredictor()
    legacy.legacy_mode = True
    legacy.legacy_horizon = 3
    assert legacy.primary_horizon == 3
    # A legacy pickle that records no horizon cannot name one. `predict()` says so
    # too: it can only refuse a mismatch it is able to see.
    legacy.legacy_horizon = None
    assert legacy.primary_horizon is None


def test_forecasting_is_only_advertised_when_a_horizon_model_is_loaded():
    """The fallback was `True`, so it was advertised while `forecast()` refused.

    `PricePredictor.__init__` sets `supports_forecasting = True`, so the attribute
    is present and true on a predictor that has never loaded anything — the
    `getattr` default was not even the only way to reach the wrong answer.
    """
    assert _registry(_Loaded(models={1: object()})).supports_forecasting is True
    assert _registry(_Loaded(models={})).supports_forecasting is False
    assert _registry(
        _Loaded(models={1: object()}, supports_forecasting=False)
    ).supports_forecasting is False


def test_supported_routes_are_the_routes_the_artifact_records():
    """Was the literal `["DEL-BOM", "BOM-DEL"]`, whatever had been trained."""
    assert _registry(_Loaded(models={1: object()},
                             routes=["blr-del", " DEL-BOM "])).supported_routes == [
        "BLR-DEL", "DEL-BOM"]
    # No recorded route list is reported as none, not as two invented routes.
    assert _registry(_Loaded(models={1: object()})).supported_routes == []


def test_registry_reports_no_horizons_when_predictor_declares_none():
    """An undeclared horizon set is reported as empty, not as a default four.

    The fallback was `[0, 1, 3, 7]`, so `/capabilities` advertised four horizons
    — including the untrainable 0 — for any predictor that did not declare them.
    """
    from backend.services.model_registry import ModelRegistry

    class Bare:
        pass

    registry = ModelRegistry(predictor=Bare())
    assert registry.supported_horizons == []
    assert registry.target_definition == "unknown"

@pytest.mark.asyncio
async def test_prediction_service_rejects_incompatible_horizon():
    """Verify PredictionService rejects if forecasting is not supported."""
    from backend.services.prediction_service import PredictionService
    from backend.utils.exceptions import PredictionUnavailable

    mock_registry = MagicMock()
    mock_registry.supports_forecasting = False
    # Derived from `feature_metadata`, not typed out — see the same change in
    # `test_legacy_model_rejection.py`. A test double is the one place a stale
    # copy of the feature contract can survive a repository-wide de-duplication.
    from backend.ml.feature_metadata import LEGACY_FEATURE_SET
    mock_registry.expected_features = [f.name for f in LEGACY_FEATURE_SET]
    
    service = PredictionService(model_registry=mock_registry)
    
    # Executing predict should fail fast with PredictionUnavailable exception
    with pytest.raises(PredictionUnavailable, match="Active model does not support forecasting"):
        # We can bypass snapshot provider check by passing Mock
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
        await service.predict("DEL", "BOM", FUTURE_DATE)
