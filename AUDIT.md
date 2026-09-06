# SkyMind — Production Readiness & Credibility Audit

**Date:** 2026-08-18 · **Scope:** full repository, read-only · **Method:** five parallel deep audits (claims, security, ML, architecture, frontend/CI), with every CRITICAL finding re-verified by hand against source and shipped artifacts.

---

## Verdict

There is real engineering in this repository, and it is better than its own README suggests. A working Puppeteer-based MCP flight scraper, a chronological train/test split, circuit breakers with cache-stampede prevention, a LangGraph chatbot behind a firewall/governance layer, a genuinely-enforced zero-synthetic-data policy in the live path, 139 test files. That is a real portfolio.

It is currently wrapped in three problems that would each end a technical interview on their own.

**First, the ML result is an artifact of target leakage, and the headline number is the worst model.** The `>92% accuracy` claim maps to exactly one of three shipped models — the one with R² = 0.42. The other two are 90.6% and 91.7%, both *below* the claim.

**Second, the money path lets the client set the price it pays.** An unauthenticated caller can book a ₹50,000 flight for ₹1, and the server's own "price tampering" guard validates the client's number against a database value the client wrote.

**Third, the product's core output is a constant.** The `/predict` page always says "BUY NOW", always shows ₹0 savings, and always shows today's date — because the frontend mapper silently drops the two fields the page reads.

None of these is a style problem. All three are mechanisms, and all three are fixable. The good news: the fixes are mostly *subtraction*, and the strongest version of this project is the honest one.

---

## Part 1 — The five questions that end the interview

These are ordered by how quickly they land. Each is a question a competent interviewer asks within ninety seconds of opening the repo.

**1. "For your horizon-0 model, what is `target_price`, and how is `price_change_1d` computed?"**

Two lines, two files. `backend/services/training_dataset_builder.py:70-72`:

```python
if horizon == 0:
    df_features = df_features_raw.copy()
    df_features["target_price"] = df_features["price"]
```

`backend/ml/features/booking_curve.py:70-71`:

```python
price_1d = df["price"] - gp["price"].shift(1)
price_3d = df["price"] - gp["price"].shift(3)
```

The target *is* `price`, and two features are arithmetic in `price`. The model can partially invert them. This is not theoretical — the shipped artifact confesses it. From `backend/ml/models/fare_forecast_0d.metadata.json`, `price_change_3d` is the **#1 feature at 0.374 importance** and `price_change_1d` is **#3 at 0.106**. Together, **48% of the model's explanatory power comes from two functions of the label.**

**2. "Accuracy of what? Show me R² next to that number."**

"Accuracy" is not a regression metric. Here it is `100 − MAPE`, relabelled at `backend/ml/price_model.py:190-191, 222-223`:

```python
mape = float(np.mean(np.abs((y_test.values - preds) / np.maximum(y_test.values, 1))) * 100)
eq_accuracy = float(max(0.0, 100.0 - mape))
...
"equivalent_accuracy_100_minus_mape": float(eq_accuracy),
"accuracy": float(eq_accuracy / 100.0),
```

The internal key is honest. The public one is flattened to `accuracy`. Here is what actually shipped:

| Model | "accuracy" | R² | MAE | Train rows | Test rows |
|---|---|---|---|---|---|
| `fare_forecast_0d` | **90.59%** | 0.932 | ₹991 | 25,229 | 6,308 |
| `fare_forecast_1d` | **98.64%** | **0.425** | ₹97 | 2,398 | 600 |
| `fare_forecast_3d` | **91.74%** | 0.707 | ₹709 | **105** | **27** |
| `fare_forecast_7d` | *no metadata file* | — | — | — | — |

The `>92%` claim describes only the 1d model — the one explaining **under half the variance**. MAPE is flattering here precisely because the prices cluster tightly (see question 3). Meanwhile a fourth `.pkl` sits in the serving directory with no metadata at all, five days staler than the rest: an unevaluated artifact in a production path.

**3. "Ten carriers, identical price distributions. What did the model learn?"**

This is the deepest finding. `backend/database/supabase_upload_final.csv` is 6,328 rows — 86% of the training corpus. I profiled it directly:

```
flight_number:    1 distinct value  → 'HIST-000' × 6328
seats_available:  1 distinct value  → '50' × 6328
days_until_dep:   1 distinct value  → '14' × 6328

price mean by airline:
  2T: n=662 mean=9522 min=2542 max=17253      QP: n=635 mean=9426 min=2532 max=17539
  6E: n=648 mean=9118 min=2573 max=17773      S5: n=618 mean=9133 min=2509 max=17046
  9I: n=637 mean=9328 min=2570 max=17100      SG: n=638 mean=9533 min=2566 max=17591
  AI: n=635 mean=9277 min=2615 max=17331      UK: n=583 mean=9281 min=2573 max=17431
  G8: n=661 mean=9216 min=2560 max=17736      I5: n=611 mean=9127 min=2555 max=17540
```

Every one of ten carriers has the same mean within 4.5%, and the same min and max within a few rupees. IndiGo (`6E`, low-cost) and Vistara (`UK`, full-service) are statistically indistinguishable. That is impossible in real Indian domestic fare data and it is the exact signature of `randint(~2500, ~17800)` with route and airline labels attached *independently of price*. Route explains almost nothing: between-route variance over within-route variance is **0.068**.

This closes the loop on finding 1. Because the legitimate features carry near-zero information about the label **by construction**, R² = 0.932 is not reachable any other way. The leak is not a contributing factor — it is the entire result.

The generator is not in the repo, but the technique is, in your own hand at `backend/scratch/ingest_mock_data.py:52-54` (`price = float(random.randint(25000, 55000))`). And your own diagnostic script names the problem in its own section header — `backend/scratch/audit_training_loss.py:84`: *"STAGE 6: Horizon 1d Metrics Audit (Why MAE=0, RMSE=0, Accuracy=100%)"*. Someone already found this. The README was never revised.

**4. "Show me the sigmoid demand model."**

README lines 33-37 sell a "Proprietary Market Simulation Engine" as one of three core pillars, with "Sigmoid Demand Modeling", "quadratic inventory decay", and "Deterministic Seeded Randomness". A repository-wide search for `sigmoid`, `inventory_pressure`, `quadratic`, and `seeded` returns **zero matches** outside XGBoost's `random_state=42`. The generator was deliberately removed (`backend/database/database.py:63`: *"Synthetic training dataset generation removed"*). There is nothing to open.

This pillar also directly contradicts your own `docs/ZERO_SYNTHETIC_DATA_AUDIT.md` and the live-path assertion at `flight_data_service.py:56` (*"Absolutely no simulated data fallbacks are allowed"*). The README advertises as a feature the exact thing the code forbids.

**5. "Your landing page says 92.4% in one place and 93.2% in another. Which is it?"**

`frontend/app/page.tsx:139` falls back to `"92.4%"`; line 244 falls back to `"93.2%"`. Same metric, two hardcoded values, one screen. Neither matches any shipped model.

---

## Part 2 — Critical findings

### CRIT-1 · Target leakage produces the entire ML result
`training_dataset_builder.py:70-72`, `ml/features/booking_curve.py:70-71`

Covered above. Two aggravating details. The `shift(1)` is **positional, not temporal** — your own validation reports (`backend/validation_reports/validation_2026-07-22_080322.json`) record `average_unique_recorded_dates: 1.047`, and I confirmed zero historical groups have more than one observation date. So "price_change_1d" is actually the difference against a *same-day sibling row*: contemporaneous information wearing a time-lag name. There are no booking curves in the historical data at all.

And your leakage test cannot catch this. `ml/booking_curve_validator.py:186` masks *future* rows and recomputes — but `price − past_price` is unchanged by that mask, so it passes vacuously. It tests temporal leakage; the defect is target leakage.

**Fix:** for horizon 0, either drop the horizon-0 model entirely (predicting today's price from today's price is not a product) or drop both lag features and report the honest R². Expect it to fall hard — that is the point. Then rebuild the corpus from the `is_live=True` rows only.

### CRIT-2 · The client sets the price it pays
`routers/booking.py:63, 89-103, 127` → `routers/payment.py:78-84`

`CreateBookingRequest.flight_data: dict` is raw client JSON. The server reads the price out of it and writes it as the booking total:

```python
total_price, base_fare, taxes = _extract_price_details(req.flight_data)   # :127
# _extract_price_details just reads flight_data["price"]["grandTotal"]     # :92-96
```

`flight_offer_id` is stored as `amadeus_booking_id` and never validated against any server-side offer. This makes the guard in `payment.py` vacuous:

```python
# Amount validation (prevent price tampering)
db_price = float(booking.get("total_price", 0))
if abs(db_price - req.amount) > 1:
```

It compares the client's `amount` against a database value **the client itself supplied**. Full exploit, no authentication required at any step: `POST /booking/create` with `flight_data={"price":{"grandTotal":"1"}}` → `POST /payment/create-order` with `amount=1` (passes) → pay ₹1 through real Razorpay → `POST /payment/verify` → booking `CONFIRMED`, ticket PDF issued. This is the live UI path.

**Fix:** persist server-priced offers at search time keyed by `flight_offer_id`; on booking, look the price up server-side and ignore every client price field.

### CRIT-3 · A real payment can be replayed onto any booking
`routers/payment.py:127-165`

The HMAC covers only `order_id|payment_id`. `booking_id` is not bound into the signature, and although `create-order` records `notes.booking_id`, it is never read back. Pay ₹1 on your own booking, keep the valid triple, resubmit it with any expensive booking's `booking_id`. The idempotency check at `:151` only inspects the *target* booking, so one payment replays across unlimited bookings.

**Fix:** `client.order.fetch(order_id)`, assert `notes.booking_id == req.booking_id` and `amount == booking.total_price`, and add a uniqueness constraint on `razorpay_order_id`.

### CRIT-4 · The core product output is a constant
`frontend/lib/api.ts:262-305` → `frontend/app/predict/page.tsx:68-87`

The backend correctly sends `canonical_forecast` and `optimal_booking` (`prediction_service.py:406,415`). The mapper — documented at `lib/api.ts:248` as *"the SINGLE source of truth for mapping the backend response"* — returns an object literal of nine keys, and **neither field is among them.** I verified both are absent. So both are permanently `undefined` in the browser.

The page reads exactly those two fields:

```ts
const recHorizon = cForecast ? cForecast.optimal_booking_horizon : (result?.optimal_booking?.prediction_horizon ?? 0);
const recTitle = recDecision === "BOOK_NOW" || recHorizon === 0 ? "BUY NOW" : `WAIT ${recHorizon} DAY...`;
const savings  = cForecast ? cForecast.calculated_savings : (result?.optimal_booking?.estimated_savings ?? 0);
const optDateStr = cForecast ? cForecast.optimal_booking_date : (result?.optimal_booking?.booking_date ?? new Date().toISOString());
```

`recHorizon` is unconditionally `0`, so line 77 short-circuits and **a `WAIT` recommendation cannot reach the screen.** Savings render "₹0 (0.0%)". "RECOMMENDED BOOKING DATE" is the user's own system clock. The explanation collapses to a hardcoded sentence: *"Today's live fare is already the lowest expected price across all forecast horizons."*

Every forecasting mechanism behind this works. None of it reaches the user.

**Fix:** add both keys to the mapper — then fix CRIT-5 so the type system prevents recurrence.

### CRIT-5 · The frontend does not typecheck, and that is why CRIT-4 survived
`frontend/tsconfig.json:11`, `frontend/next.config.js:24-29`

`"strict": false`, plus:

```js
typescript: { ignoreBuildErrors: true },
eslint:     { ignoreDuringBuilds: true },
```

A real `tsc --noEmit` run produces **36 errors**, 33 of them missing type exports. `types/index.ts` never defines `PredictionResult`, `PredictRequest`, `FlightSearchResponse`, `Booking`, `Passenger`, and eleven others — yet `lib/api.ts:30-51` imports all of them. `PredictionResult` resolving to nothing is *precisely* why `result?.canonical_forecast` raised no error against a field the mapper never produces. `npm run build` succeeds only because checking is disabled.

Compounding: `npm run lint` cannot run either — there is no ESLint config and no `eslint` dependency anywhere. **No linting or typechecking happens in this project at all.**

**Closed during the fix phase (2026-08-31).** The measured count from a clean `node node_modules/typescript/bin/tsc --noEmit` was **37 errors**, not 36; ~34 shared one root cause. `frontend/types/index.ts` stopped at `FlightOffer` after 140 lines, so 20 imported members did not exist. The file now carries all of them, derived from the actual backend response shapes — `backend/services/prediction_presentation.py` for `/predict`, `backend/routers/live_search.py` for `/live-search`, the booking and payment routers for the rest — rather than from what the frontend appeared to want. `tsc --noEmit` now exits 0. Three consequences of doing it from evidence:

- **`optimal_booking` and `canonical_forecast` are read by the UI and can never arrive.** Neither is a field on `PredictionResponse`, so FastAPI's `response_model` strips both before the browser sees them, and `lib/api.ts#predictPrice` never sets either. The canonical-forecast branch of `app/predict/page.tsx` is unreachable code. Typed as optional with that stated inline, because deleting the branch is a product decision.
- **`PredictionResult.trend` never existed.** `app/page.tsx:40` read `p.trend || "STABLE"`, and `PredictionResponse` defines no `trend` field, so all three landing-page cards showed "Stable" unconditionally regardless of the forecast. Replaced with `trendFromDecision()` in `lib/api.ts`, deriving the trend from `recommendation.decision` — the only directional signal the endpoint returns. `app/predict/page.tsx:410` had a second, inconsistent inline derivation (`decision === "BOOK_NOW" ? "RISING" : "STABLE"`, which could never yield `FALLING`, making `PriceChart`'s green path unreachable); both call sites now share the one definition.
- **The error envelope does not match the parser.** Every backend error goes through the handlers in `backend/main.py` as `{success: false, error: {code, message, details}}`, but `ApiError` in `lib/api.ts` reads `body?.detail`. Every server-side error message is currently discarded before the user sees it. Typed as `ApiErrorEnvelope`; the parser fix is a behaviour change and is listed in Phase 1.

Two further defects surfaced only because the compiler could finally see them. `components/prediction/ForecastTimeline.tsx:48` set `justify: "space-between"`, which is not a CSS property — the intended `justifyContent` was silently absent from every forecast card for as long as the file has existed. And `app/flights/page.tsx` passed `max_results: 30` into `searchFlights`, which neither forwards it nor could use it: `LiveSearchRequest` has no such field, so the cap was never applied. The same call also dropped `infants`, so an infant selected in the search form never reached the provider; both are fixed.

`typescript.ignoreBuildErrors` is now `false`. `next build` could not be verified in the audit sandbox — `node_modules` was installed on Windows, so the `linux-x64` SWC binary is absent and the registry is unreachable from there — so the build gate is asserted by CI, not by a local run.

### CRIT-6 · `pip install -r requirements.txt` fails — deploy and CI are both broken
`backend/requirements.txt:57-60`

The file contains **31 NUL bytes**: UTF-16LE fragments of `boto3>=1.34.0` and `openai>=1.14.0` spliced into a UTF-8 file. Verified by hexdump:

```
b'fastmcp\r\nb\x00o\x00t\x00o\x003\x00>\x00=\x001\x00.\x003\x004\x00.\x000\x00\r\n\x00...'
```

pip rejects this outright. It breaks `render.yaml`'s build command, `.github/workflows/daily.yaml`, and any reviewer following your README. Note `boto3` has **zero import sites** — delete it rather than repair it. Also `flights` and `fastmcp` are bare unversioned names, and `flights` is a generic PyPI name (dependency-confusion surface).

### CRIT-7 · CORS wildcard with credentials
`backend/main.py:52-58`

```python
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, ...)
```

Any origin can make credentialed cross-site requests. The irony: lines 37-48 build a correct `allowed_origins` allowlist from env — and then never use it. One-line fix.

### CRIT-8 · This is not a git repository
No repository at the root. `git rev-parse` fails from root, `backend/`, and `frontend/`.

Correction added during the fix phase: there *is* one nested repository, `backend/india-flight-mcp/.git` — 2 commits (`3be880d initial files`, `d5bae63 optimize`) on `main`, no remote, its own sensible `.gitignore`, and no secret-shaped files in its history. It covers only the scraper subtree, so the finding stands as written for the project as a whole.

For a resume project this is the quietest fatal problem on the list. There is no history, no commits, no contribution graph, nothing to link. A reviewer cannot see how you work. It also means `.gitignore` is **inert** — so on your eventual `git init && git add .`, the Windows `venv/` (no gitignore entry) and every clutter file goes in with it.

It also means I could not check whether `backend/.env` was ever committed. Given what is in it, treat the secrets as exposed regardless (see CRIT-9).

### CRIT-9 · Live high-privilege credentials in plaintext
`backend/.env`, `.env`

Present and live: a Supabase **`service_role`** JWT (bypasses all RLS, expires ~2036), a direct Postgres connection string with password, a Gmail app password (send *and read* mail), Twilio auth token, NVIDIA API key, OpenAI project key, LangSmith key, Razorpay test secret. That combination is a full-compromise set.

They are currently covered by `.gitignore` — but `.gitignore` is inert (CRIT-8), and this directory has just been shared for audit. **Rotate all of them before anything else on this list.**

**Escalation found during the fix phase — two of these secrets were not in `.env` at all.** The first `git add` staged them as *source code*, where no ignore rule can ever reach them:

- `backend/scratch/alter_price_history_provenance.py:4` — `os.environ.get("DATABASE_URL", "<live DSN>")`. The fallback default was byte-identical to `backend/.env:DATABASE_URL`: Supabase project ref plus database password, in a script whose whole job is to run `ALTER TABLE` against `price_history`. Unset environment meant silently issuing DDL against production.
- `backend/test_nemo.py:8` — `os.getenv("NVIDIA_API_KEY", "<live key>")`. Byte-identical to `backend/.env:NVIDIA_API_KEY`.

Both defaults are removed; the scripts now fail loudly (`sys.exit`) or skip when the variable is absent. The generalisable point is that a hardcoded fallback is *worse* than no default — it converts a missing-configuration error into a successful connection to production, which is the same failure mode as every other finding in this report. It also means the gitignore hardening in this section is necessary but not sufficient: the check that actually settles the question is comparing each live `.env` value against the content of every file about to be committed. After the fix, that sweep is clean across all 554 staged files.

One precise note on gitignore semantics, since it matters for what you add next: `.env` is a glob, not a prefix. It matches basename `.env` exactly at any depth — so it covers `frontend/.env` but **not** `.env.production`, `.env.backup`, or `frontend/env.download` (which already exists and mirrors your Supabase config). You want `.env*` plus `!.env*.example`.

---

## Part 3 — Full findings index

### Security

| ID | Sev | Finding |
|---|---|---|
| S1 | CRIT | Client-controlled booking price (CRIT-2) |
| S2 | CRIT | Payment signature omits `booking_id` — replayable (CRIT-3) |
| S3 | CRIT | CORS `*` with credentials (CRIT-7) |
| S4 | CRIT | Live service_role / Postgres / Gmail / Twilio credentials in plaintext (CRIT-9) |
| S5 | HIGH | Every endpoint the product uses is unauthenticated: `POST /booking/create`, both `/payment/*`, `/api/chat`, `/live-search`, `/api/v1/predict`, all `/system/*`, `/auth/send-otp`. The endpoints that *do* enforce auth are the ones the UI never calls — `frontend/lib/api.ts:120-140` never sends an `Authorization` header at all, so `Bearer` appears nowhere in the frontend. Read access control therefore lives entirely in Supabase RLS policies **not present in this repo** — while the backend queries with the service_role client that bypasses them. |
| S6 | HIGH | Unauthenticated LLM chat: no rate limit, unbounded token size, and **both guardrails fail open** (`chat.py:90-91,124-125` catch and continue). `ChatMessage.role` accepts `system`, only the last *user* message is screened, all 10 are forwarded — so payload in a `system` message bypasses the firewall entirely. The shipped `firewall_audit.log` shows `jailbreak-detect` at `"status": "ERROR"` on every root entry, so this path already fires in practice. |
| S7 | HIGH | Unauthenticated OTP with attacker-chosen `user_id` (`auth.py:186-242`): send a victim's OTP to your own address, verify it, and set `phone_verified = True` on their profile. Also an unauthenticated send-anything primitive on your real Gmail and Twilio accounts. |
| S8 | HIGH | Write-side IDOR — `booking.py:69` takes `user_id` from the request body. Passenger passport and Aadhaar numbers get stored against arbitrary user IDs. |
| S9 | HIGH | Weak OTP crypto (`notifications.py:361-368`): Mersenne Twister `random.choices` for a security token, unsalted single-round SHA-256 over a 10⁶ keyspace, non-constant-time `==`. `payment.py` correctly uses `hmac.compare_digest` — inconsistent. |
| S10 | MED | No rate limiting anywhere (verified: zero `slowapi`/`Limiter`/`throttle` references). Exposed: LLM chat, a Puppeteer scrape per `/live-search` call, SMS/email spend on `/auth/send-otp`. |
| S11 | MED | `/docs`, `/redoc`, `/openapi.json` all public — a free map of every unauthenticated route above. No HSTS, no CSP, no `TrustedHostMiddleware`. |
| S12 | MED | Global handler returns `str(exc)` (`main.py:130-142`), leaking internals. |
| S13 | MED | PostgREST filter injection — `flight_repository.py:34` interpolates user input into `.or_(...)`; commas and dots inject filter clauses into a service-role query. Bounded impact today, one column-list change from serious. |
| S14 | MED | Booking totals leak via error text (`payment.py:83`) on an unauthenticated endpoint — an oracle for any booking's total. |
| S15 | MED | Full user prompts logged on every chat branch (`chat.py:77-135`). No `*.log` gitignore pattern. |
| S16 | LOW | `secret_key: str = "change-me-in-production"` (`config.py:15`). Verified nothing signs with it today — auth delegates to Supabase — but it is a live trap for the next handler that reaches for it. |

Cleared, so you can answer these confidently: `backend/bash.py` is **not** a vulnerability despite the name — it is an offline ingestion script with no `subprocess`/`eval`/`exec`, guarded by `__main__`, imported by nothing. No SSRF (every outbound base URL is a constant or env-driven), no command injection (MCP spawns fixed `node` + hardcoded script path), no `pickle`/`yaml.load` on untrusted input, no path traversal. No `NEXT_PUBLIC_*` var holds server-side material. The two `firewall_audit.log` files contain timings and decisions only — no prompts, no secrets.

### Machine learning

| ID | Sev | Finding |
|---|---|---|
| M1 | CRIT | Target leakage is the entire result (CRIT-1) |
| M2 | CRIT | Training corpus is statistically inert synthetic noise (Part 1, Q3) |
| M3 | CRIT | "Accuracy" = `100 − MAPE`; the `>92%` claim is the R²=0.42 model (Part 1, Q2) |
| M4 | CRIT | **No baseline comparison exists.** The only quality gate is `r2 < 0.0` — it rejects only models worse than predicting the mean. `benchmark.py` is never called in production *and* is broken twice over: `:99` is named `naive_persistence` with a docstring saying "last known price" but computes `np.full_like(y_true, np.mean(y_true))`, and `:105` is a **centered** rolling mean over `y_true` — a "baseline" that reads the answer. Both are built from `y_true` alone. |
| M5 | CRIT | Train/serve skew on the model's #1 feature. `price_change_1d` has **four** implementations; training uses a single-row lag (`booking_curve.py:70`) while serving uses a **windowed mean** (`prediction_features.py:88`). Different quantities, same name. `test_prediction_feature_parity.py:12` checks column *names and ordering* only, so it passes while the skew is wide open. |
| M6 | HIGH | Reproducibility is broken at the root. `database.py:163-164` recomputes `days_until_dep` from **wall-clock time at training** and overwrites the correct stored column. I verified: against the training timestamp, **100% of rows in both CSVs (13,682 rows) collapse to `days_until_dep = 0`, `urgency = 1.0`** — destroying the booking-window signal and changing every feature value on every re-run, so `dataset_hash` anchors nothing. The shipped metadata records no git commit, no seed, no hyperparameters, no library versions. No model card. |
| M7 | HIGH | No held-out test set. `hyperparameter_optimizer.py:132` selects on `X_val`; `model_trainer.py:208` reports final metrics on that same `X_val`. Reported metrics are model-selection metrics. No purge/embargo, so the last `horizon` days of training targets fall inside the validation window. |
| M8 | HIGH | **The entire audit-grade ML stack is dead code.** `model_trainer.py`, `dataset_splitter.py`, `cross_validation.py`, `benchmark.py`, `hyperparameter_optimizer.py`, `model_artifact.py` have zero production callers — `run_pipeline.py:46-50` calls the legacy `price_model.train()` path instead. The good code exists and does not run. This is the most fixable finding in the ML section. |
| M9 | HIGH | Drift detection cannot detect drift. It never invokes the model (`drift_detection.py:60-63` uses the std of `price`); `market_drift_score` is documented as "airline mix / route frequency shifts" but computes `(feature_drift + prediction_drift)/2` from no airline or route data; it compares the *current* snapshot's two halves rather than against the training distribution; no KS, no PSI; threshold is a 40% mean fare move, so it effectively never fires; and it gates nothing. Related: `feature_validation.py:87` emits `"determinism_verified": True` as a hardcoded literal. |
| M10 | MED | Five of sixteen features have **exactly 0.000000 importance** in every model: `hour_of_day`, `is_peak_hour`, `demand_score`, `seasonality_factor`, `is_live`. Two of them — Seasonality Factors and Peak-Hour Indicators — are singled out by name in README:30 as "high-impact". Root cause is structural: `market.py:81-82,156-157` hardcodes two to NaN, and `departure_time` is absent from the persisted column set (`ingestion_controller.py:147-156`) so the hour features can never populate. |
| M11 | MED | `95.0` model accuracy is a hardcoded default threaded through the whole confidence system (`confidence_engine.py:11`, `assembler.py:32`, `recommendation_engine.py:97`, and three more). User-facing "95% confidence" is a literal times a cache-freshness factor. A test enshrines it: `assert rec_live["confidence"] == 95.0`. |
| M12 | MED | `price_model.py:423-425` silently inflates predictions: `if raw_pred < 800: raw_pred = raw_pred * 1.15`. |
| M13 | MED | `price_model.py:281` sets `self._trained = True` unconditionally, even when every horizon was rejected by the quality gate and `self.models` is empty. `predict.py:61` gates readiness on exactly that flag, so a model-less predictor passes readiness and fails as a 500 instead of a 503. |
| M14 | MED | `backend/evals/` contains **zero price-regression evaluation** — it is entirely a chatbot harness. No MAE/MAPE/error-bound assertion exists anywhere in the repo, despite `docs/EVALUATION_FRAMEWORK.md:11` claiming otherwise. |

Credit where due: the split is **genuinely chronological** (`price_model.py:153-162` sorts by `recorded_at`, no shuffling), and `cross_validation.py` implements proper expanding folds. That is the right instinct, correctly implemented — it just isn't wired in.

### Architecture

| ID | Sev | Finding |
|---|---|---|
| A1 | CRIT | `requirements.txt` corrupted (CRIT-6) |
| A2 | CRIT | ~30 sites call the **synchronous** Supabase client from `async def` handlers, parking the event loop on every request. Worst: `booking.py:165,202,254,283,303,333,343`, `payment.py:65,142,156,224,228`, `auth.py:146,236,257,288`, `alerts.py:100,137,172,225,237`. Also `prediction_service.py:246` runs synchronous model inference on the loop. Fix is one word per handler — `def` instead of `async def` lets FastAPI use its threadpool. Do the money paths first. |
| A3 | HIGH | **Four source files are not valid Python.** They contain literal `\n` two-character sequences instead of newlines — LLM output written to disk without unescaping. `governance/policy.py` (37), `conversation/models.py` (89), `conversation/governance.py` (82), `conversation/governance/__init__.py` (38). All fail `compile()`. The app does not crash because nothing imports them — they are *broken dead code*, which is the worst possible artifact to leave for a reviewer who opens one. |
| A4 | HIGH | `conversation/governance.py` and `conversation/governance/` both exist — Python resolves the package, so the module is unreachable by construction. Both are broken, and both duplicate `governance/engine.py`, which is the version actually wired in. Delete the `conversation/` tree except `decision_result.py`. |
| A5 | HIGH | `start_scheduler()` (`services/scheduler.py:285`) is **never called**. Price alerts, route collection, and daily retraining never run in the deployed app. README's architecture diagram shows APScheduler inside the running service; the real cron is GitHub Actions. |
| A6 | HIGH | `config.py` defines a proper pydantic `Settings` — and only **three** modules use it, against **52 scattered `os.getenv` sites**. Worse, `llm_provider.py:47,94` resolve a missing key to `"mock_nvidia_key"`, so misconfiguration surfaces as a confusing 401 mid-request instead of at startup. |
| A7 | MED | Dead code: `routers/notifications.py` (177 LOC, **never registered** — its endpoints don't exist at runtime), `firewall/circuit_breaker.py`, `firewall/policy.py`, `governance/decision_engine.py` + `interfaces.py`, the `conversation/` tree, `bash.py`. Reachable only from tests: `production_readiness.py` and its six validators, `agent_graph.py`, `model_trainer.py`, `booking_curve_validator.py`. |
| A8 | MED | `flight_data_provider.py`: three of four `FlightDataProvider` implementations are stubs returning `[]`, the fourth is a passthrough — and it **inverts the dependency direction**, with the bottom-layer "provider" importing the top-layer orchestrator. Three contract test files assert against these stubs. Amadeus is documented as removed. Delete. |
| A9 | MED | Real import cycle: `ml.price_model` → `training_dataset_builder` → `model_registry` → `ml.price_model`, papered over with two function-local imports. |
| A10 | MED | Two competing `CircuitBreaker` implementations; "policy" spread across four homes with three schemas, including two different files both named `policy.yaml`. |
| A11 | MED | 172 broad `except Exception`, 3 bare `except:`, of which **36 neither log nor re-raise**. Worst: `notifications.py:129,135,141`, `auth.py:166,207,213`, `flight_search_service.py:34` (hides model-load failure), plus five ML feature extractors silently returning defaults. |
| A12 | MED | Observability is instrumented and discarded: ~8 OpenTelemetry counters and histograms are created but **no `MeterProvider` is ever configured**, so all of them go to the no-op default. The only tracer provider is set as an import side-effect from inside a subpackage and exports to console. No request-ID propagation. And `main.py:80` filters logging to paths matching `predict|system|validation|health` — **booking, payment, and auth requests are never logged at all.** |
| A13 | LOW | Dual import roots requiring a `sys.path` hack (`main.py:7`): 618 `from backend.X` vs 41 bare `from services.X`. |
| A14 | LOW | Three declared Python versions: `runtime.txt` 3.11.9, `render.yaml` 3.11.0, CI 3.10. CI trains the pickles on an interpreter you don't deploy. |
| A15 | LOW | Business logic in routers: `booking.py:99` hardcodes an 85/15 base-to-tax split inside an HTTP handler, with a fallback that silently produces a zero-priced booking. `chat.py`, `flights.py`, `predict.py`, `system.py` are clean by contrast — that's the right shape. |

Important positive, and worth saying in your README: **failures do not fall back to fake data.** The zero-synthetic-data policy is genuinely enforced in the runtime paths. `flight_search_service.py:38-46` degrades to `recommendation="MONITOR"` with "Model training in progress" rather than inventing a price. That is real engineering discipline.

### Frontend

| ID | Sev | Finding |
|---|---|---|
| F1 | CRIT | Recommendation is a constant (CRIT-4) |
| F2 | CRIT | 36 typecheck errors, suppressed by config; no ESLint at all (CRIT-5) |
| F3 | HIGH | Whole categories of failure render as plausible real data. The pattern is `catch` substituting a *number*: `PopularDestinations.tsx:16-20` ships `min_price_inr: 4299` as `STARTING AT ₹4,299` — and fires on a successful *empty* result too; `page.tsx:54-74` substitutes a price, a confidence, *and* a trend per route, ~20 lines above a claim of "zero synthetic filler data"; `dashboard/page.tsx:63-65` renders a DB outage byte-identically to "you have no bookings", with no error branch at all; `settings/page.tsx:18` renders an unreachable metrics API as a **zero-error model**. |
| F4 | HIGH | Trust badges default to the reassuring value. `lib/api.ts:440` `provenance: f.provenance \|\| "REAL_PROVIDER"` and `:450` a hardcoded `data_source: "LIVE_SEARCH"`, rendered at `flights/page.tsx:358` as "LIVE · GOOGLE FLIGHTS" — so a flight with *no* provenance is badged live. Worse: `:293-294` `provider_status \|\| "ONLINE"` and `market_snapshot_available ?? true` make your genuinely well-written degradation banner (`predict/page.tsx:229-233`) **unreachable in exactly the situation it was written for.** |
| F5 | HIGH | Money-facing fabrication. `success/page.tsx:36` manufactures a plausible Razorpay ID when none exists (`pay_v2_${Date.now().toString(36)}`), renders a static `VERIFIED` never derived from `verifyPayment()`, and has zero error handling — a failed payment renders a confirmed booking. `checkout/page.tsx:195,199` presents an invented `price * 0.85` / `price * 0.15` split as an itemised tax breakdown. |
| F6 | HIGH | `Chatbot.tsx:437-446` attaches `confidenceScore: 0.95` and `sources: ["Google Flights Stream", "SkyMind XGBoost Inference"]` to any message containing "₹". A fabricated confidence with a named provenance chain is the most legally exposed pattern in the repo. `ForecastDebugPanel.tsx:18` defaults `invariants_passed ?? true` → renders *"✓ All 4 mathematical forecast invariants satisfied"* for a validation that never ran. |
| F7 | HIGH | Zero frontend tests. No jest, vitest, testing-library, cypress, or playwright. `lib/api.ts` — 594 lines holding every data transformation including the CRIT-4 mapper — has no test. |
| F8 | HIGH | `render.yaml` cannot boot the app. `rootDir: backend` + `startCommand: uvicorn main:app`, but `main.py:18-19` uses absolute `from backend.X` imports and there is no `backend/__init__.py`. `DEPLOYMENT.md:58` even hedges toward the working form in a parenthetical; `render.yaml` ships the broken one. *(Static analysis — verify with one clean boot.)* |
| F9 | MED | React Query is installed, provided, and used in **zero** files, despite README:85. Every fetch is hand-rolled `useEffect`. Also unused: `zustand` (README:46 claims it), `recharts` (README:48 claims it), plus `react-hot-toast`, `clsx`, `tailwind-merge`, `class-variance-authority`. `typescript` and the `@types/*` packages are in `dependencies`, not `devDependencies`. |
| F10 | MED | Hardcoded `localhost:8000` defaults in `next.config.js:17,21` and `lib/api.ts:87`. `next.config.js` inlines env at build time, so a missing var **bakes in permanently**. |
| F11 | LOW | 60 `: any` / `as any`, 15 of them in `lib/api.ts`. Every API function is `apiRequest<any>`. Credit: **zero** `@ts-ignore` — the suppression is centralised in `next.config.js` instead. |
| F12 | LOW | Loaders narrate work they cannot observe — `LOADING_STEPS` advanced by a 700ms `setInterval` with no backend progress signal. |
| F13 | LOW | Dead components carrying live-looking fabrications: `MarketSignals.tsx:70-72` hardcodes `95.4%` "Historical Accuracy" / "Validated on holdout split"; `DecisionCard.tsx:44` is `horizon === 0 ? "Low" : "Low"`. Delete rather than fix. |

Genuine credit on accessibility, which is better than most portfolio work: 19 `aria-*` attributes, 5 `role=`, proper `<nav>`/`<main>`/`<section>`, alt text on all four raw `<img>` tags, `aria-hidden` on decorative SVGs, and **zero** `onClick` on `<div>`. Gaps are one keyboard handler total and no `next/image` despite configured `remotePatterns`. Also genuinely good: `app/admin/page.tsx` (real loading, real error card, every value from the API) and `PriceChart.tsx` (confidence band from real API bounds, not a multiplier).

### Testing and CI

| ID | Sev | Finding |
|---|---|---|
| T1 | CRIT | **CI has no trigger on push or pull request.** `.github/workflows/daily.yaml` is the only workflow: `schedule` + `workflow_dispatch`, running `run_pipeline.py`. No pytest, no lint, no typecheck, no build, no deploy. 139 test files and 377 tests are never executed by automation. Nothing can block a bad merge — which is why CRIT-4, CRIT-5, and CRIT-6 all shipped. |
| T2 | HIGH | **The suite is structurally hollow where it matters most,** even though it doesn't look it. Quantitatively it's fine — 0 `assert True`, ~78 weak assertions out of 1,036 (7.5%). Anyone grading by grep concludes it's healthy. But: `test_contract_amadeus_provider.py` and `test_contract_sabre_provider.py` assert that an unimplemented stub returns nothing (`assert len(res) == 0`) — **they will fail the day someone implements Amadeus.** `test_contract_google_provider.py` mocks 100% of the provider's behaviour, then asserts a literal typed four lines above. `test_model_trainer.py:48-59` patches `ModelTrainer.train` itself and asserts the mock returned what was assigned to it — zero implementation lines execute. `test_production_readiness.py:10` asserts the status is one of the only three values the function can return, and is **green on a repo whose own readiness report says FAIL**. `test_thread_safe_cache.py` has no threads. There is **not a single recorded API fixture in the repo** — zero VCR/respx/jsonschema — so no test can detect an upstream API change. "Contract" is unearned. |
| T3 | HIGH | The two ML guarantees this project most needs both rest on tests pointed at code production does not execute. `test_target_leakage.py` tests `_build_shifted_dataset`, whose only callers are test files; the real path is `training_dataset_builder.build()`, which is untested and contains the leak. `cross_validation.py:6-7` declares in caps *"Future observations never leak into any training fold"* and **no test asserts it** — and `test_cross_validation.py:61` passes even if zero folds ran, because the module fills every metric key with `NaN` unconditionally. |
| T4 | MED | No pytest config and **no coverage measurement of any kind** — no `pytest.ini`, `pyproject.toml`, `setup.cfg`, or `.coveragerc`. Coverage is entirely unknown; nobody has ever measured it. |
| T5 | MED | Tests hit real external services. `langsmith_tracer.py:16-18` loads `backend/.env` **at import time**, so live OpenAI, NVIDIA and LangSmith keys are active during test runs — verified billed POSTs to `api.openai.com` from `test_openai_planner_phase1.py:28` and `test_openai_judge_phase3.py:39`, plus three remote Postgres round-trips from `test_production_readiness.py`. `conftest.py` provides no env or network isolation. Worse, `test_openai_planner_phase1.py:26` asserts `fallback_used is True`, which **only holds if a live OpenAI call fails** — the test asserts a different thing depending on network weather and on which sibling files pytest collected. |
| T6 | MED | Evidence the suite does not cleanly pass. `backend/.pytest_cache/.../lastfailed` holds 4 whole-file entries (collection errors), one of which — `test_openai_planning_judge.py` — **no longer exists on disk**: a file that failed collection was deleted rather than fixed. |
| T7 | MED | No Dockerfile, no container definition, no documented rollback, with `autoDeploy: true`. "Reproducible" rests on Render's buildpack plus three conflicting Python version files. `DEPLOYMENT.md` is also stale — it documents a single `global_model.pkl` while the app serves per-horizon artifacts. |
| T8 | MED | **A reviewer cannot get this running from the README.** `README.md:113` says `python run.py` — but `run.py` is a *training script* (`model.train()` then `db.upload_model()`), not the API server. It never starts a server, and it requires Supabase credentials. Also missing: the real serve command, the `skymind_complete.sql` init step (without which `database.py:28-31` raises at import), all four frontend env vars, the `PYTHONPATH` export CI depends on, `cd backend/india-flight-mcp && npm install` for the scraper live search depends on, and any mention that 139 test files exist or how to run them. |

Genuinely strong tests, which should be your template: `test_feature_determinism.py` (100 iterations through the real pipeline, NaN-aware, `assert len(hashes) == 1`), `test_cache_stampede.py:27-40` (real 5-way `asyncio.gather` race, mocks the data source not the lock, would fail if single-flight were removed), `test_zero_synthetic_data.py`, `test_chatbot_response_validator.py`. The pattern is clear: tests that mock a *dependency* or call a *real leaf function* are strong; the ML and readiness surfaces are the weak ones.

### Documentation

Three documents contradict each other on test counts (`PROJECT_STATUS.md:10` says 23/23, two others say 27, reality is 377). `PROJECT_STATUS.md:7` describes the provider as "Google Flights via SerpAPI … and mock fallback engine" — there is no SerpAPI client and no mock engine in the repo; it's Puppeteer. `docs/ZERO_SYNTHETIC_DATA_AUDIT.md` and `docs/FLIGHT_SEARCH_AUTHENTICITY_AUDIT.md` document **unresolved "CRITICAL VIOLATIONS"** at code locations that are now clean — shipping an open self-audit is worse than shipping none, especially since the same defaults *do* still exist one layer up in the Node scraper (`stdio_server.js:90-91` defaults an unknown carrier to IndiGo/`6E`, `:101` defaults duration to 135 minutes, `GoogleFlightsProvider.js:63` fabricates a midnight departure) and the docs don't mention that. And `production_readiness_report.json:3` reads `"overall_status": "FAIL"` at repo root where any reviewer will open it.

Also: `PATCH_NOTES.md:26` claims the predictor "automatically attempts to pull the latest model from the cloud if the local file is missing" — `load()` raises `FileNotFoundError` instead. Hot-swap does not exist: `sync_from_cloud()` and `download_model()` are never called, and `self._last_loaded_time` is initialised and never read or written.

---

## Part 4 — Remediation roadmap

Ordered by leverage, not by severity. Several of these unblock the others.

### Phase 0 — Today (2 hours, non-negotiable)

**Rotate every credential in `backend/.env` and `.env`.** Supabase service_role, Postgres password, Gmail app password, Twilio token, NVIDIA, OpenAI, LangSmith, Razorpay. Then replace `.gitignore`'s env lines with `.env*` and `!.env*.example`, and add `*.log`, `venv/`, `.venv/`, `scratch/`, `validation_reports/`, `*_report.json`, `.pytest_cache/`, `*.tsbuildinfo`, and the scraper's `*.html`/`*.png` debris.

**Fix `requirements.txt`.** Rewrite as clean UTF-8, delete `boto3` (zero imports), pin `flights` and `fastmcp`. This one file currently breaks deploy, CI, and every reviewer's first command.

**Fix CORS.** One line: pass the `allowed_origins` list `main.py:37-48` already builds.

**`git init`.** Then commit in a sequence that tells a story rather than one "initial commit" — the history is part of what you're showing. I'd stage this deliberately rather than let me do it, since you commit manually. Verify with `git status` that no `.env`, no `venv/`, and no 666KB `extracted.txt` is staged.

### Phase 1 — Make the repo defensible (1 day, pure subtraction)

Delete, don't fix: the four syntactically-invalid files and the whole `conversation/` tree except `decision_result.py`; the three stub providers in `flight_data_provider.py` and their three contract tests; the orphan `firewall/circuit_breaker.py` and `firewall/policy.py`; `governance/decision_engine.py` + `interfaces.py`; the dead frontend components carrying fabricated metrics (`MarketSignals.tsx`, `DecisionCard.tsx`); `routers/notifications.py` (or register it); `bash.py`, `npx.cmd` (it hardcodes a path that no longer exists and leaks your username), the `scratch/` trees, `test_flight{,2,3,4}.py`, `test_nemo.py`, `test_email.html`, `test_ticket.pdf`, `article.txt`, `extracted.txt`, `flight_raw.json`, both `firewall_audit.log`s, the four root `*_report.json`, and the stray `backend/backend/`.

Then rewrite the README against reality (Part 5), and delete or resolve the stale audit docs. Rename the two colliding `policy.yaml` files.

This phase removes nothing that works and transforms the first impression. It is the highest ratio of credibility gained to effort spent in this entire document.

### Phase 2 — Close the money path (1 day)

CRIT-2 and CRIT-3 must land together; either alone still leaves a paid-for-₹1 or a replay path. Persist server-priced offers at search time keyed by `flight_offer_id`; price bookings server-side only. On verify, fetch the Razorpay order and assert `notes.booking_id` and `amount` match, with a uniqueness constraint on `razorpay_order_id`.

Then add `Depends(get_current_user)` to booking, payment, chat, and live-search, and make `frontend/lib/api.ts:127` attach `Authorization: Bearer ${session.access_token}`. Until that header exists, the correct IDOR checks already written in `booking.py`, `user.py`, `alerts.py` and `auth.py` protect nothing the UI touches. Derive `user_id` from the token, never the body. Add `slowapi` limits on `/api/chat`, `/live-search`, and `/auth/send-otp`. Close the fail-open guardrails in `chat.py` and stop accepting a client-supplied `system` role.

### Phase 3 — Make CI real, then let it find things (1 day)

Add a `push` + `pull_request` workflow running `pytest`, `tsc --noEmit`, `next build`, and `next lint`. Add a `pytest.ini` with `--strict-markers`, `asyncio_mode`, and coverage with a threshold. Add ESLint. Set `strict: true` and delete both `ignore*` flags from `next.config.js`.

Do this **before** writing new tests — until CI runs, no test is a safety net, and adding tests to an unenforced suite adds nothing. Then define the 15 missing interfaces in `types/index.ts`; the 33 type errors will point directly at CRIT-4 and its siblings. Isolate the network from tests (`conftest.py` should block outbound and stub the tracer) so the suite stops billing your OpenAI account and stops depending on network weather.

**Landed 2026-08-31.** `.github/workflows/ci.yaml` runs on `push` to any branch, on `pull_request`, and on dispatch, in five independent jobs: secret hygiene, Python syntax over every tracked `.py`, `pytest`, frontend typecheck plus `next build`, and ESLint. Lint is its own job so a style finding cannot mask a type error. Supporting files: `pytest.ini` at the root (`testpaths`, `pythonpath = .`, `asyncio_mode = auto`, `--strict-markers`), `backend/requirements-dev.txt` (pytest and pytest-asyncio were absent from `requirements.txt` altogether, so a clean checkout could not run the 146 test modules), and `frontend/.eslintrc.json` with `eslint` + `eslint-config-next` pinned in `devDependencies`.

Each gate was falsified rather than trusted. The dotenv rule rejects `.env`, `backend/.env`, `frontend/.env.production`, `frontend/env.download` and `env.bak` while passing `.env.example`, `.env.local.example`, `next-env.d.ts` and `evals/environment.py` — the `env.download` case matters because that is the file this repo actually leaked, and no `.env*` glob matches it. The credential-shape rule fires on all six shapes present in `.env` (PEM header, `eyJ`-prefixed JWT, DSN with password, `sk-`, `nvapi-`, `rzp_live_`) and does not fire on a 6-character redaction or on an `.example` placeholder, so this document does not trip it. The syntax gate exits 1 on each of the three defect families this repo actually contained — a plain syntax error, JSON-escaped text, and UTF-16LE with NUL bytes — and reports 400/400 on the real index.

Two caveats, both stated rather than papered over. `next build` and `pytest` have never been executed here: the sandbox has a Windows-installed `node_modules` (no `linux-x64` SWC binary), no pytest, and no package-registry access. Treat the first CI run as a diagnosis. And `frontend/package-lock.json` predates the two ESLint additions, so the install step falls back from `npm ci` to `npm install` with a CI warning until `npm install` is run once in `frontend/` and the refreshed lockfile is committed.

Two items in this phase as written were deliberately not done. `eslint.ignoreDuringBuilds` stays `true`, and the comment above it in `next.config.js` now says why (lint is a blocking CI gate, not a build gate) instead of claiming CI already covered it; `typescript.ignoreBuildErrors` is now `false`, which is the flag that was actually hiding defects. And `strict: true` in `tsconfig.json` was left alone: `strictNullChecks` is already on, so the remaining increment is mostly `noImplicitAny` over a codebase that uses `any` freely, and that is a large mechanical change whose only honest verification is a build this sandbox cannot run. Do it as its own commit once CI is green. Coverage thresholds are likewise deferred until the suite's first real run establishes what the baseline is — a threshold picked before that number is known is either vacuous or arbitrary.

### Phase 4 — Fix the ML story (2–3 days, the one that matters most)

This is the phase that decides whether the project is impressive.

Start by **rebuilding the corpus**. Drop the 6,328 `HIST-000` rows entirely — they are noise with labels attached and no model trained on them means anything. Keep the `is_live=True` observations and keep collecting; a small honest dataset beats a large fabricated one, and "I found my training data was synthetic and rebuilt the pipeline" is a *better* interview story than any accuracy number.

Then **fix the leak**: drop the horizon-0 model (predicting today's price from today's price is not a product) and drop the `price_change_*` features from the remaining horizons, or compute them strictly from information available at prediction time.

Then **fix `days_until_dep`** (`database.py:163-164`) to derive from `recorded_at`, not wall-clock — this single line currently collapses 100% of your rows to a constant and makes every training run irreproducible.

Then **wire in the good code you already wrote.** `model_trainer.py`, `dataset_splitter.py`, `cross_validation.py`, `model_artifact.py` are audit-grade and dead. Route `run_pipeline.py` through them, which gets you a three-way split, real expanding-window CV, and metadata with seeds and hyperparameters almost for free.

Then **add a baseline** — predict-last-price and predict-route-mean, computed honestly from features and history rather than from `y_true`. Report your model against them. A model that beats predict-last-price by 8% on real data is a genuinely good result and completely defensible. Rewrite `benchmark.py:99,105`, both of which currently read the answer.

Then **resolve the train/serve skew** on `price_change_1d` by making training and serving call the same function, and write a parity test that compares *values*, not column names. Finally, publish a model card with the real numbers.

### Phase 5 — Production hygiene (2 days)

Convert the ~30 blocking DB calls off the event loop, money paths first. Route all 52 `os.getenv` sites through `get_settings()` and add validators that hard-fail on missing credentials when `debug is False` — remove the `"mock_nvidia_key"` fallbacks so misconfiguration fails at startup, not mid-request. Configure a real `MeterProvider` so the OpenTelemetry instrumentation you already wrote stops going to `/dev/null`, add request-ID propagation, and remove the `main.py:80` path filter that currently excludes booking, payment, and auth from logs entirely. Either call `start_scheduler()` from the lifespan (with a leader guard before you scale workers) or delete it and document GitHub Actions as the scheduler. Split `/health` from `/ready`. Fix `render.yaml`'s import path and verify with one clean boot. Add a Dockerfile and settle on one Python version.

Then apply one project-wide rule to the frontend: **a `catch` may never substitute a plausible value.** Return a discriminated `{ok: false, error}` and render it. That single rule fixes F3, F4, F5, and F6 together, and it un-breaks the honest degradation banner you already wrote.

---

## Part 5 — Repositioning this for your resume

The instinct behind the current README — make it sound impressive — is backwards for engineering hiring. Inflated claims don't raise your ceiling; they hand the interviewer a script for dismantling you, and they obscure work that is genuinely good. Every claim in that file is a promise to be interrogated.

**Cut entirely:** ">92% accuracy" (it's `100−MAPE` on the R²=0.42 model). "Decentralized Multi-Agent System" (four pure functions, ~130 lines, one synchronous call, combined by a fixed weighted sum — and the "sigmoid demand modeling" one uses a reciprocal and a linear clamp). The entire "Proprietary Market Simulation Engine" pillar (does not exist, and contradicts your own zero-synthetic-data policy). "Sub-100ms inference" (never measured anywhere; the only measured latencies in the repo are chatbot evals at P95 3.4–4.6 seconds). "Hot-swap mechanism" (the functions are never called). "Zustand", "Recharts", "React Query" (all installed, all unused). "Thousands of proprietary market signals" (16 features, and scraped Google Flights data is not proprietary).

**Keep and lead with, because it's real and verifiable:** a Puppeteer-based flight scraper behind a proper stdio JSON-RPC MCP server. Circuit breakers plus single-flight cache-stampede prevention — and you have a *real* concurrency test proving it (`test_cache_stampede.py`), which is rarer in portfolio work than any accuracy number. A chronological train/test split with per-horizon model artifacts, dataset hashing, and residual statistics. A LangGraph chatbot with a firewall and governance layer. A feature-determinism test that runs 100 iterations through the real pipeline. And an enforced zero-synthetic-data policy where failures degrade honestly instead of inventing prices — say this explicitly, because most projects at this level do the opposite and yours has the discipline to be worth pointing at.

**The framing I'd actually use,** once Phase 4 lands: *"Flight price forecasting on scraped market data. XGBoost per booking horizon, chronological holdout, benchmarked against predict-last-price. MAE ≈ ₹X (baseline ₹Y). Includes drift detection, feature-determinism tests, and an enforced no-synthetic-data policy in the serving path."*

That is a paragraph that survives every follow-up question, and it describes a stronger engineer than the current README does.

**One more thing worth saying out loud in interviews:** you found the leakage yourself. `backend/scratch/audit_training_loss.py` is titled *"Why MAE=0, RMSE=0, Accuracy=100%"* — you noticed the metrics were impossible and wrote a script to investigate. That instinct is the single most valuable thing in this repository, and it's currently buried in a `scratch/` folder. Finish that investigation, write up what you found, and the story becomes "I caught target leakage in my own model and rebuilt the pipeline." Senior engineers hire that. Nobody hires 92.4%.

---

## Appendix — Method and confidence

Five parallel audits (claims, security, ML, architecture, frontend/CI) covering ~393 backend modules, 39 frontend source files, 139 test files, and 15 documentation files.

**Verified by hand, independent of the audit agents:** the target-leakage chain (`target_price = price` plus both lag features) and the feature importances proving it drives the model; all four models' metrics including the R²=0.42 / "98.6% accuracy" pair and the metadata-less 7d artifact; the synthetic corpus profile (single-valued `flight_number`/`seats_available`/`days_until_dep`, and near-identical price distributions across all ten carriers); the absence of `.git`; the 31 NUL bytes in `requirements.txt`; the CORS wildcard alongside the unused allowlist; the client-controlled booking price and the circular payment "validation"; and the frontend mapper's omission of `canonical_forecast`/`optimal_booking` against the predict page's exclusive reliance on them.

**Reported with quoted file:line evidence but not independently re-verified by me:** the four syntactically-invalid files, the dead scheduler, the CI trigger analysis, the test-quality assessments, the secret inventory, and the `render.yaml` import-path failure (static analysis — confirm with one clean boot).

**Explicitly not determined:** the generator for the `HIST-000` rows (absent from the repo; the shape matches `scratch/ingest_mock_data.py`'s technique). The provenance of the 1,026 `is_live=True` rows — flight numbers are `AI-2417`-style, which that script does not produce, so these may be genuine captures. Whether the 1,000-row drift sample reflects a live PostgREST cap. Supabase RLS policies, which are not in this repo and which currently carry all real read authorization. No training run was executed and no file was modified.
