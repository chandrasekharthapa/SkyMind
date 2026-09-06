"""Model Registry.

Manages active prediction models, exposing capability matrices, feature schemas,
versions, and timestamps dynamically from the loaded PricePredictor.
Loads dataset metadata from model.metadata.json.

Extended (Milestone 5) to support:
  - latest / best / production / archived registration slots
  - register_training_result() for the new ModelTrainer workflow
  - registry.json persistence for full metadata auditability
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.ml.price_model import get_predictor

logger = logging.getLogger(__name__)

_REGISTRY_JSON = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "ml", "models", "registry.json"
)

class ModelRegistry:
    """Registry for both the live PricePredictor and new ModelTrainer training runs."""

    def __init__(self, predictor: Optional[Any] = None):
        # Resolved on first use, not here. This was
        # `self._predictor = predictor or get_predictor()`, and because the
        # singleton at the bottom of this module is built at module scope, merely
        # importing this file reached into `backend/ml/models/` and read whatever
        # artifacts were there. When `get_predictor` reacted to a failed load by
        # training, that import also started an XGBoost fit whose dataset builder
        # imports this module back — so a missing model artifact surfaced as
        # `ImportError: ... partially initialized module`. `get_predictor` no longer
        # trains; resolving lazily closes the other half, so importing the registry
        # is just an import.
        self._resolved_predictor: Optional[Any] = predictor
        # Registration slots: keyed by slot name → entry dict (archived is a list)
        self._slots: Dict[str, Any] = {
            "latest": None,
            "best": None,
            "production": None,
            "archived": [],
        }

    @property
    def _predictor(self) -> Any:
        """The predictor this registry reports on, resolved on first access."""
        if self._resolved_predictor is None:
            self._resolved_predictor = get_predictor()
        return self._resolved_predictor

    @_predictor.setter
    def _predictor(self, predictor: Any) -> None:
        """Assignable: the verification harness swaps in probe predictors."""
        self._resolved_predictor = predictor

    def get_metadata(self, horizon: Optional[int] = None) -> Dict[str, Any]:
        """Metadata for one horizon; by default the horizon actually being served.

        The default was the literal `3`, and every one of the eleven callers in this
        file took it. So on a build whose loadable artifacts were, say, 1d and 7d,
        every metadata property here — dataset version, dataset hash, training
        timestamp, observation count, evaluation metrics, feature-set version —
        looked up horizon 3, found nothing, and returned its fallback. `/system` then
        published those fallbacks as the deployed model's provenance.
        """
        metadata_dict = getattr(self._predictor, "metadata", {})
        if not metadata_dict:
            return {}
        if horizon is None:
            horizon = getattr(self._predictor, "primary_horizon", None)
            if horizon is None:
                return {}
        return metadata_dict.get(horizon, {})

    @property
    def model_version(self) -> Optional[str]:
        """The version the active artifact records for itself, or None.

        This was `getattr(self._predictor, "model_version", "2.0.0")`. The default
        never fired — `PricePredictor.__init__` does assign the attribute — but the
        value it returns is a literal that no training run changes, so it was the
        same string before and after a retrain. Reading the *artifact's* metadata
        first at least reports what the loaded pickle was stamped with rather than
        what the running code happens to say, which is the same ordering
        `training_timestamp` and `dataset_version` below already use.

        `model_version` is a code-contract version, not an artifact identity: two
        artifacts trained a month apart carry the same one. `dataset_version`,
        `dataset_hash` and `training_timestamp` are the fields that distinguish
        them, and all three are read off metadata.
        """
        recorded = self.get_metadata().get("model_version")
        if isinstance(recorded, str) and recorded:
            return recorded
        declared = getattr(self._predictor, "model_version", None)
        return declared if isinstance(declared, str) and declared else None

    @property
    def feature_schema_version(self) -> Optional[str]:
        """The feature-schema version the active artifact records, or None.

        Same change as `model_version` above: metadata first, then the predictor,
        then nothing. No shipped artifact records this key — all three quarantined
        metadata files have `feature_schema_version: null` — so the predictor
        attribute is what answers today, and when neither says, the answer is None
        rather than a "2.0.0" invented by the reader.
        """
        recorded = self.get_metadata().get("feature_schema_version")
        if isinstance(recorded, str) and recorded:
            return recorded
        declared = getattr(self._predictor, "feature_schema_version", None)
        return declared if isinstance(declared, str) and declared else None

    @property
    def training_timestamp(self) -> Optional[str]:
        """When the active model was trained, or None if nothing is trained.

        The default used to be the literal "2026-07-20T12:00:00Z". Because no
        code ever assigned `predictor.training_timestamp`, that fixed date was
        what every caller received — including the /system endpoints, which
        published it as fact.
        """
        meta = self.get_metadata()
        return meta.get("training_timestamp") or getattr(
            self._predictor, "training_timestamp", None)

    @property
    def dataset_version(self) -> Optional[str]:
        """The version of the training dataset used to train the current model."""
        # Was "DATASET_2026_Q3_V1" — a version string for a dataset that was
        # never compiled under that name.
        return self.get_metadata().get("dataset_version")

    @property
    def dataset_hash(self) -> Optional[str]:
        """The MD5 hash of the training dataset, or None if not recorded."""
        return self.get_metadata().get("dataset_hash")

    @property
    def dataset_timestamp(self) -> Optional[str]:
        """When the training dataset was compiled, or None if not recorded."""
        return self.get_metadata().get("training_timestamp")

    @property
    def training_policy_version(self) -> str:
        """Version of the training policy configuration applied during dataset validation."""
        meta = self.get_metadata()
        return meta.get("training_policy_version", "1.0.0")

    @property
    def observation_count(self) -> int:
        """Raw historical observations in the training dataset, or 0 if unrecorded.

        The fallback was `4200` — a figure no run ever counted, published by
        `/system` as the size of the training corpus for any build whose metadata
        did not record one (which, with the default horizon fixed at 3, was most of
        them).
        """
        count = self.get_metadata().get("observation_count")
        if isinstance(count, int) and count >= 0:
            return count
        logger.warning(
            "Deployed model metadata records no observation_count; reporting 0 "
            "rather than an assumed corpus size.")
        return 0

    @property
    def coverage_days(self) -> int:
        """Span in days covered by the training observations, or 0 if unrecorded.

        The fallback was `30`, with the same problem as `observation_count`'s 4200.
        """
        days = self.get_metadata().get("coverage_days")
        if isinstance(days, int) and days >= 0:
            return days
        logger.warning(
            "Deployed model metadata records no coverage_days; reporting 0 rather "
            "than an assumed 30-day span.")
        return 0

    @property
    def duplicate_rate(self) -> float:
        """The rate of duplicates in the training dataset."""
        meta = self.get_metadata()
        return meta.get("duplicate_rate", 0.0)

    @property
    def missing_rate(self) -> float:
        """The rate of missing value fields in the training dataset."""
        meta = self.get_metadata()
        return meta.get("missing_rate", 0.0)

    @property
    def evaluation_metrics(self) -> Dict[str, Any]:
        """Test-set evaluation metrics (MAE, RMSE, MAPE) for the served horizon."""
        meta = self.get_metadata()
        recorded = meta.get("evaluation_metrics")
        if isinstance(recorded, dict) and recorded:
            return recorded
        # Same horizon as `get_metadata()` resolves to, rather than the literal 3
        # this used: `getattr(self._predictor, "metrics", {}).get(3, {})`.
        primary = getattr(self._predictor, "primary_horizon", None)
        metrics = getattr(self._predictor, "metrics", {}) or {}
        return metrics.get(primary, {}) if primary is not None else {}

    @property
    def training_dataset_version(self) -> str:
        """Legacy compatibility wrapper for dataset_version."""
        return self.dataset_version

    @property
    def expected_features(self) -> List[str]:
        """Strict ordered list of feature names expected by the model's xgboost estimator."""
        return getattr(self._predictor, "feature_cols", [])

    @property
    def model_capabilities(self) -> List[str]:
        """Dynamic array mapping capabilities supported by this model instance."""
        caps = ["predict"]
        if self.supports_forecast:
            caps.append("forecast")
        return caps

    @property
    def supports_live_market_features(self) -> bool:
        """Indicates if the deployed model utilizes real-time features like is_live."""
        return "is_live" in self.expected_features

    @property
    def supports_forecast(self) -> bool:
        """Indicates if the model registry registers forecasting abilities."""
        return hasattr(self._predictor, "forecast")

    @property
    def supports_confidence_interval(self) -> bool:
        """True if the model produces valid prediction bands."""
        return True

    @property
    def supports_multi_day_prediction(self) -> bool:
        """True if multi day predictions sequences are supported."""
        return True

    @property
    def prediction_horizon(self) -> Optional[int]:
        """The horizon the deployed model answers by default, in days, or None.

        This read `getattr(self._predictor, "prediction_horizon", 3)` against an
        attribute `PricePredictor` never assigns, so the property was the literal 3
        behind a `getattr` — reported as the deployed model's horizon whether or not
        a 3d artifact existed. `prediction_service` uses it twice: to pick which
        forecast point becomes the published `predicted_price`, and to choose whose
        accuracy figure is published beside it. With only 1d and 7d artifacts loaded
        it therefore hunted a 3d point that the curve no longer contains.

        `PricePredictor.primary_horizon` is the shortest horizon actually loaded.
        When nothing is loaded this returned `min(supported_horizons)`, justified in
        this docstring as keeping an `int` contract for the response model — but
        `GET /api/v1/system/model/metadata` is annotated `Dict[str, Any]` and has no
        response model, so nothing required the int and the endpoint published
        `prediction_horizon: 1` beside `trained: false` and a `model_load_error`. A
        horizon is a claim about an artifact; with no artifact there is no claim, and
        `1` was the same fabrication as a 12:00 departure time on a row that never
        carried one. It is `None` now, and the two consumers refuse rather than
        substitute.
        """
        horizon = getattr(self._predictor, "primary_horizon", None)
        if isinstance(horizon, int) and horizon > 0:
            return horizon
        logger.warning(
            "Predictor %s has no loaded horizon, so none is reported: "
            "prediction_horizon is null and predictions are refused in this state.",
            type(self._predictor).__name__,
        )
        return None

    @property
    def target_definition(self) -> str:
        """What the deployed model was trained to predict, as the model states it.

        `training_target` is an alias kept for existing callers. Both fall back to
        `"unknown"` rather than to `"Future Lowest Fare"`, which was a hardcoded
        description of a target no production path ever built: the label is the
        fare on the same booking curve at the earliest observation on or after
        `t + horizon` days, and the only code that ever took a per-day *minimum*
        was a method production did not call. A wrong description of the target is
        worse than an absent one, because it is the sentence a reader trusts when
        deciding whether a number means what they think.
        """
        return getattr(self._predictor, "training_target", "unknown")

    @property
    def training_target(self) -> str:
        """Alias of `target_definition`; see it for why the fallback is "unknown"."""
        return self.target_definition

    @property
    def supported_routes(self) -> List[str]:
        """Routes the loaded artifacts were actually fitted on, `origin-destination`.

        This returned the literal `["DEL-BOM", "BOM-DEL"]`. It was the answer
        `/capabilities` gave with no model loaded at all, with a model trained on
        one route, and with a model trained on forty — advertising two routes that
        may never have been trained while hiding every route that was.

        `train()` now records the routes surviving each horizon's row filters into
        the artifact's `trained_routes` key and `load()` reads it back. An empty
        list means no loaded artifact says, which is the honest answer and the same
        convention `supported_horizons` follows.
        """
        routes = getattr(self._predictor, "trained_routes", None)
        if not isinstance(routes, list) or not routes:
            logger.warning(
                "Predictor %s records no trained routes; reporting none rather than "
                "advertising a fixed route list.",
                type(self._predictor).__name__,
            )
            return []
        return sorted({str(r).strip().upper() for r in routes if r})

    @property
    def supports_forecasting(self) -> bool:
        """True only when a horizon model is loaded that a forecast can be built from.

        The fallback was `True`. A predictor with no `supports_forecasting`
        attribute — and one with the attribute still at its `__init__` default of
        `True`, which is every predictor that has never loaded anything — advertised
        forecasting while `forecast()` raised `InsufficientHistory` on every call.
        """
        declared = bool(getattr(self._predictor, "supports_forecasting", False))
        if not declared:
            return False
        if getattr(self._predictor, "legacy_mode", False):
            return declared
        return bool(getattr(self._predictor, "models", None))

    @property
    def supported_horizons(self) -> List[int]:
        """Horizons the loaded predictor will actually answer for, in days.

        The fallback is empty, not `[0, 1, 3, 7]`. A predictor that does not
        declare its horizons is one this registry knows nothing about, and the
        old default named four — including horizon 0, which
        `booking_curve_definition.MIN_TRAINABLE_HORIZON_DAYS` rules out as a
        target — so `/capabilities` advertised horizons no model had been trained
        for whenever the attribute was missing. An empty list is the honest
        answer to "what can this thing predict" when nothing has said.
        """
        horizons = getattr(self._predictor, "supported_horizons", None)
        if horizons is None:
            logger.warning(
                "Predictor %s declares no supported_horizons; reporting none "
                "rather than assuming a default set.",
                type(self._predictor).__name__,
            )
            return []
        return horizons

    @property
    def feature_set_version(self) -> str:
        """Which feature set the active model requires: "legacy" or "feature_set_v1".

        Taken from the loaded artifact's metadata if it records one, then from the
        predictor, and only then inferred from the feature-column count — and the
        inference says so in the log, because it is a guess about a model's input
        contract read off a length.

        The whole expression used to be a single `getattr` whose *default* was that
        inference. Nothing assigned `predictor.feature_set_version`, so the default
        was the only branch that ever ran, and the 16-name legacy `feature_cols`
        list made it `"legacy"` unconditionally. `PricePredictor` now declares
        `feature_set_version = "legacy"` outright and `train()` records it in the
        artifact, so the first two branches carry every real case and the inference
        is reached only by a predictor double or an artifact written before either
        change. Type-guarding here also removes the
        reason `training_dataset_builder.build` imported `unittest.mock` in
        production: this value selects a feature builder in
        `feature_engineering_pipeline`, which raises `ValueError` on a string it
        does not know, so a test double's auto-generated attribute reaching it was
        a crash the builder had to defend against downstream of the guess.
        """
        recorded = self.get_metadata().get("feature_set_version")
        if isinstance(recorded, str) and recorded:
            return recorded
        declared = getattr(self._predictor, "feature_set_version", None)
        if isinstance(declared, str) and declared:
            return declared
        inferred = "legacy" if len(self.expected_features) <= 16 else "feature_set_v1"
        logger.warning(
            "Neither the loaded artifact's metadata nor predictor %s declares a "
            "feature_set_version; inferring %r from %d feature column(s).",
            type(self._predictor).__name__, inferred, len(self.expected_features))
        return inferred

    @property
    def feature_count(self) -> int:
        """Expected feature columns count."""
        return len(self.expected_features)

    @property
    def required_feature_order(self) -> List[str]:
        """Expected ordering of features."""
        return self.expected_features

    # ── Registration API (Milestone 5) ─────────────────────────────────────

    def register_training_result(
        self,
        result: Any,          # TrainingResult
        benchmark: Any,       # BenchmarkResult | None
    ) -> Dict[str, Any]:
        """Register a completed training run in the appropriate slots.

        Rules:
        - Always updates 'latest'.
        - Updates 'best' if new model has lower MAE than current best.
        - Updates 'production' only if the benchmark returned a verdict in
          `TrainingPolicy.PROMOTABLE_VERDICTS`. A run with no benchmark object,
          or one whose verdict is `not_compared`, does not promote: the gate is
          the comparison, so an absent comparison cannot clear it.
        - Previous production entry is moved to 'archived'.

        Returns:
            Registry entry dict that was written.
        """
        entry: Dict[str, Any] = {
            "model_id": result.model_id,
            "forecast_horizon": result.forecast_horizon,
            "feature_set_version": result.feature_set_version,
            "dataset_hash": result.dataset_hash,
            "dataset_version": result.dataset_version,
            "training_rows": result.training_rows,
            "validation_rows": result.validation_rows,
            "metrics": result.metrics,
            "training_duration_seconds": result.training_duration_seconds,
            "training_timestamp": result.training_timestamp,
            "git_commit": result.git_commit,
            "config_hash": result.config_hash,
            "benchmark_verdict": benchmark.verdict if benchmark else "unknown",
            "benchmark_improvement_pct": (
                benchmark.improvement_pct if benchmark else None
            ),
            # Which baseline the verdict is against, so a registry entry states
            # what the model was better *than*. "improved" on its own does not.
            "benchmark_baseline": getattr(benchmark, "best_baseline", None),
            "benchmark_baseline_value": getattr(benchmark, "best_baseline_value", None),
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }

        # Always latest
        self._slots["latest"] = entry
        logger.info(f"[ModelRegistry] Registered '{result.model_id}' → slot=latest")

        # Best: lower MAE wins
        current_best = self._slots.get("best")
        new_mae = result.metrics.get("mae", float("inf"))
        best_mae = (
            current_best["metrics"].get("mae", float("inf"))
            if current_best else float("inf")
        )
        if new_mae < best_mae:
            self._slots["best"] = entry
            logger.info(f"[ModelRegistry] New best model → MAE={new_mae:.2f}")

        # Production: only on a verdict from a completed comparison.
        #
        # This was `benchmark is None or benchmark.verdict != "regressed"`, which
        # promoted a model that had never been benchmarked at all, and promoted
        # every verdict string it did not recognise — including the
        # `"not_compared"` that `ModelBenchmark` now returns when no baseline
        # could be computed. The set is imported from `TrainingPolicy` rather
        # than restated so the registry and the policy cannot drift apart on
        # what "promotable" means.
        from backend.services.training_policy import TrainingPolicy

        verdict = benchmark.verdict if benchmark else None
        if verdict in TrainingPolicy.PROMOTABLE_VERDICTS:
            current_prod = self._slots.get("production")
            if current_prod is not None:
                self._slots["archived"].append(current_prod)
                logger.info(
                    f"[ModelRegistry] Archived previous production: "
                    f"{current_prod.get('model_id')}"
                )
            self._slots["production"] = entry
            logger.info(
                f"[ModelRegistry] Promoted '{result.model_id}' → slot=production "
                f"(benchmark={verdict})"
            )
        else:
            logger.warning(
                f"[ModelRegistry] Model '{result.model_id}' NOT promoted to "
                f"production (benchmark verdict="
                f"{verdict if verdict is not None else 'absent'}). Previous "
                f"production retained."
            )

        self._persist_registry()
        return entry

    def get_slot(self, slot: str) -> Optional[Dict[str, Any]]:
        """Return the registry entry for a named slot."""
        if slot == "archived":
            return self._slots["archived"]  # returns list
        return self._slots.get(slot)

    def _persist_registry(self) -> None:
        """Write registry slots to registry.json for auditability."""
        try:
            os.makedirs(os.path.dirname(_REGISTRY_JSON), exist_ok=True)
            payload = {
                "latest": self._slots.get("latest"),
                "best": self._slots.get("best"),
                "production": self._slots.get("production"),
                "archived": self._slots.get("archived", []),
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
            with open(_REGISTRY_JSON, "w") as fh:
                json.dump(payload, fh, indent=2, default=str)
        except Exception as e:
            logger.warning(f"[ModelRegistry] Failed to persist registry.json: {e}")

    def load_registry(self) -> None:
        """Reload slots from registry.json if it exists."""
        try:
            if os.path.isfile(_REGISTRY_JSON):
                with open(_REGISTRY_JSON) as fh:
                    data = json.load(fh)
                self._slots["latest"] = data.get("latest")
                self._slots["best"] = data.get("best")
                self._slots["production"] = data.get("production")
                self._slots["archived"] = data.get("archived", [])
        except Exception as e:
            logger.warning(f"[ModelRegistry] Failed to load registry.json: {e}")


# Singleton registry instance
model_registry = ModelRegistry()

