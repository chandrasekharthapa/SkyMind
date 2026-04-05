# SkyMind — Complete Integration & Deployment Guide
> Full-system sync: FastAPI backend ↔ Next.js frontend (2026 production)

---

## What Was Done

### Zero Ghost Connections — Integration Map

```
POST /predict              ←→  hooks/usePrediction.ts  →  app/predict/page.tsx
GET  /airports             ←→  lib/api.ts searchAirports  →  FlightSearchForm.tsx
GET  /flights/search       ←→  lib/api.ts searchFlights  →  app/flights/page.tsx
POST /booking/create       ←→  lib/api.ts createBooking  →  app/booking/page.tsx
POST /payment/create-order ←→  lib/api.ts createRazorpayOrder  →  app/checkout/page.tsx
POST /payment/verify       ←→  lib/api.ts verifyPayment  →  app/checkout/page.tsx
POST /alerts/subscribe     ←→  hooks/useAlerts.ts addAlert  →  app/predict/page.tsx
GET  /alerts/user/{id}     ←→  hooks/useAlerts.ts poll  →  app/dashboard/page.tsx
DELETE /alerts/{id}        ←→  hooks/useAlerts.ts removeAlert
POST /auth/signup          ←→  app/auth/page.tsx
GET  /user/trips           ←→  app/dashboard/page.tsx
GET  /health               ←→  deployment health check
```

---

## Quick Start (Local Dev)

### 1. Backend

```bash
cd backend

# Copy and fill env
cp .env.example .env
# Fill: SUPABASE_URL, SUPABASE_SERVICE_KEY, DATABASE_URL
# Optional: AMADEUS_*, RAZORPAY_*, GMAIL_*, FAST2SMS_API_KEY

pip install -r requirements.txt

uvicorn main:app --reload --port 8000
# → http://localhost:8000
# → http://localhost:8000/docs  (Swagger UI)
```

### 2. Frontend

```bash
cd frontend

# Copy and fill env
cp .env.local.example .env.local
# Fill: NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY
# NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
# NEXT_PUBLIC_RAZORPAY_KEY=rzp_test_xxxx

npm install
npm run dev
# → http://localhost:3000
```

---

## Environment Variables Reference

### Backend `.env`

| Key | Required | Description |
|-----|----------|-------------|
| `SUPABASE_URL` | ✅ | Project URL from Supabase dashboard |
| `SUPABASE_SERVICE_KEY` | ✅ | Service role key (not anon) |
| `DATABASE_URL` | ✅ | PostgreSQL connection string for ML training |
| `SECRET_KEY` | ✅ | JWT secret — generate with `openssl rand -hex 32` |
| `AMADEUS_CLIENT_ID` | ⚡ | Amadeus API client ID (free sandbox) |
| `AMADEUS_CLIENT_SECRET` | ⚡ | Amadeus API client secret |
| `RAZORPAY_KEY_ID` | ⚡ | Razorpay key ID (`rzp_test_*` for sandbox) |
| `RAZORPAY_KEY_SECRET` | ⚡ | Razorpay secret |
| `GMAIL_USER` | 📧 | Gmail address for notifications |
| `GMAIL_APP_PASSWORD` | 📧 | Gmail App Password (not regular password) |
| `FAST2SMS_API_KEY` | 📱 | Fast2SMS key for Indian SMS |
| `TWILIO_ACCOUNT_SID` | 📱 | Twilio SID (fallback SMS + WhatsApp) |
| `TWILIO_AUTH_TOKEN` | 📱 | Twilio auth token |
| `CORS_ORIGINS` | 🌐 | Comma-separated allowed frontend origins |

### Frontend `.env.local`

| Key | Required | Description |
|-----|----------|-------------|
| `NEXT_PUBLIC_API_BASE_URL` | ✅ | Backend URL (primary) |
| `NEXT_PUBLIC_API_URL` | ✅ | Backend URL (legacy alias, keep same value) |
| `NEXT_PUBLIC_SUPABASE_URL` | ✅ | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | ✅ | Supabase anon key |
| `NEXT_PUBLIC_RAZORPAY_KEY` | ⚡ | Razorpay publishable key |

---

## Production Deployment

### Backend → Render

1. Connect GitHub repo to [render.com](https://render.com)
2. New Web Service → `backend/` directory
3. Build: `pip install -r requirements.txt`
4. Start: `uvicorn main:app --host 0.0.0.0 --port $PORT --lifespan on`
5. Add all env vars from the table above
6. Set `CORS_ORIGINS=https://your-app.vercel.app`
7. Health check path: `/health`

### Frontend → Vercel

```bash
cd frontend
npx vercel --prod
```

In Vercel dashboard → Settings → Environment Variables:
- `NEXT_PUBLIC_API_BASE_URL` = `https://your-backend.onrender.com`
- `NEXT_PUBLIC_API_URL` = same value
- Add all other `NEXT_PUBLIC_*` vars

---

## Key Architecture Decisions

### CORS
`main.py` reads `CORS_ORIGINS` from env at startup so you never need to redeploy just to add a new frontend domain. Localhost:3000 is always allowed.

### Lifespan
Uses `@asynccontextmanager` lifespan (FastAPI ≥0.93). The deprecated `@app.on_event("startup")` pattern is gone. APScheduler starts inside lifespan and the ML model loads on startup.

### API Base URL
All frontend API calls go through `apiRequest()` in `lib/api.ts` which reads `NEXT_PUBLIC_API_BASE_URL` first, falling back to `NEXT_PUBLIC_API_URL`, then `http://localhost:8000`. This means you only need to set one env var.

### Passenger Data
`passengers` in `POST /booking/create` is strictly `List[PassengerData]` (array of objects). The frontend sends `[{ type, first_name, last_name, ... }]` — never a flat string or a single object.

### Prediction Endpoint
`POST /predict` lives in `main.py` (not inside a router) so it's reachable at `/predict` exactly as the frontend expects. The `/ai/price` GET endpoint in `routers/prediction.py` is for internal dashboard widgets.

### Date Handling
All dates are ISO-8601 strings throughout: `"2026-05-15"` for dates, `"2026-05-15T06:30:00"` for datetimes. No `Date` objects cross the API boundary.

### ML Model
The XGBoost predictor is a singleton (`get_predictor()`). It loads from disk on startup if a saved model exists, otherwise trains from Supabase `price_history` data on first prediction call. **Do not change the feature list or hyperparameters.**

---

## Database Schema Notes

The app expects these Supabase tables:
- `airports` — IATA codes, city, name, country, state
- `airlines` — carrier data  
- `routes` — origin/destination pairs with pricing
- `flights` — cached live flight data
- `price_history` — ML training data (origin, destination, price, features)
- `price_alerts` — user price subscriptions
- `bookings` — booking records with `flight_offer_data` JSONB
- `profiles` — user profiles linked to `auth.users`
- `v_domestic_routes` — view joining routes + airports

Run `backend/database/skymind_complete.sql` in Supabase SQL Editor to set up the full schema.

---

## Verification Checklist

```
Backend:
  ✅ GET  /health              → { status: "ok", model: "loaded" }
  ✅ GET  /airports?q=del      → airport suggestions
  ✅ GET  /flights/search?origin=DEL&destination=BOM&departure_date=... → flights
  ✅ POST /predict             → { predicted_price, forecast[], trend, recommendation }
  ✅ POST /booking/create      → { booking_id, booking_reference }
  ✅ POST /payment/create-order → { order_id, amount, key }
  ✅ POST /payment/verify      → { success: true }
  ✅ POST /alerts/subscribe    → { alert_id, message }
  ✅ GET  /alerts/user/{id}    → { alerts[], triggered[] }
  ✅ DELETE /alerts/{id}       → { success: true }

Frontend:
  ✅ / (home)                  → Landing page with search form
  ✅ /flights                  → Search results with ML badges
  ✅ /predict                  → 30-day chart + alert form
  ✅ /booking                  → Passenger form
  ✅ /checkout                 → Razorpay payment
  ✅ /success                  → Booking confirmation
  ✅ /dashboard                → Trips + alerts
  ✅ /auth                     → Email/OTP/Google login

Data flow:
  ✅ Prediction displays as "BOOK NOW" not "BOOK_NOW"
  ✅ Confidence displays as "87%" not "0.87"
  ✅ Forecast has 30 entries with { day, date, price, lower, upper }
  ✅ Chart renders with shaded CI bands
  ✅ Booking passengers sent as array of objects
  ✅ Razorpay signature verified with HMAC-SHA256 compare_digest
  ✅ CORS allows localhost:3000 and production Vercel URL
  ✅ Scheduler starts via asynccontextmanager lifespan
```
