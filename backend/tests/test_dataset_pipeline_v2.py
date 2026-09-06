"""Unit & Integration Tests for Flight Price Dataset Pipeline v2.0."""

import pytest
import os
import json
import pandas as pd
from datetime import datetime, date, timedelta, timezone

from backend.dataset.config import default_dataset_config
from backend.dataset.dates import compute_calendar_days_until_dep, validate_days_until_dep_row
from backend.dataset.itinerary import generate_itinerary_id, attach_itinerary_id_to_row
from backend.dataset.snapshot import attach_snapshot_metadata, compute_snapshot_sequences
from backend.dataset.collection_strategy import collection_strategy
from backend.dataset.features import engineer_dataset_features
from backend.dataset.validation_pipeline import validation_pipeline
from backend.dataset.exporter import dataset_exporter
from backend.dataset.doctor import (
    EXIT_FAIL,
    EXIT_PASS,
    EXIT_WARN,
    booking_curve_shape,
    run_dataset_doctor,
)


def test_calendar_date_subtraction():
    """Verify exact calendar date subtraction with zero off-by-one errors."""
    dep = "2026-08-15"
    rec = "2026-07-16T12:00:00Z"
    days = compute_calendar_days_until_dep(dep, rec)
    assert days == 30, f"Expected 30 days, got {days}"

    row_valid = {"departure_date": dep, "recorded_at": rec, "days_until_dep": 30}
    row_invalid = {"departure_date": dep, "recorded_at": rec, "days_until_dep": 29}
    assert validate_days_until_dep_row(row_valid) is True
    assert validate_days_until_dep_row(row_invalid) is False


def test_stable_itinerary_id():
    """Deterministic 16-character hash over the curve identity plus cabin.

    `generate_itinerary_id` used to take six positional strings with the per-flight
    component in the fifth slot, and this test passed `"6E101"` into it. The provider
    publishes no flight number, so in production that slot was the literal `"NONE"`
    on every row and all of a carrier's departures on a route, date and cabin shared
    one id — which `time_series_plugin` then deletes wholesale when the pooled
    timestamps do not ascend. The id is built from `BOOKING_CURVE_KEYS` now, so the
    fixtures carry `departure_time`.
    """
    record = {"origin_code": "DEL", "destination_code": "BOM",
              "departure_date": "2026-08-15", "departure_time": "06:10",
              "airline_code": "6E", "cabin_class": "ECONOMY"}
    messy = {"origin_code": "del ", "destination_code": "bom ",
             "departure_date": "2026-08-15", "departure_time": "06:10",
             "airline_code": "6e", "cabin_class": "economy"}
    id1 = generate_itinerary_id(record)
    id2 = generate_itinerary_id(messy)
    assert id1 == id2
    assert len(id1) == 16

    # Two departures of one carrier on one route and date are two itineraries. This
    # is the assertion the old signature could not make: with the per-flight
    # component absent both rows hashed the same string.
    sibling = {**record, "departure_time": "19:45"}
    assert generate_itinerary_id(sibling) != id1

    # An incomplete identity is refused rather than hashed with a placeholder.
    with pytest.raises(ValueError):
        generate_itinerary_id({k: v for k, v in record.items()
                               if k != "departure_time"})

    # `attach_itinerary_id_to_row` leaves the key absent instead of raising, so one
    # unidentified observation does not abandon the rest of an export.
    unidentified = attach_itinerary_id_to_row(
        {k: v for k, v in record.items() if k != "departure_time"})
    assert "itinerary_id" not in unidentified
    assert attach_itinerary_id_to_row(dict(record))["itinerary_id"] == id1


def test_snapshot_sequence_numbering():
    """Verify 1-indexed snapshot sequence tracking per itinerary_id."""
    df = pd.DataFrame([
        {"itinerary_id": "itin_1", "snapshot_time": "2026-07-01T10:00:00Z"},
        {"itinerary_id": "itin_1", "snapshot_time": "2026-07-05T10:00:00Z"},
        {"itinerary_id": "itin_2", "snapshot_time": "2026-07-02T10:00:00Z"}
    ])
    df_seq = compute_snapshot_sequences(df)
    seqs = df_seq["snapshot_sequence"].tolist()
    assert seqs == [1, 2, 1]


def test_collection_strategy_horizons():
    """Verify multi-horizon revisit target generation."""
    targets = collection_strategy.get_target_departure_dates(base_date=date(2026, 7, 26))
    assert len(targets) == 14
    assert collection_strategy.is_target_horizon(30) is True


def test_feature_engineering_pipeline():
    """Verify feature engineering without data leakage."""
    df = pd.DataFrame([
        {"origin_code": "DEL", "destination_code": "BOM", "departure_date": "2026-08-15", "recorded_at": "2026-07-16T12:00:00Z", "price": 4500.0, "airline_code": "6E"},
        {"origin_code": "DEL", "destination_code": "BOM", "departure_date": "2026-08-15", "recorded_at": "2026-07-20T12:00:00Z", "price": 4800.0, "airline_code": "6E"}
    ])
    df_feat = engineer_dataset_features(df)
    assert "route_distance_km" in df_feat.columns
    assert "domestic_vs_international" in df_feat.columns
    assert "hub_route" in df_feat.columns
    assert "airline_type" in df_feat.columns
    assert "historical_route_average" in df_feat.columns


def test_validation_pipeline_plugin_chain():
    """A duplicate observation is filtered; the fixture carries a curve identity.

    `departure_time` is here because `DuplicateValidationPlugin` refuses to
    de-duplicate a frame with no curve identity and passes it through untouched —
    de-duplicating on `(recorded_at, price)` alone would collapse unrelated
    departures that happen to share a fare. Without the column this test asserted a
    filter that no longer runs.
    """
    row = {"origin_code": "DEL", "destination_code": "BOM",
           "departure_date": "2026-08-15", "departure_time": "06:10",
           "recorded_at": "2026-07-16T12:00:00Z", "price": 4500.0,
           "airline_code": "6E", "days_until_dep": 30}
    df = pd.DataFrame([row, dict(row)])  # the second is the duplicate
    cleaned_df, results = validation_pipeline.process(df)
    assert len(cleaned_df) == 1, "Duplicate row should be filtered out"

    # A sibling departure priced the same is not a duplicate.
    sibling = pd.DataFrame([row, {**row, "departure_time": "19:45"}])
    cleaned_sibling, _ = validation_pipeline.process(sibling)
    assert len(cleaned_sibling) == 2, \
        "two departures of one carrier sharing a fare are distinct observations"


def test_dataset_exporter_and_quality_report(tmp_path):
    """Verify DatasetExporter generates CSV, manifest, and quality_report.json.

    `output_dir` was `"backend/dataset/exports"` — the real export directory, the
    one `doctor.py` reads by default. So running the suite left a 707-byte
    `flight_price_dataset_v2.0.csv` holding this fixture's single row in the
    repository, beside a manifest recording `total_rows: 1` and a quality report
    saying `validation_status: PASS`, and all three were staged for commit. Any
    reader — including the doctor, including a future me — would take that for the
    dataset. It writes to `tmp_path` now.
    """
    df = pd.DataFrame([
        {"origin_code": "DEL", "destination_code": "BOM", "departure_date": "2026-08-15", "departure_time": "06:10", "recorded_at": "2026-07-16T12:00:00Z", "price": 4500.0, "airline_code": "6E"}
    ])
    out_dir = str(tmp_path)
    csv_path, report = dataset_exporter.export(df, output_dir=out_dir)
    assert os.path.exists(csv_path)
    assert csv_path.startswith(out_dir), "the export must not escape tmp_path"
    assert report["summary"]["validation_status"] == "PASS"

    assert os.path.exists(os.path.join(out_dir, "quality_report.json"))


def _write_csv(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)
    return str(path)


def _curve_rows():
    """One booking curve, observed twice — the shape a labelled row needs.

    `departure_time` is the per-flight component of `BOOKING_CURVE_KEYS`; both rows
    carry the same one, which is what makes them two observations of one curve rather
    than two flights.

    `is_live`/`is_synthetic` are here because `filter_training_eligible_dataframe`
    requires both columns and treats their absence as "cannot be shown to be observed
    data". Without them the doctor's per-horizon count is zero for every horizon and
    it reports FAIL — a true statement about this fixture, but not the one the tests
    below mean to make, which is about a corpus that is clean and merely too small.
    """
    return [
        {"origin_code": "DEL", "destination_code": "BOM", "departure_date": "2026-08-15",
         "departure_time": "06:10",
         "recorded_at": "2026-07-16T12:00:00Z", "days_until_dep": 30, "price": 4500.0,
         "airline_code": "6E", "is_live": True, "is_synthetic": False},
        {"origin_code": "DEL", "destination_code": "BOM", "departure_date": "2026-08-15",
         "departure_time": "06:10",
         "recorded_at": "2026-07-20T12:00:00Z", "days_until_dep": 26, "price": 4700.0,
         "airline_code": "6E", "is_live": True, "is_synthetic": False},
    ]


def test_dataset_doctor_refuses_a_corpus_it_cannot_read(tmp_path):
    """A named file that does not exist is a FAIL, not a fabricated sample.

    `run_dataset_doctor()` used to build a one-row frame from literals in
    `doctor.py` when it could not read a corpus, and then graded that. The
    replaced assertion was `assert code in (0, 1, 2)` — every value the function
    can return, so it held whatever the tool decided, including a verdict about a
    row the tool had invented.
    """
    assert run_dataset_doctor(filepath=str(tmp_path / "absent.csv")) == EXIT_FAIL


def test_dataset_doctor_fails_a_corpus_with_bad_fares(tmp_path):
    rows = _curve_rows()
    rows[1]["price"] = -1.0
    assert run_dataset_doctor(filepath=_write_csv(tmp_path / "bad.csv", rows)) == EXIT_FAIL


def test_dataset_doctor_fails_an_empty_corpus(tmp_path):
    """Zero rows satisfies every integrity check vacuously, so it must not pass."""
    empty = pd.DataFrame(columns=list(_curve_rows()[0].keys()))
    empty.to_csv(tmp_path / "empty.csv", index=False)
    assert run_dataset_doctor(filepath=str(tmp_path / "empty.csv")) == EXIT_FAIL


def test_dataset_doctor_warns_when_there_are_too_few_labellable_rows(tmp_path):
    """A clean but tiny corpus is PARTIAL, never PASS.

    Two observations of one curve pass every schema and integrity check. They are
    two rows against a floor of 100, so training would be refused for every
    horizon, and the verdict has to say so rather than reading as a green light.
    """
    code = run_dataset_doctor(filepath=_write_csv(tmp_path / "tiny.csv", _curve_rows()))
    assert code == EXIT_WARN


def test_booking_curve_shape_counts_labellable_rows_not_all_rows():
    """The number that decides trainability, asserted directly.

    Rows on single-observation curves can never carry a label: the target is a
    later fare on the same curve, and there is no later fare. A corpus can hold any
    number of them and still produce nothing to fit.

    The five singles differ in `departure_time` — five departures of one carrier on
    one route and date. They used to differ in `flight_number`, which is no longer a
    curve component, so on the current key they would have been one curve of five and
    this test would have asserted the pooling it exists to catch.
    """
    singles = pd.DataFrame([
        {**_curve_rows()[0], "departure_time": f"0{i}:10"} for i in range(5)
    ])
    shape = booking_curve_shape(singles)
    assert shape["rows"] == 5
    assert shape["curves"] == 5
    assert shape["single_observation_curves"] == 5
    assert shape["rows_on_multi_observation_curves"] == 0
    assert shape["curve_keys_missing"] == [], \
        "the fixture must carry the whole key, or the bound is inflated"

    shape = booking_curve_shape(pd.DataFrame(_curve_rows()))
    assert shape["curves"] == 1
    assert shape["longest_curve"] == 2
    assert shape["rows_on_multi_observation_curves"] == 2

