# Quarantined model artifacts

These artifacts are kept as evidence and are **not loadable**. `PricePredictor.load()`
refuses any artifact whose metadata carries no `leak_audit` block, and none of these has
one — they were trained before the check existed. Nothing here is served.

They are not deleted because their `feature_importances` blocks are the measurement that
justifies the rest of this directory's history.

## Why they were withdrawn

At horizon 0 the training target is the observed price itself
(`services/training_dataset_builder.py`, `df_features["target_price"] = df_features["price"]`).
Two of the sixteen features are defined in `ml/features/booking_curve.py` as

```python
price_1d = df["price"] - gp["price"].shift(1)
price_3d = df["price"] - gp["price"].shift(3)
```

so at that horizon both features are `target − a lagged target`. They contain the answer.

The `.metadata.json` files record how much the models leaned on them:

| artifact | observations | train / test | R² | MAPE | published "accuracy" | importance on `price_change_*` |
|---|---|---|---|---|---|---|
| `fare_forecast_0d` | 31,537 | 25,229 / 6,308 | 0.9318 | 9.41% | 90.59% | **48.07%** |
| `fare_forecast_1d` | 2,998 | 2,398 / 600 | 0.4248 | 1.36% | 98.64% | 10.26% |
| `fare_forecast_3d` | 132 | 105 / 27 | 0.7072 | 8.26% | 91.74% | 0.00% |

Three things in that table are worth stating plainly.

**The 0d model's single largest input is a leak.** `price_change_3d` alone carries 37.4% of
the importance and `price_change_1d` a further 10.6%. An R² of 0.932 on fare prediction was
substantially measuring the model's ability to recover `price` from `price − lag(price)`.

**The published accuracy figure is not accuracy.** It is `100 − MAPE`
(`ml/price_model.py`, `equivalent_accuracy_100_minus_mape`). The 1d artifact is the proof:
it reports **98.64%** while its R² is **0.4248**. Fares within a route cluster tightly, so
percentage error stays small even when the model explains under half the variance. The
frontend displayed the 100 − MAPE number as model accuracy.

**The 3d artifact was accepted on a 27-row test fold** and its metadata says
`"quality_gate_passed": true`. That field was a literal, written unconditionally after the
check rather than recording it.

## Why the leak was invisible

`ml/booking_curve_validator.py` does run a leakage test, and it passed. It masks every row
recorded *after* the target timestamp:

```python
df_masked = df_raw_sorted[pd.to_datetime(df_raw_sorted["recorded_at"]) <= target_timestamp]
```

A feature built from *past* rows survives that mask by construction, and `price − lag(price)`
is built from past rows. The test could only ever have detected a feature reading the future.
It was answering a different question from the one it was named for.

Two details made it worse. The `groupby` in `booking_curve.py` keys on
origin / destination / airline / departure_date but omits `flight_number`, which
`services/booking_curve_definition.py` includes in `BOOKING_CURVE_KEYS`. Sibling flights
scraped in the same pass therefore land in one group, so `shift(1)` is often not a time lag
at all but the price of a different flight recorded at the same instant. And the rolling
family (`rolling(window=10, min_periods=1)`) includes the current row, so for a
single-observation curve `rolling_mean_price == price == target_price` exactly.

## Why the app was still able to show a curve

The leak does not survive to serving. At inference the same feature names are computed
differently — `curve_points[-1]["price"] - curve_points[-2]["price"]`, the latest observed
price minus the previous one, over a history query that does not filter by airline — and in
the legacy path they were literal `np.nan`. Anything still missing became `np.nan` in
`predict()`. So the two features carrying 48% of the model's weight were routinely absent,
and the ensemble fell back to a near-constant output.

`forecast()` handled that by recognising the constants:

```python
if abs(price - 6097.73) < 1.0 or abs(price - 9300.0) < 1.0:
    drift_factor = {0: 1.0, 1: 1.08, 3: 0.96, 7: 1.03}.get(h, 1.0)
    price = float(lowest_fare_anchor) * drift_factor
```

On that path the published forecast was the scraped fare multiplied by four hardcoded
factors, and the model contributed nothing to it. `9300.0` also appears as a mock price in
two test fixtures. The override is deleted; `forecast()` now raises `InsufficientHistory`
(HTTP 503) when the movement features cannot be computed.

## What has to be true before an artifact loads again

`load()` requires `leak_audit` in the metadata with `clean: true`. That block is produced by
`audit_feature_leakage()` in `ml/price_model.py`, which fits a depth-3 probe on each feature
alone and scores it against the test fold; any feature reaching an R² of 0.50 by itself is
recorded as a suspect and the acceptance gate rejects the run. The gate also requires
R² ≥ 0.0, MAPE ≤ 35%, and a test fold of at least 30 rows — the criterion the 3d artifact
above would fail.

`fare_forecast_7d.pkl` is here for a different reason: it never had a `.metadata.json`
sibling, so `load()` skipped it silently and the 7d horizon has never existed at runtime
despite being listed in `supported_horizons`.

`global_model.pkl` is here because `load()` falls back to it when no horizon artifact loads.
Leaving it in place would have routed every request to a legacy model trained by the same
code with the same leak.

