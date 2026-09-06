# SkyMind — Deployment & Operations Guide (2026)

This guide covers the full deployment cycle, including the new **GitHub Actions Pipeline** and **Cloud Model Persistence**.

---

## 1. Prerequisites & Services
- **Backend**: [Render.com](https://render.com) (Web Service)
- **Frontend**: [Vercel.com](https://vercel.com) (Next.js)
- **Database/Cloud**: [Supabase.com](https://supabase.com) (Postgres + Storage)
- **CI/CD**: GitHub Actions

---

## 2. Supabase Configuration (Critical)

### Database
Run `backend/database/skymind_complete.sql` in the Supabase SQL Editor to initialize all tables, views, and functions.

### Storage
1. Go to **Storage** in the Supabase Dashboard.
2. Create a new bucket named `models`.
3. Set the bucket to **Public** (or ensure your Service Role key has full access).
4. This bucket will hold the `global_model.pkl` trained by GitHub Actions.

---

## 3. GitHub Actions Setup (Retraining Pipeline)

The daily pipeline ensures your AI model stays accurate and your alerts stay active even if your Render backend is sleeping.

### GitHub Secrets
Add the following to **Settings > Secrets and variables > Actions**:
| Secret | Description |
|:---|:---|
| `SUPABASE_URL` | Your Supabase Project URL |
| `SUPABASE_SERVICE_KEY` | The **service_role** key (required for storage uploads) |
| `GMAIL_USER` | Gmail address for flight alerts |
| `GMAIL_APP_PASSWORD` | 16-character Gmail App Password |
| `TWILIO_ACCOUNT_SID` | (Optional) For SMS/WhatsApp alerts |
| `TWILIO_AUTH_TOKEN` | (Optional) |

---

## 4. Backend Deployment (Render)

### Environment Variables
Ensure the following are set in the Render Dashboard:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `DATABASE_URL` (Direct Postgres connection string)
- `CORS_ORIGINS` (Your Vercel URL)
- `SECRET_KEY` (Random string for JWT)

### Build & Start
- **Build Command**: `pip install -r backend/requirements.txt`
- **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Root Directory**: `backend` (or run from root with `uvicorn backend.main:app`)

---

## 5. Frontend Deployment (Vercel)

### Environment Variables
- `NEXT_PUBLIC_API_BASE_URL`: Your Render URL (e.g., `https://skymind-api.onrender.com`)
- `NEXT_PUBLIC_SUPABASE_URL`: Same as backend
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`: Supabase **anon** key
- `NEXT_PUBLIC_RAZORPAY_KEY`: Your Razorpay test key

---

## 6. Verification Checklist

### Local Pipeline Test
Run this command from the project root to verify the GitHub logic locally:
```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)/backend
python backend/run_pipeline.py
```
*Check your Supabase `models` bucket to see if `global_model.pkl` appeared.*

### Production Sync Test
1. Deploy to Render.
2. Delete `backend/ml/models/global_model.pkl` if it exists locally.
3. Start the server. 
4. **Expected Result**: Log should show `Local model missing, attempting to download from Supabase Storage...` followed by `Model downloaded successfully`.
