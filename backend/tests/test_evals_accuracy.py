"""Accuracy and error-bound tests for the evaluation platform.

This file has been named "accuracy" since Phase 2.5.3 and contained none. The three
tests in it were a shape check on the health report, `assert run_doctor() in
(0, 1, 2)` — the function's entire range, so it could not fail — and a markdown
assertion whose fixture hand-built a flat `environment` dict no summary has ever
emitted. Not one of them touched a metric, while
`docs/EVALUATION_FRAMEWORK.md` described the module as "Model accuracy & error
bounds tests".

What is tested now, in the order it appears:

  * `backend.ml.metrics` against figures worked out by hand, including the two
    claims the rest of the code leans on: that MAPE excludes a non-positive actual
    and counts the exclusion, and that R² is exactly 0.0 for a forecaster
    predicting `mean(y_true)` — which is what makes "R² >= 0" mean "at least as
    accurate as one constant chosen with hindsight".
  * `forecast_evaluator.evaluate` — NaN rather than zeros on an unscorable frame,
    `sample_count` / `excluded_rows`, and a raise on a frame missing its columns.
  * `ForecastAccuracyEvaluator` through its `store=` seam: an empty store must SKIP
    and never PASS, a forecaster worse than a hindsight constant must FAIL, and —
    the bound this suite never had — a forecaster that loses to the fare already on
    screen must FAIL even while meeting both absolute bounds.
  * `run_doctor` must return 2 when the corpus is absent, and must not when it is
    present.
"""

import json
import math
import tempfile

import pandas as pd
import pytest

from backend.evals.datasets.loader import dataset_loader
from backend.evals.doctor import run_doctor
from backend.evals.environment import environment_inspector, ProviderHealthReport
from backend.evals.evaluators.deterministic.forecast_accuracy import (
    MAX_MAPE,
    MIN_R2,
    MIN_SCORED_FORECASTS,
    ForecastAccuracyEvaluator,
)
from backend.evals.reports.markdown import generate_markdown_report
from backend.ml import metrics as m
from backend.services.forecast_evaluator import forecast_evaluator

# Imported rather than re-typed. The flat-key `environment` fixture survived here
# precisely because it had been hand-copied into two modules, so correcting one
# left the other asserting a shape production does not emit. One definition cannot
# drift from itself.
from backend.tests.test_evals_resilience import _health_summary


# --------------------------------------------------------------------------- #
# backend.ml.metrics — known values, worked out by hand                       #
# --------------------------------------------------------------------------- #

# actual / forecast pair used by the arithmetic tests below. Errors are +10, -10
# and +30 on fares of 100, 200 and 300, which makes every metric a short sum:
#   MAE  = (10 + 10 + 30) / 3                       = 16.6667
#   RMSE = sqrt((100 + 100 + 900) / 3)              = 19.1485
#   MAPE = mean(10/100, 10/200, 30/300) * 100       =  8.3333
#   R^2  = 1 - 1100 / 20000                         =  0.945
_TRUE = [100.0, 200.0, 300.0]
_PRED = [110.0, 190.0, 330.0]


def test_mae_and_rmse_are_the_textbook_figures():
    assert m.mae(_TRUE, _PRED) == pytest.approx(50.0 / 3.0)
    assert m.rmse(_TRUE, _PRED) == pytest.approx(math.sqrt(1100.0 / 3.0))
    assert m.median_absolute_error(_TRUE, _PRED) == pytest.approx(10.0)
    assert m.mean_error(_TRUE, _PRED) == pytest.approx(10.0)


def test_r2_and_mape_are_the_textbook_figures():
    assert m.r2(_TRUE, _PRED) == pytest.approx(0.945)
    assert m.mape(_TRUE, _PRED) == pytest.approx(100.0 * 0.25 / 3.0)


def test_compute_all_returns_every_metric_key():
    report = m.compute_all(_TRUE, _PRED)
    assert set(report) == set(m.METRIC_KEYS)
    assert len(m.METRIC_KEYS) == 7


def test_mape_excludes_a_non_positive_actual_and_counts_the_exclusion():
    """The row is dropped, not scored against a substituted denominator.

    The old implementation divided by `max(abs(actual), 1.0)`, which keeps a
    zero-fare row and scores it against ₹1. Both errors below are exactly 10% of
    their own fare, so a clipped denominator on the middle row would be visible in
    the figure.
    """
    value, used, excluded = m.mape_with_coverage([100.0, 0.0, 200.0],
                                                [110.0, 50.0, 180.0])
    assert value == pytest.approx(10.0)
    assert (used, excluded) == (2, 1)


def test_mape_is_undefined_rather_than_zero_when_no_actual_is_positive():
    value, used, excluded = m.mape_with_coverage([0.0, -50.0], [10.0, 10.0])
    assert math.isnan(value)
    assert (used, excluded) == (0, 2)
    assert math.isnan(m.mape([0.0, -50.0], [10.0, 10.0]))


def test_r2_is_exactly_zero_for_a_hindsight_constant():
    """The arithmetic `forecast_accuracy`'s floor rests on.

    `MIN_R2 = 0.0` is documented as "at least as accurate as one constant chosen
    with hindsight". That is only true if predicting `mean(y_true)` scores exactly
    0.0, so it is pinned here rather than asserted in prose.
    """
    y_true = [100.0, 200.0, 300.0, 400.0]
    assert m.r2(y_true, [250.0] * 4) == pytest.approx(0.0)
    assert m.r2(y_true, [1000.0] * 4) < 0.0
    assert m.r2(y_true, y_true) == pytest.approx(1.0)


def test_direction_accuracy_is_undefined_on_a_single_point():
    assert math.isnan(m.direction_accuracy([100.0], [100.0]))


def test_undefined_metrics_are_nan_not_zero():
    """Zero MAE reads as a perfect forecaster; the acceptance gates compare with
    `>=`, and every comparison against NaN is False, so they fail closed."""
    undefined = m.undefined_metrics()
    assert set(undefined) == set(m.METRIC_KEYS)
    assert all(math.isnan(v) for v in undefined.values())


# --------------------------------------------------------------------------- #
# forecast_evaluator — aggregate error over resolved forecasts                #
# --------------------------------------------------------------------------- #

def test_forecast_evaluator_scores_a_frame_and_reports_its_coverage():
    frame = pd.DataFrame({"actual_price": _TRUE, "forecast_price": _PRED})
    report = forecast_evaluator.evaluate(frame)
    assert report["sample_count"] == 3
    assert report["excluded_rows"] == 0
    assert report["mae"] == pytest.approx(50.0 / 3.0)
    assert report["mape"] == pytest.approx(100.0 * 0.25 / 3.0)


def test_forecast_evaluator_excludes_an_unreadable_fare_and_says_how_many():
    """A fare that arrives as None or as a string is coerced away and counted.

    `.mean()` on the raw column would have skipped it silently, so the metric
    would have been over a smaller set than the caller believed.
    """
    frame = pd.DataFrame({"actual_price": [100.0, 200.0, 300.0, None],
                          "forecast_price": [110.0, 190.0, "n/a", 300.0]})
    report = forecast_evaluator.evaluate(frame)
    assert report["sample_count"] == 2
    assert report["excluded_rows"] == 2
    assert report["mae"] == pytest.approx(10.0)


def test_forecast_evaluator_is_undefined_not_perfect_on_an_unscorable_frame():
    empty = forecast_evaluator.evaluate(pd.DataFrame())
    assert empty["sample_count"] == 0
    assert math.isnan(empty["mae"]) and math.isnan(empty["mape"])

    unreadable = forecast_evaluator.evaluate(
        pd.DataFrame({"actual_price": [None, None], "forecast_price": ["x", "y"]}))
    assert unreadable["sample_count"] == 0
    assert unreadable["excluded_rows"] == 2
    assert math.isnan(unreadable["rmse"])


def test_forecast_evaluator_raises_on_a_frame_missing_its_columns():
    """Holding the wrong frame is a bug, not an evaluation with no data."""
    with pytest.raises(ValueError) as excinfo:
        forecast_evaluator.evaluate(pd.DataFrame({"price": [100.0]}))
    assert "forecast_price" in str(excinfo.value)


def test_forecast_evaluator_groups_by_horizon():
    frame = pd.DataFrame({"actual_price": [100.0, 200.0, 300.0],
                          "forecast_price": [110.0, 190.0, 330.0],
                          "horizon_days": [1, 1, 7]})
    grouped = forecast_evaluator.evaluate_grouped(frame, "horizon_days")
    assert set(grouped) == {"1", "7"}
    assert grouped["1"]["sample_count"] == 2
    assert grouped["7"]["mae"] == pytest.approx(30.0)
    assert forecast_evaluator.evaluate_grouped(frame, "route") == {}


# --------------------------------------------------------------------------- #
# ForecastAccuracyEvaluator — the bound that can fail                         #
# --------------------------------------------------------------------------- #

class _FakeForecastStore:
    """Returns exactly the rows it was handed, or raises what it was handed.

    The evaluator accepts `store=` for this reason: `forecast_store` imports
    `backend.database.database`, which raises at import without Supabase
    credentials, so the read path and every bound would otherwise be untestable
    anywhere except a machine pointed at a live project.
    """

    def __init__(self, rows=None, error=None):
        self._rows = rows or []
        self._error = error

    def load_resolved_forecasts(self):
        if self._error is not None:
            raise self._error
        return list(self._rows)


def _resolved_rows(count, error_pct, quoted_error_pct=None, quoted_rows=None,
                   negative_actuals=False):
    """`count` resolved forecasts whose MAPE is exactly `error_pct`.

    The error alternates sign, so the percentage error of every row is exactly
    `error_pct` and the signed mean error is ~0. A corpus drawn from a seeded RNG
    would pin the seed rather than the metric.
    """
    rows = []
    for i in range(count):
        actual = 5000.0 + 137.0 * ((i * 7) % 23)
        if negative_actuals:
            actual = -actual
        direction = 1.0 if i % 2 else -1.0
        row = {
            "id": f"fc_{i}",
            "horizon_days": 7,
            "actual_price": actual,
            "forecast_price": actual * (1.0 + direction * error_pct / 100.0),
        }
        if quoted_error_pct is not None and (quoted_rows is None or i < quoted_rows):
            row["quoted_price"] = actual * (1.0 + direction * quoted_error_pct / 100.0)
        rows.append(row)
    return rows


def _evaluate(rows=None, error=None):
    evaluator = ForecastAccuracyEvaluator(store=_FakeForecastStore(rows, error))
    return evaluator.evaluate_batch([])


def test_no_resolved_forecast_is_a_skip_and_never_a_pass():
    result = _evaluate(rows=[])
    assert result.status == "SKIPPED"
    assert result.passed is False
    assert result.score is None
    assert result.details["resolved_forecasts"] == 0


def test_a_corpus_below_the_minimum_is_a_skip_with_the_count_in_it():
    """A bound passed on five points is a bound passed on noise."""
    result = _evaluate(rows=_resolved_rows(5, error_pct=2.0))
    assert result.status == "SKIPPED"
    assert result.passed is False
    assert result.details["scored"] == 5
    assert result.details["min_required"] == MIN_SCORED_FORECASTS


def test_a_store_that_cannot_be_read_is_infrastructure_not_a_result():
    result = _evaluate(error=RuntimeError("no Supabase credentials"))
    assert result.status == "INFRASTRUCTURE_UNAVAILABLE"
    assert result.passed is False
    assert result.score is None
    assert "no Supabase credentials" in result.reason


def test_an_accurate_forecaster_passes_both_absolute_bounds():
    result = _evaluate(rows=_resolved_rows(40, error_pct=2.0))
    assert result.status == "PASS"
    assert result.passed is True
    assert result.score == pytest.approx(1.0)
    assert result.details["scored"] == 40
    assert result.details["metrics"]["mape"] == pytest.approx(2.0)
    assert result.details["metrics"]["r2"] > MIN_R2
    # No row records the fare that was on screen, so the baseline is reported as
    # skipped with its reason rather than approximated from something else.
    assert [b["name"] for b in result.details["skipped_baselines"]] == ["persistence"]


def test_a_forecaster_worse_than_a_hindsight_constant_fails():
    """The bound that can fail, which is the whole point of the evaluator."""
    result = _evaluate(rows=_resolved_rows(40, error_pct=40.0))
    assert result.status == "FAIL"
    assert result.passed is False
    assert result.score == pytest.approx(0.0)
    assert result.details["metrics"]["r2"] < MIN_R2
    assert result.details["metrics"]["mape"] > MAX_MAPE
    assert {c["name"] for c in result.details["checks"] if c["passed"] is False} == {
        "r2_beats_a_hindsight_constant", "mape_within_ceiling"}


def test_a_forecaster_that_loses_to_the_fare_on_screen_fails():
    """The check nothing in this repository had: 8% error is comfortably inside
    both absolute bounds, and still worthless beside a 1% persistence baseline."""
    result = _evaluate(rows=_resolved_rows(40, error_pct=8.0, quoted_error_pct=1.0))
    checks = {c["name"]: c for c in result.details["checks"]}
    assert result.status == "FAIL"
    assert result.passed is False
    assert checks["r2_beats_a_hindsight_constant"]["passed"] is True
    assert checks["mape_within_ceiling"]["passed"] is True
    assert checks["beats_the_fare_already_on_screen"]["passed"] is False
    # Two of three bounds met, rounded to four decimal places on the way out.
    assert result.score == pytest.approx(2.0 / 3.0, abs=1e-4)
    assert result.details["skipped_baselines"] == []


def test_beating_the_fare_on_screen_is_a_pass():
    result = _evaluate(rows=_resolved_rows(40, error_pct=2.0, quoted_error_pct=20.0))
    assert result.status == "PASS"
    assert len(result.details["checks"]) == 3
    assert all(c["passed"] for c in result.details["checks"])


def test_too_few_quoted_fares_skips_only_the_baseline():
    result = _evaluate(rows=_resolved_rows(40, error_pct=2.0, quoted_error_pct=20.0,
                                           quoted_rows=10))
    assert result.status == "PASS"
    assert len(result.details["checks"]) == 2
    reason = result.details["skipped_baselines"][0]["reason"]
    assert "only 10 of 40" in reason


def test_a_bound_with_no_number_is_an_error_not_a_pass():
    """A comparison against NaN is False, so an unmeasurable bound would otherwise
    read as a bad model rather than as an absent measurement — the inverse defect,
    and no better. Every actual here is non-positive, so MAPE is undefined."""
    result = _evaluate(rows=_resolved_rows(40, error_pct=2.0, negative_actuals=True))
    checks = {c["name"]: c for c in result.details["checks"]}
    assert result.status == "ERROR"
    assert result.passed is False
    assert result.score is None
    assert checks["mape_within_ceiling"]["value"] is None
    assert checks["mape_within_ceiling"]["passed"] is None
    assert "mape_within_ceiling" in result.reason


def test_the_details_of_an_undefined_run_are_valid_json():
    """`json.dumps` emits a bare `NaN` token, which is not JSON. `summary.json` is
    written from these details, so a NaN here makes the artifact unparseable."""
    result = _evaluate(rows=_resolved_rows(40, error_pct=2.0, negative_actuals=True))
    encoded = json.dumps(result.details, allow_nan=False)
    assert "NaN" not in encoded
    assert '"mape": null' in encoded


def test_a_single_planner_item_is_not_scored_as_a_forecast():
    """`evaluate_item` exists to satisfy the base class. A forecast's outcome lands
    days after the query that produced it, so per-item scoring would be scoring
    the plan again under an accuracy label."""
    result = ForecastAccuracyEvaluator(store=_FakeForecastStore()).evaluate_item({}, {})
    assert result.status == "SKIPPED"
    assert result.passed is False
    assert result.score is None


def test_the_evaluator_does_not_import_the_store_at_module_scope():
    """Regression. `evaluator.py` imports every evaluator module so they
    self-register, and `forecast_store` imports `backend.database.database`, which
    raises at import without Supabase credentials. A module-scope import here made
    the entire suite — `doctor.py` included — unimportable in CI.
    """
    import backend.evals.evaluators.deterministic.forecast_accuracy as module
    assert "forecast_store" not in vars(module)
    # Constructing it must not reach for a database either.
    assert ForecastAccuracyEvaluator().name == "forecast_accuracy"


# --------------------------------------------------------------------------- #
# Health reporting and the doctor's exit code                                 #
# --------------------------------------------------------------------------- #

def test_provider_health_report_shape():
    report = environment_inspector.inspect()
    assert isinstance(report, ProviderHealthReport)
    assert report.filesystem.healthy is True
    assert report.benchmark_validity in ("FULL", "PARTIAL", "INVALID")
    # Every component must carry the reason it reached its verdict; the report is
    # printed by `doctor.py` and rendered into the markdown table verbatim.
    for component in (report.openai, report.langsmith, report.filesystem, report.dataset):
        assert component.reason


def test_doctor_returns_two_when_the_corpus_is_absent():
    """The old assertion was `exit_code in (0, 1, 2)` — the function's entire
    range. Pointing the loader at an empty directory is the one condition the
    doctor is documented to exit 2 on, so it is the condition asserted.
    """
    original_base_dir = dataset_loader.base_dir
    with tempfile.TemporaryDirectory() as empty_dir:
        try:
            dataset_loader.base_dir = empty_dir
            assert run_doctor() == 2
        finally:
            dataset_loader.base_dir = original_base_dir


def test_doctor_does_not_report_a_critical_failure_on_the_real_corpus():
    """0 or 1 depending on whether optional SDKs and API keys are present; 2 would
    mean a critical failure, which the shipped corpus and filesystem must not
    produce."""
    assert run_doctor() in (0, 1)


def test_markdown_report_shows_a_failed_dataset_check_rather_than_a_tick():
    """The report's checklist and infrastructure table must follow the health
    report down to an unhealthy component. Both `environment` and `provider_health`
    are separate dumps of the same model, so both are overridden here — the report
    reads whichever it finds first.
    """
    summary = _health_summary(evaluation_result="FAIL", benchmark_validity="INVALID")
    for key in ("environment", "provider_health"):
        summary[key]["dataset"].update({
            "healthy": False,
            "current_mode": "DEGRADED",
            "reason": "no corpus for dataset version '9.9.9'",
        })
    report_md = generate_markdown_report(summary)
    assert "**Benchmark Validity**: **`INVALID`**" in report_md
    assert "no corpus for dataset version '9.9.9'" in report_md
    assert "- [ ] Dataset loaded and verified — no corpus" in report_md
    assert "- [x] Dataset loaded and verified" not in report_md
