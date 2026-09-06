"""Booking Curve Pipeline Validation and Monitoring Library.

Provides a reusable API for chronology verification, duplicate checks,
target leakage validation, health metrics, feature coverage analysis,
target quality evaluation, and feature drift detection.
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import pandas as pd
import numpy as np

# Module-level, unlike the deliberately local imports further down: those pull in
# `feature_engineering_pipeline`, which is heavy and which imports back into this
# package. `booking_curve_definition` imports nothing from this project — pandas and
# numpy only — and `LEAKAGE_IDENTITY_COLUMNS` below is built from it at import time,
# so it has to be available here.
from backend.services.booking_curve_definition import BOOKING_CURVE_KEYS

logger = logging.getLogger(__name__)

# backend/ml/<this file> -> backend/validation_reports. Anchored to this file
# rather than to the working directory. generate_validation_report() calls
# os.makedirs(history_dir), so the previous relative default
# "backend/validation_reports" did not merely read the wrong place — launched
# from backend/ it created backend/backend/validation_reports and wrote the run
# there, splitting the drift history that detect_feature_drift() compares
# against into two directories that never see each other.
DEFAULT_HISTORY_DIR = Path(__file__).resolve().parent.parent / "validation_reports"


@dataclass
class ValidationResult:
    status: str  # PASS, WARNING, FAIL
    warnings: List[str]
    errors: List[str]
    metrics: Dict[str, Any]


@dataclass
class ValidationReport:
    timestamp: str
    feature_set_version: str
    overall_status: str  # PASS, WARNING, FAIL
    readiness_score: int  # 0 to 100
    chronology: ValidationResult
    duplicates: ValidationResult
    leakage: ValidationResult
    health: ValidationResult
    coverage: ValidationResult
    target_quality: ValidationResult
    drift: ValidationResult

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "feature_set_version": self.feature_set_version,
            "overall_status": self.overall_status,
            "readiness_score": self.readiness_score,
            "chronology": asdict(self.chronology),
            "duplicates": asdict(self.duplicates),
            "leakage": asdict(self.leakage),
            "health": asdict(self.health),
            "coverage": asdict(self.coverage),
            "target_quality": asdict(self.target_quality),
            "drift": asdict(self.drift),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def validate_chronology(df_raw: pd.DataFrame) -> ValidationResult:
    """Verifies that every booking curve is sorted chronologically by recorded_at."""
    errors = []
    warnings = []
    
    if df_raw.empty:
        return ValidationResult("FAIL", [], ["Dataset is empty."], {})
        
    df = df_raw.copy()
    # `format="ISO8601"` on every `recorded_at` parse in this module. Postgres
    # renders a `timestamptz` without the microseconds field when it is zero, and
    # rows written from Python go through `datetime.isoformat()`, which does the
    # same — so this column mixes `...T10:00:00.123456+00:00` with
    # `...T10:00:01+00:00`. Without a format pandas infers one shape from the
    # first value and then, at the default `errors="raise"`, dies with `time data
    # ... doesn't match format` on the first row of the other shape. These
    # validators read the whole corpus, so that is a hard stop. `errors` stays at
    # its default deliberately: a value that is not ISO-8601 at all should still
    # fail loudly here rather than become a NaT that silently shrinks a count.
    df["recorded_dt"] = pd.to_datetime(df["recorded_at"], format="ISO8601")
    
    # Sort and group by booking curve keys.
    #
    # `BOOKING_CURVE_KEYS`, not a hand-typed subset of it. This was
    # `["origin_code", "destination_code", "airline_code", "departure_date"]` — four
    # columns, carrying no per-flight component at all, so every one of a carrier's
    # departures on a route and date pooled into a single "curve". That is not a
    # weaker check here, it is an inverted one: this function reads each group's
    # timestamps in frame order and FAILs when they are not ascending, and a pooled
    # group is one real curve's ascending timestamps followed by the next curve's,
    # starting over. A corpus sorted correctly by curve then time therefore failed
    # chronological integrity, and the errors named a group that does not exist.
    group_keys = list(BOOKING_CURVE_KEYS)
    missing_cols = [col for col in group_keys if col not in df.columns]
    if missing_cols:
        return ValidationResult("FAIL", [], [f"Missing group key columns: {missing_cols}"], {})
        
    # Check if df is sorted chronologically within each group
    grouped = df.groupby(group_keys)
    out_of_order_count = 0
    total_groups = 0
    
    for name, group in grouped:
        total_groups += 1
        # Check if timestamps are monotonically increasing
        times = group["recorded_dt"].tolist()
        if times != sorted(times):
            out_of_order_count += 1
            errors.append(f"Booking curve group {name} is not sorted chronologically.")
            
    status = "FAIL" if out_of_order_count > 0 else "PASS"
    metrics = {
        "total_groups": total_groups,
        "out_of_order_groups": out_of_order_count,
        "chronological_integrity_pct": ((total_groups - out_of_order_count) / total_groups * 100) if total_groups > 0 else 100.0
    }
    
    return ValidationResult(status, warnings, errors, metrics)


def validate_duplicates(df_raw: pd.DataFrame, df_cleaned: pd.DataFrame) -> ValidationResult:
    """Validates duplicate removal rate and preservation of daily history."""
    warnings = []
    errors = []
    
    raw_size = len(df_raw)
    cleaned_size = len(df_cleaned)
    removed = raw_size - cleaned_size
    dup_pct = (removed / raw_size * 100) if raw_size > 0 else 0.0
    
    # Failure condition: If we removed more than 90% of the dataset, it indicates too aggressive cleaning
    if dup_pct > 90.0:
        errors.append(f"Deduplication rate is extremely high ({dup_pct:.1f}%). Cleaning may be too aggressive.")
    elif dup_pct > 50.0:
        warnings.append(f"Deduplication rate is high ({dup_pct:.1f}%). Check if duplicate queries are running frequently.")
        
    # Check if historical observations on different dates are preserved.
    #
    # The key is `BOOKING_CURVE_KEYS`; it was a four-column list with no per-flight
    # component. Both sides of the comparison used the same key, so the check was
    # weakened rather than inverted — but weakened in the direction that matters:
    # with two of a carrier's departures pooled into one group, deduplication can
    # delete every observation of one of them on some date and the pooled group
    # still shows that date as covered by the sibling. This is the check whose job
    # is to catch exactly that deletion.
    #
    # A frame that cannot answer the question says so. It used to skip silently, so
    # a corpus with no curve identity produced a PASS on a check that never ran.
    group_keys = list(BOOKING_CURVE_KEYS)
    absent = [col for col in group_keys + ["recorded_at"] if col not in df_raw.columns]
    if absent:
        warnings.append(
            "Day-preservation not checked: the raw frame is missing "
            f"{', '.join(absent)}, so an observation cannot be tied to a curve and "
            "a deleted day cannot be distinguished from one a sibling departure "
            "still covers."
        )
    else:
        df_raw_date = df_raw.copy()
        # `format="ISO8601"` for the reason recorded at `validate_chronology`.
        df_raw_date["recorded_date"] = pd.to_datetime(
            df_raw_date["recorded_at"], format="ISO8601").dt.date
        df_clean_date = df_cleaned.copy()
        df_clean_date["recorded_date"] = pd.to_datetime(
            df_clean_date["recorded_at"], format="ISO8601").dt.date
        
        raw_unique_days = df_raw_date.groupby(group_keys)["recorded_date"].nunique().sum()
        clean_unique_days = df_clean_date.groupby(group_keys)["recorded_date"].nunique().sum()
        
        # We must never delete different-day historical observations!
        if clean_unique_days < raw_unique_days:
            errors.append(f"Historical days were lost during deduplication: raw had {raw_unique_days} unique days, clean has {clean_unique_days}.")
            
    status = "FAIL" if errors else ("WARNING" if warnings else "PASS")
    metrics = {
        "raw_rows": raw_size,
        "retained_rows": cleaned_size,
        "duplicates_removed": removed,
        "duplicate_pct": dup_pct
    }
    
    return ValidationResult(status, warnings, errors, metrics)


# Columns that identify an observation rather than describe it. Excluded from the
# leakage comparison because they are copied through from the raw frame, so they
# cannot change under masking and comparing them proves nothing.
#
# The identity half comes from `BOOKING_CURVE_KEYS`, so a change to the curve key
# cannot leave a component of the identity being compared as though it were a
# feature. `flight_number` stays in the set explicitly: it is no longer part of the
# key (see the note above `BOOKING_CURVE_KEYS`) but it is still a column the
# training frame carries, and it is still not a feature.
LEAKAGE_IDENTITY_COLUMNS = frozenset(BOOKING_CURVE_KEYS) | frozenset({
    "flight_number",
    "recorded_at", "search_timestamp", "recorded_date",
    "price", "target_price", "days_until_dep", "seats_available",
})


def leakage_comparison_columns(full: pd.DataFrame, masked: pd.DataFrame) -> List[str]:
    """Every numeric engineered column the two frames share.

    Derived, not enumerated. The previous version compared a hardcoded list of ten
    lag and rolling features, so the fourteen route- and airline-level aggregates —
    which at the time were whole-corpus `groupby(route).transform(...)`, the largest
    leak in the pipeline — were not on it and the validator returned PASS over them
    for as long as they existed. A list that has to be extended by hand each time a
    feature is added is a list that will be out of date by the next feature.

    The invariant makes the derivation sound: a feature for an observation recorded
    at time t is computed from the observations recorded at or before t, so masking
    everything after t cannot change it. That is true of *every* causal feature, not
    of ten chosen ones, so every numeric feature is a legitimate subject of the
    comparison.

    Numeric only, because the comparison uses `np.isnan`, which raises TypeError on
    an object column — the airline and route codes among them.
    """
    return [
        col for col in full.columns
        if col in masked.columns
        and col not in LEAKAGE_IDENTITY_COLUMNS
        and pd.api.types.is_numeric_dtype(full[col])
        and pd.api.types.is_numeric_dtype(masked[col])
    ]


def _values_disagree(val_full: Any, val_masked: Any, tol: float = 1e-5) -> bool:
    """True when the two values differ, counting a one-sided NaN as a difference.

    The previous form was `if not (isnan(a) and isnan(b)): if abs(a - b) > tol`.
    With one side NaN the guard passes and `abs(NaN - 5000) > tol` evaluates to
    False, so "NaN in the full frame, 5000 in the masked frame" — a feature that
    materialises out of masked data, which is leakage of the most direct kind —
    was reported as agreement. Both comparisons in that form are False for a NaN,
    so the hole could not be seen from either branch.
    """
    a_nan, b_nan = pd.isna(val_full), pd.isna(val_masked)
    if a_nan and b_nan:
        return False
    if a_nan or b_nan:
        return True
    return abs(float(val_full) - float(val_masked)) > tol


def validate_target_leakage(df_raw: pd.DataFrame, feature_set_version: str) -> ValidationResult:
    """Detects target leakage by recomputing features on masked timeline subsets.

    For a sampled observation at time t, rebuild the whole feature frame from a
    corpus truncated at t and require every numeric feature of that observation to
    be unchanged. A feature that moves saw something recorded after t.

    Three things about how this is done are load-bearing:

    * **The mask uses the column the features order by.** It used to mask on
      `recorded_at` while `resolve_ordering_timestamp_column` resolves to
      `search_timestamp` when that column is present, so the rows the validator
      hid and the rows the features excluded were two different sets — enough to
      manufacture a failure on a causal feature and to hide one on a leaky feature.
    * **Rows are aligned by index label.** It used to locate the observation by
      matching five identity columns and taking `.iloc[0]` of the result, which
      silently picked an arbitrary row whenever a curve had two observations at one
      timestamp. `build_training_dataset` returns a frame carrying the input's
      index, and the masked frame is a boolean slice of the same frame, so the
      label identifies the row exactly.
    * **The comparison list is derived.** See `leakage_comparison_columns`.
    """
    warnings: List[str] = []
    errors: List[str] = []

    if df_raw.empty:
        return ValidationResult("FAIL", [], ["Raw dataset is empty."], {})

    from backend.ml.feature_engineering_pipeline import feature_engineering_pipeline
    from backend.services.booking_curve_definition import (
        FALLBACK_TIMESTAMP_KEY,
        ORDERING_TIMESTAMP_KEY,
        ordering_timestamps,
        resolve_ordering_timestamp_column,
    )

    # The curve key, from the module that owns it. This was a four-column
    # hand-typed list with no per-flight component. The leak test itself survived
    # that — it masks by timestamp over the whole corpus and compares row-by-row by
    # index label, so any sampled row is a legitimate subject — but the *sampling*
    # did not: `len(g) >= 3` was measuring the depth of a pooled group, so on a
    # corpus where no real curve has three observations this still found groups of
    # three or more, sampled five of them, and reported `groups_tested: 5` with a
    # PASS. That is a claim of longitudinal coverage the corpus does not have,
    # published by the validator whose subject is booking curves.
    group_keys = list(BOOKING_CURVE_KEYS)
    missing = [k for k in group_keys if k not in df_raw.columns]
    if missing:
        return ValidationResult(
            "FAIL", [], [f"Cannot group curves: missing columns {missing}."], {})

    # The generators refuse a duplicated index, and this function aligns rows by
    # label, so own the labels rather than trusting the caller's.
    df_raw = df_raw.reset_index(drop=True)
    order_col = resolve_ordering_timestamp_column(df_raw)
    if order_col is None:
        return ValidationResult(
            "FAIL", [],
            ["No usable observation timestamp column, so the timeline cannot be "
             "masked and leakage cannot be tested."], {})

    df_raw = df_raw.assign(_leak_ts=ordering_timestamps(df_raw))
    unorderable = int(df_raw["_leak_ts"].isna().sum())
    if unorderable:
        warnings.append(
            f"{unorderable} of {len(df_raw)} observations have no parseable "
            f"observation time in either '{ORDERING_TIMESTAMP_KEY}' or "
            f"'{FALLBACK_TIMESTAMP_KEY}' and were excluded from the leakage check.")
    df_raw = df_raw[df_raw["_leak_ts"].notna()]
    if df_raw.empty:
        return ValidationResult(
            "FAIL", warnings,
            [f"No observation has a parseable observation time in either "
             f"'{ORDERING_TIMESTAMP_KEY}' or '{FALLBACK_TIMESTAMP_KEY}'."], {})

    df_raw_sorted = df_raw.sort_values(by=group_keys + ["_leak_ts"], kind="mergesort")
    ts_all = df_raw_sorted["_leak_ts"]
    corpus = df_raw_sorted.drop(columns=["_leak_ts"])

    grouped = corpus.groupby(group_keys, sort=False, dropna=False)
    test_groups = [g for _, g in grouped if len(g) >= 3]
    if not test_groups:
        warnings.append("No booking curves found with size >= 3. Skipping deep leakage check.")
        return ValidationResult("PASS", warnings, [], {"groups_tested": 0})

    def engineer(frame: pd.DataFrame, what: str) -> Optional[pd.DataFrame]:
        try:
            return feature_engineering_pipeline.build_training_dataset(
                frame, feature_set_version)
        except Exception as exc:  # recorded, never swallowed: status becomes FAIL
            errors.append(f"Feature engineering raised on the {what} frame: {exc!r}")
            return None

    df_features_full = engineer(corpus, "full")
    if df_features_full is None:
        return ValidationResult("FAIL", warnings, errors, {"groups_tested": 0})

    sampled_groups = test_groups[:5]
    leakage_detected = False
    compared_values = 0
    compared_columns = 0

    for group_df in sampled_groups:
        group_sorted = group_df.loc[ts_all.loc[group_df.index].sort_values(
            kind="mergesort").index]
        # The second observation on the curve: at least one row before it, and at
        # least one after it to hide.
        label = group_sorted.index[1]
        cut = ts_all.loc[label]

        masked_rows = corpus[ts_all.loc[corpus.index] <= cut]
        if len(masked_rows) == len(corpus):
            warnings.append(
                f"Masking at {cut} hid no observation, so the comparison for that "
                "curve could not discriminate anything.")
            continue

        df_features_masked = engineer(masked_rows, f"frame masked at {cut}")
        if df_features_masked is None:
            continue
        if label not in df_features_masked.index or label not in df_features_full.index:
            errors.append(f"Observation {label} is absent from an engineered frame.")
            continue

        cols = leakage_comparison_columns(df_features_full, df_features_masked)
        if not cols:
            errors.append(
                "No numeric engineered column is common to the full and masked "
                "frames, so this check compared nothing.")
            continue
        compared_columns = max(compared_columns, len(cols))

        row_full = df_features_full.loc[label]
        row_masked = df_features_masked.loc[label]
        for col in cols:
            compared_values += 1
            if _values_disagree(row_full[col], row_masked[col]):
                leakage_detected = True
                errors.append(
                    f"Target leakage detected! Feature '{col}' changed from "
                    f"{row_full[col]} to {row_masked[col]} when the "
                    f"{len(corpus) - len(masked_rows)} observations recorded after "
                    f"{cut} were masked, for observation {label} "
                    f"({group_sorted.iloc[1].get('airline_code')} "
                    f"{group_sorted.iloc[1].get('departure_date')})."
                )

    if not compared_values and not errors:
        errors.append(
            "The leakage check compared no values, so it cannot report PASS.")

    status = "FAIL" if leakage_detected or errors else "PASS"
    metrics = {
        "groups_tested": len(sampled_groups),
        "leakage_detected": leakage_detected,
        "features_compared": compared_columns,
        "values_compared": compared_values,
        "ordering_column": order_col,
    }

    return ValidationResult(status, warnings, errors, metrics)


# The number of errors a refusal quotes. The full list can run to one entry per
# leaking feature per sampled curve; the log line and the artifact metadata want
# enough to name the problem and not so much that either becomes unreadable.
LEAK_ERRORS_QUOTED = 6


def timeline_leak_verdict(
    df_raw: pd.DataFrame, feature_set_version: str
) -> Dict[str, Any]:
    """`validate_target_leakage` as a verdict a training run can act on.

    Two reasons this exists rather than the caller reading `.status` directly.

    **A PASS can mean the check did not run.** With no booking curve of three or
    more observations there is nothing to mask, so `validate_target_leakage`
    returns PASS with `groups_tested: 0` and a warning. That is the shape of a
    thin corpus — 100 observations of 100 distinct flights, each seen once — and
    it is exactly the corpus whose lag and rolling features are all NaN and whose
    route aggregates nothing has audited. Reading that PASS as a clean bill of
    health is the same defect as `leak_audit.get("clean", True)` in
    `price_model.evaluate_acceptance`: it credits a check that never happened.
    `ran` is therefore derived from `values_compared`, and `clean` requires both.

    **The verdict has to survive into an artifact.** The return value is plain
    JSON-serialisable data so it can be written into a horizon's metadata beside
    the acceptance record, which is what lets a reader of a `.pkl` a year from now
    see which audit permitted it to exist.

    The caller decides what to do about `clean is False`; nothing here logs or
    raises. `price_model.train()` refuses every horizon, because a leaking feature
    build is a property of the pipeline, not of one horizon's fit.
    """
    result = validate_target_leakage(df_raw, feature_set_version)
    metrics = result.metrics or {}
    values_compared = int(metrics.get("values_compared") or 0)
    ran = values_compared > 0
    return {
        "clean": bool(result.status == "PASS" and ran),
        "ran": ran,
        "status": result.status,
        "feature_set_version": feature_set_version,
        "groups_tested": int(metrics.get("groups_tested") or 0),
        "features_compared": int(metrics.get("features_compared") or 0),
        "values_compared": values_compared,
        "ordering_column": metrics.get("ordering_column"),
        "raw_observations": int(len(df_raw)),
        "errors": list(result.errors[:LEAK_ERRORS_QUOTED]),
        "error_count": len(result.errors),
        "warnings": list(result.warnings[:LEAK_ERRORS_QUOTED]),
    }


# ── Contemporaneous leakage ──────────────────────────────────────────────────
# `validate_target_leakage` masks the observations recorded *after* a row's own
# timestamp, so by construction it cannot discriminate anything a feature reads
# from a row recorded at the same instant: those rows survive every mask it
# builds. It passes over that whole class. The two checks below cover it from
# opposite ends — one asks what the features know about the label, the other asks
# whose observations a feature is allowed to see.

# An exact affine copy of the label explains it to machine precision. The bound
# is deliberately this tight rather than 0.99: fares are sticky, so a legitimate
# price feature on a short corpus really can reach r² = 0.99 against a fare seven
# days out, and an error bound low enough to catch that would fire on honest
# data. What no honest feature reaches is a *numerically exact* linear relation,
# which is what `target * 2 + 3` — or the label itself under another name —
# produces. The 0.999 band is reported as a named warning instead of an error, so
# a human sees it without the gate crying wolf.
AFFINE_R2_ERROR_CEILING = 0.99999
AFFINE_R2_WARN_CEILING = 0.999
# A feature can be a copy of the label without being affine in it: `min(target,
# cap)` is neither affine nor innocent, and neither is a copy that NaNs out on a
# few rows. Measured separately, as a fraction of the rows where both are known.
AFFINE_EXACT_FRACTION_CEILING = 0.99
AFFINE_EXACT_TOLERANCE = 1e-6
# Below this many paired rows, r² = 1.0 is arithmetic rather than evidence: two
# points always lie on a line, and three nearly do.
MIN_AFFINE_ROWS = 8

# Feature categories whose definitions in `feature_metadata` say the value is
# computed across the cross-section: the live snapshot, or the route/airline
# history including the rows stamped at this instant. Only these may change when
# a *different* flight's simultaneous observation is removed from the corpus.
#
# Everything else is keyed on the five-part booking-curve key or on the calendar,
# so another flight's row must not enter its window. That is exactly the defect
# `attach_future_target` raises about — a four-key join pools every flight on the
# route into one curve — and no timeline mask can see it, because a simultaneous
# row is never on the future side of any cut.
CATEGORIES_READING_THE_CROSS_SECTION = frozenset({"market", "route", "airline"})


def feature_categories(feature_set_version: str) -> Dict[str, str]:
    """`{feature name: declared category}` for one feature set.

    Read from `feature_metadata` rather than restated here, for the same reason
    `leakage_comparison_columns` derives its list: a second copy of the contract
    is a copy that will disagree with the first one by the next feature.
    """
    from backend.ml.feature_metadata import FEATURE_SET_V1, LEGACY_FEATURE_SET
    sets = {"legacy": LEGACY_FEATURE_SET, "feature_set_v1": FEATURE_SET_V1}
    if feature_set_version not in sets:
        raise ValueError(f"Unknown feature set version: '{feature_set_version}'")
    return {f.name: f.category for f in sets[feature_set_version]}


def validate_label_independence(
    df_labelled: pd.DataFrame,
    feature_set_version: str,
    target_col: str = "target_price",
) -> ValidationResult:
    """No feature may be an affine function of the supervised label.

    The timeline check cannot see this class at all. It compares a row's features
    against the same row's features computed from a truncated corpus; a column
    that simply *is* the label under another name is identical in both frames and
    passes. That is not hypothetical for this repository — `target_price` was
    assigned from `price` on the same row for horizon 0, and the four-key label
    join put another flight's later fare into the label while every price feature
    kept reading its own.

    Measured as Pearson r² of the label on each numeric feature, which for a
    simple linear fit with an intercept *is* the R² of that fit — no regression is
    fitted here, and none needs to be. Two errors and one warning come out of it:
    a numerically exact affine relation, a feature equal to the label on almost
    every row, and the 0.999-to-0.99999 band reported by name for review.

    Deliberately overlapping `price_model.audit_feature_leakage`, and not
    replacing it. That one fits a single-feature XGBoost probe on the train fold
    and scores it on the test fold, so it sees non-linear dependence this cannot —
    but it needs xgboost, sklearn and an already-split dataset, so it cannot run
    in the validation harness or in CI, and it reports a ceiling on test R² rather
    than an exact-copy verdict. Two oracles over one property, with different
    dependencies and different failure modes, is the point.
    """
    warnings: List[str] = []
    errors: List[str] = []

    if df_labelled.empty:
        return ValidationResult("FAIL", [], ["Labelled dataset is empty."], {})
    if target_col not in df_labelled.columns:
        return ValidationResult(
            "FAIL", [],
            [f"Missing '{target_col}': there is no label to test independence "
             f"from, so this check cannot report PASS."], {})

    y = pd.to_numeric(df_labelled[target_col], errors="coerce")
    known = int(y.notna().sum())
    if known < MIN_AFFINE_ROWS:
        return ValidationResult(
            "FAIL", [],
            [f"Only {known} of {len(df_labelled)} rows carry a numeric "
             f"'{target_col}', below the {MIN_AFFINE_ROWS} needed to measure "
             f"dependence."], {"rows_labelled": known})
    if y.dropna().nunique() < 2:
        return ValidationResult(
            "FAIL", [],
            [f"The label is constant across all {known} labelled rows, so no "
             f"feature's dependence on it can be measured."],
            {"rows_labelled": known})

    try:
        categories = feature_categories(feature_set_version)
    except ValueError as exc:
        return ValidationResult("FAIL", [], [str(exc)], {})

    per_feature: Dict[str, Any] = {}
    for col in df_labelled.columns:
        if col == target_col or col in LEAKAGE_IDENTITY_COLUMNS:
            continue
        if not pd.api.types.is_numeric_dtype(df_labelled[col]):
            continue
        paired = pd.DataFrame({
            "_x": pd.to_numeric(df_labelled[col], errors="coerce"), "_y": y,
        }).dropna()
        entry: Dict[str, Any] = {
            "rows": int(len(paired)), "r2": None, "exact_fraction": None,
            "category": categories.get(col),
        }
        if len(paired) < MIN_AFFINE_ROWS:
            entry["skipped"] = (f"{len(paired)} paired rows, below "
                                f"{MIN_AFFINE_ROWS}")
        elif paired["_x"].nunique() < 2:
            entry["skipped"] = "constant over the paired rows"
        else:
            r = paired["_x"].corr(paired["_y"])
            entry["r2"] = None if pd.isna(r) else round(float(r) ** 2, 9)
            entry["exact_fraction"] = round(float(
                ((paired["_x"] - paired["_y"]).abs()
                 <= AFFINE_EXACT_TOLERANCE).mean()), 6)
        per_feature[col] = entry

    scored = {c: e for c, e in per_feature.items() if e["r2"] is not None}
    if not scored:
        errors.append(
            f"No feature could be measured against the label over "
            f"{len(df_labelled)} rows, so this check compared nothing and cannot "
            f"report PASS.")

    # Whether the caller passed the frame this check is about. `attach_future_target`
    # labels the *raw* frame; `training_dataset_builder.build` then copies the label
    # onto the *engineered* frame, and only the second one carries the features. Hand
    # this function the first and almost every column it sees is an identity column
    # it skips by design, so it returns PASS having measured `stops` — measured, not
    # supposed: on a four-flight fixture the raw frame probes exactly one feature.
    # A blind run must not be able to look like a clean one.
    declared_probeable = sorted(set(categories) - set(LEAKAGE_IDENTITY_COLUMNS))
    declared_scored = sorted(set(declared_probeable) & set(scored))
    if declared_probeable and not declared_scored:
        errors.append(
            f"None of the {len(declared_probeable)} probeable features declared by "
            f"'{feature_set_version}' is present and measurable in this frame, so "
            f"nothing this check compared was a feature the model trains on. Pass "
            f"the engineered frame carrying '{target_col}', not the raw corpus.")
    elif len(declared_scored) * 2 < len(declared_probeable):
        warnings.append(
            f"Only {len(declared_scored)} of {len(declared_probeable)} probeable "
            f"declared features were measurable here; the rest were absent, "
            f"constant, or too sparse. The comparison is thinner than the feature "
            f"set.")

    affine = sorted((c for c, e in scored.items()
                     if e["r2"] >= AFFINE_R2_ERROR_CEILING),
                    key=lambda c: -scored[c]["r2"])
    copies = sorted(c for c, e in scored.items()
                    if e["exact_fraction"] >= AFFINE_EXACT_FRACTION_CEILING)
    suspect = sorted((c for c, e in scored.items()
                      if AFFINE_R2_WARN_CEILING <= e["r2"] < AFFINE_R2_ERROR_CEILING),
                     key=lambda c: -scored[c]["r2"])

    for col in affine:
        errors.append(
            f"Feature '{col}' is an affine function of '{target_col}': r2="
            f"{scored[col]['r2']} over {scored[col]['rows']} paired rows "
            f"(limit {AFFINE_R2_ERROR_CEILING}). A feature that is the label "
            f"rescaled is the label.")
    for col in copies:
        if col in affine:
            continue
        errors.append(
            f"Feature '{col}' equals '{target_col}' on "
            f"{scored[col]['exact_fraction']:.1%} of the "
            f"{scored[col]['rows']} rows where both are known (limit "
            f"{AFFINE_EXACT_FRACTION_CEILING:.0%}).")
    for col in suspect:
        warnings.append(
            f"Feature '{col}' explains {scored[col]['r2']:.6f} of the label as a "
            f"straight line over {scored[col]['rows']} rows. Below the "
            f"{AFFINE_R2_ERROR_CEILING} error bound, above {AFFINE_R2_WARN_CEILING}: "
            f"sticky fares can do this, so it is named rather than refused.")

    r2_values = [e["r2"] for e in scored.values()]
    return ValidationResult(
        "FAIL" if errors else ("WARNING" if warnings else "PASS"),
        warnings, errors,
        {
            "rows_labelled": known,
            "features_probed": len(scored),
            "features_unprobed": sorted(set(per_feature) - set(scored)),
            "declared_probeable": len(declared_probeable),
            "declared_scored": declared_scored,
            "max_r2": max(r2_values) if r2_values else None,
            "affine_features": affine,
            "label_copies": copies,
            "suspect_features": suspect,
            "error_ceiling": AFFINE_R2_ERROR_CEILING,
            "warn_ceiling": AFFINE_R2_WARN_CEILING,
            "per_feature": per_feature,
        })


def validate_curve_key_isolation(
    df_raw: pd.DataFrame,
    feature_set_version: str,
    max_cases: int = 5,
) -> ValidationResult:
    """A curve feature must ignore another flight's simultaneous observation.

    Take a row, find the observations of *other booking curves* recorded on the same
    route at the same instant, remove exactly those from the corpus, and rebuild.
    Every feature of that row whose declared category is not in
    `CATEGORIES_READING_THE_CROSS_SECTION` must be unchanged: it is keyed on the
    five-part booking-curve key, or on the calendar, so another curve's quote is not
    in its window. A different flight number is a different curve, and so is a
    different departure date on the same flight.

    This is the blind spot of `validate_target_leakage` stated as a check. That
    one masks rows recorded after a cut; a simultaneous row is on neither side of
    any cut it draws, so pooling curves together is invisible to it — and pooling
    curves together is not a hypothetical defect here. It is the one
    `attach_future_target` refuses a four-key frame over, because the label join
    had it: `flight_number` was appended only inside a branch that was never true,
    so one flight's features were paired with another flight's later fare.

    One way this check can pass without checking anything, and it is the reachable
    one: if no route carries two curves at one instant there is nothing to remove, so
    no case is built. `cases_tested` is reported for that, and `curve_isolation_
    verdict` derives `ran` from it rather than from the PASS. Measured on a corpus of
    one flight per route: PASS, `cases_tested` 0, `ran` False.

    Three further tripwires below — nothing compared, nothing populated compared,
    no cross-sectional feature moved — are arithmetic, and on `feature_set_v1` none
    of them can fire. Measured, not assumed: the eight `temporal` features are
    calendar-derived and therefore populated on every row, and removing a same-instant
    row moves nineteen of the thirty declared `market`/`route`/`airline` features, so
    a corpus reduced to a single search snapshot still reports 115 populated
    comparisons and still catches four-key pooling through `observation_count`. The
    first two are kept for a feature set that drops those families. The third is a
    warning rather than an error, because `legacy` is a measured counterexample to the
    inference it used to make: of the six cross-sectional features it declares, three
    are identity codes the numeric comparison never sees and the three that remain are
    per-row functions no removal can move, yet the same corpus under a pooling
    regression still FAILs, so no movement was never evidence of no power.

    The load-bearing risk is elsewhere, and it cost three rewrites: see the comment on
    case ranking. A check that removes something and compares can be flawless in its
    comparison and still blind, because it chose a row whose values could not move.
    """
    warnings: List[str] = []
    errors: List[str] = []

    if df_raw.empty:
        return ValidationResult("FAIL", [], ["Raw dataset is empty."], {})

    from backend.ml.feature_engineering_pipeline import feature_engineering_pipeline
    from backend.services.booking_curve_definition import (
        BOOKING_CURVE_KEYS,
        FALLBACK_TIMESTAMP_KEY,
        ORDERING_TIMESTAMP_KEY,
        ordering_timestamps,
        resolve_ordering_timestamp_column,
    )

    missing = [k for k in BOOKING_CURVE_KEYS if k not in df_raw.columns]
    if missing:
        return ValidationResult(
            "FAIL", [],
            [f"Cannot test curve isolation: the frame is missing booking-curve "
             f"key column(s) {missing}, so two flights cannot be told apart."], {})

    try:
        categories = feature_categories(feature_set_version)
    except ValueError as exc:
        return ValidationResult("FAIL", [], [str(exc)], {})

    df_raw = df_raw.reset_index(drop=True)
    order_col = resolve_ordering_timestamp_column(df_raw)
    if order_col is None:
        return ValidationResult(
            "FAIL", [],
            ["No usable observation timestamp column, so 'the same instant' has "
             "no meaning and simultaneity cannot be tested."], {})

    ts = ordering_timestamps(df_raw)
    unorderable = int(ts.isna().sum())
    if unorderable:
        warnings.append(
            f"{unorderable} of {len(df_raw)} observations have no parseable "
            f"observation time in either '{ORDERING_TIMESTAMP_KEY}' or "
            f"'{FALLBACK_TIMESTAMP_KEY}' and were excluded from the isolation check.")
    corpus = df_raw[ts.notna()]
    ts = ts[ts.notna()]
    if corpus.empty:
        return ValidationResult(
            "FAIL", warnings,
            [f"No observation has a parseable observation time in either "
             f"'{ORDERING_TIMESTAMP_KEY}' or '{FALLBACK_TIMESTAMP_KEY}'."], {})

    # A "cross-section" is one route at one instant. Two of its rows belong to
    # different booking curves when any of the five curve keys differs — a
    # different flight number, and also a different departure date, which is a
    # different curve for the same reason.
    identity = corpus[list(BOOKING_CURVE_KEYS)].astype(str).agg("\x1f".join, axis=1)
    # 1-based position of each observation along its own curve. A row at position 1
    # has no prior observation, so its lag and rolling features are NaN and moving
    # them is not possible; a case built on such a row cannot discriminate.
    position = ts.groupby(identity).rank(method="first")
    section_keys = pd.DataFrame({
        "o": corpus["origin_code"].astype(str),
        "d": corpus["destination_code"].astype(str),
        "t": ts,
    })

    # Which cases get built matters more than how many, and three successive
    # orderings of them measured nothing. Taking the first five sections in (origin,
    # destination, instant) order sampled only BOM–BLR on a corpus whose one
    # multi-flight route was DEL–BOM, because "BOM" sorts first. Ranking by section
    # width and breaking ties alphabetically then picked the 6E flight out of a
    # section holding two AI flights and one 6E — and 6E, the only 6E on the route,
    # is the one flight a four-key join does not pool. Preferring the alphabetically
    # first of the two AI flights picked the one that sorts *earlier* at that
    # instant, and a rolling window over the last ten observations up to and
    # including this row does not move when a row *after* it is removed. All three
    # reported a deliberately reintroduced four-key pooling regression as clean,
    # while engineering that corpus under the regression moves eleven curve features.
    #
    # So: a candidate case per distinct curve in the cross-section, not one per
    # cross-section, ranked by how nearly the target collides with a sibling — the
    # number of the five key parts it shares with the closest observation of a
    # different curve at the same instant. Four shared parts is a curve one dropped
    # key away from being pooled with another, which is the join this check exists to
    # catch; three is a coincidence of route and date. Then position along its own
    # curve, because a row at position 1 has NaN lags that cannot move, and then
    # position within the cross-section, because siblings removed from *before* a row
    # are the ones that shift a trailing window. Routes are interleaved last, so a
    # corpus whose nearest collisions all sit on one route still spends cases
    # elsewhere.
    keys = corpus[list(BOOKING_CURVE_KEYS)].astype(str)
    # A cross-section on one route at one instant is a handful of flights. The scan
    # below is quadratic in the section, so it is capped — deterministically, by
    # sorted identity — rather than left to a pathological corpus to make slow.
    MAX_SECTION_SCAN = 60
    ranked: List[Any] = []
    for _, section in section_keys.groupby(["o", "d", "t"], sort=True, dropna=False):
        ids = identity.loc[section.index]
        if ids.nunique() < 2:
            continue
        scan = sorted(section.index, key=lambda i: (identity[i], str(i)))[:MAX_SECTION_SCAN]
        rows = {i: keys.loc[i].tolist() for i in scan}
        order = {i: k for k, i in enumerate(section.index)}
        seen: set = set()
        for i in scan:
            if identity[i] in seen:
                continue
            others = [j for j in scan if identity[j] != identity[i]]
            if not others:
                continue
            seen.add(identity[i])
            nearest = max(
                sum(1 for a, b in zip(rows[i], rows[j]) if a == b) for j in others)
            siblings = [j for j in section.index if identity[j] != identity[i]]
            route = (section_keys.at[i, "o"], section_keys.at[i, "d"])
            ranked.append(((-nearest, -float(position[i]), -order[i],
                            str(section_keys.at[i, "t"]), identity[i]),
                           route, i, siblings))
    ranked.sort(key=lambda entry: entry[0])

    by_route: Dict[Any, List[Any]] = {}
    for _, route, label, siblings in ranked:
        by_route.setdefault(route, []).append((label, siblings))
    cases: List[Any] = []
    while len(cases) < max_cases and any(by_route.values()):
        for route in sorted(by_route):
            if by_route[route] and len(cases) < max_cases:
                cases.append(by_route[route].pop(0))

    if not cases:
        warnings.append(
            "No route has two different booking curves observed at the same "
            "instant, so the isolation comparison had nothing to remove.")
        return ValidationResult("PASS", warnings, [], {
            "cases_tested": 0, "cases_available": 0, "values_compared": 0,
            "populated_compared": 0, "cross_sectional_moved": [],
            "uncategorised_compared": [], "ordering_column": order_col})

    def engineer(frame: pd.DataFrame, what: str) -> Optional[pd.DataFrame]:
        try:
            return feature_engineering_pipeline.build_training_dataset(
                frame, feature_set_version)
        except Exception as exc:  # recorded, never swallowed: status becomes FAIL
            errors.append(f"Feature engineering raised on the {what} frame: {exc!r}")
            return None

    full = engineer(corpus, "full")
    if full is None:
        return ValidationResult("FAIL", warnings, errors, {"cases_tested": 0})

    values_compared = 0
    populated_compared = 0
    cross_sectional_moved: set = set()
    uncategorised_compared: set = set()

    for label, siblings in cases:
        reduced = corpus.drop(index=siblings)
        masked = engineer(reduced, f"frame without {len(siblings)} simultaneous sibling(s)")
        if masked is None:
            continue
        if label not in masked.index or label not in full.index:
            errors.append(f"Observation {label} is absent from an engineered frame.")
            continue
        cols = leakage_comparison_columns(full, masked)
        if not cols:
            errors.append(
                "No numeric engineered column is common to the two frames, so "
                "this comparison compared nothing.")
            continue
        row_full, row_masked = full.loc[label], masked.loc[label]
        for col in cols:
            # An undeclared category is held to the *stricter* standard rather
            # than excused: a column the metadata does not describe is one nobody
            # has claimed reads the cross-section, so it must not move.
            if col not in categories:
                uncategorised_compared.add(col)
            cross = categories.get(col) in CATEGORIES_READING_THE_CROSS_SECTION
            if not cross:
                values_compared += 1
                if not pd.isna(row_full[col]):
                    populated_compared += 1
            if not _values_disagree(row_full[col], row_masked[col]):
                continue
            if cross:
                cross_sectional_moved.add(col)
                continue
            declared = (f"category {categories[col]!r}" if col in categories
                        else "no declared category in "
                             f"'{feature_set_version}' metadata")
            errors.append(
                f"Curve isolation broken: feature '{col}' ({declared}) changed "
                f"from {row_full[col]} to {row_masked[col]} when "
                f"{len(siblings)} simultaneous observation(s) of other booking "
                f"curves on the same route were removed. A feature that is not "
                f"declared cross-sectional is reading another curve's history, "
                f"for observation {label}.")

    # Two arithmetic tripwires, and one measurement that is deliberately not one.
    # Neither error below can fire on `feature_set_v1` — the docstring records the
    # measurement — and they are not the thing protecting this check from vacuity;
    # `cases_tested` is. What they protect is a future feature set that drops the
    # calendar or the market families, in which case a comparison really could end up
    # with nothing populated on either side. `and not errors` on each keeps a real
    # isolation failure at the front of the list rather than buried behind a note
    # about the corpus.
    if not values_compared and not errors:
        errors.append(
            "The curve-isolation check compared no feature outside "
            f"{sorted(CATEGORIES_READING_THE_CROSS_SECTION)}, so it cannot report "
            "PASS.")
    if values_compared and not populated_compared and not errors:
        errors.append(
            f"All {values_compared} curve-keyed values compared were NaN in the "
            f"full frame, so 'unchanged' was true of nothing. This corpus cannot "
            f"discriminate pooling; it is not evidence of isolation.")
    # "No cross-sectional feature moved" is a warning, not an error, and the reason is
    # measured. It was an error, on the argument that a removal which moves nothing
    # proves nothing. That inference is false, and `legacy` is the counterexample: of
    # the six cross-sectional features it declares, `origin_code`, `destination_code`
    # and `airline_code` are non-numeric and never reach the comparison, and the three
    # that do — `demand_score`, `seasonality_factor`, `is_live` — are per-row functions
    # that no removal can move. So every honest `legacy` corpus tripped this line and
    # FAILed. `model_registry.feature_set_version` returns `"legacy"` for any artifact
    # whose metadata records it, so as an error this refused to let a legacy model be
    # retrained, ever. The same corpus under a four-key pooling regression still FAILs,
    # naming `price_change_1d` and `price_change_3d`: the check has power on `legacy`,
    # and the absence of cross-sectional movement was never evidence that it did not.
    if not cross_sectional_moved:
        warnings.append(
            "Removing another flight's simultaneous observation moved no feature "
            f"declared cross-sectional in '{feature_set_version}' metadata. That is "
            "expected of a feature set whose cross-sectional features are per-row "
            "functions; it is reported because it means this run has no positive "
            "control, and the isolation claim rests on the curve-keyed comparison "
            "alone.")

    # FAIL or PASS, never WARNING, matching `validate_target_leakage` — because
    # `curve_isolation_verdict` refuses training on anything short of PASS. Two
    # warnings are reachable: rows with no parseable observation timestamp, which is
    # a data-quality note `validate_chronology` owns, and the missing positive
    # control above. Neither is a reason to refuse to train.
    return ValidationResult(
        "FAIL" if errors else "PASS",
        warnings, errors,
        {
            "cases_tested": len(cases),
            "cases_available": len(ranked),
            "values_compared": values_compared,
            "populated_compared": populated_compared,
            "cross_sectional_moved": sorted(cross_sectional_moved),
            "uncategorised_compared": sorted(uncategorised_compared),
            "ordering_column": order_col,
        })


def label_independence_verdict(
    df_labelled: pd.DataFrame, feature_set_version: str, horizon: int
) -> Dict[str, Any]:
    """`validate_label_independence` as a verdict a training run can act on.

    Same two reasons `timeline_leak_verdict` exists, with the same two answers:
    `ran` is derived from what was actually measured rather than from the status,
    and the return value is plain JSON so it can be written into the horizon's
    metadata beside the acceptance record.

    Per horizon, unlike the timeline and isolation audits. Those are properties of
    the raw corpus and the feature pipeline, which every horizon shares; this one
    is a property of the label, and the label is what the horizon chooses. A
    feature that is innocent against a fare 7 days out can be the fare itself at
    horizon 0 — that exact substitution is in this repository's history.
    """
    result = validate_label_independence(df_labelled, feature_set_version)
    metrics = result.metrics or {}
    probed = int(metrics.get("features_probed") or 0)
    declared_scored = list(metrics.get("declared_scored") or [])
    ran = probed > 0 and bool(declared_scored)
    return {
        "clean": bool(result.status in ("PASS", "WARNING") and ran),
        "ran": ran,
        "status": result.status,
        "feature_set_version": feature_set_version,
        "horizon": int(horizon),
        "rows_labelled": int(metrics.get("rows_labelled") or 0),
        "features_probed": probed,
        "declared_probeable": int(metrics.get("declared_probeable") or 0),
        "declared_scored": len(declared_scored),
        "max_r2": metrics.get("max_r2"),
        "affine_features": list(metrics.get("affine_features") or []),
        "label_copies": list(metrics.get("label_copies") or []),
        "suspect_features": list(metrics.get("suspect_features") or []),
        "error_ceiling": AFFINE_R2_ERROR_CEILING,
        "labelled_rows_supplied": int(len(df_labelled)),
        "errors": list(result.errors[:LEAK_ERRORS_QUOTED]),
        "error_count": len(result.errors),
        "warnings": list(result.warnings[:LEAK_ERRORS_QUOTED]),
    }


def curve_isolation_verdict(
    df_raw: pd.DataFrame, feature_set_version: str
) -> Dict[str, Any]:
    """`validate_curve_key_isolation` as a verdict a training run can act on.

    `clean` requires a PASS *and* that the comparison had power: at least one case
    built, at least one curve-keyed value compared, and at least one of those values
    populated rather than NaN on both sides. A corpus of single-observation curves
    satisfies "no curve feature moved" vacuously, and that is the corpus this project
    actually has least of — which is precisely why it must not be the corpus that buys
    a clean verdict.

    Warnings do not enter `clean`, and two are reachable: rows with no parseable
    observation timestamp, a data-quality finding `validate_chronology` owns, and a
    run in which no cross-sectional feature moved, which is a missing positive control
    rather than a defect — `legacy` produces it on every corpus. Both are quoted in
    the verdict so a reader of the metadata sees them.
    """
    result = validate_curve_key_isolation(df_raw, feature_set_version)
    metrics = result.metrics or {}
    cases = int(metrics.get("cases_tested") or 0)
    values = int(metrics.get("values_compared") or 0)
    populated = int(metrics.get("populated_compared") or 0)
    ran = cases > 0 and values > 0 and populated > 0
    return {
        "clean": bool(result.status == "PASS" and ran),
        "ran": ran,
        "status": result.status,
        "feature_set_version": feature_set_version,
        "cases_tested": cases,
        "cases_available": int(metrics.get("cases_available") or 0),
        "values_compared": values,
        "populated_compared": populated,
        "cross_sectional_moved": list(metrics.get("cross_sectional_moved") or []),
        "uncategorised_compared": list(metrics.get("uncategorised_compared") or []),
        "ordering_column": metrics.get("ordering_column"),
        "raw_observations": int(len(df_raw)),
        "errors": list(result.errors[:LEAK_ERRORS_QUOTED]),
        "error_count": len(result.errors),
        "warnings": list(result.warnings[:LEAK_ERRORS_QUOTED]),
    }


def compute_health_metrics(df_raw: pd.DataFrame) -> ValidationResult:
    """Computes booking curve depth, coverage, singleton curves, and missing route/airline counts."""
    warnings = []
    errors = []
    
    if df_raw.empty:
        return ValidationResult("FAIL", [], ["Dataset is empty."], {})
        
    # Every depth figure below — `avg_observations_per_curve`, the `pct_ge_*`
    # ladder, `max_unique_dates` — is computed over these groups, so the key decides
    # what they mean. It was a four-column hand-typed list carrying no per-flight
    # component, which pools all of a carrier's departures on a route and date into
    # one "curve": measured on a live 65-flight DEL-BOM fetch, 29 IndiGo departures
    # became a single group, so the published depth was roughly 29x the real thing.
    # These are the numbers a reader consults to decide whether the corpus has
    # enough longitudinal history to train on, and they said yes.
    #
    # Unlike the other three grouping sites in this module, this one had no
    # missing-column guard at all: `groupby` on an absent column raises `KeyError`,
    # which would have turned an honest "no curve identity yet" report into a crash
    # for every frame collected before migration 001 adds `departure_time`.
    group_keys = list(BOOKING_CURVE_KEYS)
    missing_keys = [k for k in group_keys if k not in df_raw.columns]
    if missing_keys:
        return ValidationResult(
            "FAIL", [],
            [f"Cannot measure booking curve depth: the frame is missing "
             f"{', '.join(missing_keys)}. Grouping on the remaining columns would "
             f"pool distinct departures into one curve and report depth that no "
             f"curve has."], {})
    if "recorded_at" not in df_raw.columns:
        return ValidationResult(
            "FAIL", [],
            ["Cannot measure booking curve depth: no 'recorded_at' column, so "
             "observations cannot be placed on a timeline."], {})
    grouped = df_raw.groupby(group_keys)
    sizes = grouped.size()
    
    total_curves = len(sizes)
    avg_obs = float(sizes.mean()) if total_curves > 0 else 0.0
    median_obs = float(sizes.median()) if total_curves > 0 else 0.0
    max_obs = int(sizes.max()) if total_curves > 0 else 0
    
    singleton_curves = int((sizes == 1).sum())
    singleton_pct = (singleton_curves / total_curves * 100) if total_curves > 0 else 0.0
    
    pct_ge_2 = float((sizes >= 2).sum() / total_curves * 100) if total_curves > 0 else 0.0
    pct_ge_3 = float((sizes >= 3).sum() / total_curves * 100) if total_curves > 0 else 0.0
    pct_ge_7 = float((sizes >= 7).sum() / total_curves * 100) if total_curves > 0 else 0.0
    pct_ge_14 = float((sizes >= 14).sum() / total_curves * 100) if total_curves > 0 else 0.0
    
    # Compute unique recorded dates per curve
    df_raw_date = df_raw.copy()
    # `format="ISO8601"` for the reason recorded at `validate_chronology`.
    df_raw_date["rec_date"] = pd.to_datetime(
        df_raw_date["recorded_at"], format="ISO8601").dt.date
    unique_dates = df_raw_date.groupby(group_keys)["rec_date"].nunique()
    avg_unique_dates = float(unique_dates.mean()) if total_curves > 0 else 0.0
    max_unique_dates = int(unique_dates.max()) if total_curves > 0 else 0
    
    # Routes / Airlines lacking depth (missing or having average observations < 2)
    routes = df_raw["origin_code"] + "-" + df_raw["destination_code"]
    unique_routes = routes.unique()
    airlines = df_raw["airline_code"].unique()
    
    # Identify routes/airlines that average less than 2 observations per curve
    shallow_routes = []
    for r in unique_routes:
        o, d = r.split("-")
        r_sizes = sizes[sizes.index.get_level_values("origin_code") == o]
        r_sizes = r_sizes[r_sizes.index.get_level_values("destination_code") == d]
        if r_sizes.empty or r_sizes.mean() < 2.0:
            shallow_routes.append(r)
            
    shallow_airlines = []
    for a in airlines:
        a_sizes = sizes[sizes.index.get_level_values("airline_code") == a]
        if a_sizes.empty or a_sizes.mean() < 2.0:
            shallow_airlines.append(a)
            
    # Apply health thresholds
    if singleton_pct > 50.0:
        errors.append(f"Critical singleton curve percentage: {singleton_pct:.1f}% (limit: 50.0%).")
    elif singleton_pct > 30.0:
        warnings.append(f"High singleton curve percentage: {singleton_pct:.1f}% (threshold: 30.0%).")
        
    status = "FAIL" if errors else ("WARNING" if warnings else "PASS")
    metrics = {
        "total_curves": total_curves,
        "average_observations": avg_obs,
        "median_observations": median_obs,
        "maximum_observations": max_obs,
        "singleton_curves_pct": singleton_pct,
        "pct_ge_2": pct_ge_2,
        "pct_ge_3": pct_ge_3,
        "pct_ge_7": pct_ge_7,
        "pct_ge_14": pct_ge_14,
        "average_unique_recorded_dates": avg_unique_dates,
        "maximum_unique_recorded_dates": max_unique_dates,
        "shallow_routes_count": len(shallow_routes),
        "shallow_routes": shallow_routes,
        "shallow_airlines_count": len(shallow_airlines),
        "shallow_airlines": shallow_airlines
    }
    
    return ValidationResult(status, warnings, errors, metrics)


def compute_feature_coverage(df_features: pd.DataFrame) -> ValidationResult:
    """Computes coverage, standard deviation, and variance for every feature, flagging degenerate ones."""
    warnings = []
    errors = []
    
    if df_features.empty:
        return ValidationResult("FAIL", [], ["Engineered feature dataset is empty."], {})
        
    # Identity and bookkeeping columns, which the training frame carries but which
    # are not features. The identity half comes from `BOOKING_CURVE_KEYS` so that a
    # change to the curve key cannot leave a component of the identity being graded
    # for coverage and variance as though it were a feature. `flight_number` stays
    # named explicitly: it is no longer part of the key but the frame still carries
    # it, and it is still not a feature.
    non_feature_cols = set(BOOKING_CURVE_KEYS) | {
        "target_price", "training_weight",
        "recorded_date", "recorded_at", "recorded_datetime", "search_timestamp",
        "departure_date_dt", "recorded_date_shift",
        "flight_number", "id"
    }
    feature_cols = [c for c in df_features.columns if c not in non_feature_cols]
    
    feature_stats = {}
    
    for col in feature_cols:
        series = df_features[col]
        if not pd.api.types.is_numeric_dtype(series):
            continue
            
        total = len(series)
        null_count = int(series.isna().sum())
        non_null_count = total - null_count
        
        nan_pct = (null_count / total * 100) if total > 0 else 100.0
        populated_pct = 100.0 - nan_pct
        
        mean_val = float(series.mean()) if non_null_count > 0 else np.nan
        std_val = float(series.std()) if non_null_count > 1 else np.nan
        min_val = float(series.min()) if non_null_count > 0 else np.nan
        max_val = float(series.max()) if non_null_count > 0 else np.nan
        var_val = float(series.var()) if non_null_count > 1 else np.nan
        
        feature_stats[col] = {
            "nan_pct": nan_pct,
            "populated_pct": populated_pct,
            "mean": mean_val,
            "std": std_val,
            "min": min_val,
            "max": max_val,
            "variance": var_val
        }
        
        # Check thresholds
        if nan_pct == 100.0:
            warnings.append(f"Feature '{col}' is 100% NaN.")
        elif nan_pct > 80.0:
            warnings.append(f"High NaN percentage for feature '{col}': {nan_pct:.1f}%.")
            
        # Check constant / zero variance features
        if non_null_count > 1 and var_val == 0.0:
            errors.append(f"Degenerate constant feature detected: '{col}' has zero variance.")
            
    status = "FAIL" if errors else ("WARNING" if warnings else "PASS")
    
    return ValidationResult(status, warnings, errors, {"features": feature_stats})


def compute_target_quality(df_features: pd.DataFrame) -> ValidationResult:
    """Evaluates target price stats, checking for negatives, coverage, and duplicates."""
    warnings = []
    errors = []
    
    if "target_price" not in df_features.columns:
        return ValidationResult("FAIL", [], ["Missing target_price column in features dataframe."], {})
        
    series = df_features["target_price"]
    total = len(series)
    null_count = int(series.isna().sum())
    non_null_count = total - null_count
    
    coverage = (non_null_count / total * 100) if total > 0 else 0.0
    
    if coverage < 50.0:
        errors.append(f"Target price coverage is too low: {coverage:.1f}% (limit: 50.0%).")
    elif coverage < 80.0:
        warnings.append(f"Target price coverage is sub-optimal: {coverage:.1f}% (threshold: 80.0%).")
        
    mean_val = float(series.mean()) if non_null_count > 0 else np.nan
    median_val = float(series.median()) if non_null_count > 0 else np.nan
    std_val = float(series.std()) if non_null_count > 1 else np.nan
    min_val = float(series.min()) if non_null_count > 0 else np.nan
    max_val = float(series.max()) if non_null_count > 0 else np.nan
    
    # Check for negative values
    neg_count = int((series < 0.0).sum())
    if neg_count > 0:
        errors.append(f"Target price has negative values: {neg_count} records.")
        
    # Check duplicate targets
    dup_targets = int(series.duplicated().sum())
    dup_pct = (dup_targets / total * 100) if total > 0 else 0.0
    
    status = "FAIL" if errors else ("WARNING" if warnings else "PASS")
    metrics = {
        "total_targets": total,
        "populated_targets": non_null_count,
        "coverage_pct": coverage,
        "mean": mean_val,
        "median": median_val,
        "std": std_val,
        "min": min_val,
        "max": max_val,
        "negative_count": neg_count,
        "duplicate_count": dup_targets,
        "duplicate_pct": dup_pct
    }
    
    return ValidationResult(status, warnings, errors, metrics)


def detect_feature_drift(new_report: Dict[str, Any], history_dir: str) -> ValidationResult:
    """Compares current feature statistics to historical validation reports to detect data drift."""
    warnings = []
    errors = []
    
    if not os.path.exists(history_dir):
        return ValidationResult("PASS", ["No historical reports folder found for drift check."], [], {})
        
    files = [f for f in os.listdir(history_dir) if f.endswith(".json")]
    if not files:
        return ValidationResult("PASS", ["No historical reports found to compute feature drift."], [], {})
        
    files.sort()
    latest_hist_file = os.path.join(history_dir, files[-1])
    
    try:
        with open(latest_hist_file, "r") as f:
            hist_report = json.load(f)
    except Exception as e:
        return ValidationResult("WARNING", [f"Failed to load historical report: {e}"], [], {})
        
    # Compare feature statistics
    new_feats = new_report.get("coverage", {}).get("metrics", {}).get("features", {})
    hist_feats = hist_report.get("coverage", {}).get("metrics", {}).get("features", {})
    
    drift_features = []
    for col, stats in new_feats.items():
        if col in hist_feats:
            new_mean = stats.get("mean")
            hist_mean = hist_feats[col].get("mean")
            new_var = stats.get("variance")
            hist_var = hist_feats[col].get("variance")
            
            # Check for collapsed variance
            if hist_var is not None and hist_var > 0.01 and (new_var is None or new_var <= 0.0001):
                warnings.append(f"Collapsed variance warning for feature '{col}': historical {hist_var:.4f} -> current {new_var}.")
                
            # Check for mean drift (> 50% relative change and > 10.0 absolute change)
            if new_mean is not None and hist_mean is not None and hist_mean != 0.0:
                rel_diff = abs(new_mean - hist_mean) / abs(hist_mean)
                abs_diff = abs(new_mean - hist_mean)
                if rel_diff > 0.50 and abs_diff > 10.0:
                    warnings.append(
                        f"Mean drift detected for feature '{col}': historical {hist_mean:.2f} -> current {new_mean:.2f} "
                        f"(rel diff: {rel_diff*100:.1f}%)."
                    )
                    drift_features.append(col)
                    
    status = "WARNING" if warnings else "PASS"
    metrics = {
        "compared_file": os.path.basename(latest_hist_file),
        "drift_detected_count": len(drift_features),
        "drift_features": drift_features
    }
    
    return ValidationResult(status, warnings, errors, metrics)


def generate_validation_report(
    df_raw: pd.DataFrame,
    df_cleaned_raw: pd.DataFrame,
    df_features: pd.DataFrame,
    feature_set_version: str,
    history_dir: str | os.PathLike | None = None
) -> ValidationReport:
    """Orchestrates all checks, computes score, determines overall status, and persists report."""
    history_dir = str(DEFAULT_HISTORY_DIR if history_dir is None else history_dir)
    os.makedirs(history_dir, exist_ok=True)
    
    chrono_res = validate_chronology(df_raw)
    dup_res = validate_duplicates(df_raw, df_cleaned_raw)
    leakage_res = validate_target_leakage(df_raw, feature_set_version)
    health_res = compute_health_metrics(df_raw)
    coverage_res = compute_feature_coverage(df_features)
    target_res = compute_target_quality(df_features)
    
    new_report_dict = {
        "coverage": asdict(coverage_res)
    }
    drift_res = detect_feature_drift(new_report_dict, history_dir)
    
    # Calculate Readiness Score
    base_score = 100
    results = [chrono_res, dup_res, leakage_res, health_res, coverage_res, target_res, drift_res]
    for r in results:
        if r.status == "FAIL":
            base_score -= 20
        elif r.status == "WARNING":
            base_score -= 10
            
    readiness_score = max(0, min(100, base_score))
    
    if any(r.status == "FAIL" for r in results):
        overall_status = "FAIL"
    elif any(r.status == "WARNING" for r in results):
        overall_status = "WARNING"
    else:
        overall_status = "PASS"
        
    report = ValidationReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        feature_set_version=feature_set_version,
        overall_status=overall_status,
        readiness_score=readiness_score,
        chronology=chrono_res,
        duplicates=dup_res,
        leakage=leakage_res,
        health=health_res,
        coverage=coverage_res,
        target_quality=target_res,
        drift=drift_res
    )
    
    # Persist Report using unique date string to never overwrite
    filename = f"validation_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M%S')}.json"
    filepath = os.path.join(history_dir, filename)
    try:
        with open(filepath, "w") as f:
            f.write(report.to_json())
        logger.info(f"Saved validation report to: {filepath}")
    except Exception as e:
        logger.error(f"Failed to persist validation report: {e}")
        
    return report
