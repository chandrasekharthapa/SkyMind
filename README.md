# ✈️ SkyMind — AI Flight Optimization & Booking Platform

A production-grade intelligent flight platform combining real-time search, ML price prediction, hidden route discovery, and seamless booking.

---

## 🧠 AI Features

| Feature | Description |
|---------|-------------|
| **Price Prediction** | Prophet + scikit-learn forecasts future prices with confidence intervals |
| **Hidden Route Finder** | Dijkstra graph algorithm finds cheaper multi-stop routes |
| **AI Travel Assistant** | Natural language flight queries via LLM |
| **Smart Price Alerts** | Cron-based monitoring with Supabase notifications |

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────┐
│                   FRONTEND (Vercel)               │
│   Next.js 14 + TypeScript + TailwindCSS           │
│   ShadCN UI + Framer Motion + Mapbox              │
└────────────────────┬─────────────────────────────┘
                     │ REST API
┌────────────────────▼─────────────────────────────┐
│                  BACKEND (Render)                  │
│   FastAPI + Python 3.11                           │
│   scikit-learn + Prophet + Pandas                 │
└────┬──────────────┬──────────────────────────────┘
     │              │
┌────▼────┐  ┌──────▼──────┐
│Supabase │  │ Amadeus API  │
│Postgres │  │ AviationStack│
└─────────┘  └─────────────┘
```

---

## 📦 Tech Stack

**Frontend**
- Next.js 14 (App Router)
- TypeScript
- TailwindCSS + ShadCN UI
- Framer Motion
- React Query (TanStack)
- Chart.js + react-chartjs-2
- Mapbox GL JS

**Backend**
- FastAPI
- SQLAlchemy + Alembic
- Supabase PostgreSQL
- Redis (caching)

**AI/ML**
- scikit-learn (price prediction)
- Prophet (time-series forecasting)
- Pandas + NumPy

**APIs**
- Amadeus Flight Offers Search API
- AviationStack (live flight data)
- Razorpay (payments)

---

## 🚀 Quick Start

### Prerequisites
- Node.js 18+
- Python 3.11+
- Supabase account
- Amadeus API key (free sandbox)
- Razorpay test keys

### 1. Clone & Install

```bash
git clone https://github.com/yourname/flight-ai-platform
cd flight-ai-platform

# Frontend
cd frontend && npm install

# Backend
cd ../backend && pip install -r requirements.txt
```

### 2. Environment Variables

**frontend/.env.local**
```env
NEXT_PUBLIC_SUPABASE_URL=your_supabase_url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_anon_key
NEXT_PUBLIC_MAPBOX_TOKEN=your_mapbox_token
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_RAZORPAY_KEY=rzp_test_xxxx
```

**backend/.env**
```env
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_KEY=your_service_key
DATABASE_URL=postgresql://user:pass@host:5432/db
AMADEUS_CLIENT_ID=your_amadeus_client_id
AMADEUS_CLIENT_SECRET=your_amadeus_secret
AVIATIONSTACK_API_KEY=your_aviationstack_key
RAZORPAY_KEY_ID=rzp_test_xxxx
RAZORPAY_KEY_SECRET=your_razorpay_secret
REDIS_URL=redis://localhost:6379
SECRET_KEY=your_jwt_secret_key
```

### 3. Database Setup

```bash
# Run migrations in Supabase SQL editor (paste contents of database/schema.sql)
```

### 4. Run Locally

```bash
# Terminal 1: Backend
cd backend
uvicorn main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend
npm run dev
```

---

## 🌐 Deployment

### Supabase Setup
1. Create project at supabase.com
2. Run `database/schema.sql` in SQL Editor
3. Enable Row Level Security on all tables
4. Copy URL and anon key to env files

### Amadeus API (Free Sandbox)
1. Register at developers.amadeus.com
2. Create an app → get Client ID & Secret
3. Free sandbox: 2,000 API calls/month

### Razorpay Test Mode
1. Register at razorpay.com
2. Settings → API Keys → Generate Test Keys
3. Use `rzp_test_*` keys in env

### Vercel (Frontend)
```bash
cd frontend
vercel --prod
# Set all NEXT_PUBLIC_* env vars in Vercel dashboard
```

### Render (Backend)
1. Connect GitHub repo to Render
2. New Web Service → backend directory
3. Build: `pip install -r requirements.txt`
4. Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add all env vars in Render dashboard

---

## 📁 Project Structure

```
flight-ai-platform/
├── frontend/
│   ├── app/
│   │   ├── page.tsx              # Landing page
│   │   ├── flights/page.tsx      # Search results
│   │   ├── predict/page.tsx      # Price prediction
│   │   ├── booking/page.tsx      # Booking form
│   │   ├── checkout/page.tsx     # Payment
│   │   └── dashboard/page.tsx   # User dashboard
│   ├── components/
│   │   ├── ui/                   # ShadCN components
│   │   ├── layout/               # Header, Footer
│   │   ├── flights/              # Flight cards, filters
│   │   ├── charts/               # Price charts
│   │   └── maps/                 # Mapbox components
│   ├── lib/
│   │   ├── supabase.ts           # Supabase client
│   │   ├── api.ts                # API client
│   │   └── utils.ts              # Utilities
│   └── hooks/                    # Custom React hooks
├── backend/
│   ├── main.py                   # FastAPI app
│   ├── routers/                  # Route handlers
│   ├── models/                   # SQLAlchemy models
│   ├── services/                 # Business logic
│   └── ml/                       # ML models
├── database/
│   └── schema.sql                # Full DB schema
└── docs/
    └── api.md                    # API documentation
```

---

## 🔑 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/flights/search` | Search flights via Amadeus |
| GET | `/flights/prediction/{route}` | Get AI price prediction |
| GET | `/flights/hidden-routes` | Find cheaper alternate routes |
| POST | `/booking/create` | Create booking |
| POST | `/payment/create-order` | Create Razorpay order |
| POST | `/payment/verify` | Verify payment |
| GET | `/user/trips` | Get user's trips |
| POST | `/alerts/subscribe` | Subscribe to price alert |

---

## 📜 License

MIT
