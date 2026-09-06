# SkyMind Copilot — Request & Execution Workflows

## 1. AI Flight Fare Prediction Workflow

```
User Search Request (origin, destination, departure_date)
   │
   ▼
[Next.js Frontend (/predict)] ──HTTP POST /api/v1/predict──► [FastAPI backend/main.py]
                                                                     │
                                                                     ▼
                                                        [PredictionService.predict()]
                                                                     │
                         ┌───────────────────────────────────────────┴───────────────────────────────────────────┐
                         ▼                                                                                       ▼
           [LiveMarketService.get_snapshot()]                                                          [HistoricalDataService]
           - Queries Google Flights / SerpAPI                                                          - Reads route historical
           - Cache check / freshness evaluation                                                          booking curves
           - Evaluates provider_status (ONLINE vs DEGRADED)
                         │                                                                                       │
                         └───────────────────────────────────────────┬───────────────────────────────────────────┘
                                                                     │
                                                                     ▼
                                                      [ML Feature Vector Extraction]
                                                      - Calculates lead time, day of week
                                                      - Applies feature scalers & encoders
                                                      - Executes XGBoost Model Inference
                                                                     │
                                                                     ▼
                                                    [CanonicalForecastService]
                                                    - TimelineBuilder constructs points (0..30d)
                                                    - SavingsCalculator computes exact savings
                                                    - RecommendationEngine issues BUY_NOW / WAIT
                                                    - ConfidenceEngine grades model & market quality
                                                    - ForecastValidationEngine asserts 4 invariants
                                                                     │
                                                                     ▼
                                                    [ForecastMapper.to_dto()]
                                                    - Serializes domain model to JSON payload
                                                    - Attaches forecast_metadata & diagnostics
                                                                     │
                                                                     ▼
                                                   [FastAPI Response (HTTP 200 OK)]
                                                                     │
                                                                     ▼
                                                    [Frontend Page (/predict)]
                                                    - Renders Canonical metrics directly
                                                    - Renders SVG PriceChart with index px(i)
                                                    - Renders interactive ForecastDebugPanel
```

---

## 2. Evaluation & Doctor CLI Workflow

```
Developer Command: `python -m backend.evals.doctor`
   │
   ▼
[backend/evals/doctor.py]
   ├── 1. Environment & API Keys Inspection
   ├── 2. Provider Provenance & Live Snapshot Check
   ├── 3. Model Registry & XGBoost Artifact Verification
   └── 4. Evaluator Harness Execution (14+ test metrics)
   │
   ▼
Generates JSON & Markdown Evaluation Audit Report
```
