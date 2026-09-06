"""Served-forecast accuracy evaluator: how wrong were the forecasts this system
actually published, measured against the fares that actually happened?

This is the eval the suite did not have. Every other evaluator scores the
*planner* — did it pick the right intent, the right entities, the right tools —
and the suite's headline `overall_success_rate` was therefore a statement about
query parsing that a reader would reasonably take as a statement about price
forecasting. Nothing in `backend/evals/` had ever compared a forecast to an
outcome, and `docs/EVALUATION_FRAMEWORK.md` claimed the harness "Evaluates price
forecast accuracy (MAPE, RMSE)".

Where the numbers come from. `forecast_evaluation_scheduler` resolves each pending
forecast against the realised fare on the same booking curve — the same
`price_at_horizon` rule the training label uses — and writes `actual_price` onto
the row. `forecast_store.load_resolved_forecasts` reads those rows and
`forecast_evaluator.evaluate` computes the metric set over them. Nothing is
computed here; this file only decides whether the figures clear a bound.

The bound. Two of them, both of which can fail:

  * **R² >= `MIN_R2`.** R²'s denominator is the variance about `mean(y_true)`, so
    "R² >= 0" is exactly "at least as accurate as one constant chosen with
    hindsight". A forecaster that cannot clear it has not learned the fare level
    of the routes it is quoting. It is a floor, not a target.
  * **MAPE <= `MAX_MAPE`.** A percentage bound is only meaningful with a stated
    number, and the number here is a deployment choice rather than a discovered
    fact, so it is a module constant with the reasoning attached rather than a
    figure buried in a comparison.

Neither bound is checked on fewer than `MIN_SCORED_FORECASTS` resolved forecasts.
An R² over three points is noise, and passing a bound on noise is the failure mode
this whole subsystem was rewritten to remove. Below that count the result is
SKIPPED with the count in the reason — and `AIEvaluator` treats an all-skipped run
as FAIL, so a suite in which this is the only evaluator cannot come out green by
having no data.

What this cannot yet measure, and why that is recorded rather than approximated.
The bound that matters most for a fare forecaster is the **persistence baseline**:
beating the fare that was on screen when the advice was given. `forecast_store`
rows do not carry that quoted fare — `forecast_evaluator` documents the same gap —
so the baseline is reported in `skipped_baselines` with its reason, in the shape
`backend.ml.benchmark` uses, instead of being approximated from something else. It
becomes live automatically once a quoted fare is recorded on the forecast row: if
a row carries `quoted_price` (or `recommendation.quoted_price`), persistence is
computed and enforced.

Why the store is imported inside the method. `backend.services.forecast_store`
imports `backend.database.database`, which **raises at import time** when
`SUPABASE_URL` / `SUPABASE_SERVICE_KEY` are unset and builds a live client when
they are. `evaluator.py` imports every evaluator module at import so they
self-register, so importing the store at module scope here would make the entire
eval suite — including `doctor.py` and every deterministic evaluator that needs no
database at all — unimportable on a machine without Supabase credentials, which
describes CI. The import is therefore deferred into `evaluate_batch` and a failure
to import is reported as INFRASTRUCTURE_UNAVAILABLE, which is what it is. The
store is also injectable, so the read path can be exercised without Supabase.
"""

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from backend.evals.evaluators.base import BaseEvaluator
from backend.evals.registry import EvaluatorResult, register_evaluator
from backend.ml import metrics as m
from backend.services.forecast_evaluator import forecast_evaluator

logger = logging.getLogger(__name__)

# Below this many resolved forecasts, no bound is checked. Chosen so that R² is
# computed over enough points to mean something; a smaller corpus is a young
# corpus, which is a state to report rather than a result to grade.
MIN_SCORED_FORECASTS = 30

# At least as accurate as a single constant chosen with hindsight. See the module
# docstring: this is arithmetically that comparison, not an approximation of it.
MIN_R2 = 0.0

# Percentage-error ceiling. A fare forecast wrong by more than this much on
# average is not usable for a book-now / wait decision, which is the only thing
# the product does with it. Stated here so the number is arguable rather than
# implicit.
MAX_MAPE = 15.0

# Persistence must be beaten by at least this fraction of its own MAE, matching
# `backend.ml.benchmark._IMPROVEMENT_THRESHOLD`: a forecaster level with the fare
# already on screen has added nothing.
MIN_PERSISTENCE_IMPROVEMENT = 0.005


def _finite(value: Any) -> Optional[float]:
    """`value` as a float, or None if it is missing, NaN or infinite.

    Every bound below is written as an explicit comparison against a finite
    figure. A comparison against NaN is False, which would make a metric that
    could not be computed *fail* the bound and read as a bad model rather than as
    an absent measurement — the inverse of the defect this suite had, and no
    better.
    """
    if value is None:
        return None
    try:
        as_float = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(as_float) or math.isinf(as_float) else as_float


def _quoted_fare(row: Dict[str, Any]) -> Optional[float]:
    """The fare on screen when the forecast was published, if the row records it."""
    direct = _finite(row.get("quoted_price"))
    if direct is not None:
        return direct
    rec = row.get("recommendation")
    if isinstance(rec, dict):
        for key in ("quoted_price", "current_price", "price_at_forecast"):
            nested = _finite(rec.get(key))
            if nested is not None:
                return nested
    return None


def _persistence_baseline(frame: pd.DataFrame) -> Tuple[Optional[Dict[str, float]], str]:
    """Persistence metrics over the rows that record a quoted fare, or why not."""
    if "quoted_price" not in frame.columns:
        return None, ("forecast rows record no quoted fare, so 'beat the price "
                      "already on screen' cannot be computed")
    usable = frame[frame["quoted_price"].notna() & frame["actual_price"].notna()]
    if len(usable) < MIN_SCORED_FORECASTS:
        return None, (f"only {len(usable)} of {len(frame)} resolved forecast(s) record "
                      f"a quoted fare; {MIN_SCORED_FORECASTS} needed to compare against "
                      f"persistence")
    return m.compute_all(
        usable["actual_price"].to_numpy(dtype=float),
        usable["quoted_price"].to_numpy(dtype=float),
    ), ""


@register_evaluator("forecast_accuracy")
class ForecastAccuracyEvaluator(BaseEvaluator):
    """Bounds on the error of forecasts this system published and later resolved."""

    name = "forecast_accuracy"
    category = "deterministic"
    feedback_key = "forecast_accuracy_score"

    def __init__(self, config: Any = None, store: Any = None):
        # `store` is injectable for the same reason `ForecastStore(database=...)`
        # is: the read path is worth exercising without a live Supabase project.
        # Left None, the module singleton is imported on first use — see the module
        # docstring for why that import cannot happen at module scope.
        super().__init__(config)
        self._store = store

    def _resolve_store(self) -> Any:
        if self._store is None:
            from backend.services.forecast_store import forecast_store
            self._store = forecast_store
        return self._store

    def evaluate_item(self, expected: Dict[str, Any], actual: Dict[str, Any]) -> EvaluatorResult:
        """Not a per-query check.

        The planner items this suite iterates are queries and plans; a forecast's
        outcome is recorded days after the query that produced it. `evaluate_batch`
        is overridden and reads the resolved outcomes directly, so this method
        exists only to satisfy the base class and says so rather than returning
        something that would be counted.
        """
        return self._skip("forecast_accuracy is measured over resolved forecasts, "
                          "not over a single planner item")

    def evaluate_batch(self, batch_items: List[Dict[str, Any]]) -> EvaluatorResult:
        """Load every resolved forecast, score it, and apply the bounds.

        `batch_items` is ignored: this evaluator's input is the forecast store, not
        the planner run. It is accepted so the coordinator can call every evaluator
        the same way.
        """
        try:
            rows = self._resolve_store().load_resolved_forecasts()
        except Exception as exc:
            # A read failure — or a store that cannot even be imported because this
            # process has no database credentials — is infrastructure, not a model
            # result. Reported as such so it cannot be mistaken for "the forecaster
            # has no error".
            logger.error("[forecast_accuracy] Could not read resolved forecasts: %s", exc)
            return EvaluatorResult(
                evaluator_name=self.name,
                category=self.category,
                score=None,
                status="INFRASTRUCTURE_UNAVAILABLE",
                passed=False,
                reason=f"Could not read resolved forecasts from the store: {exc}",
                details={"error": str(exc)},
                feedback_key=self.feedback_key,
            )

        if not rows:
            return self._skip(
                "No forecast has been resolved against a realised fare yet, so the "
                "served model has no measured error. Publish forecasts and let "
                "forecast_evaluation_scheduler resolve them.",
                details={"resolved_forecasts": 0})

        frame = pd.DataFrame(rows)
        for column in ("actual_price", "forecast_price"):
            frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
        quoted = [_quoted_fare(row) for row in rows]
        if any(q is not None for q in quoted):
            frame["quoted_price"] = quoted

        report = forecast_evaluator.evaluate(frame)
        scored = int(report.get("sample_count") or 0)

        if scored < MIN_SCORED_FORECASTS:
            return self._skip(
                f"Only {scored} resolved forecast(s) are scorable "
                f"({report.get('excluded_rows', 0)} excluded of {len(rows)} read); "
                f"{MIN_SCORED_FORECASTS} are needed before an accuracy bound means "
                f"anything",
                details={"resolved_forecasts": len(rows),
                         "scored": scored,
                         "min_required": MIN_SCORED_FORECASTS,
                         "metrics": _jsonable(report)})

        r2_value = _finite(report.get("r2"))
        mape_value = _finite(report.get("mape"))

        checks: List[Dict[str, Any]] = [
            self._check("r2_beats_a_hindsight_constant", r2_value,
                        lambda v: v >= MIN_R2, f">= {MIN_R2}"),
            self._check("mape_within_ceiling", mape_value,
                        lambda v: v <= MAX_MAPE, f"<= {MAX_MAPE}%"),
        ]

        skipped_baselines: List[Dict[str, str]] = []
        persistence, why_not = _persistence_baseline(frame)
        if persistence is None:
            skipped_baselines.append({"name": "persistence", "reason": why_not})
        else:
            model_mae = _finite(report.get("mae"))
            base_mae = _finite(persistence.get("mae"))
            required = None if base_mae is None else base_mae * (1.0 - MIN_PERSISTENCE_IMPROVEMENT)
            checks.append(self._check(
                "beats_the_fare_already_on_screen", model_mae,
                lambda v: required is not None and v <= required,
                f"MAE <= {required:.2f} (persistence MAE {base_mae:.2f} less "
                f"{MIN_PERSISTENCE_IMPROVEMENT:.1%})" if required is not None
                else "persistence MAE undefined"))

        unmeasured = [c["name"] for c in checks if c["value"] is None]
        failures = [c for c in checks if c["passed"] is False]

        if unmeasured:
            # A bound whose figure is NaN was not checked. Calling that a pass is
            # the defect; calling it a failure blames the model for an absent
            # measurement. It is an ERROR: something that should have produced a
            # number did not.
            return EvaluatorResult(
                evaluator_name=self.name,
                category=self.category,
                score=None,
                status="ERROR",
                passed=False,
                reason=(f"{len(unmeasured)} bound(s) could not be evaluated because "
                        f"their metric is undefined over {scored} scored forecast(s): "
                        f"{', '.join(unmeasured)}"),
                details={"scored": scored, "checks": checks,
                         "metrics": _jsonable(report)},
                feedback_key=self.feedback_key,
            )

        passed = not failures
        score = sum(1 for c in checks if c["passed"]) / float(len(checks))

        return EvaluatorResult(
            evaluator_name=self.name,
            category=self.category,
            score=round(score, 4),
            status="PASS" if passed else "FAIL",
            passed=passed,
            reason=(f"{len(checks)} bound(s) met over {scored} resolved forecast(s)"
                    if passed else
                    f"{len(failures)} bound(s) missed over {scored} resolved "
                    f"forecast(s): " + "; ".join(
                        f"{c['name']} = {c['value']:.4f}, needs {c['requirement']}"
                        for c in failures)),
            details={
                "resolved_forecasts": len(rows),
                "scored": scored,
                "excluded_rows": report.get("excluded_rows"),
                "checks": checks,
                "skipped_baselines": skipped_baselines,
                "metrics": _jsonable(report),
                "bounds": {"min_r2": MIN_R2, "max_mape": MAX_MAPE,
                           "min_scored_forecasts": MIN_SCORED_FORECASTS},
            },
            feedback_key=self.feedback_key,
        )

    @staticmethod
    def _check(name: str, value: Optional[float], predicate, requirement: str) -> Dict[str, Any]:
        """One bound: its figure, whether it held, and what it required.

        `passed` is `None` — not False — when the figure is undefined, so the
        caller can tell "missed the bound" from "never measured".
        """
        return {
            "name": name,
            "value": value,
            "requirement": requirement,
            "passed": None if value is None else bool(predicate(value)),
        }

    def _skip(self, reason: str, details: Optional[Dict[str, Any]] = None) -> EvaluatorResult:
        return EvaluatorResult(
            evaluator_name=self.name,
            category=self.category,
            score=None,
            status="SKIPPED",
            passed=False,
            reason=reason,
            details=details or {},
            feedback_key=self.feedback_key,
        )


def _jsonable(report: Dict[str, Any]) -> Dict[str, Any]:
    """NaN out of a metric report becomes None, so the JSON artifact is valid JSON.

    `json.dumps` emits a bare `NaN` token, which is not JSON and which a strict
    reader rejects. None reads as "undefined" in every consumer.
    """
    return {k: (None if _finite(v) is None and isinstance(v, float) else v)
            for k, v in report.items()}
