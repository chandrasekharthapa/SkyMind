import pytest
import asyncio
from datetime import date, timedelta

from backend.services.prediction_service import prediction_service
from backend.ml.price_model import get_predictor
from backend.tests.model_availability import requires_trained_model

# Computed, not written down: `PredictionValidator.validate_request` rejects a
# past departure date, so a literal turns this test red on a date nobody chose.
# It was "2026-07-30", which went past on 2026-07-31.
FUTURE_DATE = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")


def test_encoder_separates_known_routes_and_marks_unknown_ones():
    """Distinct codes for values the model was fitted on; 0 for values it was not.

    This test used to assert only `enc_bom != enc_bbi and both > 0`, and it passed
    with no model loaded at all — because `_encode_category` had two fallbacks
    below the real lookup: a hardcoded `IATA_REGISTRY` mapping thirty airports to
    1-30, and `(abs(hash(val)) % 900) + 31`. Both invent a positive code for a
    value the model has never seen, so the assertion was satisfied by the
    fabrication rather than by the encoder. Worse, the registry's 1-30 collide with
    trained codes, which also start at 1, so "distinct and positive" was true of
    two codes that both named some *other* airport.

    Both fallbacks are gone. The honest properties are the two below: a value in
    the horizon's map encodes to its own positive code, and a value outside it
    encodes to 0 — the reserved unseen marker that training itself produces via
    `.map(encoders[col]).fillna(0)`.
    """
    horizons = requires_trained_model()
    predictor = get_predictor()

    h = next((x for x in horizons if isinstance(x, int)), None)
    encoders = predictor.encoders_by_horizon.get(h, predictor.encoders) or {}
    dest_map = encoders.get("destination_code", {})
    if len(dest_map) < 2:
        pytest.skip(
            "the loaded model's destination_code encoder holds "
            f"{len(dest_map)} value(s); at least 2 are needed to assert that "
            "distinct destinations receive distinct codes."
        )

    first, second = sorted(dest_map)[:2]
    enc_first = predictor._encode_category("destination_code", first, horizon=h)
    enc_second = predictor._encode_category("destination_code", second, horizon=h)

    assert enc_first != enc_second, (
        f"{first} and {second} are separate values in the horizon {h} encoder but "
        f"both encoded to {enc_first}"
    )
    assert enc_first > 0 and enc_second > 0, (
        "codes for values present in the encoder must be positive; 0 is reserved "
        "for unseen values"
    )

    # A value the encoder does not hold is unseen, not some other airport.
    unseen = "ZZZ"
    assert unseen not in dest_map, "pick a code the fixture data cannot contain"
    assert predictor._encode_category("destination_code", unseen, horizon=h) == 0


@pytest.mark.asyncio
async def test_predictions_and_forecasts_differ_by_route():
    """Verify that prediction output and forecast points differ across distinct route requests."""
    requires_trained_model()
    res_bom = await prediction_service.predict("DEL", "BOM", FUTURE_DATE)
    res_bbi = await prediction_service.predict("DEL", "BBI", FUTURE_DATE)

    # Assert predicted prices differ based on route-specific features and market snapshots
    assert res_bom["predicted_price"] != res_bbi["predicted_price"]

    # Assert forecast arrays differ by route
    forecast_bom_prices = [f["price"] for f in res_bom["forecast"]]
    forecast_bbi_prices = [f["price"] for f in res_bbi["forecast"]]
    assert forecast_bom_prices != forecast_bbi_prices


def test_cache_keys_are_route_specific():
    """Verify that cache keys in market snapshot and prediction layers include route identifiers."""
    from backend.services.market_snapshot_provider import market_snapshot_provider
    
    key_bom = market_snapshot_provider._get_cache_key("DEL", "BOM", FUTURE_DATE)
    key_bbi = market_snapshot_provider._get_cache_key("DEL", "BBI", FUTURE_DATE)
    
    assert key_bom != key_bbi
    assert "DEL-BOM" in key_bom or "BOM" in key_bom
    assert "DEL-BBI" in key_bbi or "BBI" in key_bbi
