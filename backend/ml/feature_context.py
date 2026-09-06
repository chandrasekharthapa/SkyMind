from dataclasses import dataclass
from datetime import datetime
from typing import Union, Optional, Any
import pandas as pd

@dataclass(frozen=True)
class FeatureContext:
    historical_data: Union[list, pd.DataFrame]
    market_snapshot: Optional[Union[dict, Any]]
    prediction_context: dict
    route_statistics: dict
    airline_statistics: dict
    booking_statistics: dict
    current_timestamp: datetime
