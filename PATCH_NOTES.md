# SkyMind — Patch Notes (April 2026)

> **⚠️ Audit flag (2026-09-28):** Some operational claims below are not supported by the current code and are left in place only for history. Specifically: (a) L7 "**synthetic** fare population" contradicts the project's zero-synthetic-data policy — the ingestion path now stores only scraped values and invents nothing; (b) L9 "retrains every 24 hours" and L8 alert cron run **only** via the GitHub Actions workflow, and daily retraining will produce no model until the corpus carries `departure_time` labels; (c) L10/L26 cloud model auto-sync / "pull the latest model from the cloud" is not a demonstrated hot-swap — serving now fails-closed when no clean artifact loads. See `AUDIT.md`.

## 🚀 FEATURE: GitHub-Driven Automation Pipeline
> **Issue**: Server downtime on Render (free tier) caused background jobs to miss alert checks and data ingestion cycles.

- **Solution**: Implemented a unified GitHub Actions pipeline (`backend/run_pipeline.py`).
- **Data Ingestion**: Automated daily synthetic fare population into Supabase.
- **Alert Checks**: Cron-triggered alert monitoring ensures notifications are sent even if the backend is sleeping.
- **Model Retraining**: XGBoost model now retrains every 24 hours on GitHub's infrastructure.
- **Cloud Persistence**: Trained models are automatically pushed to **Supabase Storage** (`models/global_model.pkl`), allowing the backend to sync on restart.

---

## 🎨 UI/UX: Mobile Stability & "Clean White" Realignment
- **Mobile Overflow Fix**: Resolved critical bug where date inputs extended beyond card boundaries on mobile devices.
  - Reduced horizontal padding on narrow viewports.
  - Implemented `min-width: 0` and `max-width: 100%` on all `.ui-input` elements.
  - Forced `box-sizing: border-box` to ensure padding doesn't break layout.
- **Aesthetic Finalization**: Stripped away legacy "Grey" ornamentation in favor of a cinematic white executive look.
- **Form UX**: Improved `AirportDropdown` and `PassengerSelector` alignment on small screens.

---

## 🛠️ Backend: Database & ML Resilience
- **Supabase Storage Integration**: Added `Database.upload_model()` and `Database.download_model()` to manage ML artifacts.
- **Model Auto-Sync**: The `PricePredictor` now automatically attempts to pull the latest model from the cloud if the local file is missing.
- **Engine Refinement**: Updated `FlightDataService` to handle larger training batch generations for more robust daily updates.

---

## 🔑 Deployment Updates
- **GitHub Secrets**: New requirements for `SUPABASE_SERVICE_KEY` in GitHub Actions.
- **Bucket Creation**: New requirement for a `models` bucket in Supabase Storage.
- **PYTHONPATH Fix**: Standardized backend module resolution in CI/CD environments.

---

## 📜 Full Version History
- **v2.4.1**: Mobile UI overflow resolution & layout stabilization.
- **v2.4.0**: Implementation of GitHub Actions Daily Pipeline + Cloud Model Sync.
- **v2.3.0**: "Clean White" aesthetic update & legacy ornament removal.
- **v2.2.0**: Transition from Prophet to XGBoost v2.4 (900 estimators).
