"""SkyMind Recommendation Engine.

Analyzes predicted forecasts against observed live market prices to determine
deterministic booking recommendations (BOOK_NOW, WAIT, or MONITOR).
Also supports sorting, deduplicating, and highlighting flight search options.
"""

import time
import math
import logging
import re
from typing import Dict, Any, List, Optional, Tuple

from backend.services.recommendation_policy import RecommendationPolicy, recommendation_policy as default_policy
from backend.services.event_publisher import EventPublisher, AuditLogEventPublisher
from backend.services.flight_normalizer import NormalizedFlight
from backend.services.confidence_policy import published_confidence

logger = logging.getLogger(__name__)

class RecommendationEngine:
    def __init__(
        self,
        recommendation_policy: Optional[RecommendationPolicy] = None,
        event_publisher: Optional[EventPublisher] = None
    ):
        self.policy = recommendation_policy or default_policy
        self.event_publisher = event_publisher or AuditLogEventPublisher()

    @staticmethod
    def compute_optimal_booking_window(
        formatted_forecast: List[Dict[str, Any]],
        current_lowest: Optional[float]
    ) -> Dict[str, Any]:
        """Finds the earliest forecast date with the minimum predicted price across all available forecast horizons.

        Tie-breaking rule: If multiple horizons have identical minimum prices, select the earliest prediction_horizon (e.g. Day 0 over Day 1 over Day 3).
        """
        forecast_points = list(formatted_forecast) if formatted_forecast else []
        if current_lowest is not None and not math.isnan(current_lowest) and current_lowest > 0:
            has_day0 = any(
                (f.get("day") if isinstance(f, dict) else getattr(f, "day", None)) == 0
                for f in forecast_points
            )
            if not has_day0:
                today_str = forecast_points[0].get("date") if (forecast_points and isinstance(forecast_points[0], dict)) else "Today"
                forecast_points.insert(0, {"day": 0, "date": today_str, "price": float(current_lowest)})

        if not forecast_points:
            curr_price = float(current_lowest) if (current_lowest is not None and not math.isnan(current_lowest) and current_lowest > 0) else 0.0
            return {
                "booking_date": None,
                "prediction_horizon": 0,
                "expected_price": round(curr_price),
                "estimated_savings": 0,
                "percentage_savings": 0.0,
                "recommendation": "BUY NOW"
            }

        # Sort/min by (price, horizon_day) tuple to guarantee earliest horizon on price ties
        best_point = min(
            forecast_points,
            key=lambda x: (
                float(x.get("price", 0) if isinstance(x, dict) else getattr(x, "price", 0)),
                int(x.get("day", 0) if isinstance(x, dict) else getattr(x, "day", 0))
            )
        )

        best_price = float(best_point.get("price") if isinstance(best_point, dict) else getattr(best_point, "price"))
        best_day = int(best_point.get("day") if isinstance(best_point, dict) else getattr(best_point, "day"))
        best_date = str(best_point.get("date") if isinstance(best_point, dict) else getattr(best_point, "date"))

        curr_price = float(current_lowest) if (current_lowest is not None and not math.isnan(current_lowest) and current_lowest > 0) else best_price
        
        estimated_savings = max(0.0, curr_price - best_price)
        percentage_savings = (estimated_savings / curr_price * 100.0) if curr_price > 0 else 0.0

        rec_str = "BUY NOW" if best_day == 0 else "WAIT"

        return {
            "booking_date": best_date,
            "prediction_horizon": best_day,
            "expected_price": round(best_price),
            "estimated_savings": round(estimated_savings),
            "percentage_savings": round(percentage_savings, 1),
            "recommendation": rec_str
        }

    def generate_recommendation(
        self,
        current_lowest: Optional[float],
        formatted_forecast: List[Dict[str, Any]],
        prediction_horizon: int,
        predicted_price: float,
        origin: str,
        destination: str,
        snapshot_quality: Optional[float] = None,
        model_accuracy: Optional[float] = None,
        is_live_market: bool = False
    ) -> Dict[str, Any]:
        """Compares current observed lowest fare against future forecast fare to issue booking advice.

        `snapshot_quality` and `model_accuracy` defaulted to 1.0 and 95.0. A caller
        that passed neither therefore published 95.0 as its confidence, which is
        what every caller in this repository did whenever the metric lookup in
        `prediction_service` missed. They now default to None, which publishes a
        null confidence: no measurement, no number.

        The degraded branch below used to compute `model_accuracy * 0.85` while the
        live branch computed `model_accuracy * max(0.5, snapshot_quality)`, so a
        request with no live fare at all scored higher than a live one with poor
        snapshot quality. Both branches now go through
        `confidence_policy.published_confidence`, which holds the no-live
        multiplier at or below the live floor.

        `is_live_market` is separate from whether `current_lowest` exists. A fare
        can be present and still come from recorded history rather than a live
        search, and that case must not be scored as though the market were
        observed. The branch below keys the decision on having a fare; the
        confidence keys on where the fare came from.
        """
        rec_start = time.time()

        # Compute optimal booking window across all available forecast horizons
        optimal_booking = self.compute_optimal_booking_window(formatted_forecast, current_lowest)

        # Historical-only / Degraded mode fallback when live current_lowest fare is unavailable
        if current_lowest is None or math.isnan(current_lowest) or current_lowest <= 0:
            hist_confidence = published_confidence(
                model_accuracy=model_accuracy,
                snapshot_quality=snapshot_quality,
                is_live_market=False
            )
            return {
                "decision": "MONITOR",
                "reasons": [
                    "Prediction generated using historical booking curves because live market data is currently unavailable."
                ],
                "confidence": hist_confidence,
                "optimal_booking": optimal_booking
            }

        best_day = optimal_booking["prediction_horizon"]
        best_price = optimal_booking["expected_price"]
        savings = optimal_booking["estimated_savings"]
        pct_savings = optimal_booking["percentage_savings"]

        if best_day == 0:
            rec_decision = "BOOK_NOW"
            rec_reasons = [
                "Today's expected fare matches the lowest predicted fare across all forecast horizons. Waiting is not expected to produce additional savings."
            ]
        else:
            rec_decision = "WAIT"
            if savings > 0:
                rec_reasons = [
                    f"The forecast indicates the lowest expected fare occurs in approximately {best_day} day(s). Waiting is expected to reduce the fare by ₹{savings} ({pct_savings}%)."
                ]
            else:
                rec_reasons = [
                    f"The forecast suggests the optimal booking date occurs in {best_day} day(s)."
                ]

        # Confidence: the model's recorded accuracy discounted by observed market
        # data quality. Both terms must be measured; see confidence_policy.
        adjusted_confidence = published_confidence(
            model_accuracy=model_accuracy,
            snapshot_quality=snapshot_quality,
            is_live_market=is_live_market
        )

        result = {
            "decision": rec_decision,
            "reasons": rec_reasons,
            "confidence": adjusted_confidence,
            "optimal_booking": optimal_booking
        }

        # Publish Event
        self.event_publisher.publish("RecommendationGenerated", {
            "origin": origin,
            "destination": destination,
            "decision": rec_decision,
            "prediction_horizon": best_day,
            "latency_seconds": round(time.time() - rec_start, 4)
        })

        return result

    # ── Legacy Search Sorting and Highlighting ───────────────────────

    # Sentinel returned when a flight's duration is unknown or unparseable, chosen
    # so such a flight sorts last and can never be reported as the fastest option.
    UNKNOWN_DURATION_MINUTES = 9999

    @staticmethod
    def get_duration_minutes(flight: NormalizedFlight) -> int:
        """Parse an ISO-8601 duration (PT2H15M, PT135M) into minutes.

        Returns UNKNOWN_DURATION_MINUTES when the duration is absent or cannot be
        parsed. The unparseable case previously returned 0: `re.match` on
        `PT(?:(\\d+)H)?(?:(\\d+)M)?` succeeds against any string beginning "PT"
        with both groups None, so a malformed value such as "PT" or "PT--"
        scored 0 minutes and won every "fastest" comparison — the exact opposite
        of the 9999 sentinel the absent case already used.
        """
        duration_str = flight.itineraries[0].duration if flight.itineraries else ""
        if not duration_str:
            return RecommendationEngine.UNKNOWN_DURATION_MINUTES

        match = re.fullmatch(r"\s*PT(?:(\d+)H)?(?:(\d+)M)?\s*", duration_str, re.IGNORECASE)
        if match and (match.group(1) or match.group(2)):
            h = int(match.group(1) or 0)
            m = int(match.group(2) or 0)
            return h * 60 + m

        logger.warning(f"Unparseable duration {duration_str!r}; treated as unknown, not fastest.")
        return RecommendationEngine.UNKNOWN_DURATION_MINUTES

    @staticmethod
    def deduplicate_flights(flights: List[NormalizedFlight]) -> List[NormalizedFlight]:
        """Merge identical flights using canonical FlightNormalizer deduplication."""
        from backend.services.flight_normalizer import FlightNormalizer
        return FlightNormalizer.deduplicate_flights(flights)

    @staticmethod
    def sort_flights(flights: List[NormalizedFlight], criterion: str = "price") -> List[NormalizedFlight]:
        """Sort flights by price, duration, stops, or departure time."""
        c_lower = criterion.lower()
        if c_lower == "duration":
            return sorted(flights, key=lambda x: RecommendationEngine.get_duration_minutes(x))
        elif c_lower == "stops":
            return sorted(flights, key=lambda x: len(x.itineraries[0].segments) - 1 if x.itineraries else 0)
        elif c_lower == "departure_time":
            # `or ""` on the value as well as the guard: departure_time is
            # Optional[str] and is now legitimately None when a provider omits it
            # (it used to be back-filled with a fabricated noon timestamp), and
            # sorted() raises TypeError comparing None against str.
            return sorted(
                flights,
                key=lambda x: (
                    (x.itineraries[0].segments[0].departure_time or "")
                    if (x.itineraries and x.itineraries[0].segments)
                    else ""
                )
            )
        return sorted(flights, key=lambda x: x.price)

    @staticmethod
    def identify_highlights(flights: List[NormalizedFlight]) -> Tuple[Optional[NormalizedFlight], Optional[NormalizedFlight], Optional[NormalizedFlight]]:
        """Identify Cheapest, Fastest, and Best Value flights from the options list."""
        if not flights:
            return None, None, None

        cheapest = min(flights, key=lambda x: x.price)

        # Only flights whose duration is actually known can be compared on speed.
        # `min()` over a list where every duration is unknown returns the first
        # element, which reported an arbitrary flight as the fastest on no evidence.
        timed = [
            f for f in flights
            if RecommendationEngine.get_duration_minutes(f)
            < RecommendationEngine.UNKNOWN_DURATION_MINUTES
        ]
        fastest = min(timed, key=RecommendationEngine.get_duration_minutes) if timed else None
        if not timed:
            logger.warning(
                f"No duration available for any of {len(flights)} option(s); "
                "'fastest' left unset and best-value scored on price and stops only."
            )

        min_price = cheapest.price if cheapest.price > 0 else 1.0
        # With no timed flight, this stays at the sentinel, so every dur_ratio below
        # is exactly 1.0 and the duration term becomes a constant that cancels out of
        # the ranking. When some flights are timed, an unknown duration yields a
        # ratio of 9999/min_dur and loses — unknown data must not win a comparison.
        min_dur = (
            RecommendationEngine.get_duration_minutes(fastest) if fastest
            else RecommendationEngine.UNKNOWN_DURATION_MINUTES
        )
        min_dur = min_dur if min_dur > 0 else 1.0

        best_value = None
        best_score = float("inf")
        
        for f in flights:
            dur = RecommendationEngine.get_duration_minutes(f)
            stops = len(f.itineraries[0].segments) - 1 if (f.itineraries and f.itineraries[0].segments) else 0
            
            price_ratio = f.price / min_price
            dur_ratio = dur / min_dur
            stops_penalty = 1.0 + (stops * 0.5)

            score = (price_ratio * 0.5 + dur_ratio * 0.3) * stops_penalty
            if score < best_score:
                best_score = score
                best_value = f

        return cheapest, fastest, best_value


recommendation_engine = RecommendationEngine()
