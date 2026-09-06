# SkyMind Copilot — System Architecture (Production Reference v2.0)

## 1. Executive Summary
SkyMind is an enterprise-grade flight fare forecasting and copilot platform. It combines real-time flight market search providers (Google Flights / Amadeus / Mock engines), dynamic feature engineering pipelines, machine learning inference (XGBoost / LightGBM models), and a mathematically reconciled Canonical Forecast Engine to deliver airfare predictions, booking window recommendations, and interactive AI copilot assistance.

---

## 2. Layered System Architecture

```
+-----------------------------------------------------------------------+
|                           FRONTEND LAYER                              |
|   Next.js 14 App Router | React Server/Client Components | Tailwind   |
|   Pages: / (Home), /flights (Search), /predict (AI Forecast UI)      |
+-----------------------------------------------------------------------+
                                    |
                            HTTP / REST JSON
                                    |
+-----------------------------------------------------------------------+
|                          API ROUTER LAYER                             |
|   FastAPI App (backend/main.py) | CORS | Middleware | OpenTelemetry    |
+-----------------------------------------------------------------------+
           |                                             |
           v                                             v
+------------------------------------+     +----------------------------+
|        PREDICTION SERVICE          |     |    COPILOT & AGENT SYSTEM  |
|  - Feature Vector Extraction       |     |  - Intent Extractor        |
|  - ML Inference (XGBoost v2)       |     |  - Route Recommendation    |
|  - Booking Curve Reconstruction    |     |  - LangSmith Evaluation    |
+------------------------------------+     +----------------------------+
                   |                                     |
                   v                                     v
+-----------------------------------------------------------------------+
|                    CANONICAL FORECAST ENGINE                          |
|   backend/services/forecast/                                          |
|   - SavingsCalculator (Single-source savings math)                   |
|   - TimelineBuilder (Dynamic horizon alignment 0..30+ days)           |
|   - ConfidenceEngine (Model score + snapshot data quality)            |
|   - ForecastValidationEngine (Mathematical invariant assertions)      |
|   - ForecastAssembler -> CanonicalForecastDomain                      |
+-----------------------------------------------------------------------+
                                    |
                            ForecastMapper
                                    |
                                    v
+-----------------------------------------------------------------------+
|                         DATA & PROVIDER LAYER                         |
|   - Live Market Service (Google Flights SerpAPI / Mock Fallback)      |
|   - Historical Data Service (Price History CSV & In-memory Store)     |
|   - Evaluation Doctor & Harness (backend/evals/)                     |
+-----------------------------------------------------------------------+
```

---

## 3. Directory Layout & Module Structure

- **`backend/`**: Core FastAPI Python backend application
  - `main.py`: FastAPI server initialization, routing, CORS, and endpoint mounting.
  - `domain/`: Immutable domain models (`canonical_forecast.py`).
  - `services/`: Core application services.
    - `forecast/`: Modular Canonical Forecast package (`assembler.py`, `savings_calculator.py`, `timeline_builder.py`, `confidence_engine.py`, `forecast_validator.py`, `recommendation_engine.py`, `canonical_forecast_service.py`).
    - `prediction_service.py`: Feature extraction, ML inference, and snapshot integration.
    - `live_market_service.py`: Provider client (SerpAPI Google Flights client with TTL cache & mock fallback).
    - `historical_data_service.py`: Price history data provider.
    - `recommendation_engine.py`: Baseline booking window evaluation strategy.
    - `copilot_agent.py`: Flight search assistant.
  - `mappers/`: DTO mapping layer (`forecast_mapper.py`).
  - `evals/`: Evaluation framework (`doctor.py`, evaluation harness, provider provenance).
  - `models/`: Trained ML artifacts (XGBoost models, scalers, encoders).
  - `tests/`: Automated Pytest suite (`test_canonical_forecast_v2.py`, `test_evals_v2.py`, etc.).
- **`frontend/`**: Next.js 14 TypeScript web frontend application
  - `app/`: Next.js App Router pages (`page.tsx`, `predict/page.tsx`, `flights/page.tsx`).
  - `components/`: UI components (`charts/PriceChart.tsx`, `debug/ForecastDebugPanel.tsx`, `flights/`, `layout/`).
  - `types/`: Shared TypeScript interface definitions (`index.ts`).
  - `hooks/`: Custom React hooks (`usePrediction.ts`, `useFlights.ts`).
  - `lib/`: Utility libraries (`api.ts`, `formatters.ts`).
