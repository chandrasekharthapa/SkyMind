"""A dependency-free estimator for the fold-boundary tests.

`TimeSeriesCrossValidator` asks a model for exactly three things: `get_params`, so
`sklearn.base.clone` can rebuild it per fold, `fit`, and `predict`. Everything the
cross-validation and splitter tests assert is about *which rows landed in which
fold and when they were observed* — never about the quality of the fit — so an
`XGBRegressor` there buys nothing and costs the ability to run the tests anywhere
gradient boosting is not installed. It also makes those tests slow enough that the
tempting thing to assert is `n_folds >= 1` rather than the exact fold count.

This fits a straight line to the first feature by least squares. It is
deterministic, has no dependency beyond numpy, and returns a genuinely varying
prediction, so metric aggregation over folds exercises real numbers.

Not a test module: it defines no `test_*` function and is imported, not collected.
"""

from __future__ import annotations

import numpy as np


class LinearOnFirstFeature:
    """Least-squares fit of the target on one feature. Deterministic, no deps."""

    def __init__(self, fallback: float = 0.0):
        self.fallback = fallback
        # The validator stamps its seed onto the model it clones; carrying the
        # attribute keeps that assignment from being the thing under test.
        self.random_state = 0

    def get_params(self, deep: bool = False):
        return {"fallback": self.fallback}

    def fit(self, X, y):
        x = np.asarray(X, dtype=float)[:, 0]
        y = np.asarray(y, dtype=float)
        # A degenerate column (one row, or every value identical) has no slope;
        # predicting the training mean is the honest answer and keeps `polyfit`
        # from emitting a rank warning on every fold.
        if len(x) < 2 or np.ptp(x) == 0.0:
            self._slope, self._intercept = 0.0, float(np.mean(y))
        else:
            self._slope, self._intercept = np.polyfit(x, y, 1)
        return self

    def predict(self, X):
        x = np.asarray(X, dtype=float)[:, 0]
        return self._slope * x + self._intercept
