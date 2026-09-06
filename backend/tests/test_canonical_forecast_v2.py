"""Unit & Integration Tests for SkyMind Canonical Forecast System."""

import pytest
import math
from backend.services.forecast.savings_calculator import SavingsCalculator
from backend.services.forecast.timeline_builder import TimelineBuilder
from backend.services.forecast.confidence_engine import ConfidenceEngine
from backend.services.forecast.forecast_validator import ForecastValidationEngine
from backend.services.forecast.assembler import ForecastAssembler
from backend.services.forecast.canonical_forecast_service import canonical_forecast_service
from backend.mappers.forecast_mapper import ForecastMapper


def test_savings_calculator():
    """Verify single-source savings calculation logic."""
    # Degraded / No Current Fare
    abs_sav, pct_sav = SavingsCalculator.calculate_savings(None, 5000.0)
    assert abs_sav == 0.0 and pct_sav == 0.0

    # Current fare lower than future min fare -> BUY NOW branch
    abs_sav, pct_sav = SavingsCalculator.calculate_savings(6487.0, 6608.0)
    assert abs_sav == 0.0 and pct_sav == 0.0

    # Current fare higher than future min fare -> WAIT branch
    abs_sav, pct_sav = SavingsCalculator.calculate_savings(7000.0, 6300.0)
    assert abs_sav == 700.0 and pct_sav == 10.0


def test_timeline_builder():
    """Verify timeline point building, day 0 alignment, and bounds validation."""
    raw_forecast = [
        {"day": 1, "date": "2026-08-01", "price": 5000.0, "lower": 4800.0, "upper": 5200.0},
        {"day": 3, "date": "2026-08-03", "price": 4500.0, "lower": 4300.0, "upper": 4700.0}
    ]
    builder = TimelineBuilder()
    points = builder.build_timeline(raw_forecast, current_fare=5200.0, base_confidence=90.0)

    assert len(points) == 3, "Should automatically insert Day 0 point"
    assert points[0].horizon_days == 0
    assert points[0].predicted_price == 5200.0
    assert points[1].horizon_days == 1
    assert points[2].horizon_days == 3

    # The inserted day-0 point is the observed market fare, not a model output, so
    # it must carry no confidence at all. It previously inherited the model's
    # figure, which asserted an accuracy claim about a number the model never
    # produced. The forecast points, which have no confidence of their own here,
    # take the base.
    assert points[0].confidence_score is None
    assert points[1].confidence_score == 90.0
    assert points[2].confidence_score == 90.0


def test_timeline_point_confidence_precedence():
    """A point's own recorded confidence wins over the aggregate, and None survives."""
    builder = TimelineBuilder()
    raw_forecast = [
        {"day": 1, "date": "2026-08-01", "price": 5000.0, "lower": 4800.0,
         "upper": 5200.0, "confidence": 98.64},
        {"day": 3, "date": "2026-08-03", "price": 4500.0, "lower": 4300.0,
         "upper": 4700.0, "confidence": None},
        {"day": 5, "date": "2026-08-05", "price": 4400.0, "lower": 4200.0,
         "upper": 4600.0}
    ]
    points = builder.build_timeline(raw_forecast, current_fare=None, base_confidence=90.59)

    by_day = {p.horizon_days: p for p in points}
    assert by_day[1].confidence_score == 98.64, "per-horizon metric must win"
    assert by_day[3].confidence_score is None, "an explicit None must not be back-filled"
    assert by_day[5].confidence_score == 90.59, "a point with no figure takes the base"


def test_timeline_builder_accepts_null_base_confidence():
    """With no recorded metric anywhere, every model point publishes null."""
    builder = TimelineBuilder()
    raw_forecast = [
        {"day": 1, "date": "2026-08-01", "price": 5000.0, "lower": 4800.0, "upper": 5200.0}
    ]
    points = builder.build_timeline(raw_forecast, current_fare=None, base_confidence=None)
    assert points[0].confidence_score is None
    assert points[0].to_dict()["confidence_score"] is None


def test_confidence_engine():
    """Verify confidence breakdown scoring."""
    engine = ConfidenceEngine()
    res = engine.compute_confidence(model_accuracy=95.0, snapshot_quality=1.0, is_live_market=True)
    assert res["overall_confidence"] == 95.0
    assert res["breakdown"]["model_validation_score"] == 95.0
    assert res["breakdown"]["market_data_quality"] == 1.0


def test_confidence_engine_publishes_null_when_unmeasured():
    """No recorded accuracy means a null confidence, not a low or default one."""
    engine = ConfidenceEngine()
    res = engine.compute_confidence(model_accuracy=None, snapshot_quality=1.0, is_live_market=True)
    assert res["overall_confidence"] is None
    assert res["breakdown"]["model_validation_score"] is None
    assert res["breakdown"]["prediction_reliability"] is None


def test_confidence_engine_is_monotone_in_information():
    """Losing the live market must never raise the published confidence.

    The old code paid `accuracy * 0.85` with no live market against a floor of
    `accuracy * 0.5` with one, so a request that failed to reach the market scored
    higher than one that reached a market of the worst measurable quality.
    """
    engine = ConfidenceEngine()
    worst_live = engine.compute_confidence(
        model_accuracy=95.0, snapshot_quality=0.0, is_live_market=True
    )["overall_confidence"]
    no_live = engine.compute_confidence(
        model_accuracy=95.0, snapshot_quality=1.0, is_live_market=False
    )["overall_confidence"]
    assert no_live <= worst_live, (
        f"no live market published {no_live} against {worst_live} for the worst "
        "live market; missing information raised the score"
    )


def test_confidence_engine_clamps_to_scale_only():
    """A measured figure is bounded to 0-100 and otherwise reported as measured.

    `max(70.0, min(99.0, x))` rewrote a model measured at 42 as 70 and one at 100
    as 99. Only the scale of the published field may bound the value.
    """
    engine = ConfidenceEngine()
    low = engine.compute_confidence(
        model_accuracy=42.0, snapshot_quality=1.0, is_live_market=True
    )
    assert low["breakdown"]["model_validation_score"] == 42.0
    high = engine.compute_confidence(
        model_accuracy=100.0, snapshot_quality=1.0, is_live_market=True
    )
    assert high["breakdown"]["model_validation_score"] == 100.0


def test_forecast_validator_invariants():
    """Verify formal mathematical invariant assertions."""
    validator = ForecastValidationEngine()
    builder = TimelineBuilder()
    
    raw_forecast = [{"day": 0, "date": "2026-07-26", "price": 6000.0, "lower": 5800.0, "upper": 6200.0}]
    timeline = builder.build_timeline(raw_forecast, current_fare=6000.0, base_confidence=90.0)

    # Valid BOOK_NOW invariant
    diag_valid = validator.validate(
        current_fare=6000.0,
        expected_min_fare=6000.0,
        optimal_horizon_days=0,
        decision="BOOK_NOW",
        calculated_savings=0.0,
        timeline=timeline
    )
    assert diag_valid.invariants_passed is True
    assert len(diag_valid.violations) == 0

    # Invalid WAIT invariant (decision WAIT but savings == 0)
    diag_invalid = validator.validate(
        current_fare=6000.0,
        expected_min_fare=6000.0,
        optimal_horizon_days=0,
        decision="WAIT",
        calculated_savings=0.0,
        timeline=timeline
    )
    assert diag_invalid.invariants_passed is False
    assert len(diag_invalid.violations) > 0


def test_canonical_forecast_service_integration():
    """Verify end-to-end CanonicalForecastService build and Mapper serialization."""
    raw_forecast = [
        {"day": 0, "date": "2026-07-26", "price": 6487.0, "lower": 6200.0, "upper": 6700.0},
        {"day": 7, "date": "2026-08-02", "price": 6608.0, "lower": 6400.0, "upper": 6900.0}
    ]
    domain = canonical_forecast_service.build_canonical_forecast(
        formatted_forecast=raw_forecast,
        current_fare=6487.0,
        model_accuracy=95.0,
        snapshot_quality=1.0,
        is_live_market=True
    )
    assert domain.recommendation_decision == "BOOK_NOW"
    assert domain.calculated_savings == 0.0
    assert domain.optimal_horizon_days == 0
    assert domain.is_valid is True

    dto = ForecastMapper.to_dto(domain)
    assert dto["recommendation_decision"] == "BOOK_NOW"
    assert dto["calculated_savings"] == 0.0
    assert dto["diagnostics"]["invariants_passed"] is True
    assert len(dto["timeline"]) == 2
    assert "forecast_metadata" in dto
    assert dto["forecast_metadata"]["currency"] == "INR"
    assert "metadata" in dto["timeline"][0]


@pytest.mark.parametrize("c_price, f_price, expected_rec, expected_sav", [
    (5000.0, 5500.0, "BOOK_NOW", 0.0),
    (5000.0, 4500.0, "WAIT", 500.0),
    (5000.0, 5000.0, "BOOK_NOW", 0.0),
    (None, 4500.0, "MONITOR", 0.0)
])
def test_forecast_property_reconciliation(c_price, f_price, expected_rec, expected_sav):
    """Property-based verification of forecast reconciliation invariants across price points."""
    raw_forecast = [
        {"day": 0, "date": "2026-07-26", "price": c_price if c_price else f_price, "lower": 4000.0, "upper": 6000.0},
        {"day": 5, "date": "2026-07-31", "price": f_price, "lower": 4000.0, "upper": 6000.0}
    ]
    domain = canonical_forecast_service.build_canonical_forecast(
        formatted_forecast=raw_forecast,
        current_fare=c_price,
        model_accuracy=95.0,
        snapshot_quality=1.0,
        is_live_market=c_price is not None
    )
    assert domain.recommendation_decision == expected_rec
    assert domain.calculated_savings == expected_sav
    assert domain.is_valid is True


def test_canonical_forecast_publishes_null_confidence_when_unmeasured():
    """An unmeasured model produces a forecast with null confidence throughout.

    `model_accuracy` and `snapshot_quality` used to default to 95.0 and 1.0, so
    this call — which states that nothing was measured — previously published the
    highest confidence the pipeline can emit.
    """
    raw_forecast = [
        {"day": 0, "date": "2026-07-26", "price": 6487.0, "lower": 6200.0, "upper": 6700.0},
        {"day": 7, "date": "2026-08-02", "price": 6608.0, "lower": 6400.0, "upper": 6900.0}
    ]
    domain = canonical_forecast_service.build_canonical_forecast(
        formatted_forecast=raw_forecast,
        current_fare=6487.0,
        model_accuracy=None,
        snapshot_quality=None,
        is_live_market=False
    )
    assert domain.confidence_score is None
    assert domain.confidence_breakdown["model_validation_score"] is None
    assert domain.confidence_breakdown["prediction_reliability"] is None
    assert all(p.confidence_score is None for p in domain.timeline)

    dto = ForecastMapper.to_dto(domain)
    assert dto["confidence_score"] is None
    assert all(p["confidence_score"] is None for p in dto["timeline"])
