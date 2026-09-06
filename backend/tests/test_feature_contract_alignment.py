"""The feature contract has one definition, and the serving paths ask for it.

`backend/ml/feature_metadata.py` declares two feature sets. `PricePredictor` can
consume exactly one of them: `feature_cols` is its input shape for `train()` and
for `predict()` alike, and nothing anywhere converts a `feature_set_v1` vector
into a legacy one. Four hand-maintained copies of that 16-name list used to exist
— in `price_model`, in `feature_validation`, in `prediction_features`, and as a
literal in the old parity test. Three are gone; this file is what keeps them gone.

The defect that motivated it: `PricePredictor.forecast` chose its feature set with
`"legacy" if self.legacy_mode else "feature_set_v1"`, and `legacy_mode` is True
only on the single-pickle `global_model.pkl` path. So every normal forecast built
a 64-name v1 vector, and `predict()` reindexed it onto the legacy 16 — NaN-filling
the nine names v1 does not declare, `days_until_dep` and `urgency` among them. The
published curve was computed without the booking horizon, which is the one
quantity a horizon sweep varies, and nothing raised or logged.

Value-level train/serve agreement is `test_training_inference_parity.py`'s job.
This file asserts the contract those two paths are asked for.
"""

from datetime import date, datetime, timedelta, timezone

import numpy as np
import pytest

from backend.ml.feature_context import FeatureContext
from backend.ml.feature_engineering_pipeline import feature_engineering_pipeline
from backend.ml.feature_metadata import FEATURE_SET_V1, LEGACY_FEATURE_SET
from backend.ml.price_model import PricePredictor
from backend.services.feature_validation import (
    EXPECTED_FEATURE_COLS,
    FEATURE_NAMES_BY_VERSION,
    feature_validation_service,
)
from backend.utils.exceptions import PredictionUnavailable

LEGACY_NAMES = [definition.name for definition in LEGACY_FEATURE_SET]
V1_NAMES = [definition.name for definition in FEATURE_SET_V1]

DEPARTURE = date(2026, 10, 1)
BOOKED_FROM = date(2026, 9, 2)


def _history(rows: int = 8):
    """One curve with `rows` observations, one per day, ending the day before."""
    return [
        {
            "origin_code": "DEL",
            "destination_code": "BOM",
            "airline_code": "6E",
            "flight_number": "6E-101",
            "departure_date": DEPARTURE.isoformat(),
            "price": 5000.0 + 40 * index,
            "recorded_at": (
                datetime(2026, 9, 1, tzinfo=timezone.utc) - timedelta(days=index)
            ).isoformat(),
            "seats_available": 9,
        }
        for index in range(rows)
    ]


def _built(horizon: int, version: str):
    """The FeatureVector `forecast()` builds for one horizon, at its booking date."""
    booking_date = BOOKED_FROM + timedelta(days=horizon)
    context = FeatureContext(
        historical_data=_history(),
        market_snapshot={
            "origin": "DEL",
            "destination": "BOM",
            "airline": "6E",
            "departure_date": DEPARTURE.isoformat(),
            "lowest_fare": 5200.0,
        },
        prediction_context={
            "origin": "DEL",
            "destination": "BOM",
            "airline": "6E",
            "departure_date": DEPARTURE.isoformat(),
            "seats_available": np.nan,
            "current_price": 5200.0,
            "lowest_fare": 5200.0,
            "days_until_dep": (DEPARTURE - booking_date).days,
        },
        route_statistics={},
        airline_statistics={},
        booking_statistics={},
        current_timestamp=datetime.combine(
            booking_date, datetime.min.time(), tzinfo=timezone.utc
        ),
    )
    return feature_engineering_pipeline.build(context, version)


def _vector(horizon: int, version: str):
    return _built(horizon, version).features


@pytest.fixture(scope="module")
def predictor():
    """A predictor with no artifact loaded.

    Every assertion below is about the declared contract, which `__init__`
    establishes. Nothing here calls `predict()`, which would need a fitted model —
    the refusal it delegates to is reachable on its own.
    """
    return PricePredictor()


def test_the_input_shape_is_the_declared_legacy_set(predictor):
    """`feature_cols` is derived, not copied — order included.

    Order matters: it is the fitted estimator's column order, and
    `model_schema_validator` compares names position by position.
    """
    assert predictor.feature_cols == LEGACY_NAMES
    assert predictor.feature_set_version == "legacy"
    assert len(predictor.feature_cols) == len(set(predictor.feature_cols))


def test_the_declared_version_is_one_the_pipeline_accepts(predictor):
    """A version string the pipeline does not know is a `ValueError` at serve time."""
    built = _built(1, predictor.feature_set_version)
    assert list(built.features) == predictor.feature_cols
    assert built.feature_set_version == predictor.feature_set_version


def test_foreign_names_are_disjoint_from_the_input_shape(predictor):
    """The guard's vocabulary cannot overlap the names it is protecting.

    If a legacy name leaked into `FOREIGN_FEATURE_NAMES`, every well-formed vector
    would be refused; if the set were empty, no malformed one would be.
    """
    assert predictor.FOREIGN_FEATURE_NAMES
    assert not predictor.FOREIGN_FEATURE_NAMES & set(predictor.feature_cols)
    assert predictor.FOREIGN_FEATURE_NAMES == set(V1_NAMES) - set(LEGACY_NAMES)


def test_a_v1_vector_is_refused_rather_than_reindexed(predictor):
    """The regression. A foreign vector must not be answered.

    Before the fix this dict reached `df[self.feature_cols]`, which kept the seven
    names the two sets share, discarded the other 57, and invented NaN for nine —
    then returned a float that no caller could tell from a prediction.
    """
    foreign_vector = _vector(1, "feature_set_v1")
    assert len(foreign_vector) == len(V1_NAMES)

    with pytest.raises(PredictionUnavailable) as raised:
        predictor._reject_foreign_features(foreign_vector)

    message = str(raised.value)
    assert "feature_set_v1" in message
    assert "'legacy'" in message
    # The message has to name what would have been substituted, because the
    # substitution is the damage and the count is what makes it legible.
    assert "days_until_dep" in message


def test_a_legacy_vector_is_accepted(predictor):
    """And with the horizon in it, which is what the forecast needs."""
    predictor._reject_foreign_features(_vector(1, "legacy"))


def test_a_partial_legacy_vector_is_still_accepted(predictor):
    """Omitting a value you could not compute is not the same fault.

    `flight_search_service` builds fifteen of the sixteen names by hand and lets
    `predict()` derive `urgency`. A guard that rejected that would have taken the
    per-flight prediction path down with it.
    """
    partial = {
        name: value
        for name, value in _vector(1, "legacy").items()
        if name != "urgency"
    }
    partial["origin"] = "DEL"  # an undeclared extra, as real callers pass
    predictor._reject_foreign_features(partial)


def test_the_horizon_reaches_the_model_under_the_legacy_set():
    """The quantity a horizon sweep varies is in the vector, and it moves.

    Measured at these four booking dates: `days_until_dep` is 28, 22, 15, 8 and
    `urgency` is 1/(days+1) — 0.0345, 0.0435, 0.0625, 0.1111. This is the whole
    point of a forecast curve, and it is what the published one was computed
    without.
    """
    horizons = [1, 7, 14, 21]
    vectors = [_vector(h, "legacy") for h in horizons]

    days = [v["days_until_dep"] for v in vectors]
    urgency = [v["urgency"] for v in vectors]
    assert not any(np.isnan(d) for d in days)
    assert days == sorted(days, reverse=True)
    assert len(set(days)) == len(days)
    assert urgency == sorted(urgency)
    assert len(set(urgency)) == len(urgency)


def test_a_horizon_past_departure_yields_nan_not_a_negative_horizon():
    """`BOOKED_FROM + 30` is the day after `DEPARTURE`.

    You cannot book a flight that has left, and the pipeline says so with NaN
    rather than a negative number the model has never been fitted on. This is
    also why the sweep above stops at 21.
    """
    late = _vector(30, "legacy")
    assert np.isnan(late["days_until_dep"])
    assert np.isnan(late["urgency"])


def test_the_v1_set_does_not_declare_the_horizon_by_the_name_the_model_knows():
    """The mechanism of the defect, stated as an assertion.

    v1 spells the horizon `days_until_departure`. Nothing renames it, so a v1
    vector reindexed onto the legacy columns loses the horizon entirely — the
    value is right there in the dict under a name the fitted estimator has never
    seen, which is why nothing looked wrong.
    """
    v1_vector = _vector(7, "feature_set_v1")

    assert "days_until_dep" not in v1_vector
    assert "urgency" not in v1_vector
    assert v1_vector["days_until_departure"] == 22.0

    # And the same two names are present under the set the model does eat.
    legacy_vector = _vector(7, "legacy")
    assert legacy_vector["days_until_dep"] == 22.0
    assert "days_until_departure" not in legacy_vector


def test_validation_selects_from_the_contract_rather_than_copying_it():
    """`EXPECTED_FEATURE_COLS` is the legacy list itself, not a list like it.

    Identity, not equality: an equal-but-separate list is exactly the state this
    change removed, and it would satisfy `==` right up until someone edited one of
    the two.
    """
    assert EXPECTED_FEATURE_COLS is FEATURE_NAMES_BY_VERSION["legacy"]
    assert FEATURE_NAMES_BY_VERSION["legacy"] == LEGACY_NAMES
    assert FEATURE_NAMES_BY_VERSION["feature_set_v1"] == V1_NAMES
    assert set(FEATURE_NAMES_BY_VERSION) == {"legacy", "feature_set_v1"}


def test_validation_expects_the_deployed_models_set():
    """Whatever the registry advertises is what gets graded.

    This was `self.expected_features = EXPECTED_FEATURE_COLS` in `__init__`, fixed
    at import time, so `production_readiness` could grade a frame against a
    contract the running model did not hold.
    """
    from backend.services.model_registry import model_registry

    deployed = model_registry.feature_set_version
    assert feature_validation_service.expected_features == FEATURE_NAMES_BY_VERSION.get(
        deployed, FEATURE_NAMES_BY_VERSION["legacy"]
    )


def test_validation_follows_the_registry_when_it_advertises_v1(monkeypatch):
    """The non-tautological half.

    With nothing loaded the registry answers `"legacy"` and so does the fallback,
    so the test above passes either way. Pinning the v1 case is what makes the
    property's behaviour distinguishable from the constant it replaced.
    """
    from backend.services.model_registry import model_registry

    monkeypatch.setattr(
        type(model_registry),
        "feature_set_version",
        property(lambda self: "feature_set_v1"),
    )
    assert feature_validation_service.expected_features == V1_NAMES


def test_an_unrecognised_advertised_set_falls_back_to_legacy(monkeypatch):
    """A version string with no name list is a fallback, not a KeyError.

    The fallback is deliberate and logged: a readiness check's job is to report
    that state, not to crash on it. Pinned so that a future third feature set
    added to `feature_metadata` and forgotten here degrades visibly instead of
    taking the check down.
    """
    from backend.services.model_registry import model_registry

    monkeypatch.setattr(
        type(model_registry),
        "feature_set_version",
        property(lambda self: "feature_set_v9_unreleased"),
    )
    assert feature_validation_service.expected_features == LEGACY_NAMES
