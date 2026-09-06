"""Canonical Schema Definitions for Flight Price Dataset v2.0."""

from typing import Dict, List, Any

# Mandatory raw observation columns required prior to feature engineering.
#
# `flight_number` used to be here and `departure_time` did not, which is exactly
# backwards. `SchemaValidationPlugin` does two things with this list: it fails when a
# column is absent, and it *drops every row* holding NaN in one of them. Google
# Flights publishes no flight number — measured, on the shipped parser, over a live
# 65-flight DEL-BOM fetch — so once the synthetic default was removed the column is
# NULL on every honestly-collected row, and this list was instructing the export path
# to reject the entire corpus. Meanwhile `departure_time`, which
# `BOOKING_CURVE_KEYS` now names as the per-flight component and which every label
# and every curve feature therefore depends on, was not required at all: a frame
# without it passed schema validation and only became silently unlabellable later.
#
# Pre-migration frames have no `departure_time` column, so the plugin will report it
# absent and fail. That is the intended reading — the corpus cannot support the
# pipeline's own definition of a curve until migration 001 is applied — and it is
# reported rather than worked around.
MANDATORY_RAW_COLUMNS = [
    "origin_code",
    "destination_code",
    "departure_date",
    "departure_time",
    "airline_code",
    "price",
    "recorded_at"
]

# Canonical dtype mapping for output dataset v2.0
CANONICAL_SCHEMA_TYPES: Dict[str, str] = {
    "itinerary_id": "string",
    "origin_code": "string",
    "destination_code": "string",
    "departure_date": "string",
    "departure_time": "string",
    "recorded_at": "string",
    "airline_code": "string",
    "flight_number": "string",
    "cabin_class": "string",
    "price": "float64",
    "days_until_dep": "int64",
    "snapshot_sequence": "int64",
    "snapshot_time": "string",
    "snapshot_date": "string",
    "dataset_version": "string",
    "feature_version": "string",
    "collector_version": "string",
    "pipeline_version": "string",
    "schema_version": "string"
}

# Valid IATA airport codes in Indian aviation network
VALID_IATA_CODES = {
    "DEL", "BOM", "BLR", "MAA", "CCU", "HYD", "GOI", "GOX", "COK", "BBI",
    "AMD", "PNQ", "IXC", "JAI", "LKO", "ATQ", "TRV", "GAU", "PAT", "IDR"
}

# Prohibited empty columns that must never exist without derivation
PROHIBITED_EMPTY_COLUMNS = ["duration", "terminal"]
