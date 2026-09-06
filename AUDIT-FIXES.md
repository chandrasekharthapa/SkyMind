# SkyMind — Fix Log

What changed in the codebase after the audits in `AUDIT.md` and
`AUDIT-ADDENDUM.md`, why, and what is still open. Written to be read by someone
who has not seen the audits: each entry states the defect, then the fix.

Everything below is in the working tree and **not committed** — the commit is
yours to make after reviewing the diff.

---

## Fixed

**1. Live credentials were committed, and five source files did not parse.**
`.env` and `backend/.env` were tracked, and a Supabase `service_role` JWT plus a
Postgres connection string with its password had also been pasted into tracked
`.py` files. Separately, five of ~400 tracked Python files could not be compiled
at all — four had been written to disk JSON-escaped (`\n` as two characters), one
was UTF-16LE with a BOM — and nothing noticed because none of the five is
imported by any runtime path. The literals are gone from source, the dotenv files
are untracked and ignored, and CI now fails on either class. **The credentials
themselves still need rotating; that is on you.**

**2. Nothing in this repository was ever checked automatically.**
`frontend/next.config.js` set `typescript.ignoreBuildErrors` and
`eslint.ignoreDuringBuilds` with the comment "CI handles them separately" — there
was no CI, only a nightly data-pipeline workflow. With the suppression removed
`tsc --noEmit` reported 37 errors; they are now zero, mostly missing exports in
`@/types` and components reading fields the API does not send. ESLint had neither
a config nor the dependency; both are present now. `.github/workflows/ci.yaml`
runs five jobs on every push: secret hygiene, a parse check over every tracked
`.py`, `pytest`, frontend typecheck and production build, and ESLint.

**3. Ingestion reported success when it had ingested nothing.**
Four separate shapes, all of which made a failed run look like a good one. The
MCP transport returned an empty list instead of raising when the browser call
failed, so a scraper crash read as "no flights today". The row count in the
result was the number of rows *displayed*, not the number *persisted*. The
scheduler treated a zero-row batch as success, so the circuit breaker could
never open — a breaker cannot trip on a callee that returns failure as data.
And the booking-horizon field was computed from wall-clock time at write, not
from the row's own `recorded_at`, so re-processing a batch changed its features.
All four now fail loudly. A synthetic `flight_number` default that invented an
identity for rows the scraper had not given one was removed rather than fixed.

**4. The application did not boot.**
`from database import database as db` binds the *module* named `database`, not
the singleton object of the same name inside it. Twenty call sites were
therefore calling instance methods on a module. The boot path's bare imports are
now package-qualified, and the singleton is imported by name.

**5. A model that failed to load took the whole process down.**
Startup and `/health` now degrade — the API reports the model as unavailable and
keeps serving the endpoints that do not need it — instead of raising at import
time.

**6. `/system` published four numbers nobody had measured.**
Dataset version `DATASET_2026_Q3_V1`, training timestamp
`2026-07-20T12:00:00Z`, observation count `4200`, coverage `30 days`. All four
were hardcoded fallbacks for values no code path ever assigned, so the endpoint
served them unconditionally — a plausible-looking dataset description with no
dataset behind it. They now come from the loaded artifact's metadata and are
`null` when absent.

**7. The code wrote columns the database did not have.**
`price_history` and `bookings` were both out of step with their writers.
`backend/migrations/001_*.sql` is authored — additive and idempotent, dropping
nothing — and **has not been run**. Read it before applying it to your Supabase
project.

**8. Today's fare was served as an AI prediction, and the UI called it verified.**
`predicted_price` was populated with the current price when no model was
available, and the frontend rendered an evidence panel next to it whose
"verification" lines were literals that always displayed. Prediction and current
price are now distinct fields, a missing prediction is absent rather than
substituted, and the fabricated panel is deleted.

**9. The audit endpoint served UNAUDITED while a recorded FAIL sat on disk.**
`validation_status` resolved its report directory relative to the current working
directory, so it found nothing whenever the server was started from anywhere but
one specific folder — and "not found" rendered as UNAUDITED rather than as an
error. The path is now derived from `__file__`. (The same CWD-relative pattern
survives at `routers/chat.py:32`, listed below as open.)

**10. Confidence was 95.0 whenever it was unknown, and the polarity was backwards.**
The fallback was not neutral: a request that lost its market snapshot — strictly
less information — came back with *higher* confidence than one that had it,
because the snapshot's contribution was subtracted rather than added. Confidence
is now computed from named inputs, carries provenance for each, and falls when an
input is missing.

**11. The training label leaked, and the features could read the present.**
This is the finding that matters most, because every accuracy number the project
had ever printed was produced under it.

The booking-curve key was supposed to identify one flight's price history, but
`flight_number` was appended to it inside a branch that was never true. The key
was therefore route-plus-date, so the "next observation on this curve" that
became the training label could be a *different flight's* fare quoted at the same
moment. The lags were positional (`shift(1)`, `shift(3)`) over a frame that mixes
flights and search times rather than time-based, so a row's "price 1 day ago"
could be a fare quoted after it. And the route and market aggregates were
whole-corpus `groupby(...).transform(...)`, which computes a row's
`historical_maximum_fare` over observations recorded *after* it, including the one
it is supervised against — on a 75-row batch-written fixture, 3 rows had a route
maximum exactly equal to their own fare.

Fixed by making the identity complete, the lags time-based with an explicit
tolerance per horizon, and every aggregate as-of: the value for an observation at
time *t* is computed from observations at or before *t* and from nothing else.
Snapshot aggregates are now keyed on the resolved ordering column instead of
`recorded_at`, which is what made them leak under batch writes: on that same
fixture, keying on `recorded_at` moved 8 of the 12 snapshot features once later
rows were masked — `lowest_fare` 4588 → 6727, `average_fare` 5657.5 → 6727,
`fare_spread` 2139 → 0, `price_std_dev` 1512.50 → 0, `total_live_flights` 2 → 1.
Training and serving now call one shared definition
(`backend/services/market_aggregate_definition.py`) rather than two
implementations that disagreed under identical feature names.

**12. The shipped model files were trained under that leak.**
Every `.pkl` in `backend/ml/models/` predates the fix, so its metrics describe a
model that could see its own answer. They are moved to
`backend/ml/models/quarantine/`, and `load()` refuses any artifact whose metadata
does not carry a clean leak-audit record. The project ships with no model until
one is retrained — which is the honest state, and better than a good-looking
number you cannot defend in an interview.

**13. The acceptance gate could not fail, and the number beside it was not accuracy.**
`MIN_TEST_R2` was `0.0`, which any fitted model clears, and the figure published
alongside it as "accuracy" was a different quantity entirely. The threshold now
binds, and the metric is named for what it computes.

**14. The leak audits now run during training.**
Three checks existed in various states of disconnection — one had no production
caller, one was never written: that a feature is not a function of later data,
that a booking-curve window does not read another flight's simultaneous fare, and
that no feature is an affine transform of the label. `train()` now runs all three
before fitting, refuses the horizon when a verdict is not clean, and records each
verdict in the artifact metadata — which is what §12's `load()` check reads.

One of those audits raised an error when no cross-sectional feature moved under
masking. That condition is true of every honest `legacy` feature set, whose
cross-sectional features are all per-row functions nothing can move, so as
written it would have blocked all future legacy retraining. It is a warning now,
with the reasoning recorded at the code.

**15. Two smaller correctness fixes.**
A booking curve now exists only when its flight identity is complete, rather than
being silently grouped under a partial key; and the forecast path fails closed —
when there is not enough history for a horizon, the API says so instead of
returning a number. The Puppeteer Chrome path is no longer hardcoded to one
machine.

**16. Every horizon was served by one horizon's model.**
`predict()` answered a horizon it had no artifact for by falling back to the
shortest one it did have, and the forecast loop iterated the *declared* horizons
`[1, 3, 7]` regardless of what had loaded. A build carrying only a 1-day artifact
therefore published a three-point curve in which all three points were the 1-day
model's output, labelled 1d, 3d and 7d. It looked like a forecast and was one
number repeated. `predict()` now refuses a horizon it cannot serve, the loop
iterates only the horizons that have a model, and it refuses outright when none
does — with the gap logged rather than filled.

**17. The encoders were not stable across horizons or across restarts.**
The per-horizon label encoders shared one dictionary, so training a second
horizon overwrote the first horizon's categories while its model kept the integer
codes from the old mapping. The unseen-category fallback was
`(abs(hash(val)) % 900) + 31`, and `hash()` on a `str` is salted per process — the
same unknown airline mapped to a different code on every restart, so a model's
inputs depended on which interpreter served the request. Both are keyed and
deterministic now. A feature that is NaN for every training row is also no longer
accepted silently: training records or refuses it, which is what makes the
`departure_time` gap in §"Open work" visible rather than invisible.

**18. The registry answered from literals instead of from the artifact.**
`supported_routes` returned `["DEL-BOM", "BOM-DEL"]` whatever had been trained;
`supports_forecasting` defaulted to `True` for a predictor that never declared it;
`observation_count` and `coverage_days` fell back to `4200` and `30`. Each now
derives from the loaded artifact and reports absence as absence. Two guards that
existed only to undo those defaults are gone with them, including one in
production code that imported `unittest.mock` to detect a value the registry
should never have returned. `load()` is atomic: a partially-read artifact leaves
the previous model in place rather than a half-populated one.

**19. The observation time was resolved per column, so the entire legacy corpus
fell out of the pipeline.**
`ordering_timestamps` — the canonical "when was this fare observed" — picked
`search_timestamp` or `recorded_at` by *presence* and then read only that one
column. Migration 001 adds `search_timestamp` with no default and no backfill, so
on every row written before it the column exists and is NULL. The resolver
returned all-`NaT`, and the corpus emptied by two independent routes: the lag
helper's `if not usable.any()` early return made every price-movement feature and
the supervised label NaN, so the label join dropped every row; and, earlier still,
`training_dataset_builder` compared `departure_date >= recorded_date` against
`None` for every row, dropped the whole frame, and logged the false explanation
"every observation was recorded after its departure date" — which sent the reader
looking at the data instead of at that line. Nothing raised. Training simply saw
an empty dataset.

It now coalesces *per observation*: `search_timestamp` where it parses,
`recorded_at` where it does not. That matches the writer, which resolves a missing
`search_timestamp` to `recorded_at` before insert and derives `booking_date` from
the result — a reader that refused the fallback disagreed with the writer about
the same fact. The residual skew is ingest latency, bounded by seconds, and cannot
move an as-of match: the tightest tolerance any caller uses is half a day.

Five hand-rolled copies of the same rule were sweeping the corpus in three
mutually contradictory orders. Three preferred `recorded_at` — the *insert* time —
over the search instant: `dataset/dates.py` (a search at 23:58 recorded at 00:03
made a correct `days_until_dep` fail by one), `dataset/snapshot.py`, and
`dataset/plugins/chronology_plugin.py`, which also raised `KeyError` on a frame
carrying neither column instead of reporting one it could not validate. Two also
picked the column by presence, including `drift_detection.py`, where the
consequence was that the chronological sort was a no-op — NaT sorts last — so the
70/30 baseline-versus-current split divided rows in database return order and
every drift score compared two arbitrary halves. It now refuses to score when
fewer than twenty observations can be placed in time. `curve_window_definition`
selected its stamp on truthiness, so an unparseable `search_timestamp` shadowed a
`recorded_at` that would have parsed. All of them go through the one definition
now, and a row-level `observed_at_of_record` exists so that no sixth copy gets
written.

`dataset/snapshot.py` was also fabricating an observation time: a row carrying
neither timestamp was stamped with `datetime.now()`, writing the moment the
exporter ran into `snapshot_time` and `snapshot_date` — the two columns downstream
consumers order the curve by — indistinguishably from a real observation. Such
rows now record `None` and are left unnumbered rather than given a position
derived from frame order.

**20. The forecast evaluation subsystem had never evaluated a forecast.**
The scheduler called `.eq("status", "PENDING")` directly on the table builder with
no `.select()` in between, which raises `AttributeError`; the handler caught it and
returned 0. So the subsystem meant to tell you whether past forecasts came true
had never completed an iteration — and repairing that one line would have been
worse than leaving it broken, because the body it unblocked fabricated its ground
truth. The fallback query carried no date predicate, so it selected every recorded
price for the route regardless of when it was observed, then took `min()` — the
cheapest fare ever seen on the route became the "actual". The primary query matched
`departure_date = forecast_time + horizon`, which is not what a horizon means. The
forecast's `airline` and `flight_number` were read and never used, so nothing
constrained the match to the flight that had been forecast. A forecast that could
not be evaluated had no terminal state either, and stayed `PENDING` for ever.

The body was rewritten before the call: the actual is now the observation on the
forecast's own booking curve nearest the target date within an explicit tolerance,
admitted only through the same provenance predicate the training loader uses
(`is_synthetic IS FALSE AND is_live IS TRUE`), and a forecast whose actual cannot
be established is closed as unevaluable with the reason recorded instead of
retried for ever.

**21. The confidence interval was ±6% of whatever the model happened to say.**
`forecast()` computed `band = max(120.0, price * 0.06)` and published `price ±
band` as the model's prediction interval. Nothing the model measured was an input
to that width: it was the same interval for a horizon the model predicts well and
one it predicts badly, symmetric no matter how skewed the errors were, and it
never widened as the model got worse. At any fare above ₹2,000 it worked out to
exactly 12% of the point estimate, every time. The lower bound was then clamped
with `max(IMPLAUSIBLE_FARE_FLOOR, price - band)`, so a model implying a fare below
₹800 published an interval it had not implied. An interval whose width is a
constant is a decoration on the point estimate, not a statement of uncertainty —
and nothing in the response distinguished it from a measured one.

`train()` now records, per horizon, the signed 10th, 50th and 90th percentiles of
its own test-fold residuals together with the number of residuals they were
measured on. Since `residuals = y_test - preds`, `price + p10 … price + p90` is an
empirical 80% interval for the *actual* fare: asymmetric exactly where the errors
are, and shifted by the model's bias rather than centred on a point estimate that
may be systematically off. `_interval_bounds` builds it, and refuses — with
`IntervalUnavailable`, a `PredictionUnavailable` subclass the routers already map
to 503 — when an artifact records no quantiles, records fewer than 20 residuals,
records unreadable or non-finite ones, or records a p90 below its p10. There is no
fallback, because a fabricated width and a measured one are indistinguishable once
published. A bound below the plausibility floor is now logged and published as-is
rather than moved. The width is pooled absolute rupee error, so it is the same at
₹2,000 as at ₹40,000 — a real limitation, stated in the code and bounded by the
sample size the response now carries, rather than the old band's fixed 12%.

`interval_basis` — the method, the two percentiles, the two quantiles and the
sample size — travels from the predictor through `PredictionFormatter` and into
the `ForecastDay` schema and the chatbot's evidence package, so where a published
interval came from is now readable from the response. None of the shipped
artifacts carry the new block, so every interval request against them refuses
until a retrain; they are quarantined and unloadable anyway (§12).

Three more invented bands went with it. `timeline_builder.py` gave its inserted
day-0 point `fare * 0.96 … fare * 1.04` — a ±4% uncertainty band around a fare
that had been *observed*; an observation's bounds are the observation, so it now
publishes a zero-width interval. A point arriving with no bounds took `price *
0.95 … price * 1.05`; that is a broken producer, and it now raises rather than
manufacturing an interval no model implied. And a "bounds sanity check" rewrote any
inverted interval to `price * 0.98 … price * 1.02` — which is why
`ForecastValidationEngine`'s first invariant, `lower <= price <= upper`, had never
once fired: the repair ran first and left the check nothing to find. The point now
passes through unaltered, the violation is logged, and the invariant records it.

**22. A flight the provider did not identify was published as an IndiGo flight.**
`evidence_builder.py` defaulted a missing carrier to `"6E"` and a missing carrier
name to `"IndiGo"`, a missing flight number to `"UNKNOWN_4"`, and every absent
amount to ₹0 — including forecast bounds, so a point with no interval was
published as `lower_bound_inr: 0.0, upper_bound_inr: 0.0`, an interval asserting
the fare cannot exceed zero. These items are interpolated straight into the model
prompt under a business policy reading "You NEVER fabricate flight prices,
schedules, or airport routes", and `"UNKNOWN_4"` is a string a model will quote
back as a flight number. `normalize_currency_amount` returned `0.0` from its
`except`, which is the worst available answer for a fare: a number no provider
sent, and the minimum of any set it joins. It now returns `None` for absent,
unparseable and non-finite input; every field keeps its null; the synthetic id
survives only inside the dedup key, where it cannot reach a caller; and
`price_spread_inr` is null rather than ₹0 when there are not two prices to
subtract. `test_evidence_builder.py`'s `assert normalize_currency_amount("invalid")
== 0.0` was ratifying the old behaviour and now asserts the null.

**23. Zero was published as the answer for "how wrong was this model", in three
places, and zero means perfect.** MAE, RMSE and MAPE of 0.0 do not read as "not
measured"; they read as a flawless forecaster. The most serious instance was in the
training path: `evaluation.py` returned `{k: 0.0 for k in [...]}` when no
(actual, predicted) pair survived NaN-filtering, logged as "returning zero
metrics", and `price_model`'s acceptance gate is `math.isfinite(r2) and r2 >=
MIN_TEST_R2` with `MIN_TEST_R2 = 0.0` — so R² of exactly 0.0 **passes**. A horizon
whose evaluation set was entirely unusable published perfect errors and was
registered by the gate that exists to reject models like it. It now returns NaN,
which is the convention `metrics.mape_with_coverage` had already established and
documented for this project ("not a large error and not a small one"), and which
makes the existing gate fail closed without touching the gate: `math.isfinite(nan)`
is False. The empty case could not simply be delegated to `compute_all`, because
`metrics.r2([], [])` returns **1.0**.

`forecast_evaluator.py` held the second copy: an empty frame returned nine zeros
including `recommendation_accuracy`. It also recomputed the metrics inline instead
of calling `backend.ml.metrics`, and its MAPE used `abs_error / max(actual, 1.0)` —
the clipped denominator `mape_with_coverage` exists to repudiate, which does not
skip a non-positive fare but scores the row against ₹1. It published `bias` and
`drift` as two diagnostics that are the same number by algebra. And
`recommendation_accuracy` counted `MONITOR` as automatically correct, so a
recommender that always said `MONITOR` scored 100%; it cannot be computed from
these columns at all, since it needs the fare quoted when the advice was given.
Six uncalled methods went with it, along with the `evaluation_history.jsonl` they
read and wrote, a file that has never existed — and into which
`track_historical_prediction` wrote per-prediction records that `get_rolling_metrics`
averaged as per-evaluation ones.

`consistency_validator.py` held the third: five error metrics initialised to 0.0,
never assigned, logged once per forecast day as "Observational Metrics for Horizon
Nd — MAE: 0.00, RMSE: 0.00 …", and returned in a `metrics` block that
`prediction_service` published in **every** `ForecastValidated` event. Forecast
error needs a realised fare, so prediction time cannot compute it; the block is
gone and the measurement lives only in `forecast_evaluation_scheduler` and
`forecast_evaluator`. Two adjacent zeros in the same file: its deviation gauge was
labelled `airline_distribution.get("origin", "NA")` — `MarketSnapshot` has no route
field and that dict maps airline to count, so every point in the series was
labelled `"NA"`; the route is now passed from the call site, where it was already
in scope. And `prediction_anomalies_total` was declared and never incremented, so
the anomaly counter read 0 however many fired. `prediction_deviation_rupees` was
removed as an unlabelled duplicate of the validator's own deviation series.

Four test modules ratified all of this. `test_evaluation.py` asserted `mae == 0.0`
for the unevaluable case; `test_prediction_accuracy_metrics.py` and
`test_forecast_accuracy_metrics.py` were near-duplicates asserting only that the
five fabricated keys were *present*, which no constant can fail; and
`test_historical_platform.py` asserted the `bias` key. All four now pin the
undefined-not-zero property, and the seven-name metric list that had been written
out by hand in four places is derived from `metrics._METRIC_FUNCS`, so a key and
its implementation cannot drift apart.

**24. There was a second ingestion driver, with its own route list, writing
straight to `price_history`.**

`backend/bash.py` — 144 lines under a filename that reads like a stray shell
command — was a working "Manual Data Ingestion Script": it looped an 18-pair
`STRATEGIC_ROUTES` constant across ten booking horizons, called the live MCP
transport, and inserted the rows with
`db.supabase.table("price_history").insert(...)`, bypassing the persistence path
in `ingestion_controller` that everything else goes through. Two route lists and
two writers, in a project whose entire ML claim rests on one corpus.

The scheduled pipeline does not read that constant and never did.
`run_pipeline.py` calls `scheduler._collect_popular_routes`, which builds its
batches from `route_catalog_config` — that is, from
`backend/route_catalog/routes.yaml`. So the four routes that were in
`STRATEGIC_ROUTES` and not in the catalogue (`BBI-BOM`, `BOM-BBI`, `BBI-BLR`,
`BLR-BBI`) were never being collected on a schedule, whatever the script listed;
they were only ever collected on the days somebody ran `python bash.py` by hand.
Those four are now enabled entries in the catalogue, which takes the collected
set from 52 routes to 56.

The other four (`DEL-DXB`, `DXB-DEL`, `BOM-DXB`, `DXB-BOM`) are recorded in the
catalogue with `enabled: false` and the reason written beside them. They are
international, the only provider wired to the collector is the Google Flights
scraper reached over MCP, and nothing in this repository shows that transport
returning results for an international pair. Enabling them would add a route that
logs a zero-match
warning for each of thirteen departure buckets every day and stores nothing —
and in the stored corpus, a route that yielded nothing is indistinguishable from
a route with no fares. `routes_from` filters on the flag, so a disabled entry
costs nothing at collection time; the pair survives as a record of intent
instead of as a daily silent failure.

`routes.yaml` and `routes.json` were edited together. The loader prefers the YAML
and falls back to the JSON, so letting them disagree would mean the collected
route set changed depending on which file parsed. Both now yield the same 56
active pairs and the same 7 batches of 8, verified by loading each through the
real `routes_from` predicate.

Ten more loose files went with it, all of them one-off probes that had been
committed: `scratch_list_cols.py` and `scratch_list_cols_alerts.py` (print the
column names of a table), `scratch_test_booking.py` (inserts a booking row —
running it wrote to the live database), `test_flight.py` through
`test_flight4.py` and root `test_flight.py` (print one MCP search response),
`test_nemo.py`, and root `scratch_trace.py`. The four `backend/test_flight*.py`
files were also the last places in the repository still importing
`services.mcp_client` rather than `backend.services.mcp_client` — the shadow
spelling that §"the imports loaded a second copy of the application" describes in
`run_pipeline.py`. Nothing imports any of the eleven, and nothing in `.github`
names them. The originals are archived at
`.archive/loose-scratch-scripts-2026-09-02.tar.gz`.

One correction to what the earlier version of this file said about them: they are
**not** collected by `pytest`. `pytest.ini` sets `testpaths = backend/tests`, so
the `test_*.py` files at `backend/` and at the repository root were never
gathered into a run. They were untidiness, not a failing suite — and `bash.py`
was not scratch at all, which is why its route list was folded in rather than
deleted with it.

**25. Every forecast was computed without the booking horizon.**

`PricePredictor.forecast` chose its feature set with
`fs_version = "legacy" if self.legacy_mode else "feature_set_v1"`. `legacy_mode`
is `True` on exactly one code path — the single-pickle `global_model.pkl` load —
and `False` in `__init__` and on every normal per-horizon load. So every forecast
the application actually served built a 64-name `feature_set_v1` vector and handed
it to `predict()`, which reindexed it onto the model's hardcoded legacy 16.

Measured against the real pipeline: the two feature sets share **seven** names.
Reindexing therefore kept those seven, discarded the other 57 values, and
substituted NaN for nine — `days_until_dep`, `urgency`, `day_of_week`, `month`,
`week_of_year`, `hour_of_day`, `is_peak_hour`, `demand_score`,
`seasonality_factor`. Two of those nine encode *when you book*, which is the only
thing a 30-day horizon sweep varies. The loop did recompute the horizon per point
and put it in `prediction_context`; the v1 set spells it `days_until_departure`, a
name the fitted estimator has never seen, so the pipeline emitted it under that
spelling and the reindex dropped it. Confirmed by building both sets at booking
horizons 1, 7, 14, 21: under `legacy`, `days_until_dep` is 28, 22, 15, 8 and
`urgency` moves with it; under `feature_set_v1`, `days_until_dep` is absent at
every horizon and `days_until_departure` carries the value.

The consequence is a curve whose points differ only through
horizon-independent features — which is why it came out nearly flat — computed
from a vector nine of whose columns were NaN, with no exception raised and nothing
logged. Three things that look like they should have caught it could not.
`forecast_engine`'s `validate_schema` is strict about count, names and positional
order, but it validates the vector built for the *point* prediction, and
`forecast()` rebuilds its own from `snapshot_ctx` — a green schema check sat one
line above the call that ignored it. The `missing_movement` guard reads
`price_change_1d` and `price_change_3d`, both among the seven shared names, so it
saw real values. And the refusal that did exist at the old line 1755 had inverted
polarity: it raised `InsufficientHistory("the loaded model predates the current
feature set")` for the legacy-pickle case, where a legacy vector was in fact
*correct*, and let the broken case through. It was also unreachable as a
safeguard, since `legacy_mode` implies `self.models` is empty and the
`available = [h for h in self.supported_horizons if h in self.models]` check below
already refuses by name.

`forecast()` now builds to `self.feature_set_version`, and `predict()` refuses
outright, through `_reject_foreign_features`, any vector carrying a name declared
by another feature set — naming the count of values that would have been
discarded and the legacy features that would have been NaN-filled. A caller that
omits a value it could not compute is unaffected: that arrives as NaN by design,
and `flight_search_service` relies on it, hand-building fifteen of the sixteen
names and letting `predict()` derive `urgency`.

Underneath the defect was a duplicated contract. Four hand-maintained copies of
the legacy 16-name list existed: `PricePredictor.feature_cols`,
`feature_validation.EXPECTED_FEATURE_COLS`,
`prediction_features.PredictionFeatureBuilder`, and a literal in a parity test.
The first two now derive from `backend/ml/feature_metadata.py`, which is the one
place the sets are declared — verified as a pure de-duplication, since the old
literals were name-for-name and order-for-order identical to `LEGACY_FEATURE_SET`.
Order matters here: it is the fitted estimator's column order and
`model_schema_validator` compares names position by position.
`prediction_features.py` was deleted outright — `build_predict_features` had no
caller, and it was drifting on its own; it and its two tests are archived at
`.archive/prediction-features-dead-copy-2026-09-02.tar.gz`.
`FeatureValidationService.expected_features` was `self.expected_features =
EXPECTED_FEATURE_COLS`, fixed at import time to the legacy set whatever was
loaded, so `production_readiness` could grade a frame against a contract the
running model did not hold; it now reads `model_registry.feature_set_version` at
call time, and falls back to legacy with a warning when the registry cannot
answer. A fifth copy survives as dict-literal keys in
`flight_search_service.py:207-223`; it agrees with the legacy set and was left
alone.

Two smaller things went with it. `PricePredictor` now *declares*
`feature_set_version = "legacy"` and records it in the artifact metadata, which
retires the registry's fallback of inferring the set from `len(expected_features)
<= 16` — that inference is now reached only by a test double or a pre-change
artifact. And `train()` refuses before doing any work if the registry advertises a
feature set the predictor cannot fit; previously the mismatch surfaced as a bare
`KeyError` on nine column names, raised only after every leakage audit had already
run over the full corpus.

`backend/tests/test_feature_contract_alignment.py` holds thirteen tests over this:
that `feature_cols` is the declared legacy list including order, that the foreign
name set is non-empty and disjoint from it, that a v1 vector is refused and a
partial legacy one accepted, that the horizon is present and monotone across four
booking dates under `legacy` and absent under `feature_set_v1`, and that
validation follows the deployed model's advertised set. Value-level train/serve
agreement was already covered, more strongly than anything this ticket would have
added: `test_training_inference_parity.py` compares `build_training_dataset`
against a per-row `build` for **both** feature sets with no exemption list, and
guards its own fixture against degeneracy.

**26. The eval suite could not report a failure, and its headline number was about
query parsing.**

Nine mechanisms, each of which independently produced a green report from a run
that had measured nothing.

`evaluator.py` computed `overall_success_rate` as 100.0 when `executed_count` was
zero, and because `failed_count` is also zero in that state the verdict came out
`PASS`. Every evaluator skipping — no API key, planner in fallback, an evaluator
that failed to construct — was therefore indistinguishable from every evaluator
passing. The rate is now `None` when nothing executed, that state is `FAIL` with
the skip reasons logged, and passing on a benchmark whose own schema did not hold
is `FAIL` too. Four headline metrics defaulted to their best possible value —
`intent_accuracy` and `entity_accuracy` to 100.0, `tool_f1_score` to 1.0,
`p95_latency_ms` to 50.0 — whenever the evaluator was absent or had returned
`score=None`, which is exactly what a skipped evaluator returns. The defaults are
gone. `INFRASTRUCTURE_UNAVAILABLE` was counted as executed and, because such a
result carried `passed=True`, as a pass; it is now counted as the skip it is.

`base.py` used one denominator for two different counts, so a batch could report a
pass ratio over items it had not scored; it now counts executed items only, treats
an executed-but-unscored batch as `ERROR`, and returns `passed=False` on a skip.
`run.py` could not exit non-zero at all. `markdown.py` printed three
infrastructure rows — Filesystem, Dataset and Network — as literal `| YES | YES |
HEALTHY |` text, ticked "Dataset loaded and verified" unconditionally, and defaulted
an absent verdict to `PASS` / `FULL` / `HEALTHY`; and its OpenAI and LangSmith rows
read four flat keys (`openai_api_key_configured`, `langsmith_installed`, ...) that
**no summary has ever contained**, so that table was wired to nothing while the two
tests covering it hand-built the same flat shape. There was no Network check
anywhere, so that row is gone rather than given a fabricated source.

On the dataset side, `loader.py` validated the corpus, logged the errors, and
returned the records anyway — a corpus with duplicate IDs produced a full run and a
report calling the benchmark valid. The verdict is now recorded on
`last_schema_errors` / `last_source` and surfaces as `INVALID`. Its `version`
parameter was dead: every request read `v2.0/golden.jsonl`, and any version it
didn't recognise silently fell through to the converted legacy corpus, so
`--version 9.9.9` returned ten records and reported success. The version now
selects the directory, an absent directory loads nothing, and `metadata.json` beside
the corpus is cross-checked against it — a declared count or version the corpus
contradicts is a schema error. That manifest had declared 120 records and a
25-record smoke tier against a corpus of 15 and 6; the false figures had already
propagated into `backend/evals/README.md`. `doctor.py` ended with a second bare
`load_dataset` call and printed "schema validated" for a property it never read; it
now reads the recorded verdict, and its exit code is 2 when the corpus is absent.

`groundedness` returned `passed=True` with `status="SKIPPED"` when `OPENAI_API_KEY`
was unset — the whole defect class in one line, in a directory named
`evaluators/llm/` that contained no network call. It is now a deterministic check in
`evaluators/deterministic/` that resolves airline codes through
`normalization/airline.py` and can fail on an entity the retrieved context does not
support. Over the golden corpus the seven evaluators return 11 PASS / 4 SKIPPED / 0
FAIL, with every skip carrying a reason.

The suite also gained `forecast_accuracy`, the first evaluator here whose subject is
a forecast rather than a plan. It reads forecasts already resolved against a
realised fare out of `forecast_store` and bounds three things: R² above 0, which
means beating one constant chosen with hindsight; MAPE at or under 15%; and, once a
quoted fare is on the forecast row, the improvement over the fare that was already
on screen. That third bound is the one this repository never had — 8% error passes
both absolute bounds and is still worthless beside a 1% persistence baseline.
Below 30 resolved forecasts it reports `SKIPPED` rather than a bound met on noise,
and **without Supabase credentials it reports `INFRASTRUCTURE_UNAVAILABLE`**, so on
a machine with no database the headline rate remains a statement about query
planning only. Its `forecast_store` import is deferred into the method that uses it:
at module scope it made `evaluator.py`, and therefore `doctor.py`, unimportable
without credentials, because `backend/database/database.py` raises at import time.
A test pins that.

Two CLI tiers are accepted and match **zero** records: no golden record carries a
`nightly` or `regression` tag, so `--tier nightly` and `--tier regression` load
nothing and now report `FAIL` / `INVALID` instead of a perfect score over an empty
run. The 2 adversarial cases are marked with a per-record boolean, not a tier.
`full` works because the loader reads it as "every record".

Three test modules and two documents were rewritten to match. `test_evals_accuracy.py`
had carried the name since Phase 2.5.3 with no accuracy in it — a shape-only health
check, a markdown test whose fixture hand-built the flat `environment` shape nothing
emits, and `assert run_doctor() in (0, 1, 2)`, which is the entire range of the
function. It is now 29 tests that check `backend/ml/metrics.py` against figures
worked by hand, including that R² is exactly 0.0 for a hindsight constant, which is
what `forecast_accuracy`'s floor means. `test_evals_resilience.py` covers the
"result that could not fail" class directly: 15 tests, all passing.
`test_evals_v2.py` asserted `isinstance(summary["overall_success_rate"], float)`,
satisfied by precisely the 100.0 that hid the defect; it now asserts the rate agrees
with the executed and passed counts beside it, and that the registry holds all seven
evaluators rather than a subset. Measured: `test_evals_accuracy.py` 29/29,
`test_evals_resilience.py` 15/15. `test_evals_v2.py` is `ast`-clean but could not be
executed here, because `backend.evals.evaluator` transitively imports
`opentelemetry`, which this environment does not have.

`docs/EVALUATION_FRAMEWORK.md` lines 5, 6 and 11 were false — the doctor was said to
verify "model artifact integrity" and run "14+ evaluation test scenarios", neither of
which it has ever done, and the pytest descriptions named suites and property-based
tests that do not exist. `backend/evals/README.md` documented a `datasets/regression/`
directory that isn't there, LangSmith as the system of record, a 25-case smoke tier,
four LLM-judged evaluators of which one exists as a deterministic check, a
Cost/Tokens evaluator that does not exist, `compare.py` as taking run names rather
than paths to a `summary.json`, and airline resolution as a step of the shared
normalization pipeline, which does not touch it — `6E` and `IndiGo` are compared
literally there. Both now describe the code, and every claim in them was checked
against the code before it was written.

**27. Ordering the rows was mistaken for splitting them, and two of the four
baselines had seen the answer.**

A chronological split keeps every training row's *features* older than the test
fold. It does not keep their *labels* older, and for a forecaster the label is the
whole exposure: `attach_future_target` labels a row observed at `t` with a fare on
the same booking curve at or after `t + h`, accepted within
`lag_tolerance_days(h)`. The training rows near the fold boundary were therefore
labelled by prices recorded *inside the test period*, and the fit consumed them.
Nothing in the frame reveals this, because the leak is in the label's realisation
time and no column carries it. `chronological_split` now takes `embargo_days` and
purges every training row whose label could reach the test fold; both training
paths compute the width the same way, `float(h) + lag_tolerance_days(h)`, from the
same function, so one of them cannot silently embargo nothing. `split_record`
reports `n_purged_by_embargo`, the measured fold gap, and `embargo_is_effective` —
the stronger claim that the gap is at least the width asked for — and it goes into
the artifact's metadata in place of a hardcoded `"split_strategy"` string that was
true of any split at all. It also carries a booking-curve overlap census, so a
curve appearing on both sides of the boundary is visible rather than assumed away.

The purge takes rows out of the training fold, which the 100-row corpus gate did
not bound, so both paths gained a post-purge floor. `price_model.train` keeps the
previous validated model and writes no artifact, recording
`"only N training row(s) after a X day label embargo"`; `model_trainer` raises a
`RuntimeError` naming the purge count and the horizon. **On an hourly corpus of a
few hundred rows a 7-day forecaster cannot be trained at all** — 10.5 days of purge
against a training window of about 6.7 days empties the fold — and that refusal is
the correct output, not a regression. Cross-validation gets the same width at every
fold boundary: without it the CV error could come in below the holdout error, each
fold leaking a little of its own validation period back into training, while the
report printed the two numbers side by side as though they were comparable.

`dataset_splitter.py` and `cross_validation.py` — the two modules that carry the
audit-grade split reporting — were dead code, called from nowhere. `model_trainer`
now calls both, with the embargo, and fails on an ineffective one instead of
logging it.

Of the four baselines a new model was measured against, two had seen the label.
`naive_persistence` was `np.full_like(y_true, np.mean(y_true))` — the mean of the
*test* actuals. No last-known price enters it, so it is not persistence; a
forecaster does not know the mean of the period it is forecasting, so it is an
oracle; and its R² is identically 0.0, because R²'s denominator *is* the variance
about `mean(y_true)`. That "independent baseline" was arithmetically the same check
as `MIN_TEST_R2 = 0.0`, and the pipeline was counting it twice. `rolling_mean_3` was
`np.convolve(y_true, np.ones(3) / 3, mode="same")`, and `mode="same"` is centred:
the prediction for row *i* is the mean of `y[i-1]`, `y[i]` and `y[i+1]`. It contains
the answer and the next answer as well, so on any fare series smooth enough to be
worth forecasting it holds the lowest error of any baseline, becomes
`best_baseline`, and drives every honest model to the verdict `regressed`. A
benchmark that fails a model because the baseline read the label is worse than no
benchmark.

Both are gone. What remains is persistence against the fare actually observed for
that row at the moment it was observed — the number a user gets for free by reading
the price off the screen — a constant computed from the *training* labels only, and
the previous production model where predictions for the same rows exist. Each needs
an input the caller has to supply, and an absent input is recorded in
`skipped_baselines` with its reason rather than dropped; a run with no baseline at
all now returns `not_compared`. Previously "we compared and it was the same" and
"we never compared" both printed as `unchanged`, and the second was the state this
module was in.

One consequence to expect rather than debug: the persistence criterion will very
likely reject every horizon on the `price_model.train` path, because
`LEGACY_FEATURE_SET` carries no fare level at all and a model that cannot see the
current price cannot beat holding it. The pipeline's response is the one already
chosen — `rejected[h] = "quality gate: ..."`, the previous model retained, no
artifact written — and the forecast path shows "not enough data yet". The fix is
`feature_set_v1`, with `price` among the features, which `model_trainer` already
uses.

**28. Four of the prediction's inputs were invented, and the model was fed its own
output as the market price.**

`prediction_service.predict` built the feature vector from a market snapshot that
knew, per flight, the fare, the carrier, the flight number, the seat count and the
departure time. It used the first three and synthesized the other two from the
route:

```python
seats_available = None
if market_snapshot.seat_information:
    seats_available = int(round(
        market_snapshot.seat_information.get("average", 15.0)))

# Derive departure_time_str from snapshot time distributions to
# prevent fabrication
departure_time_str = None
if market_snapshot.departure_distribution.get("morning"):
    departure_time_str = f"{departure_date}T08:00:00"
elif market_snapshot.departure_distribution.get("afternoon"):
    departure_time_str = f"{departure_date}T14:00:00"
elif market_snapshot.departure_distribution.get("evening"):
    departure_time_str = f"{departure_date}T20:00:00"
```

`seats_available` is a per-flight column of `price_history`; the mean over every
flight on the route is a different quantity, and the `15.0` default made it a
constant when the snapshot reported no seat counts at all. `departure_time` is also
per-flight, and the chain above returns `T08:00:00` whenever *any* flight on the
route leaves in the morning — an `if/elif` that stops at the first non-empty
bucket, so on a route with a morning departure every flight was scored as leaving
at eight. The comment claimed the derivation prevented fabrication. It was the
fabrication. Both now come out of `cheapest_by_airline[airline]`, the same mapping
the fare comes from, so all five values describe one flight; when the provider
reported neither, the model is sent `None` and the generators return NaN.

Passing the provider's real departure time through would have silently produced NaN
where training produced an hour. Training reads that column with
`pd.to_datetime(...).dt.hour`; serving reads it with `"T" in s` then
`split("T")[1].split(":")[0]`. Every *stored* value carries a "T" only because
ingestion normalised it — the live provider's `"21:40"` does not. The serving value
now goes through the same `MarketDataController.normalize_departure_time` that
ingest uses, so the column has one definition, the one the model was fitted on.

The 100-row history cap bounded the wrong population. `get_price_history_cache`
filtered on route and departure date, the database applied the cap, and
`price_changes_from_records` narrowed to a single booking curve *afterwards* — so
on a route with several carriers a day the newest 100 route-wide rows could contain
nought to two observations of the flight being priced. `price_change_1d` and
`price_change_3d` then came back NaN, and the refusal reported the *route's*
observation count as the reason the *flight's* features were missing. The query now
takes optional keyword-only `airline_code` and `flight_number`, so the cap bounds
the curve the features are about; the five positional callers that genuinely want
every carrier are unchanged. Its `except Exception: return []` is also logged now —
five callers treat this as a cache and an outage must not take search down, but a
refusal that names an observation count is only accurate when nothing was logged
there.

The fourth was the model reading its own output. `snapshot_ctx["current_price"]`
was `quoted_fare_val if not math.isnan(quoted_fare_val) else predicted_price`.
`forecast()` appends that value as the booking curve's latest observation and every
movement feature is a difference against it, so whenever the live fare was
unavailable the model was conditioned on itself — and the "you would save ₹X"
figure compared the model against the model. It is `else None` now, which is what
the adjacent line already did.

Fixing `prediction_service` alone would not have changed the published number.
Step 5's point prediction is overwritten by the forecast curve's point for
`horizon_day`, and `PricePredictor.forecast` rebuilds its own vector per horizon
from `snapshot_ctx` rather than consuming `features`. It had the same defects
independently, on the path that produces the answer: no `flight_number`, so
`curve_identity_is_complete` rejected the key and all fourteen booking-curve
features were NaN for every point on every curve; `"seats_available": np.nan`
hardcoded; no `departure_time`; a `today + timedelta(days=30)` default departure
date, from which every calendar feature and the booking horizon itself were then
derived; its own route-wide 100-row query; and
`snapshot.get("lowest_fare") or snapshot.get("current_price") or snapshot.get("average_fare")`
as the anchor — three substitutions in one expression, of which `average_fare` is a
route-wide mean no passenger can book, and `or` treats `0.0` as absent. All six are
closed. Where a value has no source the method now raises `InsufficientHistory`,
and the refusal names the flight it counted rather than the route: "DEL-BOM 6E 6E101
on 2026-10-01 has 1 recorded price observation(s)".

Verified with two throwaway probes and by extending `test_market_snapshot.py` and
`test_prediction_repository.py`. The snapshot tests are built so the route's
aggregates give a *different* answer than the quoted flight's values — mean seats
38 against the cheapest flight's 4, first non-empty bucket morning against its
21:40 departure — so they cannot be satisfied by reading the aggregates. Eight
snapshot tests, five repository tests, and sixteen probe assertions across both
paths pass.

---

**29. The health endpoint could not report the one failure that mattered, and
there were two of it.** `/health` returned `"status": "ok"` unconditionally. Not
"ok if the model loaded" — the string was a literal in the return dict. A
deployment where every call to `/api/v1/predict` returns 503 because no artifact
passed the leak audit reported itself healthy, so an uptime check watching this
endpoint could never fire on the failure the audit was created to surface.
`status` now derives from whether a model is actually serving: `"ok"` when
trained, `"degraded"` otherwise. Deliberately not a non-2xx status, because the
process *is* serving — flight search, airports and the chatbot do not need the
model, and a load balancer should not pull the instance. The prediction
endpoints refuse on their own.

`"model": "lazy"` was the second wrong answer in the same dict. It was returned
whenever the predictor was untrained, and "lazy" is a specific claim: the model
has not been asked for yet, it loads on first use. But `get_predictor()` runs in
the FastAPI lifespan hook — by the time anything can call `/health`, the load
has already been attempted, and if it failed, §5 recorded why in `load_error`.
The field is now three-valued: `ready`, `failed`, `lazy`. The distinction is
operational — lazy means wait, failed means go and look at the artifacts.

Which brings up the actual ticket. `PricePredictor` has recorded
`refused_artifacts` since §12 (one entry per artifact whose metadata lacks a
clean leak-audit block) and `load_error` since §5, and **neither field reached
any endpoint**. From outside the process, a models directory in which every
artifact fails the audit was indistinguishable from an empty one: `trained:
false`, `training_timestamp: null`, no reason given. That is the difference
between "nobody has trained this yet" and "models exist and this service is
refusing to serve them" — and the refusal is the interesting event. Both fields
are now published by `/health`, `/info` and `/model/metadata`, and `/info` adds
an `unavailable` entry naming the refusal count.

Two more defects surfaced while fixing those. `prediction_horizon` was a
literal in both places it appeared: `3` in `get_system_info`, `0` in
`get_model_metadata` — two endpoints of one service publishing different
answers to "which horizon does the deployed model forecast", neither of them
reading the artifacts. `0` is the one horizon
`booking_curve_definition.MIN_TRAINABLE_HORIZON_DAYS` rules out as a target,
since at horizon 0 the label is the observation's own price. Both now read
`model_registry.prediction_horizon`, the shortest horizon actually loaded, which
is the same value `prediction_service` uses to pick the published point.

And `main.py` carried a **second** `/health` implementation — same fields, same
hardcoded `"ok"`, plus a `version` key the router's copy did not have. Render's
health check points at the unprefixed one, so the copy deciding whether a deploy
counted as live was not the copy anything else read. It delegates now and adds
only the extra key.

The frontend was reading the old contract. `healthCheck()` in `lib/api.ts`
dropped `model_load_error`, `refused_artifacts` and `degraded_capabilities` on
the floor, and `app/settings/page.tsx` rendered `status === "ok" ? "ONLINE" :
"OFFLINE"` — which, with `status` now honest, would have labelled a reachable
backend OFFLINE. Connection state and model state are separate rows on that
page; the first now tracks reachability (three states, including the
client-side `offline` sentinel), the second the three model states, and a panel
below lists the load error and each refused artifact.

Which exposed the consumer side of addendum findings S-4 and S-5, whose backend
half this section also closes. Every field on the system-info surface used to
carry a hardcoded fallback — `dataset_size` 4216 or 7103, `training_timestamp`
`"2026-07-20T12:00:00Z"`, `feature_count` 18, and
`mae 481.0 / rmse 921.0 / mape 5.04 / median_ae 320.0 / r2 0.9855` against a real
measured R² of 0.425. Worse, `get_model_metadata()` floored the figure it
published: `if training_samples < 5000: training_samples = max(raw_samples,
7103)`, so any genuine training set smaller than 5,000 rows was reported to the
API as at least 7,103. None of those numbers came from a measurement. They are
gone; unknown is `null`, and an `unavailable` list names which fields are null
and why, so a caller can tell "not measured" from "measured as zero".
`_feature_count()` counts the model's actual feature list or returns `null`.

`getModelPerformance()` then declared `mae: number` while returning
`d.validation_metrics?.mae`, so with the literals gone absence arrived as
`undefined` and `perf?.mae || 0` drew it as ₹0 MAE and R² 0.0000 — a measurement
of a very bad model rather than the absence of one. Every metric is
`number | null` now and renders as "not measured". The same page's Policy
Enforcement card was four literals: two green "ENFORCED ✓" ticks, a typed
`feature_set_v1`, and "LIVE_SEARCH MCP STREAM" as the data source. They rendered
identically on a deployment with no model, no validation report and no data.
Each row now shows a measured value — refusal count, `validation_status`
(`UNAUDITED` when no report exists on disk), the real `feature_set_version`, and
`/health`'s `data_source`, which replaced `"SKYMIND_INTELLIGENCE"` (a product
name, not a source) with `trained_model` / `none`.

`test_system_hardening.py` asserted `body["status"] == "ok"` — a test that
passed *because* the literal was there, and would have kept passing on a
deployment serving nothing. It now asserts the coupling,
`(status == "ok") == (model == "ready")`, which holds in both states without
needing a trained model. Four tests were added: the two `/health` endpoints
return the same body modulo `version` and `time`; a patched refusal is visible
through all three endpoints; `lazy` is reported only when nothing failed; and
both `prediction_horizon` fields equal `model_registry.prediction_horizon`.

**Verification gap, stated plainly:** these five tests are compile-checked
only. `fastapi` is not installed in the environment I am working in, so
`TestClient(app)` cannot be constructed and nothing in
`test_system_hardening.py` can execute here. The frontend half is verified —
`tsc --noEmit` passes clean over the whole project. Run
`pytest backend/tests/test_system_hardening.py` in your venv.

---

## Found and recorded, not yet fixed

These are real, located, and left alone deliberately — mostly because the
one-line repair would produce a number rather than a correct one.

**`is_live` is a constant — reviewed and closed as of §36, on the reasoning
rather than by an edit.** This entry used to read that `is_live` is hardcoded
`True` at four sites and that the two consumers disagree about the corpus. Both
halves needed correcting. The four sites are three, one of the cited paths
(`services/prediction_features.py`) does not exist in this repository, and each
surviving site is correct where it stands: `ingestion_controller.format_payload`
writes market observations from the live search path and nothing else, so the
flag is a property of the function (now stated as such, beside `is_synthetic:
False`, pointing at `domain/provenance.py`); `flight_search_service.py:217` is a
serve-time feature value for a fare that just came back from the provider; and
`price_model.py:1915` defaults the column to `True` when building a prediction
frame, which is exactly train/serve parity, because the training corpus is
filtered to `is_live IS TRUE` and therefore contains no other value. Forcing
anything else there would introduce skew, not remove it.

The consumer half is closed for real. `database.py` derives its predicate from
`PROVENANCE_SQL` and `PROVENANCE_IS_FILTERS`, and `training_eligibility.py:53`
calls `has_authentic_provenance` — both from `backend/domain/provenance.py`, which
is now the single definition. The two paths cannot disagree about what the corpus
is without the shared module changing.

What remains, and it is a data property rather than a code defect: because the
column is a constant on the write path and a filter on the read path, it partitions
nothing. It earns its place only once a second ingest path exists that can write
`False`.

**`snapshot_id` is minted twice and never joined.**
`flight_search_service.py:209` and `scheduler.py:122`/`149` each generate one, so
rows from the same search can carry different snapshot identities and nothing
ever joins on the field.

**Deduplication is incomplete.** `deduplicate_session_aware` omits `cabin_class`
from its key, so an economy and a business quote for the same flight collapse
into one. There is no in-batch dedupe and no `on_conflict` on the write
(`flight_search_service.py:321-361`); the unique index is authored as STEP 7 of
migration 001 and deliberately gated on the writer-side dedupe landing first,
because adding it now would start rejecting batches.

**The training corpus is publicly readable.**
`CREATE POLICY "pub_ph" … USING (TRUE)` at `skymind_complete.sql:606` grants
anonymous SELECT on `price_history`.

**An unseeded airline or airport fails the whole batch** with Postgres 23503 —
one unknown carrier discards every row written with it.

**Provenance defaults to real.** `live_search.py:106` defaults the provenance
field to `"REAL_PROVIDER"`, which is the wrong direction for a default: an
unlabelled row should be suspect, not trusted.

**Loose ends.** `app/flights/page.tsx:45` holds a dead `dataSource` state;
`routers/notifications.py` is never mounted; `hash_otp`
(`services/notifications.py:364`) is an unsalted SHA-256 of a six-digit OTP, so the
whole keyspace is a million precomputable hashes; the frontend's `ApiError` reads
`body?.detail` (`lib/api.ts:148`) while the backend sends
`{success, error:{code,message,details}}`; `POST /booking/create`
(`routers/booking.py:159`) has no auth dependency; `GET /flights/airports` returns
`{"airports": []}` with HTTP 200 on exception (`routers/flights.py:156`);
`requirements.txt` pins with `>=` only; and `main.py:7`'s `sys.path.append` can go now
that the boot path is package-qualified.

Two entries that were here are closed. `get_predictor()` no longer trains on load
failure — see §5 and the docstring at `ml/price_model.py:2291`, which records why
training inside an import was wrong three separate ways. And
`fare_forecast_7d.pkl` having no `metadata.json` is moot: `backend/ml/models/` now
contains nothing but `quarantine/`, because §12 moved every shipped artifact there
and `load()` refuses any file without a clean leak-audit block. Horizon 7 does not
load, and that is now the designed outcome rather than a silent one.

A third is closed as of §35. `PolicyLoader(file_path="policy.yaml")` at
`routers/chat.py:32` was listed here as a CWD-relative path, the same defect as §9.
It was worse than a path bug: the loader's response to a missing file was a policy
with no rules, which made the firewall's decision unconditionally `is_safe`. There
was a second copy at `services/agent_graph.py:59`. Both are fixed.

**30. Running the test suite rewrote four tracked files, and the reports it
rewrote were graded by a gate that could not fail.** Executing
`backend/tests/` overwrote `historical_data_report.json`, `drift_report.json`,
`feature_validation_report.json` and `production_readiness_report.json` — four
files at the repository root, all four tracked. The sweep on 2026-09-01 is the
proof: the committed `historical_data_report.json` read
`total_observations: 1000, status: "PASS"`, and after the run it read `0` /
`"FAIL"`. Not a stale build artifact left lying around — version-controlled
content edited by the act of testing, in a repository where those four files are
the only machine-generated evidence a reviewer is likely to open.

One anti-pattern, copied four times. Each service computed its destination as
`os.path.join(os.path.dirname(sys_dir), "..", "<name>.json")`, which resolves to
the repository root. That is `__file__`-anchored, which is precisely what
`.gitignore`'s existing `backend/backend/` tripwire comment asserts makes this
class of bug impossible — so the lesson needed extending rather than applying:
anchoring is not enough when the anchor points at tracked content. Nothing in the
codebase reads any of the four reports; they are write-only. So the fix is to
redirect them rather than to preserve them. `backend/utils/report_paths.py` now
owns one `REPORTS_DIR` (`backend/reports/`, gitignored) and one `write_report()`,
each writer takes an optional `destination`, `run_full_validation` takes a
`report_dir` that redirects all four at once, and the tests pass `tmp_path`.
`write_report` records `report_written_to` in the dict *before* the dump, so the
file on disk and the value handed back are the same document and a test can
round-trip one against the other; a failed write swaps that key for
`report_write_error` rather than raising.

Then the reports themselves. `historical_data_audit.run_audit` measured five
things — observation count, missing-cell percentage, duplicate percentage, route
coverage, curve density — and gated on two. Duplicates, coverage and density were
computed, written into the artifact, and never consulted, and there was no FAIL
branch for a non-empty frame at all: the only way to fail was an empty database.
The committed report is the demonstration, reading
`duplicate_observation_percentage: 20.0` beside `status: "PASS"`. Every published
figure now carries a named bound, a breach appends a sentence naming it to
`failed_bounds`, and `status` derives from whether that list is empty.

`booking_curve_density_avg` was the second defect in the same method:
`total_obs / route_count`, which is observations per **route**, published under the
name of observations per **booking curve**. A route carries many flight numbers
across many departure dates, so the committed `125.0` overstates real per-curve
density by however many curves those eight routes contain — and per-curve depth is
exactly the quantity that decides whether a booking curve can be fitted at all. It
is now counted over `BOOKING_CURVE_KEYS` through `curve_group_columns()`, the same
grouping the training set uses, and both figures are published side by side as
`observations_per_booking_curve_avg` and `observations_per_route_avg` so the
difference is visible instead of collapsed.

`production_readiness` was fabricating a diagnosis. For any non-PASS audit status
it appended the fixed string `"Historical Data Audit: Partial coverage or
duplicate observations"` — including on the empty-database path, whose actual
recorded reason is "Database returned no records". A rollup that invents the reason
for a subsystem's failure is worse than one that omits it, because the invented
reason is plausible and sends the reader to the wrong place. It now quotes the
audit's own `failed_bounds` or `reason`, and zero observations escalates from a
warning to a failure, since there is nothing there to be ready with.

`feature_validation`'s `determinism_verified` field was the literal `True` on every
run, and the module docstring claimed the module verifies determinism. It cannot:
`validate_features_dataframe` receives an already-built frame, so it has no way to
build the features a second time and compare. The field is now `None` with a
`determinism_check` string saying why, which matters because `production_readiness`
copies this report into its own output verbatim — the claim travelled. The same
method's empty-frame path returned without writing anything, so on an empty corpus
the report file kept whatever the previous run had left there: a stale PASS
describing a frame that no longer existed. An empty frame is a result, and it now
gets an artifact like any other.

Two of the tests meant to catch all of this could not. `test_production_readiness`
asserted `os.path.exists(<repo-root>/production_readiness_report.json)` — a check
that cannot fail for its stated reason, because that path is a tracked file and
exists before the test starts. It would have passed had the run written nothing at
all. Instead it passed for the wrong reason: the run really did write there, which
is how the tracked reports were being edited in the first place. And
`test_drift_detection` asserted `0.0 <= report["feature_drift_score"] <= 1.0`,
which raises `TypeError: '<=' not supported between 'float' and 'NoneType'` on the
`UNMEASURABLE` report §19 taught that service to publish — so the refusal the
service was corrected into making surfaced as a test error rather than as the pass
it is. The five modules go from one test each to five, three, three, three and one
strengthened; all eleven pass, and the skips quote the subsystem's own stated
reason for being unable to measure rather than asserting a bound on data that is
not there. A full run afterwards leaves `git status` clean on the four tracked
reports and creates no `backend/reports/` at all, which is the measurement that
every writer honoured the destination it was given.

One step here is yours. The `.gitignore` entry stops these four reports being
regenerated inside the tree, but it does not untrack the copies already committed —
`.gitignore` has no effect on a tracked path. Their content is a single snapshot of
a synthetic-corpus run from 2026-07-27, timestamped within 1.2 seconds across all
four, and `production_readiness_report.json:3` reads `"overall_status": "FAIL"`,
which `AUDIT.md` already flags as among the first things a reviewer opens. Untrack
them with `git rm --cached historical_data_report.json drift_report.json
feature_validation_report.json production_readiness_report.json`.

**31. A pandas warning that was on the list as cosmetic was dropping rows at
eleven call sites and crashing at five others.** Postgres renders a `timestamptz`
without the microseconds field when it is zero, and Python's
`datetime.isoformat()` does the same. So every timestamp column in this project
holds two shapes at once — `2026-08-15T10:00:00.123456+00:00` from one writer and
`2026-08-15T10:00:01+00:00` from the next — and `pd.to_datetime` with no explicit
`format` infers a *single* format from the first non-null element and applies it
to the whole column. What that does depends only on `errors`. With
`errors="coerce"` every element of the other shape becomes `NaT`. With the
default `errors="raise"` the call raises
`ValueError: time data "2026-08-15T10:00:01+00:00" doesn't match format
"%Y-%m-%dT%H:%M:%S.%f%z"`. One defect, silent row loss at the sites that coerce
and a production crash at the sites that do not.

The warning is inverted, which is why this looked cosmetic.
`UserWarning: Could not infer format, so each element will be parsed
individually` is emitted on the **safe** path: pandas warns precisely when
inference *failed*, and having failed it parses per element and gets every row
right. The dangerous case emits nothing at all — inference succeeded, pandas was
confident, and confident is what made it lossy. A warning that fires only when
nothing is wrong is worse than no warning, because silencing it is the natural
response and silencing it here means picking the format inference guessed.

Measured on pandas 2.3.3: `pd.to_datetime(pd.Series([WITH_MICROS,
WITHOUT_MICROS]), errors="coerce", utc=True)` returns one timestamp and one
`NaT`.

Where a `NaT` landed. `database.get_training_dataset` sorts on `recorded_at` and
the booking horizon is measured from it, so a coerced row lost both its position
in the curve and its horizon. `booking_curve_definition.ordering_timestamps` is
the shared observation axis that `DatasetSplitter`, `TimeSeriesCrossValidator`
and `chronological_split` all order by — the axis §25 exists to make single.
`dataset/snapshot.py` writes `snapshot_time` itself with `observed.isoformat()`
and then could not read back the rows it had just written, dropping them into its
own `unorderable` branch. `dataset_quality_validator` computed temporal coverage
and duplicate rates over the survivors. On the raising side:
`time_series_plugin`'s chronology assertion and four parses in
`booking_curve_validator`, all with `errors` at its default, so real mixed data
would have taken down a validation run rather than shrinking one.

Sixteen call sites across eight files now pass `format="ISO8601"`, which accepts
both shapes without guessing. Six production sites deliberately do not, which
accounts for all twenty-two `pd.to_datetime` calls outside `backend/tests/` —
none was left unexamined. `departure_time` at `database.py:354` and
`temporal.py:162` holds `"HH:MM"` strings that ISO8601 rejects (measured:
`["10:30", "10:30:00"]` gives two `NaT` *with* the format and parses fine
without it). `recorded_date` at `temporal.py:121`, `dataset_splitter.py:279` and
`cross_validation.py:160` holds `datetime.date` objects, one shape, so inference
loses nothing — and the latter two are fallbacks that only fire when the shared
axis is absent, so a mixed-precision column cannot reach them.
`forecast_evaluation_scheduler.py:96` parses a scalar, and a scalar has no second
element to be inferred against.

`format="ISO8601"` alone was not enough, and probing before editing is the only
reason that did not turn a silent `NaT` into an `AttributeError`. On a column
mixing a bare date with a full timestamp — `["2026-08-20",
"2026-08-21T00:00:00Z"]`, which is exactly what `departure_date` holds, since one
writer stores the date the user asked for and another stores a parsed instant —
the format alone returns **object** dtype, and `booking_horizon_days` does
`getattr(departs.dt, "tz", None)` two lines further on. All three
`departure_date` sites therefore pass `utc=True` as well; with it the result is
`datetime64[ns, UTC]` for every input shape measured — bare dates, timestamps,
`datetime.date` objects, all-null, and empty — and the existing branch strips the
tz, so a naive input lands on the value it had before. On that mixed pair the
horizon went from `[5.0, nan]` to `[5.0, 6.0]`.

ISO8601 cannot lose a legitimate `departure_date` in exchange, because all nine
entry points validate the field as `"%Y-%m-%d"` before it reaches a frame
(`routers/predict.py:38`, `routers/live_search.py:43`, `dataset/dates.py:31`,
`temporal.py:213`, `flight_search_service.py:160` and `:451`,
`ingestion_controller.py:70` and `:234`, `prediction_service.py:98`). Measured:
`"15/08/2026"` is `NaT` with the format and without it.

One near-miss worth recording, because it is the more expensive kind of mistake.
In `time_series_plugin` I first replaced the string sort with a parsed one —
`pd.to_datetime(group[ts_col], ...).sort_values()` — and the next line asserts
`times.is_monotonic_increasing`, which is trivially true of a series you just
sorted. That would have left a green check that could never fail again, which is
strictly worse than the crash it was fixing. Reverted to the minimal change: keep
`sorted_group = group.sort_values(by=ts_col)`, add only the format, and leave
`errors` at its default so a value that is not ISO-8601 at all still fails loudly.
When the bug is a crash, fix the crash and do not touch the assertion being
protected.

`backend/tests/test_mixed_precision_timestamps.py` covers it, and its first test
asserts the pandas behaviour itself — `inferred.isna().sum() == 1` — so if a
future pandas stops inferring, the module fails rather than quietly testing
nothing. The rest check that the shared axis keeps both shapes, that the row-level
and frame-level definitions agree on both, that a horizon comes back for both,
that a mixed `departure_date` column yields `[5.0, 6.0]`, and that every snapshot
gets a sequence number. Proven not born green: patching `pd.to_datetime` inside
`booking_curve_definition` and `snapshot` to strip the `format` kwarg fails 6 of
the 6 non-premise cases, and the snapshot module logs its own production
consequence while doing it — `[snapshot] 1 of 2 row(s) carry no usable
observation time; their snapshot_sequence is left null rather than assigned by
frame order.` Six pass and one skips in this workspace; the skip is the
parametrized case, which needs real `pytest`, and both of its columns were
checked by hand.

**32. `backend/scratch/` was fifty tracked files, and the application depended on
two of them.** The audit recorded six probe scripts. The directory held fifty, and
every one was tracked: one-off DB probes, hand-written `ALTER TABLE` scripts, a
613 KB scraped-payload dump, eight UTF-16LE PowerShell captures, and about twelve
`test_*.py` files sitting outside `backend/tests/` where `pytest.ini`'s
`testpaths` would never collect them — two of which have side effects,
`test_noir_email.py` sending mail and `test_mcp_call.py` driving the scraper.

Two of the fifty matter beyond tidiness. `ingest_mock_data.py` is the script that
wrote the synthetic corpus the ML results turned out to be measuring —
`AUDIT.md:90` quotes its `price = float(random.randint(25000, 55000))` — so the
mechanism behind the headline finding was sitting in version control the whole
time. And `alter_price_history_provenance.py` defaulted `DATABASE_URL` to a string
byte-identical to the live DSN in `backend/.env`, in a file whose only job is to
run DDL against `price_history`; an unset environment meant silently issuing
`ALTER TABLE` against production. Its DDL is now migration 001, which also
records why its own corrective `UPDATE` matched zero rows.

Grepping for references before deleting found two live dependencies, and both
were rehomed rather than removed. `services/eval_logger.py` — production code,
reached from the chat path — appended its runtime evaluation log to
`backend/scratch/evals/chat_evaluations.jsonl`, and 21 KB of that log was
committed. A served application writing an append-only log into tracked content is
§30's defect in a different directory; it now writes to `REPORTS_DIR/evals`, which
is gitignored. And `test_booking_curve_pipeline.py:453` imported
`backend.scratch.run_validation_dashboard`, so the shipped test suite depended on
a directory named scratch. That file is an operator entry point, not a probe, and
it moved to a new `backend/tools/` package whose `__init__.py` states the
distinction: a command a person runs, not a module the application imports.

Moving it exposed a bug of its own. Its `sys.path.append` was
`dirname(dirname(__file__))`, which from `backend/scratch/` resolves to
`backend/` — one level short of where the `backend` package is importable from.
Every `import backend.<...>` below it worked only because the process happened to
be launched from the repository root. Measured: appending the old path and
importing `backend.database.database` from `/tmp` raises
`ModuleNotFoundError: No module named 'backend'`; with the third `dirname` the
script runs from `/tmp` and reaches its own empty-dataset guard. The frontend's
admin page was telling operators to run the old path in its error state, so it was
pointing at a script that would have died on line 11 from most working
directories.

Four stale cross-references were corrected rather than left to rot:
`ml/price_model.py`'s note that `validate_target_leakage` had no production
caller, migration 001's provenance narration (which also cited
`database/database.py:101` by line number, now `domain.provenance.PROVENANCE_SQL`
by name, since the line had already moved), the admin page's command, and CI's
credential-gate comment. That last one is load-bearing prose: it is the reason the
gate decodes every tracked file in Python instead of using `grep -lEI`. `grep -I`
skips any file containing a NUL byte, and nine tracked files had them — the eight
PowerShell captures plus `backend/test_ticket.pdf` — so the check that exists to
find a leaked JWT structurally could not read the nine files most likely to be an
unreviewed dump of one. Deleting the eight leaves one, which is why the comment
now says the hole is not a function of how many exist: the next binary, UTF-16 log
or archive would reopen it.

`backend/scratch/` is now in `.gitignore`, so `git add -A` cannot re-track it, and
the five remaining mentions of the path in the tree are all deliberate history.
Everything this fix pass deleted is copied under `.archive/` — also gitignored,
with a `README.md` naming each archive — so "removed" does not mean
"unrecoverable" while you are still reviewing. While the deletions are only in the
working tree, git is the better recovery route anyway: every removed path is still
staged as an addition in your index, so `git show
:backend/scratch/ingest_mock_data.py` prints the original.

Two steps here are yours. Forty-eight of the fifty paths read `AD` in
`git status` — staged as additions, absent from disk; the other two were created
after your `git add -A` and were never in the index — so run `git add -A` before
committing. A bare `git commit` would still include the forty-eight. And
`.gitignore` cannot untrack the log that moved:
`git rm --cached backend/scratch/evals/chat_evaluations.jsonl`.

**33. Booting the API found a 500 on the one endpoint whose job is to report that
no model is loaded.** You ran `python -m uvicorn backend.main:app` against your own
tree and walked the system endpoints. Four of them behaved: startup printed the
refusal — `No prediction model is available: load failed (FileNotFoundError...).
Not training a replacement` — `/health` returned `degraded` with `model: failed`,
`degraded_capabilities: [price_prediction, fare_forecast]` and `data_source: none`,
`/info` returned `trained: false` with an `unavailable` map naming each null, and
`/version` returned its three version fields. `/api/v1/system/model/metadata`
returned HTTP 500.

The cause was one line. `get_model_metadata` read the metrics through
`predictor.get_performance()`, which calls `ensure_ready()`, which calls `load()`,
and `load()` raises `FileNotFoundError` when no artifact on disk is loadable. So
the endpoint that exists to describe the model's state raised on precisely the
state it exists to describe, while every remaining field in its own response —
`trained`, `model_load_error`, `refused_artifacts`, `unavailable` — is purpose-built
for "no model". `get_system_info` survived the same condition only because it reads
everything through `getattr`.

That matters beyond the status code. A 500 makes a designed refusal
indistinguishable from a crash to anything watching the API: one endpoint reported
this deployment as `degraded`, another as `trained: false` with a reason, and the
third as a server fault. The fix gates the metrics read on `_trained`. Because
`ensure_ready()` returns immediately when `_trained` is set, gating on it provably
cannot reach `load()`, so the remaining `try/except` is for a genuinely unexpected
read failure — a truncated artifact, say — and that is named in `unavailable`
rather than swallowed. The missing-metrics message also stopped asserting a loaded
model; it now distinguishes "no model is loaded, so there are no evaluation
metrics" from "reading the loaded model's metrics failed (`<exception>`)" from
"not present in the loaded model's evaluation metrics".

Worth being plain about why no check caught it: nothing in this repository had ever
executed that path. `backend/tests/test_system_hardening.py` imports
`fastapi.testclient`, and the environment I verify in has no fastapi, so the module
is a collection error there rather than a run; CI has never executed the suite at
all. And the existing test three functions above the new one already sets
`_trained = False` and calls `/api/v1/system/model/metadata` — it would have caught
this the first time it ran. A regression test is appended,
`test_model_metadata_reports_a_missing_model_instead_of_returning_500`, which
asserts the 200, the null metrics, the exact `model_load_error` string, and that
`/health`, `/info` and `/model/metadata` describe the one condition the same way.
Run it on your machine, where the dependencies are real:
`pytest backend/tests/test_system_hardening.py -v` from the repository root.

**34. The audit report the API serves was computed six weeks before the fix pass.**
The same live run surfaced a second thing, which is not a bug in the code and is
why it sits here rather than in a diff. `/api/v1/system/validation/latest` returned
a real report — `overall_status: FAIL`, `readiness_score: 70`, chronology,
duplicates, leakage and health `PASS`, coverage `WARNING`, target_quality `FAIL` —
and `/info` reported the same verdict through `validation_status`. That report is
stamped `2026-07-22T08:03:22.883416+00:00`. Every fix in this log is dated August
and September.

So the score the API publishes was produced by the pre-fix pipeline, by the same
readiness checks §9 and §30 found were computing verdicts from hardcoded sample
payloads and rewriting tracked files as a side effect. Its `coverage: WARNING` was
computed before §31 fixed the sixteen timestamp-parsing sites that were dropping
rows, and its `target_quality: FAIL` before the forecast path was made to refuse
rather than invent. The verdict may well still be FAIL — on ~1,026 genuinely live
rows it probably should be — but nothing in that payload is evidence either way,
because it is not a measurement of the code you are running.

Regenerate it and read the new one. The response already carries `timestamp`, so
nothing needs building to make the staleness visible; it needs looking at. Until
then, treat `readiness_score: 70` the way you would treat any number whose
provenance you cannot vouch for in an interview: as a figure you have to explain
**35. The chatbot firewall detected violations and allowed all of them through.**
The same boot log carried a line that reads like configuration noise:

    Policy file policy.yaml not found. Using default policy.

It was not noise. `routers/chat.py:32` and `services/agent_graph.py:59` both
constructed `PolicyLoader(file_path="policy.yaml")` — a path relative to the
process's working directory. The only launchable form of this app is
`python -m uvicorn backend.main:app` from the repository root, and the policy file
is `backend/policy.yaml`, so the path resolved to a file that has never existed, on
every launch since the loader was written.

What happened next is the defect. A missing file substituted `PolicyConfig()`:
`default_action: ALLOW`, `rules: []`. `RuleEngine.evaluate` then leaves
`final_action` at the default and computes `is_safe = final_action != BLOCK`, so
`is_safe` was unconditionally `True` — and `routers/chat.py:65` gates interception
on `if not firewall_decision.is_safe`. The guardrails still ran, still returned
UNSAFE, and still populated `decision.violations`; `AuditStage` still recorded the
violation. Then the request proceeded. The four shipped rules that do the
blocking — `jailbreak_block`, `content_block`, `topic_block`, `high_risk_block` —
were loaded in no deployment. A firewall that detects and permits is worse than no
firewall, because the audit trail says it caught something.

`PolicyLoader` now resolves `backend/policy.yaml` from its own `__file__`, and both
call sites pass no path at all. `governance/engine.py` had already been right on
both counts — it resolves from `__file__` and its missing-policy path falls through
to `action = "REFUSE"` — which is why the domain-governance layer was intact while
the firewall layer was inert. An absent or unparseable policy is now refused at
construction rather than replaced with a permissive one. A *later* hot-reload
failure keeps the last policy that did load, which is the behaviour that was
already correct; a file that exists and declares zero rules warns loudly instead of
raising, because unlike an absent file that is an operator's explicit choice.

Measured on the shipped tree: the default resolves to `backend/policy.yaml` and
loads all five rules, no `policy.yaml` exists at the repository root, a missing
path raises `FileNotFoundError`, an empty file raises `ValueError`, a policy edited
into an invalid shape keeps the previous rules *and* the previous non-permissive
`default_action`, and a valid edit is still hot-reloaded.

The test that should have caught this is worth reading, because it was green the
whole time. `test_production_validation.py`'s `test_security_prompt_injection_guardrail`
is documented as "Validates Firewall interception against OWASP LLM01 Prompt
Injection" and asserted exactly one thing: `context.decision is not None`. A
decision object is constructed on every path through the engine, including the path
that waves the request through, so the assertion could not fail for the reason the
test is named after — and it built its loader with the same broken
`file_path="policy.yaml"`, so it was green in precisely the deployment it exists to
rule out. It now mocks the guardrail client, uses the shipped policy, and asserts
that a flagged jailbreak yields `is_safe: False`, that `jailbreak-detect` appears in
`violations`, and that `jailbreak_block` is the rule that fired. Two tests were
added beside it: one that the default path resolves next to the package rather than
to the working directory, and one that a missing or empty policy refuses to
construct instead of admitting everything.

One more thing from the boot log, in the same file family. `firewall/rules/models.py`
carried a Pydantic V1 `class Config` with `allow_population_by_field_name`, which V2
renamed to `populate_by_name`; under the pinned `pydantic>=2.7.0` the old key is
ignored, so the three composite condition fields could only be populated by their
`and` / `or` / `not` aliases, never by field name. That is the
`UserWarning: Valid config keys have changed in V2` line printed on every boot. It
is now `model_config = ConfigDict(populate_by_name=True)`, and the `json_encoders`
entry beside it was dropped — it was keyed by the string `"RuleCondition"` rather
than by a type, so it never matched anything under V1 either. The other V1 remnant,
`governance/models.py:100`'s `json_encoders = {float: lambda v: round(v, 3)}`, was
deliberately left alone: it is deprecated but still functional under V2, and
changing it would change how floats are rounded in telemetry output.

---

**36. The repository named four data sources, four "coming soon" providers and a
provider it has never called.**

Six related claims, all of which an interviewer reaches by opening one file.

`services/flight_data_provider.py` defined four provider classes.
`GoogleFlightsProvider` works. `AmadeusProvider` ("Amadeus GDS Sandbox"),
`SabreProvider` ("Sabre GDS Sandbox") and `CachedProvider` ("Supabase Cache
Provider") were each a single `return []`, referenced by no production module —
the only construction site in the repository is
`market_snapshot_provider.py:69`, `provider or GoogleFlightsProvider()`. Two of
them had contract tests, and both tests asserted that an empty list is an empty
list. Deleted, along with those tests, rather than implemented: there are no
Amadeus or Sabre credentials, and `MarketSnapshotProvider` calls exactly one
provider and has no failover logic a second source could feed. The abstract base
class stays, because `test_market_snapshot_provider.py` substitutes failing and
timing-out doubles for it, which is a real use of the abstraction. A new test
asserts the set of concrete implementations is exactly
`{"GoogleFlightsProvider"}`, so a placeholder cannot come back under a vendor's
name. The Supabase cache is not lost with `CachedProvider`: reading cached
snapshots is `market_snapshot_provider.py`'s own job, done against the database
directly.

**The live path labelled itself `LIVE_MAKEMYTRIP_MCP`.** The transport is
`flight_data_service` → `mcp_client` → `india-flight-mcp/src/mcp/stdio_server.js`
→ `GoogleFlightsProvider.js`, which drives Puppeteer over
`google.com/travel/flights`. It has never been MakeMyTrip; `MakeMyTripProvider.js`
sat in that directory required by nothing until §44 deleted it. The label mattered
because
`flight_search_service.py` passes it to `format_payload` as `provider`, and §28
made `data_source` derive from `provider` — so both provenance columns on every
stored row named a provider this code cannot call. A provenance column holding
the wrong provider is worse than an empty one, because it reads as evidence.
Renamed to `LIVE_GOOGLE_FLIGHTS_MCP` at `flight_search_service.py:448` and
`scheduler.py:293`, with the three assertions in `test_route_catalog.py`. Rows
written earlier keep the old string and nothing filters on the column, so there
is no query to migrate.

**The scraper layer was fabricating four fields, and no previous sweep had read
it.** Every synthetic-data pass over this repository had been Python-only, and
these are in JavaScript, upstream of the normalizer that was audited twice:

- An unrecognised carrier became IndiGo / `6E` (`stdio_server.js`). Not a display
  default — it reached `price_history.airline_code`.
- An unparseable duration became exactly 135 minutes. This is why it survived two
  audits: 135 minutes *is* "2 hr 15 min", the most common real value on these
  routes, so the fabricated figure was indistinguishable from a measured one.
- An unparseable clock time became `{date}T00:00:00` (`GoogleFlightsProvider.js`).
  `departure_time` is now persisted and is the only source of `hour_of_day` and
  `is_peak_hour`, so this fed a midnight departure into two features.
- A card with no stops line was reported as nonstop (`let stops = 0`).

All four now emit `null`. That is safe because `normalize_mcp_flight` already
degrades: a missing carrier becomes `"UNKNOWN"` / `"Unknown Carrier"`, and the
schedule fields are `Optional` on `NormalizedSegment`.

Two further defects in the same file, found while making the time nullable.
`new Date(null)` is the **epoch**, not an invalid date, so the overnight-arrival
guard compared `0 <= 0`, called it overnight, and published a 1970-01-02 arrival.
And it re-emitted the corrected value with `.toISOString()` while the departure
stayed naive-local: measured under `TZ=Asia/Calcutta`, a 23:10 departure with a
01:25 arrival produced `2026-09-05T19:55:00` — the wrong calendar day, and 5h30m
*before* the departure the handler existed to fix. The arithmetic is now done on
the date half only, and yields `2026-09-06T01:25:00`.

**`FlightAggregator.js` could not be imported at all.** It required seven
providers; five of those files (`CleartripProvider`, `EaseMyTripProvider`,
`YatraProvider`, `GoibiboProvider`, `HappyFaresProvider`) have never existed, so
`require` threw `MODULE_NOT_FOUND` before the class body — which broke
`src/server.js`, `src/mcp/tools.js`, and `src/mcp/server.js`, the one `npm start`
runs. Measured: `MODULE_NOT_FOUND` before, `LOADED` after requiring only the
provider that exists. The nested `README.md` listed those same five as "coming
soon" and claimed bank-offer parsing, which for the wired provider is
`getOffers() { return []; }`; it now documents one provider, three entry points,
and which single one the backend actually spawns.

**`format_payload` had an `is_synthetic` parameter no caller passed.** It was
worse than dead: the returned dict hardcoded `is_live: True` beside
`is_synthetic: bool(is_synthetic)`, so a row written through it would have carried
both flags true at once — a contradiction `has_authentic_provenance` rejects on the
first condition while the SQL loaders' second condition calls it live. The function
writes market observations and nothing else, so both flags are now constants of the
function, pointing at `domain/provenance.py` as the single definition.

`docs/FLIGHT_SEARCH_AUTHENTICITY_AUDIT.md` was the document that would have been
read alongside all of this, and it was stale in three ways and wrong in a fourth.
It attributed the live path to MakeMyTrip; it quoted two `data_source` strings
(`ZERO-BIAS CACHE`, `ERROR RECOVERY`) that appear nowhere in the source; it
attached confidence scores of 95.0% / 75.0% / 60.0% to the three search paths when
`flight_search_service.py` contains the word "confidence" zero times — those three
figures are the shape of the defect `confidence_policy.py` exists to prevent; and
it credited the search path with `MarketSnapshotProvider`'s 300 s TTL, which
belongs to the prediction path. Its top recommendation was to **synthesize
spread-out departure times by flight index** — a recommendation to fabricate the
exact field the audit was written about, and one that would have been more
convincing than `T12:00:00` and no less invented. The document now carries a status
line, a FIXED/OPEN mark per finding, and that recommendation recorded as rejected
with the reason.

One thing recorded rather than changed: `training_weight` is written as the
constant 2.0 and consumed as the XGBoost sample weight
(`model_trainer.py:248`, `price_model.py:1105`), so the column expresses no
weighting scheme while looking like one. Stored rows carry 2.0, so writing 1.0 for
new rows would weight the older, partly-seeded block twice as heavily as newly
observed fares. Either define a real scheme or drop the column; do not change the
value alone.

**Verified in this environment.** `py_compile` passes on all seven touched Python
files. `node --check` passes on the six touched JS files, and both previously
unloadable modules import. A probe through `format_payload` returns
`provider = data_source = LIVE_GOOGLE_FLIGHTS_MCP`, `departure_time` normalised to
`2026-09-20T06:05:00`, `flight_number` `None` and absent from the DB payload. A
probe through `confidence_policy` returns `None` for an unmeasured model, `42.0`
for a model measured at 42 (no 70 floor), and `40.0` both for the worst live-market
quality and for no live market at all — the ordering that makes losing a data
source unable to raise published confidence. `routes.yaml` still parses.
`pytest backend/tests/test_flight_data_provider.py` and
`pytest backend/tests/test_route_catalog.py` need your venv; `fastapi` and
`pydantic` are not installed here.

**One thing you need to know before you commit.** `backend/india-flight-mcp` has
its own `.git`, and `git ls-files -s backend/india-flight-mcp` returns nothing —
the parent repository does not track a single file in it. Every JavaScript fix in
this section is on disk and will run, and **none of it will be in your commit.**
That directory is already on your list to resolve (submodule or vendor); until you
do, those fixes exist only in your working tree.

---

**37. The frontend could not reach the API at all, and the refusal named no reason.**
Found in your own boot log: six `OPTIONS … 400 Bad Request` lines against
`/api/v1/predict` and `/live-search`, with no `POST` following any of them. A 400
on an `OPTIONS` request is Starlette's `CORSMiddleware` refusing a preflight, and
it refuses for exactly three reasons — disallowed origin, method, or header. The
method (`POST`) was allowed and the only header the frontend sends is
`Content-Type`, which is CORS-safelisted, so the origin was being rejected: no
request ever reached a route, and the browser fell through to `apiRequest`'s
network-error branch.

The allow-list was five hardcoded strings — `localhost:3000`, `localhost:3001`,
`localhost:3002`, `127.0.0.1:3000`, `https://localhost:3000`. `npm run dev` walks
up to 3003, 3004 and beyond whenever a port is held, and `127.0.0.1:3001` was
never on the list at all, so the frontend broke the moment it landed anywhere
outside those five. Replaced with `allow_origin_regex` covering any loopback
origin on any port — `localhost`, `127.0.0.1` and `[::1]` — active only when
`SKYMIND_ENV` is not `production`. In production the regex is `None` and only
`CORS_ORIGINS` is honoured; if that variable is empty in production the API now
logs a warning at startup naming the consequence, rather than refusing every
browser request in silence. The regex is applied with `fullmatch`, so
`http://localhost.evil.com:3000` is refused — verified against nine origins, five
matching and four rejected.

The reason this cost a debugging session is the second half of the finding: the
refusal was **unobservable from the server**. Starlette does write the reason into
the preflight response body, but a browser never surfaces a preflight body, and
the `observability_middleware` in `main.py` logged only paths matching
`predict|system|validation|health` at `INFO` — which, with no `logging.basicConfig`
anywhere in the project, has no handler and prints nothing. The middleware now
logs every 4xx at `WARNING` with the `Origin` header attached, plus
`Access-Control-Request-Method` and `-Headers` when the request is a preflight, so
the next occurrence names its own cause. `time`, `json` and `logging` moved to the
top of `main.py`; they were imported halfway down the file, below the code that
now needs them.

**And the error the user would have seen was the wrong one.** `frontend/lib/api.ts`
read a failed response's message from `body?.detail`, but every one of the three
`@app.exception_handler` blocks in `main.py` emits
`{success:false, error:{code,message,details}}` — a shape with no `detail` key. So
every backend error, on every path, reached the UI as the bare fallback string
`Request failed — HTTP 500`, and the message the API had composed was parsed and
thrown away. It now reads `body?.error?.message` first and keeps `body?.detail`
second, because a `HTTPException` raised before those handlers run still uses it.

`SKYMIND_ENV` is documented in `backend/.env.example` alongside `CORS_ORIGINS`. It
is the first environment flag in the project; there was no way to ask "is this
production?" before it.

---

**38. The metadata endpoint published a horizon for a model that does not exist.**
Visible in the boot log the moment CORS was fixed and requests started arriving:
`Predictor PricePredictor has no loaded horizon, so none can be reported as the
prediction horizon; returning the smallest declared horizon (1d).` That warning
was written by `model_registry.prediction_horizon`, and directly beneath it
`GET /api/v1/system/model/metadata` answered `200 OK` — publishing
`prediction_horizon: 1` alongside `trained: false`, a populated `model_load_error`
and an `unavailable` list. A horizon is a claim about an artifact. With no artifact
there is no claim, and `1` was the same fabrication as a 12:00 departure time on a
row that never carried one, arriving through the same mechanism: a schema was
believed to demand a value, so one was invented.

The justification was in the docstring — the smallest declared horizon "is
returned so the response model still gets an int" — and it was false. Both
consumers are `Dict[str, Any]`: `/model/metadata` and `/info` are annotated as
plain dicts and neither declares a response model, so nothing anywhere required an
int. The property is `Optional[int]` now and returns `None`, the endpoint publishes
`prediction_horizon: null`, and the warning no longer names a substitute it is not
making.

`prediction_service` resolves that horizon once and uses it three times — the
`predict()` call itself, the forecast point that becomes the published
`predicted_price`, and the accuracy figure printed beside it. It now raises
`PredictionUnavailable` if the horizon is `None`, which the router maps to 503. The
branch should be unreachable, because the guards above it refuse first; it exists
because the *previous* behaviour would have silently predicted at 1d and labelled
the response 1d with nothing loaded to predict with. Two tests asserted the old
substitution (`== 1` for an empty registry, `> 0` on the live one) and now assert
`is None` and `is None or > 0`.

---

**39. The tool that answers "can I train yet?" fabricated its own patient, then
graded a test fixture.** `backend/dataset/doctor.py` is what an operator runs
before a training run. When there was no export on disk and
`database.get_training_dataset()` raised, it built a one-row frame from literals
in its own source — `DEL→BOM, 2026-08-15, ₹4500, 6E101, days_until_dep=30` — ran
six checks against it, and printed `DATASET DOCTOR RESULT: PASS (Dataset v2.0 is
100% production-ready for ML)`. That row satisfies every check it was graded by,
because both the row and the checks were written in the same file. A diagnostic
that invents a patient reports on the invention.

There was a second copy of the same row on disk, and it got there from the test
suite. `test_dataset_exporter_and_quality_report` called
`dataset_exporter.export(df, output_dir="backend/dataset/exports")` — the real
export directory, the one the doctor reads by default. So `pytest` wrote a
707-byte `flight_price_dataset_v2.0.csv` holding that single fixture row into the
repository, beside a manifest recording `total_rows: 1` and a quality report
saying `validation_status: PASS`, and all three were staged for commit. The test
immediately after it ran the doctor over that file and asserted
`code in (0, 1, 2)` — every value the function can return, so it held whatever
the tool decided. The readiness answer, the artifact it read, and the test that
checked it were all self-generated.

`_load_corpus` now raises rather than fabricates: an absent named file, an
unreachable corpus, and a corpus that returns no eligible rows are each reported
as the finding. A zero-row frame is a FAIL rather than a vacuous pass — it is the
same shape as an R² of 1.0 over an empty fold, where no counter-example found is
not evidence. The verdict names the corpus it graded, where it came from, how
many rows it had, and what the checks reach: it is a data-integrity verdict, not
the model-readiness one it used to claim, and it says so and points at the
acceptance gate.

The check that was missing is the one that decides the question. None of the six
looked at booking-curve shape, and a row can only carry a supervised label if its
own curve holds a later observation — so a corpus of one-observation curves
yields zero training rows however many rows it has. `booking_curve_shape()` is
lifted out as a function so it can be asserted on directly, and reports
`rows_on_multi_observation_curves` as an explicit **upper** bound on trainable
rows: a row also needs its later observation to fall at or after `t + horizon`,
which this does not check. An upper bound is the useful direction, because when
it is already below `TrainingPolicy.min_shifted_rows` no horizon can clear the
policy and training will be refused for all of them. The deleted quality report
recorded `single_observation_itineraries_pct: 100.0`, which is exactly the
condition this check exists to name.

The test file was retargeted at `tmp_path` and asserts the export cannot escape
it. The tautological doctor test is replaced by five that can fail: an absent
path is `EXIT_FAIL`, a negative fare is `EXIT_FAIL`, an empty corpus is
`EXIT_FAIL`, a clean two-row curve is `EXIT_WARN` and not `PASS`, and
`booking_curve_shape` returns 0 labellable rows for five single-observation
curves and 2 for one two-observation curve. `backend/dataset/exports/` is
gitignored, with the reason written where the next reader will find it, and the
three fixture files are deleted from the working tree. They remain in the index
from the earlier `git add`, so `git rm --cached -r backend/dataset/exports` is on
your list below.

---

**40. The fail-closed forecast state was dressed as a crash, in scikit-learn
vocabulary, with a retry button that could never succeed.** With no model trained,
`POST /api/v1/predict` correctly answers 503 — and the forecast page rendered that
under a red-bordered card headed `INFERENCE SESSION ERROR`, reading `Prediction
unavailable: ML model estimator is uninitialized or missing.`, above a
`Retry Inference` button. Three separate problems in one panel. "Estimator" is
scikit-learn's word for a fitted object and means nothing to a traveller.
"Uninitialized" describes a process fault, when the actual state is that no
artifact has ever cleared the acceptance gate — a fact about the training corpus.
And retrying cannot change the outcome: the same request will be declined
identically until a model exists, so the button offers an action that is
guaranteed to fail.

The 503 is the design decision from earlier in this pass working exactly as
chosen: refuse rather than invent. Presenting it as a malfunction understates the
system and misleads the user in the one place the honesty work was supposed to
show.

`usePrediction` was discarding the information needed to tell the two cases apart.
`ApiError` carries `statusCode`, and the hook flattened it to `err.message`, so the
page could not distinguish "the server declined, by design" from "something
broke". The hook now exposes `errorStatus`, and the page branches on it: a 503
renders a neutral grey `Forecast Not Available Yet` notice with no retry control,
and every other status — including a network failure, where `errorStatus` is null —
keeps the red error card and the retry button, which is where retrying is a
sensible thing to offer.

The router's detail string is what the user actually reads, so it is now written
for them: *"No forecast model has been trained yet, so SkyMind will not guess where
this fare is going. Fare search still works."* The last clause matters — search and
forecast are separate paths, and a user seeing a red error on this page has no way
to know the rest of the product is fine.

Verified end to end rather than assumed: `HTTPException(503, detail=...)` →
`main.py`'s `StarletteHTTPException` handler → `error.message` → `api.ts` reads
`body?.error?.message` → `ApiError(message, 503)` → `errorStatus === 503` → the
notice card. `tsc --noEmit` passes with 0 errors.

Two things checked and deliberately left alone. `getattr(predictor, "_trained",
False)` looked like it might be probing an attribute that does not exist — which
would refuse predictions forever even after a successful train — but `_trained` is
real, initialised False at `price_model.py:668` and set True only after the
acceptance gate passes. And the four sidebar rows showing `—` (Historical
Accuracy, Market Freshness, Data Provider, Last Updated) are correct: each falls
back to an em-dash rather than a number, which is the fabricated-evidence panel
from §8 staying fixed.

---

**41. Your real `price_history` export, measured: no, you cannot train yet — and
the reason is collection cadence, which no amount of tuning reaches.** You gave me
a Supabase export of `price_history`: 35,894 rows, 33 columns. Rather than
estimate, I ran the shipped labeller over it — `attach_future_target`, the one
definition of the training target, after
`filter_training_eligible_dataframe`, the one definition of an eligible row. That
filter keeps 33,069 of the 35,894 (it drops 2,468 rows flagged `is_live=False`,
156 below the ₹800 plausibility floor and 201 above the ₹60,000 ceiling). What
comes back:

| horizon | labelled rows | distinct curves | routes | vs the floor of 100 |
|---|---|---|---|---|
| 1 day | 149 | 117 | 2 | clears, barely |
| 3 days | 2,114 | 184 | 6 | clears |
| 7 days | **1** | 1 | 1 | refused |

So `python backend/run_pipeline.py` on this corpus would train two of three
horizons and refuse the third, and the two it trained would be fitted on 149 rows
covering two routes and 2,114 rows covering six. That is not a model; it is an
overfit of a fortnight in July.

The cause is the collection calendar. The 35,894 rows span 57 days but land on
only **nine** of them — 07-05 (546 rows), 07-19 (157), 07-20 (2,254), 07-21 (230),
07-22 (1,000), 07-23 (15,674), 07-24 (13,712), 07-27 (2,145), 08-31 (176).

The eligible corpus is narrower still, and this is the histogram that governs,
because these are the only rows a label can be attached to: 07-05 (543), 07-19
(**1**), 07-20 (**14**), 07-21 (**2**), 07-22 (1,000), 07-23 (15,574), 07-24
(13,614), 07-27 (2,145), 08-31 (176). Four of the nine collection days contribute
essentially nothing once the eligibility rule runs, so what the trainer sees is one
isolated day in early July, a dense three-day block, a fourth day five days later,
and one day five weeks after that.

A booking curve needs the *same flight* priced again on a *later* day, and only
1,563 of 25,881 curves are observed on more than one date. The corpus therefore
contains essentially two genuine day-over-day transitions (07-22→07-23 and
07-23→07-24) plus one four-day one (07-23→07-27, which the 3-day horizon's forward
window of `[t+3, t+4.5]` days admits). Every labelled row traces back to those: 101
of the 149 rows at 1 day and 1,833 of the 2,114 at 3 days are observations made on
07-23. Eighty-eight percent of the eligible corpus sits on the two consecutive days
07-23 and 07-24.

This is why the doctor's `at most 13,226 labellable` line needed the check that now
sits beside it. That ceiling counts every row whose curve carries *any* later
observation, and on this corpus almost all of those "later" observations are the
same day's repeat measurement. The ceiling overstates the 1-day horizon by a
factor of 89.

**The most serious finding is that `flight_number` does not hold a flight number.**
It holds the row's rank within its search result set, prefixed with the airline
code. Of the 1,648 searches, 1,562 (94.8%) carry numeric suffixes forming a dense
sequence `1000, 1001, … 1000+n−1` with no repeats, and 1,596 (96.8%) start at
exactly 1000. Across the corpus the suffix `1000` occurs 2,800 times, `1001` 1,566,
`1010` 1,155, `1050` 141 and `1071` once — a decay curve shaped like search-result
depth, in only 76 distinct values. Real flight numbers do not do that.

Two independent corroborations. `stops` changes within 159 of the 2,093 curves that
have at least two observations and a recorded `flight_number` (7.6%) — one "flight"
going from nonstop to one-stop between observations. (That denominator is the
non-null-`flight_number` subset; the raw corpus has 3,213 multi-observation curves,
the extra 1,120 being rows with no flight number at all.) And the shape of the exception proves the rule: every one of
the 32,709 rows written by collector `1.0.0` carries a suffix at or above 1000,
without exception. The only 156 rows that do not are all on 2026-07-19, from a batch
with no `collector_version` and no `provider` recorded at all — and those 156 hold
just **four** distinct values, `6E100` (56 times), `AI101` (40), `6E102` (40) and
`AI103` (20). Four numbers repeating across a batch is what a flight number looks
like. A dense non-repeating run from 1000 is what a result index looks like. The
corpus contains both, and the pre-versioned code path is the one that recorded the
real thing.

`flight_number` is one of the five `BOOKING_CURVE_KEYS`, so `attach_future_target`'s
presence guard is satisfied and the join proceeds, while the exact defect that
module was written to prevent — labelling a row with a *different aircraft's* later
fare — happens anyway. The rank is stable enough between consecutive searches that
the median within-curve fare ratio is only 1.051, which is why nothing looked
wrong; 38 of those 2,093 curves move by more than 2× and 10 by more than 5×. This
has to be fixed at ingest before any of these rows are trainable, and it is not
repairable after the fact: the true flight identity was never recorded.

Four columns carry no information. `training_weight` is **2 for every live row**, so
the `sample_weight` argument threaded through training is mathematically identical
to no weighting at all. `seats_available` takes three distinct values across 33,426
live rows, with 30.0 on 32,587 of them (97.5%) — a scraped placeholder, not
inventory. (Scope matters on that one: the raw table has 52 distinct seat counts, and
every one of the varied values is on a row the eligibility filter drops. The rows
that reach training are the constant ones.) `duration` and `terminal` are 100% null,
and both sit in
`PROHIBITED_EMPTY_COLUMNS`, which is why the doctor FAILs that check. Two more are
redundant rather than empty: `search_timestamp` is byte-identical to `recorded_at`
in all 33,426 live rows, and `snapshot_id` has exactly the same cardinality as
`search_id` (1,648). And `provider = LIVE_MAKEMYTRIP_MCP` contradicts
`data_source = GOOGLE_FLIGHTS` on every row — two fields naming the origin of the
same fare, disagreeing.

Two fare-corruption cohorts, both narrow and both dated. The 156 rows recorded on
2026-07-19 are the only non-round-rupee prices in the corpus, ₹58.18 to ₹105.45:
those are USD values written into an INR column. They are exactly the rows whose
`flight_number` suffix is below 1000 — set equality, 156 against 156 — every one has
a NULL `collector_version` and a NULL `provider`, and among the live rows they are
the only ones with `seats_available = 9.0`. One code path, one day, three
fingerprints. And 201 rows exceed ₹60,000 for domestic ECONOMY, the worst of them
COK–DEL at ₹161,424, BOM–GOI at ₹118,724 and DEL–IXC at ₹113,784 — an order of
magnitude out. The eligibility filter excludes both cohorts, so they cannot reach
training, but they are in the table and they would corrupt any statistic computed
straight from it.

A third excluded cohort is worth naming because its exclusion is over-determined and
its label is misleading. The 2,468 rows dropped for `is_live = False` are all on
07-20 (2,240) and 07-21 (228), and **every one of them has a NULL `flight_number`** —
so the mandatory-key rule would have dropped them even if the flag had said live.
They also carry `is_synthetic = False` and `data_source = GOOGLE_FLIGHTS`, so nothing
in the row marks them as fabricated; they are simply unusable. This is also why
07-20's 2,254 raw rows become 14 eligible ones.

Two integrity findings the doctor now reports. `days_until_dep` is wrong on 14,257
rows (42.7%), every one of them off by exactly +1 — consistent with the value being
computed in IST against a `recorded_at` stored in UTC. And there are 423 exactly
duplicated snapshots, 601 on curve identity plus `recorded_at`. Separately, there
is no `departure_time` column at all, which confirms migration 001 is still
unapplied and is why `hour_of_day` and `is_peak_hour` have 0% coverage.

Measuring this corpus exposed four code defects, all now fixed.

**`parse_to_date` could not read a Supabase timestamp.** Postgres exports a
`timestamptz` as `2026-07-23 08:43:28.003237+00` — a *two-digit* UTC offset.
`datetime.fromisoformat` requires `+HH:MM` before Python 3.11, and `parse_to_date`
called it with no fallback. This was not cosmetic: `engineer_dataset_features`
calls it on `recorded_at` for every row, so the entire `backend/dataset` v2.0
feature build raised `ValueError: Invalid isoformat string` on the first row of any
genuine export. It had only ever run to completion against fixtures whose
timestamps happened to be `fromisoformat`-shaped. It now parses through
`pd.to_datetime(..., utc=True)`, which accepts every form Postgres emits, with the
hand-rolled paths kept as fallbacks; verified by running the real feature build to
completion, `(800, 46)`.

**A parse failure was being reported as a corpus defect.**
`validate_days_until_dep_row` wrapped the above in `except Exception: return False`,
and the doctor counted every `False` as a "date mismatch". On your export that
printed `35894 date mismatches` — all 35,894 rows — when the true figure is 14,257,
and it would have printed a different number on Python 3.11, where the string
parses. A check whose result depends on the interpreter's minor version is not
measuring the data. There is now `classify_days_until_dep_row`, returning `"ok"`,
`"mismatch"` or `"unreadable"`, and the doctor reports the two failures separately
because they have different causes and different fixes. `validate_days_until_dep_row`
survives as the boolean face of it, so the existing test contract holds. It also
read `recorded_at` before `search_timestamp`, the reverse of the precedence the
label join and the ingestion writer both use, which by itself made a correct
`days_until_dep` fail by one whenever a search crossed midnight before it was
written.

**The doctor's trainability verdict was true and still misleading.** `[OK] Trainable
rows: PASS (at most 13226 labellable, floor 100)` is literally correct and leaves a
reader concluding training is fine, when the labeller yields 149, 2,114 and 1. The
doctor now has a ninth check that calls `attach_future_target` for each horizon the
system declares and FAILs any that falls below `TrainingPolicy.min_shifted_rows`, so
the report states what training will actually receive rather than a second estimate
of it. On your export it prints `1d=149, 3d=2114, 7d=1 — horizon(s) [7] below the
floor of 100` and exits 2. The horizon list itself moved out of
`PriceModel.__init__` into `booking_curve_definition.SUPPORTED_TRAINING_HORIZONS`,
because a diagnostic grading a corpus against a second copy of that list could pass
horizons the trainer does not train — and because a pandas-only tool should not
have to import xgboost to learn them.

**The readiness grader was a third, separately written copy of the label join, and
it graded this corpus A.** `DatasetQualityValidator.evaluate_horizon_readiness` —
called on every training run from `price_model.py`, and the source of the
`horizon_readiness` block in the JSON reports — built its own join on
`origin_code, destination_code, departure_date, recorded-date` plus `airline_code`
and **never `flight_number`**, kept every match instead of the earliest, and at
horizon 0 set `shifted_cnt = len(df)` and graded it ready. That is the precise
defect `booking_curve_definition` exists to eliminate, reintroduced in a third
place. Measured on your export, the old join reported **225,485** shifted rows at 1
day, 15,967 at 3 and 1,990 at 7 — grade A and `ready=True` for all three, plus grade
A for horizon 0. It claimed more trainable rows at one day than the corpus has rows
in total, and the same training run then refused the 7-day horizon on
`shifted_rows=1`: the report and the gate contradicted each other in one log.

It now counts with `attach_future_target` like everything else, refuses any horizon
below `MIN_TRAINABLE_HORIZON_DAYS` with the reason stated instead of grading it,
reports a corpus it cannot label at all as `F` with the labeller's own error text,
and derives `ready` from `policy.MIN_SHIFTED_ROWS` — the threshold that actually
gates training — rather than from a third independent set of numbers. The letter
grade is kept, since callers print it, but it no longer decides anything. On your
corpus it now reads `0d F not-ready`, `1d C ready (149)`, `3d A ready (2114)`,
`7d D not-ready (1)`, `14d C not-ready (94)`, `30d D not-ready (4)`. Both shipped
tests that touch this method still pass.

What it would take to make this trainable, concretely. First fix `flight_number` at
ingest so a curve is one aircraft; nothing else matters until that holds, because
every label attached under the current key may be another aircraft's fare. Then
collect on a **daily** schedule over a fixed route set.

The arithmetic is worth stating because it explains why volume has not helped. The
label is a forward as-of match: a row observed at `t` is labelled with the earliest
later observation of the same flight in the window `[t + h, t + h + max(0.5, h/2)]`.
So a 1-day label needs the same flight seen again 1 to 1.5 days later, and a 7-day
label needs it seen again 7 to 10.5 days later. Nothing about how many rows you
capture in one sitting affects either condition — 15,674 rows on 07-23 produced 101
labelled rows at 1 day, because the constraint is the *return visit*, not the batch
size.

Under daily collection, the number of 1-day training rows is roughly (flights
tracked) × (consecutive-day pairs). Twenty routes at twenty flights each, collected
daily for a fortnight, is 400 curves × 13 transitions ≈ 5,200 labelled rows at the
1-day horizon — against the 149 the 35,894 rows here yield. The 7-day horizon
produces its first label on the eighth day of unbroken collection and reaches a
hundred rows as soon as a hundred flights survive that eight-day span, so three to
four weeks of daily runs clears all three horizons comfortably. The corpus you have
cannot get there by any amount of tuning; it needs a scheduler that runs and keeps
running.

**42. What the live scraper can actually fetch, measured against a live page: six
real fields, and no flight number in existence.** §41 said the corpus cannot train
because of collection cadence. That was true but not sufficient: the pipeline as it
stood could not produce a trainable row on *any* cadence. You ran a throwaway probe
(`probe_fetch.js`, since deleted) that drove the real MCP server over stdio the way
`mcp_client.py` does, against DEL→BOM for 2026-09-24. It returned 65 flights from
130 cards. Per-field coverage after the `stdio_server.js` mapping — i.e. what a
`price_history` row would contain:

| field | populated | distinct | note |
|---|---|---|---|
| `departure_time` | 65/65 | 53 | real, naive-local |
| `arrival_time` | 65/65 | 63 | real |
| `price` | 65/65 | 15 | ₹5,985–₹7,719, no zeros, nothing in the USD range |
| `duration_minutes` | 65/65 | 12 | 130–315 |
| `airline` / `primary_airline` | 65/65 | 5 | all five mapped to IATA, no `Unknown` |
| `stops` | 65/65 | 2 | 58 nonstop, 7 one-stop |
| **`flight_number`** | **0/65** | 1 | null on every row |
| **`seats`** | **0/65** | 1 | never assigned by the provider at all |

**Google Flights does not publish a flight number.** Zero matches for
`/\b(6E|SG|IX|AI|QP|UK|9I|EK|QR|BA|SQ|LH)[- ]?\d{2,4}\b/` anywhere in the live page
text; a 2026-07-19 capture of DEL→BBI agrees. This is not a selector to repair.
Since `flight_number` is one of the five `BOOKING_CURVE_KEYS` and
`curve_identity_mask` requires all five non-blank, **every honestly collected row is
unlabellable** — which is the real blocker, and it is upstream of cadence.

Three changes to `GoogleFlightsProvider.js` follow from the measurement.

*The flight-number extractor is deleted, not fixed.* It never matched a flight
number, because there are none. What it did match, on the expanded detail cards, was
the departure day glued to the carbon figure — "Sep 24" + "117 kg CO2e" → `24117` —
on 41 of those 65 cards (July's capture gave `26123` by the same mechanism). Its
guard `known.some(k => l.includes(k) || airline !== "Unknown")` could not stop it:
the second disjunct ignores `k`, so `some()` is true for every line once the airline
is identified. Nothing fabricated ever reached the database, but only because of an
unrelated filter, described next.

*`if (lines.length < 6) continue;` is load-bearing in a way nobody wrote down.*
Google renders every flight twice, and the expanded card contains no newlines, so it
arrives as a single line and is dropped. The live capture is exactly 65 expanded
cards (1 line) + 58 nonstop summaries (10 lines) + 7 one-stop summaries (11 lines,
the extra line being the layover). Add a newline to Google's detail markup and that
filter stops halving the list — every flight doubles *and* the deleted regex, had it
survived, would have started emitting `24117`. The guard is now documented for what
it does.

*Duplicate cards are now de-duplicated explicitly.* Google lists some departures
twice, under a "Best" heading and again in the full list. The 65 parsed cards
contained one exact repeat — Air India 21:00→23:20, ₹6,950, 140 min, nonstop,
identical in every field. Left in, each run writes two observations for that flight
at the same `recorded_at`, double-weighting it in the booking curve. The de-dup keys
on `(airline, departureTime, arrivalTime, basePrice, stops)` and deliberately omits
`flightNumber`, which is constant and would de-duplicate nothing. Re-running the
edited source over the same 130 captured cards yields 64 flights, 64 distinct
signatures, `flightNumber` empty on all of them.

*And the constructive half.* `departure_time` is the identity `flight_number` was
supposed to be. On these 65 rows, the shipped key
`(origin, destination, airline, flight_number, departure_date)` yields **5** distinct
identities — it collapses onto the five airline codes. Substituting `departure_time`
for `flight_number` yields **64 of 65**, and the single collision is that exact
duplicate card, not two different flights. Switching `BOOKING_CURVE_KEYS` is
therefore the one change that makes collection worth starting, and it depends on
migration 001, which is yours to apply.

*MakeMyTrip is not an alternative — measured dead, twice over.* You ran the probe
against the live site. Two mechanisms, independent of each other:

The **results URL** — `makemytrip.com/flight/search?itinerary=DEL-BOM-24/09/2026&
tripType=O&paxType=A-1_C-0_I-0&cabinClass=E`, the canonical deep link — returned
`final_url` unchanged (so no redirect and no bot wall), `title` `""`, and a `body_text`
of literally **`200-OK`**: six characters. Zero anchors, zero `data-cy` attributes,
zero `<input>`/`<button>`/`<form>`/`<select>`, zero console errors, and every shipped
selector (`data-cy="flightNumber"`, `airlineName`, `departureTime`, `price`,
`listingCard`) false. That is not a page a selector fix reaches; the server answers a
health-check stub to this client.

The **form page** hydrated properly — correct title, 13,515 characters, 402 anchors,
805 `data-cy` attributes — and still exposed **zero** `<input>`, `<button>`, `<form>` or
`<select>` elements, so there is nothing for an automated search to fill or submit.
The repo's `makemytrip_debug.html`, captured 46 days earlier, agreed
attribute-for-attribute: 805 `data-cy` in both, 0 `<input>` in both. The failure is
reproducible, not a bad day. (That capture is no longer in the tree — §44 deleted it
with the provider. The counts above are the record of it.)

Flight numbers on the MakeMyTrip path: **NONE**, on both URLs.

(An earlier draft of this section said the capture was of the homepage and inferred
from `data-cy="flightNumber"` appearing zero times that the scrape never reached
results. Both of those were wrong — the URL is the correct search page and the dump is
taken deliberately before submission. The conclusion stands on the element counts
above instead, which is stronger evidence than the selector census was.)

---

**43. The booking-curve key now names a column the provider actually publishes —
and switching it exposed twenty-one places that had hand-typed the old one.**

`BOOKING_CURVE_KEYS` is now
`('origin_code', 'destination_code', 'airline_code', 'departure_time', 'departure_date')`.
The fourth component was `flight_number`. §42 is the measurement that forced it: across
65 live DEL-BOM flights Google Flights publishes a flight number **zero** times, so the
key's per-flight component was NULL on every honestly-collected row, and a curve with a
NULL component is not a curve. The shipped key resolved those 65 observations to **5**
identities — one per airline code, pooling 29 IndiGo departures into a single "price
history". `departure_time` resolves them to **64**, the one collision being a byte-identical
duplicate card.

*Why this is not a one-line change.* The tuple is defined once, but twenty-one call
sites had a copy of it typed out as string literals, and code that iterates
`BOOKING_CURVE_KEYS` while a neighbour asserts on a typed list will not tell you they
have diverged. Sixteen were in production code, five in test fixtures. In severity
order, what the copies were doing:

1. **`curve_window_definition._curve_frame` raised a live `KeyError`** on the serving
   path — the only one of the twenty-one that announced itself.
2. **26 inference features were silently NaN**: 14 booking-curve, 5 volatility, 7 trend.
   The generators grouped on a key whose fourth component did not exist in the frame,
   found no group, and returned nulls. Now measured populated (12/14, 5/5, 7/7) on a
   five-day curve.
3. **`itinerary_id` collapsed**, so `time_series_plugin` deleted *every* row of a
   pooled itinerary as a duplicate, and `snapshot_sequence` counted sibling departures
   as repeat observations of one flight.
4. **`compute_health_metrics` published roughly 29× the real booking-curve depth** —
   pooled siblings counted as history.
5. **`validate_chronology` returned a false FAIL** on a correctly-sorted corpus.
6. **`validate_target_leakage` reported `groups_tested: 5` and PASS** over depth the
   corpus does not have.
7. **`doctor.py`'s `booking_curve_shape` inflated its own upper bound**, in the
   direction that makes an untrainable corpus look trainable.
8. **`MANDATORY_RAW_COLUMNS` listed `flight_number`**, and `SchemaValidationPlugin`
   both fails on an absent column *and* drops every row holding NaN in one — so the
   export path was instructed to reject the entire real corpus. It now lists
   `departure_time` instead.

*The rule applied everywhere.* Where a curve key is incomplete, the code now refuses to
answer rather than answering on a narrower key. `curve_identity_is_complete` /
`curve_identity_mask` require all five components non-empty; `attach_future_target`
refuses a frame missing any of them; `ForecastEvaluationScheduler._curve_from` retires a
forecast as UNEVALUABLE rather than matching four-of-five. That last one means every
forecast stored before today is correctly refused: it names no departure time, and
guessing which of a carrier's departures it meant is the defect itself.

*Two stale fixtures, both of which had stopped testing anything.* Neither was caused by
the key change; both were exposed by it.

`test_ingestion_batch_timestamp_consistency`'s transport mock carried no `status` field.
`_guarded_transport` refuses a transport dict without one — "transport returned dict
without a status" — so the search took the DB-fallback branch, `insert_observations` was
never reached, and the test's own `assert mock_insert.called` was failing on a contract
violation in the fixture rather than on anything about timestamps. Worse, it was not
failing at all: the runner was counting the un-awaited coroutine as a pass. Fixed, plus
two new assertions that `departure_time` survives `format_payload` → `get_db_payload`,
because if it stops surviving, every row ingested from then on has no curve identity,
carries no label, and nothing else in the suite notices.

`test_forecast_evaluation_scheduler` asserted `completed == 1` against mocks wired for
`table().select().eq().execute()` — the chain `_load_pending` had *before* the evaluator
rebuild changed it to `.select("*").eq(...).order(...).limit(...).execute()`. `.order`
fell through to an
auto-created `MagicMock`, `.data` was a `MagicMock` rather than the fixture rows, and the
loop iterated its default empty iterator. The test read none of its own fixture and
reported 0 while asserting 1. Replaced with a builder that returns `self` from every
link, so it cannot go stale again, and records which columns were filtered. It now
asserts the three properties the rebuilt evaluator exists for: the outcome is the
**earliest** in-window observation and not the cheapest fare nearby (two decoy rows,
both cheaper, must not win); the window is applied to `search_timestamp`, so the
realised row's `recorded_at` deliberately sits outside it — the nightly-batch shape of
your real corpus; and all five curve keys are filtered.

*The doctor's exit codes were inconsistent with their own meaning.* `booking_curve_shape`
returned FAIL for a corpus that is merely too shallow to label. FAIL means "the corpus is
damaged"; WARN/PARTIAL means "the corpus is clean but not trainable yet". A collection
run that has not gathered enough days is the second thing, and reporting it as damage is
how you end up deleting a corpus that was fine. Regraded to WARN.

*Verified.* 110 passed, 0 failed, 1 skipped across the twelve modules the change
touches — `test_dataset_pipeline_v2` (12), `test_trend_features` (2),
`test_volatility_features` (2), `test_booking_curve_features` (3), `test_target_leakage`
(3), `test_shifted_training_dataset` (4), `test_training_dataset_shift` (3),
`test_future_target_alignment` (3), `test_training_inference_parity` (7),
`test_booking_curve_pipeline` (14), `test_historical_platform` (17),
`test_production_training_pipeline` (40, 1 gated skip for the absent model artifact).
Train/serve parity holds value-for-value on all 64 `FEATURE_SET_V1` features and all 16
legacy features, with an empty exemption list.

*And it is inert until you apply migration 001.* `departure_time` does not exist in your
`price_history` yet. Until it does, every ingest carrying it will be rejected by the
database, `hour_of_day` and `is_peak_hour` stay NaN for 100% of training rows while the
serving path supplies a real departure hour, and no row can carry a label — because
`attach_future_target` raises on a *missing* key column. A key column that is present and
NULL was a different matter entirely, which is the state this migration creates and which
§45 had to close before the migration is safe to run. Applying the
migration is yours; I will not run DDL against your live database. Step 8b of that file
must stay unrun until writer-side de-duplication lands, and step 8a is *expected* to
report collisions today because every existing row predates the column — that is not a
reason to widen the key.

---

**44. MakeMyTrip is deleted; Google Flights is the only provider, in the tree as well
as in fact.**

§42 measured MakeMyTrip dead: its search widget renders no interactive elements at
all under automation, and the results URL that needs no form answers with a
six-character body. This section deletes it. The instruction was "get rid of mmt
keep the google flights only", and the point of doing it rather than leaving a dead
file in the tree is that a scraper on disk reads to an interviewer as a second data
source, which the project does not have.

**Deleted.** Four files, all under `backend/india-flight-mcp`:

| Path | Size | Tracked in the nested repo? |
| :--- | ---: | :--- |
| `src/providers/MakeMyTripProvider.js` | 265 lines | yes |
| `src/mcp/makemytrip_debug.html` | 443,709 B | no |
| `src/mcp/makemytrip-before-form.png` | 781,219 B | no |
| `src/mcp/makemytrip-error-1784458378861.png` | 775,716 B | no |

The provider file already carried a `DEAD CODE` header. Unreachability was proved
before deleting, not assumed: `grep -rn "require.*MakeMyTrip"` across the MCP
package matched one comment and no `require`, and after the deletion
`require('./src/FlightAggregator')` still loads and reports `providers: GoogleFlights
| count: 1`. `node --check` is clean on `FlightAggregator.js` and
`src/mcp/stdio_server.js`, and `src/mcp/tools.js` requires cleanly.

**`parse_mmt_flight_string` deleted — and it was not dead code.** An earlier pass
guessed it was unreferenced. It was not: `flight_normalizer.normalize_mcp_flight`
called it at line 220, on the raw-card branch that the live Google Flights path
actually takes. It was *inert*, which is a different thing. What it was fed is
`flight_name`, built at `stdio_server.js:110` as the carrier's display name with the
flight number appended — and the provider publishes no flight number (0 of 65 on the
live 2026-09-03 fetch), so the string is a bare `"Air India Express"`, the regex
`\b([A-Z0-9]{2})[- ]*([0-9]+)` finds no digits, and the function returned `("", "")`
on every real card. Both fallbacks below it fell through to what they fall through to
now, so removing it changes no observable value.

It was deleted because of what makes it inert: the input, not the code. `[- ]*`
matches the empty string, so any display text carrying two alphanumerics followed by
digits synthesises a flight number out of them. That is precisely how the scraper
regex deleted in §42 turned "Sep 24" and "117 kg CO2e" into flight 24117 on 41 of 65
cards. A fabricator that is quiet only because today's provider happens to emit a
short string is a fabricator waiting for an input. The module-level alias
`parse_mmt_flight_string = MarketDataController.parse_mmt_flight_string` went with it;
`import re` stays, because `_TIME_ONLY` still needs it.

**Prose corrected in seven files**, because a stale sentence naming the wrong
provider is worse than no sentence — it reads as evidence. `FlightAggregator.js`
(header), `india-flight-mcp/README.md` ("What it searches", offers paragraph),
`flight_data_provider.py` (the `GoogleFlightsProvider` docstring), `flight_search_service.py`
(the `LIVE_GOOGLE_FLIGHTS_MCP` block at 448), `booking_curve_definition.py` (why
`departure_time` and not `flight_number` is a curve key), `flight_normalizer.py` (the
raw-card branch), `docs/FLIGHT_SEARCH_AUTHENTICITY_AUDIT.md` (§2 item 1). Two stale
statements inside *this* log were also wrong and are fixed: §24 twice asserted the
collector's only provider is "the MakeMyTrip transport", which contradicted
`route_catalog/routes.yaml:282-293`, a live file that already named the Google Flights
scraper correctly.

**Kept deliberately, as evidence.** §42's measurement of the MakeMyTrip failure stays,
because it is the justification for the curve-key change in §43 — delete it and
`departure_time` looks like an arbitrary choice. The record of the
`LIVE_MAKEMYTRIP_MCP` provenance mislabel stays at `flight_search_service.py:344-351`
and `scheduler.py:293-295`; those comments make no false present-tense claim, and rows
written before the relabel still carry the old string in `data_source` and `provider`.
No query anywhere filters on either column.

**One test gated, not fixed.** `test_prediction_live_search.py::test_prediction_service_invokes_snapshot_provider`
was failing with `PredictionUnavailable: Active model does not support forecasting`.
That is the §12 quarantine working, against a test that had no gate. Its first
assertion looks model-independent — "queries snapshot provider and never invokes
search directly" — but `PredictionService.predict` checks the capability
precondition at step 1b (`prediction_service.py:191-204`), deliberately ahead of the
snapshot fetch, so that an unservable request does not first pay for a scrape and an
inference. With no artifact the method therefore raises before `get_market_snapshot`
is called and `.called` is False for reasons that have nothing to do with routing. The
whole test now begins with `requires_trained_model()` and skips with the
artifact-absent reason.

**Verification.** `py_compile` clean on the four edited Python modules.
`backend/tests/`, sandbox: `test_flight_data_provider` 2, `test_contract_google_provider`
1, `test_live_flight_search_fidelity` 2, `test_zero_synthetic_data` 2,
`test_route_catalog` 9, `test_flight_stabilization` 5, `test_market_snapshot_provider`
2, `test_market_snapshot_cache` 1 — **24 passed, 0 failed**, plus the one gated skip
above. `test_chat_search_parity_regression` could not be run here (`openai` is not
installed in this sandbox); run it on Windows. Counted over `*.py`, `*.js`, `*.ts`,
`*.tsx`, `*.md`, `*.yaml` and `*.json`, the string "MakeMyTrip" appeared 69 times in
11 files before this section and appears 38 times in 10 afterwards — of which 21 are
in this log, 11 of them added by this section, which is the only honest way to count a
section that names the thing it deleted. Outside the two audit documents there are
12 mentions left, all deliberate prose: `flight_search_service.py` (3),
`FlightAggregator.js` (2), `flight_normalizer.py` (2), and one each in
`booking_curve_definition.py`, `flight_data_provider.py`, `ingestion_controller.py`,
`india-flight-mcp/README.md` and `scheduler.py`. No `require`, `import`, class,
function or file name anywhere refers to it.

**Warning: the four deletions are invisible to your commit.** `backend/india-flight-mcp`
has its own `.git`. Nothing under it — these deletions, the §42 scraper fixes, or
anything else — enters the outer repository until you decide whether that directory is
a submodule or vendored source. That decision is still on your list, and this section
is the third change that depends on it.

---

**45. Applying migration 001 would have re-opened the cross-flight label leak, because
the labeller never consulted the identity it was given.**

This one was found by refusing to write a line of code before checking whether it was
needed, and it is the reason the migration should not be applied until this section's fix
is in your tree.

The plan for the database said the third step was a `collector_version` boundary: bump the
version in the fixed collector, filter training on it, and the 32,709 rows written by
`1.0.0` stop reaching the model. Before writing it I checked whether it was redundant —
if `departure_time` in `BOOKING_CURVE_KEYS` (§43) already excluded every pre-migration
row, the filter would be dead code of exactly the kind this pass has been deleting.

It is not redundant, and the reason is a defect rather than an oversight.

`curve_identity_is_complete` states the contract plainly, and has since §43:

> Callers must treat False as "this observation has no curve": every curve-derived
> feature is unknown, which is NaN, and not a window of length 1.

`curve_window_definition.py:140` honours it — `self.unidentified = ~curve_identity_mask(df)`,
and those rows are dropped before the rolling windows are computed. `_price_at_offset`, the
shared as-of body underneath **both** `price_at_horizon` (the supervised label) and
`price_at_lag` (the `price_change_1d` / `price_change_3d` features), did not. It grouped
with `pd.merge_asof(by=keys)` and never looked at the mask.

`merge_asof(by=...)` factorises its key columns, and a null factorises to a value that
matches other nulls. So on a route, airline and date where `departure_time` is NULL, every
flight is one group and one curve. Measured on a four-row frame — two distinct departures,
each observed on 2026-07-01 and 2026-07-04, at ₹5,000/₹5,300 and ₹9,000/₹9,400:

```
curve_identity_mask   -> [False, False, False, False]
attach_future_target(h=3) returned 2 rows:
   price=5000.0  target_price=5300.0
   price=9000.0  target_price=5300.0      <-- the other flight's fare
```

The ₹9,000 departure was told that in three days it would cost ₹5,300 — a 41% fall
invented by the join. `curve_identity_mask` said, correctly, that not one of those rows had
a curve. Nothing consulted it, and nothing reported it.

**Why this was about to become live rather than being historical.** The note above
`BOOKING_CURVE_KEYS` claimed that until migration 001 is applied, `departure_time` is
absent, the mask is False for every row, "and nothing trains — that is the honest state,
not a regression". Half of that is true. `attach_future_target` raises on a *missing* key
column, so the absent-column case really does train nothing. The migration adds
`departure_time` with no default and no backfill. The moment you ran it, the column would
be **present and NULL on all 32,709 pre-migration rows**: the missing-column guard silent,
the identity mask False, and the label populated anyway — with a sibling departure's fare.
Applying the migration was the trigger. I had also told you the "nothing trains" version
verbally when you asked what to do about the database; that was wrong, and this is the
correction.

This is defect 1 of this module's own header returning through a different door. §43 closed
it by *naming* a fifth key the provider actually publishes; naming a key is not the same as
requiring it to be populated.

**The fix is one statement, in the shared body.**

```python
    usable = frame["_ts"].notna() & pd.Series(
        curve_identity_mask(df).to_numpy(dtype=bool), index=df.index)
```

`usable` already gated both sides of the join — `right` is the price side, `left` is the row
side — so unidentified observations now appear on neither. It is placed in
`_price_at_offset` rather than in the two wrappers deliberately: a label that refuses to
pool two flights and a lag feature that pools them happily is train/serve skew manufactured
from one frame, and putting the mask in one wrapper and not the other is exactly how that
would happen.

Two details worth knowing before you read the diff:

* The mask is `curve_identity_mask(df)`, which checks all five `BOOKING_CURVE_KEYS`, not
  just the `keys` the call resolved. That matches `curve_window_definition`, the one caller
  that was already compliant, so the two cannot disagree about which rows have a curve. It
  is also safe: every production caller passing `group_cols` passes
  `curve_group_columns(...)`, the full present set (`price_model.py:1046`,
  `ml/features/booking_curve.py:143` and `:274`). Nobody passes a deliberate subset. The
  `group_cols=[]` and `group_cols=BOOKING_CURVE_KEYS` call sites in the tests belong to
  `chronological_split`, a different function.
* **The serving path is unaffected, and I checked rather than assumed.**
  `booking_curve.py:222` already returns all-NaN features when the request's own identity is
  incomplete, and each history row is admitted only if
  `get_booking_curve_group_key(candidate) == target_key` against a complete key — a NULL
  component renders `"NONE"` and fails that comparison. Every row in a serving frame is
  therefore fully identified, and the new gate is inert there.

Also corrected while in the file, because all three were prose asserting the opposite of the
code:

* `price_at_horizon`'s docstring still opened "The curve key includes `flight_number`", six
  weeks after §43 replaced it. Rewritten to three properties instead of two, the new one
  being that a row without an identity is not labelled at all — with the note that naming
  the fifth key was not sufficient on its own.
* `attach_future_target`'s docstring justified raising on a missing key column by saying
  `price_at_lag` and `price_at_horizon` "group on whichever keys are present". They no
  longer do. It still raises, and the reason is now the honest one: the join would return an
  empty frame either way, and an empty frame reads to a caller as "no data" rather than "no
  fifth key".
* The `BOOKING_CURVE_KEYS` note now separates absent-column from NULL-value and says which
  one the migration creates.

**A test that fails for the stated reason.** `backend/tests/test_curve_identity_gate.py`,
171 lines, six functions. The regression case is parametrised over `None`, `""` and
`"   "`, because `curve_identity_mask` strips before comparing and a blank string is not an
identity either. Falsified by loading a copy of the module with that one statement reverted
and running the shipped test against it: **4 failed, 4 passed** — the three blank variants
and the `price_at_lag` case, each with the cross-flight fare printed in the assertion
message. The four functions that pass both before and after are doing a different job and
say so: one guards the fixture arithmetic (`lag_tolerance_days(3) == 1.5`, so that
"no label" is evidence of the gate rather than of a tolerance that never admitted the match),
one asserts the gate drops rows rather than failing the frame, one is the positive control
(distinct departure times, each labelled from its own curve: 5000→5300 and 9000→9400), and
one holds the absent-column path to still raising.

**Do not write the `collector_version` filter.** It would have hidden this instead of
fixing it — legacy rows excluded, and the next NULL `departure_time` from any source
pooling silently again. If you still want a version boundary afterwards, the column already
separates the batches (`1.0.0` on 32,709 rows, NULL on 3,185) and no destructive statement
against `price_history` is needed for it.

Verification, this sandbox: `test_curve_identity_gate` 8, `test_booking_curve_features` 3,
`test_booking_curve_pipeline` 14, `test_future_target_alignment` 3,
`test_shifted_training_dataset` 4, `test_training_dataset_shift` 3, `test_target_leakage` 3,
`test_training_inference_parity` 7, `test_historical_platform` 17,
`test_production_training_pipeline` 40 + 1 gated skip, `test_feature_contract_alignment` 13,
plus seven feature modules — **135 passed, 0 failed, 1 gated skip**. `py_compile` clean.
Five failures elsewhere are the sandbox, not this change, and each was confirmed by running
it against the pre-fix module: four need a real XGBoost booster
(`test_training_pipeline` ×2, `test_training_reproducibility` ×2).
`test_production_validation` is import-blocked on `openai`. Run those four on Windows.

**Correction, entered when §50 was written.** This paragraph originally counted
`test_price_prediction_features` among the sandbox failures, on the grounds that it "needs
the network". That was wrong, and it is the one diagnosis in this log that pointed away
from a real defect instead of at one. The test fails on Windows too, for two shipped
reasons that have nothing to do with connectivity — see §50. The symptom is easy to
misread as a network failure, because the sentinel that rejects its mock reports the
transport as broken, which is what a dead scraper also looks like. The lesson is the one
I have applied everywhere else and did not apply here: prove a failure is
environment-caused by reproducing it against the pre-fix module, and treat "needs the
network" as a hypothesis rather than a category.

---

**46. The corpus's training value under the corrected curve identity is exactly zero, and
migration 001's own gate said the opposite in four places.**

Asked whether to delete `price_history` and start fresh, I measured the export rather than
answering from the earlier figures. The 35,894-row snapshot: 33 columns, **no
`departure_time`**; every row `is_synthetic = false, data_source = 'GOOGLE_FLIGHTS'`; 33,426
`is_live = true`, and the 2,468 `is_live = false` rows are exactly the ones carrying no
flight number. The fare bounds in `domain/provenance.py` remove 156 rows below ₹800 (the
₹58–₹105 USD-read-as-INR batch of 2026-07-19) and 201 above ₹60,000, leaving **33,069
training-eligible rows** over 54 routes and 6 airlines.

What those 33,069 rows yield as training examples, measured three ways:

| grouping | h=1 | h=3 | h=7 |
|---|---|---|---|
| as the table stands (no `departure_time`) | `ValueError` | `ValueError` | `ValueError` |
| after migration 001 (column present, NULL) | 0 | 0 | 0 |
| on `flight_number`, the key before 2026-09-03 | 149 | 2,114 | 1 |

Row three reproduces the 149 / 2,114 / 1 figures §41 reported, and identifies where they came
from: grouping on `flight_number`, which this corpus uses as a search rank (`6E1000` ×2,015,
`6E1004` ×1,139, …). Every one of those labels was a cross-flight label by construction. Row
two is the honest number, and it cannot be improved: the per-flight component was never
recorded, and no column here can reconstruct it — there is no time-of-day field anywhere in
the 33, and a search rank does not map to a schedule. **These rows can never be a training
example at any horizon, and nothing done later recovers them.**

They are not worthless, and the distinction decides the deletion question. `route_aggregates`
and `airline_aggregates` are as-of and grouped on *route*, not on curve, so all 33,069 sit in
the history that supplies fourteen features to future rows on those 54 routes. Keeping them
costs nothing in label safety — post-§45 they cannot be labelled or lend a lag feature. What
it costs is honesty of the aggregates: nine collection dates, **29,386 of 35,894 rows (82%)
from two adjacent days**, 2026-07-23 and 07-24, then five weeks to a 176-row visit on 08-31.
As-of means that burst is in the past for *every* future row, so `observation_density` and
`average_booking_lead` on those routes measure when the scraper ran, not what the market did.

Four prose corrections, all in the migration file and its neighbours:

1. **STEP 1's comment claimed the wrong failure mode** — "until this column exists
   `curve_identity_mask` is False for every row, no observation can be labelled". True of the
   *absent* column; this ALTER creates the *NULL* state, which is the §45 leak. The comment
   now carries the ordering requirement: do not run STEP 1 unless §45's statement is in the
   tree. This was the fourth copy of that conflation and the most dangerous, sitting in the
   file whose reader is about to create the state.
2. **8a's collision census did not share 8b's predicate.** The census filtered on
   `search_session_id IS NOT NULL`; the index also requires `departure_time IS NOT NULL`.
   GROUP BY treats NULLs as equal, so the census collapsed each session's whole route/date
   into one group and reported collisions among rows the index would never see — it said 8b
   would fail where 8b would have succeeded. Fixed, and it now reports `indexable_rows` so a
   zero that means "nothing to police" is distinguishable from a zero that means "no
   collisions". **Consequence for the deletion question: emptying the table does not release
   STEP 8.** The writer-side de-duplication in its PRECONDITION does, and that is still not
   in the tree. STEP 8's preamble said the same thing and is corrected too.
3. **STEP 3 has nothing to relabel.** `HIST-000` appears on zero rows, against the 6,328
   AUDIT-ADDENDUM §2.2 measured. Either the seeded block was deleted between the two
   measurements or §2.2 measured a seed artefact rather than this table; the file now says so
   and tells you to believe 3a's output over either.
4. **Two comments asserted a NULL `search_timestamp` corpus as fact.** Measured: the column
   is populated on all 35,894 rows. The per-row coalesce in `ordering_timestamps` is still
   right — any insert omitting the column stores NULL and one such row loses its label under
   a per-column reader — but the hazard is reachable, not occurring, and both
   `booking_curve_definition.ordering_timestamps` and `training_dataset_builder` now say
   which.

Checked and unaffected: `forecast_evaluation_scheduler`. `_curve_from` refuses a forecast
missing any of the five keys, and `_resolve_outcome` matches observations with
`query.eq(key, curve[key])` — `departure_time = '<value>'` never matches a NULL row — so the
one realised out-of-sample error figure in the project cannot pick up a legacy row.

Verification: `py_compile` clean on both edited Python files; `test_curve_identity_gate` 8,
`test_future_target_alignment` 3, `test_booking_curve_pipeline` 14,
`test_shifted_training_dataset` 4, `test_training_dataset_shift` 3, `test_target_leakage` 3,
`test_training_inference_parity` 7 — **42 passed, 0 failed**. The migration file is SQL and
was not executed: no database, live or local, was touched by any part of this.

---

**47. The one precondition migration 001's STEP 8 names is now in the tree: a batch of
observations is de-duplicated before it is written, not after.**

STEP 8b of the migration creates a unique index over an observation's identity, and its
PRECONDITION block said in as many words that adding it while the writer can still submit
two rows with the same identity would turn a duplicate into a rejected *batch* — PostgREST
fails the whole insert, so one repeated flight would cost you the other nineteen. Two ways
out were named: de-duplicate writer-side, or upsert with `on_conflict`. Only the first can
land first, because `on_conflict` names an index by name and PostgREST rejects every insert
that references one which does not exist yet. So the upsert has to arrive in the same change
as 8b, and the de-duplication has to arrive before either.

`deduplicate_observation_batch` in `backend/services/booking_curve_definition.py` collapses a
batch on exactly the seven columns 8b indexes: `search_session_id`, the four booking-curve
keys, `departure_time`, and `cabin_class`. Four things about it are deliberate:

1. **The survivor is the lowest fare, not the first row.** Two rows with the same identity
   and different prices mean the provider quoted the same flight twice in one page; keeping
   the cheaper one is the only choice that cannot make a fare look higher than it was
   offered. An unreadable fare sorts as `+inf`, so it *loses* to any row with a readable
   one rather than silently winning by being first. The survivor keeps the position of the
   group's first appearance, so batch order is still the provider's order.
2. **Rows outside 8b's partial predicate are passed through untouched.** The index is
   `WHERE search_session_id IS NOT NULL AND departure_time IS NOT NULL`; a row missing
   either cannot collide with anything, so collapsing it would destroy data the database
   would have accepted. Those rows are counted separately as `unindexable`, which is what
   makes "nothing was collapsed" readable — no collisions and nothing the index can see are
   different states.
3. **The identity reads `departure_time` by name, with `.get`.** `get_db_payload` drops keys
   whose value is `None`, so an absent column and a NULL one arrive here identically; a
   positional or subscript read would have raised on one and returned a false key on the
   other. This is §45's bug in its writer-side form.
4. **It never merges across searches.** `search_session_id` leads the key, so two visits to
   the same flight on different days stay two rows. That is the entire longitudinal signal —
   a de-duplicator that dropped it would leave the table looking clean and unable to produce
   a single label. `test_separate_searches_are_never_collapsed` exists for that one property.

It is called in two places. At the sole writer,
`historical_data_service.insert_observations`, which logs at WARNING rather than INFO,
because after 8b lands that same batch would have been rejected whole. And at the one call
site, `flight_search_service.search`, *before* `rows_submitted = len(db_payloads)` is taken —
otherwise a collapsed duplicate would be reported to the caller as
`persistence_error: submitted 20, database persisted 19`, which is §3's defect (a row count
that is not the number of rows persisted) arriving through a new door. The search response
now carries `provider_duplicate_rows` so the collapse is visible instead of inferred.

**Why batch scope is sufficient here rather than merely convenient.**
`search_session_id` is minted once per `FlightSearchService.search()` call
(`flight_search_service.py:339`), and each call performs exactly one insert with no retry.
The index's first key column therefore cannot repeat across two batches, so no duplicate
exists that a writer-side pass over one batch could miss. If a retry is ever added, or the
session id is ever reused across inserts, this reasoning expires and the upsert becomes
necessary — that is why the migration keeps 8b gated instead of declaring the problem
solved.

**The index and the code are held together mechanically.**
`test_observation_dedup.py::test_key_matches_the_migrations_index` parses the column list out
of the `CREATE UNIQUE INDEX` statement in
`backend/database/migrations/001_price_history_and_run_metadata.sql` — a paren-depth scan
anchored on the full statement text, not a regex over a line — and fails if it disagrees with
`OBSERVATION_IDENTITY_KEYS`. Editing one without the other is caught. The migration's
PRECONDITION and its 8a diagnostic note both previously said this code was not in the tree;
both now say it is, and name this section.

Verification: `test_observation_dedup.py` — 18 test functions, 21 cases,
**21 passed / 0 failed / 0 skipped**, re-run from a clean harness that shares no state with
the run that first produced that figure. Six mutations of the shipped code were each caught
by the tests that should catch them: making the collapse a no-op fails 11; dropping
`cabin_class` from the key fails 3; restoring `flight_number` to it fails 4; keeping the
first row instead of the cheapest fails 8; dropping `search_session_id` fails 3, including
the corpus-destroying case above; and three separate edits to the SQL column list each fail
the parity test alone. One test is deliberately dormant on the current corpus
(`test_empty_batch_and_idempotence`). The full suite over all 137 test modules stands at
**592 passed / 14 failed / 24 skipped** — every one of the 14 needs something this sandbox
does not have (a real XGBoost booster ×10, the network ×1, `fastapi` ×3 modules
import-blocked), and the 24 skips are 19 model-availability gates plus 5 empty-corpus gates.
**No database was touched, and 8b remains unrun.**

---

**48. A fare of unknown denomination was stored, and shown, as rupees. The same
fabrication was implemented eight times independently, and 156 rows already in the
corpus are US dollars.**

Nothing in this project filters `price_history` on `currency`. The plausibility window is
in rupees, `training_dataset_builder` averages the `price` column without consulting any
currency, and the loaders' predicate names two boolean columns and nothing else. So a row
whose fare is not in rupees is not a fare in another unit — it is a wrong number, and it
is wrong in a way that survives every check downstream of it.

That is measured, not hypothetical. **156 rows recorded on 2026-07-19 carry fares between
₹58 and ₹105, and they are US dollars.** A dollar fare is off by a factor of about 83, and
the window cannot be used as a substitute for a currency check: those particular rows are
small enough to fall outside it, but a $900 fare lands in the `price` column as `900` —
inside the window, and indistinguishable from a very cheap rupee fare.

The reason nobody noticed for weeks is the second half of this entry. Eight sites, in two
groups:

*Write path (three).* `GoogleFlightsProvider.js` located the price line by testing it for
`'₹'` **or** `'$'` and then stripped the symbol it had just matched, discarding the one
piece of evidence it had. `flight_data_service`'s FX loop read
`(f.get("currency") or "INR").upper()`, so a fare of unknown denomination was declared to
already be in the target currency and skipped by the converter. And
`MarketDataController.format_payload`'s `currency: str = "INR"` parameter default stamped
rupees on every row while the one production caller never passed the argument.

*Display path (five).* `NormalizedFlight.currency` was `str = "INR"`; both
`normalize_db_flight` and `normalize_mcp_flight` reached it through
`.get("currency", "INR")`; `chatbot_tools` re-derived it as
`(price_data.get("currency") or "INR")`; and `flight_formatter.format_currency`'s own
`currency: str = "INR"` default renders `f"₹{int(price):,}"` for that value. A $58 fare
therefore displayed as **₹58** — a cheap-looking rupee fare, not a visibly wrong number.
The frontend was worse than any of them: `formatCurrency(amount)` took no currency
argument at all and stamped `₹` on whatever it was given.

*The fix.* Absence is now unknown rather than rupees, everywhere.
`backend/domain/provenance.py` gains `decode_currency`, which maps `"INR"`, `"inr"`, `"₹"`,
`"Rs"`, `"rs."`, `"$"`, `"US$"`, `"€"`, `"£"` and the plain ISO codes to a code and
everything else — `None`, `""`, `"   "`, `"rupees"`, `"XYZ"`, `NaN`, a non-string — to
`None`; plus `fare_currency_is_corpus_currency` and `screen_observation_fares`, which
refuses a row for exactly one reason and reports why. The JS now derives `currency` from
the symbol `findIndex` matched and emits it on the flight object, and `stdio_server.js`
passes it through as `currency: f.currency || null` next to the price. All five display
sites decode instead of defaulting, `format_currency` renders a bare number when the unit
is unknown rather than falling through to the string `"None"`, and the frontend gains a
second formatter: `formatCurrency` stays as-is for figures computed from the corpus, which
are rupees by construction now that ingest refuses anything else, and the new `formatFare`
takes the unit as data for a provider-quoted fare. `FlightPrice.currency` in
`frontend/types/index.ts` is now `string | null`, which is what the wire has always
actually carried.

*Two ordering facts that are load-bearing.* The screen runs **before**
`deduplicate_observation_batch`, at both call sites, because the de-duplicator keeps the
*lowest* fare in an identity group: a group holding the same flight quoted once at 70
dollars and once at 6,000 rupees collapses to the dollar row, which the screen then drops
— losing a good observation to a bad one. And the screen runs before `rows_submitted` is
taken, because otherwise every batch containing a foreign fare would publish
`persistence_error: submitted 3, database persisted 2`, a fabricated database fault on the
very field added to stop fabricated persistence claims. The refusal is published as its own
metadata instead — `refused_rows` with `refused_currencies`, so a batch reading
`{"USD": 20}` says plainly that Google served the page in dollars.

*Two things deliberately not changed.* The read predicate `has_authentic_provenance` still
mirrors the loaders' SQL, which has no currency condition; folding the rule in there would
recreate exactly the drift `provenance.py` exists to prevent, and would silently exclude
every already-stored row, whose `currency` has never been measured. And the JS
`basePrice = 0` fallback stays: it is already inert on both paths (ingest skips
`price <= 0`, `normalize_mcp_flight` returns `None`), while emitting `null` would make
`float(flight.get("price", 0.0))` raise `TypeError` inside the batch-level `try` and lose
the **whole batch**.

*Consequence for fixtures, which is itself a property worth having.* A test that submits a
row must now carry a readable currency and a fare inside the window. Five fixtures across
three shipped modules needed that, and they were found by grepping for
`insert_observations|format_payload|flight_search_service.search(` **before** running
anything — each would otherwise have failed on an empty batch, which reads like a
de-duplication or timestamp bug rather than a fixture gap. Each site now carries a comment
saying why the currency is there.

*Measured.* `backend/tests/test_observation_currency_guard.py` is new: 23 test functions,
61 cases with parametrisation, over the `decode_currency` boundary, the refusals and their one-reason-per-row accounting, the
inclusive window bounds, idempotence, non-mutation of the caller's rows, the untouched read
predicate, the call-site metadata, and the display path end to end (a card with no currency
must not render with a `₹`; a `"$"` card renders `$58.00`; a cached row stays unstated).
Together with the modules the change touches —
`test_observation_dedup.py`, `test_flight_stabilization.py`,
`test_chat_search_parity_regression.py`, `test_live_flight_search_fidelity.py`,
`test_prediction_pipeline_regression.py`, `test_historical_platform.py`,
`test_booking_curve_pipeline.py`, `test_route_catalog.py`, `test_longitudinal_integrity.py`,
`test_curve_identity_gate.py` and `test_canonical_forecast_v2.py` — that is
**168 passed / 0 failed / 0 skipped** in one run. `tsc --noEmit` over the frontend exits 0.
**No database was touched.** The 156 dollar rows are still in `price_history`; the guard
stops the next one, and it is one more reason the wipe in §46 is the cheaper option.

---

**49. The collection cadence and the label definition were designed independently, and
they do not fit: 5 of the 13 departure buckets can never carry a label at any horizon
the system trains. Measured, not argued. Separately, a run that stores nothing
labellable now goes red instead of green.**

*The question.* Only a repeat visit to the same flight creates a supervised label, so
the collector's cadence decides whether the corpus can ever become trainable. §46
measured the existing corpus at zero labels and attributed that to the curve-identity
switch; that left the forward-looking question open. Does the cadence the collector
*will* run on, once migration 001 is applied and `departure_time` starts landing,
actually produce labels?

*The geometry.* `_collect_popular_routes_async` recomputes `target_date` on every run
as `now + days_out`, so departure dates roll forward with the calendar. A given
departure date `D` is therefore visited **once per bucket**, on day `D − b` for each
bucket `b`, and never twice at the same offset. `price_at_horizon(h)` is a forward
`merge_asof` taking the earliest observation on the same curve in the window
`[t + h, t + h + lag_tolerance_days(h)]`, with `lag_tolerance_days(h) = max(0.5, h/2)`.
Substituting `t = D − b` gives the condition exactly: a row at bucket `b` is labellable
at horizon `h` if and only if some other bucket `b′` satisfies
`b − h − tol(h) ≤ b′ ≤ b − h`. Labels come from *pairs of buckets*, not from the passage
of time.

*The measurement.* Live buckets are `[1, 2, 3, 5, 7, 10, 14, 21, 30, 45, 60, 75, 90]`
(`backend/route_catalog/routes.yaml`) and `SUPPORTED_TRAINING_HORIZONS` is `(1, 3, 7)`.
Simulating 140 daily runs over that bucket set and passing the frame through the
project's own `attach_future_target`:

| bucket | h=1 | h=3 | h=7 |
|---|---|---|---|
| 1 | — | — | — |
| 2 | ✓ | — | — |
| 3 | ✓ | — | — |
| 5 | — | ✓ | — |
| 7 | — | ✓ | — |
| 10 | — | ✓ | ✓ |
| 14 | — | ✓ | ✓ |
| 21 | — | — | ✓ |
| 30 | — | — | ✓ |
| 45 | — | — | — |
| 60 | — | — | — |
| 75 | — | — | — |
| 90 | — | — | — |

Buckets **{1, 45, 60, 75, 90}** — 5 of 13, and **38.5%** of every run's 715 searches —
can never carry a label at any supported horizon. Bucket 1 at least supplies the label
for bucket 2; **45, 60, 75 and 90 participate in the join on neither side**, so 4 of 13
buckets are pure cost. Overall labelled share is 15.3% at h=1, 30.0% at h=3, 29.1% at
h=7.

*And the h=1 labels are lost to scheduler jitter, which is worse than it sounds.* Where
`b − b′` equals `h` exactly, the pair needs the later observation to be at least `h`
days after the earlier one *by wall clock*. Two things push it under: GitHub Actions
starts scheduled runs late by a random amount, and within a run the collector iterates
buckets in ascending order, so the `b−1` search happens *earlier in the run* than the
`b` search. Re-running the same simulation with a 0–20 minute run delay and a 20-second
per-search offset drops h=1 from 1,112 labelled rows to **520** — every cell whose only
partner sits at an exact `h`-day remove (b=2 and b=3 at h=1, b=10 at h=3, b=21 at h=7)
loses slightly over half its supply, while cells that also have a slacker partner barely
move (b=10 at h=7 goes 532 → 528, because b′=1 and b′=2 absorb what b′=3 loses).
h=1's entire label supply is of the exact-difference kind — its only possible partner is
`b−1` — so h=1 is a coin flip on Actions scheduling.

*What was fixed, and what is a decision for you.* The reporting half is fixed here; the
bucket set is in `## Open work` because it changes how much you scrape.

`deduplicate_observation_batch` has always returned an `unindexable` count, and its own
comment describes those rows as "exactly the rows that can never be labelled". Its only
production caller — `flight_search_service.py` — discarded the number. So a collection
run in which the provider published no departure times stored its rows, reported
`rows_inserted: N`, wrote `search_success: True`, logged "Ingestion batch complete.
Stored N observation(s)", and exited 0, while growing the corpus by nothing that can
ever be trained on. That number is now surfaced as `unidentified_rows` in the search
metadata and logged per search, aggregated by the collector, and **gated**: alongside
the existing zero-rows `RuntimeError`, a run whose every confirmed row lacks a complete
booking-curve identity now raises, which `run_pipeline.py` turns into a red workflow.

The gate counts only rows from a *fully confirmed* insert. On a partial write
`unidentified_rows` is measured over the rows submitted and `rows_persisted` says how
many landed, with nothing saying which — attributing the shortfall either way invents a
fact, and attributing it to the unidentified bucket would fail a run that did store
labellable rows. Such a batch is counted in neither bucket, and the snapshot publishes
`rows_identity_known` as the denominator so `rows_identified` and `rows_unidentified`
cannot be read against `rows_inserted` by mistake.

*Measured.* Three new cases in `backend/tests/test_historical_platform.py` (the gate
firing and naming the five keys; a partially-unidentified run passing with both counts
recorded; a partial write leaving the split unknown). Falsification: replacing the gate
condition with `if False:` fails `test_run_storing_only_unidentifiable_rows_fails` and
nothing else, and the file was restored byte-identically afterwards. Together with the
modules the change touches — `test_historical_platform.py`, `test_observation_dedup.py`,
`test_booking_curve_pipeline.py`, `test_curve_identity_gate.py`,
`test_observation_currency_guard.py` — **124 passed / 0 failed / 0 skipped**, plus
**42 passed / 0 failed / 8 skipped** over the sixteen other modules that reference
`flight_search_service` or the collector. I then widened the sweep to every module that
touches the predictor or a model artifact, twenty-two of them, and got **150 passed /
0 failed / 12 skipped** over twenty-one; the twenty-second,
`backend/tests/test_system_hardening.py`, imports `fastapi.testclient` and cannot run in
this sandbox at all, so it stays on your Windows list. That widened sweep turned up one
module that could not pass anywhere; §50 has it. **No database was touched and no route
configuration was changed.**

*One more thing this uncovered, recorded rather than fixed.* `backend/dataset/collection_strategy.py`
and `backend/services/route_collection_strategy.py` are imported by tests only — neither
is on the production path — and the first declares
`TARGET_COLLECTION_HORIZONS = [90, 75, 60, 45, 30, 21, 14, 10, 7, 5, 3, 2, 1, 0]`, a
*different* bucket list from the live one, including horizon 0 which
`attach_future_target` refuses by construction. A future reader wiring up the plausible-
looking module would get a cadence the labeller cannot use.

---

**50. A shipped test had been unable to pass since two earlier fixes landed, for two
independent reasons, and nobody noticed because nobody had run it. It is the only test
that inspects the live feature dict on the search path.**

Widening §49's verification sweep to every module that touches the predictor turned up
exactly one that fails rather than skips:
`backend/tests/test_price_prediction_features.py::test_zero_synthetic_features_pipeline`,
whose whole job is to assert that the features reaching the model are derived,
provider-sourced, or `NaN` — never a synthetic default. It asserted
`len(captured_features) == 1` and got 0. Two separate causes, either one sufficient:

*Cause one — a stale transport envelope.* The test monkeypatches
`flight_data_service.search_flights` with a bare `{"data": [...]}`. Fixing the first of
§3's four silent-success shapes — a transport returning an empty list instead of raising,
so that a scraper crash read as "no flights today" — meant giving the transport a
discriminated result: `data` / `status` / `error` / `error_kind` / `attempts`, built by
`flight_data_service._result`. The search service was made to refuse a result carrying no
`status`, on the reasoning that a transport which answers without one cannot be vouched
for and must be treated as broken rather than as an empty market
(`flight_search_service.py:419`). That sentinel fired on the test's own mock, so the
search fell through to the DB cache (also mocked empty) and the predictor was never
reached. The mock now mirrors `_result` exactly, with a comment saying why the envelope
must not be trimmed back down.

*Cause two — a missing Class B gate.* With cause one fixed the test still fails, because
§12's quarantine makes the predictor refuse to serve when there is no audited artifact on
disk: `predict` returns before a feature vector is ever built, so `captured_features` is
empty for a reason that has nothing to do with synthetic values. §44 already did exactly
this for `test_prediction_live_search.py` — "one test gated, not fixed" — and the ~12-file
Class B gating pass recorded in `## Open work` item 3 was meant to catch the rest; this
module was missed by both. Its sibling `test_prediction_zero_synthetic.py` — same
assertion, entering through `prediction_service.predict` instead of
`flight_search_service.search` — was gated correctly, with a docstring spelling out this
exact failure mode. The gate is now on both, and the docstring records that they are
counterparts so neither gets deleted as a duplicate of the other.

*What this costs, stated plainly.* Both tests now skip until you train a model, and
between them they are the only coverage that reads the actual dict handed to the
predictor. While they skip, the no-fabrication claim on the feature path rests on the
layers underneath — `test_zero_synthetic_data.py` on the normalizer,
`test_missing_values.py` and `test_feature_vector.py` on the builder — none of which sees
that dict. **Both belong on the list you re-run once a model exists**, and a green skip
here is not evidence of anything.

*The general lesson, which is the reason this is written down.* A test that cannot run
reports as "not failing", and this log now has that shape three times: §13's acceptance
gate that could not fail, §39's readiness tool that fabricated its own input rather than
admit it had none, and now a module whose fixture went stale two fixes ago and was never
executed again. A suite is only as honest as the count of tests that actually ran, which
is why every figure here is quoted as passed / failed / **skipped**.

---

**51. A run could store one row out of 715 attempted searches and still exit 0. The two
existing gates check whether the corpus grew at all and whether any of it is labellable;
neither asks whether the day's collection is a *day's* collection. That is now a
failure-rate ceiling, and the run goes red above it.**

*The hole.* §49 added a gate for a run whose every confirmed row is unlabellable, and an
older one fires when nothing is stored. Between them sits the case that neither sees: a
run where a handful of searches succeed and the rest fail. One live search out of 715
stores its rows, clears both gates, writes a snapshot recording `search_success` and
exits 0 — the workflow is green and the day looks collected. The information was already
being computed: `if failed_searches:` logged an error naming the provider and persistence
counts, and nothing acted on it. A broken selector, an expired session, a provider
rate-limiting the scraper, and a partly-migrated schema all produce exactly this shape.

*Why a rate and not a count.* A count cannot be set without knowing how many searches the
day planned, which changes with the route list and the bucket set — the very two things
Open work item 2 asks you to change. The ceiling is `failed / attempted`, read from
`SCHEDULER_MAX_SEARCH_FAILURE_RATE` with a default of 0.5, following the clamp pattern
`SCHEDULER_MAX_RUN_MINUTES` already uses. One of the four tests sets that variable and
asserts the gate fires at the new value, so the ceiling is a control rather than a
documented intention.

*Why failures and not the live share.* The obvious formulation — gate on the fraction of
searches that came back live — is wrong, and it took a test to see why. `STATUS_EMPTY` is
a real answer: the provider was reached, the page parsed, and the route has no flights that
day. Counting empty against the live share would turn a genuinely quiet market red, which
is the same category of error as the fabrications this log exists to remove, pointed the
other way. Empty is excluded from the numerator, and the residual case — mostly empty with
a few live, which is what a silently broken parser looks like — gets a warning naming the
shape rather than a raise, because separating it from a quiet market would duplicate the
judgement `STATUS_EMPTY` already encodes and get it wrong in a second place. A run that is
empty the whole way through stores nothing and the zero-rows gate already owns it.

*What the gate cost me, which is the part worth reading.* It broke one of §49's own tests.
`test_partial_write_leaves_the_identity_split_unknown` drove a single search that submitted
nine observations and stored two, and asserted the run completed. Under the new ceiling that
is one failed search out of one — a 100% failure rate — so the run now raises. The
tempting fix was a minimum-sample rule: do not judge a rate until N searches have run. I
rejected it. It adds a knob that can be misconfigured, and the case it would suppress —
a few searches, most of them failing — is precisely the case the gate exists to catch.
The gate is right; the *fixture* was single-search, and a rate over one sample is
all-or-nothing by arithmetic, not by defect.

So the test was rebuilt to isolate what it actually claims: three clean searches alongside
the partial one, a 25% failure rate that clears the ceiling, and the assertion that
`rows_identity_known` is 15 rather than 17. That is a strictly stronger statement than the
original made. The single-search version could only show the identity counters sitting at
zero, which is equally consistent with the accumulator never having run at all; the new
one shows the two rows that did land being *excluded* from a denominator that is otherwise
populated. The old scenario did not lose its coverage — it became its own test, asserting
that a one-of-one partial write is a red run, with the rejected minimum-sample alternative
written into the docstring so the next reader does not re-propose it.

*An honest limitation, recorded rather than fixed.* All three gates raise before the
snapshot metadata is written, so the run that most needs a diagnostic row leaves none.
This is pre-existing — it is true of the two older gates as well — and it is inert today,
because the `snapshot_metadata` table does not exist until you apply migration 001.
Restructuring the function so a failed run still records its metrics before raising would
churn code that is now covered by twenty-five tests, for a benefit nothing can read yet.
The full reason string goes to the GitHub Actions log in the meantime, and one of the new
tests asserts `insert_snapshot_metadata` is *not* called on a failed run, so the current
behaviour is pinned rather than assumed. **When migration 001 lands, the follow-up is to
write the metadata row first with `search_success: False` and the reason string, then
raise** — and to change that assertion in the same commit, which is what will stop the
change from being made silently.

*Measured.* `test_historical_platform.py` — **25 passed / 0 failed / 0 skipped**, up from
21 tests before this section. Then the gate was falsified: with its condition disabled,
exactly three tests fail —
`test_run_with_a_token_yield_fails_even_though_rows_were_stored`,
`test_the_ceiling_is_configurable_and_the_gate_reads_it`, and
`test_a_run_whose_only_search_partly_wrote_fails_the_yield_gate` — and the other twenty-two
still pass, including the two that read `search_failure_rate` out of the snapshot, since
those keys are written outside the gate. `scheduler.py` was then restored and confirmed
byte-identical by SHA-256. Across the six modules that reference the scheduler, the
collector, or the curve-identity gate: **135 passed / 0 failed / 0 skipped**. **No database
was touched and no route configuration was changed.**

---

**52. Every evaluation run wrote timestamped artifacts into the tracked repo tree, and
the path it wrote to existed in four independent copies. The fourth copy is the one that
mattered: the health check that reports the results directory as writable was probing a
directory the run never used, and creating it as a side effect.**

`backend/evals/results/` holds 32 tracked files from sixteen runs on 2026-07-24. It was
never gitignored, so every execution of `test_ai_evaluator_smoke_run` added two more files
to the working tree — which is how thirty-two of them came to be in the index. Same shape
as `test_dataset_exporter_and_quality_report` and the same fix, but with one extra defect
underneath it.

The directory path was defined in four places. `EvaluationConfig.output_directory` was the
nominal default; `environment.py` held the literal `"backend/evals/results"`; `doctor.py`
printed a third literal; and `EnvironmentInspector.inspect()` read the module-level default
rather than the caller's config. All four were CWD-relative, which is the recurring defect
class in this repo — the house fix is to anchor to `__file__`, as `backend/utils/report_paths.py`
already does — so the directory materialised wherever the process happened to start.

The fourth copy is the operative one, and it is worth being precise about why. That check
*creates* the directory it probes. So while it read the module default, the tracked
`backend/evals/results/` was re-created on every single run no matter what directory the
caller had configured, and the "writable" row it published described a directory the run
had never written to. A caller could redirect the output correctly and still see the
tracked path re-appear and a health row about the wrong location. `inspect()` now takes
`output_directory`, both callers pass theirs, and the row names the resolved path so the
doctor prints what was actually checked.

While in there: `os.makedirs(exist_ok=True)` not raising does not prove a directory is
writable — it returns quietly for an existing directory with no write permission, which is
exactly the condition that row claims to have tested. The check now writes and removes a
`.write_probe`, so "Results directory is writable" is a measurement rather than an
inference.

*The redirect was asserted, not assumed.* `assert summary["total_cases"] == 6` passes
whether the artifacts land in `tmp_path`, in the default directory, or nowhere at all, so
on its own it would not have noticed `output_directory` being ignored again — and being
ignored in a second place is precisely what had happened. The smoke test now asserts that
exactly one timestamped run directory exists under `tmp_path`, that it contains
`summary.json` and `report.md`, and that the filesystem health row names `tmp_path`.

A deliberate non-change: four test call sites still call `inspect()` with no
`output_directory`, so they transiently create and delete a `.write_probe` in the real
results directory. Nothing persists, the directory is now gitignored, and those calls are
the only coverage of the default path. Removing them would trade real coverage for nothing.

*Two coordinator verdicts had been asserted in this changelog and pinned by nothing.*
§26 claimed that a run measuring nothing cannot pass and that a schema-invalid benchmark
cannot pass. The first was covered only conditionally — `test_evals_v2.py` runs the real
smoke suite, where the deterministic evaluators do execute, so its `executed == 0` branch
had never been taken on any machine. Both branches now have a test that takes them
deliberately, in `test_evals_resilience.py`. The first stubs the registry to a single
evaluator returning `INFRASTRUCTURE_UNAVAILABLE` with `passed=True` — the status a missing
credential produces, and the reason such results were once counted as executed *and* as
passes — then asserts `executed == 0`, `overall_success_rate is None`, a `FAIL` verdict,
and all four headline metrics `None`. That is the state a CI runner with no keys is *in*,
which is what made the old green report worthless rather than merely wrong. The second
stubs the loader into reporting a duplicate-ID schema error and the registry into a single
passing evaluator, so `failed_count` is 0 and the rate is a clean 100.0, and asserts the
verdict is still `FAIL`. Written against the real registry it passed for the wrong reason:
an evaluator fails in a sandbox with no database, so `FAIL` arrived either way and the
branch under test was never exercised. Stubbing the registry is what makes the schema-error
branch the only possible source of the verdict.

*Measured.* Across `test_evals_v2.py`, `test_ai_evaluation.py`, `test_evals_resilience.py`
and `test_evals_accuracy.py`: **56 passed / 0 failed / 0 skipped**, the 54 that existed
before plus the two above. `backend/evals/results` held sixteen entries before the sweep and
sixteen after — a `diff` of the before and after listings is identical, so a full smoke run
now leaves the tracked tree untouched — and the run's own health row read
`Results directory is writable (/…/tmp/tp_rk9f6mev/results)`. Three falsifications, each
firing on exactly its own test and no other: dropping the `inspect()` pass-through fails
`test_ai_evaluator_smoke_run` with the tracked path in the message; restoring `else 100.0`
fails the skipped-run test; deleting the `INVALID` branch fails the schema-invalid test on
"a 100% success rate on a benchmark whose schema did not hold is still a FAIL". Both
temporarily-modified files were restored and confirmed byte-identical by SHA-256. Eleven
further modules outside the eval package — the scheduler, collector, curve-identity,
currency-guard, longitudinal, forecast-metrics and dataset-pipeline suites — ran
**128 passed / 0 failed / 2 skipped**, the two skips being the known model-gated cases.
**No database was touched and no route configuration was changed.**

*An accident of mine, recorded because you are about to review the diff.* Restoring
`backend/evals/evaluator.py` after one of those falsifications, I ran
`git checkout -- backend/evals/evaluator.py`. That restores from the **index**, and the
index here is your `git add -A` snapshot from before most of this fix pass — so it silently
replaced the file with a version predating §26 and destroyed about ninety-seven lines of
earlier work. Your index was not modified: `git checkout -- <path>` writes only the working
tree, so the snapshot you hold is intact, and nothing else in the tree was touched. The file
was rebuilt from the regions still verbatim in the session record, from §26's specification,
and against the 54 existing tests as the acceptance oracle; it compiles and those 54 pass
unchanged, plus the 2 new ones. What is *not* recovered is prose: the module docstring and
the head of `_score_pct`'s docstring — roughly twenty lines of comment — are re-authored
rather than original. Behaviour is verified; that wording is not the wording that was there.
**Read `backend/evals/evaluator.py` more closely than the rest of the diff.** The rule I
should have been following, and now do: never `git checkout`, `git restore`, `git stash` or
`git reset` in this repo; copy to `/tmp/<name>.SAFE`, keep the `sha256sum`, restore with
`cp`, and verify with `sha256sum -c`.

**53. A request body could name the account a booking belonged to. The endpoint has no
auth dependency by design, so an unauthenticated caller could file a booking — passenger
names, passport and Aadhaar numbers included — against any account id they chose to type,
and the ownership checks on the other four booking endpoints then read that
attacker-supplied value as truth. Separately: the frontend attached no `Authorization`
header on any call, so all eleven token-protected endpoints were unreachable from the
app.**

`CreateBookingRequest` carried `user_id: Optional[str] = None`, and `create_booking`
wrote it straight into `bookings.user_id`. Naming the defect precisely matters here
because the obvious description is wrong: the hole was not "the create endpoint has no
authentication". Guest checkout is a real product decision — `app/booking/page.tsx` does
not gate on a session — and a hard `Depends(get_current_user)` would turn every anonymous
checkout into a 401. The hole was that **ownership arrived in the body**, and
`GET /booking/{id}`, `POST /{id}/cancel` and `GET /{id}/download` all authorise by
comparing the session's id against that column. Forge the column at creation time and
those three checks pass for the forger. That is closed: `user_id` is removed from the
request model and set only from the subject of a verified bearer token, via a new
`get_current_user_optional` dependency. An anonymous booking now stores NULL, which is
the honest record of "we do not know who this is" — and which the ownership checks
correctly refuse to hand to anybody, including the guest who created it.

The field was **removed rather than ignored**, deliberately. Pydantic V2 discards unknown
keys by default, so a stale deployed client still sending `user_id` has it dropped
silently instead of receiving a 422; and a reader of the model now sees the rule instead
of a field whose value is quietly unused.

*The breaking half is documented, not shipped.* Requiring an account to book is a
two-line change and the endpoint's docstring names both lines — swap the dependency for
`get_current_user`, and have the booking page redirect to login when
`supabase.auth.getSession()` returns no session — with the warning not to make the first
change without the second. That decision is yours, not mine to make unilaterally.

*The second finding, measured en route.* `frontend/lib/api.ts::apiRequest` set only
`Content-Type`. No caller passed an `Authorization` header and the helper never added
one, so every endpoint behind `Depends(get_current_user)` — three in `alerts.py`, two in
`auth.py`, three in `booking.py`, two in `user.py`, plus the profile pair — was
unreachable from the browser. Fixed by an `authHeader()` helper that reads the current
Supabase session and contributes nothing when there is none. Checked before shipping it:
`backend/main.py:79` already lists `"Authorization"` in the CORS `allow_headers`, so
attaching the header cannot fail preflight, and an endpoint that ignores the header is
unaffected. Reachability is worth stating exactly, because it is easy to overclaim: the
alert functions are exported and `hooks/useAlerts.ts` calls them, but **no page imports
that hook**, so the alert endpoints have no live caller today. The api.ts comment says so
now; an earlier draft of it claimed `/alerts/subscribe` "is the one this client actually
calls", which was not true.

*And a third, of the same shape with the opposite symptom.* `POST /alerts/subscribe` also
took `user_id` from the body. It **does** require a token and did reject a mismatched
body value with 403, so the forgery route was closed there. The live bug was the absent
case: `payload["user_id"]` was set only `if req.user_id`, and nothing in this repo ever
sends the field — so every alert a signed-in user created was stored with a NULL owner
while the token proving who they were sat unread in the request. `GET
/alerts/user/{user_id}` filters on `user_id` and `DELETE /alerts/{id}` refuses a row it
does not own, so the three alert endpoints were useless *as a set*: create an alert, and
neither you nor anyone else could ever list or delete it. The duplicate-suppression
query was gated on the same field, so it never ran either. Ownership now comes from the
token unconditionally, and `user_id` is gone from `AlertRequest` and from
`SetAlertRequest` in `frontend/types/index.ts`.

*A status code that was answering the wrong question.* `get_current_user` declared
`authorization: Optional[str] = Header(...)`. The `...` makes the header a **required
request parameter**, so a call carrying no token at all was rejected by FastAPI's
validation layer as **422 Unprocessable Entity** before the function ran. That is not the
answer to "you are not logged in", it is not the status any client branches on, and it
made eleven endpoints look like they had malformed schemas rather than missing
credentials. `Header(None)` moves the decision inside the function, where a missing token
is a 401 like every other unauthenticated case. One more line was needed: the explicit
401s sit inside a `try` whose `except Exception` re-raises everything as a 401 with a
different message, so `except HTTPException: raise` now precedes it — the pattern the
routers already use.

*Three fabricated values on the payment screen, from an assumption already removed
server-side.* `backend/routers/booking.py::_extract_price_details` used to assume
`base == 85% of total` and wrote that invented split into `bookings.base_fare` and
`bookings.taxes`, the two columns a refund is computed from. It stores NULL now when the
provider sends no base fare — a change made during the earlier ingest-honesty sweep and,
until this entry, recorded only in that function's docstring rather than here. The
display half was still live in two places. `app/booking/page.tsx` fell back to
`Math.round(price * 0.85)`, and
`app/checkout/page.tsx` showed `price * 0.85` and `price * 0.15` **unconditionally** —
without so much as checking whether a base fare existed — labelled "Base Intelligence
Fare" and "Taxes & Network Fees" on the screen where the user authorises the charge. Most
Google Flights results carry no base fare, so that breakdown was invented for nearly
every checkout. Both pages now read the real value off the stored offer and render "Not
itemised by the airline" when there is none. The same file also had `booking?.origin_code
|| "DEL"` and `|| "BOM"`, which rendered a route the backend had stored as NULL — stored
that way precisely because it could not be parsed — as a confident "DEL ➔ BOM"; both are
now "—".

*Measured.* `backend/tests/test_booking_ownership.py` is new: 14 tests over the two
request contracts, both write paths, and the four dependency behaviours. Each was
falsified by reverting the production code and confirming the expected failure —
reinstating body-supplied booking ownership fails 4, reinstating the body-gated alert
ownership fails 3, dropping `except HTTPException: raise` fails 1, dropping the
missing-header 401 fails 1. The third of those is why one test asserts on the exception
*detail* rather than the status: the generic handler answers 401 too, so a status-only
assertion could not have detected the swallowed raise and would have stayed green. All
three touched routers were restored from `/tmp/*.SAFE` copies and verified byte-identical
by `sha256sum -c` afterwards. Across thirty modules in three batches: **138 passed / 1
skipped**, **98 passed / 1 skipped**, and **57 passed**. Two further modules
(`test_live_search.py`, `test_prediction_resilience.py`) are import-blocked in my sandbox
only, both on `from fastapi.testclient import TestClient` — they need the real library
and are in your Windows list. `tsc --noEmit` exits 0. **No database was touched.**

## Open work, in priority order

1. **Train/serve skew — closed, pending one migration you have to apply.** §25 has
   the forecast-path repair and the contract de-duplication. `departure_time` is
   the remaining dependency and it is code-complete: migration 001 adds the column,
   `format_payload` normalises and writes it, `get_db_payload` submits it, and
   `database.py` derives `hour_of_day` / `is_peak_hour` from it. Until you apply
   migration 001 those two declared features are NaN for 100% of the training
   corpus while the serving path supplies a real departure hour — and an insert
   carrying `departure_time` will be rejected by a database that lacks the column.
   Applying the migration is the last step, and it is yours.

   **Order matters here, and it did not before §45.** Apply the migration only with
   §45's labeller fix in your tree. The column arrives present and NULL on all
   32,709 existing rows, and until that fix `_price_at_offset` pooled NULL with NULL
   and handed one departure a sibling departure's later fare as its label. The
   migration was the trigger for that, not the cure. §45 has the measurement.
2. **Decide the departure-bucket set before you start the 3–4 week collection — this
   one is a decision, not a fix, because it costs scraping time.** §49 measures it:
   under today's 13 buckets, 5 of them (1, 45, 60, 75, 90) can never carry a label at
   h=1, 3 or 7, and four of those five never participate in the label join on either
   side. That is 38.5% of every run's 715 searches producing rows the trainer cannot
   use. h=1 is additionally a coin flip on GitHub Actions start-time jitter, because
   its only possible partner bucket is `b−1` and the collector visits `b−1` earlier
   within the same run.

   The verified replacement is
   `[1, 2, 3, 5, 7, 10, 14, 22, 30, 38, 46, 54, 62, 70, 78, 86]` — an even step-8 tail
   above 14. It makes 15 of 16 buckets labellable (bucket 1 becomes label-only, feeding
   h=1 for bucket 2), drops dead rows from 38.5% to 6.2%, raises h=7's labelled share
   from 29.1% to 64.9%, and the whole step-8 tail is jitter-immune because every pair is
   separated by more than the horizon.

   **The cost is why it is yours.** 16 buckets × 55 enabled routes is 880 searches a
   day against today's 715, and 715 Puppeteer scrapes at ~20 s each already consume
   essentially all of `SCHEDULER_MAX_RUN_MINUTES = 240` (715 × 20 s ≈ 238 min). So the
   bucket set cannot be widened at the current route count. **The affordable pairing,
   and my recommendation, is to cut the enabled route list to ~20 and adopt the
   16-bucket set:** ≈320 searches, ≈107 minutes, well inside the budget, and it matches
   the plan you already described — collect over a fixed small route set for 3–4 weeks.
   Twenty routes × 16 buckets also yields denser per-curve histories than 55 × 13 does,
   which is what a booking-curve model actually needs. Both lists live in
   `backend/route_catalog/routes.yaml`; nothing in code needs to change.
3. **Remaining loose ends from `AUDIT-ADDENDUM.md` — all three now closed.** The
   `Could not infer format` warning from `booking_curve_definition.py` was not a
   warning to silence; §31 records what it was hiding and fixes sixteen call
   sites. The ~12 Class B test files now gate on `requires_trained_model()` /
   `requires_forecast_metrics()`, including `test_prediction_forecast.py`, which
   §28 turned into a refusal case by removing the invented inputs. The two
   mock-registry tests no longer assert a 16-element `expected_features` list. The
   two `/system` items that were here — `/health` raising when both load and train
   fail, and `refused_artifacts` / `load_error` not reaching `/system` — are closed
   by §5 and §29.
4. **Repo hygiene — closed.** `backend/scratch/` turned out to be fifty tracked
   files rather than the six the audit named, two of them load-bearing. §32 has
   the full account.
5. **Regenerate the stored validation report.** §34: the report the API serves is
   dated `2026-07-22`, so `readiness_score: 70` / `overall_status: FAIL` describes
   the pre-fix pipeline. This needs a run against your database, so it is below.

---

## Yours to do

Rotate every credential named in §1 — the Supabase `service_role` key and
Postgres password first, since that key bypasses row-level security. Removing
them from source does not un-leak them; they are in the git history and were
briefly public.

Decide whether booking should require an account. §53 closed the part that was a
security hole — ownership can no longer be asserted by a request body — but left guest
checkout working, because making it require a session is a product decision and doing it
carelessly turns every anonymous checkout into a 401. If you want it, the two lines are
named in the `create_booking` docstring: swap `get_current_user_optional` for
`get_current_user`, and redirect to login from `app/booking/page.tsx` when
`supabase.auth.getSession()` returns no session. Do not do the first without the second.
Worth knowing either way: because the old frontend never sent `user_id`, **every booking
already in your database has a NULL owner**, so no existing booking can be fetched,
cancelled or downloaded by anyone — those three endpoints authorise on that column. If
you want the ones belonging to real accounts to work again, they need a backfill you run
by hand.

Run `npm install` in `frontend/` and commit the refreshed lockfile — `npm ci`
currently falls back because the lockfile is out of sync with `package.json`.

Decide what `backend/india-flight-mcp` is: it is a nested repository with its own
git directory, which is why `git add -A` keeps re-adding a broken gitlink. Either
make it a proper submodule or vendor it.

Read `backend/database/migrations/001_price_history_and_run_metadata.sql` before
applying it, and apply it yourself. I have not touched your database.

Regenerate the validation report, for the reason in §34 — the one the API currently
serves predates every fix in this log by six weeks, and its `readiness_score` is a
figure you would have to explain rather than cite. It needs your database, so it
has to be your run.

Untrack the four generated reports at the repository root:
`git rm --cached historical_data_report.json drift_report.json
feature_validation_report.json production_readiness_report.json`. §30 stopped them
being rewritten, but `.gitignore` cannot untrack a path already committed, and one
of them presents a stale `"overall_status": "FAIL"` to anyone browsing the repo.

Untrack the eval log that moved out of `backend/scratch/`:
`git rm --cached backend/scratch/evals/chat_evaluations.jsonl`. Same reason — §32
repointed the writer at a gitignored directory, which does not untrack the 21 KB
already committed.

Untrack the one-row dataset export the test suite wrote:
`git rm --cached -r backend/dataset/exports`. §39 has the reason — a CSV holding a
single fixture row, a manifest saying `total_rows: 1` and a quality report saying
`validation_status: PASS`, all three staged, and the file the readiness tool read
by default and called Dataset v2.0. They are deleted from disk and gitignored now.

Untrack the sixteen eval runs from July: `git rm --cached -r backend/evals/results`.
§52 has the reason — 32 files from runs on 2026-07-24, each one two artifacts a test
execution happened to drop in the tracked tree. The writer is redirected and the
directory is gitignored now, which does not untrack what is already committed.

Run `git add -A` before committing. 84 paths this fix pass deleted still read `AD`
in `git status` — staged as additions from your earlier `git add -A`, absent from
disk — so a bare `git commit` would reintroduce all of them, including 48
`backend/scratch/` paths, the 16 verification scripts, the two provider contract
tests §36 removed, and the three export fixtures in §39.

Run the tests this sandbox cannot. Two lists, and the second one matters more than it
looks. **Needs your venv, runnable today** — these fail here only because `fastapi`,
`xgboost` or `openai` are genuinely absent:

```
pytest backend/tests/test_system_hardening.py backend/tests/test_training_pipeline.py \
       backend/tests/test_training_reproducibility.py backend/tests/test_feature_importance.py \
       backend/tests/test_live_search.py backend/tests/test_prediction_resilience.py \
       backend/tests/test_production_validation.py backend/tests/test_booking_ownership.py -v
```

`test_booking_ownership.py` passes 14/14 in my sandbox against a stubbed pydantic, so
re-run it on the real library before you trust it: one of its tests turns on pydantic V2
discarding unknown keys by default, which is exactly the kind of behaviour a stub can get
wrong. It is in this list rather than the blocked one because it does not need a
`TestClient` — the other two here do, which is the only reason they fail in my sandbox.

**Needs a trained model, so it stays a skip until then** — and per §50 these two are the
only coverage that inspects the actual feature dict handed to the predictor, so a green
run without them is not evidence about fabricated features:

```
pytest backend/tests/test_price_prediction_features.py \
       backend/tests/test_prediction_zero_synthetic.py \
       backend/tests/test_prediction_live_search.py -v
```

Confirm they report `skipped`, not `passed`, before you train — a `passed` there would
mean a stale artifact is on disk. After you train, re-run them and read the result; that
is the point at which the no-fabrication claim on the feature path is actually tested.

Review the staged diff and commit. Nothing in this repository has been staged or
committed by me.
