"""Runtime Routes Validation Suite."""

from datetime import date, timedelta

import pytest
from backend.services.market_snapshot_provider import market_snapshot_provider
from backend.services.prediction_service import prediction_service
from backend.tests.model_availability import requires_trained_model

# Computed, not written down: `PredictionValidator.validate_request` rejects a
# past departure date, so a literal turns this test red on a date nobody chose.
# It was "2026-07-30", which went past on 2026-07-31.
FUTURE_DATE = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")


@pytest.mark.asyncio
async def test_runtime_multiple_routes_validation():
    """Verify system generates deterministic predictions across multiple route pairs.

    Gated on a servable artifact: `assert resp["predicted_price"] > 0` is a claim
    about a number the model produces, and with the shipped artifacts quarantined
    `predict` refuses before producing one.
    """
    requires_trained_model()
    routes = [("DEL", "BOM"), ("DEL", "BBI"), ("BOM", "HYD"), ("DEL", "MAA")]
    predictions = {}

    for orig, dest in routes:
        resp = await prediction_service.predict(origin=orig, destination=dest, departure_date=FUTURE_DATE)
        assert resp["predicted_price"] > 0
        assert "recommendation" in resp
        predictions[f"{orig}-{dest}"] = resp["predicted_price"]

    # Verify at least 2 distinct price predictions across routes
    unique_prices = set(predictions.values())
    assert len(unique_prices) >= 2, "System must return route-differentiated predictions"
