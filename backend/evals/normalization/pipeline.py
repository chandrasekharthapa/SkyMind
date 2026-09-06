"""Shared Normalization Pipeline for SkyMind Evaluation Platform.

Order of Execution:
Airport -> City -> Date -> Entity -> Comparison

Every evaluator consumes normalized entities to prevent duplicated normalization logic.
"""

from typing import Dict, Any, Tuple
from backend.evals.normalization.airport import normalize_airport
from backend.evals.normalization.city import normalize_city
from backend.evals.normalization.dates import normalize_date
from backend.evals.normalization.entities import normalize_entities


class SharedNormalizationPipeline:
    """Shared pipeline normalizing expected vs actual entity inputs prior to scoring."""

    def normalize(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Runs full normalization chain across input fields."""
        if not data:
            return {}
        return normalize_entities(data)

    def compare_entities(self, expected: Dict[str, Any], actual: Dict[str, Any]) -> Tuple[bool, float, Dict[str, Any]]:
        """Compares expected vs actual entity dicts after running normalization."""
        norm_expected = self.normalize(expected)
        norm_actual = self.normalize(actual)

        if not norm_expected and not norm_actual:
            return True, 1.0, {"matched": [], "missing": []}

        if not norm_expected or not norm_actual:
            return False, 0.0, {"matched": [], "missing": list(norm_expected.keys())}

        matched = []
        missing = []

        for key, exp_val in norm_expected.items():
            act_val = norm_actual.get(key)
            if act_val and str(exp_val).upper() == str(act_val).upper():
                matched.append(key)
            else:
                missing.append(key)

        score = len(matched) / float(len(norm_expected)) if norm_expected else 1.0
        passed = len(missing) == 0

        return passed, round(score, 4), {"matched": matched, "missing": missing, "expected": norm_expected, "actual": norm_actual}


normalization_pipeline = SharedNormalizationPipeline()
