"""
SkyMind — Database Layer
Wraps Supabase client and SQLAlchemy for ML training data retrieval.
"""

import os
import logging
from datetime import datetime

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

if not _SUPABASE_URL or not _SUPABASE_KEY:
    raise RuntimeError(
        "❌ Missing Supabase credentials (SUPABASE_URL / SUPABASE_SERVICE_KEY)"
    )

_supabase_client = create_client(_SUPABASE_URL, _SUPABASE_KEY)

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
        logger.info("✅ SQLAlchemy engine initialised.")
    except Exception as exc:
        logger.warning(f"SQLAlchemy init failed (non-fatal): {exc}")


# ══════════════════════════════════════════════════════════════════════
# Database class
# ══════════════════════════════════════════════════════════════════════

class Database:
    def __init__(self):
        self.supabase = _supabase_client

    # ── ML training dataset ─────────────────────────────────────────
    def get_training_dataset(self) -> pd.DataFrame:
        """
        Fetch price_history rows and engineer features for XGBoost training.
        Ensures 'is_live' and price changes are correctly formatted for 2026 logic.
        """
        if not _SessionLocal:
            raise RuntimeError("DATABASE_URL not configured — cannot load training data")

        session = _SessionLocal()
        try:
            logger.info("🚀 Fetching training dataset from price_history...")

            # Select all columns to ensure we don't miss new 2026 features
            result = session.execute(
                text("""
                    SELECT *
                    FROM price_history
                    WHERE price IS NOT NULL
                      AND price >= 800
                      AND price <= 60000
                    ORDER BY recorded_at DESC
                    LIMIT 100000
                """)
            )
            rows = result.fetchall()
            if not rows:
                raise RuntimeError("No training data found in price_history")

            columns = list(result.keys())
            df = pd.DataFrame(rows, columns=columns)
            
            # ── TYPE FIX (CRITICAL) ──────────────────────────────────
            # Fixes the 'unsupported operand type(s) for -: Decimal and float'
            if "price" in df.columns:
                df["price"] = pd.to_numeric(df["price"], errors='coerce').astype(float)
            # ─────────────────────────────────────────────────────────

            # ── Feature engineering ──────────────────────────────────
            
            # 1. Date Handling
            if "departure_date" in df.columns:
                df["departure_date"] = pd.to_datetime(df["departure_date"], errors="coerce")
                today = pd.Timestamp.now().normalize()
                df["days_until_dep"] = (df["departure_date"] - today).dt.days.clip(lower=0).fillna(7)
            else:
                df["days_until_dep"] = 7

            # 2. Urgency Feature (1 / (days + 1)) - Matches PricePredictor exactly
            df["urgency"] = 1 / (df["days_until_dep"] + 1)

            # 3. Handle 'is_live' for Weighted Training (REQUIRED 2026 UPDATE)
            # Maps boolean True to 2.0 and False to 1.0 to match router priority logic
            if "is_live" in df.columns:
                df["is_live"] = df["is_live"].fillna(False).map({True: 2.0, False: 1.0}).astype(float)
            else:
                df["is_live"] = 1.0

            # 4. Categorical Cleaning
            for col in ("origin_code", "destination_code", "airline_code"):
                if col in df.columns:
                    df[col] = df[col].astype(str).str.upper().str.strip()

            # 5. Numeric defaults & safety
            numeric_defaults = {
                "day_of_week": 0, "month": 1, "week_of_year": 1,
                "hour_of_day": 12, "is_peak_hour": 0, "seats_available": 30,
                "price_change_1d": 0, "price_change_3d": 0,
                "demand_score": 0.5, "seasonality_factor": 1.0,
            }
            
            for col, val in numeric_defaults.items():
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(val)
                else:
                    df[col] = val

            # Filter for final quality
            df = df[(df["price"] >= 800) & (df["price"] <= 60000)]
            
            logger.info(f"✅ Training dataset ready: {len(df)} rows.")
            return df

        finally:
            session.close()

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


# ── Singleton ─────────────────────────────────────────────────────────
database = Database()