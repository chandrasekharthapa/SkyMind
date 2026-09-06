"""Test support: is there a model on disk that a test could legitimately use?

Not a test module — no `test_` prefix, so neither pytest nor the offline runner
collects anything here.

Nineteen test functions in this suite are about the *number a model produces*. Since
the three shipped artifacts were moved to `backend/ml/models/quarantine/` (their
metadata records no clean leak audit, and the R² of 0.932 they reported was
measuring `price_change_1d`, which at horizon 0 is defined as
`target - target.shift(1)`), those nineteen raised `FileNotFoundError` or
`PredictionUnavailable` and read as nineteen broken features. They are not broken;
they are inapplicable, and a suite that cannot say the difference is not telling
you anything.

Nineteen is measured, not asserted: it is the number of tests that skipped with this
helper's reason across a full sweep of all 137 `test_*.py` modules on 2026-09-05.
The count is not load-bearing — nothing reads it — so if a future sweep disagrees,
the sweep is right and this sentence is stale. An earlier version of it said
"twenty", written before the last five gates were applied.

The one thing a skip helper must not become is a switch that turns tests off. So
the probe here calls the real loader and treats exactly two outcomes as "no
model": the loader's own "nothing on disk" signal, and a load that completes
having accepted no horizon. Anything else — a corrupt pickle, a metadata file
that will not parse, an `AttributeError` inside `load()` — propagates, so a
loader bug fails its test rather than skipping it.
"""

import pytest

_HOW_TO_GET_ONE = (
    "Train one with `python -m backend.run_pipeline` (writes "
    "backend/ml/models/fare_forecast_<h>d.pkl plus a .metadata.json carrying a "
    "leak_audit block) to run this test. The artifacts under "
    "backend/ml/models/quarantine/ are deliberately not loadable; see the README "
    "there."
)


def trained_model_status():
    """`(loaded_horizons, reason)` for the predictor's artifacts on disk.

    `loaded_horizons` is the sorted list of horizons `load()` accepted — empty
    when there is no servable model. `reason` is a sentence naming the cause,
    empty when a model did load.

    Deliberately calls the loader rather than checking for files: "a .pkl is
    present" and "a .pkl this build will serve" are different questions, and a
    refused artifact is exactly as unusable as an absent one.
    """
    from backend.ml.price_model import get_predictor

    predictor = get_predictor()
    try:
        predictor.load()
    except FileNotFoundError as exc:
        # The loader's own signal for an empty models directory. Narrow on
        # purpose: a corrupt artifact raises something else and must not skip.
        return [], f"no model artifact on disk ({exc}). {_HOW_TO_GET_ONE}"

    horizons = sorted(getattr(predictor, "models", {}) or {})
    if horizons:
        return horizons, ""

    if getattr(predictor, "legacy_mode", False) and getattr(predictor, "model", None) is not None:
        # A legacy global_model.pkl loaded. It has no per-horizon metrics, so a
        # forecast test still cannot run, but a point-prediction test can — the
        # caller decides via `requires_forecast_metrics`.
        return ["legacy"], ""

    refused = getattr(predictor, "refused_artifacts", []) or []
    detail = "; ".join(refused) if refused else "load() accepted no horizon"
    return [], f"no servable model artifact: {detail}. {_HOW_TO_GET_ONE}"


def requires_trained_model():
    """Skip the calling test unless a servable model artifact exists.

    Call it as the first statement of a test whose subject is the model's own
    output. Do not call it in a test about routing, validation, response shape or
    anything else that holds with no model loaded — those must keep failing when
    they break.
    """
    horizons, reason = trained_model_status()
    if not horizons:
        pytest.skip(reason)
    return horizons


def requires_forecast_metrics(horizon=None):
    """Skip unless a loaded artifact records evaluation metrics for `horizon`.

    Separate from `requires_trained_model` because these are separate states and
    they produce different exceptions in production: an absent artifact raises
    `FileNotFoundError` from `load()`, while an artifact that loaded but records
    no `evaluation_metrics` raises `PredictionUnavailable("...records no
    evaluation metrics...")` from the forecast engine. A test asserting a
    confidence figure needs the second, not just the first.
    """
    from backend.ml.price_model import get_predictor

    horizons = requires_trained_model()
    predictor = get_predictor()
    metrics = getattr(predictor, "metrics", {}) or {}
    wanted = [horizon] if horizon is not None else list(horizons)
    for h in wanted:
        if isinstance(metrics.get(h), dict) and metrics[h]:
            return h
    pytest.skip(
        f"a model loaded for horizon(s) {horizons} but records no evaluation "
        f"metrics for {wanted}, so there is no measured confidence to assert. "
        f"{_HOW_TO_GET_ONE}"
    )
