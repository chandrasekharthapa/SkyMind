"""CLI Dashboard to run and render Booking Curve validation results."""

import os
import sys
import json
from datetime import datetime, timezone

# The repository root, so `import backend.<...>` below resolves when this file is
# run directly. It used to append `dirname(dirname(__file__))`, which from
# `backend/scratch/` was `backend/` — one level short of where the `backend`
# package is importable from. The imports worked anyway, but only because the
# process happened to be launched from the repository root; run it from anywhere
# else and it died on line 11.
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.database.database import database as db
from backend.services.training_dataset_builder import training_dataset_builder
from backend.services.model_registry import model_registry
from backend.ml.booking_curve_validator import generate_validation_report

def get_status_str(status: str) -> str:
    # Use simple ANSI colors if terminal supports it
    if status == "PASS":
        return "\033[92mPASS\033[0m"
    elif status == "WARNING":
        return "\033[93mWARNING\033[0m"
    else:
        return "\033[91mFAIL\033[0m"

def main():
    print("=========================================")
    print("Initializing Booking Curve Pipeline...")
    print("=========================================")
    
    # Check if DB has data
    df_raw = db.get_training_dataset()
    if df_raw.empty:
        print("\033[91mError: Database training dataset is empty!\033[0m")
        return
        
    print(f"Loaded {len(df_raw)} raw rows from database.")
    
    # 1. Run Feature Engineering & Target join (horizon=3)
    print("Running feature engineering pipeline and target join...")
    df_raw_cleaned, df_features = training_dataset_builder.build(horizon=3)
    
    # Determine feature set version
    fs_version = model_registry.feature_set_version
    from unittest.mock import MagicMock
    if isinstance(fs_version, MagicMock):
        expected_cols = getattr(model_registry, "expected_features", [])
        if isinstance(expected_cols, MagicMock):
            expected_cols = []
        fs_version = "legacy" if len(expected_cols) <= 16 else "feature_set_v1"
        
    # 2. Run validator
    print("Generating validation report...")
    report = generate_validation_report(df_raw, df_raw_cleaned, df_features, fs_version)
    
    # 3. Render Dashboard
    print("\n========================================")
    print("       BOOKING CURVE VALIDATION         ")
    print(f"Chronology ........ {get_status_str(report.chronology.status)}")
    print(f"Duplicates ........ {get_status_str(report.duplicates.status)}")
    print(f"Leakage ........... {get_status_str(report.leakage.status)}")
    print(f"Feature Coverage .. {get_status_str(report.coverage.status)}")
    print(f"Booking Curves .... {get_status_str(report.health.status)}")
    print(f"Target Quality .... {get_status_str(report.target_quality.status)}")
    print(f"Feature Drift ..... {get_status_str(report.drift.status)}")
    print("----------------------------------------")
    print(f"Model Readiness .... {report.readiness_score}%")
    print("========================================\n")
    
    # Show warning/error summaries if present
    all_warnings = (report.chronology.warnings + report.duplicates.warnings + 
                    report.leakage.warnings + report.health.warnings + 
                    report.coverage.warnings + report.target_quality.warnings + 
                    report.drift.warnings)
                    
    all_errors = (report.chronology.errors + report.duplicates.errors + 
                  report.leakage.errors + report.health.errors + 
                  report.coverage.errors + report.target_quality.errors + 
                  report.drift.errors)
                  
    from backend.services.dataset_quality_validator import dataset_quality_validator
    quality_report = dataset_quality_validator.validate(df_raw, df_features)

    print("\n==========================================================================")
    print("                      DATASET HEALTH & TEMPORAL METRICS                   ")
    print("==========================================================================")
    print(f"Total Observations ........ {quality_report.observation_count}")
    print(f"Real Observations ......... {quality_report.real_count}")
    print(f"Synthetic Observations .... {quality_report.synthetic_count}")
    print(f"Route Coverage ............ {quality_report.route_coverage}")
    print(f"Airport Coverage .......... {quality_report.airport_coverage}")
    print(f"Airline Coverage .......... {quality_report.airline_coverage}")
    print(f"Avg Booking Curve Length .. {quality_report.booking_curve_length}")
    print(f"Temporal Coverage Days .... {quality_report.temporal_coverage_days}d")
    print(f"Duplicate Rate ............ {quality_report.duplicate_rate:.2f}%")
    print("==========================================================================\n")

    print("==========================================================================")
    print("                   TRAINING READINESS DASHBOARD                           ")
    print("==========================================================================")
    print(f"{'Horizon':<10} | {'Grade':<6} | {'Ready':<6} | {'Shifted Pairs':<14} | {'Reason'}")
    print("--------------------------------------------------------------------------")
    for key, readiness in quality_report.horizon_readiness.items():
        ready_str = "\033[92mYes\033[0m" if readiness.ready else "\033[91mNo\033[0m"
        print(f"{key:<10} | {readiness.grade:<6} | {ready_str:<15} | {readiness.shifted_count:<14} | {readiness.reason}")
    print("==========================================================================\n")

    if all_warnings:
        print("Warnings Summary:")
        for w in all_warnings:
            print(f" - \033[93m{w}\033[0m")
            
    if all_errors:
        print("\nErrors Summary:")
        for e in all_errors:
            print(f" - \033[91m{e}\033[0m")
            
    # Print where the report actually went, read from the module that wrote it,
    # rather than restating a relative path this script cannot verify.
    from backend.ml.booking_curve_validator import DEFAULT_HISTORY_DIR
    print(f"\nReport exported to {DEFAULT_HISTORY_DIR}")

if __name__ == "__main__":
    main()
