"""
SkyMind — Database Layer
Wraps Supabase client and SQLAlchemy for ML training data retrieval.
Strictly returns live data with no synthetic fallbacks.
"""

import os
import logging

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.domain.provenance import (
    LIVE_KEY,
    MAX_PLAUSIBLE_FARE,
    MIN_PLAUSIBLE_FARE,
    PROVENANCE_IS_FILTERS,
    PROVENANCE_SQL,
    decode_flag,
)

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


# Synthetic training dataset generation removed (purged post-2025 refactoring)


# ══════════════════════════════════════════════════════════════════════
# Database class
# ══════════════════════════════════════════════════════════════════════

class Database:
    def __init__(self):
        self.supabase = _supabase_service
        self.anon = _supabase_anon
        # True when the last get_training_dataset() call returned an empty frame
        # because *reading* failed, rather than because the table is empty. The
        # two are not the same thing and callers were unable to tell them apart.
        self.last_load_failed: bool = False

    # ── ML training dataset ─────────────────────────────────────────
    #
    # Provenance filter. `is_synthetic` alone is not trustworthy, and the reason
    # is recorded here because it is not visible from this file: the script
    # `alter_price_history_provenance.py` added the column with
    # `ADD COLUMN IF NOT EXISTS is_synthetic BOOLEAN DEFAULT FALSE`, which makes
    # every pre-existing row read back FALSE, and added `data_source` with
    # `DEFAULT 'GOOGLE_FLIGHTS'` the same way. Its corrective backfill then ran
    # `UPDATE ... WHERE (is_live IS NOT TRUE) AND (data_source IS NULL OR
    # is_synthetic IS NULL)` — but the two ADD COLUMN defaults had already
    # removed every NULL, so that UPDATE matched zero rows. Net effect: the
    # seeded block is labelled `is_synthetic = FALSE, data_source =
    # 'GOOGLE_FLIGHTS'`, and the old predicate here
    # (`is_synthetic IS NULL OR is_synthetic = FALSE`) admitted all of it.
    #
    # So filter on two independent conditions instead of one label:
    #   * `is_synthetic IS FALSE`  — excludes NULL as well as TRUE (fail closed).
    #   * `is_live IS TRUE`        — the seeded rows all carry is_live = FALSE,
    #                                which is set from observed data at ingest
    #                                time rather than by a later migration.
    # Either one alone would be enough today; requiring both means a single
    # mislabelling cannot re-admit fabricated rows into training.
    #
    # The predicate itself lives in `backend/domain/provenance.py`. It was
    # written out by hand here, again as a `.is_()` chain in
    # `_load_from_supabase`, again in `forecast_evaluation_scheduler`, and a
    # fourth site — `services.training_eligibility` — applied neither condition
    # while claiming to have replaced them.
    #
    # `alter_price_history_provenance.py` was one of the fifty files under
    # `backend/scratch/`, all of which were tracked and have since been archived
    # to `.archive/backend-scratch-2026-09-02.tar.gz` and removed. The DDL
    # it applied by hand is now in `backend/database/migrations/`; the paragraph
    # above is kept because the *shape* of what it did to existing rows is the
    # reason this predicate needs two conditions, and that is not recoverable from
    # the schema.
    _PROVENANCE_SQL = PROVENANCE_SQL

    def get_training_dataset(self) -> pd.DataFrame:
        """
        Fetch price_history rows for XGBoost training.

        Returns live, non-synthetic observations only. An empty frame means one
        of two things — check `self.last_load_failed` to tell which.
        """
        self.last_load_failed = False

        # Try SQLAlchemy first (faster for large datasets)
        if _SessionLocal:
            try:
                return self._load_from_db()
            except Exception as exc:
                # Was logger.warning. This is the primary loader; if it fails
                # because `is_synthetic` does not exist on this database, the
                # Supabase path below fails for the same reason and the caller
                # silently receives an empty frame. Not a warning.
                logger.error(f"SQLAlchemy training load failed, falling back to Supabase: {exc}")

        # Try Supabase client directly
        try:
            return self._load_from_supabase()
        except Exception as exc:
            logger.error(f"Supabase training load failed: {exc}")
            self.last_load_failed = True
            return pd.DataFrame()

    def _load_from_db(self) -> pd.DataFrame:
        """Load training data via SQLAlchemy."""
        session = _SessionLocal()
        try:
            logger.info("Fetching training dataset from price_history (SQLAlchemy)...")
            result = session.execute(
                text(f"""
                    SELECT *
                    FROM price_history
                    WHERE price IS NOT NULL
                      AND price >= {MIN_PLAUSIBLE_FARE}
                      AND price <= {MAX_PLAUSIBLE_FARE}
                      AND {self._PROVENANCE_SQL}
                    ORDER BY recorded_at ASC
                    LIMIT 100000
                """)
            )
            rows = result.fetchall()

            if not rows:
                logger.warning("No eligible rows found in DB.")
                return pd.DataFrame()

            columns = list(result.keys())
            df = pd.DataFrame(rows, columns=columns)
            logger.info(f"Loaded {len(df)} live non-synthetic rows for training.")
            return self._engineer_features(df)
        finally:
            session.close()

    def _load_from_supabase(self) -> pd.DataFrame:
        """Load training data via Supabase client.

        The predicate must match `_PROVENANCE_SQL` exactly. It previously did
        not: this path used `.neq("is_synthetic", True)`, which PostgREST turns
        into `is_synthetic <> true` — and `NULL <> true` is NULL, so a row with
        an unknown label was *excluded* here while the SQLAlchemy path's
        `is_synthetic IS NULL OR is_synthetic = FALSE` *included* it. The two
        loaders disagreed about the same row, and which one ran depended on
        whether DATABASE_URL happened to be set.

        Both conditions and both fare bounds now come from the same module the
        SQL predicate is built from, so "must match" is no longer something a
        reader has to check by eye across two hundred lines.
        """
        logger.info("Fetching training dataset from price_history (Supabase)...")
        query = self.supabase.table("price_history").select("*")
        for column, value in PROVENANCE_IS_FILTERS:
            query = query.is_(column, value)
        res = (
            query
            .gte("price", MIN_PLAUSIBLE_FARE)
            .lte("price", MAX_PLAUSIBLE_FARE)
            .limit(50000)
            .execute()
        )
        rows = res.data or []

        if not rows:
            logger.warning("No live rows found in Supabase.")
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        logger.info(f"Loaded {len(df)} live non-synthetic rows for training.")
        return self._engineer_features(df)

    def _engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply feature engineering to raw price_history data.
        
        Derives all features deterministically or keeps them as np.nan.
        No synthetic default values are allowed.
        """
        import numpy as np

        if df is None or df.empty:
            return pd.DataFrame()

        # TYPE FIX: Ensure price is float (handles Python Decimal from Postgres)
        if "price" in df.columns:
            df["price"] = pd.to_numeric(df["price"], errors="coerce").astype(float)

        # Observation timestamp, parsed first because the booking horizon below
        # is measured from it. UTC-normalised so it can be subtracted from
        # departure_date without a tz-aware/tz-naive mismatch.
        #
        # `format="ISO8601"` because otherwise pandas infers one format from the
        # first non-null value and coerces everything that does not match it to
        # NaT. Supabase returns `timestamptz` with microseconds, Python's
        # `datetime.isoformat()` omits that field when it is zero, and this column
        # holds rows from both — so the inferred format silently discarded the
        # other shape's observation time, and a NaT here drops the row from the
        # sort below and from every horizon computed from it. See
        # `booking_curve_definition.ordering_timestamps` for the full note.
        if "recorded_at" in df.columns:
            df["recorded_at"] = pd.to_datetime(
                df["recorded_at"], errors="coerce", utc=True, format="ISO8601")
            df = df.sort_values("recorded_at")

        # Date handling - deterministically derived
        if "departure_date" in df.columns:
            df["departure_date"] = pd.to_datetime(
                df["departure_date"], errors="coerce", utc=True, format="ISO8601")

            # Booking horizon. This was `(departure_date - Timestamp.now()).clip(lower=0)`,
            # which is the horizon as of *training time*, not as of the observation.
            # Every historical row departed before today, so every one clipped to 0
            # and `urgency` below became the constant 1.0 — while inference passes a
            # real horizon computed as (departure_date - today) at request time.
            # Two headline features were constants in training and live at serving:
            # a train/serve skew, not a missing feature. Measure from recorded_at,
            # which is what the observation actually saw.
            if "recorded_at" in df.columns:
                horizon = (df["departure_date"] - df["recorded_at"]).dt.days
                # A negative horizon means the row was recorded after departure —
                # a provenance defect. Clipping it to 0 relabels it as "departing
                # today", which is how the old code turned bad rows into a
                # plausible-looking constant. Drop the value instead; XGBoost
                # handles NaN natively and the count is logged below.
                invalid = int((horizon < 0).sum())
                if invalid:
                    logger.warning(
                        f"{invalid} row(s) have departure_date earlier than recorded_at; "
                        "booking horizon left undefined for those rows."
                    )
                df["days_until_dep"] = horizon.where(horizon >= 0)
            else:
                # No observation timestamp means the horizon is unknowable. Do not
                # substitute the current date.
                logger.warning("recorded_at absent; days_until_dep and urgency left undefined.")
                df["days_until_dep"] = np.nan

            df["day_of_week"] = df["departure_date"].dt.weekday
            df["month"] = df["departure_date"].dt.month
            df["week_of_year"] = df["departure_date"].dt.isocalendar().week
        else:
            df["days_until_dep"] = np.nan
            df["day_of_week"] = np.nan
            df["month"] = np.nan
            df["week_of_year"] = np.nan

        # Urgency - derived
        df["urgency"] = 1 / (df["days_until_dep"] + 1)

        if df["days_until_dep"].notna().any():
            logger.info(
                f"Booking horizon: {int(df['days_until_dep'].min())}–"
                f"{int(df['days_until_dep'].max())} days, "
                f"{df['days_until_dep'].nunique()} distinct value(s)."
            )

        # `is_live` stays a boolean.
        #
        # This was `df["is_live"].fillna(False).map({True: 2.0, False: 1.0,
        # 2.0: 2.0, 1.0: 1.0}).astype(float)`, commented "map True→2.0,
        # False→1.0 for weighted training". Three things were wrong with it.
        #
        # The dict does not contain the entries it appears to. In Python
        # `1.0 == True` and the two hash equal, so `{True: 2.0, ..., 1.0: 1.0}`
        # keeps only the last of the pair: the literal is really
        # `{True: 1.0, False: 1.0, 2.0: 2.0}`. A Postgres BOOLEAN column arrives
        # as bools, so *every* row mapped to 1.0 — the not-live encoding — and
        # the True/False distinction this line exists to preserve was destroyed
        # at load time. The decoder in `price_model` collapsed the same way in
        # the opposite direction (`{2.0: True, 1.0: True, False: False}`), so
        # 1.0 came back as True and the round trip only looked correct because
        # two collisions cancelled.
        #
        # It is not what weights the training either. XGBoost's sample weights
        # come from the separate `training_weight` column (`model_trainer.py`
        # reads it); `is_live` is a *feature*, listed in `price_model.feature_cols`.
        #
        # And re-encoding a boolean as 1.0/2.0 made 1.0 mean the opposite of what
        # it means everywhere else, which is what let the collapse go unnoticed.
        #
        # After the provenance filter above, every row here is live by
        # construction, so this column is constant True in training — the same
        # value the serving path sends. That is worth being able to see; the old
        # encoding hid it. A value `decode_flag` cannot read, or a frame with no
        # such column, is recorded as not live: one rule, fail-closed, matching
        # `has_authentic_provenance`. Neither case can arise from the loaders
        # above, whose predicate requires the column and requires it TRUE.
        if LIVE_KEY in df.columns:
            df[LIVE_KEY] = df[LIVE_KEY].map(decode_flag).eq(True)
        else:
            df[LIVE_KEY] = False

        # hour_of_day / is_peak_hour — the hour the flight DEPARTS, which is the
        # quantity the serving path sends under this name
        # (flight_search_service.py parses it from the segment departure
        # timestamp). This block used to compute it from `recorded_at`: the hour
        # the price was *observed*. That is not a skew in scale, it is a different
        # variable — and because the collector runs on a schedule, the observed
        # hour is close to constant across the corpus, so the model saw a nearly
        # useless column in training and a real departure hour in production. The
        # peak-hour buckets (7-10, 17-20) are Indian clock hours, which is why the
        # old code had to tz_convert; a departure timestamp is already local.
        #
        # `departure_time` is captured at ingest and added by migration 001. Rows
        # written before it stay NaN — XGBoost handles NaN natively, and NaN is
        # the honest value for an unknown departure hour.
        if "departure_time" in df.columns:
            dep_ts = pd.to_datetime(df["departure_time"], errors="coerce", utc=False)
            df["hour_of_day"] = dep_ts.dt.hour.astype("float64")
            df["is_peak_hour"] = (
                df["hour_of_day"].isin([7, 8, 9, 10, 17, 18, 19, 20])
                .astype("float64")
                .where(df["hour_of_day"].notna())
            )
        else:
            df["hour_of_day"] = np.nan
            df["is_peak_hour"] = np.nan

        # Categorical cleaning
        for col in ("origin_code", "destination_code", "airline_code"):
            if col in df.columns:
                df[col] = df[col].astype(str).str.upper().str.strip()

        # `price_change_1d` / `price_change_3d` are NOT computed here.
        #
        # This block used to compute them as
        # `groupby(["origin_code", "destination_code"])["price"].shift(1)` and
        # `.shift(3)`, which is wrong twice over: a positional shift is n
        # *observations* back rather than n days, and grouping on two keys pooled
        # every airline, flight and departure date on the route into one price
        # history, so "the previous observation" was routinely a different
        # flight. `backend/ml/features/booking_curve.py` owns these two names and
        # computes them as as-of day-based lags on the full five-part booking
        # curve key; `feature_engineering_pipeline.build_training_dataset` gives
        # the generator's output precedence over a same-named raw column, so
        # these values never reached a model — they were a second definition
        # waiting for a caller to read the frame directly.
        #
        # The companion `price_lag_1` / `price_lag_3` columns are gone with them;
        # nothing in the repository read either name.

        # Clean/filter target variable
        df = df[df["price"].notna()]
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
        except Exception as exc:
            # An empty list is indistinguishable from "no flights scheduled",
            # so a swallowed error here reads to every caller as a successful
            # search that found nothing. Log it, as the sibling queries do.
            logger.error(f"search_flights({origin}->{destination}, {departure_date}) error: {exc}")
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
