"""System and model metadata, reported only from what was actually measured.

Every field here used to carry a hardcoded fallback: dataset_size defaulted to
4216 or 7103, training_timestamp to "2026-07-20T12:00:00Z", feature_count to 18,
and the validation metrics to mae 481.0 / rmse 921.0 / mape 5.04 / r2 0.9855.
Worse, get_model_metadata() floored the figure it published:

    if training_samples < 5000:
        training_samples = max(raw_samples, 7103)

so any real training set smaller than 5000 rows was reported to the API as at
least 7103 rows. None of those numbers came from a measurement. They are gone.
Unknown is now reported as null, and `unavailable` names which fields are null
and why, so a caller can tell "not measured" from "measured as zero".

Two further gaps closed here: `prediction_horizon` was a literal — `3` in
`get_system_info`, `0` in `get_model_metadata`, for the same quantity — and both
now read `model_registry.prediction_horizon`, the shortest horizon actually loaded.
And `load_error` / `refused_artifacts`, which `PricePredictor` has recorded since
the leak audit, reached no endpoint at all, so "no model has been trained" and
"models exist and this service refuses to serve them" were the same response.
"""
import logging
from typing import Any, Dict, List, Optional

from backend.ml.price_model import get_predictor
from backend.services.model_registry import model_registry
from backend.services.validation_service import validation_service

logger = logging.getLogger(__name__)


def _unmocked(value: Any) -> Any:
    """Return value unless it is a test double standing in for a real object."""
    return None if hasattr(value, "_mock_name") else value


class SystemInfoService:
    """Consolidates system configuration, validation state and model metrics."""

    def _feature_count(self) -> Optional[int]:
        """How many features the model actually takes, or None if unknowable."""
        expected = _unmocked(getattr(model_registry, "expected_features", None))
        if isinstance(expected, (list, tuple)) and expected:
            return len(expected)
        cols = _unmocked(getattr(get_predictor(), "feature_cols", None))
        if isinstance(cols, (list, tuple)) and cols:
            return len(cols)
        return None

    def get_system_info(self) -> Dict[str, Any]:
        predictor = get_predictor()
        latest_report = validation_service.get_latest_report()
        last_val_time = latest_report.get("timestamp") if latest_report else None

        fs_version = _unmocked(getattr(model_registry, "feature_set_version", None))
        model_version = _unmocked(getattr(predictor, "model_version", None))
        trained_at = _unmocked(getattr(predictor, "training_timestamp", None))
        dataset_size = _unmocked(getattr(predictor, "dataset_size", None))
        if not isinstance(dataset_size, int):
            dataset_size = None

        unavailable: List[str] = []
        if model_version is None:
            unavailable.append("model_version")
        if fs_version is None:
            unavailable.append("feature_set_version")
        if trained_at is None:
            unavailable.append("training_timestamp: no model has been trained or loaded")
        if dataset_size is None:
            unavailable.append("dataset_size: no training run has counted observations")

        # Why no model is loaded, and which artifacts were declined.
        #
        # `PricePredictor` has recorded both since the leak audit — `load()` appends
        # a reason to `refused_artifacts` for every artifact whose metadata lacks a
        # clean audit block, and `get_predictor()` writes the load exception to
        # `load_error` instead of reacting by training a replacement — and neither
        # field reached any endpoint. From outside the process a models directory in
        # which every artifact fails the audit was indistinguishable from an empty
        # one: `trained: false`, `training_timestamp: null`, and no reason given.
        # That is the difference between "nobody has trained this yet" and "a model
        # exists and this service refuses to serve it".
        load_error = _unmocked(getattr(predictor, "load_error", None))
        refused = _unmocked(getattr(predictor, "refused_artifacts", None)) or []
        refused = [str(r) for r in refused] if isinstance(refused, (list, tuple)) else []
        if refused:
            unavailable.append(
                f"refused_artifacts: {len(refused)} artifact(s) on disk were "
                f"declined; see the list for each reason")

        return {
            "schema_version": "1.0.0",
            "api_version": "v1",
            "backend_version": "11.0.0",
            "model_version": model_version,
            "feature_set_version": fs_version,
            "validator_version": "1.0.0",
            "training_timestamp": trained_at,
            "dataset_size": dataset_size,
            # Was the literal `3`, while `get_model_metadata` below published the
            # literal `0` for the same quantity — two endpoints of one service
            # disagreeing about which horizon the deployed model answers, and
            # neither reading the artifacts. `model_registry.prediction_horizon` is
            # the shortest horizon actually loaded, which is the number
            # `prediction_service` uses to pick the published point.
            "prediction_horizon": _unmocked(
                getattr(model_registry, "prediction_horizon", None)),
            "supported_horizons": _unmocked(
                getattr(model_registry, "supported_horizons", None)) or [],
            "trained": bool(getattr(predictor, "_trained", False)),
            "model_load_error": load_error,
            "refused_artifacts": refused,
            "last_validation_timestamp": last_val_time,
            "validation_status": (
                latest_report.get("overall_status") if latest_report else "UNAUDITED"
            ),
            "unavailable": unavailable,
        }

    def get_model_metadata(self) -> Dict[str, Any]:
        predictor = get_predictor()
        trained = bool(getattr(predictor, "_trained", False))

        # `get_performance()` calls `ensure_ready()`, which calls `load()`, which
        # raises FileNotFoundError when no artifact is loadable — so on precisely
        # the state this endpoint exists to describe, reading the metrics raised
        # and the whole response became a 500. Every other field below is already
        # built for "no model": `trained`, `model_load_error`, `refused_artifacts`
        # and `unavailable`. `/health` reports that condition as `degraded` and
        # `/info` as `trained: false` with a reason; this endpoint alone reported
        # it as a server fault, which makes a designed refusal indistinguishable
        # from a crash to anything watching the API.
        #
        # `ensure_ready()` returns immediately when `_trained` is set, so gating
        # on it means the call below can no longer reach `load()` at all. The
        # guard that remains is for a genuinely unexpected read failure, and that
        # is named in `unavailable` rather than swallowed.
        perf: Dict[str, Any] = {}
        perf_error: Optional[str] = None
        if trained:
            try:
                perf = predictor.get_performance() or {}
            except Exception as exc:  # reported below, never silent
                logger.warning("Reading the loaded model's metrics failed: %s", exc)
                perf_error = f"{type(exc).__name__}: {exc}"

        dataset_size = _unmocked(getattr(predictor, "dataset_size", None))
        if not isinstance(dataset_size, int):
            dataset_size = None
        # Prefer the count the trained model itself recorded; fall back to the
        # observation count the last build saw. No floor, no default.
        recorded = perf.get("training_samples")
        training_rows = recorded if isinstance(recorded, int) else dataset_size

        metric_keys = ("mae", "rmse", "mape", "median_ae", "r2")
        metrics = {k: float(perf[k]) for k in metric_keys
                   if isinstance(perf.get(k), (int, float))}

        unavailable: List[str] = []
        if training_rows is None:
            unavailable.append("training_rows: no training run has counted observations")
        missing_metrics = [k for k in metric_keys if k not in metrics]
        if missing_metrics:
            # Say which of the three reasons it is. "not present in the loaded
            # model's evaluation metrics" asserts a loaded model, which is the one
            # thing that is not true when nothing loaded.
            if perf_error:
                reason = f"reading the loaded model's metrics failed ({perf_error})"
            elif not trained:
                reason = "no model is loaded, so there are no evaluation metrics"
            else:
                reason = "not present in the loaded model's evaluation metrics"
            unavailable.append(
                "validation_metrics " + ", ".join(missing_metrics) + ": " + reason)

        refused = _unmocked(getattr(predictor, "refused_artifacts", None)) or []
        refused = [str(r) for r in refused] if isinstance(refused, (list, tuple)) else []

        return {
            "schema_version": "1.0.0",
            "api_version": "v1",
            "backend_version": "11.0.0",
            "model_name": "FareForecastEstimator",
            "algorithm": "XGBoost Regressor (Gradient Boosted Trees)",
            "training_date": _unmocked(getattr(predictor, "training_timestamp", None)),
            "feature_count": self._feature_count(),
            "training_rows": training_rows,
            "validation_metrics": metrics or None,
            # Was the literal `0`, i.e. "this model predicts the present" — the one
            # horizon `booking_curve_definition.MIN_TRAINABLE_HORIZON_DAYS` rules out
            # as a target, because at horizon 0 the label is the observation's own
            # price. `/info` published `3` for the same field. Both now read the
            # registry.
            "prediction_horizon": _unmocked(
                getattr(model_registry, "prediction_horizon", None)),
            "trained": trained,
            "model_load_error": _unmocked(getattr(predictor, "load_error", None)),
            "refused_artifacts": refused,
            "feature_set_version": _unmocked(
                getattr(model_registry, "feature_set_version", None)),
            "unavailable": unavailable,
        }


# Global instance for DI
system_info_service = SystemInfoService()
