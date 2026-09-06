"""Deterministic Latency Percentile Evaluator (P50, P90, P95, P99)."""

from typing import Dict, Any, List
from backend.evals.evaluators.base import BaseEvaluator
from backend.evals.registry import EvaluatorResult, register_evaluator


@register_evaluator("latency")
class LatencyEvaluator(BaseEvaluator):
    name = "latency"
    category = "deterministic"
    feedback_key = "latency_p95_ms"

    def evaluate_item(self, expected: Dict[str, Any], actual: Dict[str, Any]) -> EvaluatorResult:
        lat_ms = float(actual.get("latency_ms", 0.0))
        target_ms = float(expected.get("max_latency_ms", 3000.0))
        passed = lat_ms <= target_ms
        score = max(0.0, 1.0 - (lat_ms / (target_ms * 2.0)))

        return EvaluatorResult(
            evaluator_name=self.name,
            category=self.category,
            score=round(score, 4),
            passed=passed,
            details={"latency_ms": lat_ms, "target_max_ms": target_ms},
            feedback_key=self.feedback_key
        )

    def evaluate_batch(self, batch_items: List[Dict[str, Any]]) -> EvaluatorResult:
        times = [float(item.get("actual", {}).get("latency_ms", 0.0)) for item in batch_items]
        if not times:
            return EvaluatorResult(evaluator_name=self.name, category=self.category, score=1.0, passed=True, details={}, feedback_key=self.feedback_key)

        times.sort()
        cnt = len(times)
        p50 = times[int(cnt * 0.50)]
        p90 = times[int(cnt * 0.90)]
        p95 = times[min(int(cnt * 0.95), cnt - 1)]
        p99 = times[min(int(cnt * 0.99), cnt - 1)]

        passed = p95 <= 3500.0
        score = 1.0 if passed else 0.5

        return EvaluatorResult(
            evaluator_name=self.name,
            category=self.category,
            score=score,
            passed=passed,
            details={"p50_ms": round(p50, 2), "p90_ms": round(p90, 2), "p95_ms": round(p95, 2), "p99_ms": round(p99, 2)},
            feedback_key=self.feedback_key
        )
