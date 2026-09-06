"""Production Readiness Module (Milestone 8).

Automatically executes all validation subsystems and generates production_readiness_report.json
with overall status: PASS, WARNING, or FAIL.

Section 5 exercises the prediction and recommendation validators against real
output from the production path. It used to build a `sample_pred` literal:

    sample_pred = {
        "predicted_price": 5938.86,
        "forecast": [
            {"day": 0, "price": 5938.86, "lower": 5582.53, "upper": 6295.19},
            ...
        ],
        "recommendation": {"decision": "MONITOR"},
    }
    pred_val = prediction_validation_service.validate_prediction_response(sample_pred)
    rec_val  = recommendation_validation_service.validate_recommendation(
        recommendation=sample_pred["recommendation"],
        current_lowest_fare=5922.0, predicted_price=5938.86)

Every figure there was chosen to satisfy the rules being applied to it: the bounds
bracket the prices, the decision is a member of the accepted set, and 5938.86
against 5922.0 is a 0.3% delta, inside every contradiction threshold. So the two
checks below that read `pred_val["valid"]` and `rec_val["valid"]` could not fail,
whatever the real system did — and this file is the thing that decides whether the
report says PASS. A readiness suite validating a payload it wrote itself measures
its own arithmetic.
"""

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.services.historical_data_audit import historical_data_audit_service
from backend.services.feature_validation import feature_validation_service
from backend.services.model_readiness import model_readiness_service
from backend.services.drift_detection import drift_detection_service
from backend.services.prediction_validation import prediction_validation_service
from backend.services.recommendation_validation import recommendation_validation_service
from backend.utils.report_paths import REPORTS_DIR, report_path, write_report

logger = logging.getLogger(__name__)

REPORT_PATH = report_path("production_readiness_report.json")

# How far ahead the sampled prediction asks about. Any future date satisfies
# `PredictionValidator.validate_request`; 21 days is far enough that a fare is
# normally quotable and near enough to sit inside the corpus's booking window.
SAMPLE_DEPARTURE_OFFSET_DAYS = 21


class ProductionReadinessService:
    def __init__(self):
        pass

    @staticmethod
    def _predict_sync(origin: str, destination: str, departure_date: str) -> Dict[str, Any]:
        """`prediction_service.predict` from synchronous code.

        Run on its own thread with its own event loop, because this method is
        called from a sync entry point that may itself be running inside one —
        `asyncio.run` raises in that case.
        """
        from backend.services.prediction_service import prediction_service

        def _run() -> Dict[str, Any]:
            return asyncio.run(
                prediction_service.predict(origin, destination, departure_date)
            )

        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_run).result()

    def _live_predictions(self) -> Tuple[List[Dict[str, Any]], List[str]]:
        """One real prediction per route the loaded artifacts were fitted on.

        Returns the payloads that came back and the reasons the rest did not. A
        refusal is a reason, not a substituted payload: the production path
        declining to answer is the finding, and hiding it behind a literal is what
        made these checks unfalsifiable.
        """
        from backend.services.model_registry import model_registry

        routes = model_registry.supported_routes
        if not routes:
            return [], [
                "no loaded artifact records a trained route, so there is no route "
                "the production path can be asked about"
            ]

        departure = (
            datetime.now(timezone.utc).date() + timedelta(days=SAMPLE_DEPARTURE_OFFSET_DAYS)
        ).strftime("%Y-%m-%d")

        payloads: List[Dict[str, Any]] = []
        reasons: List[str] = []
        for route in routes:
            parts = str(route).split("-")
            if len(parts) != 2 or not all(len(p) == 3 and p.isalpha() for p in parts):
                reasons.append(f"route {route!r} is not an `AAA-BBB` pair")
                continue
            origin, destination = parts
            try:
                payloads.append(self._predict_sync(origin, destination, departure))
            except Exception as err:
                # Recorded, not raised: one unservable route should not stop the
                # report, and the reason belongs in it.
                reasons.append(f"{route}: {type(err).__name__}: {err}")

        return payloads, reasons

    @staticmethod
    def _unrun(reasons: List[str]) -> Dict[str, Any]:
        """The shape a validator's slot takes when there was nothing to validate.

        `valid` is False, deliberately. A check that did not run has not been
        satisfied, and this report's only consumer reads `valid` to decide whether
        to say PASS.
        """
        return {
            "valid": False,
            "status": "NOT_RUN",
            "errors": ["no live prediction could be obtained from the production path"],
            "reasons": reasons,
        }

    def run_full_validation(self, report_dir: Optional[str] = None) -> Dict[str, Any]:
        """Run all production validation sub-systems and compile master readiness report.

        `report_dir` redirects this report *and* every sub-report into one
        directory, each keeping its usual filename. It defaults to `REPORTS_DIR`.
        A test passes `tmp_path` so that a validation run cannot rewrite files in
        the working tree — which is what it used to do, four of them, all tracked.
        """
        logger.info("[ProductionReadiness] Executing master production validation suite...")

        out_dir = report_dir or REPORTS_DIR

        def _dest(name: str) -> str:
            return os.path.join(out_dir, name)

        # 1. Historical Data Audit
        data_audit = historical_data_audit_service.run_audit(
            destination=_dest("historical_data_report.json"))

        # 2. Feature Validation (using training dataset features)
        from backend.database.database import database as db
        df_raw = db.get_training_dataset()
        feature_val = feature_validation_service.validate_features_dataframe(
            df_raw, destination=_dest("feature_validation_report.json"))

        # 3. Model Readiness Check
        model_readiness = model_readiness_service.check_readiness()

        # 4. Drift Detection
        drift_report = drift_detection_service.run_drift_analysis(
            destination=_dest("drift_report.json"))

        # 5. Prediction & recommendation validation, on real output.
        predictions, prediction_reasons = self._live_predictions()
        if predictions:
            first = predictions[0]
            pred_val = prediction_validation_service.validate_prediction_response(first)
            recommendation = first.get("recommendation") or {}
            # `current_market.lowest_fare`, which is what the response actually
            # carries — there is no top-level `current_price` key. `safe_float`
            # renders a NaN fare as None, which the isinstance test below rejects.
            fare = (first.get("current_market") or {}).get("lowest_fare")
            predicted = first.get("predicted_price")
            if isinstance(fare, (int, float)) and isinstance(predicted, (int, float)):
                rec_val = recommendation_validation_service.validate_recommendation(
                    recommendation=recommendation,
                    current_lowest_fare=float(fare),
                    predicted_price=float(predicted),
                    confidence=first.get("confidence"),
                )
            else:
                # The decision is still checked for membership, but the
                # contradiction rules are all thresholds on the delta between the
                # two figures, and inventing either is what §5 existed to stop.
                rec_val = self._unrun(
                    prediction_reasons
                    + [
                        f"the prediction carries current_market.lowest_fare={fare!r} "
                        f"and predicted_price={predicted!r}; the contradiction rules "
                        f"need both as numbers"
                    ]
                )
        else:
            pred_val = self._unrun(prediction_reasons)
            rec_val = self._unrun(prediction_reasons)

        # 5b. Route diversity — one number served for every route was a finding of
        # the audit, and this check existed with no caller.
        diversity = prediction_validation_service.validate_route_diversity(predictions)

        # Determine overall status
        failed_checks = []
        warning_checks = []

        # The audit now reports which bounds it breached, so the rollup quotes
        # them instead of guessing. This line used to append the fixed string
        # "Historical Data Audit: Partial coverage or duplicate observations"
        # whatever the audit had found — including on the empty-database path,
        # where the audit's own reason is "Database returned no records" and
        # neither coverage nor duplicates is what went wrong.
        if data_audit.get("status") != "PASS":
            detail = ("; ".join(data_audit.get("failed_bounds") or [])
                      or data_audit.get("reason") or "no reason recorded")
            # No observations at all is not a warning about data quality; there is
            # no data to be ready with. Every other breach stays a warning.
            if data_audit.get("total_observations", 0) < 1:
                failed_checks.append(f"Historical Data Audit: {detail}")
            else:
                warning_checks.append(f"Historical Data Audit: {detail}")

        if not feature_val.get("valid"):
            failed_checks.append("Feature Validation: Missing required features or low completeness")

        if not model_readiness.get("is_ready"):
            failed_checks.append(f"Model Readiness: {', '.join(model_readiness.get('reasons', []))}")

        if drift_report.get("drift_detected"):
            warning_checks.append("Drift Detection: Significant feature or prediction drift detected")
        if drift_report.get("overall_drift_status") == "UNMEASURABLE":
            warning_checks.append(
                f"Drift Detection: not measurable — {drift_report.get('reason')}")

        if not pred_val.get("valid"):
            if pred_val.get("status") == "NOT_RUN":
                failed_checks.append(
                    "Prediction Validation: no live prediction to validate — "
                    + "; ".join(prediction_reasons)
                )
            else:
                failed_checks.append(
                    "Prediction Validation: "
                    + "; ".join(pred_val.get("errors") or ["invalid bounds or format"])
                )

        if not rec_val.get("valid"):
            if rec_val.get("status") == "NOT_RUN":
                failed_checks.append(
                    "Recommendation Validation: no live recommendation to validate — "
                    + "; ".join(rec_val.get("reasons") or [])
                )
            else:
                failed_checks.append(
                    "Recommendation Validation: "
                    + "; ".join(rec_val.get("errors") or ["decision logic contradiction"])
                )

        # Tri-state: None means the check could not be measured, which is a warning
        # rather than a pass. `if not diversity["valid"]` would have conflated the
        # two.
        if diversity.get("valid") is False:
            failed_checks.append(
                f"Route Diversity: {diversity.get('unique_price_count')} distinct "
                f"prediction(s) across {diversity.get('total_routes_tested')} route(s)"
            )
        elif diversity.get("valid") is None:
            warning_checks.append(f"Route Diversity: not measured — {diversity.get('reason')}")

        if len(failed_checks) > 0:
            overall_status = "FAIL"
        elif len(warning_checks) > 0:
            overall_status = "WARNING"
        else:
            overall_status = "PASS"

        master_report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_status": overall_status,
            "failed_checks": failed_checks,
            "warning_checks": warning_checks,
            "historical_data_audit": data_audit,
            "feature_validation": feature_val,
            "model_readiness": model_readiness,
            "drift_detection": drift_report,
            "prediction_validation": pred_val,
            "recommendation_validation": rec_val,
            "route_diversity": diversity,
            "prediction_sample": {
                "routes_requested": len(predictions) + len(prediction_reasons),
                "predictions_obtained": len(predictions),
                "reasons": prediction_reasons,
            },
        }

        write_report(master_report, _dest("production_readiness_report.json"))
        logger.info(
            "[ProductionReadiness] Report status %s; written to %s",
            overall_status,
            master_report.get("report_written_to")
            or master_report.get("report_write_error"))

        return master_report


production_readiness_service = ProductionReadinessService()
