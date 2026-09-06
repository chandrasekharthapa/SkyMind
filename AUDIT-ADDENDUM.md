# SkyMind Audit — Addendum

Companion to `AUDIT.md`. Covers the three areas requested after the first report: the data
ingestion pipeline end to end, an exhaustive synthetic/fake-data sweep, and a deep audit of the
chatbot (core and guardrails).

Same ground rules as the first report. Brutal candor, interviewer scrutiny assumed, and nothing in
the repo has been modified — this is still read-only reporting. Every claim below is marked
**[verified]** if I read the code or executed the measurement myself, or **[reported]** if it comes
from a delegated sweep that I did not independently reproduce. One subagent conclusion was wrong
and is corrected in §3.2 rather than repeated.

Audit date: 2026-08-31. Corpus and log measurements were taken against the files as shipped.

---

## Verdict up front

The three areas do not fail independently. They fail the same way, and it is worth naming the
pattern before the detail, because it is the single most useful thing in this document.

Every layer of this system converts an error into a plausible value and returns success. The
scraper cannot launch, so it returns an empty list, which is indistinguishable from a route with
no flights. The pipeline reads that empty result, backfills from cache, and counts cache reads as
inserts — which satisfies the only gate that could have caught it. The forecast validator tests
invariants that an earlier stage has already repaired into place. The chatbot's grounding check
returns "valid" for four of eight tools because those tools emit shapes it cannot read prices from.
The firewall defaults to ALLOW when its policy file is missing and logs `is_safe: true` next to the
UNSAFE verdict that should have blocked.

None of these are missing features. Every one of them is a *present* mechanism whose failure mode
is silence. That is why the CI is green, the row counts rise, and the dashboards report 95%
confidence over a corpus that has one distinct flight number.

There is real engineering in here — the circuit breakers, the single-flight cache-stampede
prevention, the determinism test, the zero-synthetic-data *policy* — and §5 is about how to talk
about it. But the honest summary of these three areas is that the pipeline does not ingest, the
"no synthetic data" guarantee is enforced everywhere except in the file that trains the model, and
the chatbot's safety layer is off.

---

## 1. The data ingestion pipeline

### 1.1 The failure chain, in order

I traced this stage by stage. Each numbered link is **[verified]** by reading the cited code.

**Link 1 — the scraper cannot start.** `backend/india-flight-mcp/src/providers/BaseProvider.js:30`
launches Puppeteer with a hardcoded path:

```js
executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
```

There is no environment-variable override and no fallback to a bundled Chromium. CI runs on
`ubuntu-latest`, so this path does not exist and the browser never launches. On any non-Windows
host — CI, Docker, a Linux VPS, a reviewer's Mac — ingestion is dead on arrival.

**Link 2 — the failure is laundered into a legitimate result.** The provider's `handleError`
returns `[]`. An empty array is exactly what a genuinely sold-out or unserved route returns, so
from this point forward no downstream code can distinguish "Chrome is missing" from "no flights
today."

**Link 3 — no retry, no signal.** `backend/services/flight_data_service.py:175-179` returns
`{"data": []}` on that empty result. Tenacity is in `requirements.txt` and used elsewhere; it is
not applied here.

**Link 4 — the fallback fills the hole.** `backend/services/flight_search_service.py:207-223`
sets a `DB_FALLBACK` marker and serves rows from cache. This is defensible behaviour for a *search
request* — the user gets something rather than an error page. It is not defensible for an
*ingestion run*, and the two paths share it.

**Link 5 — cache reads are counted as writes.** `backend/services/scheduler.py:125-130` adds those
fallback rows into `total_inserted`.

**Link 6 — the only gate is defeated.** `scheduler.py:157-159`:

```python
if total_inserted == 0:
    raise ...
```

This is the sole guard against a no-op ingestion run, and Link 5 guarantees it never fires. The
gate is not weak; it is measuring the wrong quantity. `total_inserted` counts rows *handled*, not
rows *newly observed*.

**Link 7 — the run reports success.** `run_pipeline.py` exits 0. The stale `global_model.pkl` is
re-uploaded to Supabase Storage, the scheduler logs a successful cycle, and row counts go up
because cached rows are re-written.

The net effect: a pipeline that has never ingested a single new observation on any Linux host
produces green CI, rising row counts, and a freshly-timestamped model artifact. Nothing in the
system's own telemetry can tell you otherwise.

### 1.2 Persistence has no idempotency guarantee

**[verified]** I grepped every UNIQUE and PRIMARY KEY constraint in
`backend/database/skymind_complete.sql`. Constraints exist on `airports`, `airlines`, `profiles`,
`routes` (`UNIQUE(origin_code, destination_code)` at line 298), `bookings.booking_reference`, and
the coupons table. The `price_history` table — defined at line 342, the one table the entire
pipeline writes to — has **no UNIQUE constraint of any kind**.

Consequences, in descending order of severity. There is no natural key, so re-running a day's
ingestion silently duplicates every row rather than upserting. `ON CONFLICT` cannot be used
because there is no conflict target to name, which means idempotency cannot be added at the query
level without a migration. And because Link 5 above re-writes cached rows, the duplication is not
hypothetical: the row count grows on every cycle whether or not new data arrived, which is
precisely the metric that makes the pipeline *look* healthy.

Also worth flagging: line 22 of the same file begins `DROP TABLE IF EXISTS public.price_history
CASCADE;`. A schema file that destroys the production observation table on execution is a
foot-gun sitting in the repo with no guard rail around it.

### 1.3 The training join produces zero rows for every horizon above 0

**[verified]** `backend/services/training_dataset_builder.py:85-91` builds the supervised set with
a default (inner) merge that pairs each observation against a later observation of the same flight
group. But the synthetic block that constitutes 86% of the corpus has exactly **one**
`recorded_date` per group. An inner join on a group with one date yields nothing for any horizon
greater than 0.

So the 1d, 3d, and 7d models are trained on whatever the small live block supports, while the 0d
model gets the full corpus — and the 0d target is set by `training_dataset_builder.py:70-72` to
`target_price = price`, i.e. the feature it is predicting. That is the leakage documented as
CRIT-1 in the main report, and this join behaviour is why the leak is load-bearing rather than
incidental: for horizon 0 the join is trivially satisfied and the label is the input.

### 1.4 Reproducibility is void: the corpus's own horizon field is overwritten

This is the finding I most want to draw attention to, because it resolves an apparent
contradiction and because it is a clean, self-contained story.

**[verified by measurement.]** `backend/database/database.py:163-164` does this to every row it
loads:

```python
today = pd.Timestamp.now().normalize()
df["days_until_dep"] = (df["departure_date"] - today).dt.days.clip(lower=0)
```

The stored `days_until_dep` column is discarded and recomputed from the wall clock at load time.
The function's own docstring three lines above reads *"Derives all features deterministically or
keeps them as np.nan. No synthetic default values are allowed."*

I measured the effect on the shipped corpus. `price_history_cleaned_2026.csv` holds 7,354 rows with
`departure_date` spanning 2023-01-01 to 2026-05-20. **Zero** of those dates are in the future.
After `.clip(lower=0)`, all 7,354 rows get `days_until_dep = 0`, and the derived
`urgency = 1/(days_until_dep + 1)` at line 175 becomes the constant 1.0 for the entire training
set. Two of the README's headline features — "Urgency Scores" and the booking horizon — are
constants at training time.

Meanwhile inference serves a genuine future horizon. A user searching a flight three weeks out is
scored by a model for which that feature was 0 in every training row. That is textbook train/serve
skew, and it is *caused by* the very function whose docstring promises determinism.

The apparent contradiction, and its resolution. My earlier measurement showed the stored
`days_until_dep` agreeing perfectly with `departure_date − recorded_at` — exactly 14 days across
all 6,328 synthetic rows, 0% disagreement. Re-measuring against the full cleaned corpus showed
83.4% *disagreement*. Both numbers are correct; they are measuring different things, and splitting
the corpus by block explains it:

| block | n | `departure_date − recorded_at` | stored `days_until_dep` | disagreement |
|---|---|---|---|---|
| synthetic (`HIST-000`) | 6,328 | 1 distinct value: **14** | 57 distinct, range 1–59 | **96.9%** |
| live | 1,026 | 5 distinct values | 5 distinct, range 3–46 | **0.0%** |

The live block is internally consistent — its horizon field matches its own timestamps, which is
what real observations look like. The synthetic block has a horizon column that varies from 1 to 59
while every row was recorded exactly 14 days before departure. Those two facts cannot both
describe real observations. The `days_until_dep` column in the synthetic block was generated
independently of the timestamps.

And it was generated to *look* right. I computed the correlation between the synthetic block's
`days_until_dep` and its `price`: **−0.8155**. Real fares do rise as departure approaches, so a
strong negative correlation is exactly the sanity check an author (or a reviewer) would run — and
it passes. The generator produced a plausible price-vs-horizon relationship and then contradicted
it with a constant `recorded_at` offset. This is the sharpest available demonstration that the
corpus is synthetic: not a missing value or an obvious placeholder, but a feature engineered to
survive the check a careful person would think to perform, while a check nobody thinks to
perform — does the horizon agree with the timestamps? — fails on 96.9% of rows.

The 0d model's shipped feature importances make the consequence concrete. From
`backend/ml/models/fare_forecast_0d.metadata.json`, top eight by importance:

```
price_change_3d        0.3744
airline_code           0.1629
price_change_1d        0.1063
origin_code            0.0798
week_of_year           0.0774
destination_code       0.0738
month                  0.0415
seats_available        0.0360
```

`price_change_3d` and `price_change_1d` are computed at `ml/features/booking_curve.py:70-71` as
`price − shift(price)` — the leaked deltas. Together they carry **48%** of the model. `days_until_dep`
and `urgency` do not appear in the top eight at all, which is expected: they were constants.

### 1.5 Pipeline findings summary

| # | Finding | Evidence | Severity |
|---|---|---|---|
| P-1 | Scraper hardcodes a Windows Chrome path; ingestion cannot run on Linux/CI/Docker | `BaseProvider.js:30` | Critical |
| P-2 | Scrape failure returns `[]`, indistinguishable from an empty route | `handleError`; `flight_data_service.py:175-179` | Critical |
| P-3 | Cache reads counted as inserts, defeating the only no-op gate | `scheduler.py:125-130` vs `:157-159` | Critical |
| P-4 | No UNIQUE constraint on `price_history`; no idempotency possible | `skymind_complete.sql:342` | High |
| P-5 | `days_until_dep` recomputed from wall clock; all training rows collapse to 0 | `database.py:163-164`, measured 7,354/7,354 | High |
| P-6 | `urgency` is the constant 1.0 across the entire training set | `database.py:175`, follows from P-5 | High |
| P-7 | Inner join yields zero rows for every horizon > 0 | `training_dataset_builder.py:85-91` | High |
| P-8 | Schema file drops the production observation table on execution | `skymind_complete.sql:22` | Medium |
| P-9 | No retry on the scrape path despite Tenacity being a dependency | `flight_data_service.py:175-179` | Medium |

---

## 2. Synthetic and fake data sweep

The request was to make sure there is no synthetic or fake data anywhere. The finding is more
interesting than a yes or no: **the codebase enforces a zero-synthetic-data policy in the request
path, and violates it in the training path and in the reporting layer.** The policy is real, it is
tested, and it is worth keeping on the resume. It just does not cover the places that matter most
for the ML claims.

### 2.1 Where the policy holds

**[verified]** `flight_normalizer.py` and `live_search.py` deliberately preserve nulls rather than
filling them, and degrade honestly when live data is unavailable instead of inventing prices. This
is a genuine design decision, consistently applied, and `test_feature_determinism.py` (100
iterations against the real pipeline) is a real test of real behaviour. Keep this.

### 2.2 The training corpus is generated

**[verified by measurement.]** `backend/database/supabase_upload_final.csv` — 6,328 rows, 86% of
the corpus:

| column | distinct values | value |
|---|---|---|
| `flight_number` | 1 | `HIST-000` |
| `seats_available` | 1 | `50` |
| `days_until_dep` | 1 | `14` |
| `is_live` | 1 | `False` |
| `cabin_class` | 1 | `Economy` |
| `currency` | 1 | `INR` |
| `departure_date − recorded_at` | 1 | 14 days |

All 1,008 distinct `recorded_at` values fall at exactly 00:00:00. Zero `day_of_week`/`month`
mismatches — consistent with dates generated programmatically rather than observed.

The airline signal is the clincher. All ten airlines have statistically indistinguishable price
distributions (means 9,118–9,533, with min and max agreeing within rupees). In the real Indian
market, IndiGo and SpiceJet do not price like Vistara and Air India; LCC and full-service carriers
are separable on price alone. Here they are not, which is the signature of a single random draw
with airline labels attached independently afterward.

This is *why* the leak in §1.3 dominates. The legitimate features carry approximately zero signal
by construction, so the only thing left for the model to learn is the leaked price delta. The
model is not badly tuned; it is correctly learning the one informative thing in front of it, and
that thing is the answer.

Note also that within the cleaned corpus the two blocks are distinguishable at a glance:
`HIST-000` for 6,328 rows versus 223 other flight numbers for the 1,026 live rows;
`cabin_class` = `Economy` versus `ECONOMY`. The live block is genuine data. It is 14% of the
corpus.

### 2.3 Fabricated values in the serving and reporting path

Three sites where the running system emits numbers that did not come from data. All **[verified]**
by reading the code.

**The model's output is overridden by a magic-number branch.** `backend/ml/price_model.py:516-520`:

```python
lowest_fare_anchor = snapshot.get("lowest_fare") or snapshot.get("current_price")
if lowest_fare_anchor and isinstance(lowest_fare_anchor, (int, float)) and lowest_fare_anchor > 0:
    if abs(price - 6097.73) < 1.0 or abs(price - 9300.0) < 1.0:
        drift_factor = {0: 1.0, 1: 1.08, 3: 0.96, 7: 1.03}.get(h, 1.0)
        price = float(lowest_fare_anchor) * drift_factor
band = max(120.0, price * 0.06)
```

When the model emits either of two memorised constants, its prediction is discarded and replaced
with the current fare times a hardcoded drift factor. The forecast shape a user sees — flat, then
+8%, then −4%, then +3% — is not a prediction; it is that dictionary. `9300.0` is also a test
fixture price, so the branch fires under test. The confidence interval is a flat ±6% with a ₹120
floor and an ₹800 lower clamp, not a model-derived interval.

An interviewer who finds this will ask why two specific float constants appear in a comparison, and
there is no good answer available. This is the single most damaging line in the repo.

**Displayed confidence is floored, and rises when data quality falls.**
`backend/services/forecast/confidence_engine.py:16-17`:

```python
eff_model_acc = max(70.0, min(99.0, model_accuracy))
eff_quality = max(0.5, min(1.0, snapshot_quality)) if is_live_market else 0.85
```

Confidence can never display below 70%. And the polarity is inverted: a *total* data outage scores
0.85, while degraded-but-real live data bottoms out at 0.5. The system reports more confidence
when it knows less. Defaults are `model_accuracy = 95.0, snapshot_quality = 1.0`, so an
uninitialised call renders as 95% confident.

**Training-set size is actively suppressed, not merely defaulted.**
`backend/services/system_info_service.py:54-57`:

```python
raw_samples = getattr(predictor, "dataset_size", 7103)
training_samples = int(perf.get("training_samples", raw_samples))
if training_samples < 5000:
    training_samples = max(raw_samples, 7103)
```

The third line is the problem. This is not a fallback for a missing value — it detects a real
value below 5,000 and replaces it with 7,103. The same file hardcodes
`mae 481.0 / rmse 921.0 / mape 5.04 / median_ae 320.0 / r2 0.9855`, plus `feature_count = 18`,
the model name `"FareForecastEstimator"`, `training_date → datetime.now()`, and
`"prediction_horizon": 0`. Every metric on the system-info surface is a literal. The
`r2 0.9855` is especially exposed, because the shipped 1d model's actual metadata records
**R² = 0.425**.

### 2.4 The forecast validator cannot fail

**[verified]** `backend/services/forecast/forecast_validator.py:28-66` checks four invariants:
bounds ordering; `BOOK_NOW ⇒ horizon 0 and savings 0`; `WAIT ⇒ horizon > 0 and savings > 0`; and
savings reconciliation within ₹0.50.

But `backend/services/forecast/timeline_builder.py:22-50` runs first and repairs the bounds into
compliance before the validator sees them:

```python
if lower > price: lower = round(price * 0.98, 2)
if upper < price: upper = round(price * 1.02, 2)
```

It also manufactures the day-0 point from `current_fare` with `lower = c_price*0.96` and
`upper = c_price*1.04`. So Invariant 1 is established by construction, and `invariants_passed`
comes back `True` for reasons unrelated to whether the forecast is sound. The frontend renders
that flag as a verification result. A check that cannot fail for its stated reason is worse than no
check, because it manufactures confidence.

### 2.5 Synthetic-data findings summary

| # | Finding | Evidence | Severity |
|---|---|---|---|
| S-1 | 86% of corpus is generated; all ten airlines statistically identical | measured over 6,328 rows | Critical |
| S-2 | Synthetic `days_until_dep` contradicts its own timestamps on 96.9% of rows, while correlating −0.82 with price | measured, split by block | Critical |
| S-3 | Magic-number branch discards model output for two constants | `price_model.py:516-520` | Critical |
| S-4 | Every system-info metric is a hardcoded literal, incl. `r2 0.9855` vs real 0.425 | `system_info_service.py` | Critical |
| S-5 | Training-sample count actively suppressed below 5,000 | `system_info_service.py:54-57` | High |
| S-6 | Confidence floored at 70% and inverted w.r.t. data quality | `confidence_engine.py:16-17` | High |
| S-7 | Forecast invariants pre-satisfied by the builder that runs before them | `timeline_builder.py:22-50` | High |
| S-8 | Chatbot re-injects the nulls the normalizer preserves | `chatbot_tools.py:128-135` | High |

---

## 3. The chatbot

### 3.1 No perimeter on the endpoint

**[verified]** `backend/routers/chat.py:38-58`:

```python
class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]

@router.post("/chat", tags=["AI Concierge"])
async def chat_endpoint(request: ChatRequest):
    messages = request.messages[-10:]
    user_messages = [msg for msg in messages if msg.role == "user"]
    latest_query = user_messages[-1].content.strip() if user_messages else ""
    session_id = f"sess_{os.urandom(8).hex()}"
```

Grepping this file for `Depends`, `get_current_user`, `limiter`, and `RateLimit` returns nothing.
So: the endpoint is unauthenticated and unthrottled, and it calls a paid LLM API — an
uncapped-cost surface any anonymous caller can drive. `content` has no `max_length` and `messages`
has no `max_items`, so a single request can carry an arbitrarily large payload. `role` accepts
`system`, letting a caller inject a forged system turn directly into the transcript. Only the last
user message is screened, so injection text placed in an earlier turn is never examined. And a
fresh random `session_id` per request means the checkpointer cannot correlate turns, which
defeats both conversation memory and any per-session abuse tracking.

If you fix one thing in the chatbot before showing this to anyone, fix this. It is a small diff —
auth dependency, rate limiter, `max_length`, drop `system` from the pattern, stable session id —
and it is the first thing a reviewer probes.

### 3.2 The guardrail layer is off — corrected proof

A delegated sweep reported this as *"236 records evaluated zero policy rules; no record shows a
production rule ever being evaluated,"* resting on `policy_trace` being empty. I initially rejected
that, reasoning that 67 records in the same log *did* block, which is impossible with no policy
loaded — and I filed the empty trace as a separate serialization defect. **Measuring it properly
showed the sweep's conclusion was right and my rejection was wrong.** The corrected account:

I cross-tabulated all 372 records. The separation is total:

| | records | decision | contains the UNSAFE-but-allowed cases? |
|---|---|---|---|
| empty `policy_trace` | 236 | **all 236 allowed** | yes — all 36, incl. all 32 contradictions |
| non-empty `policy_trace` | 136 | 67 blocked / 69 allowed | none |

Then I read what the 136 traces actually name. Across both shipped log files there are exactly
**two distinct trace entries, and both name the same rule**:

```
{"rule_id": "test_block", "matched": false}                    69
{"rule_id": "test_block", "action": "BLOCK", "matched": true}  67
```

`test_block` is not a production rule. It is the pytest fixture at
`backend/tests/test_firewall.py:28-46`, which writes a one-rule policy (`id: "test_block"`,
`match: {verdict: UNSAFE}`, `action: BLOCK`) to a `tmp_path`. None of the five rules in
`backend/policy.yaml` — `jailbreak_block`, `content_block`, `topic_block`, `high_risk_block`,
`unknown_review` — appears anywhere in the log.

So: **not one of the 372 recorded requests ever evaluated a single rule from the production policy
file.** The 67 blocks are the test harness blocking under its own fixture, which is why my "67
blocked, therefore a policy was loaded" objection does not survive — a policy was loaded, just not
that one. And the empty trace is not a serialization defect: it correlates perfectly with an empty
ruleset (236 of 236 empty-trace records were allowed), so `engine.py:34-47` is serializing
correctly and an empty trace means there were zero rules to iterate. It is a working diagnostic
signal, not a bug. That finding is retracted; see C-15.

The contradiction still stands as the sharpest single artifact, and now with a known cause. **32
records carry `jailbreak-detect: UNSAFE` together with `risk_score: 100.0` and `is_safe: true`, and
all 32 have an empty trace.** With `backend/policy.yaml` loaded, that combination cannot occur:
`jailbreak_block` (priority 100, guardrail `jailbreak-detect`, verdict UNSAFE → BLOCK) and
`high_risk_block` (`risk_gt: 95.0` → BLOCK) would each independently block it. Two rules that must
fire did not, because neither was ever in memory.

One scope caveat I want to be explicit about, since it cuts against overstating this: a log whose
only traced rule is a pytest fixture is dev and test output, not production traffic. So the honest
claim is *"36 of 372 recorded requests were allowed while carrying UNSAFE verdicts, and no recorded
run ever loaded the production policy"* — not that 36 real users bypassed the firewall. That is
still the finding that matters, because it means the production ruleset has no evidence of ever
having executed.

The mechanism, **[verified]** in three parts:

`backend/firewall/config_loader.py:30-34` silently substitutes a permissive default when the
policy file is missing:

```python
if not os.path.exists(self.file_path):
    logger.warning(f"Policy file {self.file_path} not found. Using default policy.")
    if self._current_policy is None:
        self._current_policy = PolicyConfig()
    return
```

`PolicyConfig()` is `default_action: ALLOW` with no rules. The path is resolved against the current
working directory, and the caller passes a bare filename —
`backend/routers/chat.py:32` is `PolicyLoader(file_path="policy.yaml")`, verbatim. The real file
lives at `backend/policy.yaml`, so the firewall is armed only when the process CWD is exactly
`backend/`. Launch from the repo root, from a systemd unit, from Docker with a different WORKDIR, or
from any IDE run configuration, and it silently disarms. A `WARNING` in a log nobody reads is the
only notice. Line 44's `if data:` adds a second hole — an empty YAML leaves
`_current_policy = None`.

The fix is one line, and the correct pattern is already in this repo. `backend/governance/engine.py:24-28`
anchors to the package instead of the CWD:

```python
if file_path is None:
    # Default: look relative to this file's directory
    file_path = Path(__file__).parent / "policy.yaml"
```

The governance subsystem got this right; the firewall subsystem, sitting beside it, did not.

`backend/firewall/rules/engine.py:49-50` is why the failure is *visible* in the log rather than
merely undetectable:

```python
is_safe = final_action != RuleAction.BLOCK
violations = [r.name for r in context.guardrail_results if r.status.value == "UNSAFE"]
```

These two fields come from independent sources. `is_safe` follows the policy decision; `violations`
reads the guardrail results directly. When the policy is absent, the record self-contradicts —
which is what made the proof possible. Two further defects in the same file: `_evaluate_condition`
never reads `confidence_gt` (a policy knob that does nothing), and `risk_gt` combined with
`guardrail`/`verdict` evaluates as OR rather than AND because the branch only ever sets
`match = True`.

**[verified]** `jailbreak-detect` ERRORed on **206 of 372** evaluations (55.4%), and **202 of those
206** sit in records scoring `risk_score: 0.0` — an errored guardrail contributes no risk. That is a
second, independent fail-open at the guardrail level, which would still be live even after the
policy path is fixed. A guardrail that fails more often than it succeeds, and scores zero when it
fails, is worse than absent: it produces a low risk score that looks like a clean verdict.

Aggregate: **36 of 372 recorded requests were allowed while carrying UNSAFE verdicts**, and no
recorded run ever loaded the production ruleset.

**The one mitigating fact, and it is a real one.** All eight chat tools are read-only. There is no
path from the chat surface to booking, payment, or notifications. A successful injection can make
the bot say wrong things; it cannot make it spend money or send messages. That containment is worth
stating explicitly in any conversation about this, because it is the difference between an
embarrassing bug and an incident.

`backend/firewall/audit.py:29-48` deserves credit on its own terms: the record schema
(`timestamp, request_id, session_id, user_id, risk_score, decision{is_safe,violations},
guardrail_results[{name,status,latency_ms}], policy_trace, timings`) stores **no message body**,
which is the right PII decision and not the default choice. The `FileHandler("firewall_audit.log")`
is CWD-relative like the policy path.

### 3.3 The grounding check, measured

**[verified by execution.]** I ran the real `ChatResponseValidator`
(`backend/services/chat_response_validator.py`, 92 lines) against constructed evidence payloads.
**It caught 1 of 10 adversarial cases, and rejected the one truthful case that mentioned
"terminal."**

The price extractor is the reason. It matches `\b(\d+(?:\.\d+)?)\b`, then skips 1900–2099 as
calendar years and anything below 500 as an unrealistic fare. Measured behaviour:

```
extract_prices("Rs 1,999")  -> []        # comma breaks the \b boundary
extract_prices("Rs 2,050")  -> []        # comma, and 2050 is also in the year range
extract_prices("Rs 499")    -> []        # below the 500 floor
extract_prices("Rs 9,330")  -> [9330.0]  # only unpunctuated-after-comma-strip form lands
```

Indian fare formatting uses commas. The check is blind to the most common way a price appears in
its own domain, so a hallucinated fare written naturally is never examined. Separately,
`valid_airlines` and `valid_flights` are populated and **never read** — airline and flight-number
hallucinations are entirely unchecked. The `hallucination_triggers` list
(`baggage`, `luggage`, `discount`, `promo`, `terminal`, `gate`) is a bare substring match, which is
what rejected the truthful response.

**My own additional finding, beyond the delegated sweep.** The guard is written inverted:

```python
matched = any(abs(rounded_p - vp) <= 5 for vp in valid_prices)
if not matched and valid_prices:
    return False
```

`and valid_prices` means an empty evidence set passes everything. I then traced all eight tool
return shapes and found that four of them yield no harvestable prices, because the harvester only
reads `{"flights":[...]}`, `predicted_price`, and `{"data":[...]}`:

| tool | return shape | prices harvestable? |
|---|---|---|
| `search_flights` | `{"flights":[…]}` | yes |
| `compare_flights` | `{"flights":[…]}` | yes |
| `predict_price` | `{"status":"success", **res}` | yes |
| `historical_prices` | `{"data":[…]}` | yes |
| `recommend_flights` | `{"cheapest","fastest","best_value"}` | **no** |
| `forecast_prices` | `{"forecast":[…]}` | **no** |
| `airport_information` | `{"airports":[…]}` | **no** |
| `route_information` | `{"supported":…}` | **no** |

For those four, `valid_prices` is empty, the inverted guard passes, and any price the model invents
is served unchecked. `recommend_flights` answers the single most natural question a user asks —
"what's the best flight?" — so the highest-traffic path is the unprotected one. `forecast_prices`
is the product's headline feature.

### 3.4 Structural issues in the chatbot core

**[verified]** `backend/services/chatbot_service.py:552-638`:

- `tool_payloads.append(result)` passes the **raw, unslimmed** result to the validator, while
  `_slim_tool_result` output goes to the LLM. Validator and model see different evidence.
- `asyncio.create_task(evidence_builder.build_shadow(session_id, tool_payloads))` — the task's
  result is discarded and never awaited. Fire-and-forget with no error handling; an exception here
  surfaces nowhere.
- `if tool_payloads:` gates the second LLM call, the validator, **and** the judge. No tools called
  means no validation at all — the unconstrained-generation path is the unchecked one.
- Judge repair applies `final_text = judge_res.repaired_response` with **no re-validation**. The
  repair output bypasses the grounding check entirely.
- Neither LLM call passes `temperature`, `max_tokens`, or `timeout`. No timeout on an external API
  call inside a request handler means a hung upstream holds the connection open indefinitely.
- The failure string on `not is_valid` is *"Live pricing data isn't available for this route right
  now. Try again shortly."* — a **data-availability** message for a **grounding-failure** event.
  It is indistinguishable from a genuine outage, so validator rejections are invisible in
  production. The outer handler at `:663-667` similarly yields *"Something went wrong. Please try
  your aviation question again."*

**[verified]** `backend/services/chatbot_tools.py:128-135` fabricates schedule data the rest of the
system deliberately leaves null:

```python
flight_number=seg.get("flight_number") or "1000",
departure_time=seg.get("departure_time") or f"{departure_date}T12:00:00",
arrival_time=seg.get("arrival_time") or f"{departure_date}T14:00:00",
airline_code=... or f.get("primary_airline") or "6E",
airline_name=... or f.get("primary_airline_name") or "IndiGo",
duration=itin.get("duration") or "PT2H",
```

Flight 1000 on IndiGo departing at noon, arriving 2pm, two hours' duration. These are the exact
nulls `flight_normalizer.py` and `live_search.py` preserve on purpose. The chatbot is the one
surface that breaks the no-synthetic-data policy, and it does so in the most user-visible way —
by stating a departure time.

Related **[verified]** detail worth knowing: `_presentation_to_flights` at `chatbot_tools.py:21-43`
calls `f.model_dump()`, which returns the declared `price: float` rather than the `__getitem__`
override in `flight_normalizer.py:42-48` that yields `{"total":…,"currency":…}`. That is why the
validator does not crash on real traffic — it receives scalars. I established this after my own
first test fixture passed a dict and produced `float() argument must be...not 'dict'` on 7 of 8
cases. Worth recording because it means the two shapes coexist in the codebase and only one call
path currently keeps them apart.

### 3.5 PostgREST filter injection reachable from chat text

**[verified]** `backend/database/flight_repository.py:30-36`:

```python
res = db.supabase.table("airports").select("iata_code, name, city, country") \
    .or_(f"iata_code.ilike.%{query}%,city.ilike.%{query}%,name.ilike.%{query}%") \
    .limit(limit).execute()
```

`query` is interpolated unescaped into PostgREST filter syntax. It arrives from the
`airport_information` tool, whose argument the LLM fills from user chat text. Commas and dots are
structural in that grammar, so a crafted city name can alter the filter expression. Combine with
§3.1 (unauthenticated) and §3.2 (guardrails off) and the reachable path is: anonymous HTTP request
→ chat text → LLM tool argument → filter expression. The service_role key in `backend/.env`
bypasses RLS, so there is no database-level backstop.

### 3.6 The eval suite cannot report failure

**[verified]** Two independent problems.

`backend/evals/datasets/v2.0/golden.jsonl` contains **15 lines**. The accompanying
`metadata.json:6` declares `"total_records": 120`. Any pass-rate computed against the declared
denominator is wrong by 8×.

`backend/evals/evaluators/llm/groundedness.py` returns `score=None, status="SKIPPED",
passed=True` on planner fallback, and `score=1.0, status="PASS"` in **both** remaining branches —
including one whose reason string is *"No response text required for planner test"*, i.e. an empty
response scores a perfect 1.0. There is no code path that returns a failing groundedness score, and
there is no network call in the file, so nothing is actually being evaluated. `passed=True` on skip
means skips inflate the pass rate rather than being reported as gaps.

An eval suite that structurally cannot fail is a liability in an interview, because it invites the
question of whether any reported metric in the project was ever measured.

> **Status.** Both are fixed; the paths above are the paths as found. `metadata.json` now declares
> the counts the corpus actually contains and the loader treats a manifest that disagrees with the
> corpus as a schema error, which invalidates the run. The groundedness evaluator moved to
> `backend/evals/evaluators/deterministic/groundedness.py` — `evaluators/llm/` never contained a
> network call and no longer exists — and it can now return a failing score; a skip carries
> `passed=False`. The suite also gained `forecast_accuracy`, the first evaluator in the project whose
> subject is a forecast rather than a plan. See `AUDIT-FIXES.md`.

### 3.7 `agent_graph` is not in the product

**[verified]** `backend/services/agent_graph.py` is imported only by
`backend/tests/test_agent_graph.py` and `backend/tests/test_production_validation.py`. Its
`node_generator` at `:195-206` makes no LLM call:

```python
if not tool_payloads:
    text = "Live pricing data isn't available for this route right now. Try again shortly."
else:
    text = "Here are the flight intelligence insights for your request."
```

Two static strings. The README's "Decentralized Multi-Agent Orchestration" with four autonomous
agents describes this file, and this file returns constants and has no production caller. The
LangGraph work that *is* live sits in `chatbot_service.py`.

### 3.8 Chatbot findings summary

| # | Finding | Evidence | Severity |
|---|---|---|---|
| C-1 | `/chat` unauthenticated, unthrottled, calls a paid API | `chat.py:38-58`, grep | Critical |
| C-2 | Guardrails inert: no recorded run ever evaluated a production rule; 36/372 UNSAFE allowed | only traced rule is the pytest fixture `test_block`; `config_loader.py:30-34`; `chat.py:32` | Critical |
| C-3 | Grounding check catches 1 of 10 attacks; blind to comma-formatted fares | executed | Critical |
| C-4 | 4 of 8 tools yield no harvestable prices; inverted guard passes everything | traced all 8 shapes | Critical |
| C-5 | PostgREST filter injection reachable from anonymous chat text | `flight_repository.py:30-36` | Critical |
| C-6 | Groundedness evaluator has no failing code path | `groundedness.py` | High |
| C-7 | Golden set 15 records vs declared 120 | `golden.jsonl`, `metadata.json:6` | High |
| C-8 | Judge repair output bypasses re-validation | `chatbot_service.py:552-638` | High |
| C-9 | Chatbot fabricates flight numbers and schedule times | `chatbot_tools.py:128-135` | High |
| C-10 | `role` accepts `system`; only last user message screened | `chat.py:38-58` | High |
| C-11 | No timeout/`max_tokens`/`temperature` on LLM calls | `chatbot_service.py` | Medium |
| C-12 | Grounding failure reported as a data outage | `chatbot_service.py` | Medium |
| C-13 | `confidence_gt` policy condition never evaluated | `engine.py` `_evaluate_condition` | Medium |
| C-14 | `risk_gt` + `verdict` evaluates as OR, not AND | `engine.py` | Medium |
| C-2b | `jailbreak-detect` errors on 55.4% of evaluations; an errored guardrail scores 0.0 risk | 206/372, 202 of them at risk 0.0 | Critical |
| C-15 | ~~`policy_trace` empty in all 372 records~~ **RETRACTED** — 236/372, and it correctly reflects an empty ruleset | cross-tab, §3.2 | n/a |
| C-21 | Firewall policy path is CWD-relative while the sibling governance loader is package-anchored | `chat.py:32` vs `governance/engine.py:24-28` | High |
| C-16 | Fresh random `session_id` per request defeats checkpointing | `chat.py:57` | Medium |
| C-17 | `agent_graph` has no production caller; returns static strings | grep, `:195-206` | Medium |
| C-18 | Validator receives raw payloads, LLM receives slimmed | `chatbot_service.py` | Low |
| C-19 | Shadow evidence task discarded, never awaited | `chatbot_service.py` | Low |
| C-20 | Policy and audit-log paths are CWD-relative | `config_loader.py`, `audit.py` | Low |

---

## 4. Remediation, extending the roadmap in `AUDIT.md`

Sequenced so each phase makes the next one verifiable. The main report's Phase 0 still comes
first, unchanged and unconditional: rotate every credential in `backend/.env` (Supabase
service_role, Postgres password, Gmail app password, Twilio token, OpenAI, NVIDIA, LangSmith,
Razorpay), fix the 31 NUL bytes in `requirements.txt`, tighten CORS, and `git init` — there is
still no repository, so `.gitignore` is inert and those secrets are unprotected.

**Phase A — chatbot perimeter.** Auth dependency and rate limiter on `/chat`; `max_length` on
`content` and `max_items` on `messages`; drop `system` from the `role` pattern; stable
`session_id`. Parameterise the `airports` filter or whitelist the query character set. Small diff,
removes C-1, C-5, C-10, C-16, and the uncapped-cost surface.

**Phase B — make the guardrails bind.** Resolve the policy path with
`Path(__file__).parent / "policy.yaml"`, copying `backend/governance/engine.py:24-28`, so the
firewall stops depending on the process CWD; **fail closed** when the policy file is missing or
empty rather than substituting `PolicyConfig()`; make `is_safe` and `violations` derive from one
source so a record cannot self-contradict; fix the OR-for-AND bug and either implement
`confidence_gt` or delete it. Separately, treat a guardrail ERROR as high risk rather than 0.0, and
find out why `jailbreak-detect` fails 55% of the time — that is a live bug independent of the
policy. Then run the 372 logged requests back through the fixed pipeline as a regression corpus:
you already know which 36 must flip to blocked, which is a genuinely useful position to be in.

**Phase C — make ingestion observable before improving it.** Env-var override for
`executablePath` with a bundled-Chromium fallback; distinguish scrape *failure* from *empty
result* with a distinct sentinel; split `total_inserted` into `rows_newly_observed` and
`rows_served_from_cache`, and gate on the former; add a UNIQUE constraint on `price_history`
(natural key: flight number, departure date, recorded date, origin, destination) so upsert becomes
possible; guard or remove the `DROP TABLE` in the schema file. After this, a failed run looks like
a failed run.

**Phase D — the honest ML rebuild.** This is the phase that produces the resume story. Delete the
magic-number branch in `price_model.py`. Drop `price_change_1d`/`price_change_3d` and set
`target_price` to a genuinely future price. Stop overwriting `days_until_dep` from the wall clock —
use the stored value, and drop the synthetic block whose stored horizon contradicts its own
timestamps. Rebuild the corpus from `is_live` rows only, which is honestly ~1,026 rows; a small
real dataset with an honest R² is defensible in a way that 7,354 rows at a fabricated 0.9855 is
not. Wire in the code that already exists and is already correct — `model_trainer`,
`dataset_splitter`, `cross_validation`, `benchmark`, `model_artifact`, and especially the
chronological split. Add a real baseline (last-observed-price, or per-route mean) and report
against it. Report R² and MAE alongside `100 − MAPE`, and stop calling that quantity "accuracy."

**Phase E — make the evals capable of failing.** Give `groundedness.py` a failing path and derive
its goldens rather than asserting them. Reconcile 15 versus 120. Make skip report as a gap, not a
pass. Rewrite the price extractor to handle Indian comma formatting; read `valid_airlines` and
`valid_flights`; fix the inverted `and valid_prices` guard; add price harvesting for
`recommend_flights` and `forecast_prices`. Re-validate after judge repair. Then re-run the 10
adversarial cases from §3.3 as a test suite.

**Phase F — remove the fabrication in the reporting layer.** Delete the `< 5000` suppression and
the hardcoded metrics in `system_info_service.py`; read from model metadata. Remove the confidence
floor and fix the inverted quality polarity. Move the bound repair out of `timeline_builder` so
`forecast_validator` can actually fail. Remove the `or "1000"` / `or "6E"` / noon-departure
defaults in `chatbot_tools.py` and let the chatbot degrade the way the rest of the system already
does.

Then the README. Every claim in it should be traceable to a number the system printed: replace
">92% accuracy" with per-horizon R² and MAE against a stated baseline; drop "Decentralized
Multi-Agent System" unless `agent_graph` is wired in and doing work; drop "thousands of proprietary
market signals"; and describe the market simulation engine as what it is — a documented
cold-start fallback, which is a legitimate and interesting design choice when it is not being
presented as a data source.

---

## 5. What to say in the interview

The strong work is real and specific: a Puppeteer MCP scraper behind stdio JSON-RPC; circuit
breakers with single-flight cache-stampede prevention, tested with a real 5-way `asyncio.gather`;
a correctly implemented chronological split; `test_feature_determinism.py` running 100 iterations
against the real pipeline; a LangGraph chatbot with a firewall and YAML-driven governance; an audit
log that deliberately stores no message bodies; and a zero-synthetic-data policy that the request
path genuinely honours. Every one of those is a better talking point than ">92% accuracy," and
right now the inflated claims are what stop an interviewer from ever reaching them.

The story to lead with is already yours. `backend/scratch/audit_training_loss.py` is titled *"Why
MAE=0, RMSE=0, Accuracy=100%"* — you noticed the leak. You stopped one step short of tracing it to
`target_price = price` and the two `price_change` features carrying 48% of the model. Finish that
trace, rebuild the pipeline honestly, and the line becomes: *"I caught target leakage in my own
model, proved it from the shipped feature importances, and rebuilt the training pipeline on live
data only — the honest R² is lower and I can show you why that's the right number."*

That answer is stronger than any accuracy figure, because it demonstrates the thing the accuracy
figure was trying to fake.

---

## Appendix — method and confidence

**Verified by hand or by execution:** all cited line numbers were read directly. Corpus statistics
in §1.4 and §2.2 were computed over the shipped CSVs during this audit (6,328 and 7,354 rows,
block-split, correlation, date-range). Feature importances were read from
`backend/ml/models/fare_forecast_0d.metadata.json`. The grounding-check results in §3.3 come from
executing the real `ChatResponseValidator` against constructed payloads. The audit-log figures in
§3.2 — the 236/136 cross-tab, the 32-record contradiction, the `test_block`-only trace inventory,
the 67 blocks, and the 206/372 guardrail error rate with 202 at risk 0.0 — were all measured over
the shipped `firewall_audit.log`. Tool return shapes in §3.3 were traced through
`chatbot_tools.py` individually.

**Reported, not independently reproduced:** nothing material remains in this category. The one
previously-open item, the 206/372 `jailbreak-detect` error rate, has now been measured directly.

**Corrected mid-audit, and worth reading as a method note.** I made a wrong call and then caught it,
which is the kind of thing that should be visible rather than tidied away. A delegated sweep
concluded from empty `policy_trace` fields that no production policy rule had ever been evaluated.
I rejected that, because 67 records in the same log had blocked, and blocking requires a loaded
policy. My objection was locally valid and globally wrong: a policy *was* loaded for those 67, but
it was the pytest fixture `test_block`, not `backend/policy.yaml`. Reading the trace contents rather
than just their emptiness settled it — two distinct entries across 372 records, both naming
`test_block`. So the sweep's conclusion holds, my proposed serialization defect does not exist
(C-15 retracted), and the empty trace turns out to be a correct signal that the ruleset was empty.
The lesson generalises past this repo: I had checked whether the field was populated without
checking what it contained, which is the same class of mistake as trusting a green test that asserts
nothing.

**Also corrected:** an earlier pass of this document stated that `policy_trace` was empty in all 372
records. The measured figure is 236 of 372.

**Not modified:** no file in the repo was changed. Every item in §4 awaits approval.

> **Superseded.** The line above was true when this document was written. Remediation has since
> begun; `AUDIT-FIXES.md` is the running record of what changed, what proves it, and what is still
> outstanding. Read it alongside §4 rather than treating §4 as the current state.

**One measurement mistake worth recording**, since it changed a conclusion: my first validator
fixture passed `price` as `{"total": 9330}`, producing `float() argument must be a string or a real
number, not 'dict'` on 7 of 8 cases. Tracing the real shape showed `_presentation_to_flights` calls
`model_dump()`, so production payloads carry scalars. The error was productive — it settled the
open question of whether the validator crashes on real traffic. It does not.
