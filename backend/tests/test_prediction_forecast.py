"""What `forecast()` publishes, and what it refuses.

Two of these are gated on a model existing on disk. That is not a way of
switching them off: `requires_trained_model()` calls the real loader and skips
only when nothing servable loaded, so a loader bug still fails. The third is
ungated on purpose — a refusal is exactly what an incomplete snapshot should
produce, with or without a model, and that is the assertion.

This module previously held one test that called
`predictor.forecast(snapshot, days=5)` and asserted `len(forecast) == 4`. Three
things were wrong with it. `days` was a parameter `forecast()` never read, so the
5 did nothing. Four points cannot be returned by a method that publishes one per
loaded horizon out of `[1, 3, 7]`. And the snapshot it passed named no airline
and no flight number, which since the curve-identity fix is a refusal — so the
test's subject no longer existed.
"""

import pytest

from backend.ml.price_model import get_predictor
from backend.tests.model_availability import requires_trained_model
from backend.utils.exceptions import InsufficientHistory

# A snapshot with a complete identity: the five parts of the booking-curve key
# plus the two per-flight columns. Anything less is a refusal, which is the
# subject of the last test rather than of the first two.
def _snapshot(**overrides):
    snap = {
        "origin": "DEL",
        "destination": "BOM",
        "airline": "6E",
        "flight_number": "6E101",
        "departure_date": "2026-12-20",
        "departure_time": "2026-12-20T21:40:00",
        "seats_available": 12,
        "current_price": 9500.0,
    }
    snap.update(overrides)
    return snap


def test_a_forecast_publishes_one_point_per_loaded_horizon():
    """The count is derived, not asserted as a literal.

    `forecast()` iterates `[h for h in supported_horizons if h in models]`, so
    the number of points is a fact about what loaded. Writing `== 4` pinned a
    curve length no configuration of this code produces.
    """
    horizons = requires_trained_model()
    predictor = get_predictor()

    try:
        forecast = predictor.forecast(_snapshot())
    except InsufficientHistory as exc:
        pytest.skip(
            f"a model is loaded but this route has no usable price history: {exc}")

    expected = [h for h in predictor.supported_horizons if h in predictor.models]
    assert [d["day"] for d in forecast] == expected, (
        f"loaded horizons {horizons}, servable {expected}, published "
        f"{[d.get('day') for d in forecast]}")


def test_every_published_point_carries_an_interval_that_contains_it():
    horizons = requires_trained_model()
    predictor = get_predictor()

    try:
        forecast = predictor.forecast(_snapshot())
    except InsufficientHistory as exc:
        pytest.skip(
            f"a model is loaded but this route has no usable price history: {exc}")

    assert forecast, f"horizons {horizons} loaded but no point was published"
    for day in forecast:
        for key in ("day", "date", "price", "lower", "upper"):
            assert key in day, f"{key} missing from {day}"
        assert day["lower"] <= day["price"] <= day["upper"], day
        # The interval is derived from recorded residuals now, not from ±6% of
        # the point. A zero-width interval would mean no residuals were found,
        # which the engine is supposed to refuse rather than publish.
        assert day["lower"] < day["upper"], (
            f"zero-width interval at horizon {day['day']}: {day}")


def test_a_snapshot_with_no_flight_identity_is_refused_rather_than_answered():
    """Ungated: this holds whether or not a model is on disk.

    With no model, `ensure_ready()` raises `FileNotFoundError` before the
    identity is read; with one, the missing airline and flight number make the
    booking-curve key incomplete. Either way the caller gets an exception rather
    than a curve, which is the property under test — the old behaviour was to
    forecast this as an IndiGo flight because `snapshot.get("airline", "6E")`
    supplied one.
    """
    predictor = get_predictor()
    anonymous = _snapshot(airline=None, flight_number=None)

    with pytest.raises((InsufficientHistory, FileNotFoundError)):
        predictor.forecast(anonymous)
