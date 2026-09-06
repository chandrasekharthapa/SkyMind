"""Forecast Evaluator Service.

Aggregate accuracy over forecasts whose outcome is already known: given a frame
of `forecast_price` / `actual_price` pairs it reports the error metrics, in total
or grouped by any column the frame carries (route, airline, horizon, month, lead
time — whatever the caller has put there).

The per-forecast half of this job lives elsewhere and is the part that runs:
`forecast_evaluation_scheduler` resolves each pending forecast against the
realised fare on the same booking curve and writes the outcome to
`forecast_store`. This module aggregates such outcomes once they are loaded.

Two things this file used to do, and no longer does, because they were the audit's
findings about it:

  * **It restated the metrics.** MAE, RMSE, MAPE, median absolute error and bias
    were computed inline here, and the MAPE used `abs_error / max(actual, 1.0)` —
    the clipped denominator that `backend.ml.metrics.mape_with_coverage` exists to
    document as wrong, since it does not skip a non-positive actual, it scores the
    row against a fare of ₹1. Every figure now comes from `backend.ml.metrics`, so
    there is one definition of each metric in the project. It also published
    `bias` and `drift` as separate diagnostics; `mean(pred) - mean(actual)` and
    `mean(pred - actual)` are the same number, so `drift` was the bias under a
    second name. The metric set's own name for it, `mean_error`, is what is
    reported.

  * **It answered with zeros when it had nothing.** An empty frame returned
    `{"mae": 0.0, "rmse": 0.0, "mape": 0.0, ...}` — a *perfect* forecaster. The
    undefined case is now NaN, via `metrics.undefined_metrics()`, and the row
    counts say why.

Removed outright: `persist_evaluation`, `evaluate_with_history`,
`track_historical_prediction`, `get_prediction_error_history`,
`get_rolling_metrics` and `calculate_recommendation_accuracy`. Nothing in the
repository called any of them; they read and wrote
`backend/ml/models/evaluation_history.jsonl`, which has never existed, and
`get_rolling_metrics` returned `rolling_mae: 0.0` for that empty history.
`track_historical_prediction` wrote per-prediction records into the same file the
rolling metrics averaged as per-evaluation records, so the first caller of both
would have got the shapes mixed. Aggregate history belongs in `forecast_store`
alongside the outcomes, not in a side file with two record shapes.

`recommendation_accuracy`, `average_savings` and `average_loss` went with them.
They cannot be computed from these columns: whether "book now" was right depends
on the fare that was available when the advice was given, and the frame carries
the forecast and the outcome, not the quoted fare. What the old code scored
instead was whether the realised fare landed on the forecast's expected side
within a 2% dead band — with `MONITOR` counted as automatically correct, so a
recommender that always said `MONITOR` scored 100%. Recording the quoted fare on
the forecast row is what these metrics need first.
"""

import logging
from typing import Any, Dict

import pandas as pd

from backend.ml import metrics as m

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ("actual_price", "forecast_price")


class ForecastEvaluator:
    def evaluate(self, df_eval: pd.DataFrame) -> Dict[str, Any]:
        """Error metrics for a frame of realised-vs-forecast fare pairs.

        Returns `backend.ml.metrics.METRIC_KEYS` plus `sample_count` (pairs
        scored) and `excluded_rows` (rows dropped for an unreadable fare on
        either side). Every metric is NaN when no pair is usable — read
        `sample_count` before any figure here.

        Raises:
            ValueError: if the frame is missing `actual_price` or
                `forecast_price`. A caller holding the wrong frame is a bug, not
                an evaluation with no data.
        """
        if df_eval is None or len(df_eval) == 0:
            return self._undefined(0, 0)

        missing = [c for c in REQUIRED_COLUMNS if c not in df_eval.columns]
        if missing:
            raise ValueError(
                f"cannot evaluate forecasts: frame has no {', '.join(missing)} "
                f"column(s); it has {list(df_eval.columns)}"
            )

        # `to_numeric(errors="coerce")` rather than `astype(float)`: a fare that
        # arrives as `None` or as a string raises on astype, and pandas' own
        # `.mean()` would have skipped it silently. Coercing and counting makes
        # the exclusion visible.
        actuals = pd.to_numeric(df_eval["actual_price"], errors="coerce")
        preds = pd.to_numeric(df_eval["forecast_price"], errors="coerce")

        usable = actuals.notna() & preds.notna()
        n_used = int(usable.sum())
        n_excluded = int(len(df_eval) - n_used)

        if n_used == 0:
            logger.warning(
                "[ForecastEvaluator] %d row(s), none with a readable fare on both "
                "sides — every metric is undefined (NaN).", len(df_eval))
            return self._undefined(0, n_excluded)

        if n_excluded:
            logger.info(
                "[ForecastEvaluator] scoring %d of %d row(s); %d excluded for an "
                "unreadable actual or forecast fare.",
                n_used, len(df_eval), n_excluded)

        report: Dict[str, Any] = m.compute_all(
            actuals[usable].to_numpy(dtype=float),
            preds[usable].to_numpy(dtype=float),
        )
        report["sample_count"] = n_used
        report["excluded_rows"] = n_excluded
        return report

    def evaluate_grouped(self, df_eval: pd.DataFrame, group_col: str) -> Dict[str, Dict[str, Any]]:
        """`evaluate` per distinct value of `group_col`. Empty if the column is absent."""
        if df_eval is None or len(df_eval) == 0 or group_col not in df_eval.columns:
            return {}
        return {str(val): self.evaluate(group)
                for val, group in df_eval.groupby(group_col, dropna=False)}

    @staticmethod
    def _undefined(sample_count: int, excluded_rows: int) -> Dict[str, Any]:
        report: Dict[str, Any] = m.undefined_metrics()
        report["sample_count"] = sample_count
        report["excluded_rows"] = excluded_rows
        return report


forecast_evaluator = ForecastEvaluator()
