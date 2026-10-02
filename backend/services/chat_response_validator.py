"""Chat Response Validator.

Asserts that LLM generated responses contain only valid, verified data,
preventing hallucinations of baggage, terminals, discounts, fake prices, or fake flights.
"""

import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class ChatResponseValidator:
    _CURRENCY_AMOUNT = re.compile(
        r"(?:₹|\bRs\.?|\bINR)\s*(\d[\d,]*(?:\.\d+)?)|(\d[\d,]*(?:\.\d+)?)\s*(?:\bINR\b|\brupees?\b)",
        re.IGNORECASE,
    )

    # Two-character IATA airline code (letters, or a letter and a digit such as
    # 6E, 9W, I5) followed by a 1-4 digit flight number. Case-sensitive: codes
    # are written in capitals, and "in 2134" must not match.
    _FLIGHT_NUMBER = re.compile(r"\b(?:[A-Z]{2}|[A-Z]\d|\d[A-Z])[\s-]?\d{1,4}\b")

    @staticmethod
    def extract_prices(text: str) -> List[float]:
        """Extract fare-like amounts from the output text.

        An amount written with a rupee marker (₹, Rs, INR, "rupees") is always a
        price. A bare number is treated as one only if it is >= 500 and not a
        calendar year (1900–2099), so durations, stops, seat counts and dates are
        skipped.

        The year exclusion used to apply to every number, marked or not, so an
        invented ₹1,999 or ₹2,000 fare — ordinary sale-fare figures — could never
        fail verification.
        """
        prices: List[float] = []
        spans = []
        for m in ChatResponseValidator._CURRENCY_AMOUNT.finditer(text):
            raw = (m.group(1) or m.group(2) or "").replace(",", "")
            try:
                prices.append(float(raw))
                spans.append(m.span())
            except ValueError:
                pass

        # Bare numbers, outside the currency-marked spans already taken.
        masked = list(text)
        for a, b in spans:
            masked[a:b] = " " * (b - a)
        # Flight numbers ("6E 2134", "AI-2671", "QP1407") are not fares. Their
        # digits used to be read as unverified prices, so any data answer that
        # named a flight was rejected and replaced by the bare fallback summary.
        masked_text = ChatResponseValidator._FLIGHT_NUMBER.sub(
            lambda m: " " * len(m.group(0)), "".join(masked))
        cleaned = re.sub(r"(?<=\d),(?=\d)", "", masked_text)
        for match in re.finditer(r"\b(\d+(?:\.\d+)?)\b", cleaned):
            try:
                val = float(match.group(1))
            except ValueError:
                continue
            if 1900 <= int(val) <= 2099 or val < 500:
                continue
            prices.append(val)
        return prices

    @staticmethod
    def _num(value: Any) -> Optional[float]:
        """A price as a float, or None. Accepts {"total": x} price objects too."""
        if isinstance(value, dict):
            value = value.get("total")
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def collect_verified_prices(tool_results: List[Dict[str, Any]]) -> set:
        """Every fare figure the tools actually returned, rounded to the rupee.

        This used to read only `result["flights"]`, `predicted_price` and
        `data`. recommend_flights returns its options under cheapest / fastest /
        best_value, so a turn that called only that tool produced an EMPTY set —
        and an empty set disabled the check below entirely ("if not matched and
        valid_prices"), letting any invented fare through. It also called
        float() on whatever `price` held and indexed forecast days with [],
        either of which raised on an unexpected shape and turned the whole chat
        turn into "Something went wrong".
        """
        valid: set = set()

        def add(v: Any) -> None:
            n = ChatResponseValidator._num(v)
            if n is not None:
                valid.add(round(n))

        def add_flight(f: Any) -> None:
            if isinstance(f, dict):
                add(f.get("price"))

        for result in tool_results:
            if not isinstance(result, dict):
                continue
            for f in result.get("flights") or []:
                add_flight(f)
            for key in ("cheapest", "fastest", "best_value"):
                add_flight(result.get(key))
            if "predicted_price" in result:
                add(result.get("predicted_price"))
            for day in result.get("forecast") or []:
                if isinstance(day, dict):
                    for k in ("price", "lower", "upper"):
                        add(day.get(k))
            data = result.get("data")
            if isinstance(data, list):
                for r in data:
                    if isinstance(r, dict):
                        add(r.get("price"))
        return valid

    # Words for details SkyMind's tools never return. Mentioning one is a sign the
    # model is describing something it was not given — unless the sentence says
    # the detail is NOT available, which is the honest answer to "is baggage
    # included?" and used to be rejected just the same.
    HALLUCINATION_TRIGGERS = ("baggage", "luggage", "discount", "promo", "terminal", "gate")
    _NEGATION = re.compile(
        r"\b(?:not|no|don't|doesn't|isn't|aren't|can't|cannot|won't|unavailable|"
        r"unable|without|n't|never|don’t|doesn’t|isn’t|can’t)\b",
        re.IGNORECASE,
    )

    # A sentence that sends the user to check a detail is not asserting it:
    # "Check the airline's baggage policy before you fly" is advice. That tip,
    # which the model adds to most flight answers, used to get the whole answer
    # thrown out and replaced by the bare fallback table.
    _ADVISORY = re.compile(
        r"\b(?:check|confirm|verify|review|policy|policies|varies|vary|may|might|"
        r"depend(?:s|ing)?|subject to|airline'?s|airline’s|website|app|before (?:you )?(?:fly|book))\b",
        re.IGNORECASE,
    )

    @classmethod
    def _asserts_unverified_detail(cls, text: str) -> Optional[str]:
        for sentence in re.split(r"(?<=[.!?\n])\s+", text):
            lowered = sentence.lower()
            for word in cls.HALLUCINATION_TRIGGERS:
                if (re.search(r"\b" + word, lowered)
                        and not cls._NEGATION.search(sentence)
                        and not cls._ADVISORY.search(sentence)):
                    return word
        return None

    @staticmethod
    def validate_llm_response(text: str, tool_results: List[Dict[str, Any]]) -> bool:
        """Verifies text content matches values inside tool_results.

        Returns True if valid, False if it contains hallucinations.

        Two kinds of answer are checked differently:

        * A data answer (tools ran): every fare-like number — rupee-marked, or a
          bare number >= 500 that is not a year — must match a tool figure, and
          details the tools never return (baggage, terminal, gate, discount) must
          not be asserted, since the model would be attributing them to the
          specific flights it was shown.
        * A knowledge answer (no tools): general aviation questions ("what is a
          layover?", "how much cabin baggage can I carry?") are answered from the
          model's knowledge, so the detail words are the subject, not a sign of
          invention, and bare numbers are ordinary facts ("35,000 feet", "180
          seats"). Only rupee-marked amounts are checked — and with no tool data
          there is nothing to match them against, so any quoted price fails.
          Previously both kinds were checked the same way, which threw out
          correct answers to baggage or altitude questions.
        """
        valid_prices = ChatResponseValidator.collect_verified_prices(tool_results)
        knowledge_answer = not [r for r in tool_results if isinstance(r, dict)]

        if knowledge_answer:
            amounts = [
                float((m.group(1) or m.group(2) or "0").replace(",", ""))
                for m in ChatResponseValidator._CURRENCY_AMOUNT.finditer(text)
            ]
        else:
            amounts = ChatResponseValidator.extract_prices(text)

        for p in amounts:
            rounded_p = round(p)
            # Allow minor rounding differences of +/- 5 units
            if not any(abs(rounded_p - vp) <= 5 for vp in valid_prices):
                logger.warning(
                    f"Validation rejection: price {p} (rounded {rounded_p}) not in verified prices: "
                    f"{sorted(valid_prices)[:20]}"
                )
                return False

        if not knowledge_answer:
            word = ChatResponseValidator._asserts_unverified_detail(text)
            if word:
                logger.warning(f"Validation rejection: asserts unverified detail '{word}'")
                return False

        return True
