"""Timeline Builder for Canonical Forecast System."""

import logging
import math
from datetime import datetime, date, timedelta, timezone
from typing import List, Dict, Any, Optional
from backend.domain.canonical_forecast import TimelinePointDomain

logger = logging.getLogger(__name__)


class TimelineBuilder:
    """Builds and validates dynamic forecast timeline points."""

    def build_timeline(
        self,
        formatted_forecast: List[Dict[str, Any]],
        current_fare: Optional[float],
        base_confidence: Optional[float]
    ) -> List[TimelinePointDomain]:
        """Construct aligned TimelinePointDomain objects.

        `base_confidence` is required; it used to default to 95.0. It applies only
        to points that do not carry their own figure. Points produced by the
        forecast path each carry the metric recorded for the horizon that served
        them, so their own value is preferred over the aggregate.

        The day-0 point inserted below is the observed market fare, not a model
        output, so it is published with no confidence at all. Attaching the
        model's confidence to an observation would assert an accuracy claim about
        a number the model never produced.

        No bound on any point is invented here. Three literals used to do that:

          * the inserted day-0 point took `lower = fare * 0.96`, `upper = fare *
            1.04` — a ±4% uncertainty band around a fare that had been *observed*.
            There is no uncertainty about a number that was read off a provider
            response; the bounds are the fare itself.
          * a point with no `lower`/`upper` took `price * 0.95` and `price * 1.05`.
            A missing bound is a broken producer, and manufacturing one at the
            presentation layer publishes an interval no model implied. It raises.
          * `if lower > price: lower = round(price * 0.98, 2)` and the matching
            `upper` clause silently repaired an inverted interval — and
            `ForecastValidationEngine` exists precisely to catch
            `lower <= price <= upper` violations, so the repair ran first and left
            the check nothing to find. The point now passes through unaltered and
            the validator records the violation.
        """
        points: List[TimelinePointDomain] = []
        today_date_str = datetime.now(timezone.utc).date().strftime("%Y-%m-%d")

        # 1. Process raw forecast points from model/forecast engine
        raw_list = list(formatted_forecast) if formatted_forecast else []
        has_day0 = any((p.get("day") if isinstance(p, dict) else getattr(p, "day", None)) == 0 for p in raw_list)

        if not has_day0 and current_fare is not None and not math.isnan(current_fare) and current_fare > 0:
            c_price = float(current_fare)
            raw_list.insert(0, {
                "day": 0,
                "date": today_date_str,
                "price": c_price,
                # An observation, so its interval is degenerate: the fare is both
                # bounds. Was `c_price * 0.96` / `c_price * 1.04`.
                "lower": c_price,
                "upper": c_price,
                "confidence": None,
                "is_observed_fare": True
            })

        for item in raw_list:
            day = int(item.get("day", 0))
            d_str = str(item.get("date") or today_date_str)
            price = float(item.get("price", 0.0))

            lower_raw = item.get("lower")
            upper_raw = item.get("upper")
            if lower_raw is None or upper_raw is None:
                raise ValueError(
                    f"Forecast timeline point for day {day} carries "
                    f"lower={lower_raw!r} and upper={upper_raw!r}. A bound is not "
                    f"substituted here: the interval has to come from the model that "
                    f"produced the point."
                )
            lower = float(lower_raw)
            upper = float(upper_raw)

            if not (lower <= price <= upper):
                # Passed through, not repaired. `ForecastValidationEngine.validate`
                # asserts this invariant over the assembled timeline and records a
                # violation that flips `is_valid`; rewriting the bound here is what
                # used to stop it from ever firing.
                logger.warning(
                    "Forecast timeline point for day %d violates lower <= price <= "
                    "upper (%.2f, %.2f, %.2f). Published unaltered so the invariant "
                    "check can record it.", day, lower, price, upper,
                )

            # A point's own recorded confidence wins. `base_confidence` covers
            # callers that pass raw forecast dicts without one. An observed fare
            # carries None deliberately and must not inherit the aggregate.
            if item.get("is_observed_fare"):
                point_conf: Optional[float] = None
            elif "confidence" in item:
                point_conf = item.get("confidence")
            else:
                point_conf = base_confidence

            pt = TimelinePointDomain(
                horizon_days=day,
                booking_date=d_str,
                predicted_price=round(price, 2),
                lower_bound=round(lower, 2),
                upper_bound=round(upper, 2),
                confidence_score=None if point_conf is None else round(float(point_conf), 2),
                is_optimal=False
            )
            points.append(pt)

        # Sort chronologically by horizon_days
        points.sort(key=lambda x: x.horizon_days)
        return points
