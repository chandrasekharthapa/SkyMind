"""Canonical Forecast Service Singleton Entry Point."""

from typing import List, Dict, Any, Optional
from backend.domain.canonical_forecast import CanonicalForecastDomain
from backend.services.forecast.assembler import ForecastAssembler


class CanonicalForecastService:
    """High-level service providing reconciled canonical forecasts."""

    def __init__(self, assembler: Optional[ForecastAssembler] = None):
        self.assembler = assembler or ForecastAssembler()

    def build_canonical_forecast(
        self,
        formatted_forecast: List[Dict[str, Any]],
        current_fare: Optional[float],
        model_accuracy: Optional[float],
        snapshot_quality: Optional[float],
        is_live_market: bool
    ) -> CanonicalForecastDomain:
        """Constructs a mathematically reconciled CanonicalForecastDomain.

        `model_accuracy` and `snapshot_quality` are required and may be None; they
        used to default to 95.0 and 1.0, which meant any caller that omitted them
        published the maximum score the pipeline can produce. `is_live_market` is
        passed in rather than re-derived downstream so that one observation of the
        market decides it.
        """
        return self.assembler.assemble(
            formatted_forecast=formatted_forecast,
            current_fare=current_fare,
            model_accuracy=model_accuracy,
            snapshot_quality=snapshot_quality,
            is_live_market=is_live_market
        )


canonical_forecast_service = CanonicalForecastService()
