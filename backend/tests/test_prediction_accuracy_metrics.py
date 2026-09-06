"""What the consistency validator does *not* publish.

This module asserted `"mae" in metrics`, `"rmse" in metrics`, `"mape" in metrics`,
`"bias" in metrics`, `"drift" in metrics` on the block
`PredictionConsistencyValidator` returned — and every one of those keys was
present, holding `0.0`, from five locals initialised to zero and never assigned.
Key-presence assertions cannot tell a computed figure from a constant, so the test
passed for exactly as long as the numbers were fabricated, and would have kept
passing if the real computation were deleted.

The metrics are gone from the validator, because prediction time has no realised
fare to compare against. These tests pin their absence, and pin the plausibility
checks the validator does perform.
"""
import math

from backend.services.consistency_validator import PredictionConsistencyValidator
from backend.domain.market_snapshot import MarketSnapshot


def _snapshot(**overrides) -> MarketSnapshot:
    fields = dict(
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
        search_success=True,
    )
    fields.update(overrides)
    return MarketSnapshot(**fields)


FORECAST = [{"day": 3, "date": "2026-07-29", "price": 5500.0, "lower": 5200.0, "upper": 5800.0}]


def test_validator_publishes_no_forecast_error_metrics():
    """No `metrics` block, and none of the five fabricated keys anywhere in the result."""
    res = PredictionConsistencyValidator.validate_consistency(
        predicted_price=5200.0, market_snapshot=_snapshot(), forecast=FORECAST,
        route="DEL-BOM",
    )
    assert "metrics" not in res
    forbidden = {"mae", "rmse", "mape", "bias", "drift"}
    assert not (forbidden & set(res)), f"fabricated metric key back at top level: {res}"


def test_validator_reports_deviation_from_the_lowest_live_fare():
    res = PredictionConsistencyValidator.validate_consistency(
        predicted_price=5200.0, market_snapshot=_snapshot(), forecast=FORECAST,
        route="DEL-BOM",
    )
    assert res["deviation"] == 200.0          # |5200 - 5000|
    assert res["anomalous"] is False
    assert res["reasons"] == []


def test_validator_flags_a_prediction_far_above_the_market():
    res = PredictionConsistencyValidator.validate_consistency(
        predicted_price=30000.0, market_snapshot=_snapshot(), forecast=FORECAST,
        route="DEL-BOM",
    )
    assert res["anomalous"] is True           # 30000 > 2.5 * 10000
    assert any("2.5x" in r for r in res["reasons"])


def test_validator_flags_a_prediction_far_below_the_market():
    res = PredictionConsistencyValidator.validate_consistency(
        predicted_price=1000.0, market_snapshot=_snapshot(), forecast=FORECAST,
        route="DEL-BOM",
    )
    assert res["anomalous"] is True           # 1000 < 0.3 * 5000
    assert any("30%" in r for r in res["reasons"])


def test_validator_flags_day_one_disagreeing_with_the_point_prediction():
    res = PredictionConsistencyValidator.validate_consistency(
        predicted_price=5000.0,
        market_snapshot=_snapshot(),
        forecast=[{"day": 1, "date": "2026-07-27", "price": 9500.0}],
    )
    assert res["anomalous"] is True           # |9500 - 5000| > 0.8 * 5000
    assert any("deviates" in r for r in res["reasons"])


def test_validator_skips_every_check_without_live_benchmarks():
    """A NaN market gives the skip shape — and no deviation, rather than a zero one."""
    res = PredictionConsistencyValidator.validate_consistency(
        predicted_price=5200.0,
        market_snapshot=_snapshot(lowest_fare=math.nan, highest_fare=math.nan),
        forecast=FORECAST,
    )
    assert res["anomalous"] is False
    assert "deviation" not in res
    assert res["reasons"] == ["Missing live market price benchmarks."]
