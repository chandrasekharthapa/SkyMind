"""Test Suite for the Model Registry.

The registry is a *view* of the loaded `PricePredictor`, so the property worth
asserting is agreement, not a value. This module used to assert four literals:

    assert model_registry.model_version == "2.0.0"
    assert model_registry.feature_schema_version == "2.0.0"
    assert len(model_registry.expected_features) == 16
    assert model_registry.supports_live_market_features is True

Three of those pin the very numbers the registry was corrected to stop inventing.
`len(...) == 16` is the legacy feature count: deploy a `feature_set_v1` artifact,
which declares 18, and the test fails although nothing is wrong. And the two
version strings are literals in `PricePredictor.__init__`, so the assertion held
whatever artifact was loaded — including none — and would have broken on the first
artifact that recorded its own version, which is the case the registry now handles
first.

What replaces them: the registry must return the deployed predictor's feature list
rather than a second copy of it, that list must be one of the sets declared in
`feature_metadata`, the advertised `feature_set_version` must name the set the list
actually matches, and the absence fallbacks must stay empty rather than naming
horizons and routes no model was fitted on. Those last cases use an injected
stand-in predictor, so they need no artifact and no xgboost.
"""

from typing import List

import pytest

from backend.ml.feature_metadata import FEATURE_SET_V1, LEGACY_FEATURE_SET
from backend.services.model_registry import ModelRegistry, model_registry

DECLARED_SETS = {
    "legacy": [f.name for f in LEGACY_FEATURE_SET],
    "feature_set_v1": [f.name for f in FEATURE_SET_V1],
}


class _Standin:
    """A predictor that has loaded nothing, and declares nothing it has not got.

    Deliberately not a `MagicMock`: an auto-generated attribute would satisfy
    every `getattr` the registry performs, which is the opposite of what these
    cases test. `ModelRegistry(predictor=...)` takes it directly, so the module
    singleton is untouched.
    """

    feature_cols: List[str] = []
    models: dict = {}
    legacy_mode = False
    metadata: dict = {}


def test_the_registry_reports_the_predictors_feature_list_not_a_copy():
    assert model_registry.expected_features is not None
    assert model_registry.expected_features == getattr(
        model_registry._predictor, "feature_cols", [])
    assert model_registry.feature_count == len(model_registry.expected_features)


def test_the_deployed_feature_list_is_one_of_the_declared_sets():
    """A count cannot say which contract is deployed; a name can.

    This replaces `len(...) == 16`. It still fails if someone edits a feature set
    without updating the model that eats it — the failure just no longer depends on
    which of the two sets happens to be deployed.
    """
    features = model_registry.expected_features
    if not features:
        pytest.skip("no artifact loaded, so no feature contract is deployed")

    matches = [name for name, cols in DECLARED_SETS.items() if cols == features]
    assert matches, (
        f"deployed feature list matches no declared set: {features}")
    assert model_registry.feature_set_version == matches[0], (
        f"registry advertises {model_registry.feature_set_version!r} but the "
        f"feature list is the {matches[0]!r} set")


def test_the_live_market_capability_follows_the_deployed_contract():
    """`supports_live_market_features` is a claim about `is_live` being an input.

    Asserting it `is True` outright made the flag look independent of the contract.
    It is not, and both declared sets contain `is_live` — so the assertion that
    matters is that the flag and the contract cannot disagree.
    """
    features = model_registry.expected_features
    assert model_registry.supports_live_market_features == ("is_live" in features)
    for name, cols in DECLARED_SETS.items():
        assert "is_live" in cols, f"{name} no longer declares is_live"


def test_forecast_capability_and_the_capability_list_agree():
    caps = model_registry.model_capabilities
    assert "predict" in caps
    assert ("forecast" in caps) == model_registry.supports_forecast


def test_recorded_versions_are_strings_or_absent_never_invented():
    """Both properties read metadata, then the predictor, then give up.

    The old assertions pinned `"2.0.0"`, which is the value
    `PricePredictor.__init__` assigns. Nothing may substitute a version for an
    artifact that records none — `None` is the answer in that case.
    """
    for value in (model_registry.model_version,
                  model_registry.feature_schema_version):
        assert value is None or (isinstance(value, str) and value)


def test_an_artifacts_own_version_outranks_the_code_literal():
    standin = _Standin()
    standin.model_version = "2.0.0"
    standin.primary_horizon = 1
    standin.metadata = {1: {"model_version": "7.1.3",
                            "feature_schema_version": "9.9.9"}}

    registry = ModelRegistry(predictor=standin)
    assert registry.model_version == "7.1.3"
    assert registry.feature_schema_version == "9.9.9"


def test_a_predictor_with_nothing_loaded_advertises_nothing():
    """The fallbacks these properties used to carry were the defect.

    `supported_horizons` defaulted to `[0, 1, 3, 7]` — including horizon 0, which
    `MIN_TRAINABLE_HORIZON_DAYS` rules out as a target — and `supported_routes` to
    `["DEL-BOM", "BOM-DEL"]`, so `/capabilities` advertised four horizons and two
    routes on a deployment with no model at all.
    """
    registry = ModelRegistry(predictor=_Standin())

    assert registry.supported_horizons == []
    assert registry.supported_routes == []
    assert registry.supports_forecasting is False
    assert registry.observation_count == 0
    assert registry.coverage_days == 0
    assert registry.dataset_version is None
    assert registry.training_timestamp is None
    assert registry.target_definition == "unknown"


def test_the_prediction_horizon_is_never_zero():
    """Whatever is loaded, the published horizon must be a trainable one — or absent.

    Zero is the one value it must never be: at horizon 0 the label is the
    observation's own price. With nothing loaded the property returns None rather
    than the smallest declared horizon, so the metadata endpoint publishes no
    horizon for a model that does not exist.
    """
    standin = _Standin()
    standin.supported_horizons = [1, 3, 7]
    registry = ModelRegistry(predictor=standin)

    assert registry.prediction_horizon is None

    live = model_registry.prediction_horizon
    assert live is None or live > 0
