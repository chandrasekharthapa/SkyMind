# SkyMind Prediction Pipeline — Architecture & Production Specification

## 1. Overview & Architecture

The SkyMind Price Prediction Pipeline generates automated daily fare forecasts, observed market snapshot statistics, and deterministic booking recommendations for domestic flight routes.

```
Frontend (Next.js)
       │
       ▼ (HTTP POST /api/v1/predict)
FastAPI Router (routers/predict.py)
       │
       ▼
PredictionService (services/prediction_service.py)
       ├──► MarketSnapshotProvider (services/market_snapshot_provider.py)
       │       └──► GoogleFlightsProvider (services/flight_data_provider.py)
       │               └──► FlightSearchService / MCP Browser Scraper
       │
       ├──► FeatureEngineeringPipeline (ml/feature_engineering_pipeline.py)
       ├──► PricePredictor [XGBoost] (ml/price_model.py)
       ├──► ForecastEngine (services/forecast_engine.py)
       └──► RecommendationEngine (services/recommendation_engine.py)
```

---

## 2. Canonical Data Contract

All internal services pass and consume `NormalizedFlight` objects. Provider adapters normalize raw external search payloads into `NormalizedFlight` instances.

### `NormalizedFlight` Schema
```python
class NormalizedFlight(BaseModel):
    id: str
    primary_airline: str
    primary_airline_name: str
    seats_available: Optional[int] = None
    flight_number: str
    itineraries: List[NormalizedItinerary]
    price: float
    currency: str = "INR"
    metadata: Optional[Dict[str, Any]] = None
```

---

## 3. Confidence Semantics

SkyMind defines three distinct confidence metrics in the prediction payload:

1. **Top-Level `confidence`**: `overall_confidence = model_validation_accuracy * snapshot_quality`
   - *Meaning*: Reflects combined ML model baseline accuracy (e.g., 95.0%) scaled by live market data freshness and completeness (`snapshot_quality` between 0.5 and 1.0).
2. **Recommendation `confidence`**: `recommendation_confidence = overall_confidence`
   - *Meaning*: Trustworthiness score for the booking decision (`BOOK_NOW`, `WAIT`, `MONITOR`).
3. **Forecast Day `confidence`**: `horizon_confidence = model_validation_accuracy * (1.0 - (day * 0.02))`
   - *Meaning*: Model confidence decayed by temporal distance from today (0d = 95%, 7d = 81.7%).

---

## 4. Recommendation Logic & Thresholds

Booking decisions are computed deterministically in `RecommendationEngine`:

* **`BOOK_NOW`**: Triggered when `forecast_price > current_lowest * (1 + BOOK_THRESHOLD)` AND `potential_savings >= MIN_EXPECTED_SAVINGS` (₹500).
* **`WAIT`**: Triggered when `forecast_price < current_lowest * (1 - WAIT_THRESHOLD)`.
* **`MONITOR`**: Triggered when `forecast_price` remains within normal market variance range (`MONITOR_RANGE_PERCENT`), or when live market data is unavailable.

---

## 5. Resilience & Failure Modes

* **Circuit Breaker**: Internal `CircuitBreaker` trips `OPEN` after 5 consecutive transport failures to prevent cascading downstream delays. Transport failures are isolated from internal parsing logic.
* **Degraded / Historical Mode**: When live market search is unavailable or times out, the pipeline seamlessly transitions to historical booking curve context (`prediction_mode: "historical_only"`, `provider_status: "DEGRADED"`). `lowest_fare` is safely set to `null` without throwing exceptions.

---

## 6. API Response Contract (`PredictionResponse`)

```json
{
  "schema_version": "1.0.0",
  "api_version": "v1",
  "backend_version": "11.0.0",
  "prediction_version": "2.0.0",
  "predicted_price": 8315.56,
  "current_market": {
    "lowest_fare": 6697.0,
    "average_fare": 7541.55,
    "snapshot_timestamp": "2026-07-22T16:58:37Z",
    "provider": "Google Flights MCP"
  },
  "forecast": [ ... ],
  "recommendation": {
    "decision": "BOOK_NOW",
    "reasons": [ "..." ],
    "confidence": 95.0
  },
  "confidence": 95.0,
  "search_metadata": {
    "provider": "Google Flights MCP",
    "retrieval_time": "2026-07-22T16:58:37Z",
    "search_latency": 14.1,
    "flight_count": 20,
    "prediction_mode": "live",
    "provider_status": "ONLINE",
    "market_snapshot_available": true
  },
  "market_snapshot": { ... },
  "prediction_horizon": 3
}
```
