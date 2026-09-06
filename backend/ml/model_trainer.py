"""Model Trainer.

Orchestrates the full training workflow:
  HistoricalData → TrainingDatasetBuilder → FeatureEngineeringPipeline
  → DatasetSplitter → [HyperparameterOptimizer] → XGBRegressor
  → [CrossValidator] → ModelEvaluator → ModelBenchmark
  → FeatureImportanceAnalyzer → TrainingReport → ModelRegistry

No feature engineering logic lives here.
No prediction logic lives here.
Only orchestration.

The legacy PricePredictor.train() is unaffected.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pickle
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

BASE_ML_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_ML_DIR, "models")


def _get_git_commit() -> Optional[str]:
    """Return current HEAD commit SHA, or None if git is unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _get_env_metadata() -> Dict[str, Any]:
    """Collect runtime environment metadata for reproducibility auditing."""
    try:
        import xgboost
        xgb_ver = xgboost.__version__
    except Exception:
        xgb_ver = "unknown"

    return {
        "python_version": sys.version,
        "xgboost_version": xgb_ver,
        "numpy_version": np.__version__,
        "pandas_version": pd.__version__,
        "cpu_count": os.cpu_count(),
        "platform": platform.platform(),
    }


class ModelTrainer:
    """Orchestrates a full reproducible training run for one forecast horizon.

    Usage:
        from backend.ml.training_config import TrainingConfig
        from backend.ml.model_trainer import ModelTrainer

        config = TrainingConfig(feature_set_version="feature_set_v1", forecast_horizon=3)
        trainer = ModelTrainer()
        result, artifact = trainer.train(config)
    """

    def train(
        self,
        config: "TrainingConfig",  # noqa: F821 — forward ref to avoid circular import
        optimize: bool = False,
        n_optuna_trials: int = 50,
        run_cross_validation: bool = True,
    ) -> Tuple["TrainingResult", "ModelArtifact"]:  # noqa: F821
        """Run a full training pipeline for one horizon.

        Args:
            config: Immutable TrainingConfig for this run.
            optimize: Whether to run Optuna hyperparameter search first.
            n_optuna_trials: Number of Optuna trials (only if optimize=True).
            run_cross_validation: Whether to run cross-validation after training.

        Returns:
            (TrainingResult, ModelArtifact)
        """
        from backend.ml.training_config import TrainingConfig
        from backend.ml.training_result import TrainingResult
        from backend.ml.model_artifact import ModelArtifact
        from backend.ml.dataset_splitter import dataset_splitter
        from backend.ml.evaluation import model_evaluator
        from backend.ml.benchmark import model_benchmark
        from backend.ml.feature_importance import feature_importance_analyzer
        from backend.ml.hyperparameter_optimizer import hyperparameter_optimizer
        from backend.ml.cross_validation import time_series_cross_validator
        from backend.services.booking_curve_definition import lag_tolerance_days
        from backend.services.training_dataset_builder import training_dataset_builder

        horizon = config.forecast_horizon
        ts_start = time.monotonic()
        run_timestamp = datetime.now(timezone.utc)
        model_id = TrainingResult.make_model_id(horizon, run_timestamp.strftime("%Y%m%d_%H%M%S"))

        logger.info(f"[ModelTrainer] Starting run — model_id={model_id}  horizon={horizon}d")

        # ── 1. Load + engineer features ─────────────────────────────────────
        df_raw, df_features = training_dataset_builder.build(horizon)

        if df_features is None or df_features.empty:
            raise RuntimeError(
                f"[ModelTrainer] Training dataset is empty for horizon={horizon}d. "
                "Ensure historical data is populated before training."
            )

        if len(df_features) < config.minimum_training_rows:
            raise RuntimeError(
                f"[ModelTrainer] Insufficient training rows: "
                f"{len(df_features)} < {config.minimum_training_rows}"
            )

        # ── 2. Compute dataset hash ─────────────────────────────────────────
        dataset_hash = hashlib.sha256(
            pd.util.hash_pandas_object(df_features, index=True).values.tobytes()
        ).hexdigest()[:16]
        dataset_version = f"DS_{run_timestamp.strftime('%Y%m%d_%H%M%S')}"

        # ── 3. Encode categorical columns ───────────────────────────────────
        encoders: Dict[str, Dict[str, int]] = {}
        for col in ("origin_code", "destination_code", "airline_code"):
            if col in df_features.columns:
                df_features[col] = df_features[col].astype(str).str.upper()
                unique_vals = sorted(df_features[col].dropna().unique())
                encoders[col] = {v: i + 1 for i, v in enumerate(unique_vals)}
                df_features[col] = df_features[col].map(encoders[col]).fillna(0).astype(int)

        # ── 4. Identify feature + target columns ────────────────────────────
        non_feature_cols = {
            "target_price", "training_weight", "departure_date",
            "recorded_date", "recorded_at", "recorded_datetime",
            "departure_date_dt", "recorded_date_shift",
        }
        feature_cols = [c for c in df_features.columns if c not in non_feature_cols]

        if "target_price" not in df_features.columns:
            raise RuntimeError("[ModelTrainer] 'target_price' column missing from dataset.")

        df_valid = df_features.dropna(subset=["target_price"])
        if df_valid.empty:
            raise RuntimeError("[ModelTrainer] All target_price values are NaN.")

        # ── 5. Chronological split ──────────────────────────────────────────
        # The embargo width is the horizon *plus* the tolerance the label was
        # allowed to be late by, because that sum is when a training row's label
        # can still be realised. `attach_future_target` accepts, for a row
        # observed at `t`, the earliest fare on the same booking curve at or
        # after `t + h` and no later than `t + h + lag_tolerance_days(h)`. So a
        # row observed within that window of the first validation observation
        # carries a label recorded inside the validation period, and training on
        # it means the fit has already consumed a price from the fold it is about
        # to be scored on. Ordering by observation time does not prevent this —
        # it only orders the features. `price_model.train` computes the same
        # width from the same function, so the two training paths embargo
        # identically instead of one of them not at all.
        embargo_days = float(horizon) + lag_tolerance_days(horizon)

        split = dataset_splitter.split(
            df_valid,
            target_col="target_price",
            test_size=config.test_size,
            embargo_days=embargo_days,
        )
        split_record = split.to_dict()

        if split.train_rows < config.minimum_training_rows:
            raise RuntimeError(
                f"[ModelTrainer] Insufficient training rows after a "
                f"{embargo_days:.1f}d label embargo: {split.train_rows} < "
                f"{config.minimum_training_rows} "
                f"(purged {split.rows_purged_by_embargo} of "
                f"{split.train_rows_before_embargo}). The corpus does not yet "
                f"span enough time to train a {horizon}d forecaster without "
                f"reusing validation-period prices."
            )
        if not split.embargo_is_effective:
            # Not fatal — `train_rows` above is the criterion that decides
            # whether the run may proceed — but it must not pass silently: it is
            # the one condition under which the fold gap is narrower than the
            # label's realisation window.
            logger.warning(
                "[ModelTrainer] horizon=%dd: a %.1fd embargo was requested but "
                "the measured fold gap is %s day(s), so some training labels may "
                "have been realised inside the validation period.",
                horizon, embargo_days, split.gap_days,
            )
        logger.info(
            "[ModelTrainer] Split on '%s' — train=%d val=%d, %.1fd embargo "
            "purged %d of %d, gap %s day(s)",
            split.timestamp_column, split.train_rows, split.val_rows,
            embargo_days, split.rows_purged_by_embargo,
            split.train_rows_before_embargo, split.gap_days,
        )

        X_train = split.X_train[feature_cols].copy()
        X_val = split.X_val[feature_cols].copy()
        y_train = split.y_train
        y_val = split.y_val

        # ── 6. Optional hyperparameter optimization ─────────────────────────
        hyperparams = dict(config.hyperparameters)
        opt_result = None

        if optimize:
            opt_dir = os.path.join(MODELS_DIR, f"optuna_h{horizon}d")
            opt_result = hyperparameter_optimizer.optimize(
                X_train, y_train, X_val, y_val,
                n_trials=n_optuna_trials,
                random_seed=config.random_seed,
                output_dir=opt_dir,
            )
            hyperparams = opt_result.best_params

        # ── 7. Training ─────────────────────────────────────────────────────
        from xgboost import XGBRegressor
        np.random.seed(config.random_seed)

        model = XGBRegressor(
            **{k: v for k, v in hyperparams.items() if k != "objective"},
            objective=hyperparams.get("objective", "reg:squarederror"),
            random_state=config.random_seed,
        )

        sample_weights = None
        if "training_weight" in split.X_train.columns:
            sample_weights = np.maximum(split.X_train["training_weight"].fillna(1.0).values, 0.01)

        model.fit(X_train, y_train, sample_weight=sample_weights)
        logger.info(f"[ModelTrainer] Model trained — {len(X_train)} rows  horizon={horizon}d")

        # ── 8. Evaluation ───────────────────────────────────────────────────
        preds_val = model.predict(X_val)
        eval_report = model_evaluator.evaluate(
            y_val, preds_val,
            forecast_horizon=horizon,
            feature_set_version=config.feature_set_version,
        )

        # ── 9. Cross-validation ─────────────────────────────────────────────
        cv_report = None
        if run_cross_validation and len(df_valid) >= config.minimum_training_rows * 2:
            from xgboost import XGBRegressor as _XGBReg
            cv_model_proto = _XGBReg(
                **{k: v for k, v in hyperparams.items() if k != "objective"},
                objective=hyperparams.get("objective", "reg:squarederror"),
            )
            try:
                cv_report = time_series_cross_validator.validate(
                    df_valid,
                    cv_model_proto,
                    feature_cols,
                    "target_price",
                    n_folds=config.n_cv_folds,
                    strategy=config.validation_strategy,
                    feature_set_version=config.feature_set_version,
                    forecast_horizon=horizon,
                    min_train_rows=config.minimum_training_rows,
                    random_seed=config.random_seed,
                    # The same width as the holdout split, for the same reason,
                    # at every one of the fold boundaries. Without it the CV
                    # error could come out below the holdout error — the folds
                    # would each be leaking a little of their own validation
                    # period back into training, and the report printed the two
                    # numbers side by side as if they were comparable.
                    embargo_days=embargo_days,
                )
                eval_report.fold_metrics.extend(cv_report.fold_metrics)
                if not cv_report.boundary_is_strict_in_every_fold:
                    logger.warning(
                        "[ModelTrainer] horizon=%dd: cross-validation scored %d "
                        "fold(s) and at least one had training rows observed at "
                        "or after its own validation slice began; the fold "
                        "windows are in the training report.",
                        horizon, cv_report.n_folds,
                    )
            except Exception as e:
                logger.warning(f"[ModelTrainer] Cross-validation failed (non-fatal): {e}")

        # ── 10. Benchmarking ─────────────────────────────────────────────────
        # Both baseline inputs are supplied here because neither can be
        # reconstructed inside the benchmark without becoming an oracle: the
        # mean of the *test* labels is not a forecast anyone could have made,
        # and the last-known fare is a column of this fold that the benchmark
        # never receives.
        #
        # `price` — the fare already observed for the row — is in `feature_cols`
        # in this path, so the model can see it. That is legitimate (the current
        # fare is known at prediction time; it is the future fare that must not
        # leak) but it is exactly why the persistence baseline matters: a model
        # that has learned little beyond "repeat the input price" posts a
        # respectable MAE, and carrying that same price forward unchanged is the
        # only comparison that exposes it.
        last_known = (split.X_val["price"] if "price" in split.X_val.columns
                      else None)
        benchmark_result = model_benchmark.run(
            y_val, preds_val,
            y_last_known=last_known,
            y_train=y_train,
            feature_set_version=config.feature_set_version,
        )
        if not benchmark_result.was_compared:
            logger.warning(
                "[ModelTrainer] horizon=%dd benchmarked against no baseline at "
                "all, so its verdict is %r and means nothing: %s",
                horizon, benchmark_result.verdict,
                "; ".join(f"{s.name} ({s.reason})"
                          for s in benchmark_result.skipped_baselines),
            )

        # ── 11. Persist model + metadata ─────────────────────────────────────
        os.makedirs(MODELS_DIR, exist_ok=True)
        model_path = os.path.join(MODELS_DIR, f"model_h{horizon}d_{model_id}.pkl")
        metadata_path = os.path.join(MODELS_DIR, f"model_h{horizon}d_{model_id}.json")

        with open(model_path, "wb") as fh:
            pickle.dump({"model": model, "encoders": encoders, "feature_cols": feature_cols}, fh)

        metadata = {
            "model_id": model_id,
            "forecast_horizon": horizon,
            "feature_set_version": config.feature_set_version,
            "dataset_hash": dataset_hash,
            "dataset_version": dataset_version,
            "training_rows": split.train_rows,
            "validation_rows": split.val_rows,
            # How the folds were cut, not just how big they were. Row counts
            # alone cannot distinguish a split that embargoed its labels from one
            # that did not, so an artifact carrying only `training_rows` gave a
            # later reader no way to tell which experiment produced its metrics.
            "split": split_record,
            "metrics": eval_report.summary_metrics,
            "hyperparameters": hyperparams,
            "training_timestamp": run_timestamp.isoformat(),
            "git_commit": _get_git_commit(),
            "config_hash": config.config_hash(),
            "env": _get_env_metadata(),
            "benchmark": benchmark_result.to_dict() if benchmark_result else None,
        }

        with open(metadata_path, "w") as fh:
            json.dump(metadata, fh, indent=2, default=str)

        # ── 12. Feature importance ────────────────────────────────────────────
        importance_path = os.path.join(MODELS_DIR, f"importance_h{horizon}d_{model_id}.json")
        try:
            importance_report = feature_importance_analyzer.generate(
                model, feature_cols, X_val,
                horizon=horizon,
                feature_set_version=config.feature_set_version,
                importance_path=importance_path,
            )
        except Exception as e:
            logger.warning(f"[ModelTrainer] Feature importance generation failed (non-fatal): {e}")
            importance_report = None
            importance_path = None

        # ── 13. Training report ───────────────────────────────────────────────
        training_duration = time.monotonic() - ts_start
        report_path = os.path.join(MODELS_DIR, f"training_report_h{horizon}d_{model_id}.json")
        training_report = self._build_training_report(
            model_id=model_id,
            config=config,
            metadata=metadata,
            eval_report=eval_report,
            benchmark_result=benchmark_result,
            importance_report=importance_report,
            cv_report=cv_report,
            training_duration=training_duration,
        )
        with open(report_path, "w") as fh:
            json.dump(training_report, fh, indent=2, default=str)

        logger.info(f"[ModelTrainer] Training report persisted: {report_path}")

        # ── 14. Build result objects ──────────────────────────────────────────
        training_result = TrainingResult(
            model_id=model_id,
            forecast_horizon=horizon,
            feature_set_version=config.feature_set_version,
            dataset_hash=dataset_hash,
            dataset_version=dataset_version,
            training_rows=split.train_rows,
            validation_rows=split.val_rows,
            metrics=eval_report.summary_metrics,
            training_duration_seconds=round(training_duration, 2),
            training_timestamp=run_timestamp.isoformat(),
            git_commit=_get_git_commit(),
            config_hash=config.config_hash(),
            cv_metrics=cv_report.to_dict() if cv_report else {},
        )

        model_artifact = ModelArtifact(
            model_path=model_path,
            metadata_path=metadata_path,
            report_path=report_path,
            importance_path=importance_path,
            optimization_path=(
                os.path.join(MODELS_DIR, f"optuna_h{horizon}d", "best_params.json")
                if opt_result and opt_result.optuna_available else None
            ),
            registry_entry=None,
        )

        # ── 15. Register ─────────────────────────────────────────────────────
        try:
            from backend.services.model_registry import model_registry
            entry = model_registry.register_training_result(training_result, benchmark_result)
            model_artifact.registry_entry = entry
        except Exception as e:
            logger.warning(f"[ModelTrainer] Registry update failed (non-fatal): {e}")

        logger.info(
            f"[ModelTrainer] Run complete — model_id={model_id}  "
            f"horizon={horizon}d  MAE={eval_report.summary_metrics.get('mae', '?'):.2f}  "
            f"benchmark={benchmark_result.verdict}  "
            f"duration={training_duration:.1f}s"
        )

        return training_result, model_artifact

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_training_report(
        self,
        *,
        model_id: str,
        config: Any,
        metadata: Dict[str, Any],
        eval_report: Any,
        benchmark_result: Any,
        importance_report: Any,
        cv_report: Any,
        training_duration: float,
    ) -> Dict[str, Any]:
        """Construct the training_report.json payload."""
        report: Dict[str, Any] = {
            "model_id": model_id,
            "forecast_horizon": config.forecast_horizon,
            "model_type": config.model_type,
            "feature_set_version": config.feature_set_version,
            "random_seed": config.random_seed,
            "validation_strategy": config.validation_strategy,
            "hyperparameters": metadata.get("hyperparameters", {}),
            "training_timestamp": metadata.get("training_timestamp"),
            "git_commit": metadata.get("git_commit"),
            "config_hash": metadata.get("config_hash"),
            "env": metadata.get("env", {}),
            "dataset": {
                "hash": metadata.get("dataset_hash"),
                "version": metadata.get("dataset_version"),
                "training_rows": metadata.get("training_rows"),
                "validation_rows": metadata.get("validation_rows"),
                # `config.validation_strategy` above names the *cross-validation*
                # scheme. This is the holdout split that produced `evaluation`,
                # including the embargo width and the measured gap between the
                # folds, so the report states which experiment its headline
                # metrics came from rather than only how many rows were in it.
                "split": metadata.get("split"),
            },
            "evaluation": eval_report.to_dict() if eval_report else None,
            "benchmark": benchmark_result.to_dict() if benchmark_result else None,
            "cross_validation": cv_report.to_dict() if cv_report else None,
            "feature_importance_summary": (
                {
                    "top_10_by_gain": importance_report.top_n_by_gain(10),
                    "shap_available": importance_report.shap_available,
                }
                if importance_report else None
            ),
            "training_duration_seconds": round(training_duration, 2),
        }
        return report


model_trainer = ModelTrainer()
