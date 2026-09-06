"""SkyMind — Production Training Pipeline Automated Regression Suite.

What this module used to assert, and why it was replaced:

`test_chronological_split_ordering` was documented as verifying "that training
fold timestamps are strictly earlier than test fold timestamps". It read a
metadata file under `if os.path.exists(...)` — vacuous when absent, which is the
normal state on a fresh checkout — and when present asserted the *string*
`"Chronological_Temporal_Split"` plus the presence of two keys. A positional
split on an unsorted frame writes exactly that string, exactly those keys, and
the same row counts.

`test_equivalent_accuracy_formula` computed `expected_eq_acc` from a hardcoded
MAPE of 4.44 and then never used it, guarding everything else behind
`if 1 in predictor.metrics` and `if "mape" in metrics`, so with the shipped
artifacts quarantined it asserted nothing at all.

`test_quality_gate_rejection_protection` asserted `predictor.models.get(0) is not
None` with the message "Horizon 0d model must exist" — impossible by design since
the leaked artifacts were quarantined — and then "verified quality gate logic"
with `assert len(low_obs_df) < MIN_OBSERVATIONS_THRESHOLD`, i.e. that 50 < 100,
over two literals the test wrote itself. It passed before and after the gate was
disabled by its own `and len(df_horizon) < 1000` conjunct.

The three subjects are now exercised against the functions that decide them:
`evaluate_acceptance` and `chronological_split`, both at module level in
`backend.ml.price_model` precisely so a test can reach them without a database,
a dataset builder or an XGBoost fit; and `mape_with_coverage`, the single
definition of the published error metric.

The tests that read a *trained artifact* are marked with `requires_forecast_metrics`
so they skip with a reason on a checkout that has no servable model, rather than
failing as if a feature were broken.
"""

import math

import numpy as np
import pandas as pd
import pytest

from backend.ml.metrics import mape_with_coverage
from backend.ml.price_model import (
    MAX_TEST_MAPE,
    MIN_TEST_R2,
    MIN_TEST_ROWS,
    STRUCTURALLY_UNCOMPUTED_FEATURES,
    audit_feature_coverage,
    baseline_skill,
    chronological_split,
    evaluate_acceptance,
    get_predictor,
)
from backend.services.confidence_policy import (
    metrics_for_horizon,
    resolve_published_accuracy,
)
from backend.services.booking_curve_definition import (
    BOOKING_CURVE_KEYS,
    lag_tolerance_days,
)
from backend.tests.model_availability import requires_forecast_metrics

CLEAN_AUDIT = {"clean": True, "suspect_features": []}
COMPLETE_COVERAGE = {"complete": True, "zero_coverage_unexpected": []}
# A model that halved the error of carrying the fare forward unchanged.
BEATS_BASELINE = {"available": True, "name": "persistence", "model_mae": 150.0,
                  "baseline_mae": 300.0, "improvement_pct": 0.5}


def accepting(**over):
    """Evaluation numbers that satisfy every criterion, so one can be spoiled."""
    args = dict(r2=0.62, mape=9.4, mape_rows=400, mape_excluded=0,
                test_rows=400, leak_audit=dict(CLEAN_AUDIT),
                coverage_audit=dict(COMPLETE_COVERAGE),
                baseline=dict(BEATS_BASELINE))
    args.update(over)
    return args


# ── The acceptance gate ───────────────────────────────────────────────────────
def test_acceptance_gate_accepts_a_model_that_meets_every_criterion():
    record = evaluate_acceptance(**accepting())
    assert record["passed"] is True
    assert record["failed_criteria"] == []
    assert sorted(record["criteria"]) == [
        "baseline_comparison_is_available",
        "beats_the_last_known_fare",
        "every_declared_feature_has_data",
        "no_single_feature_explains_the_target",
        "test_fold_large_enough_to_measure",
        "test_mape_at_or_below_ceiling",
        "test_mape_is_measurable",
        "test_r2_at_or_above_floor",
    ]


# ── The baseline a fare forecaster has to beat ────────────────────────────────
def test_a_model_that_loses_to_carrying_the_fare_forward_is_refused():
    """The gate `MIN_TEST_R2 = 0.0` could never be.

    R²'s denominator is the sum of squares about `mean(y_true)`, so "R² ≥ 0" says
    only "at least as good as one constant chosen with hindsight from the test
    labels". On a fare that barely moves that is nearly free. This model has
    R² 0.62 and a 9.4% MAPE — comfortably through every other criterion — and is
    still worse than assuming the fare will not change.
    """
    record = evaluate_acceptance(**accepting(baseline={
        "available": True, "name": "persistence", "model_mae": 420.0,
        "baseline_mae": 300.0, "improvement_pct": -0.4,
    }))
    assert record["passed"] is False
    assert record["failed_criteria"] == ["beats_the_last_known_fare"]
    # The record says better-than-what and by how much, not just that it failed.
    assert record["criteria"]["beats_the_last_known_fare"]["threshold"] == 300.0
    assert record["criteria"]["beats_the_last_known_fare"][
        "improvement_pct"] == -0.4
    assert record["baseline"]["baseline_mae"] == 300.0


def test_a_tie_with_the_baseline_is_not_an_improvement():
    """Equal error means carrying the fare forward is as good, so the fit adds nothing.

    Deliberately a strict comparison rather than a tolerance: a second numeric
    threshold here would be one more number nobody could source, and the promotion
    verdict in `backend.ml.benchmark` already owns the "by how much" question.
    """
    tie = dict(BEATS_BASELINE, model_mae=300.0, baseline_mae=300.0,
               improvement_pct=0.0)
    assert evaluate_acceptance(**accepting(baseline=tie))[
        "failed_criteria"] == ["beats_the_last_known_fare"]
    barely = dict(tie, model_mae=299.999999)
    assert evaluate_acceptance(**accepting(baseline=barely))["passed"] is True


def test_an_unavailable_baseline_fails_under_its_own_name():
    """"We could not compare" must not print as "the model lost".

    The two send an operator to different places: a missing last-known fare is a
    corpus or column problem, and losing to persistence is a feature-set problem.
    """
    record = evaluate_acceptance(**accepting(baseline={
        "available": False, "name": "persistence",
        "reason": "3 of 400 scored row(s) carry no last-known price",
    }))
    assert record["failed_criteria"] == [
        "baseline_comparison_is_available", "beats_the_last_known_fare"]
    assert record["criteria"]["baseline_comparison_is_available"]["reason"] == (
        "3 of 400 scored row(s) carry no last-known price")


def test_the_gate_cannot_be_switched_off_by_omitting_the_baseline():
    """`baseline` is required, not defaulted.

    Every other way of writing this — a default of `None`, or an `if baseline:`
    around the criterion — reproduces the defect this whole function exists to fix:
    the old gate was `if r2 < 0.0 and len(df_horizon) < 1000`, and its second
    conjunct switched it off for exactly the datasets that mattered.
    """
    args = accepting()
    args.pop("baseline")
    with pytest.raises(TypeError, match="baseline"):
        evaluate_acceptance(**args)


def test_baseline_skill_reads_the_benchmarks_own_persistence_definition():
    """One definition of persistence, in `backend.ml.benchmark`, read not recopied.

    A second implementation is how `naive_persistence` came to be
    `np.mean(y_true)` — the mean of the *test* labels — in the file that computed
    it, while the prose everywhere else described carrying a fare forward.
    """
    from backend.ml.benchmark import ModelBenchmark

    last_known = np.array([4000.0, 4200.0, 3900.0] * 20)
    y_true = last_known + 100.0            # every fare rose ₹100
    preds = last_known + 60.0              # so the model is ₹40 out
    result = ModelBenchmark().run(y_true, preds, y_last_known=last_known,
                                  y_train=y_true - 500.0)

    skill = baseline_skill(result, model_mae=40.0)
    assert skill["available"] is True
    assert skill["name"] == "persistence"
    assert skill["baseline_mae"] == pytest.approx(100.0)
    assert skill["improvement_pct"] == pytest.approx(0.6)
    assert evaluate_acceptance(**accepting(baseline=skill))["passed"] is True


def test_baseline_skill_carries_the_skip_reason_when_there_was_no_baseline():
    from backend.ml.benchmark import ModelBenchmark

    y_true = np.array([4000.0, 4200.0] * 30)
    result = ModelBenchmark().run(y_true, y_true + 25.0)   # no baseline inputs
    assert result.was_compared is False

    skill = baseline_skill(result, model_mae=25.0)
    assert skill["available"] is False
    assert "last" in skill["reason"].lower() or "price" in skill["reason"].lower()
    assert evaluate_acceptance(**accepting(baseline=skill))["passed"] is False


@pytest.mark.parametrize("test_rows", [100, 1000, 31537])
def test_acceptance_gate_is_not_disabled_by_a_large_dataset(test_rows):
    """The historical defect: `if r2 < 0.0 and len(df_horizon) < 1000`.

    The second conjunct switched the only acceptance criterion in the production
    path off for any dataset of 1000 rows or more. The shipped 0d and 1d artifacts
    were trained on 31,537 and 2,998 observations, so for those two it never fired.
    Parameterised over three sizes because a single small-fold case would have
    passed against the defect for its entire life.
    """
    record = evaluate_acceptance(**accepting(r2=-0.4, test_rows=test_rows))
    assert record["passed"] is False
    assert record["failed_criteria"] == ["test_r2_at_or_above_floor"]


def test_acceptance_gate_r2_floor_is_inclusive_and_binds_just_below():
    assert evaluate_acceptance(**accepting(r2=MIN_TEST_R2))["passed"] is True
    assert evaluate_acceptance(**accepting(r2=MIN_TEST_R2 - 1e-9))[
        "failed_criteria"] == ["test_r2_at_or_above_floor"]


def test_acceptance_gate_mape_ceiling_is_inclusive_and_binds_just_above():
    assert evaluate_acceptance(**accepting(mape=MAX_TEST_MAPE))["passed"] is True
    assert evaluate_acceptance(**accepting(mape=MAX_TEST_MAPE + 0.01))[
        "failed_criteria"] == ["test_mape_at_or_below_ceiling"]


def test_acceptance_gate_refuses_a_test_fold_too_small_to_measure():
    """The shipped 3d artifact: R² 0.707, recorded on a 27-row test fold."""
    record = evaluate_acceptance(**accepting(r2=0.707, test_rows=27))
    assert record["passed"] is False
    assert record["failed_criteria"] == ["test_fold_large_enough_to_measure"]
    detail = record["criteria"]["test_fold_large_enough_to_measure"]
    assert (detail["observed"], detail["threshold"]) == (27, MIN_TEST_ROWS)


def test_acceptance_gate_refuses_a_feature_set_the_leak_audit_flagged():
    record = evaluate_acceptance(**accepting(
        leak_audit={"clean": False, "suspect_features": ["price_change_1d"]}))
    assert record["failed_criteria"] == ["no_single_feature_explains_the_target"]
    assert record["criteria"]["no_single_feature_explains_the_target"][
        "observed"] == ["price_change_1d"]


def test_an_audit_that_never_ran_is_not_a_clean_verdict():
    """`bool(leak_audit.get("clean"))`, not `.get("clean", True)`.

    An empty dict is what a caller passes when the audit could not run. Defaulting
    it to True would accept a model on the strength of a check that did not happen.
    The same applies to the coverage audit.
    """
    assert evaluate_acceptance(**accepting(leak_audit={}))[
        "failed_criteria"] == ["no_single_feature_explains_the_target"]
    assert evaluate_acceptance(**accepting(coverage_audit={}))[
        "failed_criteria"] == ["every_declared_feature_has_data"]


def test_acceptance_gate_refuses_a_model_with_an_empty_declared_feature():
    """The `hour_of_day` case.

    It was NaN for 100% of every training frame — computed from a `price_history`
    column that did not exist — while the serving path supplied a real departure
    hour under the same name. Every other criterion was satisfied, so nothing
    stopped the artifact being written, and the metadata recorded no coverage
    figure that would have shown it.
    """
    record = evaluate_acceptance(**accepting(coverage_audit={
        "complete": False, "zero_coverage_unexpected": ["hour_of_day", "is_peak_hour"]}))
    assert record["passed"] is False
    assert record["failed_criteria"] == ["every_declared_feature_has_data"]
    assert record["criteria"]["every_declared_feature_has_data"]["observed"] == [
        "hour_of_day", "is_peak_hour"]


def test_an_unmeasurable_error_is_not_reported_as_an_excessive_one():
    """NaN MAPE fails measurability first, and the record says which.

    `nan <= MAX_TEST_MAPE` is False, so the ceiling alone already refused such a
    model — but `failed_criteria` would then have named a ceiling the model was
    never measured against.
    """
    record = evaluate_acceptance(**accepting(
        mape=float("nan"), mape_rows=0, mape_excluded=400))
    assert record["passed"] is False
    assert record["failed_criteria"] == [
        "test_mape_is_measurable", "test_mape_at_or_below_ceiling"]
    assert record["criteria"]["test_mape_at_or_below_ceiling"]["observed"] is None
    measurable = record["criteria"]["test_mape_is_measurable"]
    assert (measurable["observed"], measurable["excluded"]) == (0, 400)


def test_a_non_finite_r2_is_refused_rather_than_compared():
    assert evaluate_acceptance(**accepting(r2=float("inf")))["passed"] is False
    assert evaluate_acceptance(**accepting(r2=float("nan")))[
        "failed_criteria"] == ["test_r2_at_or_above_floor"]


def test_the_verdict_is_the_conjunction_and_every_failure_is_named():
    record = evaluate_acceptance(**accepting(r2=-1.0, test_rows=5))
    assert record["passed"] is False
    assert record["failed_criteria"] == [
        "test_r2_at_or_above_floor", "test_fold_large_enough_to_measure"]


# ── The feature-coverage audit ────────────────────────────────────────────────
def _folds(**cols):
    frame = pd.DataFrame(cols)
    return frame.iloc[:3], frame.iloc[3:]


def test_coverage_audit_reports_an_all_null_feature_and_fails_the_fit():
    train, test = _folds(
        price_change_1d=[10.0, -20.0, 5.0, 8.0, -3.0],
        hour_of_day=[np.nan] * 5,
    )
    audit = audit_feature_coverage(train, test, ["price_change_1d", "hour_of_day"])

    assert audit["zero_coverage_features"] == ["hour_of_day"]
    assert audit["zero_coverage_unexpected"] == ["hour_of_day"]
    assert audit["complete"] is False
    assert audit["per_feature"]["hour_of_day"]["train_coverage"] == 0.0
    assert audit["per_feature"]["price_change_1d"]["train_coverage"] == 1.0


def test_coverage_audit_does_not_fail_on_the_two_features_never_computed():
    """`demand_score` and `seasonality_factor` are null by construction.

    They are recorded as empty — the figure is still published in the metadata —
    but they do not fail the gate, because a gate that every run fails is a gate
    nobody keeps. Compute one and remove its entry from
    `STRUCTURALLY_UNCOMPUTED_FEATURES`; the exclusion is a named list, not a
    tolerance.
    """
    assert STRUCTURALLY_UNCOMPUTED_FEATURES == {"demand_score", "seasonality_factor"}
    train, test = _folds(
        demand_score=[np.nan] * 5,
        seasonality_factor=[np.nan] * 5,
        urgency=[0.5, 0.2, 0.1, 0.25, 0.125],
    )
    audit = audit_feature_coverage(
        train, test, ["demand_score", "seasonality_factor", "urgency"])

    assert audit["zero_coverage_features"] == ["demand_score", "seasonality_factor"]
    assert audit["zero_coverage_unexpected"] == []
    assert audit["complete"] is True


def test_coverage_audit_separates_constant_from_absent():
    """A feature present on every row with one value is useless, not broken.

    Recorded under `single_value_features` and deliberately not gated: `is_live`
    is legitimately constant in a corpus of live observations, and refusing that
    would be refusing the corpus rather than a defect.
    """
    train, test = _folds(is_live=[2.0] * 5, seats_available=[np.nan] * 5)
    audit = audit_feature_coverage(train, test, ["is_live", "seats_available"])

    assert audit["single_value_features"] == ["is_live"]
    assert "is_live" not in audit["zero_coverage_features"]
    assert audit["zero_coverage_unexpected"] == ["seats_available"]


# ── The chronological split ───────────────────────────────────────────────────
def _frame(days, price_start=4000):
    ts = pd.to_datetime(["2026-01-%02d" % d for d in days], utc=True)
    return pd.DataFrame({
        "_recorded_dt": ts,
        "target_price": [price_start + i for i in range(len(days))],
    })


def test_no_training_row_was_recorded_after_a_test_row():
    """The property the old test's name promised and its body never checked."""
    df = _frame(range(1, 21))
    shuffled = df.sample(frac=1.0, random_state=7).reset_index(drop=True)

    train, test, record = chronological_split(
        shuffled, timestamp_col="_recorded_dt", train_fraction=0.8)

    assert len(train) == 16 and len(test) == 4
    assert train["_recorded_dt"].max() <= test["_recorded_dt"].min()
    assert record["boundary_is_strict"] is True

    # The contrast that makes the assertion above meaningful: the positional
    # split this function replaced puts the latest observation in the training
    # fold whenever the input is not already sorted.
    n = int(len(shuffled) * 0.8)
    assert not (shuffled.iloc[:n]["_recorded_dt"].max()
                <= shuffled.iloc[n:]["_recorded_dt"].min())


def test_the_split_sorts_regardless_of_input_order():
    df = _frame(range(1, 11))
    from_sorted = chronological_split(
        df, timestamp_col="_recorded_dt", train_fraction=0.8)
    from_shuffled = chronological_split(
        df.sample(frac=1.0, random_state=3).reset_index(drop=True),
        timestamp_col="_recorded_dt", train_fraction=0.8)
    for a, b in zip(from_sorted[:2], from_shuffled[:2]):
        pd.testing.assert_frame_equal(a, b)
    assert from_sorted[2] == from_shuffled[2]


def test_a_straddled_boundary_is_reported_not_assumed():
    """Rows sharing a timestamp across the boundary are a real overlap.

    The model then trains on an observation recorded at the same instant as one it
    is scored on. `boundary_is_strict` records it so the artifact's metadata can
    be audited for it. It is the *report*; the fix is the embargo, and
    `test_the_embargo_separates_a_boundary_that_shared_a_timestamp` below shows
    the same frame coming out separated once one is asked for.
    """
    dup = pd.DataFrame({
        "_recorded_dt": pd.to_datetime(["2026-01-01"] * 5 + ["2026-01-02"] * 5,
                                       utc=True),
        "target_price": range(10),
    })
    clean = chronological_split(dup, timestamp_col="_recorded_dt",
                               train_fraction=0.5)[2]
    assert clean["boundary_is_strict"] is True

    straddled = chronological_split(dup, timestamp_col="_recorded_dt",
                                    train_fraction=0.8)[2]
    assert straddled["boundary_is_strict"] is False
    assert straddled["train_end"] == straddled["test_start"]


def test_the_split_refuses_a_frame_with_no_timestamp_column():
    df = _frame(range(1, 11)).drop(columns=["_recorded_dt"])
    with pytest.raises(KeyError, match="observation-timestamp column"):
        chronological_split(df, timestamp_col="_recorded_dt")


def test_the_split_record_describes_the_split_it_performed():
    record = chronological_split(_frame(range(1, 11)),
                                 timestamp_col="_recorded_dt",
                                 train_fraction=0.7)[2]
    assert record["n_total"] == 10
    assert record["n_train"] + record["n_test"] == record["n_total"]
    assert record["n_train"] == 7
    assert record["train_fraction"] == 0.7
    assert record["timestamp_column"] == "_recorded_dt"


# ── The label embargo ─────────────────────────────────────────────────────────
def _curve_frame(n=50, departures=("06:10:00", "19:45:00"), freq="12h"):
    """A frame with the five booking-curve keys and an observation timestamp.

    The per-flight key is `departure_time`, which is what `BOOKING_CURVE_KEYS` has
    named since 2026-09-03; it was `flight_number`. That is not cosmetic here:
    `_group_overlap` does `frame[col]` for every key it is handed, so with the column
    absent the four tests below raise `KeyError: 'departure_time'` before asserting
    anything — and if it had instead been tolerated, each would have reported an
    overlap census over one pooled curve rather than the two the fixture describes.

    `flight_number` stays on the frame, still varying per departure. It is a real
    column of `price_history` and nothing may key on it; leaving it here means a
    regression that reached for it would still produce two groups and hide.

    The value is a local departure instant on the departure date, the shape migration
    001 declares (`TIMESTAMP WITHOUT TIME ZONE`), not a bare clock time.
    """
    ts = pd.date_range("2026-01-01", periods=n, freq=freq, tz="UTC")
    departure_date = "2026-03-01"
    return pd.DataFrame({
        "_recorded_dt": ts,
        "origin_code": ["DEL"] * n,
        "destination_code": ["BOM"] * n,
        "airline_code": ["6E"] * n,
        "departure_time": [f"{departure_date}T{departures[i % len(departures)]}"
                           for i in range(n)],
        "flight_number": [f"6E-{100 * (1 + i % len(departures))}" for i in range(n)],
        "departure_date": [departure_date] * n,
        "target_price": np.linspace(4000.0, 6000.0, n),
    })


def test_the_embargo_width_is_the_labels_realisation_time_not_the_horizon():
    """Why the call site passes `h + lag_tolerance_days(h)` and not `h`.

    `attach_future_target` labels a row observed at `t` with the earliest fare on
    the same curve at or after `t + h`, accepted within `lag_tolerance_days(h)`.
    So the observation that *defines* the label can sit as late as
    `t + h + lag_tolerance_days(h)`, and an embargo of only `h` would leave
    training rows whose labels were recorded inside the test period.
    """
    for h in (1, 3, 7):
        tolerance = lag_tolerance_days(h)
        assert 0 < tolerance < h, (
            "the tolerance is a fraction of the horizon, so it widens the "
            "embargo without ever reaching a second horizon"
        )
        width = h + tolerance
        # Exactly representable, so `gap_days >= embargo` has no float hazard.
        assert pd.Timedelta(days=width) == pd.Timedelta(days=h) + pd.Timedelta(
            days=tolerance)


def test_the_embargo_purges_every_training_row_whose_label_could_reach_the_test_fold():
    """The hole `boundary_is_strict` could only report.

    Ordering by observation time makes every training *feature* older than the
    test fold. It does nothing about the boundary rows' *labels*, which are fares
    recorded after the boundary — so the fit consumed prices from inside its own
    test period, and no column in the frame carries the fact.
    """
    df = _curve_frame(50)                       # 12h apart: 24.5 days of span
    width = 3 + lag_tolerance_days(3)           # 4.5 days

    _, _, plain = chronological_split(
        df, timestamp_col="_recorded_dt", train_fraction=0.8)
    train, test, purged = chronological_split(
        df, timestamp_col="_recorded_dt", train_fraction=0.8, embargo_days=width)

    assert purged["n_train_before_embargo"] == plain["n_train"] == 40
    assert purged["n_purged_by_embargo"] == 8       # 8 rows × 12h = the 4 days
    assert purged["n_train"] == 32 == len(train)
    assert purged["n_test"] == plain["n_test"] == 10, "the purge never drops test rows"

    # The claim, measured: the folds are at least the requested width apart.
    assert purged["gap_days"] >= width
    assert purged["embargo_is_effective"] is True
    assert train["_recorded_dt"].max() <= pd.Timestamp(purged["embargo_cutoff"])
    assert (test["_recorded_dt"].min() - train["_recorded_dt"].max()
            >= pd.Timedelta(days=width))

    # And the record says which rows it lost, not just how many remain.
    assert purged["train_end_before_embargo"] == plain["train_end"]
    assert (pd.Timestamp(purged["train_end"])
            < pd.Timestamp(purged["train_end_before_embargo"]))


def test_a_wider_embargo_purges_more():
    df = _curve_frame(50)
    purged = [chronological_split(df, timestamp_col="_recorded_dt",
                                  train_fraction=0.8,
                                  embargo_days=h + lag_tolerance_days(h))[2]
              for h in (1, 3, 7)]
    assert [r["n_purged_by_embargo"] for r in purged] == [2, 8, 20]
    assert all(r["embargo_is_effective"] for r in purged)
    assert [r["gap_days"] for r in purged] == [1.5, 4.5, 10.5]


def test_the_embargo_separates_a_boundary_that_shared_a_timestamp():
    """The straddle `test_a_straddled_boundary_is_reported_not_assumed` reports."""
    dup = pd.DataFrame({
        "_recorded_dt": pd.to_datetime(["2026-01-01"] * 5 + ["2026-01-02"] * 5,
                                       utc=True),
        "target_price": range(10),
    })
    straddled = chronological_split(dup, timestamp_col="_recorded_dt",
                                    train_fraction=0.8)[2]
    assert straddled["boundary_is_strict"] is False

    fixed = chronological_split(dup, timestamp_col="_recorded_dt",
                                train_fraction=0.8, embargo_days=0.5)[2]
    assert fixed["boundary_is_strict"] is True
    assert fixed["embargo_is_effective"] is True
    assert fixed["n_purged_by_embargo"] == 3, "the three same-instant rows"


def test_an_embargo_wider_than_the_corpus_empties_the_training_fold_and_says_so():
    """Which is a refusal at the call site, not a smaller training fold.

    `embargo_is_effective` is the flag that distinguishes it: with the training
    fold empty there is no measured gap at all, so nothing about the fold pair
    supports a test score.
    """
    record = chronological_split(_curve_frame(50), timestamp_col="_recorded_dt",
                                 train_fraction=0.8, embargo_days=400.0)[2]
    assert record["n_train"] == 0
    assert record["n_purged_by_embargo"] == 40
    assert record["gap_days"] is None
    assert record["embargo_is_effective"] is False
    assert record["boundary_is_strict"] is False


def test_an_empty_test_fold_leaves_the_embargo_ineffective():
    """The case the row-count gate cannot see.

    With no test fold there is no `test_start`, so no cutoff is computed and the
    training fold survives intact — a fold pair with no measured separation that
    would otherwise have been scored as though it had one.
    """
    record = chronological_split(_curve_frame(50), timestamp_col="_recorded_dt",
                                 train_fraction=1.0, embargo_days=4.5)[2]
    assert (record["n_train"], record["n_test"]) == (50, 0)
    assert record["n_purged_by_embargo"] == 0
    assert record["embargo_cutoff"] is None
    assert record["embargo_is_effective"] is False


def test_the_record_names_the_strategy_it_actually_used():
    """The metadata literal was `"Chronological_Temporal_Split"`.

    That string was true of a positional split on an unsorted frame, and would
    have stayed true after the embargo was added. A name that cannot become wrong
    describes nothing, so the artifact now reads this field out of the record.
    """
    df = _curve_frame(20)
    without = chronological_split(df, timestamp_col="_recorded_dt")[2]
    with_embargo = chronological_split(df, timestamp_col="_recorded_dt",
                                       embargo_days=1.5)[2]
    assert without["strategy"] == "chronological_by_observation_time"
    assert with_embargo["strategy"] == (
        "chronological_by_observation_time_with_embargo")
    assert without["embargo_days"] == 0.0
    assert without["embargo_is_effective"] is False


def test_the_split_reports_the_booking_curve_overlap_between_the_folds():
    """Reported, not eliminated — see `_group_overlap` for why.

    The number is what tells a reader which question the test fold answered:
    near 1.0 it measures continuing curves the model already knows, near 0.0 it
    measures pricing a flight never seen before. Both are legitimate; the
    metadata used to say neither.
    """
    shared = chronological_split(_curve_frame(40), timestamp_col="_recorded_dt",
                                 train_fraction=0.8,
                                 group_cols=BOOKING_CURVE_KEYS)[2]["group_overlap"]
    assert shared["group_columns"] == list(BOOKING_CURVE_KEYS)
    assert shared["n_groups_train"] == shared["n_groups_test"] == 2
    assert shared["n_groups_shared"] == 2
    assert shared["test_row_fraction_in_shared_groups"] == 1.0

    # A test fold made of flights that never appear in training. The disjointness has
    # to be created in the key the census reads: assigning a new `flight_number` here
    # left both folds on the same two `departure_time` groups, so `n_groups_shared`
    # was 2 and this half of the test asserted 0 against a frame it had not changed.
    disjoint_df = _curve_frame(40)
    disjoint_df.loc[disjoint_df.index >= 32, "departure_time"] = "2026-03-01T23:55:00"
    disjoint = chronological_split(disjoint_df, timestamp_col="_recorded_dt",
                                   train_fraction=0.8,
                                   group_cols=BOOKING_CURVE_KEYS)[2]["group_overlap"]
    assert disjoint["n_groups_shared"] == 0
    assert disjoint["test_rows_in_shared_groups"] == 0
    assert disjoint["test_row_fraction_in_shared_groups"] == 0.0


def test_curve_keys_are_compared_case_and_whitespace_insensitively():
    """`" del "` and `"DEL"` are the same airport, so they are the same curve.

    Comparing the raw strings would report a fold pair as disjoint because one
    side of the corpus was scraped with different padding.
    """
    df = _curve_frame(40)
    df.loc[df.index >= 32, "origin_code"] = " del "
    overlap = chronological_split(df, timestamp_col="_recorded_dt",
                                  train_fraction=0.8,
                                  group_cols=BOOKING_CURVE_KEYS)[2]["group_overlap"]
    assert overlap["n_groups_shared"] == 2
    assert overlap["test_row_fraction_in_shared_groups"] == 1.0


def test_the_overlap_census_is_absent_rather_than_empty_when_not_asked_for():
    """`None` says "not measured"; a zeroed dict would say "measured, none shared"."""
    assert chronological_split(_curve_frame(20),
                               timestamp_col="_recorded_dt")[2]["group_overlap"] is None
    assert chronological_split(_curve_frame(20), timestamp_col="_recorded_dt",
                               group_cols=[])[2]["group_overlap"] is None


# ── The published error figure ────────────────────────────────────────────────
def test_mape_excludes_non_positive_actuals_and_counts_them():
    """The denominator used to be `max(|actual|, 1)`.

    That keeps a row whose true fare is non-positive and divides by ₹1 instead, so
    one zero-fare row yields 200,000% — a number that is not a percentage of any
    fare, and the number the `MAX_TEST_MAPE` ceiling was comparing against.
    """
    value, used, excluded = mape_with_coverage([5000.0, 0.0], [5000.0, 4000.0])
    assert (round(value, 9), used, excluded) == (0.0, 1, 1)

    value, used, excluded = mape_with_coverage([0.0, -1.0], [5000.0, 5000.0])
    assert math.isnan(value) and (used, excluded) == (0, 2)
    # A comparison against NaN is False, so a gate reading this fails closed.
    assert not value <= MAX_TEST_MAPE


def test_mape_is_unchanged_for_fares_that_were_actually_paid():
    """No recorded figure moves for the wrong reason."""
    t, p = [5000.0, 4000.0, 6000.0], [5500.0, 4000.0, 5400.0]
    value, used, excluded = mape_with_coverage(t, p)
    assert (used, excluded) == (3, 0)
    assert round(value, 6) == round(100.0 * sum(
        abs(a - b) / a for a, b in zip(t, p)) / 3, 6)


def test_equivalent_accuracy_is_100_minus_mape_on_a_trained_artifact():
    """Reads a real artifact, and skips with a reason when there is none.

    `equivalent_accuracy_100_minus_mape` is the name the figure is published
    under. There used to be a second key, `"accuracy"`, carrying the same quantity
    divided by 100 — the quarantined 1d artifact still holds `"accuracy": 0.9864`
    beside `"r2": 0.4248`, so a reader who took the short key at face value
    reported "98.6% accurate" for a model explaining under half the variance.

    Both production accessors are used rather than reading `predictor.metrics`
    directly: `metrics_for_horizon` because `metrics` is keyed by horizon after a
    normal load and flat after a legacy one, and the forecast engine used to
    assume the flat shape unconditionally.
    """
    horizon = requires_forecast_metrics()
    metrics = metrics_for_horizon(get_predictor(), horizon)

    assert "mape" in metrics, "an artifact recording no MAPE cannot publish one"
    published = resolve_published_accuracy(metrics)
    if math.isfinite(metrics["mape"]):
        assert published == pytest.approx(max(0.0, 100.0 - metrics["mape"]),
                                          abs=0.01)
    else:
        assert published is None, (
            "an unmeasurable error must publish nothing, not 0.0"
        )


def test_a_metrics_dict_with_no_measured_error_publishes_nothing():
    """`max(0.0, 100.0 - nan)` is 0.0 in Python, which is why this is a test.

    Left unguarded, a model whose error could not be measured at all would publish
    an accuracy of exactly 0% — indistinguishable from one measured as terrible.
    """
    assert max(0.0, 100.0 - float("nan")) == 0.0
    assert resolve_published_accuracy(
        {"mae": 812.0, "r2": 0.56,
         "equivalent_accuracy_100_minus_mape": None}) is None
