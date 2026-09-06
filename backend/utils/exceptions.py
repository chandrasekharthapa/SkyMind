"""SkyMind Domain Exceptions.

Standardized domain exception types.
"""

class PredictionUnavailable(Exception):
    """Exception raised when prediction service cannot run due to missing inputs or failed data provider queries."""
    pass


class InsufficientHistory(PredictionUnavailable):
    """Raised when there is not enough recorded price history to forecast.

    A subclass of `PredictionUnavailable` so every existing handler — which
    maps that to HTTP 503 — keeps working unchanged, while the message can say
    which horizon lacked history and how many observations it had.

    This exists because the forecast path used to have no way to say "I don't
    know". When the model's dominant features were unavailable at serve time it
    emitted a near-constant, and `price_model.forecast()` detected two of those
    constants by value and substituted `lowest_fare × a hardcoded multiplier`.
    Refusing to answer is the behaviour that replaced it.
    """

    def __init__(self, message: str, horizon: int | None = None,
                 observations: int | None = None):
        super().__init__(message)
        self.horizon = horizon
        self.observations = observations


class HorizonUnavailable(PredictionUnavailable):
    """Raised when no model exists for the forecast horizon that was requested.

    Also a subclass of `PredictionUnavailable`, so the existing 503 handlers
    apply. `predict()` used to answer anyway: if `self.models` had no entry for
    the requested horizon it fell back to `self.model or
    list(self.models.values())[0]`, so a 3d model answered a 30d question and
    the result was labelled 30d everywhere downstream. The fare three days out
    and the fare thirty days out are different quantities — serving one under
    the other's name is the defect, not a degraded mode.
    """


class IntervalUnavailable(PredictionUnavailable):
    """Raised when a forecast point has no measured basis for its interval.

    Another `PredictionUnavailable` subclass, so the existing 503 handlers apply
    unchanged.

    The forecast used to publish `band = max(120.0, price * 0.06)` as its
    confidence interval: ±6% of whatever the model returned, floored at ±₹120.
    Neither figure came from anything the model measured. It was the same width
    for a horizon the model predicts well and one it predicts badly, the same
    width whether the residuals were symmetric or skewed, and it never widened
    when the model got worse — because nothing about the model was an input to
    it. An interval whose width is a constant is a decoration on the point
    estimate, not a statement about uncertainty.

    The width now comes from the residuals the model recorded on its own test
    fold. When an artifact carries no such record, or too few residuals for the
    quantiles to mean anything, this is raised instead: a published interval
    should be a measurement or absent.
    """

    def __init__(self, message: str, horizon: int | None = None,
                 residual_sample_size: int | None = None):
        super().__init__(message)
        self.horizon = horizon
        self.residual_sample_size = residual_sample_size

