"""Unit tests for `PricePredictor.load()`'s per-horizon artifact refusal.

This file used to assert the behaviour the leak audit replaced. Its metadata
fixture carried no `leak_audit` block, and it asserted `len(predictor.models) ==
4` — i.e. that an artifact with nothing recorded about whether its features
contain the target loads and serves. That is exactly the state the three shipped
artifacts were in when they reported R² 0.932 off `price_change_1d`.

It had a second defect independent of the leak audit: `supported_horizons` holds
three horizons (1d, 3d, 7d), so `== 4` could not hold whatever `load()` did. The
assertion counted a horizon the predictor has never had.

The refusal had no direct unit test at all; it was only observed indirectly, as
20 tests failing with "No prediction or forecasting models found on disk". These
tests drive `load()` over mocked artifacts so both sides of the contract are
asserted: audited artifacts load, unaudited ones are refused *and say why*.
"""

import os
from unittest.mock import patch, mock_open, MagicMock

import pytest

from backend.ml.price_model import PricePredictor, MODEL_PATH


def _payload():
    """What a horizon `.pkl` unpickles to."""
    return {
        "model": MagicMock(),
        "encoders": {"origin_code": {}},
        "metrics": {"mae": 100},
    }


def _metadata(leak_audit=...):
    """A horizon `.metadata.json`. Omit `leak_audit` to get one without the block."""
    meta = {
        "evaluation_metrics": {"mae": 100, "training_samples": 1200},
        "training_timestamp": "2026-07-20T12:00:00Z",
    }
    if leak_audit is not ...:
        meta["leak_audit"] = leak_audit
    return meta


@patch("json.load")
@patch("pickle.load")
@patch("os.path.exists", return_value=True)
@patch("builtins.open", mock_open())
def test_audited_artifacts_load(mock_exists, mock_pickle_load, mock_json_load):
    """A clean `leak_audit` is what makes an artifact loadable."""
    predictor = PricePredictor()
    mock_pickle_load.return_value = _payload()
    mock_json_load.return_value = _metadata(
        leak_audit={"clean": True, "ceiling": 0.41, "suspect_features": []})

    predictor.load()

    assert len(predictor.models) == len(predictor.supported_horizons)
    assert predictor.supports_forecasting is True
    assert predictor.legacy_mode is False
    assert predictor.refused_artifacts == []
    # Read from the metadata, not defaulted to the old unprovenanced 1803.
    assert predictor.dataset_size == 1200


@patch("json.load")
@patch("pickle.load")
@patch("os.path.exists", return_value=True)
@patch("builtins.open", mock_open())
def test_metadata_without_leak_audit_is_refused(mock_exists, mock_pickle_load, mock_json_load):
    """No `leak_audit` block means refused — this is the case that used to pass.

    Every path is present here (`os.path.exists` is True for all of them), so the
    legacy fallback is reached too and must refuse on the same grounds; the
    resulting exception is the one 20 other tests see.
    """
    predictor = PricePredictor()
    mock_pickle_load.return_value = _payload()
    mock_json_load.return_value = _metadata()  # no leak_audit

    with pytest.raises(FileNotFoundError) as excinfo:
        predictor.load()

    assert predictor.models == {}
    assert predictor.legacy_mode is False
    # One refusal per horizon, plus the legacy artifact.
    assert len(predictor.refused_artifacts) == len(predictor.supported_horizons) + 1
    assert all("no leak_audit" in r for r in predictor.refused_artifacts), \
        predictor.refused_artifacts
    # The reason must travel with the exception. A bare "not found" over a
    # directory holding four .pkl files sends the reader to the wrong question.
    assert "leak_audit" in str(excinfo.value), str(excinfo.value)


@patch("json.load")
@patch("pickle.load")
@patch("os.path.exists", return_value=True)
@patch("builtins.open", mock_open())
def test_dirty_leak_audit_is_refused_and_names_the_feature(
        mock_exists, mock_pickle_load, mock_json_load):
    """`clean: False` is refused, and the flagged feature appears in the reason."""
    predictor = PricePredictor()
    mock_pickle_load.return_value = _payload()
    mock_json_load.return_value = _metadata(
        leak_audit={"clean": False, "ceiling": 0.94,
                    "suspect_features": ["price_change_1d"]})

    with pytest.raises(FileNotFoundError):
        predictor.load()

    assert predictor.models == {}
    horizon_refusals = [r for r in predictor.refused_artifacts if not r.startswith("legacy")]
    assert len(horizon_refusals) == len(predictor.supported_horizons)
    assert all("price_change_1d" in r for r in horizon_refusals), horizon_refusals


@patch("json.load")
@patch("pickle.load")
@patch("builtins.open", mock_open())
def test_missing_metadata_sibling_is_refused(mock_pickle_load, mock_json_load):
    """A `.pkl` with no `.metadata.json` beside it is refused, not loaded blind.

    `fare_forecast_7d.pkl` actually shipped in this state, and the branch that
    skipped it was silent, so the 7d horizon simply did not exist at runtime.
    """
    predictor = PricePredictor()
    mock_pickle_load.return_value = _payload()
    mock_json_load.return_value = _metadata(leak_audit={"clean": True})

    def only_pkl(path):
        # MODEL_PATH also ends in `.pkl`, so excluding it explicitly is what
        # keeps this test about the missing sibling rather than about the legacy
        # fallback; the legacy branch has its own two tests below.
        return path.endswith(".pkl") and path != MODEL_PATH and "quarantine" not in path

    with patch("os.path.exists", side_effect=only_pkl):
        with pytest.raises(FileNotFoundError):
            predictor.load()

    assert predictor.models == {}
    assert len(predictor.refused_artifacts) == len(predictor.supported_horizons)
    assert all("no metadata sibling" in r for r in predictor.refused_artifacts), \
        predictor.refused_artifacts


@patch("pickle.load")
@patch("builtins.open", mock_open())
def test_legacy_pickle_without_audit_is_refused(mock_pickle_load):
    """The legacy branch must not be a way around the refusal.

    `global_model.pkl` has no metadata sibling, so before this the branch loaded
    it unconditionally: an artifact refused above as unaudited was served here in
    legacy mode. The audit now has to be inside the pickle's own payload.
    """
    predictor = PricePredictor()
    mock_pickle_load.return_value = _payload()  # no leak_audit key

    with patch("os.path.exists", side_effect=lambda p: p == MODEL_PATH):
        with pytest.raises(FileNotFoundError) as excinfo:
            predictor.load()

    assert predictor.legacy_mode is False
    # `getattr` because a fresh PricePredictor has no `model` attribute at all —
    # only a successful load creates it. `predictor.model is None` raises
    # AttributeError here, which would pass a `pytest.raises` test for the wrong
    # reason.
    assert getattr(predictor, "model", None) is None
    assert predictor._trained is False
    assert any(r.startswith("legacy:") for r in predictor.refused_artifacts), \
        predictor.refused_artifacts
    assert os.path.basename(MODEL_PATH) in str(excinfo.value), str(excinfo.value)


@patch("pickle.load")
@patch("builtins.open", mock_open())
def test_legacy_dirty_audit_is_refused(mock_pickle_load):
    """A legacy pickle whose own audit says `clean: False` is refused.

    Distinct from the no-audit case: this one has the block, so only the `clean`
    half of the condition can reject it. Without this test, weakening that half
    to `get("clean", True)` reddens nothing.
    """
    predictor = PricePredictor()
    payload = _payload()
    payload["leak_audit"] = {"clean": False, "ceiling": 0.91,
                             "suspect_features": ["price_change_3d"]}
    mock_pickle_load.return_value = payload

    with patch("os.path.exists", side_effect=lambda p: p == MODEL_PATH):
        with pytest.raises(FileNotFoundError) as excinfo:
            predictor.load()

    assert predictor.legacy_mode is False
    assert getattr(predictor, "model", None) is None
    legacy = [r for r in predictor.refused_artifacts if r.startswith("legacy:")]
    assert legacy, predictor.refused_artifacts
    assert "price_change_3d" in legacy[0], legacy
    assert "price_change_3d" in str(excinfo.value), str(excinfo.value)


@patch("json.load")
@patch("pickle.load")
@patch("builtins.open", mock_open())
def test_horizon_refusals_reach_the_exception(mock_pickle_load, mock_json_load):
    """With no legacy artifact present, the tail raise must still name the reasons.

    The legacy branch has its own message; this exercises the other exit, which is
    what an operator sees when `global_model.pkl` is absent and every horizon
    artifact was declined.
    """
    predictor = PricePredictor()
    mock_pickle_load.return_value = _payload()
    mock_json_load.return_value = _metadata()  # no leak_audit

    with patch("os.path.exists", side_effect=lambda p: p != MODEL_PATH):
        with pytest.raises(FileNotFoundError) as excinfo:
            predictor.load()

    message = str(excinfo.value)
    assert "leak_audit" in message, message
    for horizon in predictor.supported_horizons:
        assert f"{horizon}d:" in message, (horizon, message)


@patch("json.load")
@patch("pickle.load")
@patch("os.path.exists", return_value=True)
@patch("builtins.open", mock_open())
def test_leak_audit_without_a_clean_key_is_refused(
        mock_exists, mock_pickle_load, mock_json_load):
    """An audit block that never says `clean` is not an assurance of anything.

    `audit.get("clean", False)` is what makes this refuse. The default is the
    entire check here, and it is invisible to the `clean: False` test above —
    flipping it to `get("clean", True)` leaves that test green.
    """
    predictor = PricePredictor()
    mock_pickle_load.return_value = _payload()
    mock_json_load.return_value = _metadata(leak_audit={"ceiling": 0.44})

    with pytest.raises(FileNotFoundError):
        predictor.load()

    assert predictor.models == {}


@patch("pickle.load")
@patch("builtins.open", mock_open())
def test_legacy_audit_without_a_clean_key_is_refused(mock_pickle_load):
    """Same default, on the legacy branch."""
    predictor = PricePredictor()
    payload = _payload()
    payload["leak_audit"] = {"ceiling": 0.44}
    mock_pickle_load.return_value = payload

    with patch("os.path.exists", side_effect=lambda p: p == MODEL_PATH):
        with pytest.raises(FileNotFoundError):
            predictor.load()

    assert predictor.legacy_mode is False
    assert getattr(predictor, "model", None) is None


@patch("pickle.load")
@patch("builtins.open", mock_open())
def test_legacy_pickle_with_clean_audit_loads(mock_pickle_load):
    """The legacy path still works for an artifact that records a clean audit.

    Asserted so the refusal above is shown to be about the audit and not about
    the legacy branch having been disabled outright.
    """
    predictor = PricePredictor()
    payload = _payload()
    payload["leak_audit"] = {"clean": True, "ceiling": 0.38}
    payload["dataset_size"] = 940
    mock_pickle_load.return_value = payload

    with patch("os.path.exists", side_effect=lambda p: p == MODEL_PATH):
        predictor.load()

    assert predictor.legacy_mode is True
    assert predictor.model is not None
    assert predictor.dataset_size == 940
