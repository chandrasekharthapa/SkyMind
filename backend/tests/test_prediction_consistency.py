"""Integration Test: Prediction Consistency."""

from datetime import date, timedelta

import pytest
from backend.services.prediction_service import prediction_service
from backend.tests.model_availability import requires_trained_model

# Computed, not written down: `PredictionValidator.validate_request` rejects a
# past departure date, so a literal turns this test red on a date nobody chose.
# It was "2026-07-30", which went past on 2026-07-31.
FUTURE_DATE = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")


@pytest.mark.asyncio
async def test_prediction_deterministic_consistency():
    """Verify identical inputs yield identical prediction outputs.

    Gated: with no servable artifact `PredictionService.predict` refuses at its
    capability precondition, so there is no pair of outputs to compare. Two
    identical refusals are not the determinism this test is about.
    """
    requires_trained_model()

    resp1 = await prediction_service.predict(origin="DEL", destination="BOM", departure_date=FUTURE_DATE)
    resp2 = await prediction_service.predict(origin="DEL", destination="BOM", departure_date=FUTURE_DATE)

    assert resp1["predicted_price"] == resp2["predicted_price"]
    assert resp1["recommendation"]["decision"] == resp2["recommendation"]["decision"]
