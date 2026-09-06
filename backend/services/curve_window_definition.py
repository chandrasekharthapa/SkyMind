"""Curve-level window features: volatility and trend over one flight's own history.

One definition per feature, called by both the training and the inference branch of
`VolatilityGenerator` and `TrendGenerator`. Before this module those two branches
were independent implementations that disagreed under identical feature names:

  * **Dispersion convention.** Training used pandas `.rolling(...).std()` — the
    sample standard deviation, ddof=1 — and inference used `np.std(...)`, the
    population standard deviation, ddof=0. `rolling_volatility`,
    `coefficient_of_variation`, `volatility_trend` and `trend_strength` were all
    built on it, so four features meant different things on the two paths.
    `test_training_inference_parity.py` exempted `trend_strength` from its parity
    assertion rather than reconciling the two.

  * **Curve identity.** Both branches grouped on four keys — origin, destination,
    airline, departure date — carrying no per-flight component at all, while the
    repository defines the curve as five-part (`BOOKING_CURVE_KEYS`, whose fifth
    component is `departure_time` as of 2026-09-03 and was `flight_number` before
    it). Two different flights of one airline on one route and date were therefore
    pooled into a single price history, so an EMA "of this fare" interleaved
    another flight's fares.

  * **Ordering column.** Both sorted on `recorded_at`, hardcoded, while the
    pipeline's canonical observation time is `search_timestamp`
    (`resolve_ordering_timestamp_column`). Where the two differ — a nightly batch
    write stamps one `recorded_at` on rows searched hours apart — the window order
    was not the order the fares were observed in, and it was not the order the
    leakage check masks on either.

  * **Unknowns reported as numbers.** `.fillna(0.0)` on four rolling standard
    deviations, `.fillna(1.0)` on `volatility_trend`, `.fillna(0.0)` on
    `trend_direction` and `trend_strength`, `.clip(lower=1.0)` on two denominators,
    and at inference a curve with no history reported `ema_7`, `ema_14`,
    `rolling_median_7` and `rolling_mean_14` as the quoted fare itself — the
    model's own input column under four trend names. All of those are now NaN,
    which is what "not enough history to say" means to XGBoost.

  * **`trend_duration`** was 1.0 for a one-observation curve in training and 0.0
    for the same curve at inference.

Every feature here is causal by construction: `rolling`, `ewm` and the run-length
scan read backwards only, and the value at a row is a function of that row and
earlier ones on the same curve. Observations sharing a timestamp are collapsed to
the value at the *last* of them, so masking the corpus to `<= t` reproduces the
feature exactly — the tie group either survives whole or is absent whole. The
residual is the order of two observations of one flight at one instant, which is a
duplicate scrape rather than a curve; ties keep the input frame's order, and a
stable sort makes that deterministic for a given frame.
"""

from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from backend.services.booking_curve_definition import (
    BOOKING_CURVE_KEYS,
    MIN_OBSERVATIONS_FOR_STD,
    ORDERING_TIMESTAMP_KEY,
    ROLLING_WINDOW_OBSERVATIONS,
    curve_identity_from_record,
    curve_identity_is_complete,
    curve_identity_mask,
    observed_at_of_record,
    ordering_timestamps,
)

# Spans and windows, in observations — not days. The features are named `ema_7`,
# `rolling_median_7`, `rolling_mean_14`; on a curve scraped twice a day `ema_7`
# spans three and a half days, not seven. The names are the shipped contract and
# are left alone; this comment is the correction.
EMA_SHORT_SPAN: int = 7
EMA_LONG_SPAN: int = 14
MEDIAN_WINDOW_OBSERVATIONS: int = 7
MEAN_WINDOW_OBSERVATIONS: int = 14
VOLATILITY_TREND_SHORT_OBSERVATIONS: int = 5
VOLATILITY_TREND_LONG_OBSERVATIONS: int = 15

# `trend_strength` is |ema_short - ema_long| / (rolling std + this). It is not a
# goodness-of-fit statistic, whatever `feature_metadata.py` says about it.
TREND_STRENGTH_STD_OFFSET: float = 1.0

VOLATILITY_FEATURES: List[str] = [
    "rolling_volatility", "coefficient_of_variation", "rolling_price_range",
    "rolling_iqr", "volatility_trend",
]

TREND_FEATURES: List[str] = [
    "ema_7", "ema_14", "rolling_median_7", "rolling_mean_14",
    "trend_direction", "trend_strength", "trend_duration",
]


def curve_group_columns(df: pd.DataFrame) -> List[str]:
    """The booking-curve key columns actually present on `df`."""
    return [k for k in BOOKING_CURVE_KEYS if k in df.columns]


def _require_curve_identity(df: pd.DataFrame) -> List[str]:
    keys = curve_group_columns(df)
    if not keys:
        raise ValueError(
            "curve window features need a curve identity: none of "
            f"{BOOKING_CURVE_KEYS} is present on a frame with columns "
            f"{sorted(df.columns)[:12]}. Without one every observation would be "
            "pooled into a single price history."
        )
    return keys


def _empty(names: Sequence[str]) -> Dict[str, pd.Series]:
    return {name: pd.Series(dtype="float64") for name in names}


class _OrderedCurves:
    """A frame sorted into curve order, with the pieces every feature needs.

    `sorted_frame` is `df` ordered by curve key then observation time with a stable
    sort, so ties keep the caller's order. `price` is the numeric fare on that
    order. `tie_keys` identifies one curve at one instant, which is the unit ties
    are collapsed over. `restore` puts a computed Series back on the caller's index.
    """

    def __init__(self, df: pd.DataFrame) -> None:
        self.keys = _require_curve_identity(df)
        times = ordering_timestamps(df)
        frame = df.assign(_curve_ts=times, _curve_price=pd.to_numeric(
            df["price"], errors="coerce") if "price" in df.columns
            else pd.Series(np.nan, index=df.index, dtype="float64"))
        # An unorderable observation cannot be placed on the curve. It is dropped
        # from the windows rather than sorted to one end, where it would silently
        # become either the oldest or the newest fare.
        self.unorderable = times.isna()
        # An observation whose curve key is incomplete is dropped for the same
        # reason, one step earlier: it cannot be placed on *a* curve. The group
        # below uses `dropna=False`, so without this every unnumbered flight on a
        # route and date would share one group and one EMA — the five-key identity
        # defeated by a null. `restore` reindexes to the caller's frame, so these
        # rows come back NaN, which is what "no curve" means.
        self.unidentified = ~curve_identity_mask(df)
        frame = frame[~(self.unorderable | self.unidentified)]
        # mergesort: pandas' default quicksort is unstable, so tied observations
        # would change places between runs and the EMA with them.
        self.sorted_frame = frame.sort_values(
            by=self.keys + ["_curve_ts"], kind="mergesort")
        self.price = self.sorted_frame["_curve_price"]
        self.group = self.sorted_frame.groupby(self.keys, dropna=False)["_curve_price"]
        self.tie_keys = self.keys + ["_curve_ts"]
        self.index = df.index

    def rolling(self, window: int, how: str, **kwargs: Any) -> pd.Series:
        return self.group.transform(
            lambda s: getattr(s.rolling(window=window, min_periods=1), how)(**kwargs))

    def ewm(self, span: int) -> pd.Series:
        return self.group.transform(
            lambda s: s.ewm(span=span, adjust=False).mean())

    def count(self, window: int) -> pd.Series:
        return self.group.transform(
            lambda s: s.rolling(window=window, min_periods=1).count())

    def restore(self, values: pd.Series) -> pd.Series:
        """Collapse ties to the last observation's value, then reindex to `df`.

        Every observation sharing a curve and a timestamp takes the value of the
        window that closes after the last of them. That is what makes the feature
        mask-invariant: a prefix mask keeps or drops such a group whole, so the
        value it reproduces is the same one.
        """
        collapsed = values.groupby(
            [self.sorted_frame[k] for k in self.tie_keys], dropna=False
        ).transform("last")
        return pd.Series(collapsed, dtype="float64").reindex(self.index)


def volatility_features(df: pd.DataFrame) -> Dict[str, pd.Series]:
    """The five volatility features for every row of a training frame."""
    if df.empty:
        return _empty(VOLATILITY_FEATURES)
    curves = _OrderedCurves(df)

    observations = curves.count(ROLLING_WINDOW_OBSERVATIONS)
    enough = observations >= MIN_OBSERVATIONS_FOR_STD
    std = curves.rolling(ROLLING_WINDOW_OBSERVATIONS, "std").where(enough)
    mean = curves.rolling(ROLLING_WINDOW_OBSERVATIONS, "mean")
    low = curves.rolling(ROLLING_WINDOW_OBSERVATIONS, "min")
    high = curves.rolling(ROLLING_WINDOW_OBSERVATIONS, "max")
    q75 = curves.rolling(ROLLING_WINDOW_OBSERVATIONS, "quantile", q=0.75)
    q25 = curves.rolling(ROLLING_WINDOW_OBSERVATIONS, "quantile", q=0.25)

    short = curves.rolling(VOLATILITY_TREND_SHORT_OBSERVATIONS, "std").where(
        curves.count(VOLATILITY_TREND_SHORT_OBSERVATIONS) >= MIN_OBSERVATIONS_FOR_STD)
    long = curves.rolling(VOLATILITY_TREND_LONG_OBSERVATIONS, "std").where(
        curves.count(VOLATILITY_TREND_LONG_OBSERVATIONS) >= MIN_OBSERVATIONS_FOR_STD)

    out = {
        "rolling_volatility": std,
        # Was `std.fillna(0.0) / mean.clip(lower=1.0)`, then `.fillna(0.0)`. A
        # coefficient of variation with no dispersion figure is unknown, not zero.
        "coefficient_of_variation": (std / mean).where(mean > 0),
        "rolling_price_range": high - low,
        "rolling_iqr": q75 - q25,
        # Was `(short / long.clip(lower=1.0)).fillna(1.0)`, which reported "the
        # short and long windows are equally volatile" whenever either was unknown.
        "volatility_trend": (short / long).where(long > 0),
    }
    return {name: curves.restore(series) for name, series in out.items()}


def trend_features(df: pd.DataFrame) -> Dict[str, pd.Series]:
    """The seven trend features for every row of a training frame."""
    if df.empty:
        return _empty(TREND_FEATURES)
    curves = _OrderedCurves(df)

    ema_short = curves.ewm(EMA_SHORT_SPAN)
    ema_long = curves.ewm(EMA_LONG_SPAN)
    gap = ema_short - ema_long
    # Not `.fillna(0.0)`: 0.0 already means "the two averages are equal", so
    # filling made "flat" and "unknown" the same number.
    direction = pd.Series(np.sign(gap), index=gap.index, dtype="float64")
    direction = direction.where(gap.notna())

    std = curves.rolling(ROLLING_WINDOW_OBSERVATIONS, "std").where(
        curves.count(ROLLING_WINDOW_OBSERVATIONS) >= MIN_OBSERVATIONS_FOR_STD)
    strength = gap.abs() / (std + TREND_STRENGTH_STD_OFFSET)

    # Run length of the current sign, counted forwards from the start of the curve
    # and therefore causal. NaN where the direction itself is unknown, rather than
    # counting a run of unknowns.
    def _run_length(signs: pd.Series) -> pd.Series:
        runs = (signs != signs.shift()).cumsum()
        return signs.groupby(runs).cumcount().add(1).astype("float64")

    duration = direction.groupby(
        [curves.sorted_frame[k] for k in curves.keys], dropna=False
    ).transform(_run_length).where(direction.notna())

    out = {
        "ema_7": ema_short,
        "ema_14": ema_long,
        "rolling_median_7": curves.rolling(MEDIAN_WINDOW_OBSERVATIONS, "median"),
        "rolling_mean_14": curves.rolling(MEAN_WINDOW_OBSERVATIONS, "mean"),
        "trend_direction": direction,
        "trend_strength": strength,
        "trend_duration": duration,
    }
    return {name: curves.restore(series) for name, series in out.items()}


def _curve_frame(
    records: Optional[Sequence[Dict[str, Any]]],
    curve: Dict[str, Any],
    current_price: Optional[float],
    current_time: Any,
) -> Optional[pd.DataFrame]:
    """This curve's history plus the fare being quoted, as a training-shaped frame.

    Filtered to the curve, because these features are about one flight's own price
    history — unlike the market aggregates, which need the rest of the market.
    Returns None when the quoted fare is unusable: every feature here is a window
    ending at the quote, so without it there is nothing to end the window on. And
    None when the curve itself is not named, because a window over one flight's
    history needs to know which flight: with the per-flight component missing from
    the query no retrieved observation could match, and the features were computed
    from the quoted fare alone — `rolling_price_range` and `rolling_iqr` 0.0,
    `trend_direction` 0.0, `trend_duration` 1.0, and the three moving averages all
    equal to that single fare.
    """
    if not curve_identity_is_complete(curve):
        return None

    try:
        price = float(current_price)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if np.isnan(price):
        return None

    identity = {key: curve.get(key) for key in BOOKING_CURVE_KEYS}
    rows: List[Dict[str, Any]] = []
    for row in (records or []):
        if not isinstance(row, dict):
            continue
        # Built from `BOOKING_CURVE_KEYS`, not hand-typed. It was a literal
        # five-key dict naming `flight_number`, and the comparison below iterates
        # `BOOKING_CURVE_KEYS` — so when the per-flight component became
        # `departure_time` on 2026-09-03, `candidate["departure_time"]` raised
        # `KeyError` on the first retrieved observation. That is the one failure
        # mode in this sweep that is an exception rather than a wrong number: it
        # fires on the serving path as soon as a caller supplies a complete
        # identity, which `prediction_service` now does.
        candidate = curve_identity_from_record(row)
        if any(candidate[key] != identity[key] for key in BOOKING_CURVE_KEYS):
            continue
        # `row.get(ORDERING) or row.get(FALLBACK) or row.get("recorded_date")` was
        # the right preference order but selected on truthiness, so an unparseable
        # `search_timestamp` — truthy, and coerced to NaT by the frame constructor
        # below — shadowed a `recorded_at` that would have parsed. The row was then
        # kept with no usable position on the curve. `observed_at_of_record` tries
        # each candidate and moves on when one does not parse; `recorded_date` stays
        # as a third fallback because a serving-path history dict may carry only the
        # derived date.
        stamp = observed_at_of_record(row) or row.get("recorded_date")
        if stamp is None or row.get("price") is None:
            continue
        rows.append({**candidate, ORDERING_TIMESTAMP_KEY: stamp,
                     "price": row["price"]})

    # Last, so it is the row the caller reads back and the row every window ends on.
    rows.append({**identity, ORDERING_TIMESTAMP_KEY: current_time, "price": price})
    return pd.DataFrame(rows, index=pd.RangeIndex(len(rows)))


def _quoted_row(
    build: Any,
    names: Sequence[str],
    records: Optional[Sequence[Dict[str, Any]]],
    curve: Dict[str, Any],
    current_price: Optional[float],
    current_time: Any,
) -> Dict[str, float]:
    frame = _curve_frame(records, curve, current_price, current_time)
    if frame is None:
        return {name: float("nan") for name in names}
    columns = build(frame)
    request = frame.index[-1]
    out: Dict[str, float] = {}
    for name in names:
        value = columns[name].loc[request]
        out[name] = float(value) if pd.notna(value) else float("nan")
    return out


def volatility_features_from_records(
    records: Optional[Sequence[Dict[str, Any]]],
    *,
    curve: Dict[str, Any],
    current_price: Optional[float],
    current_time: Any,
) -> Dict[str, float]:
    """The five volatility features for a fare being quoted now.

    Calls `volatility_features` — the function the training path calls — on this
    curve's history ending in the quote. There is no second implementation.
    """
    return _quoted_row(volatility_features, VOLATILITY_FEATURES, records, curve,
                       current_price, current_time)


def trend_features_from_records(
    records: Optional[Sequence[Dict[str, Any]]],
    *,
    curve: Dict[str, Any],
    current_price: Optional[float],
    current_time: Any,
) -> Dict[str, float]:
    """The seven trend features for a fare being quoted now."""
    return _quoted_row(trend_features, TREND_FEATURES, records, curve,
                       current_price, current_time)
