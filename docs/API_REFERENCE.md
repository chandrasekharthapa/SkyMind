# SkyMind Copilot — API Specification & Endpoint Reference

## 1. Core Endpoints

### `POST /api/v1/predict`
- **Purpose**: Generates AI price forecast, booking recommendations, confidence scores, and dynamic timeline for a flight route.
- **Request Body**:
  ```json
  {
    "origin": "DEL",
    "destination": "BOM",
    "departure_date": "2026-08-15"
  }
  ```
- **Response Schema (`CanonicalForecastDTO` attached under `canonical_forecast`)**:
  ```json
  {
    "predicted_price": 6608.0,
    "canonical_forecast": {
      "current_fare": 6487.0,
      "expected_minimum_fare": 6487.0,
      "optimal_booking_horizon": 0,
      "optimal_booking_date": "2026-07-26",
      "recommendation_decision": "BOOK_NOW",
      "recommendation_reasons": [
        "Today's expected fare is already the lowest expected price across all forecast horizons."
      ],
      "calculated_savings": 0.0,
      "percentage_savings": 0.0,
      "confidence_score": 95.0,
      "confidence_breakdown": {
        "model_validation_score": 95.0,
        "market_data_quality": 1.0,
        "prediction_reliability": 95.0
      },
      "timeline": [
        {
          "horizon_days": 0,
          "booking_date": "2026-07-26",
          "predicted_price": 6487.0,
          "lower_bound": 6227.52,
          "upper_bound": 6746.48,
          "confidence_score": 95.0,
          "is_optimal": true,
          "metadata": { "currency": "INR" }
        }
      ],
      "diagnostics": {
        "invariants_passed": true,
        "violations": [],
        "execution_time_ms": 1.2
      },
      "forecast_metadata": {
        "forecast_version": "2.0.0",
        "model_version": "XGBoost v2",
        "provider": "SkyMind Intelligence Engine",
        "currency": "INR"
      },
      "is_valid": true
    }
  }
  ```

### `GET /health`
- **Purpose**: System health check endpoint.
- **Response**: `{"status": "ok", "version": "2.0.0"}`

### `GET /api/v1/performance`
- **Purpose**: Model performance metrics (MAPE, training dates, feature count).
