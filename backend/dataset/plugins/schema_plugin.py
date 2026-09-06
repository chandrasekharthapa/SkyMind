"""Schema & Mandatory Field Validation Plugin."""

from typing import Tuple, List
import pandas as pd
from backend.dataset.plugins.base import BaseValidationPlugin, ValidationPluginResult
from backend.dataset.schema import MANDATORY_RAW_COLUMNS, PROHIBITED_EMPTY_COLUMNS


class SchemaValidationPlugin(BaseValidationPlugin):
    name = "schema_validation"

    def validate(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, ValidationPluginResult]:
        errors: List[str] = []
        if df.empty:
            return df, ValidationPluginResult(plugin_name=self.name, passed=True)

        # 1. Check mandatory columns
        for col in MANDATORY_RAW_COLUMNS:
            if col not in df.columns:
                errors.append(f"Missing mandatory column: '{col}'")

        if errors:
            return df, ValidationPluginResult(plugin_name=self.name, passed=False, errors=errors)

        # 2. Reject rows with NaN in mandatory columns
        valid_mask = df[MANDATORY_RAW_COLUMNS].notna().all(axis=1)
        rejected_cnt = int((~valid_mask).sum())
        cleaned_df = df[valid_mask].copy()

        # 3. Check for prohibited empty columns
        for p_col in PROHIBITED_EMPTY_COLUMNS:
            if p_col in cleaned_df.columns and cleaned_df[p_col].isna().all():
                errors.append(f"Column '{p_col}' is permanently empty and prohibited.")

        passed = len(errors) == 0 and rejected_cnt == 0
        return cleaned_df, ValidationPluginResult(
            plugin_name=self.name,
            passed=passed,
            rejected_rows_count=rejected_cnt,
            errors=errors,
            details={"mandatory_columns_checked": MANDATORY_RAW_COLUMNS}
        )
