# SkyMind Copilot — Data Flow Reference

## 1. End-to-End Prediction Data Flow

```
[User UI Input (origin: DEL, destination: BOM)]
                       │
                       ▼
[Frontend API Call: predict({ origin, destination })]
                       │
                       ▼
[FastAPI /api/v1/predict Route Handler]
                       │
                       ▼
[PredictionService.predict()]
  ├── 1. LiveMarketService.get_snapshot() -> Retrieves current_market.lowest_fare
  ├── 2. ModelRegistry -> Evaluates ML feature vectors & XGBoost inference
  └── 3. CanonicalForecastService.build_canonical_forecast()
           ├── TimelineBuilder -> Creates TimelinePointDomain[]
           ├── SavingsCalculator -> Computes exact (abs_savings, pct_savings)
           ├── RecommendationEngineStrategy -> Formulates decision & reasons
           └── ForecastValidationEngine -> Asserts 4 mathematical invariants
                       │
                       ▼
[ForecastMapper.to_dto()]
                       │
                       ▼
[FastAPI HTTP Response JSON]
                       │
                       ▼
[Frontend Page (cForecast direct presentation)]
  ├── Current Live Fare KPI: cForecast.current_fare
  ├── Expected Minimum Fare KPI: cForecast.expected_minimum_fare
  ├── Potential Savings KPI: cForecast.calculated_savings
  ├── Forecast Confidence KPI: cForecast.confidence_score
  ├── Forecast Timeline Grid: cForecast.timeline
  └── ForecastDebugPanel: cForecast.diagnostics & raw payload
```
