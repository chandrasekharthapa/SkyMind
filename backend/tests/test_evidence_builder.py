import pytest
from backend.services.evidence_builder import (
    EvidenceBuilder,
    EvidencePackage,
    normalize_currency_amount
)


def test_currency_normalization():
    """Verify currency conversion and float rounding."""
    assert normalize_currency_amount(5000) == 5000.0
    assert normalize_currency_amount("9330.50") == 9330.5
    assert normalize_currency_amount(100.0, "USD") == 8500.0
    # Was `== 0.0`. An unparseable or absent amount is now null, because ₹0 is a
    # fare the provider never quoted and it reached the model prompt as evidence.
    assert normalize_currency_amount("invalid") is None
    assert normalize_currency_amount(None) is None
    assert normalize_currency_amount(float("nan")) is None


def test_absent_fields_stay_null():
    """A provider omission must not become a fabricated value."""
    builder = EvidenceBuilder()
    pkg = builder.build_package("sess_null", [{
        "_tool_name": "search_flights",
        "status": "success",
        "flights": [{"seats_available": 4}],
    }])

    assert len(pkg.items) == 1
    data = pkg.items[0].data
    # Previously: "UNKNOWN_1", "6E", "IndiGo", 0.0.
    assert data["flight_number"] is None
    assert data["airline_code"] is None
    assert data["airline_name"] is None
    assert data["price_inr"] is None
    assert pkg.summary_metrics["min_price_inr"] is None
    assert pkg.summary_metrics["price_spread_inr"] is None


def test_forecast_bounds_are_not_defaulted_to_zero():
    """A forecast point without bounds publishes nulls, not a 0..0 interval."""
    builder = EvidenceBuilder()
    pkg = builder.build_package("sess_fc", [{
        "_tool_name": "predict_price",
        "status": "success",
        "predicted_price": 5000.0,
        "forecast": [
            {"date": "2026-09-10", "price": 5100.0},
            {"date": "2026-09-11", "price": 5200.0, "lower": 4900.0, "upper": 5600.0,
             "interval_basis": {"lower_percentile": 10.0, "upper_percentile": 90.0}},
        ],
    }])

    fc_items = [i for i in pkg.items if i.category == "FORECAST_DAY"]
    assert len(fc_items) == 2

    unbounded = fc_items[0].data
    assert unbounded["lower_bound_inr"] is None
    assert unbounded["upper_bound_inr"] is None
    assert "interval_basis" not in unbounded

    measured = fc_items[1].data
    assert measured["lower_bound_inr"] == 4900.0
    assert measured["upper_bound_inr"] == 5600.0
    assert measured["interval_basis"]["upper_percentile"] == 90.0


def test_evidence_builder_deduplication_and_metrics():
    """Verify flight deduplication, min/max price computation, and provenance tracking."""
    builder = EvidenceBuilder()
    mock_payloads = [
        {
            "_tool_name": "search_flights",
            "status": "success",
            "flights": [
                {
                    "flight_number": "6E101",
                    "primary_airline": "6E",
                    "primary_airline_name": "IndiGo",
                    "price": 4500.0,
                },
                {
                    "flight_number": "6E101",
                    "primary_airline": "6E",
                    "primary_airline_name": "IndiGo",
                    "price": 4500.0,  # Duplicate offer
                },
                {
                    "flight_number": "UK815",
                    "primary_airline": "UK",
                    "primary_airline_name": "Vistara",
                    "price": 6200.0,
                }
            ]
        }
    ]

    pkg = builder.build_package("sess_123", mock_payloads)
    
    assert isinstance(pkg, EvidencePackage)
    assert len(pkg.items) == 2  # 1 duplicate removed
    assert pkg.deduplication_ratio > 0.0
    assert pkg.summary_metrics["min_price_inr"] == 4500.0
    assert pkg.summary_metrics["max_price_inr"] == 6200.0
    assert pkg.summary_metrics["price_spread_inr"] == 1700.0
    assert pkg.provenance_coverage == 1.0


def test_empty_or_malformed_payloads():
    """Verify robust handling of empty or malformed tool outputs."""
    builder = EvidenceBuilder()
    pkg_empty = builder.build_package("sess_456", [])
    assert len(pkg_empty.items) == 0
    assert pkg_empty.provenance_coverage == 0.0

    pkg_malformed = builder.build_package("sess_789", [{"invalid": None}, "not_a_dict"])
    assert len(pkg_malformed.items) == 0


@pytest.mark.asyncio
async def test_shadow_evidence_builder():
    """Verify non-blocking shadow evidence builder execution."""
    builder = EvidenceBuilder()
    pkg = await builder.build_shadow("sess_async", [{"status": "success", "airports": [{"code": "DEL", "name": "Delhi"}]}])
    
    assert isinstance(pkg, EvidencePackage)
    assert len(pkg.items) == 1
    assert pkg.items[0].data["iata_code"] == "DEL"
