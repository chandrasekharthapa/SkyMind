"""Groundedness / faithfulness evaluator: is every entity the planner emitted
attributable to the query it was given?

What this file used to do. With `OPENAI_API_KEY` unset it returned
`status="SKIPPED", passed=True`. With the key set, it read `actual["generated_text"]`
and `actual["tool_payloads"]` — **neither of which the planner runner has ever
produced** — found `generated_text` empty, and returned:

    score=1.0, status="PASS", reason="Executed normally",
    details={"reason": "No response text required for planner test"}

Its other branch, the one reached only if a response text somehow appeared, returned
`score=1.0` with `details={"reason": "Grounded response verified"}` and made no
comparison of any kind. So on every run in which it was not skipped, this evaluator
contributed a perfect 1.0 to `overall_success_rate` for a check it did not perform,
and the string "Grounded response verified" appeared in the report either way. It was
a pass generator wearing the name of the property it was supposed to test.

What it does now. There is no LLM judge here and no API key gate: the property is
checkable offline and deterministically, which makes it checkable in CI, which is
where it needs to run. For each test case the planner's emitted entities are
adjudicated against the query text:

  * an airport/city value is grounded if any alias that normalizes to it appears in
    the query — `origin="DEL"` is grounded in "cheapest flight from Delhi to Bombay",
    and is not grounded in "flights to Bombay";
  * an airline value is grounded if the query names that carrier under any spelling.
    `airline_code="UK"` is grounded in "What about Vistara for the same route?",
    which a literal text search would have called a violation — the code and the
    name are the same entity and only an alias table knows it;
  * a date value is grounded if the query contains a date-bearing token at all (a
    digit, a month name, or a relative-date word). A planner that resolves
    `departure_date` out of a query with no temporal reference invented it;
  * any other value is grounded if it, or its digits, appear in the query.

The evidence is the query *and any conversation context the case supplied*. A
follow-up turn — "what about Vistara for the same route?" — carries its route in
the context, not in the query, so adjudicating against the query alone would
report a planner that correctly resolved the earlier route as having invented it.

A key this file cannot adjudicate is **not** counted as grounded and **not** counted
as a violation — it is recorded in `unadjudicated` and excluded from the denominator,
because scoring a value against a rule that does not apply to it would make the
evaluator fail for the wrong reason. If nothing in the batch is adjudicable the
result is SKIPPED with that as the reason, which is a statement, rather than 1.0.

`fallback_used` no longer skips. The rule-based planner is the one more likely to
mis-attribute an entity, so exempting it from the faithfulness check exempted the
case that needed it.

The module moved from `evaluators/llm/` to `evaluators/deterministic/` because that
is what it is. `evaluators/llm/` is now empty, which is the accurate statement of the
suite's composition: it has no LLM-judge evaluator, and the one file that claimed to
be one never made a model call.
"""

import re
import logging
from typing import Any, Dict, List, Optional, Tuple

from backend.evals.evaluators.base import BaseEvaluator
from backend.evals.normalization.airline import airline_codes_mentioned, normalize_airline
from backend.evals.normalization.airport import CITY_OR_ALIAS_TO_IATA, normalize_airport
from backend.evals.registry import EvaluatorResult, register_evaluator

logger = logging.getLogger(__name__)

# Entity keys whose values are airports or cities.
PLACE_KEYS = ("origin", "destination", "from", "to", "origin_code", "destination_code")

# Entity keys whose values are airlines.
AIRLINE_KEYS = ("airline", "airline_code", "carrier", "carrier_code", "preferred_airline")

# Entity keys whose values are dates.
DATE_KEYS = ("departure_date", "return_date", "date", "travel_date")

# Words that put a date in a query without writing one.
RELATIVE_DATE_WORDS = (
    "today", "tonight", "tomorrow", "yesterday", "next", "this", "coming",
    "weekend", "week", "month", "asap", "soon", "now", "immediately", "last",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
)

# Reverse index: IATA code -> every alias that normalizes to it.
_IATA_TO_ALIASES: Dict[str, List[str]] = {}
for _alias, _code in CITY_OR_ALIAS_TO_IATA.items():
    _IATA_TO_ALIASES.setdefault(_code, []).append(_alias)


def _contains_phrase(haystack: str, needle: str) -> bool:
    """Whole-word/phrase containment, so "GOA" does not match "GOAL"."""
    if not needle:
        return False
    return re.search(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", haystack) is not None


def _place_is_grounded(value: str, query_upper: str) -> bool:
    """True if any alias for this airport code appears in the query."""
    code = normalize_airport(value) or str(value).strip().upper()
    for alias in _IATA_TO_ALIASES.get(code, []):
        if _contains_phrase(query_upper, alias):
            return True
    # The raw value as written, for a place the alias table does not carry.
    return _contains_phrase(query_upper, str(value).strip().upper())


def _airline_is_grounded(value: str, query_upper: str) -> bool:
    """True if the query names this carrier under any spelling.

    `airline_code="UK"` and the word "Vistara" are the same entity; the literal
    text search this used to fall through to called that a violation, which was
    the evaluator's one measured false positive against the golden set.
    """
    code = normalize_airline(value)
    if code and code in airline_codes_mentioned(query_upper):
        return True
    return _contains_phrase(query_upper, str(value).strip().upper())


def _query_carries_a_date(query_upper: str) -> bool:
    """True if the query contains anything a date could have been resolved from."""
    if any(ch.isdigit() for ch in query_upper):
        return True
    return any(_contains_phrase(query_upper, word.upper()) for word in RELATIVE_DATE_WORDS)


def _adjudicate(key: str, value: Any, query_upper: str) -> Tuple[Optional[bool], str]:
    """(grounded, note) for one entity, or (None, reason) if not adjudicable."""
    if value is None or value == "" or value == [] or value == {}:
        return None, f"{key}: empty value, nothing to attribute"

    if isinstance(value, (list, tuple, set)):
        verdicts = [_adjudicate(key, v, query_upper) for v in value]
        decided = [g for g, _ in verdicts if g is not None]
        if not decided:
            return None, f"{key}: no element adjudicable"
        return all(decided), f"{key}: {sum(decided)}/{len(decided)} element(s) grounded"

    if isinstance(value, dict):
        return None, f"{key}: nested dict, no rule for it"

    if isinstance(value, bool):
        return None, f"{key}: boolean flag, not an extracted value"

    key_lower = str(key).lower()

    if key_lower in PLACE_KEYS:
        ok = _place_is_grounded(str(value), query_upper)
        return ok, f"{key}={value}: {'alias found in query' if ok else 'no alias in query'}"

    if key_lower in AIRLINE_KEYS:
        ok = _airline_is_grounded(str(value), query_upper)
        return ok, f"{key}={value}: {'carrier named in query' if ok else 'carrier not named in query'}"

    if key_lower in DATE_KEYS:
        ok = _query_carries_a_date(query_upper)
        return ok, f"{key}={value}: {'query carries a date' if ok else 'query has no date reference'}"

    if isinstance(value, (int, float)):
        ok = _contains_phrase(query_upper, str(value)) or _contains_phrase(
            query_upper, str(int(value)) if float(value).is_integer() else str(value))
        return ok, f"{key}={value}: {'digits found in query' if ok else 'digits not in query'}"

    text = str(value).strip().upper()
    if len(text) < 2:
        return None, f"{key}={value}: too short to attribute"
    ok = _contains_phrase(query_upper, text)
    return ok, f"{key}={value}: {'text found in query' if ok else 'text not in query'}"


def _figures_in(text: str) -> List[str]:
    """Numeric figures a response asserts, e.g. prices and flight numbers."""
    return re.findall(r"\d[\d,]*(?:\.\d+)?", text or "")


@register_evaluator("groundedness")
class GroundednessEvaluator(BaseEvaluator):
    """Every value the planner emitted must be attributable to the query."""

    name = "groundedness"
    # Not "llm": this is a deterministic text-attribution check with no model call,
    # and labelling it llm was how it came to be gated behind an API key it never used.
    category = "deterministic"
    feedback_key = "groundedness_score"

    def evaluate_item(self, expected: Dict[str, Any], actual: Dict[str, Any]) -> EvaluatorResult:
        query = str(actual.get("query") or "")
        entities = actual.get("entities") or {}

        if not query:
            return self._skip("No query recorded on the run; groundedness needs the "
                              "input the plan was produced from")

        # Conversation context is evidence too. A follow-up turn keeps its route in
        # the context rather than restating it, so a planner that resolved the
        # earlier route correctly would look like it invented one if the context
        # were excluded.
        context = actual.get("context")
        evidence_source = query if not context else f"{query} {context}"
        query_upper = evidence_source.upper()

        grounded: List[str] = []
        violations: List[str] = []
        unadjudicated: List[str] = []

        for key, value in (entities.items() if isinstance(entities, dict) else []):
            verdict, note = _adjudicate(key, value, query_upper)
            if verdict is None:
                unadjudicated.append(note)
            elif verdict:
                grounded.append(note)
            else:
                violations.append(note)

        # A response text, if the run produced one: every figure it states must
        # appear in the evidence the tools returned. This does not fire for planner
        # runs, which emit no prose; it is here for the chat path, which does.
        response_text = actual.get("generated_text") or ""
        evidence = actual.get("tool_payloads")
        if response_text and evidence is not None:
            evidence_text = str(evidence)
            for figure in _figures_in(response_text):
                bare = figure.replace(",", "")
                if bare in evidence_text.replace(",", ""):
                    grounded.append(f"response figure {figure}: present in tool payloads")
                else:
                    violations.append(f"response figure {figure}: absent from tool payloads")
        elif response_text and evidence is None:
            unadjudicated.append("response text present but no tool_payloads to check it against")

        adjudicated = len(grounded) + len(violations)
        if adjudicated == 0:
            return self._skip(
                "Nothing adjudicable: the plan emitted no entity this check has a "
                "rule for" + (f" ({unadjudicated[0]})" if unadjudicated else ""),
                details={"unadjudicated": unadjudicated, "query": query})

        score = len(grounded) / float(adjudicated)
        passed = not violations

        return EvaluatorResult(
            evaluator_name=self.name,
            category=self.category,
            score=round(score, 4),
            status="PASS" if passed else "FAIL",
            passed=passed,
            reason=("All emitted values attributable to the query"
                    if passed else
                    f"{len(violations)} ungrounded value(s): {'; '.join(violations[:3])}"),
            details={
                "query": query,
                "adjudicated": adjudicated,
                "grounded": grounded,
                "violations": violations,
                "unadjudicated": unadjudicated,
            },
            feedback_key=self.feedback_key,
        )

    def _skip(self, reason: str, details: Optional[Dict[str, Any]] = None) -> EvaluatorResult:
        """A skip says why and does not claim to have passed."""
        return EvaluatorResult(
            evaluator_name=self.name,
            category=self.category,
            score=None,
            status="SKIPPED",
            passed=False,
            reason=reason,
            details=details or {},
            feedback_key=self.feedback_key,
        )
