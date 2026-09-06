import pytest
from unittest.mock import MagicMock
from backend.ml.price_model import PricePredictor
from backend.services.booking_curve_definition import MIN_TRAINABLE_HORIZON_DAYS


def test_independent_forecast_models():
    """Verify independent XGBoost models are registered and maintained for each horizon."""
    predictor = PricePredictor()
    assert predictor.supported_horizons == [1, 3, 7]

    # Horizon 0 is absent on purpose and its absence is the assertion: at
    # horizon 0 the label is the price on the same observation as the features,
    # so every price-derived feature is a function of the target.
    # `booking_curve_definition.MIN_TRAINABLE_HORIZON_DAYS` is the single place
    # that rule is stated, and this test reads it from there rather than
    # restating `1`, so widening the rule cannot leave this test asserting the
    # old one.
    assert 0 not in predictor.supported_horizons
    assert min(predictor.supported_horizons) >= MIN_TRAINABLE_HORIZON_DAYS

    # Mock trained models per horizon
    predictor.models = {
        1: MagicMock(),
        3: MagicMock(),
        7: MagicMock(),
    }
    predictor.legacy_mode = False
    predictor._trained = True

    # Configure mock return value array as returned by XGBoost
    predictor.models[1].predict.return_value = [5100.0]
    predictor.models[3].predict.return_value = [5500.0]
    predictor.models[7].predict.return_value = [6000.0]

    features = {"origin_code": "DEL", "destination_code": "BOM", "airline_code": "6E", "days_until_dep": 5}

    price_1d = predictor.predict(features, horizon=1)
    assert price_1d == 5100.0
    predictor.models[1].predict.assert_called_once()

    price_3d = predictor.predict(features, horizon=3)
    assert price_3d == 5500.0
    predictor.models[3].predict.assert_called_once()

    price_7d = predictor.predict(features, horizon=7)
    assert price_7d == 6000.0
    predictor.models[7].predict.assert_called_once()


def test_horizon_zero_is_not_a_trainable_target():
    """The label at horizon 0 is the feature row's own price, so it is refused.

    Asserted against the shared definition rather than against `PricePredictor`,
    because the refusal has to hold for whichever caller asks — the dataset
    builder refuses before it queries, and `attach_future_target` refuses when
    handed a frame directly.
    """
    import pandas as pd
    from backend.services.booking_curve_definition import (
        ORDERING_TIMESTAMP_KEY,
        attach_future_target,
    )

    # One flight, observed on four consecutive days. `departure_time` is the
    # per-flight component of the curve key as of 2026-09-03; `flight_number` is
    # kept alongside it, and constant, so that this frame would still label
    # correctly if the labeller were reading it — the assertion below is about the
    # horizon, and a fixture that quietly stopped forming a curve would fail here
    # for the wrong reason.
    df = pd.DataFrame([
        {
            "origin_code": "DEL", "destination_code": "BOM", "airline_code": "AI",
            "flight_number": "AI101", "departure_date": "2026-03-01",
            "departure_time": "2026-03-01T06:10:00",
            ORDERING_TIMESTAMP_KEY: pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(days=d),
            "price": 5000.0 + 100.0 * d,
        }
        for d in (0, 1, 2, 3)
    ])

    with pytest.raises(ValueError, match="not a trainable target"):
        attach_future_target(df, 0)

    # And the smallest horizon it does accept produces a label strictly later
    # than the row it labels, which is what makes it a forecast rather than a
    # restatement.
    labelled = attach_future_target(df, MIN_TRAINABLE_HORIZON_DAYS)
    assert not labelled.empty
    assert (labelled["target_price"] != labelled["price"]).all()
