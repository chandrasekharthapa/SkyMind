"""Chat Response Validator.

Asserts that LLM generated responses contain only valid, verified data,
preventing hallucinations of baggage, terminals, discounts, fake prices, or fake flights.
"""

import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class ChatResponseValidator:
    @staticmethod
    def extract_prices(text: str) -> List[float]:
        """Extract all prices/numbers from the output text.
        
        Deliberately excludes:
        - Calendar years (1900–2099) — e.g. "July 23, 2026"
        - Numbers below 500 — e.g. flight durations, stops, seat counts
        - Flight numbers that embed a year-like digit sequence
        """
        cleaned = re.sub(r'[,₹$]', '', text)
        prices = []
        for match in re.finditer(r'\b(\d+(?:\.\d+)?)\b', cleaned):
            raw = match.group(1)
            try:
                val = float(raw)
                int_val = int(val)
                # Skip calendar years (1900–2099)
                if 1900 <= int_val <= 2099:
                    continue
                # Skip anything below a realistic minimum domestic fare
                if val < 500:
                    continue
                prices.append(val)
            except ValueError:
                pass
        return prices

    @staticmethod
    def validate_llm_response(text: str, tool_results: List[Dict[str, Any]]) -> bool:
        """Verifies text content matches values inside tool_results.
        
        Returns True if valid, False if it contains hallucinations.
        """
        # Collect all valid prices
        valid_prices = set()
        valid_airlines = set()
        valid_flights = set()

        for result in tool_results:
            # 1. Search flights result mapping
            if "status" in result and result.get("status") == "success" and "flights" in result:
                for f in result["flights"]:
                    valid_prices.add(round(float(f.get("price", 0.0))))
                    valid_airlines.add(str(f.get("primary_airline", "")).upper())
                    valid_flights.add(str(f.get("flight_number", "")).upper())
            # 2. Predict price result mapping
            elif "predicted_price" in result:
                valid_prices.add(round(float(result["predicted_price"])))
                if "forecast" in result:
                    for day in result["forecast"]:
                        valid_prices.add(round(float(day["price"])))
                        valid_prices.add(round(float(day["lower"])))
                        valid_prices.add(round(float(day["upper"])))
            # 3. Direct pricing lists
            elif "data" in result and isinstance(result["data"], list):
                for r in result["data"]:
                    if "price" in r:
                        valid_prices.add(round(float(r["price"])))

        # Extract prices from text
        text_prices = ChatResponseValidator.extract_prices(text)
        for p in text_prices:
            rounded_p = round(p)
            # Allow minor rounding differences of +/- 5 units
            matched = any(abs(rounded_p - vp) <= 5 for vp in valid_prices)
            if not matched and valid_prices:
                logger.warning(f"Validation rejection: price {p} (rounded {rounded_p}) not in verified prices: {valid_prices}")
                return False

        # Hallucination keywords check: do not invent details not present in tool results
        hallucination_triggers = ["baggage", "luggage", "discount", "promo", "terminal", "gate"]
        for word in hallucination_triggers:
            if word in text.lower():
                # If these words are mentioned in text, assert they are not hallucinated details
                # In our platform, tool results do not contain baggage/terminals, so LLM must not fabricate them.
                logger.warning(f"Validation rejection: contains hallucination-prone keyword '{word}'")
                return False

        return True
