"""Base Evaluator Interface for SkyMind Evaluation Platform.

Two things `evaluate_batch` used to get wrong about its own arithmetic:

  * **The pass ratio was computed over the wrong denominator.**
    `passed_count / len(executed_scores)` counted every non-skipped item that
    reported `passed`, including items that reported `score=None` — those increment
    `passed_count` but never land in `executed_scores`. On a batch where some items
    execute without producing a score, the ratio exceeds 1.0 and the 0.80 bar cannot
    be missed. Both counts are now taken over the same set of executed items.
  * **An evaluator that executed nothing but scored nothing returned SKIPPED.**
    `if not executed_scores` conflated "no item ran" with "items ran and none
    produced a number". The first is a skip; the second is an evaluator that is
    broken, and reporting it as a skip hid it. They are now distinguished, and the
    second returns ERROR.

`passed=True` on a skipped result is also gone. A batch that did not run did not
pass, and `passed` is what a caller reads when it wants to know whether to believe
the suite.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List
from backend.evals.registry import EvaluatorResult

# Fraction of executed items that must pass for the evaluator itself to pass.
PASS_RATIO_THRESHOLD = 0.80


class BaseEvaluator(ABC):
    """Abstract base evaluator class."""

    name: str = "base_evaluator"
    category: str = "deterministic"  # "deterministic" or "llm"
    feedback_key: str = "base_metric"

    def __init__(self, config: Any = None):
        self.config = config

    @abstractmethod
    def evaluate_item(self, expected: Dict[str, Any], actual: Dict[str, Any]) -> EvaluatorResult:
        """Evaluates a single prediction against expected benchmark targets."""
        pass

    def evaluate_batch(self, batch_items: List[Dict[str, Any]]) -> EvaluatorResult:
        """Evaluates a list of prediction items and returns summary result."""
        executed_count = 0
        executed_scores = []
        passed_count = 0
        skipped_count = 0
        details_list = []
        skip_reasons = []

        for item in batch_items:
            res = self.evaluate_item(item.get("expected", {}), item.get("actual", {}))
            if res.status in ("SKIPPED", "INFRASTRUCTURE_UNAVAILABLE"):
                skipped_count += 1
                details_list.append(res.details)
                if res.reason and res.reason not in skip_reasons:
                    skip_reasons.append(res.reason)
                continue

            # One denominator for both counts: an item that ran is counted once,
            # whether or not it produced a number.
            executed_count += 1
            if res.score is not None:
                executed_scores.append(res.score)
            if res.passed:
                passed_count += 1
            details_list.append(res.details)

        if executed_count == 0:
            reason_msg = skip_reasons[0] if skip_reasons else "Evaluator unavailable or unconfigured"
            return EvaluatorResult(
                evaluator_name=self.name,
                category=self.category,
                score=None,
                status="SKIPPED",
                passed=False,
                reason=reason_msg,
                details={"total": len(batch_items), "skipped": skipped_count, "executed": 0,
                         "skip_reasons": skip_reasons},
                feedback_key=self.feedback_key
            )

        if not executed_scores:
            # Items ran and not one returned a score. That is not a skip — it is an
            # evaluator that is not measuring, and it must not read as a clean run.
            return EvaluatorResult(
                evaluator_name=self.name,
                category=self.category,
                score=None,
                status="ERROR",
                passed=False,
                reason=(f"{executed_count} item(s) executed and none returned a score; "
                        f"evaluator produced no measurement"),
                details={"total": len(batch_items), "executed": executed_count,
                         "scored": 0, "skipped": skipped_count},
                feedback_key=self.feedback_key
            )

        avg_score = sum(executed_scores) / float(len(executed_scores))
        pass_ratio = passed_count / float(executed_count)
        overall_passed = pass_ratio >= PASS_RATIO_THRESHOLD

        return EvaluatorResult(
            evaluator_name=self.name,
            category=self.category,
            score=round(avg_score, 4),
            status="PASS" if overall_passed else "FAIL",
            passed=overall_passed,
            reason=(f"{passed_count}/{executed_count} item(s) passed "
                    f"(ratio {round(pass_ratio, 4)}, threshold {PASS_RATIO_THRESHOLD})"),
            details={"total": len(batch_items), "executed": executed_count,
                     "scored": len(executed_scores), "passed": passed_count,
                     "skipped": skipped_count, "avg_score": round(avg_score, 4),
                     "pass_ratio": round(pass_ratio, 4),
                     "pass_ratio_threshold": PASS_RATIO_THRESHOLD},
            feedback_key=self.feedback_key
        )
