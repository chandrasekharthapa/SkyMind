"""Forecast Store Service.

Persists published forecasts as immutable `PENDING` rows for delayed evaluation,
and reads back the ones whose outcome is now known.

`load_resolved_forecasts` is new. The store had only `save_forecast`, so the
outcomes `forecast_evaluation_scheduler` writes — the project's only out-of-sample
error figures measured against realised fares — could be written but never read.
Nothing could report served-model accuracy because nothing could load it.
"""

import logging
from typing import Any, Dict, List, Optional

from backend.database.database import database as db

logger = logging.getLogger(__name__)

STATUS_PENDING = "PENDING"
STATUS_COMPLETED = "COMPLETED"

# Columns a resolved forecast must carry to be scorable. `forecast_evaluator`
# requires the first two; the rest are provenance a reader needs to check a figure.
RESOLVED_COLUMNS = (
    "forecast_id", "forecast_timestamp", "prediction_horizon", "forecast_price",
    "actual_price", "model_version", "dataset_version", "evaluated_at",
    "evaluation_metrics", "recommendation",
)

# One read returns at most this many rows. An accuracy report over the most recent
# N resolved forecasts is a bounded query; `select("*")` with no limit is how a
# growing table turns a report into a timeout.
DEFAULT_LIMIT = 1000


class ForecastStore:
    def __init__(self, database=None):
        # Injectable so the read path can be exercised without Supabase.
        self._db = database if database is not None else db

    def save_forecast(
        self,
        forecast_id: str,
        prediction_timestamp: str,
        horizon: int,
        predicted_price: float,
        model_version: str,
        dataset_version: str,
        recommendation: Dict[str, Any]
    ) -> None:
        """Saves a generated forecast model prediction into the forecast_store database."""
        payload = {
            "forecast_id": forecast_id,
            "forecast_timestamp": prediction_timestamp,
            "prediction_horizon": horizon,
            "forecast_price": float(predicted_price),
            "model_version": model_version,
            "dataset_version": dataset_version,
            "recommendation": recommendation,
            "status": STATUS_PENDING,
        }

        try:
            self._db.supabase.table("forecast_store").insert(payload).execute()
            logger.info(f"[ForecastStore] Forecast saved successfully: {forecast_id} (Horizon: {horizon}d)")
        except Exception as e:
            logger.error(f"[ForecastStore] Failed to write forecast entry: {e}")
            raise e

    def load_resolved_forecasts(
        self,
        horizon: Optional[int] = None,
        since: Optional[str] = None,
        limit: int = DEFAULT_LIMIT,
    ) -> List[Dict[str, Any]]:
        """Forecasts whose realised fare is recorded, most recently evaluated first.

        Only `COMPLETED` rows are returned. `UNEVALUABLE` rows carry no
        `actual_price` — they are retired forecasts, not measurements — and
        including them would put a null actual into every error figure.

        Args:
            horizon: restrict to one `prediction_horizon`, in days. Mixing horizons
                in one error figure averages a 1-day forecast with a 7-day one,
                which are different tasks with different achievable errors.
            since: ISO timestamp; only forecasts evaluated at or after it.
            limit: maximum rows.

        Returns:
            A list of row dicts. Empty when nothing has been resolved yet — which
            is a real state, not an error, and a caller must report it as "no
            measurement" rather than as a clean result.
        """
        try:
            query = (
                self._db.supabase.table("forecast_store")
                .select(",".join(RESOLVED_COLUMNS))
                .eq("status", STATUS_COMPLETED)
            )
            if horizon is not None:
                query = query.eq("prediction_horizon", int(horizon))
            if since:
                query = query.gte("evaluated_at", since)
            rows = (query.order("evaluated_at", desc=True).limit(int(limit)).execute()).data or []
        except Exception as exc:
            # Raised, not swallowed into an empty list. An empty list means "nothing
            # resolved yet" and a caller is entitled to treat it as such; a
            # transport failure returning the same value would make a broken
            # connection indistinguishable from a young corpus.
            logger.error("[ForecastStore] Failed to read resolved forecasts: %s", exc)
            raise

        # A COMPLETED row without an `actual_price` should not exist — the scheduler
        # writes the two together — but a row that slipped through would put a null
        # actual into every error figure, so it is dropped here and counted rather
        # than filtered in the query, where the null predicate is a PostgREST
        # spelling this code cannot verify against the deployed client version.
        resolved = [r for r in rows if r.get("actual_price") is not None]
        dropped = len(rows) - len(resolved)
        if dropped:
            logger.warning(
                "[ForecastStore] %d of %d COMPLETED forecast(s) carry no actual_price "
                "and were excluded; a resolved forecast without a realised fare is a "
                "scheduler bug.", dropped, len(rows))

        logger.info("[ForecastStore] Loaded %d resolved forecast(s)%s.", len(resolved),
                    f" for horizon {horizon}d" if horizon is not None else "")
        return resolved


forecast_store = ForecastStore()
