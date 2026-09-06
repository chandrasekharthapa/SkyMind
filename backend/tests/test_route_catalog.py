import pytest
import pandas as pd
from backend.route_catalog import RouteCatalogConfig, route_catalog_config
from backend.services.ingestion_controller import MarketDataController
from backend.services.training_eligibility import is_training_eligible, filter_training_eligible_dataframe
from backend.services.dataset_quality_validator import dataset_quality_validator


def test_route_catalog_loading():
    """Verify route catalog loads active routes and collector configuration."""
    routes = route_catalog_config.get_active_routes()
    assert len(routes) >= 50, f"Expected 50+ active routes, found {len(routes)}"
    
    buckets = route_catalog_config.get_departure_buckets()
    assert 1 in buckets and 90 in buckets
    assert len(buckets) >= 10

    assert route_catalog_config.get_batch_size() > 0
    assert route_catalog_config.get_worker_count() > 0


def test_deterministic_batch_generation():
    """Verify route batching is deterministic and chunks into configured sizes."""
    config = RouteCatalogConfig()
    batches_8 = config.create_route_batches(batch_size=8)
    batches_8_again = config.create_route_batches(batch_size=8)
    
    assert batches_8 == batches_8_again, "Batching must be strictly deterministic"
    assert len(batches_8[0]) == 8
    
    # Priority sorting check (DEL-BOM priority 100 should be in first batch)
    first_batch_routes = batches_8[0]
    assert ("DEL", "BOM") in first_batch_routes or ("BOM", "DEL") in first_batch_routes


def test_provenance_defaults():
    """A payload built with no stated provider must not name one.

    This previously asserted `data_source == "GOOGLE_FLIGHTS"` for a call that
    passes no provider at all — codifying the defect that `data_source` and
    `provider` disagreed about the same fact on every stored row, and that an
    observation of unknown origin was certified as a Google Flights reading.
    The contract now is: unknown origin reads back "UNKNOWN".
    """
    payload = MarketDataController.format_payload(
        origin_code="DEL",
        destination_code="BOM",
        airline_code="6E",
        price=5500.0,
        departure_date="2026-08-01",
        days_until_dep=10
    )

    assert payload["data_source"] == "UNKNOWN"
    assert payload["provider"] is None
    assert payload["is_synthetic"] is False

    db_payload = MarketDataController.get_db_payload(payload)
    assert "data_source" in db_payload
    assert "is_synthetic" in db_payload
    # `provider` is None here, and get_db_payload drops None so the column stays
    # NULL rather than being written as the string "None".
    assert "provider" not in db_payload


def test_data_source_follows_provider():
    """`data_source` must agree with the provider actually used, not a literal."""
    payload = MarketDataController.format_payload(
        origin_code="DEL",
        destination_code="BOM",
        airline_code="6E",
        price=5500.0,
        departure_date="2026-08-01",
        days_until_dep=10,
        provider="LIVE_GOOGLE_FLIGHTS_MCP"
    )

    assert payload["provider"] == "LIVE_GOOGLE_FLIGHTS_MCP"
    assert payload["data_source"] == "LIVE_GOOGLE_FLIGHTS_MCP"

    # An explicit data_source still wins, for callers that distinguish the two.
    explicit = MarketDataController.format_payload(
        origin_code="DEL",
        destination_code="BOM",
        airline_code="6E",
        price=5500.0,
        departure_date="2026-08-01",
        days_until_dep=10,
        provider="LIVE_GOOGLE_FLIGHTS_MCP",
        data_source="DB_FALLBACK"
    )
    assert explicit["data_source"] == "DB_FALLBACK"
    assert explicit["provider"] == "LIVE_GOOGLE_FLIGHTS_MCP"


def test_missing_flight_number_stays_null():
    """A flight with no identifier must not be given a fabricated one.

    `format_payload` used to fall back to f"{airline_code}1000", which gave every
    unidentified flight on a carrier the same number — the reason the stored
    corpus has a single distinct flight_number across thousands of rows.
    """
    payload = MarketDataController.format_payload(
        origin_code="DEL",
        destination_code="BOM",
        airline_code="6E",
        price=5500.0,
        departure_date="2026-08-01",
        days_until_dep=10
    )

    assert payload["flight_number"] is None
    assert "flight_number" not in MarketDataController.get_db_payload(payload)

    identified = MarketDataController.format_payload(
        origin_code="DEL",
        destination_code="BOM",
        airline_code="6E",
        price=5500.0,
        departure_date="2026-08-01",
        days_until_dep=10,
        flight_number=" 6e2012 "
    )
    assert identified["flight_number"] == "6E2012"
    assert MarketDataController.get_db_payload(identified)["flight_number"] == "6E2012"


def test_negative_horizon_is_rejected_not_clipped():
    """A departure already in the past is a provenance defect, not a same-day fare.

    Clipping the horizon to 0 relabels the row as "departing today" and makes
    `urgency` the constant 1.0, which is how a broken row became a
    plausible-looking training feature.
    """
    with pytest.raises(ValueError, match="days_until_dep"):
        MarketDataController.format_payload(
            origin_code="DEL",
            destination_code="BOM",
            airline_code="6E",
            price=5500.0,
            departure_date="2026-08-01",
            days_until_dep=-3
        )

    same_day = MarketDataController.format_payload(
        origin_code="DEL",
        destination_code="BOM",
        airline_code="6E",
        price=5500.0,
        departure_date="2026-08-01",
        days_until_dep=0
    )
    assert same_day["days_until_dep"] == 0
    assert same_day["urgency"] == 1.0


def test_training_eligibility():
    """Verify is_training_eligible filters out synthetic, invalid fare, or incomplete observations."""
    valid_record = {
        "origin_code": "DEL",
        "destination_code": "BOM",
        "airline_code": "6E",
        "price": 5500.0,
        "departure_date": "2026-08-01",
        "days_until_dep": 10,
        "is_synthetic": False,
        # Required, and it was not here before. The loaders select on
        # `is_synthetic IS FALSE AND is_live IS TRUE`; this module used to apply
        # only the first half, so this record — indistinguishable from a seeded
        # row — was eligible.
        "is_live": True,
    }
    assert is_training_eligible(valid_record) is True

    synthetic_record = dict(valid_record, is_synthetic=True)
    assert is_training_eligible(synthetic_record) is False

    # The seeded block, exactly as it sits in the corpus: the migration that
    # added `is_synthetic` defaulted it to FALSE, so the label says authentic and
    # only `is_live` says otherwise.
    seeded_record = dict(valid_record, is_live=False)
    assert is_training_eligible(seeded_record) is False

    # Absence is not authenticity. Neither column may be assumed.
    assert is_training_eligible({k: v for k, v in valid_record.items() if k != "is_live"}) is False
    assert is_training_eligible({k: v for k, v in valid_record.items() if k != "is_synthetic"}) is False

    # Postgres bools arrive as bools, but a CSV round-trip arrives as strings.
    assert is_training_eligible(dict(valid_record, is_live="true", is_synthetic="false")) is True
    assert is_training_eligible(dict(valid_record, is_live="false")) is False

    cheap_record = dict(valid_record, price=150.0)
    assert is_training_eligible(cheap_record) is False

    expensive_record = dict(valid_record, price=999999.0)
    assert is_training_eligible(expensive_record) is False

    missing_price_record = dict(valid_record, price=None)
    assert is_training_eligible(missing_price_record) is False

    missing_key_record = dict(valid_record, origin_code=None)
    assert is_training_eligible(missing_key_record) is False


def test_filter_training_eligible_dataframe():
    """Verify DataFrame filtering based on training eligibility."""
    base = {
        "origin_code": "DEL", "destination_code": "BOM", "airline_code": "6E",
        "price": 5500.0, "departure_date": "2026-08-01", "days_until_dep": 10,
        "is_synthetic": False, "is_live": True,
    }
    data = [
        base,
        dict(base, price=500.0),          # below the fare floor
        dict(base, is_synthetic=True),    # labelled synthetic
        dict(base, is_live=False),        # seeded: authentic label, not live
        dict(base, price=None),           # no fare
        dict(base, origin_code=""),       # empty mandatory key
    ]
    df = pd.DataFrame(data)
    df_filtered = filter_training_eligible_dataframe(df)
    assert len(df_filtered) == 1
    assert df_filtered.iloc[0]["price"] == 5500.0

    # The frame filter and the record filter must agree row for row; they used to
    # differ on absent columns, on string flags and on NaN prices.
    for _, row in df.iterrows():
        expected = is_training_eligible(row.to_dict())
        actual = row.name in df_filtered.index
        assert actual is expected, f"row {row.name} disagrees: frame={actual} record={expected}"

    # A frame with no provenance columns at all is not a frame of observations.
    assert filter_training_eligible_dataframe(
        pd.DataFrame([{k: v for k, v in base.items() if k not in ("is_live", "is_synthetic")}])
    ).empty


def test_multi_horizon_readiness_grading():
    """Verify dataset quality validator assigns letter grades A-F for readiness."""
    df_empty = pd.DataFrame()
    readiness_empty = dataset_quality_validator.evaluate_horizon_readiness(df_empty)
    assert readiness_empty["0d"].grade == "F"
    assert readiness_empty["0d"].ready is False
