"""SkyMind — XGBoost Price Predictor.

Strict compliance with Zero Synthetic Feature Policy: no fake seat numbers,
heuristic demand scores, or placeholder peak hour flags are fabricated.
Missing data is natively handled via XGBoost np.nan representation.
Supports genuine forecasting of future market states on separate horizons (0d, 1d, 3d, 7d).
"""

import os
import logging
import math
import pickle
import json
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
# `sklearn.model_selection.train_test_split` was imported here and never called.
# It is deleted rather than left unused: a random splitter in scope in the module
# whose only legitimate split is chronological is an invitation, and the import
# line is what a reader checks to see which kind of split this module performs.
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

from backend.domain.provenance import LIVE_KEY, decode_flag
from backend.ml.feature_metadata import FEATURE_SET_V1, LEGACY_FEATURE_SET
from backend.utils.exceptions import (
    HorizonUnavailable,
    IntervalUnavailable,
    PredictionUnavailable,
)

logger = logging.getLogger(__name__)

# Standardise path relative to this file's location
BASE_ML_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_ML_DIR, "models", "global_model.pkl")

# ── Acceptance gate ───────────────────────────────────────────────────
# The gate used to read `if r2 < 0.0 and len(df_horizon) < 1000`. The comment
# above it said "Reject models with R^2 < 0.0 on test fold" — the code said
# something narrower, because the second conjunct switches the gate off on any
# dataset of 1000 rows or more. The shipped 0d and 1d artifacts were trained on
# 31,537 and 2,998 observations, so for those two the only acceptance criterion
# in the production training path could not fire at all. A gate whose guard also
# has to be true is not a gate.
#
# The 3d artifact went the other way and shows why one criterion is not enough:
# 132 observations, a 27-row test fold, and `"quality_gate_passed": True`. The
# gate was live for it and passed it, because R² was 0.707 — measured on 27
# rows. Hence a minimum test-fold size, a MAPE ceiling, and a leak audit
# alongside the R² floor.
#
# A threshold is only as honest as the metric it reads. The MAPE the ceiling is
# compared against used to be re-derived inline with a denominator of
# `np.maximum(y_test, 1)`, which keeps a row whose true fare is non-positive and
# divides by ₹1 instead — so the number the gate checked was not a percentage of
# the fares. It now comes from `backend.ml.metrics.mape_with_coverage`, the one
# definition in the repo, which excludes those rows and reports how many it used.
# `test_mape_is_measurable` is a separate criterion so that "we measured the
# error and it was acceptable" and "we could not measure the error" cannot both
# print as a pass, and neither can print as the other's failure.
#
# Thresholds are named and recorded into each model's metadata so that the
# criteria a model was accepted under travel with the artifact, rather than
# living as a literal `"quality_gate_passed": True` written unconditionally
# after the check.
MIN_TEST_R2 = 0.0          # worse than predicting the mean of the test fold
MAX_TEST_MAPE = 35.0       # percent; a model this wrong is not servable
MIN_TEST_ROWS = 30         # below this, the metrics are noise, not evidence

# A single feature that explains more than this much of the test fold's price
# variance, on its own, is a leak signal rather than a discovery. The shipped
# 0d model put 37.4% of its importance on `price_change_3d` and 10.6% on
# `price_change_1d` — features defined as `price - price.shift(n)`, where the
# target at horizon 0 *is* `price`. Two of sixteen inputs therefore contained
# the answer, which is what an R² of 0.932 on fare prediction was measuring.
SINGLE_FEATURE_R2_CEILING = 0.50

# Below this, a returned fare is not a prediction about the Indian domestic
# market. Used only to log, never to alter a value.
IMPLAUSIBLE_FARE_FLOOR = 800.0

# `forecast()` needs the price-history features its model was trained on. When
# fewer than this many observations exist for a route the honest answer is that
# there is not enough history, not a number derived from the current fare.
MIN_FORECAST_HISTORY_ROWS = 2

# How many recorded observations of one booking curve `forecast()` reads, newest
# first. Was the bare literal `100` on a query filtered by route and departure
# date only — a cap on the wrong population, since the narrowing to a single
# flight happens afterwards in `price_changes_from_records`. The query now carries
# the flight's identity, so this bounds the curve the features are about.
FORECAST_HISTORY_ROW_CAP = 100

# The forecast interval is the model's own recorded residual distribution,
# shifted onto the point estimate. `residuals = y_test - preds`, so
# `predicted + q(residual)` is an empirical quantile of the *actual* fare, and
# any systematic bias in the model shifts the whole interval with it rather than
# being hidden by a symmetric band centred on the prediction.
#
# 10th and 90th percentiles: an 80% central interval. Below this many residuals
# the tail quantiles are one or two observations each and the interval is noise,
# so `_interval_bounds` refuses instead of publishing one.
RESIDUAL_INTERVAL_LOWER_PERCENTILE = 10.0
RESIDUAL_INTERVAL_UPPER_PERCENTILE = 90.0
MIN_RESIDUALS_FOR_INTERVAL = 20


def run_provenance() -> Dict[str, Any]:
    """What is needed to reproduce a training run, recorded with the artifact.

    The production path recorded none of this: no commit, no seed field, no
    library versions, no hyperparameter block. A rich provenance block existed
    only in `model_trainer.py`, which has no non-test callers, so nothing that
    ever shipped carried it.
    """
    import platform
    import subprocess

    commit = None
    dirty = None
    try:
        repo = os.path.dirname(os.path.dirname(BASE_ML_DIR))
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
            text=True, timeout=10).stdout.strip() or None
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain"], cwd=repo, capture_output=True,
            text=True, timeout=10).stdout.strip())
    except Exception:
        pass                                # recorded as null, never invented

    versions = {"python": platform.python_version()}
    for mod in ("numpy", "pandas", "sklearn", "xgboost"):
        try:
            versions[mod] = __import__(mod).__version__
        except Exception:
            versions[mod] = None
    return {"git_commit": commit, "git_worktree_dirty": dirty,
            "platform": platform.platform(), "library_versions": versions}


def audit_feature_leakage(X_train, y_train, X_test, y_test, feature_cols) -> Dict[str, Any]:
    """Measure how much of the target each feature explains on its own.

    The existing leakage test masks rows recorded *after* the target timestamp
    (`booking_curve_validator.py`), so it cannot see a feature built from
    contemporaneous rows — it passes by construction. This one does not care
    when a row was recorded: it asks what a model given nothing but this one
    column can predict. A feature that is `target - something` answers loudly.

    Returned verbatim into each artifact's metadata, so the audit travels with
    the model and `load()` can refuse an artifact that carries no audit at all.
    """
    per_feature: Dict[str, Any] = {}
    for col in feature_cols:
        entry: Dict[str, Any] = {"single_feature_test_r2": None, "pearson_r": None}
        try:
            xtr = pd.to_numeric(X_train[col], errors="coerce")
            xte = pd.to_numeric(X_test[col], errors="coerce")
            if xtr.notna().sum() < MIN_TEST_ROWS or xtr.nunique(dropna=True) < 2:
                entry["skipped"] = "constant or too sparse to measure"
            else:
                probe = XGBRegressor(n_estimators=60, max_depth=3,
                                     random_state=42, objective="reg:squarederror")
                probe.fit(xtr.to_frame(), y_train)
                entry["single_feature_test_r2"] = round(
                    float(r2_score(y_test, probe.predict(xte.to_frame()))), 6)
                paired = pd.concat([xte, pd.Series(np.asarray(y_test),
                                                   index=xte.index)], axis=1).dropna()
                if len(paired) > 1 and paired.iloc[:, 0].nunique() > 1:
                    entry["pearson_r"] = round(
                        float(paired.iloc[:, 0].corr(paired.iloc[:, 1])), 6)
        except Exception as exc:            # a probe that cannot run is recorded, not swallowed
            entry["error"] = f"{type(exc).__name__}: {exc}"
        per_feature[col] = entry

    scored = {c: e["single_feature_test_r2"] for c, e in per_feature.items()
              if e.get("single_feature_test_r2") is not None}
    suspects = sorted((c for c, v in scored.items() if v >= SINGLE_FEATURE_R2_CEILING),
                      key=lambda c: -scored[c])
    return {
        "method": "single-feature XGBoost probe, depth 3, scored on the test fold",
        "ceiling": SINGLE_FEATURE_R2_CEILING,
        "features_probed": len(scored),
        "features_unprobed": sorted(set(per_feature) - set(scored)),
        "max_single_feature_test_r2": max(scored.values()) if scored else None,
        "suspect_features": suspects,
        "clean": not suspects,
        "per_feature": per_feature,
    }


# Declared features that are null on every path, by construction rather than by
# accident. `feature_metadata.py` says so in as many words — "Never computed: null
# on both paths" — for both of them: no generator computes a demand score or a
# seasonality factor, in training or at serving, and none ever has. They stay in
# `feature_cols` because the column order is the fitted models' input shape.
#
# They are named here so the coverage gate below can fire on the interesting case
# — a feature that is *supposed* to carry a value and does not — without being
# switched off wholesale by two that never could. Compute one and delete its entry;
# the gate then holds it to the same standard as every other feature.
STRUCTURALLY_UNCOMPUTED_FEATURES = frozenset({"demand_score", "seasonality_factor"})


def audit_feature_coverage(X_train, X_test, feature_cols) -> Dict[str, Any]:
    """How much of each feature is actually present in the fold being fitted.

    This exists because of `hour_of_day`. It is a declared feature; the serving
    path read the departure hour off the provider's segment and supplied it, while
    the training loader computed it from `recorded_at` — the hour the price was
    *observed* — off a column `price_history` did not have, so it was NaN for 100%
    of every training row. A model cannot learn from a column it never sees, and
    the request-time vector was populating it anyway. Nothing in the pipeline
    noticed, for eight months, because no check asked the simplest possible
    question about a feature: is it there?

    A feature at 0% coverage is one of three things — never computed, computed from
    a column the corpus lacks, or computed and thrown away — and all three mean the
    fitted model is narrower than its declared feature set. `zero_coverage` is
    therefore a gate criterion, not a log line. `single_value` is recorded but not
    gated: a genuinely constant feature (every row `is_live`, say) is useless to
    the model but not evidence of a broken derivation.
    """
    per_feature: Dict[str, Any] = {}
    rows_train = int(len(X_train))
    rows_test = int(len(X_test))
    for col in feature_cols:
        tr = pd.to_numeric(X_train[col], errors="coerce") if col in X_train else pd.Series(dtype=float)
        te = pd.to_numeric(X_test[col], errors="coerce") if col in X_test else pd.Series(dtype=float)
        present_train = int(tr.notna().sum())
        per_feature[col] = {
            "train_rows_present": present_train,
            "train_coverage": round(present_train / rows_train, 6) if rows_train else None,
            "test_rows_present": int(te.notna().sum()),
            "test_coverage": round(int(te.notna().sum()) / rows_test, 6) if rows_test else None,
            "distinct_values_train": int(tr.nunique(dropna=True)),
        }

    zero = sorted(c for c, e in per_feature.items() if e["train_rows_present"] == 0)
    single = sorted(c for c, e in per_feature.items()
                    if e["train_rows_present"] > 0 and e["distinct_values_train"] <= 1)
    unexpected = sorted(set(zero) - STRUCTURALLY_UNCOMPUTED_FEATURES)
    return {
        "method": "non-null count per declared feature over the fitted train/test folds",
        "train_rows": rows_train,
        "test_rows": rows_test,
        "features_declared": len(feature_cols),
        "zero_coverage_features": zero,
        "zero_coverage_unexpected": unexpected,
        "structurally_uncomputed": sorted(STRUCTURALLY_UNCOMPUTED_FEATURES),
        "single_value_features": single,
        "complete": not unexpected,
        "per_feature": per_feature,
    }


def baseline_skill(benchmark_result, *, model_mae: float,
                   baseline_name: str = "persistence") -> Dict[str, Any]:
    """Pull one named baseline out of a `BenchmarkResult` into a gate-shaped dict.

    A separate function from `evaluate_acceptance` so the gate stays a pure
    function over plain data, and a separate function from `ModelBenchmark` so
    "what is persistence" has exactly one definition — the one in
    `backend.ml.benchmark`, which is also what the promotion verdict uses. Reading
    it out of the result rather than recomputing it here is the point: a second
    implementation of the baseline is how the old `naive_persistence` came to be
    `np.mean(y_true)` in one file while meaning "carry the fare forward" in the
    prose of another.

    `available` is False when the baseline was skipped, and the reason travels with
    it. That distinction has to survive into the gate: "we compared and the model
    won" and "we could not compare" must not reduce to the same verdict, which is
    the mistake `MIN_TEST_R2 = 0.0` embodies — see `evaluate_acceptance`.
    """
    baselines = getattr(benchmark_result, "baselines", None) or []
    skipped = getattr(benchmark_result, "skipped_baselines", None) or []
    for baseline in baselines:
        if baseline.name != baseline_name:
            continue
        value = baseline.metrics.get("mae")
        if value is None or not math.isfinite(float(value)):
            return {"available": False, "name": baseline_name,
                    "reason": "baseline MAE is not finite over the scored rows"}
        value = float(value)
        return {
            "available": True,
            "name": baseline_name,
            "model_mae": float(model_mae) if math.isfinite(model_mae) else None,
            "baseline_mae": round(value, 6),
            # Signed, and relative to the baseline: positive means the model cut
            # the error the baseline made. Reported even when negative, because
            # "how much worse" is the number that says whether the feature set is
            # short of a fare level or the fit is simply untuned.
            "improvement_pct": (
                round((value - model_mae) / value, 6)
                if value > 0.0 and math.isfinite(model_mae) else None
            ),
        }
    reason = next((s.reason for s in skipped if s.name == baseline_name),
                  "baseline %r was neither computed nor skipped, which means the "
                  "benchmark never considered it" % baseline_name)
    return {"available": False, "name": baseline_name, "reason": reason}


def evaluate_acceptance(
    *,
    r2: float,
    mape: float,
    mape_rows: int,
    mape_excluded: int,
    test_rows: int,
    leak_audit: Dict[str, Any],
    coverage_audit: Dict[str, Any],
    baseline: Dict[str, Any],
) -> Dict[str, Any]:
    """Decide whether a fitted model may be served, and record why.

    A module-level function rather than a block inside `train()` for the same
    reason `_build_recommendation` was lifted out of `search_flights`: the gate
    used to be reachable only by standing up a database, a dataset builder and an
    XGBoost fit, so nothing exercised it, and the one test named after it asserted
    that 50 < 100 — a tautology over two literals the test wrote itself, which
    passed both before and after the gate was disabled by its own second conjunct.

    Every criterion is evaluated whatever the size of the dataset. The returned
    record is written into the artifact's metadata, so the terms a model was
    accepted under travel with it; `quality_gate_passed` is derived from this
    record rather than written as a literal.

    `leak_audit` is the dict from `audit_feature_leakage`. Only its `clean` key is
    read here, but the whole dict is recorded. `coverage_audit` is the dict from
    `audit_feature_coverage`, read and recorded the same way. `baseline` is the
    dict from `baseline_skill`, and it is required rather than defaulted: a gate
    that switches itself off when a caller omits an argument is the shape of the
    defect this function was extracted to fix.

    `MIN_TEST_R2 = 0.0` is kept, but it is the weaker of the two skill criteria and
    it is worth being precise about why. R²'s denominator *is* the sum of squares
    about `mean(y_true)`, so "R² ≥ 0" is arithmetically identical to "at least as
    good as predicting one constant, chosen with hindsight from the test labels".
    Nobody could have made that forecast, and a fare that barely moves makes it
    almost free. The baseline that a fare forecaster actually has to beat is on the
    screen the user is looking at: the fare right now, carried forward unchanged.
    `beats_the_last_known_fare` is that comparison, over exactly the rows the
    model was scored on.

    That the model may not have been *shown* the current fare does not soften the
    criterion. On the legacy 16-feature set it was not: the only fare-derived
    inputs are `price_change_1d` and `price_change_3d`, both differences, so
    nothing carries the fare's level and a fit cannot do better than learn the
    typical fare for a route and month. Persistence therefore holds strictly more
    information than the model — but the product's claim is "we predict where this
    fare is going", made to a user who can already see the fare. If assuming no
    change beats the model, that claim is false whatever the model was fed. The
    asymmetry is a defect in the feature set, not unfairness in the comparison, and
    the fix is the one `backend/ml/model_trainer.py` already takes: train on
    `feature_set_v1` with the observed fare among the features.
    """
    baseline_available = bool(baseline.get("available"))
    baseline_mae = baseline.get("baseline_mae")
    model_mae = baseline.get("model_mae")
    beats_baseline = bool(
        baseline_available
        and model_mae is not None and baseline_mae is not None
        and math.isfinite(float(model_mae)) and math.isfinite(float(baseline_mae))
        and float(model_mae) < float(baseline_mae)
    )
    criteria = [
        ("test_r2_at_or_above_floor",
         math.isfinite(r2) and r2 >= MIN_TEST_R2,
         {"observed": round(r2, 6) if math.isfinite(r2) else None,
          "threshold": MIN_TEST_R2}),
        # `math.isfinite` is spelled out rather than relying on `nan <= 35.0`
        # evaluating False. It does evaluate False, so the ceiling already failed
        # closed — but silently, and for a reason the record could not state:
        # `failed_criteria` would name a MAPE ceiling the model had never been
        # measured against. Separating the two means "we measured the error and it
        # was acceptable" and "we could not measure the error" cannot print as the
        # same verdict, and neither can print as the other's failure.
        ("test_mape_is_measurable",
         math.isfinite(mape),
         {"observed": int(mape_rows), "excluded": int(mape_excluded),
          "threshold": "at least one test row with a positive fare"}),
        ("test_mape_at_or_below_ceiling",
         math.isfinite(mape) and mape <= MAX_TEST_MAPE,
         {"observed": round(mape, 6) if math.isfinite(mape) else None,
          "threshold": MAX_TEST_MAPE}),
        ("test_fold_large_enough_to_measure",
         test_rows >= MIN_TEST_ROWS,
         {"observed": int(test_rows), "threshold": MIN_TEST_ROWS}),
        # Split from the criterion below for the same reason
        # `test_mape_is_measurable` is split from the ceiling: an unavailable
        # baseline must fail under its own name. Folded together, a run whose
        # last-known fare column was missing would print as a model that lost to
        # persistence, and the operator would go looking for a modelling problem.
        ("baseline_comparison_is_available",
         baseline_available,
         {"observed": baseline.get("name"),
          "reason": baseline.get("reason"),
          "threshold": "a last-known fare for every scored test row"}),
        ("beats_the_last_known_fare",
         beats_baseline,
         {"observed": model_mae, "baseline": baseline.get("name"),
          "improvement_pct": baseline.get("improvement_pct"),
          "threshold": baseline_mae}),
        ("no_single_feature_explains_the_target",
         bool(leak_audit.get("clean")),
         {"observed": leak_audit.get("suspect_features"),
          "threshold": SINGLE_FEATURE_R2_CEILING}),
        # The `hour_of_day` criterion. A feature at 0% coverage over the training
        # fold is one the model demonstrably did not learn from, and the serving
        # path builds its vector from the same declared list — so an artifact
        # accepted with an empty column is an artifact whose request-time input is
        # wider than its training input. The two features that are null by
        # construction are excluded by name in
        # `STRUCTURALLY_UNCOMPUTED_FEATURES`; everything else must be present.
        ("every_declared_feature_has_data",
         bool(coverage_audit.get("complete")),
         {"observed": coverage_audit.get("zero_coverage_unexpected"),
          "threshold": "no declared feature null for 100% of training rows"}),
    ]
    failures = [name for name, ok, _ in criteria if not ok]
    return {
        "passed": not failures,
        "failed_criteria": failures,
        "criteria": {name: dict(passed=ok, **detail)
                     for name, ok, detail in criteria},
        # The whole comparison, not just the two booleans derived from it, so an
        # artifact's metadata answers "better than what, by how much" without a
        # reader having to re-run the benchmark.
        "baseline": dict(baseline),
    }


def _group_overlap(train, test, group_cols):
    """How many booking curves the two folds share, and how much of the test fold sits on them.

    Reported, not eliminated. A booking curve spans weeks, so any time-ordered
    boundary cuts through curves that are live on both sides of it; assigning whole
    curves to one fold would destroy the chronology that makes the split honest in
    the first place. What the overlap costs is optimism, not a label leak: the
    model has seen earlier observations of the same flight, so a test score over
    shared curves is closer to interpolation than to forecasting a new flight.

    That distinction is only auditable if the number travels with the artifact.
    `test_row_fraction_in_shared_groups` near 1.0 means the test fold measures
    "how well does it continue curves it already knows"; near 0.0 means it
    measures "how well does it price a flight it has never seen". Both are
    legitimate questions, and the metadata used to say which one was answered.
    """
    if not group_cols:
        return None

    def keys(frame):
        if not len(frame):
            return pd.Series([], dtype=object)
        parts = []
        for col in group_cols:
            values = frame[col]
            parts.append(values.astype(str).str.strip().str.upper()
                         if values.dtype == object else values.astype(str))
        joined = parts[0]
        for part in parts[1:]:
            joined = joined + "|" + part
        return joined

    train_keys, test_keys = keys(train), keys(test)
    train_set, test_set = set(train_keys), set(test_keys)
    shared = train_set & test_set
    rows_in_shared = int(test_keys.isin(shared).sum()) if len(test_keys) else 0
    return {
        "group_columns": list(group_cols),
        "n_groups_train": len(train_set),
        "n_groups_test": len(test_set),
        "n_groups_shared": len(shared),
        "test_rows_in_shared_groups": rows_in_shared,
        "test_row_fraction_in_shared_groups": (
            round(rows_in_shared / len(test_keys), 6) if len(test_keys) else None
        ),
    }


def chronological_split(df, *, timestamp_col: str, train_fraction: float = 0.8,
                        embargo_days: float = 0.0, group_cols=None):
    """Split `df` into (train, test, record) in observation-time order, with an embargo.

    A module-level function for the same reason `evaluate_acceptance` is one: the
    split was eleven lines inside `train()`, reachable only by standing up a
    database, a dataset builder and an XGBoost fit, and the test named
    `test_chronological_split_ordering` therefore asserted the *string*
    `"Chronological_Temporal_Split"` out of a metadata file — under an
    `if os.path.exists(...)` that made it vacuous when the file was absent. The
    property that matters, that no training row was recorded after a test row,
    was never checked, and could not have been from outside this function.

    Sorting happens here rather than at the call site so a caller cannot obtain a
    positional split by forgetting it. That is the failure mode worth designing
    out: `iloc[:n]` on an unsorted frame is a random split wearing a
    chronological name, and it produces the same shapes, the same row counts and
    the same metadata string as the real thing.

    `embargo_days` is the purge, and it closes the hole `boundary_is_strict` could
    only report. Ordering by observation time keeps every *feature* in the training
    fold older than the test fold, but the training rows near the boundary are
    labelled by observations that had not happened yet at that boundary: the label
    for a row observed at `t` is a fare on the same curve at or after `t + h`,
    accepted within `lag_tolerance_days(h)`, so it is realised at up to
    `t + h + lag_tolerance_days(h)`. Train on that row and the fit has consumed a
    price recorded *inside the test period*. Passing
    `embargo_days = h + lag_tolerance_days(h)` drops every training row whose label
    could reach the test fold, so the surviving rows provably have their labels at
    or before `test_start`. Nothing about the frame reveals this — the leak is in
    the label's realisation time, which no column carries — which is why the
    default here is 0.0 and the caller that knows `h` supplies it.

    `record` reports the boundary rather than asserting it. `boundary_is_strict` is
    False when the last training row and the first test row share a timestamp;
    `embargo_is_effective` is the stronger statement, that the measured gap between
    the folds is at least the embargo asked for. `group_cols` adds a booking-curve
    overlap census — see `_group_overlap` for why it is reported and not removed.
    """
    if timestamp_col not in df.columns:
        raise KeyError(
            "chronological_split needs an observation-timestamp column; %r is not "
            "in %s" % (timestamp_col, list(df.columns)[:12])
        )
    embargo = max(0.0, float(embargo_days))
    ordered = df.sort_values(timestamp_col, kind="mergesort").reset_index(drop=True)
    n_total = len(ordered)
    n_train = int(n_total * train_fraction)
    train, test = ordered.iloc[:n_train], ordered.iloc[n_train:]

    train_end_raw = train[timestamp_col].max() if len(train) else None
    test_start = test[timestamp_col].min() if len(test) else None

    # The purge. Applied to the training fold only: dropping test rows would be
    # discarding the measurement rather than the contamination.
    cutoff = None
    n_train_before = int(len(train))
    if embargo > 0.0 and test_start is not None and n_train_before:
        cutoff = test_start - pd.Timedelta(days=embargo)
        train = train[train[timestamp_col] <= cutoff]

    train_end = train[timestamp_col].max() if len(train) else None
    gap_days = (
        float((test_start - train_end) / pd.Timedelta(days=1))
        if train_end is not None and test_start is not None else None
    )
    record = {
        "strategy": "chronological_by_observation_time_with_embargo"
                    if embargo > 0.0 else "chronological_by_observation_time",
        "timestamp_column": timestamp_col,
        "train_fraction": float(train_fraction),
        "embargo_days": embargo,
        "n_total": int(n_total),
        "n_train": int(len(train)),
        "n_train_before_embargo": n_train_before,
        "n_purged_by_embargo": n_train_before - int(len(train)),
        "n_test": int(len(test)),
        "train_end": str(train_end) if train_end is not None else None,
        "train_end_before_embargo": (
            str(train_end_raw) if train_end_raw is not None else None),
        "test_start": str(test_start) if test_start is not None else None,
        "embargo_cutoff": str(cutoff) if cutoff is not None else None,
        "gap_days": round(gap_days, 6) if gap_days is not None else None,
        "boundary_is_strict": bool(
            train_end is not None and test_start is not None and train_end < test_start
        ),
        # The claim worth auditing: the folds are separated by at least the width
        # asked for. False whenever the embargo was requested and the data could
        # not honour it — including when the purge emptied the training fold.
        "embargo_is_effective": bool(
            embargo > 0.0 and gap_days is not None and gap_days >= embargo
        ),
        "group_overlap": _group_overlap(train, test, group_cols),
    }
    return train, test, record


class PricePredictor:
    # The one feature set this class can consume, named once.
    #
    # `feature_cols` was sixteen string literals under the comment "DO NOT CHANGE
    # expected model columns shape". They were name-for-name and order-for-order
    # the contents of `feature_metadata.LEGACY_FEATURE_SET`, so deriving them is
    # not a behaviour change — it removes a second copy of the deployed contract
    # from the file that is furthest from the one documenting it. The list is the
    # input shape for training (`df_train[self.feature_cols]`) and for serving
    # (`df[self.feature_cols]`) alike, and `model_registry.expected_features`
    # returns it verbatim, so this list *was* the contract.
    #
    # Declaring the version is the substantive part. `FEATURE_SET_V1` declares 64
    # features of which only 7 are legacy names; nothing converts between the two
    # sets. A model fitted on these 16 therefore cannot be served a v1 vector, and
    # `predict()` reindexing one down to these names would silently NaN-fill the
    # 9 legacy names v1 does not declare — `days_until_dep`, `urgency`,
    # `day_of_week`, `month`, `week_of_year`, `hour_of_day`, `is_peak_hour`,
    # `demand_score`, `seasonality_factor`. That is not a degraded prediction, it
    # is a prediction with the booking horizon removed. `forecast()` was doing
    # exactly this on its normal path; see the comment there.
    #
    # `model_registry.feature_set_version` prefers the artifact's own metadata,
    # then this attribute, and only then infers from `len(expected_features) <= 16`.
    # Setting it here retires the inference, which its own docstring records as
    # having once been the only branch that ever ran.
    FEATURE_SET_VERSION = "legacy"

    # Names that belong to a declared feature set this predictor cannot eat. Used
    # by `predict()` to tell "the caller omitted a value it could not compute",
    # which is normal and arrives as NaN, from "the caller built a different
    # feature set", which is a wiring fault and must not be answered.
    FOREIGN_FEATURE_NAMES = frozenset(
        f.name for f in FEATURE_SET_V1
    ) - frozenset(f.name for f in LEGACY_FEATURE_SET)

    def __init__(self):
        self.feature_set_version = self.FEATURE_SET_VERSION
        self.feature_cols = [f.name for f in LEGACY_FEATURE_SET]

        self.models = {}  # {horizon: XGBRegressor}
        # One label-encoding map per horizon. `self.encoders` used to be the only
        # store, assigned inside the training loop and again inside the load loop,
        # so whichever horizon ran last overwrote every other horizon's mapping.
        # The maps genuinely differ — each is built from the unique values
        # surviving that horizon's shift and row filters — so serving horizon 1
        # with horizon 30's mapping feeds the model an integer that stands for a
        # different airline than the one it was trained to associate with it. The
        # codes are silently wrong, never absent, which is why nothing caught it.
        self.encoders_by_horizon: Dict[int, dict] = {}
        # Kept as the primary horizon's mapping, for the legacy single-model path
        # and for callers that predate the per-horizon store.
        self.encoders = {}
        self.metrics = {}
        self.metadata = {}  # {horizon: dict}
        # Horizons whose artifact was found on disk and rejected, with the reason.
        # Published by the /system endpoints so a refusal is visible rather than
        # looking like the model was simply never trained.
        self.refused_artifacts: List[str] = []
        # Why the last `load()` attempt did not produce a model, or None if none
        # has failed. `get_predictor` records it here instead of reacting to a
        # failed load by training a replacement; see that function.
        self.load_error: Optional[str] = None
        # Horizon 0 is absent deliberately, and its absence is load-bearing.
        # `target_price` at horizon 0 is the observation's own price, so a model
        # "trained" on it fits an identity and reports an r² that measures the
        # join. `booking_curve_definition.MIN_TRAINABLE_HORIZON_DAYS` is the one
        # place that rule is stated; `attach_future_target` raises if this list
        # ever grows a 0 again, rather than quietly training on the identity.
        # The present-day point is served as the observed fare by
        # `forecast/timeline_builder.py`, which is an observation, not a
        # prediction, and is published with no confidence figure.
        #
        # Read from `SUPPORTED_TRAINING_HORIZONS` rather than written as `[1, 3,
        # 7]` here, because `backend/dataset/doctor.py` has to grade a corpus
        # against these same horizons and a second copy of the list would let the
        # diagnostic pass a corpus for horizons the trainer does not train.
        from backend.services.booking_curve_definition import (
            SUPPORTED_TRAINING_HORIZONS,
        )
        self.supported_horizons = list(SUPPORTED_TRAINING_HORIZONS)
        # `dataset_size` used to be set only at the one point in train() that
        # sees a non-empty raw frame, so on a run where the quality policy
        # rejected every horizon the attribute never existed and train()'s own
        # report raised AttributeError while building itself. None means no run
        # has counted observations yet; 0 means a run counted none.
        self.dataset_size = None
        # None until a real training run or a real metadata file supplies one.
        self.training_timestamp = None
        self._trained = False
        self._last_loaded_time: float = 0.0
        self.supports_forecasting = True
        self.legacy_mode = False
        # Which horizon the legacy `global_model.pkl` predicts, read from the
        # pickle's own `"horizon"` key. None means the artifact does not say —
        # every pickle written before `train()` started recording it. `predict()`
        # refuses a horizon that disagrees; a pickle that names no horizon cannot
        # be checked, which is itself the reason to retrain.
        self.legacy_horizon: Optional[int] = None
        # The routes each horizon's artifact was actually fitted on, read from the
        # artifact's own `trained_routes` key. Empty for a horizon whose artifact
        # predates the key — which is the honest answer, and the reason
        # `model_registry.supported_routes` no longer returns a literal.
        self.trained_routes_by_horizon: Dict[int, List[str]] = {}
        # A hand-maintained version of the training/serving code contract — not an
        # identity for the artifact this instance loaded or wrote. Nothing in
        # `train()` changes it, so two artifacts fitted a month apart on different
        # corpora both record "2.0.0", and it is stated here rather than left
        # implied because a field named `model_version` reads like the opposite.
        # The fields that do distinguish artifacts are `dataset_version`,
        # `dataset_hash` and `training_timestamp`, all written into each horizon's
        # metadata alongside this and all read back from it by `model_registry`.
        self.model_version = "2.0.0"
        self.feature_schema_version = "2.0.0"
        # What the label actually is, stated in the terms `attach_future_target`
        # computes it in. This read "Future Lowest Fare", which described neither
        # production path: the dataset builder kept the first observation of the
        # target day and `_build_shifted_dataset` took that day's minimum, so the
        # published description of the target matched one dead code path.
        self.training_target = (
            "Fare on the same booking curve at the earliest observation on or "
            "after t + horizon days, within tolerance"
        )

    def _build_shifted_dataset(self, df: pd.DataFrame, horizon: int) -> pd.DataFrame:
        """Attach the supervised label for `horizon` days ahead.

        A thin wrapper over `booking_curve_definition.attach_future_target`, which
        is also what `training_dataset_builder.build` calls. It is thin on purpose:
        this method used to contain a second, independently written target join
        that grouped to each day's minimum fare over four keys, and it was the
        only one of the two that any test exercised — including
        `test_target_leakage.py`, the test named after the defect. Delegating
        means those tests now measure the join the model is actually trained on.
        """
        from backend.services.booking_curve_definition import attach_future_target
        return attach_future_target(df, horizon)

    # ── Train ─────────────────────────────────────────────────────────
    def train(self) -> Dict[str, Any]:
        """Trains independent XGBoost models per prediction horizon if dataset quality policy passes.

        Returns a report of what actually happened: which horizons were trained and
        which the quality gate rejected. The method used to return None and set
        `self._trained = True` unconditionally at the end, so a run in which the gate
        rejected *every* horizon — training nothing and writing no model file — left
        the predictor claiming to be trained, and the scheduler logged "Model
        retrained successfully." No caller depends on the old None return.
        """
        from backend.services.training_dataset_builder import training_dataset_builder
        from backend.services.dataset_quality_validator import dataset_quality_validator

        logger.info("Starting Training Dataset Compilation...")

        trained_horizons: List[int] = []
        rejected: Dict[int, str] = {}
        # Largest raw observation count this run saw, across horizons. Assigned
        # to self.dataset_size after the loop so that a run which found nothing
        # records 0 rather than silently keeping a stale earlier figure.
        observed = 0
        # The timeline leakage audit is a property of the raw corpus and the
        # feature pipeline, both of which are the same for every horizon — the
        # horizon only decides which future observation becomes the label. So it
        # runs at most once per train() call, and its verdict applies to all of
        # them. None means "not attempted yet"; see `_timeline_audit` below.
        timeline_audit: Optional[Dict[str, Any]] = None
        # Same reasoning, same scope: whose observations a curve feature is allowed
        # to see is a property of the pipeline and the corpus, not of the horizon.
        isolation_audit: Optional[Dict[str, Any]] = None
        # This one is per horizon, and recorded per horizon, because it is a
        # property of the *label*: a feature that is innocent against a fare seven
        # days out can be the fare itself at horizon 0.
        label_audits: Dict[int, Dict[str, Any]] = {}

        # The builder engineers features to whatever set `model_registry`
        # advertises, and this class can only fit the one it declares. If those
        # disagree, `df_train[self.feature_cols]` below raises `KeyError` listing
        # nine names with no indication of why they are absent — after every
        # leakage audit has run over a full corpus. Say it once, up front, in the
        # vocabulary of the actual fault.
        from backend.services.model_registry import model_registry as _fs_registry
        builder_fs_version = _fs_registry.feature_set_version
        if builder_fs_version != self.feature_set_version:
            raise PredictionUnavailable(
                f"Refusing to train: the model registry advertises feature set "
                f"{builder_fs_version!r}, so `training_dataset_builder` will engineer "
                f"that set, but {type(self).__name__} fits "
                f"{self.feature_set_version!r} ({len(self.feature_cols)} columns) and "
                f"nothing converts between them. Either retrain against "
                f"{self.feature_set_version!r} or give this class a feature_cols list "
                f"that follows the deployed version."
            )

        for h in self.supported_horizons:
            # 1. Build training dataset via TrainingDatasetBuilder
            df_raw, df_shifted = training_dataset_builder.build(h)
            observed = max(observed, 0 if df_raw.empty else len(df_raw))

            # 2. Validate using DatasetQualityValidator
            report = dataset_quality_validator.validate(df_raw, df_shifted)

            # 3. Policy checks: skip training if validation fails
            if not report.passed:
                rejected[h] = (
                    f"observations={report.observation_count}, shifted_rows={report.shifted_rows}"
                )
                logger.warning(
                    f"Skipping training for horizon {h}d due to dataset quality policy rejection. "
                    f"Observation count: {report.observation_count}, Shifted rows: {report.shifted_rows}. "
                    f"Retaining previous validated model if available."
                )
                continue

            # 2b. Timeline leakage audit, on the raw corpus, before anything is
            #     fitted. `validate_target_leakage` rebuilds the feature frame from
            #     a corpus truncated at an observation's own timestamp and requires
            #     every numeric feature of that observation to be unchanged; a
            #     feature that moves saw something recorded later. It had no
            #     production caller at all — only an operator script and a test —
            #     so the check that would have caught the whole-corpus
            #     `groupby(route).transform("mean")` aggregates ran on nobody's
            #     machine during a training run.
            #
            #     A dirty or unrun verdict rejects *every* horizon rather than this
            #     one: a leaking feature build is a property of the pipeline, and a
            #     model trained on it is not salvageable by changing the label's
            #     offset. `timeline_leak_verdict` derives `ran` from the number of
            #     values actually compared, so the PASS a corpus with no
            #     multi-observation curve produces cannot be mistaken for clean.
            if timeline_audit is None:
                from backend.ml.booking_curve_validator import timeline_leak_verdict
                from backend.services.model_registry import model_registry
                timeline_audit = timeline_leak_verdict(
                    df_raw, model_registry.feature_set_version)
            if not timeline_audit["clean"]:
                reason = (
                    "timeline leakage audit did not run (%s of %s curves testable, "
                    "%d values compared)" % (
                        timeline_audit["groups_tested"],
                        timeline_audit["raw_observations"],
                        timeline_audit["values_compared"])
                    if not timeline_audit["ran"] else
                    "timeline leakage audit %s: %s" % (
                        timeline_audit["status"],
                        "; ".join(timeline_audit["errors"]) or "no detail recorded")
                )
                rejected[h] = reason
                logger.error(
                    "Horizon %dd: refusing to train. %s. Feature set %r, ordering "
                    "column %r, %d values compared across %d curves. No artifact "
                    "written; any previously validated model is retained.",
                    h, reason, timeline_audit["feature_set_version"],
                    timeline_audit["ordering_column"],
                    timeline_audit["values_compared"],
                    timeline_audit["groups_tested"],
                )
                continue

            # 2c. Contemporaneous leakage, which the timeline audit above cannot
            #     see at all. It masks the observations recorded *after* a row's own
            #     timestamp, so a row recorded at the *same* instant survives every
            #     mask it builds and every feature reading one is reported clean.
            #
            #     Two checks cover that class from opposite ends. `curve_isolation`
            #     asks whose observations a feature may see: remove the simultaneous
            #     observations of *other* curves on the same route and every feature
            #     not declared cross-sectional must be unchanged. That is the
            #     four-key join defect — one flight's features paired with another
            #     flight's history — stated as a check, and no timeline mask can
            #     detect it. `label_independence` asks what the features know about
            #     the label: no feature may be an affine function of it, which is
            #     what `target_price = price` at horizon 0 made every price feature.
            #
            #     Both refuse rather than warn, and the isolation verdict refuses
            #     every horizon for the same reason the timeline one does. Both
            #     derive `ran` from what they actually measured, so a corpus with no
            #     two simultaneous curves, or a frame carrying no engineered
            #     feature, cannot buy a clean verdict by being uninformative.
            if isolation_audit is None:
                from backend.ml.booking_curve_validator import curve_isolation_verdict
                from backend.services.model_registry import model_registry
                isolation_audit = curve_isolation_verdict(
                    df_raw, model_registry.feature_set_version)
            if not isolation_audit["clean"]:
                reason = (
                    "curve isolation audit did not run (%d case(s), %d values, %d "
                    "populated)" % (
                        isolation_audit["cases_tested"],
                        isolation_audit["values_compared"],
                        isolation_audit["populated_compared"])
                    if not isolation_audit["ran"] else
                    "curve isolation audit %s: %s" % (
                        isolation_audit["status"],
                        "; ".join(isolation_audit["errors"]) or "no detail recorded")
                )
                rejected[h] = reason
                logger.error(
                    "Horizon %dd: refusing to train. %s. %d of %d candidate cases "
                    "tested, %d curve-keyed values compared, %d error(s) in total. "
                    "No artifact written; any previously validated model is "
                    "retained.",
                    h, reason, isolation_audit["cases_tested"],
                    isolation_audit["cases_available"],
                    isolation_audit["values_compared"],
                    isolation_audit["error_count"],
                )
                continue

            from backend.ml.booking_curve_validator import label_independence_verdict
            from backend.services.model_registry import model_registry as _registry
            label_audit = label_independence_verdict(
                df_shifted, _registry.feature_set_version, h)
            label_audits[h] = label_audit
            if not label_audit["clean"]:
                reason = (
                    "label independence audit did not run (%d feature(s) probed, "
                    "%d of %d declared features measurable)" % (
                        label_audit["features_probed"],
                        label_audit["declared_scored"],
                        label_audit["declared_probeable"])
                    if not label_audit["ran"] else
                    "label independence audit %s: %s" % (
                        label_audit["status"],
                        "; ".join(label_audit["errors"]) or "no detail recorded")
                )
                rejected[h] = reason
                logger.error(
                    "Horizon %dd: refusing to train. %s. %d labelled rows, max r2 "
                    "against the label %s (limit %s), affine features %s, label "
                    "copies %s. No artifact written.",
                    h, reason, label_audit["rows_labelled"], label_audit["max_r2"],
                    label_audit["error_ceiling"], label_audit["affine_features"],
                    label_audit["label_copies"],
                )
                continue

            logger.info(
                "Training horizon %dd model with %d shifted observations. Audits: "
                "timeline %s, curve isolation %s (%d values), label independence "
                "%s (max r2 %s over %d features).",
                h, len(df_shifted), timeline_audit["status"],
                isolation_audit["status"], isolation_audit["values_compared"],
                label_audit["status"], label_audit["max_r2"],
                label_audit["features_probed"],
            )

            df_horizon = df_shifted.copy()

            # Was `.map({2.0: True, 1.0: False, True: True, False: False})`,
            # decoding the 2.0/1.0 encoding `database._engineer_features` used to
            # apply. Two problems, both now gone.
            #
            # The dict collapsed: `1.0 == True` and they hash equal, so the third
            # entry overwrote the second and the literal was really
            # `{2.0: True, 1.0: True, False: False}` — 1.0, the not-live
            # encoding, decoded to True. Its counterpart in `_engineer_features`
            # collapsed the other way and mapped every boolean to 1.0, so live and
            # not-live rows both arrived here and both came out True. The round
            # trip agreed with the serving path only because two collisions
            # cancelled.
            #
            # There is nothing to decode now: the loader hands over a boolean and
            # the shared reader is the same one it used, so training and serving
            # cannot disagree about what a value in this column means.
            if LIVE_KEY in df_horizon.columns:
                df_horizon[LIVE_KEY] = df_horizon[LIVE_KEY].map(decode_flag).eq(True)
            else:
                df_horizon[LIVE_KEY] = False

            defaults = {
                "day_of_week": np.nan, "month": np.nan, "week_of_year": np.nan,
                "hour_of_day": np.nan, "is_peak_hour": np.nan, "seats_available": np.nan,
                "price_change_1d": np.nan, "price_change_3d": np.nan,
                "demand_score": np.nan, "seasonality_factor": np.nan,
            }
            for col, val in defaults.items():
                if col not in df_horizon.columns:
                    df_horizon[col] = val

            # The route of each row, kept as a string so that after every row
            # filter below the artifact can record which routes it was actually
            # fitted on. `model_registry.supported_routes` returned the literal
            # `["DEL-BOM", "BOM-DEL"]` no matter what the artifact had seen, so
            # `/capabilities` advertised two routes that may never have been trained
            # and concealed every route that was. Computed before the label
            # encoding below replaces these strings with integers.
            df_horizon["_route_str"] = (
                df_horizon["origin_code"].astype(str).str.strip().str.upper()
                + "-"
                + df_horizon["destination_code"].astype(str).str.strip().str.upper()
            )

            # Label Encoding. Codes start at 1 so 0 is reserved for a value this
            # horizon never saw; `_encode_category` returns 0 at serve time for
            # exactly that case. Held per horizon — see the note in __init__.
            encoders = {}
            for col in ("origin_code", "destination_code", "airline_code"):
                df_horizon[col] = df_horizon[col].astype(str).str.upper()
                unique_vals = sorted(df_horizon[col].unique())
                encoders[col] = {v: i + 1 for i, v in enumerate(unique_vals)}
                df_horizon[col] = df_horizon[col].map(encoders[col]).fillna(0).astype(int)
            self.encoders_by_horizon[h] = encoders

            df_horizon = df_horizon[df_horizon["target_price"].notna() & np.isfinite(df_horizon["target_price"])]
            MIN_OBSERVATIONS_THRESHOLD = 100
            if len(df_horizon) < MIN_OBSERVATIONS_THRESHOLD:
                logger.warning(
                    f"Quality Gate Rejection for Horizon {h}d: Insufficient observations ({len(df_horizon)} < {MIN_OBSERVATIONS_THRESHOLD}). Retaining previous validated model."
                )
                continue

            # 1. Chronological (Time-Series) Split, ordered by the observation
            #    timestamp the shared resolver names. Re-deriving the preference
            #    order inline is how the split and the feature lags came to sort
            #    on different columns; `ordering_timestamps` also normalises to
            #    UTC, so a mixed tz-aware/naive frame cannot silently sort by
            #    string order here.
            from backend.services.booking_curve_definition import (
                curve_group_columns, lag_tolerance_days, ordering_timestamps,
                resolve_ordering_timestamp_column,
            )
            ts_col = resolve_ordering_timestamp_column(df_horizon)
            if ts_col is None:
                logger.error(
                    "Horizon %dd: no observation timestamp column, so a "
                    "chronological split is not possible and a positional one "
                    "would be a random split wearing its name. Skipping.", h,
                )
                rejected[h] = "no observation timestamp column for a chronological split"
                continue
            df_horizon["_recorded_dt"] = ordering_timestamps(df_horizon)
            df_horizon = df_horizon[df_horizon["_recorded_dt"].notna()]
            if len(df_horizon) < MIN_OBSERVATIONS_THRESHOLD:
                logger.warning(
                    "Horizon %dd: %d rows left after dropping unparseable "
                    "observation timestamps (< %d). Skipping.",
                    h, len(df_horizon), MIN_OBSERVATIONS_THRESHOLD,
                )
                rejected[h] = f"only {len(df_horizon)} rows with a parseable observation timestamp"
                continue

            # The sort lives inside `chronological_split` so that this call site
            # cannot produce a positional split by omitting it. `split_record`
            # carries the fold boundary into the artifact's metadata, replacing a
            # hardcoded `"split_strategy"` string that was true of any split.
            #
            # The embargo width is the label's realisation time, not the horizon.
            # `attach_future_target` labels a row observed at `t` with a fare on the
            # same curve at or after `t + h`, accepted within `lag_tolerance_days(h)`
            # — so the latest observation that can define the label sits at
            # `t + h + lag_tolerance_days(h)`. Purging exactly that width means every
            # surviving training row's label was already realised at `test_start`,
            # and the fit therefore consumed no price recorded during the test
            # period. Ordering alone did not give this: the boundary training rows'
            # *features* were older than the test fold while their *labels* were not.
            embargo_days = float(h) + lag_tolerance_days(h)
            df_train, df_test, split_record = chronological_split(
                df_horizon, timestamp_col="_recorded_dt", train_fraction=0.8,
                embargo_days=embargo_days,
                group_cols=curve_group_columns(df_horizon))
            n_train = split_record["n_train"]
            if not split_record["boundary_is_strict"]:
                logger.warning(
                    "Horizon %dd: the last training row and the first test row "
                    "share an observation timestamp (%s), so the folds are "
                    "adjacent rather than separated even after a %.1fd embargo. "
                    "Recorded in the artifact's split_record.",
                    h, split_record["train_end"], embargo_days,
                )
            # The purge takes rows out of the training fold, so the 100-row corpus
            # gate above no longer bounds it. A fold this small produces a fit whose
            # test score is noise, and the honest response is the same one every
            # other insufficiency gets here: keep the previous model.
            if n_train < MIN_OBSERVATIONS_THRESHOLD:
                logger.warning(
                    "Horizon %dd: %d training row(s) left after the %.1fd embargo "
                    "purged %d of %d (< %d). Retaining the previous validated "
                    "model; no artifact written.",
                    h, n_train, embargo_days,
                    split_record["n_purged_by_embargo"],
                    split_record["n_train_before_embargo"],
                    MIN_OBSERVATIONS_THRESHOLD,
                )
                rejected[h] = (
                    "only %d training row(s) after a %.1f day label embargo"
                    % (n_train, embargo_days)
                )
                continue
            # The gate above is the one that fires when the purge is too wide for the
            # corpus. This one is the backstop for the cases it cannot see: an empty
            # test fold leaves nothing to embargo against, so no cutoff is computed
            # and the training fold survives intact. A fold pair with no measured
            # separation must not be scored as though it had one.
            if not split_record["embargo_is_effective"]:
                logger.error(
                    "Horizon %dd: the %.1fd label embargo did not take effect — "
                    "measured gap between the folds is %s day(s) over %d training "
                    "and %d test row(s). Refusing to train: a model fitted across "
                    "this boundary has consumed labels realised inside its own test "
                    "period, and its test score would be measuring that.",
                    h, embargo_days, split_record["gap_days"], n_train,
                    split_record["n_test"],
                )
                rejected[h] = (
                    "label embargo of %.1f day(s) not effective: measured fold gap "
                    "%s day(s)" % (embargo_days, split_record["gap_days"])
                )
                continue
            overlap = split_record["group_overlap"]
            if overlap:
                logger.info(
                    "Horizon %dd split: %d train / %d test rows, %.1fd embargo "
                    "purged %d, fold gap %s day(s). Booking-curve overlap: %d of "
                    "%d test curves also appear in training, covering %.1f%% of "
                    "test rows.",
                    h, n_train, split_record["n_test"], embargo_days,
                    split_record["n_purged_by_embargo"], split_record["gap_days"],
                    overlap["n_groups_shared"], overlap["n_groups_test"],
                    100.0 * (overlap["test_row_fraction_in_shared_groups"] or 0.0),
                )

            X_train = df_train[self.feature_cols]
            y_train = df_train["target_price"]
            X_test = df_test[self.feature_cols]
            y_test = df_test["target_price"]

            w_train_series = df_train["training_weight"] if "training_weight" in df_train.columns else pd.Series(1.0, index=df_train.index)
            w = pd.to_numeric(w_train_series, errors="coerce").fillna(1.0)
            raw_w = np.nan_to_num(w.values, nan=1.0)
            final_weights = np.maximum(raw_w, 0.01)

            # Hyperparameters are a named dict rather than inline literals so the
            # values that produced an artifact can be recorded into its metadata.
            # Reproducing a run used to require reading this function.
            hyperparameters = {
                "n_estimators": 900,
                "learning_rate": 0.04,
                "max_depth": 9,
                "subsample": 0.9,
                "colsample_bytree": 0.9,
                "random_state": 42,
                "objective": "reg:squarederror",
            }
            model = XGBRegressor(**hyperparameters)
            model.fit(X_train, y_train, sample_weight=final_weights)

            # 2. Evaluation on Unseen Chronological Test Fold
            preds = model.predict(X_test)
            mae = float(mean_absolute_error(y_test, preds))
            rmse = float(np.sqrt(mean_squared_error(y_test, preds)))
            r2 = float(r2_score(y_test, preds)) if len(y_test) > 1 else 0.0
            # MAPE comes from `backend.ml.metrics`, which is where every other
            # evaluation path in the repo gets it. This line used to re-derive it
            # inline as `... / np.maximum(y_test.values, 1)`, a second definition
            # of the published metric that substituted a ₹1 denominator for any
            # non-positive actual instead of excluding the row. `mape_rows_used`
            # travels with the figure so a MAPE over a handful of rows cannot be
            # mistaken for one over the fold.
            from backend.ml.metrics import mape_with_coverage
            mape, mape_rows, mape_excluded = mape_with_coverage(y_test.values, preds)
            # None, not 0.0. `max(0.0, 100.0 - nan)` returns 0.0 in Python, which
            # would publish "0% accurate" for a model whose error could not be
            # measured at all — the same conflation of unmeasured with measured-bad
            # that the confidence work removed from every other published figure.
            eq_accuracy = (
                float(max(0.0, 100.0 - mape)) if math.isfinite(mape) else None
            )

            # 3. Acceptance gate. The criteria live in `evaluate_acceptance` at
            # module level so they can be exercised without a provider, a database
            # or an XGBoost fit; its docstring records why that matters.
            #
            # The baseline comes first because one of the criteria is a comparison
            # against it. `price` is the fare already observed for the row — the
            # number on the user's screen — and it is deliberately *not* in
            # `self.feature_cols`: the legacy set carries only `price_change_1d`
            # and `price_change_3d`, two differences, so the model never sees the
            # fare's level. Carrying that level forward unchanged is the forecast
            # the product is claiming to beat, and until now nothing measured it.
            # `y_train` supplies the second baseline; both are passed explicitly
            # because a benchmark that reached into the test fold for either would
            # be scoring an oracle, which is what the two deleted baselines did.
            from backend.ml.benchmark import model_benchmark
            benchmark_result = model_benchmark.run(
                y_test.values, preds,
                y_last_known=(df_test["price"] if "price" in df_test.columns
                              else None),
                y_train=y_train.values,
                feature_set_version=self.feature_set_version,
            )
            baseline = baseline_skill(benchmark_result, model_mae=mae)
            leak_audit = audit_feature_leakage(
                X_train, y_train, X_test, y_test, self.feature_cols)
            coverage_audit = audit_feature_coverage(
                X_train, X_test, self.feature_cols)
            if coverage_audit["zero_coverage_features"]:
                logger.error(
                    "Horizon %dd: %d declared feature(s) are null for 100%% of the "
                    "%d training rows — %s. Of those, %s are not on the "
                    "structurally-uncomputed list and fail the acceptance gate.",
                    h, len(coverage_audit["zero_coverage_features"]),
                    coverage_audit["train_rows"],
                    ", ".join(coverage_audit["zero_coverage_features"]),
                    ", ".join(coverage_audit["zero_coverage_unexpected"]) or "none",
                )
            gate_record = evaluate_acceptance(
                r2=r2, mape=mape, mape_rows=mape_rows,
                mape_excluded=mape_excluded, test_rows=len(y_test),
                leak_audit=leak_audit,
                coverage_audit=coverage_audit,
                baseline=baseline,
            )
            gate_failures = gate_record["failed_criteria"]

            if gate_failures:
                rejected[h] = "quality gate: " + ", ".join(gate_failures)
                logger.warning(
                    "Quality gate REJECTED horizon %dd on %s — R²=%.4f (floor %.2f), "
                    "MAPE=%s (ceiling %.2f), test rows=%d (floor %d), MAE ₹%.0f vs "
                    "last-known-fare baseline %s, leak suspects=%s, "
                    "empty features=%s. Retaining the previously validated model for "
                    "this horizon; no artifact written.",
                    h, ", ".join(gate_failures), r2, MIN_TEST_R2,
                    ("%.2f%% over %d rows" % (mape, mape_rows))
                    if math.isfinite(mape) else "not measurable",
                    MAX_TEST_MAPE, len(y_test), MIN_TEST_ROWS, mae,
                    ("₹%.0f" % baseline["baseline_mae"]) if baseline["available"]
                    else "unavailable (%s)" % baseline.get("reason"),
                    leak_audit["suspect_features"] or "none",
                    coverage_audit["zero_coverage_unexpected"] or "none",
                )
                continue

            self.models[h] = model

            # Calculate residual statistics
            residuals = y_test.values - preds
            res_list = residuals.tolist()
            fi = model.feature_importances_
            feature_importance_dict = {col: float(val) for col, val in sorted(zip(self.feature_cols, fi), key=lambda x: x[1], reverse=True)}

            pred_vs_actual_sample = [
                {
                    "actual_price": float(y_test.iloc[i]),
                    "predicted_price": float(preds[i]),
                    "residual": float(res_list[i])
                }
                for i in range(min(5, len(y_test)))
            ]

            self.metrics[h] = {
                "mae": float(mae),
                "rmse": float(rmse),
                "r2": float(r2),
                "mape": float(mape),
                # How much of the test fold the MAPE is a percentage over. A
                # figure computed on a handful of rows and one computed on the
                # whole fold are different claims.
                "mape_rows_used": int(mape_rows),
                "mape_rows_excluded": int(mape_excluded),
                # `100 - MAPE`, under the name that says so. There used to be a
                # second key, `"accuracy": eq_accuracy / 100.0`, carrying the same
                # quantity under a name that claims something else: there is no
                # accuracy for a regression, and the quarantined 1d artifact is
                # what that costs — its metadata holds `"accuracy": 0.9864` beside
                # `"r2": 0.4248`, so a reader who takes the short key at face value
                # reports "98.6% accurate" for a model explaining under half the
                # variance. Both former readers of it are now commented out in
                # favour of `confidence_policy.resolve_published_accuracy`, which
                # reads the long name first; the short one survives in that
                # resolver only to keep pre-existing pickles readable, and is no
                # longer written by this path.
                "equivalent_accuracy_100_minus_mape": eq_accuracy,
                # Was a literal 900 next to a hyperparameter dict that also said
                # 900, so tuning one would have left the recorded metrics
                # describing a model that was never fitted.
                "estimators": hyperparameters["n_estimators"],
                "training_samples": n_train,
                "test_samples": len(X_test)
            }

            logger.info(
                "Horizon %dd Model performance (Chronological Split) — MAE: ₹%.0f  "
                "RMSE: ₹%.0f  R²: %.4f  Equivalent Accuracy (100-MAPE): %s",
                h, mae, rmse, r2,
                ("%.1f%% over %d of %d test rows" % (eq_accuracy, mape_rows,
                                                     mape_rows + mape_excluded))
                if eq_accuracy is not None else "not measurable",
            )

            # The routes surviving every row filter above — the ones this model was
            # genuinely fitted on. Read back by `load()` onto
            # `trained_routes_by_horizon`, which is what `/capabilities` now reports.
            trained_routes = sorted(
                set(df_horizon["_route_str"].dropna().astype(str))
            ) if "_route_str" in df_horizon.columns else []
            self.trained_routes_by_horizon[h] = trained_routes

            # Save individual model pkl file
            path_pkl = os.path.join(BASE_ML_DIR, "models", f"fare_forecast_{h}d.pkl")
            os.makedirs(os.path.dirname(path_pkl), exist_ok=True)
            with open(path_pkl, "wb") as fh:
                pickle.dump({"model": model, "encoders": encoders,
                             "horizon": h, "trained_routes": trained_routes}, fh)

            # Save rich metadata evaluation artifact
            dataset_version = f"DS_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            dataset_hash = hashlib.md5(pd.util.hash_pandas_object(df_horizon, index=True).values).hexdigest()
            # Also kept on the instance. Callers did `getattr(predictor,
            # "training_timestamp", "2026-07-20T12:00:00Z")` — an attribute no
            # code ever assigned — so the /system endpoints published that fixed
            # date as the training time of every model, trained or not.
            self.training_timestamp = datetime.now(timezone.utc).isoformat()
            metadata = {
                "model_version": self.model_version,
                "dataset_version": dataset_version,
                "dataset_hash": dataset_hash,
                "training_timestamp": self.training_timestamp,
                "prediction_horizon": h,
                # The routes actually present in this horizon's fitted frame, after
                # every row filter. `/capabilities` reported a two-route literal
                # before this existed.
                "trained_routes": trained_routes,
                # Read out of the record rather than typed. The literal here was
                # `"Chronological_Temporal_Split"`, which was true of a positional
                # split on an unsorted frame and stayed true after the embargo was
                # added — a name that cannot become wrong describes nothing. The
                # record's own `strategy` changes when the split changes.
                "split_strategy": split_record["strategy"],
                # What the string above claims, as measured: the fold sizes, the
                # timestamp column the order came from, the boundary timestamps, the
                # embargo width and how many rows it purged, the measured gap between
                # the folds, and the booking-curve overlap between them. The string
                # alone was true of a positional split on an unsorted frame.
                "split_record": split_record,
                "observation_count": len(df_horizon),
                "train_size": len(X_train),
                "test_size": len(X_test),
                "evaluation_metrics": self.metrics[h],
                "residual_statistics": {
                    "mean_residual_bias": float(np.mean(residuals)),
                    "median_residual": float(np.median(residuals)),
                    "std_residual": float(np.std(residuals)),
                    "max_positive_error": float(np.max(residuals)),
                    "max_negative_error": float(np.min(residuals)),
                    "worst_abs_error": float(np.max(np.abs(residuals))),
                    # What `forecast()` builds its published interval from. Signed
                    # percentiles of `actual - predicted` on this horizon's test
                    # fold, so `predicted + p10 … predicted + p90` is an empirical
                    # 80% interval for the actual fare and inherits the fold's
                    # skew and bias instead of assuming symmetry. Recorded with the
                    # sample size, because an interval read off eleven residuals
                    # and one read off eleven hundred are different claims and
                    # `MIN_RESIDUALS_FOR_INTERVAL` is enforced against this number.
                    "residual_sample_size": int(len(residuals)),
                    "residual_quantiles": {
                        "p10": float(np.percentile(
                            residuals, RESIDUAL_INTERVAL_LOWER_PERCENTILE)),
                        "p50": float(np.percentile(residuals, 50.0)),
                        "p90": float(np.percentile(
                            residuals, RESIDUAL_INTERVAL_UPPER_PERCENTILE)),
                    },
                    "residual_quantile_percentiles": {
                        "lower": RESIDUAL_INTERVAL_LOWER_PERCENTILE,
                        "upper": RESIDUAL_INTERVAL_UPPER_PERCENTILE,
                    },
                },
                "feature_importances": feature_importance_dict,
                "prediction_vs_actual_sample": pred_vs_actual_sample,
                # Was `"quality_gate_passed": True` — a literal written on the
                # only path the gate's `continue` does not intercept, so it
                # asserted nothing and named no criteria. The gate's own
                # evaluation is recorded instead.
                "quality_gate": gate_record,
                "quality_gate_passed": gate_record["passed"],
                "leak_audit": leak_audit,
                # The corpus-level audit, beside the model-level one. `leak_audit`
                # asks whether any single feature explains the target on this
                # horizon's folds; `timeline_leak_audit` asks whether any feature
                # was computed from an observation recorded after the one it
                # describes. A model can pass either and fail the other, and only
                # the second one can see a whole-corpus aggregate. `load()`
                # deliberately does not gate on this key: the training path refuses
                # to write an artifact without a clean verdict, so a second check at
                # load time could only ever fire on an artifact written before this
                # existed, and every such artifact is already refused for carrying
                # no `leak_audit` at all.
                "timeline_leak_audit": timeline_audit,
                # The two contemporaneous audits, which the timeline one cannot see:
                # whose observations a feature read (corpus-level, so identical
                # across horizons) and what the features know about this horizon's
                # label (per horizon, so not). Recorded for the same reason as
                # `timeline_leak_audit` and gated in the same place — `train()`
                # refuses to reach this write without both clean.
                "curve_isolation_audit": isolation_audit,
                "label_independence_audit": label_audit,
                # Which declared features actually carried data in this fit. Named
                # for the defect it exists to prevent: `hour_of_day` was NaN for
                # 100% of every training frame while the serving path supplied a
                # real departure hour, and no artifact recorded that, so the skew
                # was invisible from the metadata alone.
                "feature_coverage": coverage_audit,
                "feature_columns": list(self.feature_cols),
                # Which contract those columns are. Artifacts recorded the names
                # but not the set they belong to, so `model_registry`'s first and
                # most authoritative branch — the artifact's own declaration — was
                # always empty, and the version reaching
                # `feature_engineering_pipeline` came from further down the chain.
                # An artifact that names its feature set can be rejected by a
                # predictor that eats a different one instead of being reindexed
                # into it.
                "feature_set_version": self.feature_set_version,
                "hyperparameters": hyperparameters,
                "random_seed": hyperparameters["random_state"],
                "provenance": run_provenance(),
            }
            path_json = os.path.join(BASE_ML_DIR, "models", f"fare_forecast_{h}d.metadata.json")
            with open(path_json, "w") as fj:
                json.dump(metadata, fj, indent=2)

            # Populate the same attribute `load()` populates. Only `load()` used
            # to set `self.metadata`, so a process that had just *trained* served
            # predictions with `self.metadata == {}` while a restarted process
            # served the same models with it fully populated — and everything
            # reading `metadata[h]` (residual statistics for interval widths, the
            # training timestamp, the leak audit) silently got nothing in the
            # first case. Same models, two different served behaviours.
            self.metadata[h] = metadata

            trained_horizons.append(h)

        # Save primary default model copy matching the shortest trained horizon.
        # This read `0 if 0 in self.models else ...`, preferring the horizon that
        # is no longer trainable; with 0 gone it would have fallen through to
        # `list(self.models.keys())[0]`, i.e. whichever horizon dict insertion
        # order happened to put first. The shortest trained horizon is named
        # explicitly so the legacy pickle's identity does not depend on dict
        # ordering, and the horizon it holds is recorded alongside it — the
        # pickle carried a model and no statement of which horizon it predicted,
        # which is what let one horizon's model be served under another's label.
        primary_h = min(self.models.keys()) if self.models else None
        # Record what this run actually observed before anything reads it: the
        # legacy pickle below and the report at the end of this method both
        # publish it.
        self.dataset_size = observed
        # `self.encoders` is the legacy single-map attribute. It now means exactly
        # one thing — the primary horizon's map — instead of "whichever horizon the
        # loop finished last". It is kept only because the legacy pickle below and
        # `_encode_category`'s fallback read it; the per-horizon dict is the source
        # of truth.
        if primary_h is not None:
            self.encoders = self.encoders_by_horizon.get(primary_h, {})
            primary_metrics = self.metrics.get(primary_h, {})
            with open(MODEL_PATH, "wb") as fh:
                pickle.dump({
                    "model": self.models[primary_h],
                    "encoders": self.encoders_by_horizon.get(primary_h, {}),
                    "metrics": primary_metrics,
                    "dataset_size": self.dataset_size,
                    "horizon": primary_h,
                    "leak_audit": self.metadata.get(primary_h, {}).get("leak_audit"),
                    "timeline_leak_audit": self.metadata.get(primary_h, {}).get(
                        "timeline_leak_audit"),
                    "curve_isolation_audit": self.metadata.get(primary_h, {}).get(
                        "curve_isolation_audit"),
                    "label_independence_audit": self.metadata.get(primary_h, {}).get(
                        "label_independence_audit"),
                }, fh)

        # `self._trained = True` used to run here unconditionally. `_trained` is the
        # flag the search service checks before asking for a prediction, so a training
        # run that produced no model at all still advertised a usable predictor.
        if self.models:
            self._trained = True
        else:
            logger.error(
                "Training produced no model: the dataset quality policy rejected all "
                f"{len(self.supported_horizons)} horizon(s) ({rejected}). The predictor is "
                "not trained."
            )

        return {
            "trained_horizons": trained_horizons,
            "rejected_horizons": rejected,
            "models_available": sorted(self.models.keys()),
            "trained": bool(self.models),
            "dataset_size": self.dataset_size,
            # The three leakage audits this run performed, published rather than
            # left only in the artifacts: a caller that got `trained_horizons: []`
            # can see which audit refused, and a caller that got a model can see
            # which audits permitted it. `timeline` and `curve_isolation` are
            # corpus-level so there is one of each; `label_independence` is per
            # horizon. None means the run never reached that audit.
            "leakage_audits": {
                "timeline": timeline_audit,
                "curve_isolation": isolation_audit,
                "label_independence": label_audits,
            },
        }

    # ── Load ──────────────────────────────────────────────────────────
    def load(self) -> None:
        """Load model weights and metadata per horizon, refusing unaudited artifacts.

        An artifact is only loaded if its metadata carries a `leak_audit` block
        recording that no single feature explains the target on its own. The
        three artifacts shipped before this check put 48% of their importance on
        `price_change_1d` and `price_change_3d`, which at horizon 0 are defined
        as `target - target.shift(n)`; the reported R² of 0.932 was measuring
        that. Refusing them is why the app reports no model rather than serving
        a number it cannot defend.
        """
        horizons_loaded = 0
        refused: List[str] = []
        # Start from nothing. `load()` used to accumulate into `self.models`,
        # `self.metrics`, `self.metadata` and `self.encoders_by_horizon` without
        # clearing them, and `sync_from_cloud()` calls it again on a live instance.
        # So a horizon whose artifact had been deleted — or which had since become
        # refusable — kept its previous model object, and `forecast()` (which
        # publishes exactly the horizons in `self.models`) went on publishing a
        # point for it. Rebuilt per call, into locals, and only committed once the
        # loop has finished, so a load that raises leaves the previous state intact.
        models: Dict[int, Any] = {}
        encoders_by_horizon: Dict[int, dict] = {}
        metrics: Dict[int, Any] = {}
        metadata: Dict[int, Any] = {}
        trained_routes: Dict[int, List[str]] = {}
        for h in self.supported_horizons:
            path_pkl = os.path.join(BASE_ML_DIR, "models", f"fare_forecast_{h}d.pkl")
            path_json = os.path.join(BASE_ML_DIR, "models", f"fare_forecast_{h}d.metadata.json")
            if os.path.exists(path_pkl) and not os.path.exists(path_json):
                # fare_forecast_7d.pkl shipped without a metadata sibling, so this
                # branch was taken silently and the 7d horizon simply never existed.
                refused.append(f"{h}d: {os.path.basename(path_pkl)} has no metadata sibling")
                logger.error(
                    "Refusing horizon %dd: %s exists but %s does not, so the artifact "
                    "carries no recorded metrics, gate outcome or leak audit.",
                    h, os.path.basename(path_pkl), os.path.basename(path_json))
                continue
            if os.path.exists(path_pkl) and os.path.exists(path_json):
                with open(path_pkl, "rb") as fh:
                    data = pickle.load(fh)
                with open(path_json, "r") as fj:
                    meta = json.load(fj)

                audit = meta.get("leak_audit")
                if not isinstance(audit, dict):
                    refused.append(f"{h}d: metadata carries no leak_audit block")
                    logger.error(
                        "Refusing horizon %dd: %s records no leak_audit. It predates the "
                        "feature-leakage check, so nothing establishes that its features "
                        "do not contain the target. Retrain to produce a loadable "
                        "artifact.", h, os.path.basename(path_json))
                    continue
                if not audit.get("clean", False):
                    suspects = audit.get("suspect_features") or []
                    refused.append(f"{h}d: leak_audit flags {', '.join(suspects) or 'the feature set'}")
                    logger.error(
                        "Refusing horizon %dd: leak_audit flags %s as explaining the "
                        "target on its own (ceiling %s).", h,
                        ", ".join(suspects) or "the feature set", audit.get("ceiling"))
                    continue

                models[h] = data["model"]
                # Was `self.encoders = data["encoders"]`: one attribute written
                # once per horizon, so the last horizon to load overwrote every
                # other horizon's category codes. See the note in __init__ — the
                # maps genuinely differ per horizon because each is built from the
                # uniques that survive that horizon's own filters, so serving one
                # horizon with another's map hands the model an integer standing
                # for a different airline. Wrong, never absent.
                encoders_by_horizon[h] = data.get("encoders") or {}
                # The routes this artifact was fitted on. Preferred from the
                # metadata sibling, since that is the file the leak audit above was
                # read from; the pickle's copy is the fallback for an artifact whose
                # metadata predates the key. Absent in both means empty, which
                # `/capabilities` reports as "no route list recorded" rather than
                # substituting the two-route literal it used to return.
                routes = meta.get("trained_routes")
                if not isinstance(routes, list):
                    routes = data.get("trained_routes")
                trained_routes[h] = (
                    sorted({str(r).strip().upper() for r in routes if r})
                    if isinstance(routes, list) else []
                )
                if not trained_routes[h]:
                    logger.warning(
                        "Horizon %dd artifact records no trained_routes; the routes it "
                        "was fitted on are unknown and will not be advertised.", h)
                metrics[h] = meta.get("evaluation_metrics", {})
                metadata[h] = meta
                horizons_loaded += 1

        self.refused_artifacts = refused
        if refused:
            logger.error(
                "load() refused %d of %d candidate horizon artifacts: %s",
                len(refused), len(self.supported_horizons), "; ".join(refused))

        if horizons_loaded > 0:
            # Committed together, replacing rather than merging — see the note
            # where these locals are declared.
            self.models = models
            self.encoders_by_horizon = encoders_by_horizon
            self.metrics = metrics
            self.metadata = metadata
            self.trained_routes_by_horizon = trained_routes
            self._trained = True
            self.supports_forecasting = True
            self.legacy_mode = False
            # Cleared, not left over: `sync_from_cloud()` calls load() again on a
            # live instance, so an instance that had been in legacy mode would
            # otherwise keep the old artifact's horizon.
            self.legacy_horizon = None
            # Default fallback model: the shortest loaded horizon, named
            # explicitly. This was `list(self.models.keys())[0]` — whichever
            # horizon dict insertion order happened to put first — which is the
            # same non-determinism `train()` was carrying, and it decided which
            # horizon's training timestamp and sample count the /system endpoint
            # published. `train()` picks `min(...)` for the same reason.
            first_h = min(self.models.keys())
            self.model = self.models[first_h]
            # `self.encoders` is the legacy single-map attribute, now meaning the
            # primary horizon's map rather than the last-loaded one.
            self.encoders = self.encoders_by_horizon.get(first_h, {})
            # Carry the recorded training time onto the instance; None if the
            # metadata file does not have one.
            self.training_timestamp = (self.metadata.get(first_h) or {}).get("training_timestamp")
            if first_h in self.metrics:
                # The default here used to be 1803 — a number with no provenance
                # that the /system endpoint then published as the training set
                # size. If the metadata does not record training_samples, say so
                # rather than inventing a figure.
                samples = self.metrics[first_h].get("training_samples")
                if isinstance(samples, int) and samples >= 0:
                    self.dataset_size = samples
                else:
                    self.dataset_size = 0
                    logger.warning(
                        "Horizon %sd metadata records no training_samples; dataset_size "
                        "reported as 0 rather than an assumed value.", first_h)
            logger.info("Successfully loaded %d horizon-specific forecasting models and metadata from disk.", horizons_loaded)
            return

        # Fallback to legacy global_model.pkl
        if os.path.exists(MODEL_PATH):
            with open(MODEL_PATH, "rb") as fh:
                data = pickle.load(fh)

            # The same audit the per-horizon branch applies. Without it this
            # branch was a way around the refusal: `global_model.pkl` carries no
            # metadata sibling, so an artifact refused above as unaudited loaded
            # here unconditionally and served predictions in legacy mode. A
            # legacy pickle has nowhere to put an audit but its own payload, so
            # that is where this looks.
            legacy_audit = data.get("leak_audit") if isinstance(data, dict) else None
            if not isinstance(legacy_audit, dict) or not legacy_audit.get("clean", False):
                if not isinstance(data, dict):
                    detail = f"the pickle holds a {type(data).__name__}, not a model payload"
                elif not isinstance(legacy_audit, dict):
                    detail = "the pickle records no leak_audit"
                else:
                    suspects = legacy_audit.get("suspect_features") or []
                    detail = f"leak_audit flags {', '.join(suspects) or 'the feature set'}"
                refused.append(f"legacy: {os.path.basename(MODEL_PATH)} — {detail}")
                self.refused_artifacts = refused
                logger.error(
                    "Refusing legacy %s: %s. Nothing establishes that its features do "
                    "not contain the target, and it has no metadata sibling in which to "
                    "record that they do not. Retrain to produce a loadable artifact.",
                    os.path.basename(MODEL_PATH), detail)
                raise FileNotFoundError(
                    "No prediction or forecasting models found on disk: "
                    + "; ".join(refused))

            self.model = data["model"]
            # Legacy mode means one model and no per-horizon artifacts. These are
            # cleared for the same reason the per-horizon branch rebuilds rather
            # than merges: `sync_from_cloud()` re-enters `load()` on a live
            # instance, and a stale `self.models` entry would make `forecast()`
            # publish a point for a horizon whose artifact is gone.
            self.models = {}
            self.metadata = {}
            self.encoders_by_horizon = {}
            self.trained_routes_by_horizon = {}
            self.encoders = data.get("encoders") or {}
            self.metrics = data.get("metrics", {})
            # Which horizon this single model predicts. `train()` records it; the
            # pickles that predate that record nothing, and a model whose horizon
            # is unknown cannot be served under a horizon label without guessing.
            # `predict()` refuses a mismatch and, when this is None, cannot check —
            # so log the difference rather than letting it pass unremarked.
            legacy_h = data.get("horizon")
            if isinstance(legacy_h, int) and legacy_h > 0:
                self.legacy_horizon = legacy_h
                self.encoders_by_horizon[legacy_h] = self.encoders
                legacy_routes = data.get("trained_routes")
                self.trained_routes_by_horizon[legacy_h] = (
                    sorted({str(r).strip().upper() for r in legacy_routes if r})
                    if isinstance(legacy_routes, list) else []
                )
                logger.info(
                    "Legacy model reports horizon %dd; requests for other horizons "
                    "will be refused.", legacy_h)
            else:
                self.legacy_horizon = None
                logger.warning(
                    "Legacy model pickle records no horizon, so nothing establishes "
                    "which forecast horizon its predictions are for. Any horizon "
                    "requested will be answered by this one model. Retrain to produce "
                    "per-horizon artifacts.")
            # Was `data.get("dataset_size", 1803)`: a legacy pickle with no
            # recorded size reported 1803 rows of training data that nobody
            # counted.
            legacy_size = data.get("dataset_size")
            if isinstance(legacy_size, int) and legacy_size >= 0:
                self.dataset_size = legacy_size
            else:
                self.dataset_size = 0
                logger.warning(
                    "Legacy model pickle records no dataset_size; reported as 0.")
            self._trained = True
            self.supports_forecasting = True
            self.legacy_mode = True
            logger.warning("Loaded legacy global model. Forecasting capabilities check: %s", self.supports_forecasting)
            return

        if refused:
            # Name the refusals in the exception. A bare "not found" over a
            # directory holding four .pkl files sends the reader to the wrong
            # question.
            raise FileNotFoundError(
                "No prediction or forecasting models found on disk: " + "; ".join(refused))
        raise FileNotFoundError("No prediction or forecasting models found on disk.")

    def sync_from_cloud(self) -> bool:
        """Force download from Supabase Storage and reload."""
        # `from database.database import ...` — the bare top-level name — resolves
        # only because main.py appends backend/ to sys.path, and when it does it
        # binds a *second copy* of the module with its own Supabase client. This
        # method then downloaded the model through a connection the rest of the
        # process does not share.
        from backend.database.database import database as db
        logger.info("Forcing model sync from cloud...")
        db.download_model(MODEL_PATH)
        self.load()
        return True

    @property
    def primary_horizon(self) -> Optional[int]:
        """The horizon this predictor answers by default, or None if it has no model.

        The shortest loaded horizon, named explicitly — the same choice `train()`
        and `load()` make for `self.model` and `self.encoders`. It exists because
        `model_registry.prediction_horizon` read
        `getattr(self._predictor, "prediction_horizon", 3)` against an attribute
        no code ever assigned, so the property was the literal 3 wearing a
        `getattr`. `prediction_service` then used that 3 both to pick which
        forecast point becomes the published `predicted_price` and to choose whose
        metrics to publish beside it — so with, say, only 1d and 7d artifacts
        loaded it looked for a 3d point that no longer exists.

        None is the honest answer when nothing is loaded, and callers that need an
        int are the callers that should already have refused.
        """
        if self.models:
            return min(self.models)
        if self.legacy_mode and self.legacy_horizon is not None:
            return int(self.legacy_horizon)
        return None

    @property
    def trained_routes(self) -> List[str]:
        """Every route any loaded horizon was fitted on, or empty if none says."""
        seen: set = set()
        for routes in self.trained_routes_by_horizon.values():
            seen.update(routes or [])
        return sorted(seen)

    def ensure_ready(self) -> None:
        if self._trained:
            return
        self.load()

    def get_performance(self) -> dict:
        self.ensure_ready()
        if isinstance(self.metrics, dict) and any(k in self.metrics for k in ("mae", "rmse", "r2", "accuracy")):
            return self.metrics
        for h in self.supported_horizons:
            if h in self.metrics and isinstance(self.metrics[h], dict) and "mae" in self.metrics[h]:
                return self.metrics[h]
        return {}

    def _encode_category(
        self, category_type: str, val: str, horizon: Optional[int] = None
    ) -> int:
        """Map a category to the integer code the given horizon's model was fitted on.

        Returns 0 for a value that horizon never saw. 0 is reserved: the training
        loop starts its codes at 1 precisely so that "unseen" has an integer of its
        own, and training itself does `.map(encoders[col]).fillna(0)`.

        Two fabricated fallbacks used to sit below the lookup, and both of them
        answered with a code belonging to something else:

          * An `IATA_REGISTRY` literal mapping thirty Indian airports to 1-30.
            Trained codes also start at 1, so an airport absent from the training
            data was rendered as whichever airport happened to receive that code —
            `BBI` became code 10, i.e. some other route entirely, and the model
            scored it as that route with no indication anything had been
            substituted. A hardcoded registry cannot agree with a map built from
            data it has never seen.
          * `return (abs(hash(val_clean)) % 900) + 31`. `hash()` on a `str` is
            salted per process (PYTHONHASHSEED), so the same unseen airline
            encoded to a different integer after every restart — the one property
            a category code must not have — and the docstring called it
            "deterministic".

        XGBoost has no safe out-of-range integer for an unknown category: any
        value falls into some existing split. 0 is the least wrong choice because
        it is the value the model was trained to see for a missing category.
        """
        # An absent category is absent, not the string `"NONE"`. `str(None)` is
        # `"None"` and `str(np.nan)` is `"nan"`, and the old body upper-cased them
        # into `"NONE"` / `"NAN"` and looked those up as if they were airline codes.
        # They miss every map and so returned 0 anyway — the right answer reached by
        # accident, and only for as long as no encoder ever holds those keys.
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return 0
        val_clean = str(val).strip().upper()
        if not val_clean or val_clean in ("NONE", "NAN", "NAT"):
            return 0
        # Per horizon: each horizon's map is built from the uniques surviving that
        # horizon's own filters, so they differ, and a code from the wrong map
        # names a different airline. Falls back to `self.encoders` (the primary
        # horizon) only when no horizon is named.
        if horizon is not None and horizon in self.encoders_by_horizon:
            encoders = self.encoders_by_horizon[horizon]
        else:
            encoders = self.encoders
        code = (encoders or {}).get(category_type, {}).get(val_clean)
        if code is None:
            logger.debug(
                "%s=%s unseen by horizon %s; encoded as 0 (the reserved unseen code).",
                category_type, val_clean, horizon)
            return 0
        return int(code)

    # ── Predict ───────────────────────────────────────────────────────
    def _reject_foreign_features(self, features: dict) -> None:
        """Refuse a feature vector built to a different contract.

        A partial dict is accepted on purpose: a caller that cannot compute
        `price_change_3d` omits it, `predict()` records NaN, and NaN is what the
        training frame holds in the same circumstance. That tolerance is also what
        let `forecast()` hand `predict()` a 64-name `feature_set_v1` vector — v1's
        names were dropped by the reindex onto `feature_cols`, the 9 legacy names v1
        does not declare became NaN, and the output was returned as a prediction
        with nothing logged.

        Omitting a value you could not compute and building the wrong feature set
        are different faults, and only the first is answerable. They are
        distinguishable by name: a key declared by another feature set and not by
        this one can only have come from building that set. Extra keys belonging to
        no declared set — a caller passing `origin` alongside `origin_code` — are
        ignored here exactly as `predict()` ignores them.
        """
        foreign = sorted(set(features) & self.FOREIGN_FEATURE_NAMES)
        if not foreign:
            return
        absent = [c for c in self.feature_cols if c not in features]
        raise PredictionUnavailable(
            f"Feature vector was built to a different contract: it carries "
            f"{len(foreign)} name(s) declared by feature_set_v1 and not by this "
            f"model's {self.feature_set_version!r} set (e.g. "
            f"{', '.join(foreign[:4])}). Reindexing it onto this model's "
            f"{len(self.feature_cols)} columns would discard "
            f"{len(set(features) - set(self.feature_cols))} supplied value(s) and "
            f"substitute NaN for {len(absent)} legacy feature(s)"
            + (f", including {', '.join(absent[:4])}" if absent else "")
            + f". Build the vector with "
            f"feature_set_version={self.feature_set_version!r}."
        )

    def predict(self, features: dict, horizon: int = 3) -> float:
        self.ensure_ready()

        if self.legacy_mode:
            # A legacy pickle holds one model. It now also records which horizon
            # that model predicts (`train()` writes `"horizon": primary_h`), so
            # asking it for a different horizon is answerable only by pretending.
            legacy_h = self.legacy_horizon
            if legacy_h is not None and int(horizon) != int(legacy_h):
                raise HorizonUnavailable(
                    f"The loaded legacy model predicts {legacy_h}d; horizon "
                    f"{horizon}d was requested and no {horizon}d model is loaded."
                )
            model_to_use = self.model
            encode_h = legacy_h
        else:
            model_to_use = self.models.get(horizon)
            encode_h = horizon
            if model_to_use is None:
                # Was: fall back to `self.model or list(self.models.values())[0]`
                # and answer anyway. That served the shortest trained horizon's
                # model under whatever horizon the caller asked for — a 3d model
                # answering a 30d question, labelled 30d all the way out to the
                # UI. The fare thirty days out and the fare three days out are
                # different quantities; substituting one for the other silently
                # is the whole defect. Refuse. `flight_search_service.py`'s
                # per-flight handler already logs at warning and sets
                # `ml_available = False`, and `prediction_service` maps this to a
                # 503, so the caller degrades rather than crashing.
                raise HorizonUnavailable(
                    f"No model trained or loaded for forecast horizon {horizon}d. "
                    f"Loaded horizons: {sorted(self.models) or 'none'}."
                )

        self._reject_foreign_features(features)

        df = pd.DataFrame([features])

        # Standardizing inputs.
        #
        # `days_until_dep` used to default to 7.0 when the caller did not supply
        # it: a request with an unknown booking horizon was scored as a flight
        # departing in a week. `urgency` is 1/(days+1), so the fabrication reached
        # the model twice. NaN is what XGBoost expects for a missing value and
        # what the training path now records for an unknowable horizon
        # (`booking_horizon_days`), so the two paths agree.
        val_dep = np.nan
        if "days_until_dep" in df.columns and not df["days_until_dep"].isna().iloc[0]:
            val_dep = max(0.0, float(df["days_until_dep"].iloc[0]))
        df["days_until_dep"] = val_dep
        df["urgency"] = (1.0 / (val_dep + 1.0)) if not pd.isna(val_dep) else np.nan

        if "is_live" not in df.columns:
            df["is_live"] = True

        defaults = {
            "day_of_week": np.nan, "month": np.nan, "week_of_year": np.nan,
            "hour_of_day": np.nan, "is_peak_hour": np.nan, "seats_available": np.nan,
            "price_change_1d": np.nan, "price_change_3d": np.nan,
            "demand_score": np.nan, "seasonality_factor": np.nan,
        }
        for col, val in defaults.items():
            if col not in df.columns:
                df[col] = val

        for col in ("origin_code", "destination_code", "airline_code"):
            val = str(df.get(col, pd.Series([""])).iloc[0]).upper()
            df[col] = self._encode_category(col, val, horizon=encode_h)
            
        for col in self.feature_cols:
            if col not in df.columns:
                df[col] = np.nan

        try:
            X = df[self.feature_cols]
            raw_pred = float(model_to_use.predict(X)[0])

            # There used to be `if raw_pred < 800: raw_pred = raw_pred * 1.15`
            # here — no log, no flag, no record in the response. A prediction
            # below any real Indian domestic fare is evidence the model has been
            # handed a feature vector it cannot use; multiplying it by 1.15
            # produced a still-implausible number that merely looked less odd.
            # The value is now returned unaltered and the condition is logged,
            # so the caller decides whether to serve it.
            if raw_pred < IMPLAUSIBLE_FARE_FLOOR:
                logger.warning(
                    "Model returned ₹%.2f for horizon %s, below the ₹%.0f plausibility "
                    "floor. Returning it unmodified. Feature vector had %d of %d "
                    "columns non-null.",
                    raw_pred, horizon, IMPLAUSIBLE_FARE_FLOOR,
                    int(X.notna().sum(axis=1).iloc[0]), len(self.feature_cols),
                )

            return float(round(raw_pred, 2))

        except Exception as exc:
            # Was `logger.error(f"Predict error ({exc})")` followed by
            # `from fastapi import HTTPException; raise HTTPException(500,
            # "Core ML pipeline inference model missing or uninitialized")`.
            # Two problems, both about what a reader is told. The message names a
            # cause that cannot be the cause here: `ensure_ready()` ran at the top
            # of this method and `model_to_use` is a fitted estimator by this
            # point, so whatever failed, it was not a missing or uninitialized
            # model — it was this feature vector against this model. And the
            # original exception was formatted into one line with no traceback and
            # then dropped, so the true cause was unrecoverable from the logs.
            #
            # The ML layer also has no business constructing an HTTP response.
            # `PredictionUnavailable` is the domain type the routers already map
            # (`routers/predict.py` → 503) and `flight_search_service` already
            # degrades on, and `from exc` keeps the original in `__cause__` so the
            # traceback survives.
            logger.error(
                "Inference failed for horizon %s on a vector of %d columns: %s: %s",
                horizon, len(self.feature_cols), type(exc).__name__, exc,
                exc_info=True,
            )
            raise PredictionUnavailable(
                f"Prediction unavailable: inference failed for horizon {horizon} "
                f"({type(exc).__name__}: {exc})."
            ) from exc

    # ── Prediction interval ───────────────────────────────────────────
    def _interval_bounds(self, horizon: int, price: float) -> Dict[str, Any]:
        """The published interval for one forecast point, from recorded residuals.

        Returns the bounds and the provenance of the figures they came from, or
        raises `IntervalUnavailable`. It does not fall back: the band this
        replaced was `max(120.0, price * 0.06)`, and a fabricated width is
        indistinguishable in the response from a measured one.

        `residuals = y_test - preds` (see `train()`), so a residual is how much
        higher the actual fare was than the prediction. `price + p10` and
        `price + p90` are therefore empirical percentiles of the actual fare
        given this prediction — asymmetric where the residuals are, and shifted
        by the model's bias rather than centred on a point estimate that may be
        systematically off.

        The bounds are not clamped. `forecast()` used to publish
        `max(IMPLAUSIBLE_FARE_FLOOR, price - band)`, which silently moved a lower
        bound up to ₹800 and so reported an interval the model had not implied;
        a bound below the floor is evidence about the prediction and is logged as
        such, exactly as `predict()` now does for the point estimate.

        Known limitation, stated because it is a property of the measurement and
        not something to paper over: the residuals are absolute rupee errors
        pooled over the whole test fold, so the interval has the same width at
        ₹2,000 as at ₹40,000. On a fold spanning cheap and expensive routes that
        is too wide at the bottom and too narrow at the top. It is still a
        measured width — the old band's 12% of the point estimate was not — but
        a per-route or relative-error interval, or quantile regression at the two
        percentiles, would be better calibrated. `interval_basis` publishes the
        sample size so a reader can judge how much the quantiles rest on.
        """
        stats = ((self.metadata.get(horizon) or {}).get("residual_statistics") or {})
        quantiles = stats.get("residual_quantiles") or {}
        sample_size = stats.get("residual_sample_size")

        if not quantiles:
            raise IntervalUnavailable(
                f"Forecast interval unavailable for horizon {horizon}d: the loaded "
                f"artifact records no residual quantiles, so there is no measured "
                f"basis for an interval width. Retrain this horizon to record them.",
                horizon=horizon,
            )
        if not isinstance(sample_size, int) or sample_size < MIN_RESIDUALS_FOR_INTERVAL:
            raise IntervalUnavailable(
                f"Forecast interval unavailable for horizon {horizon}d: its residual "
                f"quantiles were measured on {sample_size!r} residual(s), below the "
                f"{MIN_RESIDUALS_FOR_INTERVAL} needed for the "
                f"{RESIDUAL_INTERVAL_LOWER_PERCENTILE:.0f}th and "
                f"{RESIDUAL_INTERVAL_UPPER_PERCENTILE:.0f}th percentiles to describe a "
                f"distribution rather than two observations.",
                horizon=horizon, residual_sample_size=sample_size,
            )

        try:
            p_low = float(quantiles["p10"])
            p_high = float(quantiles["p90"])
        except (KeyError, TypeError, ValueError) as exc:
            raise IntervalUnavailable(
                f"Forecast interval unavailable for horizon {horizon}d: its recorded "
                f"residual quantiles are unreadable ({quantiles!r}).",
                horizon=horizon, residual_sample_size=sample_size,
            ) from exc

        if not (math.isfinite(p_low) and math.isfinite(p_high)):
            raise IntervalUnavailable(
                f"Forecast interval unavailable for horizon {horizon}d: its recorded "
                f"residual quantiles are not finite (p10={p_low}, p90={p_high}).",
                horizon=horizon, residual_sample_size=sample_size,
            )
        if p_high < p_low:
            # Percentiles cannot invert; if they have, the record was not written
            # by `train()` and nothing derived from it should be published.
            raise IntervalUnavailable(
                f"Forecast interval unavailable for horizon {horizon}d: recorded "
                f"p90 ({p_high}) is below recorded p10 ({p_low}), so the record is "
                f"not a quantile pair.",
                horizon=horizon, residual_sample_size=sample_size,
            )

        lower = float(price) + p_low
        upper = float(price) + p_high
        if lower < IMPLAUSIBLE_FARE_FLOOR:
            logger.warning(
                "Horizon %dd interval lower bound is ₹%.2f, below the ₹%.0f "
                "plausibility floor (point ₹%.2f, recorded residual p10 %+.2f over "
                "%d residuals). Publishing it unmodified.",
                horizon, lower, IMPLAUSIBLE_FARE_FLOOR, price, p_low, sample_size,
            )

        return {
            "lower": round(lower, 2),
            "upper": round(upper, 2),
            "interval_basis": {
                "method": "empirical residual quantiles from this horizon's test fold",
                "lower_percentile": RESIDUAL_INTERVAL_LOWER_PERCENTILE,
                "upper_percentile": RESIDUAL_INTERVAL_UPPER_PERCENTILE,
                "residual_p10": round(p_low, 2),
                "residual_p90": round(p_high, 2),
                "residual_sample_size": sample_size,
            },
        }

    # ── Forecast ──────────────────────────────────────────────────────
    def forecast(self, snapshot: dict) -> list:
        """Multi-horizon forecast, or a refusal.

        The signature used to be `forecast(self, snapshot, days: int = 30)`, and
        `days` was never read. The horizons published are
        `[h for h in self.supported_horizons if h in self.models]` — what is
        loaded, not what the caller asks for — so a parameter named `days`
        offered a horizon window the method does not honour. The one production
        call site (`forecast_engine.py:97`) never passed it; the only caller that
        did was a test asserting a four-point curve, which this method has not
        been able to return since `supported_horizons` became `[1, 3, 7]`.

        This method also used to end by comparing its own output against two
        hardcoded constants:

            if abs(price - 6097.73) < 1.0 or abs(price - 9300.0) < 1.0:
                drift_factor = {0: 1.0, 1: 1.08, 3: 0.96, 7: 1.03}.get(h, 1.0)
                price = float(lowest_fare_anchor) * drift_factor

        Those two numbers are what the model emits when its two highest-weighted
        features are unavailable — together 48% of the shipped 0d model's
        importance — which at serve time they routinely are, since
        `price_change_1d/3d` are built from price history the request may not
        have. So on the common path the published curve was the scraped fare
        multiplied by four hardcoded factors, and the model contributed nothing
        to it.

        The override is gone. If the history the features need is absent, this
        raises `InsufficientHistory` (HTTP 503) rather than answering.
        """
        from datetime import date, timedelta, datetime
        from backend.utils.exceptions import InsufficientHistory

        self.ensure_ready()
        if self.legacy_mode and not self.supports_forecasting:
            raise ValueError("Forecasting is disabled for legacy models.")

        today = date.today()
        forecast = []

        dep_date_str = snapshot.get("departure_date")
        if not dep_date_str:
            # Was `dep_date = today + timedelta(days=30)`. A request that named no
            # departure date was forecast as a flight thirty days out, and
            # `days_until_dep` — recomputed per horizon and the one quantity a
            # booking-horizon sweep varies — was derived from that invented date.
            # Every calendar feature (`day_of_week`, `month`, `week_of_year`,
            # `is_weekend`, `is_holiday`) described a day nobody had asked about.
            # Unreachable from `prediction_service`, whose validator requires the
            # date, which is exactly why it could sit here indefinitely.
            raise InsufficientHistory(
                "Forecast unavailable: the request names no departure date, and the "
                "horizon a fare is forecast at is measured from it, so there is "
                "nothing to forecast against.",
                observations=0,
            )
        dep_date = datetime.fromisoformat(dep_date_str.split("T")[0]).date()

        # The feature set the loaded model was actually fitted on.
        #
        # This was:
        #
        #     fs_version = "legacy" if self.legacy_mode else "feature_set_v1"
        #     ...
        #     if fs_version == "legacy":
        #         raise InsufficientHistory(
        #             "Forecast unavailable: the loaded model predates the current "
        #             "feature set, so its price-history features cannot be computed "
        #             "for this request. Retrain ... to enable forecasting.")
        #
        # `legacy_mode` is True only on the single-pickle `global_model.pkl` path,
        # so on every normal load it was False, `fs_version` was `"feature_set_v1"`
        # and the refusal was skipped. The loop below then built a 64-name v1 vector
        # and handed it to `predict()`, which reindexes whatever it is given to
        # `self.feature_cols` — the legacy 16 — and NaN-fills the difference. v1
        # declares 7 of those 16. So every published forecast point was computed
        # with `days_until_dep`, `urgency`, `day_of_week`, `month`, `week_of_year`,
        # `hour_of_day`, `is_peak_hour`, `demand_score` and `seasonality_factor` all
        # NaN — including the two that encode *when you book*, which is the only
        # quantity a booking-horizon sweep varies. `days_until_dep` is recomputed
        # per horizon at the top of the loop and put into `prediction_context`, and
        # then dropped by the pipeline because v1 does not declare that name (it
        # declares `days_until_departure`, which this model has never seen). The
        # curve's points differed only through features independent of the horizon,
        # which is why it came out flat, and no exception was raised at any point.
        #
        # Nothing converts a v1 vector into a legacy one, and `predict()` now
        # refuses to be handed one. Ask the pipeline for the set the model eats;
        # `TemporalFeatureGenerator` derives `days_until_dep` from
        # `context.current_timestamp`, which this loop already advances per horizon,
        # so the horizon reaches the model without further plumbing.
        #
        # Dropping the refusal costs no coverage. `legacy_mode` implies
        # `self.models` is empty, and the `available` check below already refuses by
        # name when no horizon model is loaded — that check was doing the work,
        # while this one only decided which feature set to build.
        fs_version = self.feature_set_version

        origin = snapshot.get("origin", "")
        destination = snapshot.get("destination", "")
        # The flight this curve is about, as far as the caller could establish it.
        # `airline` is read again inside the horizon loop below for the feature
        # vector; these two are read here because they also narrow the history query.
        curve_airline = snapshot.get("airline") or None
        curve_flight_number = snapshot.get("flight_number") or None

        from backend.database.flight_repository import flight_repository
        # Newest-first, filtered to the booking curve rather than the route.
        #
        # This was `get_price_history_cache(origin, destination, dep, 100)`. The cap
        # is applied by the database before `price_changes_from_records` narrows the
        # rows to one curve, so on a busy route the 100 newest route-wide rows could
        # leave the quoted flight with nought to two observations — and the refusal
        # below then reported the *route's* count as the reason the flight's features
        # were missing. The filter is as narrow as `snapshot` allows and no narrower.
        hist_records = flight_repository.get_price_history_cache(
            origin, destination, dep_date.strftime("%Y-%m-%d"),
            FORECAST_HISTORY_ROW_CAP,
            airline_code=curve_airline,
            flight_number=curve_flight_number,
        ) or []
        # Name what any refusal below counted. With the query narrowed, "2
        # observations" is a statement about one flight, and saying "DEL-BOM" when
        # the count came from filtering on 6E 2044 would misdescribe both the data
        # and this fix.
        subject = "-".join(filter(None, [origin, destination]))
        if curve_airline:
            subject += f" {curve_airline}"
            if curve_flight_number:
                subject += f" {curve_flight_number}"
        if len(hist_records) < MIN_FORECAST_HISTORY_ROWS:
            raise InsufficientHistory(
                f"Forecast unavailable: {subject} on "
                f"{dep_date.isoformat()} has {len(hist_records)} recorded price "
                f"observation(s); at least {MIN_FORECAST_HISTORY_ROWS} are needed to "
                f"compute the price-movement features this model was trained on.",
                observations=len(hist_records),
            )

        # The fare the curve is anchored to: the quoted flight's own, or nothing.
        #
        # Read once here rather than per horizon, because it does not vary by
        # horizon. It was read inside the loop as
        #
        #     snapshot.get("lowest_fare") or snapshot.get("current_price") or snapshot.get("average_fare")
        #
        # and written into `prediction_context` under both `current_price` and
        # `lowest_fare` — three substitutions in one expression, and none of the
        # three is reliably the quantity the name promises. `average_fare` is the
        # mean over every flight on the route, so a request with no live quote was
        # anchored to a number no passenger could book. `or` also treats 0.0 as
        # absent and falls through to the next candidate. And neither `lowest_fare`
        # nor `average_fare` is a key of the dict `ForecastEngine` passes, so in
        # production the chain always resolved to `current_price` — which
        # `prediction_service` used to set to this model's own point prediction
        # whenever the live fare was unavailable, making the anchor the model's
        # output.
        #
        # `price_changes_from_records` appends this value as the curve's latest
        # observation and every movement feature is a difference against it, so an
        # anchor with no source makes all of them fiction. Refuse instead.
        quoted_fare_raw = snapshot.get("current_price")
        try:
            quoted_fare_val = (float(quoted_fare_raw)
                               if quoted_fare_raw is not None else None)
        except (TypeError, ValueError):
            quoted_fare_val = None
        if (quoted_fare_val is None
                or not np.isfinite(quoted_fare_val)
                or quoted_fare_val <= 0):
            raise InsufficientHistory(
                f"Forecast unavailable: no live fare is quoted for {subject} on "
                f"{dep_date.isoformat()} (current_price={quoted_fare_raw!r}). The "
                f"booking curve's movement features are differences against the fare "
                f"on screen, so without one there is nothing to measure them from.",
                observations=len(hist_records),
            )

        # Only the horizons that actually have a model. This used to iterate
        # `self.supported_horizons` — [1, 3, 7] — whatever was loaded, and
        # `predict()` answered a horizon it had no model for by falling back to the
        # shortest one it did have. So a build with only a 1d artifact published a
        # three-point curve in which all three points were the 1d model's output,
        # labelled 1d, 3d and 7d. The curve looked like a forecast and was one
        # number.
        #
        # `predict()` now refuses an unavailable horizon, so iterating the declared
        # list would abort the whole forecast on the first gap. Iterate what exists,
        # and refuse only when nothing does.
        available = [h for h in self.supported_horizons if h in self.models]
        if not available:
            raise InsufficientHistory(
                "Forecast unavailable: no horizon model is loaded, so there is no "
                f"horizon to forecast. Declared horizons: {self.supported_horizons}.",
                observations=len(hist_records),
            )
        if len(available) < len(self.supported_horizons):
            logger.warning(
                "Forecasting horizons %s only; %s declared but not loaded, so no "
                "point is published for them.",
                available, sorted(set(self.supported_horizons) - set(available)))

        for h in available:
            booking_date = today + timedelta(days=h)
            days_until_dep = max(0, (dep_date - booking_date).days)
            urgency = round(1 / (days_until_dep + 1), 4)

            from backend.ml.feature_context import FeatureContext
            from backend.ml.feature_engineering_pipeline import feature_engineering_pipeline

            # Whatever the snapshot names, or nothing. This read
            # `snapshot.get("airline", "6E")`: a request whose market snapshot
            # carried no airline was forecast as IndiGo, and because `6E` is the
            # most common carrier in the corpus it has a real trained code — so the
            # model was conditioned on a specific airline nobody had quoted, and the
            # curve was labelled with the route rather than the substitution. None
            # now reaches `_encode_category` and encodes as 0, the unseen marker.
            airline = curve_airline

            sim_ctx = FeatureContext(
                historical_data=hist_records,
                market_snapshot=snapshot,
                prediction_context={
                    "origin": origin,
                    "destination": destination,
                    "airline": airline,
                    # The fifth part of the booking-curve key, and the two per-flight
                    # columns of `price_history`. None of the three was here: the key
                    # was built without a flight number, so `curve_identity_is_complete`
                    # rejected it and all fourteen curve features came back NaN for
                    # every point on every curve; `seats_available` was the literal
                    # `np.nan` whatever the snapshot knew; and `departure_time` was
                    # absent, so `hour_of_day` and `is_peak_hour` were NaN for a flight
                    # whose departure time the provider had reported. This is the path
                    # that produces the published price, so it is the path those
                    # features mattered on most.
                    #
                    # Still None whenever the caller could not establish them, and the
                    # generators turn that into NaN rather than a substitute.
                    "flight_number": curve_flight_number,
                    "departure_date": dep_date.strftime("%Y-%m-%d"),
                    "departure_time": snapshot.get("departure_time"),
                    "seats_available": snapshot.get("seats_available"),
                    "current_price": quoted_fare_val,
                    "lowest_fare": quoted_fare_val,
                    "days_until_dep": days_until_dep
                },
                route_statistics={},
                airline_statistics={},
                booking_statistics={},
                current_timestamp=datetime.combine(booking_date, datetime.min.time(), tzinfo=timezone.utc)
            )

            feat_vec = feature_engineering_pipeline.build(sim_ctx, fs_version)
            features = feat_vec.features

            # The features the model weights most heavily must actually be
            # present. If the pipeline could not compute them from the history
            # above, the model would emit its unconditioned constant — which is
            # the state the deleted override was papering over.
            missing_movement = [c for c in ("price_change_1d", "price_change_3d")
                                if c in self.feature_cols
                                and (c not in features
                                     or features.get(c) is None
                                     or (isinstance(features.get(c), float)
                                         and np.isnan(features[c])))]
            if missing_movement:
                raise InsufficientHistory(
                    f"Forecast unavailable for horizon {h}d: {', '.join(missing_movement)} "
                    f"could not be computed from {len(hist_records)} recorded "
                    f"observation(s) for {origin}-{destination}. These features carry "
                    f"most of the model's weight; without them its output is not a "
                    f"prediction about this route.",
                    horizon=h, observations=len(hist_records),
                )

            price = self.predict(features, horizon=h)

            # Was:
            #
            #     band = max(120.0, price * 0.06)
            #     "lower": round(float(max(IMPLAUSIBLE_FARE_FLOOR, price - band)), 2),
            #     "upper": round(float(price + band), 2),
            #
            # ±6% of the point estimate, floored at ±₹120, published as this
            # model's confidence interval. Nothing the model measured was an input:
            # the same width for a horizon it predicts well and one it predicts
            # badly, symmetric regardless of the residual skew, and never wider for
            # a worse model. The lower bound was then clamped up to the plausibility
            # floor, so a model implying a fare below ₹800 published an interval it
            # had not implied. See `_interval_bounds` for what replaced it.
            bounds = self._interval_bounds(h, price)
            forecast.append({
                "day": h,
                "date": booking_date.isoformat(),
                "price": round(float(price), 2),
                "lower": bounds["lower"],
                "upper": bounds["upper"],
                "interval_basis": bounds["interval_basis"],
            })

        return forecast


# ── Singleton ─────────────────────────────────────────────────────────

_predictor: PricePredictor | None = None


def get_predictor() -> PricePredictor:
    """The process-wide predictor, loaded from disk if a usable artifact exists.

    This function does not train. The body used to be::

        try:
            p.load()
        except Exception as exc:
            logger.warning(f"Prediction model load failed ({exc}) — training matching models now...")
            p.train()

    which was wrong three ways, each on its own sufficient:

    1. **It trained inside an import.** `services/model_registry.py` builds its
       singleton at module scope, and `routers/system.py` imports it, so the first
       import of a router in a process with no loadable artifact began a full
       XGBoost fit over the database while holding the import lock.
    2. **The training path imports the module that was mid-import.**
       `train()` → `training_dataset_builder.build()` → `from
       backend.services.model_registry import model_registry`, which is the module
       whose own module scope started this. Measured result: `ImportError: cannot
       import name 'model_registry' from partially initialized module
       'backend.services.model_registry' (most likely due to a circular import)` —
       an exception naming neither the missing artifact nor the training run.
    3. **It was a way around the artifact refusal.** `load()` declines any
       artifact whose metadata does not record a clean leak audit. Reacting to that
       refusal by fitting a replacement and serving it means the refusal decides
       nothing, which is the same defect that was closed on the legacy
       `global_model.pkl` branch.

    A failed load leaves the predictor untrained and `load_error` set. That is a
    state the serving paths already handle honestly: `_trained` stays False,
    `training_timestamp` and `dataset_size` stay None, `/system` lists them under
    `unavailable`, and the prediction paths refuse rather than answer. Training is
    an explicit operation — `scheduler.py`'s retraining job, `run_pipeline.py`, or
    `PricePredictor.train()` called directly.
    """
    global _predictor
    if _predictor is not None:
        return _predictor

    p = PricePredictor()
    try:
        p.load()
    except Exception as exc:
        p.load_error = f"{type(exc).__name__}: {exc}"
        logger.error(
            "No prediction model is available: load failed (%s). Not training a "
            "replacement — predictions will be refused until a model is trained "
            "explicitly. Refused artifacts: %s",
            p.load_error, p.refused_artifacts or "none",
        )

    _predictor = p
    return _predictor
