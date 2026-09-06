"""Model Benchmarking.

Compares a newly trained model against the baselines a fare forecaster has to
beat before it is worth deploying:

  1. Persistence — predict the fare last observed for that row, unchanged. The
     baseline a price forecaster must beat to have learned anything, and the one
     a user gets for free by reading the current price off the screen.
  2. Training-fold mean — predict a single constant, computed from the training
     labels only.
  3. The previous production model, when predictions for the same rows exist.

Each baseline needs an input the caller has to supply. When it is absent the
baseline is recorded in `skipped_baselines` with the reason, and a run with no
baseline at all returns the verdict `not_compared` rather than `unchanged`:
"we compared and it was the same" and "we never compared" used to print
identically, and the second one is the state this module was actually in.

Two former baselines are gone, and both were reporting skill that did not exist:

* `naive_persistence` was `np.full_like(y_true, np.mean(y_true))` — the mean of
  the *test* actuals. It is not persistence (no last-known price enters it), it
  is an oracle (a forecaster does not know the mean of the period it is
  forecasting), and its R² is identically 0.0 because R²'s denominator *is* the
  variance about `mean(y_true)`. So this "independent baseline" was arithmetically
  the same check as `price_model.MIN_TEST_R2 = 0.0`, and the pipeline was counting
  it twice.
* `rolling_mean_3` was `np.convolve(y_true, np.ones(3) / 3, mode="same")`, and
  `mode="same"` is *centred*: the prediction for row i is the mean of y[i-1],
  y[i] and y[i+1]. It contains the answer, and the next answer as well. On a
  fare series smooth enough to be worth forecasting it therefore holds the lowest
  error of any baseline, becomes `best_baseline`, and drives every honest model to
  the verdict `regressed`. A benchmark that fails a model because the baseline
  saw the label is worse than having no benchmark.

Promotion decisions belong to TrainingPolicy — this module only measures
performance and reports verdicts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List

import numpy as np

from backend.ml import metrics as m

logger = logging.getLogger(__name__)

# Improvement threshold: new model must beat baseline by at least this fraction
_IMPROVEMENT_THRESHOLD = 0.005   # 0.5 % relative improvement

# Metrics where a larger number is a better model. Everything else in
# `metrics.METRIC_KEYS` is an error and smaller is better.
_HIGHER_IS_BETTER = ("r2", "direction_accuracy")


@dataclass
class BaselineResult:
    """Metrics for one baseline comparison."""
    name: str
    metrics: Dict[str, float]
    description: str = ""


@dataclass
class SkippedBaseline:
    """A baseline that could not be computed, and why.

    Present so that an absent comparison is a fact in the report rather than a
    gap in a list nobody counts.
    """
    name: str
    reason: str


@dataclass
class BenchmarkResult:
    """Full benchmark comparison for one training run."""

    new_model_metrics: Dict[str, float]
    baselines: List[BaselineResult]
    verdict: str                     # "improved"|"unchanged"|"regressed"|"not_compared"
    primary_metric: str = "mae"                      # metric used for verdict
    improvement_pct: float = 0.0                     # relative improvement vs best baseline (positive = better)
    best_baseline: Optional[str] = None              # which baseline the verdict is against
    best_baseline_value: Optional[float] = None      # its primary metric
    rows_scored: int = 0                             # rows every figure above is over
    feature_set_version: str = ""
    skipped_baselines: List[SkippedBaseline] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @property
    def is_regression(self) -> bool:
        return self.verdict == "regressed"

    @property
    def is_improvement(self) -> bool:
        return self.verdict == "improved"

    @property
    def was_compared(self) -> bool:
        """Whether any baseline was available. False makes the verdict meaningless."""
        return bool(self.baselines)


class ModelBenchmark:
    """Benchmarks a newly trained model against baselines."""

    def run(
        self,
        y_true,
        y_pred_new: np.ndarray,
        *,
        y_last_known=None,
        y_train=None,
        y_pred_production: Optional[np.ndarray] = None,
        feature_set_version: str = "feature_set_v1",
        primary_metric: str = "mae",
    ) -> BenchmarkResult:
        """Run all available benchmarks and return a BenchmarkResult.

        Args:
            y_true: Ground-truth target prices for the test/validation fold.
            y_pred_new: Predictions from the newly trained model, row-aligned
                        with `y_true`.
            y_last_known: The fare already observed for each row at the moment it
                          was made — the `price` column of the same fold. Drives
                          the persistence baseline. Row-aligned with `y_true`.
            y_train: The training fold's labels. Their mean is the constant
                     baseline; taken from the training fold and not from `y_true`
                     so that the baseline knows nothing the model did not.
            y_pred_production: Predictions from the current production model on
                               these same rows.
            feature_set_version: Recorded on the result, so a benchmark can be
                                 attributed to the contract it was run under.
            primary_metric: Metric used for the improved/unchanged/regressed
                            verdict.

        Every baseline is scored on exactly the rows the new model was scored on.
        A baseline whose input is missing or non-finite on any of those rows is
        skipped with a reason rather than scored on a subset: an error over a
        different row set is not comparable to the model's, and a benchmark whose
        two sides are measured over different rows reports a difference that is
        partly just the rows.

        Returns:
            BenchmarkResult
        """
        y_true_arr = np.asarray(y_true, dtype=float)
        y_pred_new_arr = np.asarray(y_pred_new, dtype=float)

        mask = ~(np.isnan(y_true_arr) | np.isnan(y_pred_new_arr))
        y_true_clean = y_true_arr[mask]
        y_pred_new_clean = y_pred_new_arr[mask]
        n_scored = int(len(y_true_clean))

        new_metrics = (m.compute_all(y_true_clean, y_pred_new_clean) if n_scored
                       else m.undefined_metrics())
        baselines: List[BaselineResult] = []
        skipped: List[SkippedBaseline] = []

        # ── 1. Persistence: the fare already on the screen, carried forward ───
        if n_scored == 0:
            skipped.append(SkippedBaseline(
                "persistence", "no row has both a finite actual and a finite prediction"))
        elif y_last_known is None:
            skipped.append(SkippedBaseline(
                "persistence",
                "caller supplied no last-known price; a persistence forecast cannot "
                "be reconstructed from the actuals without becoming an oracle"))
        else:
            last_known = np.asarray(y_last_known, dtype=float)
            if last_known.shape[0] != y_true_arr.shape[0]:
                skipped.append(SkippedBaseline(
                    "persistence",
                    f"last-known price has {last_known.shape[0]} row(s), the fold has "
                    f"{y_true_arr.shape[0]}"))
            else:
                persistence_pred = last_known[mask]
                n_missing = int(np.count_nonzero(~np.isfinite(persistence_pred)))
                if n_missing:
                    skipped.append(SkippedBaseline(
                        "persistence",
                        f"{n_missing} of {n_scored} scored row(s) carry no last-known "
                        f"price, so the baseline could only be measured over a "
                        f"different row set than the model"))
                else:
                    baselines.append(BaselineResult(
                        name="persistence",
                        metrics=m.compute_all(y_true_clean, persistence_pred),
                        description="predicts the fare last observed for this row, "
                                    "unchanged",
                    ))

        # ── 2. Training-fold mean: one constant, learned before the test fold ─
        if n_scored == 0:
            skipped.append(SkippedBaseline(
                "train_mean", "no row has both a finite actual and a finite prediction"))
        elif y_train is None:
            skipped.append(SkippedBaseline(
                "train_mean",
                "caller supplied no training labels; the mean of the test actuals is "
                "not a baseline a forecaster could have computed"))
        else:
            train_arr = np.asarray(y_train, dtype=float)
            finite_train = train_arr[np.isfinite(train_arr)]
            if finite_train.size == 0:
                skipped.append(SkippedBaseline(
                    "train_mean", "no finite training label to take a mean of"))
            else:
                constant = float(np.mean(finite_train))
                baselines.append(BaselineResult(
                    name="train_mean",
                    metrics=m.compute_all(
                        y_true_clean, np.full(n_scored, constant, dtype=float)),
                    description=f"predicts the training fold's mean fare "
                                f"({constant:.2f}) for every row",
                ))

        # ── 3. Previous production model ─────────────────────────────────────
        if y_pred_production is None:
            skipped.append(SkippedBaseline(
                "previous_production", "no production predictions supplied"))
        elif n_scored == 0:
            skipped.append(SkippedBaseline(
                "previous_production",
                "no row has both a finite actual and a finite prediction"))
        else:
            prod_full = np.asarray(y_pred_production, dtype=float)
            # The length check comes before the mask, not after. `arr[mask]` with a
            # boolean mask longer than `arr` raises IndexError, so the guard on the
            # next line used to be unreachable for exactly the case it was written
            # for, and a length mismatch crashed the training run instead of
            # skipping one baseline.
            if prod_full.shape[0] != y_true_arr.shape[0]:
                skipped.append(SkippedBaseline(
                    "previous_production",
                    f"production predictions have {prod_full.shape[0]} row(s), the "
                    f"fold has {y_true_arr.shape[0]}"))
            else:
                prod_arr = prod_full[mask]
                n_missing = int(np.count_nonzero(~np.isfinite(prod_arr)))
                if n_missing:
                    skipped.append(SkippedBaseline(
                        "previous_production",
                        f"{n_missing} of {n_scored} scored row(s) have no production "
                        f"prediction"))
                else:
                    baselines.append(BaselineResult(
                        name="previous_production",
                        metrics=m.compute_all(y_true_clean, prod_arr),
                        description="the model currently serving, on these same rows",
                    ))

        verdict, improvement_pct, best_name, best_value, notes = self._verdict(
            new_metrics, baselines, primary_metric)

        if not baselines:
            logger.warning(
                "[Benchmark] no baseline could be computed, so there is no verdict. "
                "Skipped: %s",
                "; ".join(f"{s.name} ({s.reason})" for s in skipped) or "nothing",
            )
        else:
            logger.info(
                "[Benchmark] verdict=%s  new_%s=%s  best_baseline=%s (%s)  "
                "improvement=%.2f%%  over %d row(s)%s",
                verdict, primary_metric, _fmt(new_metrics.get(primary_metric)),
                best_name, _fmt(best_value), improvement_pct * 100.0, n_scored,
                ("  skipped: " + ", ".join(s.name for s in skipped)) if skipped else "",
            )

        return BenchmarkResult(
            new_model_metrics=new_metrics,
            baselines=baselines,
            verdict=verdict,
            primary_metric=primary_metric,
            improvement_pct=round(improvement_pct, 6),
            best_baseline=best_name,
            best_baseline_value=best_value,
            rows_scored=n_scored,
            feature_set_version=feature_set_version,
            skipped_baselines=skipped,
            notes=notes,
        )

    @staticmethod
    def _verdict(new_metrics, baselines, primary_metric):
        """Pick the baseline hardest to beat and grade the new model against it.

        Returns `(verdict, improvement_pct, best_name, best_value, notes)`.
        """
        higher_is_better = primary_metric in _HIGHER_IS_BETTER
        new_primary = new_metrics.get(primary_metric)

        best_name: Optional[str] = None
        best_value: Optional[float] = None
        for bl in baselines:
            value = bl.metrics.get(primary_metric)
            # A non-finite baseline figure is not a bar to clear. MAPE is NaN over a
            # fold with no positive actual, and `NaN < x` is False, so a NaN would
            # have silently won the "best baseline" comparison it could not lose.
            if value is None or not np.isfinite(value):
                continue
            if best_value is None or (value > best_value if higher_is_better
                                      else value < best_value):
                best_name, best_value = bl.name, float(value)

        if best_value is None:
            reason = ("no baseline could be computed" if not baselines else
                      f"no baseline produced a finite {primary_metric}")
            return "not_compared", 0.0, None, None, reason

        if new_primary is None or not np.isfinite(new_primary):
            return ("regressed", 0.0, best_name, best_value,
                    f"the new model's {primary_metric} is not measurable, which "
                    f"cannot be treated as beating a baseline that is")

        if best_value == 0.0:
            # A relative improvement over zero is undefined, and dividing by it used
            # to leave the verdict at "unchanged" — reporting parity with a baseline
            # that was in fact perfect. Compare absolutely and say so.
            if higher_is_better:
                better = new_primary > 0.0
            else:
                better = new_primary < 0.0
            same = new_primary == 0.0
            return (
                "unchanged" if same else ("improved" if better else "regressed"),
                0.0, best_name, best_value,
                f"baseline {best_name} scored exactly 0.0 on {primary_metric}, so the "
                f"relative improvement is undefined; compared absolutely",
            )

        if higher_is_better:
            improvement_pct = (new_primary - best_value) / abs(best_value)
        else:
            # For error metrics: improvement = baseline worse than new (baseline larger MAE)
            improvement_pct = (best_value - new_primary) / abs(best_value)

        verdict = "unchanged"
        if improvement_pct > _IMPROVEMENT_THRESHOLD:
            verdict = "improved"
        elif improvement_pct < -_IMPROVEMENT_THRESHOLD:
            verdict = "regressed"
        return verdict, improvement_pct, best_name, best_value, ""


def _fmt(value) -> str:
    """A metric for a log line, without formatting None as though it were a number."""
    if value is None:
        return "unavailable"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return str(value)


model_benchmark = ModelBenchmark()
