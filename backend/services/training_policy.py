"""Training Policy Configuration.

Defines rules and constraints required for historical aviation price forecast training.
Extended (Milestone 5) to separate benchmarking from promotion decisions:
  - ModelBenchmark measures performance only.
  - TrainingPolicy decides promotion, rejection, and manual review.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class TrainingPolicy:
    """Controls training acceptance and model promotion rules."""

    # ── Dataset quality gates (original) ─────────────────────────────────────
    min_shifted_rows: int = 100
    min_booking_curve_length: int = 3
    min_route_coverage: int = 1
    min_temporal_coverage: float = 0.05   # 5 % coverage ratio
    max_duplicate_rate: float = 0.95
    max_missing_rate: float = 0.50

    # ── Evaluation quality gates (new) ───────────────────────────────────────
    max_mae: Optional[float] = None           # reject model if MAE > this value
    min_r2: Optional[float] = None            # reject model if R² < this value
    min_direction_accuracy: Optional[float] = None  # reject model below this threshold

    # ── Promotion policy (new) ───────────────────────────────────────────────
    promotion_requires_benchmark_improvement: bool = True
    # If True, a model that benchmarks as "unchanged" (within threshold) is still
    # allowed to promote. If False, only "improved" models promote.
    allow_unchanged_promotion: bool = True

    # ── Scheduled retraining ─────────────────────────────────────────────────
    retraining_interval_days: Optional[int] = None   # None = no scheduled retraining

    # ── Legacy attribute aliases (backward-compatibility) ────────────────────
    @property
    def MIN_SHIFTED_ROWS(self) -> int:
        return self.min_shifted_rows

    @property
    def MIN_BOOKING_CURVE_LENGTH(self) -> int:
        return self.min_booking_curve_length

    @property
    def MIN_ROUTE_COVERAGE(self) -> int:
        return self.min_route_coverage

    @property
    def MIN_TEMPORAL_COVERAGE(self) -> float:
        return self.min_temporal_coverage

    @property
    def MAX_DUPLICATE_RATE(self) -> float:
        return self.max_duplicate_rate

    @property
    def MAX_MISSING_RATE(self) -> float:
        return self.max_missing_rate

    # ── Promotion decision API ────────────────────────────────────────────────

    # The verdicts that mean "this model was measured against a baseline and did
    # not come out worse". Promotion is gated on membership of this set rather
    # than on `verdict != "regressed"`, because that test passed for every string
    # it had never heard of — including `"not_compared"`, which is what
    # `ModelBenchmark` returns when no baseline could be computed at all. A model
    # that was never compared to anything must not clear a promotion gate whose
    # whole purpose is the comparison.
    PROMOTABLE_VERDICTS = frozenset({"improved", "unchanged"})

    def should_promote(self, metrics: dict, benchmark_verdict: str) -> bool:
        """Return True if a trained model meets all promotion criteria.

        Args:
            metrics: EvaluationReport.summary_metrics dict (mae, r2 etc.)
            benchmark_verdict: one of `ModelBenchmark`'s verdicts — "improved",
                "unchanged", "regressed" or "not_compared".

        Returns:
            True → safe to promote to production.
            False → hold in 'latest' slot; do not replace production.
        """
        # Anything that is not a verdict from a completed comparison is refused,
        # which covers "regressed", "not_compared", and any future or malformed
        # value. Failing closed here is cheap: the previous model keeps serving.
        if benchmark_verdict not in self.PROMOTABLE_VERDICTS:
            return False

        # If only improvement is allowed
        if self.promotion_requires_benchmark_improvement and not self.allow_unchanged_promotion:
            if benchmark_verdict != "improved":
                return False

        # Metric thresholds
        if self.max_mae is not None:
            if metrics.get("mae", float("inf")) > self.max_mae:
                return False

        if self.min_r2 is not None:
            if metrics.get("r2", -float("inf")) < self.min_r2:
                return False

        if self.min_direction_accuracy is not None:
            if metrics.get("direction_accuracy", 0.0) < self.min_direction_accuracy:
                return False

        return True

    def validate_for_retraining(
        self,
        data_audit: Optional[dict] = None,
        drift_report: Optional[dict] = None,
        feature_validation: Optional[dict] = None
    ) -> dict:
        """Validate whether the system environment satisfies retraining policy conditions.

        Prevents retraining when:
          - Data audit shows insufficient observations or poor booking curve density
          - Feature completeness is poor (< 80%)
          - Excessive feature drift (drift score > 0.40)
          - Critical validation checks fail
        """
        reasons = []

        if data_audit:
            obs = data_audit.get("total_observations", 0)
            if obs < self.min_shifted_rows:
                reasons.append(f"Insufficient observations ({obs} < {self.min_shifted_rows})")

            missing_rate = data_audit.get("missing_value_percentage", 0.0)
            if missing_rate > (self.max_missing_rate * 100):
                reasons.append(f"Excessive missing values ({missing_rate:.1f}% > {self.max_missing_rate*100:.1f}%)")

            dup_rate = data_audit.get("duplicate_observation_percentage", 0.0)
            if dup_rate > (self.max_duplicate_rate * 100):
                reasons.append(f"Excessive duplicate rate ({dup_rate:.1f}% > {self.max_duplicate_rate*100:.1f}%)")

        if feature_validation:
            valid = feature_validation.get("valid", True)
            if not valid:
                reasons.append("Feature validation checks failed (schema mismatch or missing required features)")

            completeness = feature_validation.get("feature_completeness", 1.0)
            if completeness < 0.80:
                reasons.append(f"Poor feature completeness ({completeness*100:.1f}% < 80.0%)")

        if drift_report:
            drift_score = drift_report.get("feature_drift_score", 0.0)
            if drift_score > 0.40:
                reasons.append(f"Excessive feature drift detected (score {drift_score:.2f} > 0.40)")

        allowed = len(reasons) == 0
        return {
            "allowed": allowed,
            "reasons": reasons,
            "status": "APPROVED" if allowed else "BLOCKED"
        }

    def requires_manual_review(self, metrics: dict, benchmark_verdict: str) -> bool:
        """Return True if the model should be flagged for human review.

        Two cases. A model that benchmarks as 'unchanged' while
        `promotion_requires_benchmark_improvement=True` — the original case, a
        judgement call about whether parity is good enough. And a model whose
        benchmark produced no comparison at all, which is not a judgement call
        about the model but a gap in the evidence: something a person has to
        look at, even though `should_promote` already refuses it.
        """
        if benchmark_verdict == "not_compared":
            return True
        if benchmark_verdict == "unchanged" and self.promotion_requires_benchmark_improvement:
            return True
        return False


# Default Policy singleton instance (preserves existing call-sites)
training_policy = TrainingPolicy()
