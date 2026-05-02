"""
SkyMind — Database Layer
Wraps Supabase client and SQLAlchemy for ML training data retrieval.
Falls back to synthetic data generation when DB is empty.
"""

import os
import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

load_dotenv()
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════
# Supabase client
# ══════════════════════════════════════════════════════════════════════

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
_SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

if not _SUPABASE_URL or not _SUPABASE_KEY:
    raise RuntimeError(
        "Missing Supabase credentials (SUPABASE_URL / SUPABASE_SERVICE_KEY)"
    )

# Service client: Bypass RLS (for admin tasks)
_supabase_service = create_client(_SUPABASE_URL, _SUPABASE_KEY)

# Anon client: Respect RLS (for client-facing tasks if needed, though usually handled by server)
_supabase_anon = None
if _SUPABASE_ANON_KEY:
    _supabase_anon = create_client(_SUPABASE_URL, _SUPABASE_ANON_KEY)

# ══════════════════════════════════════════════════════════════════════
# SQLAlchemy engine (used for ML training queries)
# ══════════════════════════════════════════════════════════════════════

_DATABASE_URL = os.getenv("DATABASE_URL", "")
_engine = None
_SessionLocal = None

if _DATABASE_URL:
    try:
        _engine = create_engine(
            _DATABASE_URL,
            pool_pre_ping=True,
            pool_recycle=300,
            connect_args={"sslmode": "require"},
        )
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
        logger.info("SQLAlchemy engine initialised.")
    except Exception as exc:
        logger.warning(f"SQLAlchemy init failed (non-fatal): {exc}")


# ══════════════════════════════════════════════════════════════════════
# Synthetic dataset generator (used when DB is empty)
# ══════════════════════════════════════════════════════════════════════

def _generate_synthetic_training_dataset() -> pd.DataFrame:
    """
    Generate a complete synthetic training dataset using the internal
    FlightDataService pricing engine. Covers all routes × date horizons.
    Used as fallback when price_history table is empty.
    """
    from services.flight_data_service import (
        ROUTES,
        ROUTE_BASE_PRICES,
        ROUTE_AIRLINES,
        AIRLINE_MULTIPLIERS,
        PEAK_MONTHS,
        HOLIDAYS,
        _sigmoid_demand,
        _seasonality_factor,
        _weekend_factor,
        _holiday_factor,
        _compute_price,
        _compute_demand_score,
    )
    import random
    import math

    logger.info("Generating synthetic training dataset (no DB data found)...")

    records = []
    today = datetime.now(timezone.utc).date()

    # Generate across a range of dates (past 90 days + future 60 days)
    date_range = (
        [today - timedelta(days=d) for d in range(1, 91)] +
        [today + timedelta(days=d) for d in range(0, 61)]
    )

    # Days-until-departure samples (mirrors real booking window distribution)
    days_buckets = [0, 1, 2, 3, 5, 7, 10, 14, 21, 28, 45, 60, 90]

    for origin, destination in ROUTES:
        key = (origin, destination)
        base_price = ROUTE_BASE_PRICES.get(key, 5000)
        airlines = ROUTE_AIRLINES.get(key, [("AI", 0.5), ("6E", 0.5)])

        for days_until_dep in days_buckets:
            # Reconstruct a plausible departure date
            dep_date = today + timedelta(days=days_until_dep)
            recorded_at = dep_date - timedelta(days=days_until_dep)

            for airline_code, _ in airlines:
                seed = hash(f"{origin}{destination}{dep_date}{airline_code}") % (2**31)
                rng = random.Random(seed)

                dep_hour = rng.randint(6, 22)
                seats = int(max(1, min(50, 50 * math.exp(-0.08 * max(0, 14 - days_until_dep)))))
                seats = rng.randint(max(1, seats - 5), min(50, seats + 5))

                is_holiday = (dep_date.month, dep_date.day) in HOLIDAYS
                holiday_mult = 1.25 if is_holiday else 1.0

                price = _compute_price(
                    base_price=base_price,
                    airline_code=airline_code,
                    days_until_dep=days_until_dep,
                    seats_available=seats,
                    dep_date=dep_date,
                    dep_hour=dep_hour,
                    noise_seed=seed,
                )

                # Price change features (simulated)
                price_1d_ago = _compute_price(
                    base_price, airline_code,
                    min(days_until_dep + 1, 90), seats, dep_date, dep_hour,
                    noise_seed=seed + 1,
                )
                price_3d_ago = _compute_price(
                    base_price, airline_code,
                    min(days_until_dep + 3, 90), seats, dep_date, dep_hour,
                    noise_seed=seed + 3,
                )

                records.append({
                    "origin_code": origin,
                    "destination_code": destination,
                    "airline_code": airline_code,
                    "price": float(price),
                    "currency": "INR",
                    "departure_date": dep_date,
                    "days_until_dep": days_until_dep,
                    "urgency": round(1 / (days_until_dep + 1), 4),
                    "day_of_week": dep_date.weekday(),
                    "month": dep_date.month,
                    "week_of_year": dep_date.isocalendar()[1],
                    "hour_of_day": dep_hour,
                    "is_peak_hour": 1 if dep_hour in [7, 8, 9, 18, 19, 20, 21] else 0,
                    "is_holiday": is_holiday,
                    "is_weekend": dep_date.weekday() >= 5,
                    "seats_available": seats,
                    "recorded_at": datetime(
                        recorded_at.year, recorded_at.month, recorded_at.day,
                        dep_hour, 0, 0, tzinfo=timezone.utc
                    ).isoformat(),
                    "is_live": 2.0,  # Weighted as if live for training
                    "training_weight": 1.5,
                    "price_change_1d": float(price - price_1d_ago),
                    "price_change_3d": float(price - price_3d_ago),
                    "demand_score": _compute_demand_score(days_until_dep, dep_date),
                    "seasonality_factor": float(_seasonality_factor(dep_date)),
                })

    df = pd.DataFrame(records)
    logger.info(f"Synthetic training dataset: {len(df)} rows generated.")
    return df


# ══════════════════════════════════════════════════════════════════════
# Database class
# ══════════════════════════════════════════════════════════════════════

class Database:
    def __init__(self):
        self.supabase = _supabase_service
        self.anon = _supabase_anon

    # ── ML training dataset ─────────────────────────────────────────
    def get_training_dataset(self) -> pd.DataFrame:
        """
        Fetch price_history rows for XGBoost training.
        Falls back to synthetic dataset if DB is empty or unavailable.
        """
        # Try SQLAlchemy first (faster for large datasets)
        if _SessionLocal:
            try:
                return self._load_from_db()
            except Exception as exc:
                logger.warning(f"DB load failed ({exc}), falling back to synthetic data.")

        # Try Supabase client directly
        try:
            return self._load_from_supabase()
        except Exception as exc:
            logger.warning(f"Supabase load failed ({exc}), using synthetic data.")

        # Final fallback: generate synthetic dataset
        return _generate_synthetic_training_dataset()

    def _load_from_db(self) -> pd.DataFrame:
        """Load training data via SQLAlchemy."""
        session = _SessionLocal()
        try:
            logger.info("Fetching training dataset from price_history (SQLAlchemy)...")
            result = session.execute(
                text("""
                    SELECT *
                    FROM price_history
                    WHERE price IS NOT NULL
                      AND price >= 800
                      AND price <= 60000
                    ORDER BY recorded_at ASC
                    LIMIT 100000
                """)
            )
            rows = result.fetchall()

            if not rows or len(rows) < 50:
                logger.warning(f"Only {len(rows) if rows else 0} rows in DB — using synthetic fallback.")
                return _generate_synthetic_training_dataset()

            columns = list(result.keys())
            df = pd.DataFrame(rows, columns=columns)
            return self._engineer_features(df)
        finally:
            session.close()

    def _load_from_supabase(self) -> pd.DataFrame:
        """Load training data via Supabase client."""
        logger.info("Fetching training dataset from price_history (Supabase)...")
        res = (
            self.supabase.table("price_history")
            .select("*")
            .gte("price", 800)
            .lte("price", 60000)
            .limit(50000)
            .execute()
        )
        rows = res.data or []

        if len(rows) < 50:
            logger.warning(f"Only {len(rows)} rows in Supabase — using synthetic fallback.")
            return _generate_synthetic_training_dataset()

        df = pd.DataFrame(rows)
        return self._engineer_features(df)

    def _engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply feature engineering to raw price_history data."""
        # TYPE FIX: Ensure price is float (handles Python Decimal from Postgres)
        if "price" in df.columns:
            df["price"] = pd.to_numeric(df["price"], errors="coerce").astype(float)

        # Date handling
        if "departure_date" in df.columns:
            df["departure_date"] = pd.to_datetime(df["departure_date"], errors="coerce")
            today = pd.Timestamp.now().normalize()
            df["days_until_dep"] = (df["departure_date"] - today).dt.days.clip(lower=0).fillna(7)
        else:
            df["days_until_dep"] = 7

        df["urgency"] = 1 / (df["days_until_dep"] + 1)

        # is_live: map True→2.0, False→1.0 for weighted training
        if "is_live" in df.columns:
            df["is_live"] = (
                df["is_live"].fillna(False)
                .map({True: 2.0, False: 1.0, 2.0: 2.0, 1.0: 1.0})
                .astype(float)
            )
        else:
            df["is_live"] = 1.0

        # Sort for time-series lag features
        if "recorded_at" in df.columns:
            df["recorded_at"] = pd.to_datetime(df["recorded_at"], errors="coerce")
            df = df.sort_values("recorded_at")

        # Categorical cleaning
        for col in ("origin_code", "destination_code", "airline_code"):
            if col in df.columns:
                df[col] = df[col].astype(str).str.upper().str.strip()

        # Numeric defaults
        numeric_defaults = {
            "day_of_week": 0, "month": 1, "week_of_year": 1,
            "hour_of_day": 12, "is_peak_hour": 0, "seats_available": 50,
            "price_change_1d": 0, "price_change_3d": 0,
            "demand_score": 0.5, "seasonality_factor": 1.0,
        }
        for col, val in numeric_defaults.items():
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(val)
            else:
                df[col] = val

        df = df.fillna(0)
        df = df[(df["price"] >= 800) & (df["price"] <= 60000)]

        logger.info(f"Training dataset ready: {len(df)} rows.")
        return df

    # ── Active price alerts ─────────────────────────────────────────
    def get_active_alerts(self) -> list:
        try:
            res = (
                self.supabase.table("price_alerts")
                .select("*, profiles(email, phone, full_name, notify_email, notify_sms, notify_whatsapp)")
                .eq("is_active", True)
                .execute()
            )
            return res.data or []
        except Exception as exc:
            logger.error(f"get_active_alerts error: {exc}")
            return []

    # ── Flight search from DB cache ─────────────────────────────────
    def search_flights(
        self, origin: str, destination: str, departure_date: str
    ) -> list:
        """Query cached flights from Supabase (if table exists)."""
        try:
            res = (
                self.supabase.table("flights")
                .select("*")
                .eq("origin_code", origin)
                .eq("destination_code", destination)
                .gte("departure_time", f"{departure_date}T00:00:00")
                .lte("departure_time", f"{departure_date}T23:59:59")
                .eq("status", "SCHEDULED")
                .limit(20)
                .execute()
            )
            return res.data or []
        except Exception:
            return []

    # ── Supabase Storage (Model Persistence) ────────────────────────
    def upload_model(self, local_path: str, remote_name: str = "global_model.pkl") -> bool:
        """Upload a trained model to Supabase Storage."""
        try:
            with open(local_path, "rb") as f:
                content = f.read()
            
            # Upsert = True to overwrite existing model
            res = self.supabase.storage.from_("models").upload(
                path=remote_name,
                file=content,
                file_options={"content-type": "application/octet-stream", "x-upsert": "true"}
            )
            logger.info(f"Model uploaded to Supabase Storage: {remote_name}")
            return True
        except Exception as exc:
            logger.error(f"Model upload failed: {exc}")
            return False

    def download_model(self, local_path: str, remote_name: str = "global_model.pkl") -> bool:
        """Download the latest model from Supabase Storage."""
        try:
            res = self.supabase.storage.from_("models").download(remote_name)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, "wb") as f:
                f.write(res)
            logger.info(f"Model downloaded from Supabase Storage: {remote_name}")
            return True
        except Exception as exc:
            logger.debug(f"Model download failed (this is expected on first run): {exc}")
            return False


# ── Singleton ─────────────────────────────────────────────────────────
database = Database()
