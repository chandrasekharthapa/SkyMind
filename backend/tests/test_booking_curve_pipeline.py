"""Tests for the refactored Booking Curve Training Pipeline & Grouping."""
import os
import json
import tempfile
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from backend.ml.training_config import TrainingConfig
from backend.services.training_dataset_builder import training_dataset_builder
from backend.ml.features.booking_curve import BookingCurveGenerator
from backend.ml.features.volatility import VolatilityGenerator
from backend.ml.features.trend import TrendGenerator
from backend.services.flight_search_service import flight_search_service
from backend.services.flight_data_service import STATUS_OK
from backend.ml.feature_context import FeatureContext
from backend.services.booking_curve_definition import BOOKING_CURVE_KEYS


def _make_dummy_curve(n_days=10, airline="6E", departure_time="06:10:00"):
    """A clean chronological daily history for one flight.

    `departure_time` is the per-flight component of `BOOKING_CURVE_KEYS` as of
    2026-09-03; it was `flight_number` before. Every row this helper produced carried
    a flight number and no departure time, so under the current key each one had an
    *incomplete* curve identity — the generators returned NaN for every windowed
    feature, `attach_future_target` refused the frame, and the validators reported on
    curves the frame does not describe. `flight_number` is still emitted: it is a real
    column of `price_history` and the mock provider payload below publishes one, but
    nothing keys on it.

    The value is a local departure instant with no offset, which is what migration 001
    declares the column to be (`TIMESTAMP WITHOUT TIME ZONE`) — 06:10 at the origin
    airport is 06:10 whatever UTC says. A bare `"06:10"` would serve as an opaque key,
    but `hour_of_day` and `is_peak_hour` are computed from this column and that is not
    the shape they read.
    """
    base_time = datetime(2026, 7, 1, 10, 0, 0, tzinfo=timezone.utc)
    dep_date = "2026-07-20"
    
    rows = []
    for i in range(n_days):
        recorded_at = base_time + timedelta(days=i)
        # Increasing price trend
        price = float(1000 + i * 100)
        rows.append({
            "origin_code": "DEL",
            "destination_code": "BOM",
            "airline_code": airline,
            "departure_time": f"{dep_date}T{departure_time}",
            "flight_number": f"{airline}100",
            "cabin_class": "ECONOMY",
            "price": price,
            "currency": "INR",
            "departure_date": dep_date,
            "recorded_at": recorded_at.isoformat(),
            # Both provenance columns, because `get_training_dataset` — which this
            # frame stands in for — selects on `is_synthetic IS FALSE AND is_live
            # IS TRUE` and so can only ever return rows that carry both. The
            # stub used to omit `is_synthetic`, and the eligibility filter the
            # builder applies used to ignore it being absent.
            "is_live": True,
            "is_synthetic": False,
            "seats_available": 30 - i,
            "training_weight": 2.0,
        })
    return pd.DataFrame(rows)


@pytest.mark.asyncio
async def test_ingestion_batch_timestamp_consistency():
    """Verify that all flights returned in the same search session receive the exact same recorded_at timestamp.

    Two things about this mock payload are load-bearing.

    `status` is present because `_guarded_transport` refuses a transport dict without
    one — `"transport returned dict without a status"` — and raises `_ProviderFailure`.
    Without it the search takes the DB-fallback branch, `insert_observations` is never
    reached, and `assert mock_insert.called` fails on a contract violation in the
    fixture rather than on anything about timestamps.

    `departure_time` is present because that is the per-flight component of
    `BOOKING_CURVE_KEYS` as of 2026-09-03, and `flight_number` no longer is. The
    provider publishes a departure instant on every card and no flight number on any
    of them, so a payload carrying only a flight number describes a response the
    scraper does not produce. The two are asserted on the stored rows below: if the
    column stops surviving `format_payload` → `get_db_payload`, every row ingested
    from then on has no curve identity, carries no label, and the failure is silent
    everywhere else.

    `currency` is present for a third reason of the same kind: since AUDIT-FIXES.md
    §48 the write path refuses a fare that does not say what it is denominated in,
    so a payload omitting it is screened out before the insert and this test would
    fail on an empty batch rather than on anything about timestamps.
    """
    # Mock GDS response
    mock_mcp_res = {
        "status": STATUS_OK,
        "data": [
            {"price": 5000.0, "currency": "INR", "primary_airline": "6E",
             "flight_number": "6E101", "departure_time": "2026-07-20T06:10:00"},
            {"price": 6000.0, "currency": "INR", "primary_airline": "AI",
             "flight_number": "AI202", "departure_time": "2026-07-20T19:45:00"},
        ]
    }

    with (
        patch("backend.services.flight_data_service.flight_data_service.search_flights",
              return_value=mock_mcp_res),
        patch("backend.services.historical_data_service.historical_data_service.insert_observations") as mock_insert
    ):
        # Trigger live search
        await flight_search_service.search("DEL", "BOM", "2026-07-20")

        # Verify inserted records
        assert mock_insert.called
        inserted_list = mock_insert.call_args[0][0]
        assert len(inserted_list) == 2

        # Check that both rows share the exact same timestamp string
        t1 = inserted_list[0]["recorded_at"]
        t2 = inserted_list[1]["recorded_at"]
        assert t1 == t2, f"Search batch timestamps diverged: {t1} vs {t2}"

        # And that the curve identity reached the row. Same route, same airline pair,
        # same departure date, same search: the departure time is the only thing left
        # that tells these two observations apart.
        departures = [row.get("departure_time") for row in inserted_list]
        assert all(departures), (
            f"departure_time did not survive ingest: {departures}; every row written "
            "this way has no booking-curve identity and can carry no label"
        )
        assert len(set(departures)) == 2, (
            f"both rows stored the same departure time ({departures}); the two flights "
            "would pool into one price history"
        )


def test_booking_curve_grouping_by_airline():
    """Verify that Trend/Volatility/BookingCurve generators group by airline, separating pricing structures."""
    df_6e = _make_dummy_curve(5, airline="6E")
    df_ai = _make_dummy_curve(5, airline="AI")
    # Change AI prices to be much higher
    df_ai["price"] = df_ai["price"] * 2.5
    
    df_combined = pd.concat([df_6e, df_ai], ignore_index=True)
    
    context = FeatureContext(
        historical_data=df_combined,
        market_snapshot=None,
        prediction_context={},
        route_statistics={},
        airline_statistics={},
        booking_statistics={},
        current_timestamp=datetime.now(timezone.utc)
    )
    
    # 1. Booking Curve
    bc_gen = BookingCurveGenerator()
    features = bc_gen.transform(context)
    
    # Verify price_change_1d matches within-airline sequence
    # For index 1 (second row of 6E): 1100 - 1000 = 100
    assert features["price_change_1d"].iloc[1] == 100.0
    # For index 6 (second row of AI): 2750 - 2500 = 250
    assert features["price_change_1d"].iloc[6] == 250.0
    
    # 2. Volatility
    vol_gen = VolatilityGenerator()
    vol_feats = vol_gen.transform(context)
    assert vol_feats["rolling_volatility"].iloc[4] > 0
    
    # 3. Trend
    trend_gen = TrendGenerator()
    trend_feats = trend_gen.transform(context)
    # Trend duration must be computed chronologically per airline
    assert trend_feats["trend_duration"].iloc[4] == 4.0


def test_training_inference_parity():
    """Verify that training (DataFrame transform) and inference (single-row context) yield identical features.

    The inference context has to name the flight. A booking curve is the five-part
    key whose per-flight component is `departure_time`, and a request that omits it is
    not asking about a curve: the component renders as the string `"NONE"`, nothing in
    the retrieved history matches it, and the whole block is then computed from the
    single fare being quoted. This test asserted two features and passed while the
    other twelve were that one-observation window's statistics — `observation_count`
    1.0, `days_since_first_observation` 0.0, `booking_curve_progress` 0.0 and each
    `rolling_*` equal to the quoted fare. Named, all fourteen agree exactly, so all
    fourteen are compared.

    The component was `flight_number` until 2026-09-03. Note what keeps this test
    honest across that change: the fourteen-feature loop alone would not have caught
    it, because a frame with no `departure_time` yields NaN on *both* paths and
    `pd.isna(expected) → assert pd.isna(actual)` is then satisfied by two vectors of
    nulls agreeing with each other. The two assertions at the end are the ones that
    fail, which is why they are there.
    """
    df = _make_dummy_curve(5)

    # DataFrame transform (Training)
    context_train = FeatureContext(
        historical_data=df,
        market_snapshot=None,
        prediction_context={},
        route_statistics={},
        airline_statistics={},
        booking_statistics={},
        current_timestamp=datetime.now(timezone.utc)
    )

    bc_gen = BookingCurveGenerator()
    train_feats = bc_gen.transform(context_train)

    # Single-row transform (Inference)
    # The last row represents the query today. Historical data contains first 4 rows.
    history_rows = df.iloc[:4].to_dict(orient="records")
    query_row = df.iloc[-1]

    context_inf = FeatureContext(
        historical_data=history_rows,
        market_snapshot=None,
        prediction_context={
            "origin": query_row["origin_code"],
            "destination": query_row["destination_code"],
            "airline": query_row["airline_code"],
            "departure_time": query_row["departure_time"],
            "departure_date": query_row["departure_date"],
            "current_price": query_row["price"],
            "seats_available": query_row["seats_available"],
        },
        route_statistics={},
        airline_statistics={},
        booking_statistics={},
        current_timestamp=datetime.fromisoformat(query_row["recorded_at"])
    )

    inf_feats = bc_gen.transform(context_inf)

    for name in bc_gen.feature_names:
        expected = train_feats[name].iloc[-1]
        actual = inf_feats[name]
        if pd.isna(expected):
            assert pd.isna(actual), f"{name}: inference {actual!r}, training NaN"
        else:
            assert actual == pytest.approx(float(expected)), \
                f"{name}: inference {actual!r} != training {expected!r}"

    # Not a vector of nulls agreeing with itself: the curve is five observations
    # long on both paths and the day-based change is the real one.
    assert inf_feats["observation_count"] == 5.0
    assert inf_feats["price_change_1d"] == 100.0


def test_a_query_that_names_no_flight_gets_no_curve_features():
    """The same history and the same quote, with the departure time left off.

    This is the shape the serving path used to send. Every curve feature is
    unknown, rather than the statistics of a window one observation long.

    The omitted key is `departure_time`, the per-flight component since 2026-09-03.
    On `flight_number` this test now asserts nothing it means to: the identity is
    incomplete either way, so it would still see NaN everywhere while the request it
    calls complete is one the generator can no longer resolve.
    """
    df = _make_dummy_curve(5)
    query_row = df.iloc[-1]

    bc_gen = BookingCurveGenerator()
    feats = bc_gen.transform(FeatureContext(
        historical_data=df.iloc[:4].to_dict(orient="records"),
        market_snapshot=None,
        prediction_context={
            "origin": query_row["origin_code"],
            "destination": query_row["destination_code"],
            "airline": query_row["airline_code"],
            "departure_date": query_row["departure_date"],
            "current_price": query_row["price"],
            "seats_available": query_row["seats_available"],
        },
        route_statistics={},
        airline_statistics={},
        booking_statistics={},
        current_timestamp=datetime.fromisoformat(query_row["recorded_at"])
    ))

    for name in bc_gen.feature_names:
        if name == "seats_available":
            continue
        assert np.isnan(feats[name]), f"{name} was answered for an unnamed flight"
    # Read from the request, not from a curve, so it survives.
    assert feats["seats_available"] == 26.0


def test_flights_with_no_departure_time_are_not_pooled_into_one_curve():
    """Two different departures with no departure time are not one price history.

    Training groups with `dropna=False`, so a null key formed a group of its own
    and `price_at_lag` crossed between the flights inside it — the four-key defect
    returning through the key's null handling. Rows like these reach the feature
    stage rather than being repaired at ingest: nothing substitutes a departure time
    when the provider's segment cannot be parsed, and every row written before
    migration 001 has the column NULL. They have no curve, and take no curve
    features.

    The null component was `flight_number` until 2026-09-03, and the two curves were
    separated by assigning `6E100` and `6E200`. Neither half of that still works: the
    six rows would be identity-incomplete before *and* after the assignment, so the
    second block would assert `[1, 2, 3, 1, 2, 3]` against six NaNs and fail — while
    the first block passed for the wrong reason, reporting NaN because the departure
    time was missing rather than because the flight was unidentified.
    """
    a = _make_dummy_curve(3, airline="6E", departure_time="06:10:00")
    b = _make_dummy_curve(3, airline="6E", departure_time="19:45:00")
    b["price"] = [9000.0, 9100.0, 9200.0]
    df = pd.concat([a, b], ignore_index=True)
    departures = df["departure_time"].tolist()
    df["departure_time"] = None

    feats = BookingCurveGenerator().transform(FeatureContext(
        historical_data=df,
        market_snapshot=None,
        prediction_context={},
        route_statistics={},
        airline_statistics={},
        booking_statistics={},
        current_timestamp=datetime.now(timezone.utc)
    ))

    assert feats["observation_count"].isna().all()
    assert feats["price_change_1d"].isna().all()
    assert feats["rolling_mean_price"].isna().all()
    # `seats_available` is a column of the frame, not a window over it.
    assert feats["seats_available"].notna().all()

    # With the departures named — the same values the helper produced, restored, not
    # invented — the same six rows are two curves of three, and neither one's lag
    # reaches into the other.
    df["departure_time"] = departures
    named = BookingCurveGenerator().transform(FeatureContext(
        historical_data=df,
        market_snapshot=None,
        prediction_context={},
        route_statistics={},
        airline_statistics={},
        booking_statistics={},
        current_timestamp=datetime.now(timezone.utc)
    ))
    assert list(named["observation_count"]) == [1.0, 2.0, 3.0, 1.0, 2.0, 3.0]
    # The first observation of each curve has nothing to change against; the 9000
    # curve's first row does not report 9000 - 1200.
    assert np.isnan(named["price_change_1d"].iloc[0])
    assert np.isnan(named["price_change_1d"].iloc[3])
    assert list(named["price_change_1d"].iloc[[1, 2, 4, 5]]) == [100.0, 100.0, 100.0, 100.0]



def test_target_leakage_protection_and_flow():
    """Verify that features are engineered before the target price join, avoiding future data visibility."""
    df = _make_dummy_curve(10)
    
    with patch("backend.database.database.database.get_training_dataset", return_value=df):
        df_raw, df_features = training_dataset_builder.build(horizon=3)
        
        # Verify that for horizon=3, df_features has matched target_price
        # An observation recorded on July 1 (index 0) matches future price on July 4 (index 3, price=1300)
        assert len(df_features) > 0
        first_row = df_features.iloc[0]
        assert first_row["target_price"] == 1300.0
        assert np.isnan(first_row["price_change_1d"])  # July 1 is first day of curve, hence NaN
        
        # Verify that for second row (July 2), price_change_1d is populated (100.0)
        second_row = df_features.iloc[1]
        assert second_row["target_price"] == 1400.0
        assert second_row["price_change_1d"] == 100.0  # 1100 - 1000
        
        # Target leakage validation: Verify that no "_future" suffix columns are leaked into feature list
        for col in df_features.columns:
            assert not col.endswith("_future")


def test_validator_chronology():
    """Verify that chronology validation correctly detects out-of-order timestamps."""
    from backend.ml.booking_curve_validator import validate_chronology
    
    df_ok = _make_dummy_curve(5)
    res_ok = validate_chronology(df_ok)
    assert res_ok.status == "PASS"
    
    # Intentionally corrupt chronology
    df_corrupt = df_ok.copy()
    # Swap timestamps of row 1 and row 2
    t1, t2 = df_corrupt.loc[1, "recorded_at"], df_corrupt.loc[2, "recorded_at"]
    df_corrupt.loc[1, "recorded_at"] = t2
    df_corrupt.loc[2, "recorded_at"] = t1
    
    res_corrupt = validate_chronology(df_corrupt)
    assert res_corrupt.status == "FAIL"
    assert len(res_corrupt.errors) > 0


def test_validator_duplicates():
    """Verify that duplicates validation reports correct metrics.

    The dedupe key is `BOOKING_CURVE_KEYS` plus the observation timestamp, taken from
    the shared tuple rather than typed out. Typed out, this line read
    `[..., "flight_number", ...]` and had to be found and changed by hand when the key
    moved on 2026-09-03 — and if it had been missed, it would have gone on removing
    rows the validator it is checking does not consider duplicates.
    """
    from backend.ml.booking_curve_validator import validate_duplicates

    df_raw = _make_dummy_curve(5)
    # Duplicate index 1
    df_raw = pd.concat([df_raw, df_raw.iloc[[1]]], ignore_index=True)

    df_cleaned = df_raw.drop_duplicates(subset=list(BOOKING_CURVE_KEYS) + ["recorded_at"])
    
    res = validate_duplicates(df_raw, df_cleaned)
    assert res.status == "PASS"
    assert res.metrics["duplicates_removed"] == 1
    assert res.metrics["retained_rows"] == 5


def test_validator_health_metrics():
    """Verify that health metrics computed on synthetic curves match expectation."""
    from backend.ml.booking_curve_validator import compute_health_metrics
    
    # 1 curve of size 5
    df = _make_dummy_curve(5)
    res = compute_health_metrics(df)
    assert res.status == "PASS"
    assert res.metrics["total_curves"] == 1
    assert res.metrics["singleton_curves_pct"] == 0.0
    assert res.metrics["pct_ge_2"] == 100.0
    
    # Singleton curve check
    df_single = _make_dummy_curve(1)
    res_single = compute_health_metrics(df_single)
    assert res_single.metrics["singleton_curves_pct"] == 100.0


def test_validator_feature_coverage():
    """Verify that feature coverage flags zero variance/constant features."""
    from backend.ml.booking_curve_validator import compute_feature_coverage
    
    df_feats = _make_dummy_curve(5)
    # Add engineered features
    df_feats["price_change_1d"] = [np.nan, 100.0, 100.0, 100.0, 100.0]
    df_feats["rolling_mean_price"] = [1000.0, 1050.0, 1100.0, 1150.0, 1200.0]
    df_feats["constant_feat"] = [5.0, 5.0, 5.0, 5.0, 5.0]  # Constant feature
    
    res = compute_feature_coverage(df_feats)
    assert res.status == "FAIL"  # Should fail due to zero variance on constant_feat
    assert any("constant_feat" in err for err in res.errors)


def test_validator_target_quality():
    """Verify target validation checks negatives, coverage, and duplicates."""
    from backend.ml.booking_curve_validator import compute_target_quality
    
    df_feats = _make_dummy_curve(5)
    df_feats["target_price"] = [1300.0, 1400.0, 1500.0, np.nan, np.nan]
    
    res = compute_target_quality(df_feats)
    # Coverage is 3/5 = 60%, warning threshold is 80%, so WARNING status
    assert res.status == "WARNING"
    assert res.metrics["populated_targets"] == 3
    
    # Corrupt with negative target
    df_corrupt = df_feats.copy()
    df_corrupt["target_price"] = [1300.0, 1400.0, -100.0, np.nan, np.nan]
    res_corrupt = compute_target_quality(df_corrupt)
    assert res_corrupt.status == "FAIL"


def test_validator_feature_drift():
    """Verify feature drift validation checks standard deviations and means."""
    from backend.ml.booking_curve_validator import detect_feature_drift
    
    new_report = {
        "coverage": {
            "metrics": {
                "features": {
                    "price_change_1d": {"mean": 1000.0, "variance": 100.0}
                }
            }
        }
    }
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # No files in tmpdir -> PASS
        res_empty = detect_feature_drift(new_report, tmpdir)
        assert res_empty.status == "PASS"
        
        # Write historical JSON report
        hist_report = {
            "coverage": {
                "metrics": {
                    "features": {
                        "price_change_1d": {"mean": 100.0, "variance": 100.0}
                    }
                }
            }
        }
        with open(os.path.join(tmpdir, "validation_2026-07-20.json"), "w") as f:
            json.dump(hist_report, f)
            
        # Compare -> WARNING due to mean drift from 100.0 to 1000.0
        res_drift = detect_feature_drift(new_report, tmpdir)
        assert res_drift.status == "WARNING"
        assert len(res_drift.warnings) > 0


def test_validator_report_generation():
    """Verify generate_validation_report compiles and persists JSON correctly."""
    from backend.ml.booking_curve_validator import generate_validation_report
    
    df_raw = _make_dummy_curve(5)
    df_feats = df_raw.copy()
    df_feats["price_change_1d"] = [np.nan, 100.0, 100.0, 100.0, 100.0]
    df_feats["target_price"] = [1300.0, 1400.0, 1500.0, 1600.0, 1700.0]
    
    with tempfile.TemporaryDirectory() as tmpdir:
        report = generate_validation_report(df_raw, df_raw, df_feats, "feature_set_v1", history_dir=tmpdir)
        assert report.overall_status in ["PASS", "WARNING", "FAIL"]
        assert report.readiness_score >= 0
        
        # Verify JSON file is persisted in directory
        files = os.listdir(tmpdir)
        assert len(files) == 1
        assert files[0].endswith(".json")


def test_dashboard_rendering():
    """Verify that run_validation_dashboard imports and executes cleanly (dry run check)."""
    from backend.tools.run_validation_dashboard import get_status_str
    
    # Verify status highlights
    assert "PASS" in get_status_str("PASS")
    assert "FAIL" in get_status_str("FAIL")
