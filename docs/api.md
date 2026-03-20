# SkyMind API Documentation

Base URL: `https://your-api.onrender.com`

## Authentication
Currently using Supabase JWT. Pass token in `Authorization: Bearer <token>` header.

---

## Endpoints

### Flight Search
**GET** `/flights/search`

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| origin | string | ✓ | IATA code (e.g. DEL) |
| destination | string | ✓ | IATA code (e.g. DXB) |
| departure_date | string | ✓ | YYYY-MM-DD |
| return_date | string | | YYYY-MM-DD |
| adults | int | | Default: 1 |
| cabin_class | string | | ECONOMY/BUSINESS/FIRST |
| currency | string | | Default: INR |

**Response:**
```json
{
  "flights": [...],
  "count": 15,
  "search_params": {}
}
```

---

### Price Prediction
**GET** `/prediction/price`

```json
{
  "predicted_price": 6500.0,
  "recommendation": "BOOK_SOON",
  "reason": "Good window to book. Prices may rise.",
  "price_trend": "RISING",
  "probability_increase": 0.68,
  "confidence": 0.78
}
```

---

### 30-Day Forecast
**GET** `/prediction/forecast`

```json
{
  "forecast": [
    {
      "date": "2025-02-15",
      "price": 6200,
      "confidence_low": 5580,
      "confidence_high": 6820
    }
  ],
  "best_day": {...},
  "worst_day": {...}
}
```

---

### Hidden Routes
**GET** `/prediction/hidden-routes`

```json
{
  "hidden_routes": [
    {
      "path": ["DEL", "IST", "CDG"],
      "total_price": 28000,
      "savings_vs_direct": 6999,
      "savings_percent": 20.0
    }
  ]
}
```

---

### Create Booking
**POST** `/booking/create`

```json
{
  "flight_offer_id": "offer_123",
  "flight_data": {...},
  "passengers": [
    {
      "type": "ADULT",
      "first_name": "Rahul",
      "last_name": "Sharma",
      "passport_number": "A1234567"
    }
  ],
  "contact_email": "user@example.com",
  "contact_phone": "+91-9876543210"
}
```

---

### Payment
**POST** `/payment/create-order`
**POST** `/payment/verify`

---

### Price Alerts
**POST** `/alerts/subscribe`

```json
{
  "user_id": "uuid",
  "origin_code": "DEL",
  "destination_code": "LHR",
  "departure_date": "2025-06-15",
  "target_price": 28000
}
```
