# SkyMind Copilot — Component Documentation Reference

## 1. Backend Core Components

### `backend.domain.canonical_forecast`
- **`TimelinePointDomain`**: Immutable domain representation of a timeline forecast point across an arbitrary lead time horizon (`horizon_days`, `booking_date`, `predicted_price`, `lower_bound`, `upper_bound`, `confidence_score`, `is_optimal`, `metadata`).
- **`ForecastDiagnostics`**: Stores invariant assertion pass status, violation messages, and execution latency.
- **`CanonicalForecastDomain`**: Root domain object holding reconciled metrics, recommendation decision, savings calculations, confidence breakdowns, and timeline.

### `backend.services.forecast` Package
- **`SavingsCalculator`**: Static, pure mathematical helper computing absolute and percentage savings:
  $$\text{calculate\_savings}(\text{current\_fare}, \text{expected\_min\_fare})$$
- **`TimelineBuilder`**: Builds chronologically sorted timeline points, automatically aligning Day 0 (Today) and guaranteeing $\text{lower\_bound} \le \text{predicted\_price} \le \text{upper\_bound}$.
- **`ConfidenceEngine`**: Computes unified confidence score ($0-100\%$) based on model validation metrics and market provider quality.
- **`ForecastValidationEngine`**: Enforces the 4 core mathematical invariants. Fails development loudly and produces structured diagnostic payloads in production.
- **`RecommendationEngineStrategy`**: Evaluates timeline points against live market fare to determine `BOOK_NOW`, `WAIT`, or `MONITOR` decisions and optimal booking dates.
- **`ForecastAssembler`**: Coordinates building, scoring, and validating the domain object.
- **`CanonicalForecastService`**: High-level singleton entry point.

### `backend.mappers.forecast_mapper`
- **`ForecastMapper`**: DTO mapping class converting `CanonicalForecastDomain` domain objects into JSON DTO payloads (`CanonicalForecastDTO`).

### `backend.services.prediction_service`
- **`PredictionService`**: Main ML inference service. Manages feature vector construction, model registry calls, and snapshot enrichment.

---

## 2. Frontend Core Components

### `frontend/app/predict/page.tsx`
- Pure presentation container for the AI Forecast dashboard. Consumes `result.canonical_forecast` directly with 0 client-side business calculations or price subtractions.

### `frontend/components/charts/PriceChart.tsx`
- Dynamic SVG price forecast chart component. Uses index-based `px(i)` coordinate mapping to place Day 0 ("Today") at $x = 0$ cleanly.

### `frontend/components/debug/ForecastDebugPanel.tsx`
- Interactive developer audit panel displaying raw API payloads, canonical forecast objects, timeline points, recommendation inputs, and real-time invariant status matrices.
