import uuid
from datetime import datetime, timezone, timedelta
import pytest
import pandas as pd
import numpy as np

from backend.services.ingestion_controller import MarketDataController
from backend.services.booking_curve_definition import (
    BOOKING_CURVE_KEYS,
    get_booking_curve_group_key,
    sort_booking_curves_chronologically,
    deduplicate_session_aware
)
from backend.services.training_dataset_builder import TrainingDatasetBuilder
from backend.ml.feature_engineering_pipeline import FEATURE_PIPELINE_VERSION, feature_engineering_pipeline
from backend.services.dataset_quality_validator import dataset_quality_validator


def test_search_session_generation():
    """Verify unique search session ID and search timestamp creation."""
    session_id_1 = str(uuid.uuid4())
    session_id_2 = str(uuid.uuid4())
    assert session_id_1 != session_id_2
    
    ts = datetime.now(timezone.utc).isoformat()
    assert "T" in ts and ("+00:00" in ts or "Z" in ts)


def test_metadata_propagation_and_separation():
    """Verify search_session_id and search_timestamp propagation and timestamp separation."""
    session_id = str(uuid.uuid4())
    query_ts = "2026-07-22T10:00:00.000000+00:00"
    db_ingest_ts = "2026-07-22T10:00:05.123456+00:00"

    payload = MarketDataController.format_payload(
        origin_code="DEL",
        destination_code="BOM",
        airline_code="6E",
        price=5500.0,
        departure_date="2026-08-01",
        days_until_dep=10,
        flight_number="6E2012",
        recorded_at=db_ingest_ts,
        search_session_id=session_id,
        search_timestamp=query_ts
    )

    assert payload["search_session_id"] == session_id
    assert payload["search_timestamp"] == query_ts
    assert payload["recorded_at"] == db_ingest_ts
    assert payload["search_timestamp"] != payload["recorded_at"] or payload["search_timestamp"] == query_ts

    db_payload = MarketDataController.get_db_payload(payload)
    assert "search_session_id" in db_payload
    assert "search_timestamp" in db_payload
    assert "recorded_at" in db_payload


def test_centralized_booking_curve_definition():
    """Verify centralized booking curve grouping keys."""
    assert "origin_code" in BOOKING_CURVE_KEYS
    assert "destination_code" in BOOKING_CURVE_KEYS
    assert "airline_code" in BOOKING_CURVE_KEYS
    assert "departure_time" in BOOKING_CURVE_KEYS
    assert "departure_date" in BOOKING_CURVE_KEYS

    # The per-flight component must not go back to `flight_number`. No wired
    # provider publishes one — a live 65-flight DEL-BOM fetch on 2026-09-03
    # contained zero carrier-coded numbers — so it is NULL on every row, and
    # `curve_identity_is_complete` requires all five components. Restoring it
    # makes the entire corpus unlabellable at every horizon, silently: nothing
    # raises, the training frame simply comes back empty.
    assert "flight_number" not in BOOKING_CURVE_KEYS

    rec = {
        "origin_code": "del ",
        "destination_code": " bom",
        "airline_code": "6e ",
        "departure_time": " 2026-08-15T06:15:00 ",
        "departure_date": "2026-08-15"
    }
    key = get_booking_curve_group_key(rec)
    assert key == ("DEL", "BOM", "6E", "2026-08-15T06:15:00", "2026-08-15")

    # Two departures of the same carrier on the same route and date are two
    # curves, which is the whole point of the fifth component. Under the old key
    # they were one, because both carried a NULL flight number.
    sibling = dict(rec, departure_time="2026-08-15T21:40:00")
    assert get_booking_curve_group_key(sibling) != key


def test_session_aware_duplicate_detection():
    """Verify deduplication preserves multi-session longitudinal records."""
    session_1 = "sess-001"
    session_2 = "sess-002"

    rows = [
        # Session 1: flight 6E2012 twice (duplicate inside session)
        {"origin_code": "DEL", "destination_code": "BOM", "airline_code": "6E", "flight_number": "6E2012", "departure_date": "2026-08-01", "price": 5000.0, "search_session_id": session_1, "search_timestamp": "2026-07-20T10:00:00+00:00"},
        {"origin_code": "DEL", "destination_code": "BOM", "airline_code": "6E", "flight_number": "6E2012", "departure_date": "2026-08-01", "price": 5000.0, "search_session_id": session_1, "search_timestamp": "2026-07-20T10:00:00+00:00"},
        # Session 2: flight 6E2012 next day (valid longitudinal observation)
        {"origin_code": "DEL", "destination_code": "BOM", "airline_code": "6E", "flight_number": "6E2012", "departure_date": "2026-08-01", "price": 5500.0, "search_session_id": session_2, "search_timestamp": "2026-07-21T10:00:00+00:00"}
    ]
    df = pd.DataFrame(rows)
    df_dedup = deduplicate_session_aware(df)
    assert len(df_dedup) == 2


def test_chronological_booking_curve_construction():
    """Verify booking curves are sorted chronologically by search_timestamp."""
    rows = [
        {"origin_code": "DEL", "destination_code": "BOM", "airline_code": "6E", "flight_number": "6E2012", "departure_date": "2026-08-01", "price": 6000.0, "search_timestamp": "2026-07-22T10:00:00+00:00"},
        {"origin_code": "DEL", "destination_code": "BOM", "airline_code": "6E", "flight_number": "6E2012", "departure_date": "2026-08-01", "price": 5000.0, "search_timestamp": "2026-07-20T10:00:00+00:00"},
        {"origin_code": "DEL", "destination_code": "BOM", "airline_code": "6E", "flight_number": "6E2012", "departure_date": "2026-08-01", "price": 5500.0, "search_timestamp": "2026-07-21T10:00:00+00:00"}
    ]
    df = pd.DataFrame(rows)
    df_sorted = sort_booking_curves_chronologically(df)
    
    assert list(df_sorted["price"]) == [5000.0, 5500.0, 6000.0]


def test_feature_pipeline_versioning_and_parity():
    """Verify FEATURE_PIPELINE_VERSION constant and build_training_dataset output."""
    assert FEATURE_PIPELINE_VERSION == "2.0.0"
    
    df_sample = pd.DataFrame([{
        "origin_code": "DEL", "destination_code": "BOM", "airline_code": "6E",
        "flight_number": "6E2012", "departure_date": "2026-08-01", "price": 5000.0,
        "recorded_at": "2026-07-20T10:00:00+00:00", "days_until_dep": 12,
        "day_of_week": 0, "month": 8, "week_of_year": 31, "is_holiday": False,
        "is_weekend": False, "seats_available": 10, "is_synthetic": False
    }])
    df_features = feature_engineering_pipeline.build_training_dataset(df_sample, "legacy")
    assert not df_features.empty


def test_dataset_readiness_evaluation():
    """Verify dataset quality validator multi-horizon evaluation."""
    df_sample = pd.DataFrame([{
        "origin_code": "DEL", "destination_code": "BOM", "airline_code": "6E",
        "flight_number": "6E2012", "departure_date": "2026-08-01", "price": 5000.0,
        "recorded_at": "2026-07-20T10:00:00+00:00", "is_synthetic": False
    }])
    readiness = dataset_quality_validator.evaluate_horizon_readiness(df_sample)
    assert "0d" in readiness
    assert "1d" in readiness
    assert "3d" in readiness
    assert "7d" in readiness
    assert "14d" in readiness
    assert "30d" in readiness
    assert readiness["0d"].grade in ["A", "B", "C", "D", "F"]
