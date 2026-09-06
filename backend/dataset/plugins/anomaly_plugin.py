"""Price Anomaly & Outlier Validation Plugin."""

from typing import Tuple, List
import pandas as pd
from backend.dataset.plugins.base import BaseValidationPlugin, ValidationPluginResult


class AnomalyValidationPlugin(BaseValidationPlugin):
    name = "anomaly_validation"

    def validate(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, ValidationPluginResult]:
        if df.empty or "price" not in df.columns:
            return df, ValidationPluginResult(plugin_name=self.name, passed=True)

        errors: List[str] = []

        # 1. Non-positive price rejection
        valid_price = (df["price"] > 0) & (df["price"] <= 500000.0)
        rejected_cnt = int((~valid_price).sum())
        cleaned_df = df[valid_price].copy()

        if rejected_cnt > 0:
            errors.append(f"Rejected {rejected_cnt} rows with non-positive or extreme outlier prices.")

        return cleaned_df, ValidationPluginResult(
            plugin_name=self.name,
            passed=rejected_cnt == 0,
            rejected_rows_count=rejected_cnt,
            errors=errors,
            details={"outlier_prices_rejected": rejected_cnt}
        )
