"""Integration Test: Route Isolation."""

from datetime import date, timedelta

import pytest

from backend.services.prediction_service import prediction_service
from backend.tests.model_availability import requires_trained_model

# Computed, not written down: the departure date has to be in the future or
# `PredictionValidator.validate_request` rejects it, so a literal turns this test
# red on a date nobody chose. It was "2026-07-30".
FUTURE_DATE = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")


@pytest.mark.asyncio
async def test_route_isolation_no_state_leakage():
    """Two routes must not share state inside a served prediction.

    Gated on a servable artifact: both calls go through
    `PredictionService.predict`, which refuses at its capability precondition
    while the shipped models are quarantined. Two identical refusals would prove
    nothing about isolation, and an ungated version read as a state-leak bug.
    """
    requires_trained_model()
    resp1 = await prediction_service.predict(origin="DEL", destination="BOM", departure_date=FUTURE_DATE)
    resp2 = await prediction_service.predict(origin="BOM", destination="HYD", departure_date=FUTURE_DATE)

    # Read from the response, with no default. This used to be
    # `resp.get("search_metadata", {}).get("origin") or resp.get("route", {}).get("origin", "DEL")`
    # and then `assert origin1 == "DEL"` — neither key existed, so the assertion
    # compared the literal against itself and the test could not fail for its
    # stated reason no matter what the service returned.
    assert resp1["search_metadata"]["origin"] == "DEL"
    assert resp1["search_metadata"]["destination"] == "BOM"
    assert resp1["search_metadata"]["departure_date"] == FUTURE_DATE

    assert resp2["search_metadata"]["origin"] == "BOM"
    assert resp2["search_metadata"]["destination"] == "HYD"

    # The point of the test: two routes must not share state. Prices may both be
    # unavailable offline, in which case there is nothing to compare — but the
    # routes must still be distinct.
    p1, p2 = resp1["predicted_price"], resp2["predicted_price"]
    if p1 is not None and p2 is not None:
        assert p1 != p2, "two different routes returned the same predicted price"
