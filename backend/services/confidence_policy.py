"""Confidence Policy.

Single definition of every number that reaches a published confidence figure.

Before this module the figure was assembled from defaults. Nine function
signatures carried `model_accuracy: float = 95.0` or an equivalent, and the two
places that tried to read a real metric off the predictor both failed and fell
back to that default: `forecast_engine.run_forecast` tested a string key against
an int-keyed dict, and `prediction_service` wrapped the read in a bare `except`
whose handler restored 95.0. So a confidence of 95.0 was not a measurement that
happened to be high; it was the value the system printed when it had no
measurement at all, and it was indistinguishable from a real one.

Three rules follow, and each is enforced here rather than at the call sites:

1. A confidence figure must trace to a metric a training run recorded.
   `resolve_published_accuracy` returns None when it cannot find one, and callers
   refuse the request instead of substituting a number.

2. Missing information may never raise confidence. The quality multiplier for a
   market with no live data must be no higher than the worst multiplier a live
   market can receive. The old code had it backwards: a live market with quality
   0.0 scored `accuracy * 0.5` while no live market at all scored
   `accuracy * 0.85`, so losing the data source improved the published number by
   70%. `_assert_monotone_in_information` below fails at import if that ordering
   is ever reintroduced.

3. Clamping may bound a value to its own scale and nothing else. The previous
   `max(70.0, min(99.0, model_accuracy))` did more: the floor rewrote any figure
   under 70 as 70, so a model measured at 42 published as 70, and the ceiling
   rewrote 100 as 99 to look plausible.

None of the arithmetic here is calibrated. `accuracy x quality` is a heuristic
discount, not a probability, and the accuracy term is itself `100 - MAPE` rather
than a share of variance explained. What this module guarantees is narrower and
checkable: every input is measured, and no output rises when an input is lost.
"""

import logging
import math
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── Scale bounds ─────────────────────────────────────────────────────────────
# The published field is a percentage. These bound a value to that scale; they
# are not quality thresholds and must never be used to make a figure look better.
ACCURACY_SCALE_MIN = 0.0
ACCURACY_SCALE_MAX = 100.0

# ── Quality multipliers ──────────────────────────────────────────────────────
LIVE_QUALITY_FLOOR = 0.5
LIVE_QUALITY_CEILING = 1.0
NO_LIVE_MARKET_QUALITY = 0.5


def _assert_monotone_in_information() -> None:
    """Fail at import if a missing data source could raise published confidence.

    This is rule 2 as executable code, and it is the reason the rule is a
    guarantee rather than a comment: raising NO_LIVE_MARKET_QUALITY above
    LIVE_QUALITY_FLOOR makes importing this module fail, so the inversion cannot
    be reintroduced by editing a constant.
    """
    if NO_LIVE_MARKET_QUALITY > LIVE_QUALITY_FLOOR:
        raise ValueError(
            "confidence_policy: NO_LIVE_MARKET_QUALITY "
            f"({NO_LIVE_MARKET_QUALITY}) exceeds LIVE_QUALITY_FLOOR "
            f"({LIVE_QUALITY_FLOOR}). That ordering pays a higher confidence for "
            "having no live market than for having one of the worst measurable "
            "quality, which is the inversion this module exists to prevent."
        )


_assert_monotone_in_information()


def _finite(value: Any) -> Optional[float]:
    """Coerce to float, or None if it is not a finite number."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def resolve_published_accuracy(perf: Optional[Dict[str, Any]]) -> Optional[float]:
    """Return the recorded accuracy-equivalent figure on a 0-100 scale, or None.

    None means "no training run recorded a metric for this model". It is not a
    zero and must not be replaced by a default; the caller's job is to refuse.

    Three shapes are accepted because three exist on disk. Artifacts written by
    the current training path record `equivalent_accuracy_100_minus_mape` on a
    0-100 scale and `accuracy` as the same quantity expressed as a 0-1 fraction;
    older pickles record only a subset. Confusing the two is a factor-of-100
    error in a field rendered as a percentage, so each candidate is checked
    against the scale it is declared in rather than inferred from its magnitude.

    The name describes the field this feeds, not what the number measures. It is
    `100 - MAPE`. The quarantined 1d artifact records 98.64 here against an R^2
    of 0.4248: fares cluster tightly within a route, so percentage error stays
    small even where the model explains under half the variance.
    """
    if not isinstance(perf, dict):
        return None

    # Declared on a 0-100 scale.
    candidate = _finite(perf.get("equivalent_accuracy_100_minus_mape"))
    if candidate is not None and ACCURACY_SCALE_MIN <= candidate <= ACCURACY_SCALE_MAX:
        return candidate

    # Declared as a 0-1 fraction of the same quantity.
    candidate = _finite(perf.get("accuracy"))
    if candidate is not None and 0.0 <= candidate <= 1.0:
        return candidate * 100.0

    # Derivable from the error metric itself. `mape` is a percentage, so a model
    # whose mean error exceeds 100% of the fare yields a negative figure; that is
    # a true statement about the model and is floored at zero rather than
    # discarded, because returning None there would make a measurably terrible
    # model indistinguishable from an unmeasured one.
    candidate = _finite(perf.get("mape"))
    if candidate is not None and candidate >= 0.0:
        return max(ACCURACY_SCALE_MIN, ACCURACY_SCALE_MAX - candidate)

    return None


def metrics_for_horizon(predictor: Any, horizon: Optional[int]) -> Dict[str, Any]:
    """Return the recorded metrics dict for one horizon, or {}.

    `PricePredictor.metrics` is keyed by integer horizon after a normal load and
    is a single flat dict after a legacy load. `forecast_engine` read it assuming
    the flat shape unconditionally, which is why `"accuracy" in perf` was always
    False on the normal path. Both shapes are handled here, and a horizon with no
    recorded metrics returns an empty dict rather than another horizon's numbers.
    """
    metrics = getattr(predictor, "metrics", None)
    if not isinstance(metrics, dict):
        return {}

    # Flat / legacy shape: metric names at the top level.
    if any(k in metrics for k in ("mae", "rmse", "r2", "mape", "accuracy")):
        return metrics

    if horizon is None:
        return {}
    entry = metrics.get(horizon)
    return entry if isinstance(entry, dict) else {}


def clamp_to_accuracy_scale(value: Optional[float]) -> Optional[float]:
    """Bound a figure to the 0-100 scale of the field it is published in.

    Values outside the scale indicate a unit error upstream, so this logs rather
    than silently correcting. It does not apply a floor above the scale minimum:
    a model measured at 42 publishes 42.
    """
    candidate = _finite(value)
    if candidate is None:
        return None
    if candidate < ACCURACY_SCALE_MIN or candidate > ACCURACY_SCALE_MAX:
        logger.warning(
            "Accuracy figure %s lies outside the 0-100 scale of the field it is "
            "published in; clamping. This usually means a 0-1 fraction was "
            "multiplied twice or not at all.", candidate
        )
    return max(ACCURACY_SCALE_MIN, min(ACCURACY_SCALE_MAX, candidate))


def quality_multiplier(snapshot_quality: Optional[float], is_live_market: bool) -> float:
    """Return the discount applied to accuracy for observed market-data quality.

    With a live market the observed quality is used, bounded to
    [LIVE_QUALITY_FLOOR, LIVE_QUALITY_CEILING]. Without one, or when quality was
    not measured, the multiplier is NO_LIVE_MARKET_QUALITY, which
    `_assert_monotone_in_information` pins at or below the live floor so that
    losing the data source can never raise the published figure.
    """
    if not is_live_market:
        return NO_LIVE_MARKET_QUALITY
    observed = _finite(snapshot_quality)
    if observed is None:
        return NO_LIVE_MARKET_QUALITY
    return max(LIVE_QUALITY_FLOOR, min(LIVE_QUALITY_CEILING, observed))


def published_confidence(
    model_accuracy: Optional[float],
    snapshot_quality: Optional[float],
    is_live_market: bool
) -> Optional[float]:
    """Combine a measured accuracy with the quality discount, or return None.

    None propagates: no measured accuracy means no publishable confidence.
    """
    accuracy = clamp_to_accuracy_scale(model_accuracy)
    if accuracy is None:
        return None
    return round(accuracy * quality_multiplier(snapshot_quality, is_live_market), 2)

