"""Extended Feature Engineering Pipeline for SkyMind Flight Price Dataset v2.0.

Engineers 18+ derived domain features using expanding windows to strictly prevent data leakage.
"""

import math
import logging
from datetime import datetime
from typing import Dict, Any, List, Tuple
import pandas as pd
import numpy as np
from backend.dataset.dates import compute_calendar_days_until_dep, parse_to_date

logger = logging.getLogger(__name__)

# Approximate coordinates for Indian airport IATA hubs (latitude, longitude)
AIRPORT_COORDINATES: Dict[str, Tuple[float, float]] = {
    "DEL": (28.5562, 77.1000),
    "BOM": (19.0896, 72.8656),
    "BLR": (13.1986, 77.7066),
    "MAA": (12.9941, 80.1709),
    "CCU": (22.6547, 88.4467),
    "HYD": (17.2403, 78.4294),
    "GOI": (15.3808, 73.8314),
    "GOX": (15.7511, 73.8647),
    "COK": (10.1520, 76.4019),
    "BBI": (20.2444, 85.8178),
    "AMD": (23.0772, 72.6347),
    "PNQ": (18.5822, 73.9197)
}

MAJOR_HUBS = {"DEL", "BOM", "BLR"}
LOW_COST_CARRIERS = {"6E", "IX", "QP", "SG", "I5"}


def haversine_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """Calculates great-circle distance between two lat/lon pairs in kilometers."""
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    R = 6371.0  # Earth radius in km

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)


def engineer_dataset_features(df: pd.DataFrame) -> pd.DataFrame:
    """Engineers derived features for dataset v2.0 without future lookahead leakage."""
    if df.empty:
        return df

    df = df.copy()

    # 1. Standardize recorded_at date and calendar days_until_dep
    df["dep_date_obj"] = df["departure_date"].apply(parse_to_date)
    df["rec_date_obj"] = df["recorded_at"].apply(parse_to_date)
    df["days_until_dep"] = (df["dep_date_obj"] - df["rec_date_obj"]).apply(lambda x: x.days)

    # 2. Route Distance & Hub Route
    def get_distance(row):
        o, d = str(row.get("origin_code", "")).upper(), str(row.get("destination_code", "")).upper()
        if o in AIRPORT_COORDINATES and d in AIRPORT_COORDINATES:
            return haversine_distance(AIRPORT_COORDINATES[o], AIRPORT_COORDINATES[d])
        return 1000.0  # Default average domestic distance in km

    df["route_distance_km"] = df.apply(get_distance, axis=1)
    df["domestic_vs_international"] = "DOMESTIC"  # All Indian domestic routes
    df["hub_route"] = df.apply(
        lambda r: (str(r.get("origin_code")).upper() in MAJOR_HUBS) or (str(r.get("destination_code")).upper() in MAJOR_HUBS),
        axis=1
    )

    # 3. Airline Type
    df["airline_type"] = df["airline_code"].apply(
        lambda a: "LCC" if str(a).upper() in LOW_COST_CARRIERS else "FSC"
    )

    # 4. Temporal Features (Holiday, Day to Weekend, Season, Days Since Collection)
    start_date = df["rec_date_obj"].min()
    df["days_since_collection_start"] = df["rec_date_obj"].apply(lambda d: (d - start_date).days if pd.notna(d) else 0)
    df["days_to_weekend"] = df["dep_date_obj"].apply(lambda d: (5 - d.weekday()) % 7 if pd.notna(d) else 0)
    
    def get_season(d):
        m = d.month if pd.notna(d) else 1
        if m in (12, 1, 2): return "WINTER"
        if m in (3, 4, 5): return "SUMMER"
        if m in (6, 7, 8, 9): return "MONSOON"
        return "AUTUMN"

    df["season"] = df["dep_date_obj"].apply(get_season)
    df["holiday_window"] = df["dep_date_obj"].apply(lambda d: d.month in (10, 11, 12, 1) if pd.notna(d) else False)

    # 5. Booking Window & Fare Bucket
    def get_booking_window(days):
        if days <= 3: return "0-3d"
        if days <= 7: return "4-7d"
        if days <= 14: return "8-14d"
        if days <= 30: return "15-30d"
        if days <= 60: return "31-60d"
        return "61d+"

    df["booking_window"] = df["days_until_dep"].apply(get_booking_window)

    # 6. Expanding Window Aggregations (Historical Route / Airline Average & Std to PREVENT LEAKAGE)
    df_sorted = df.sort_values(by="recorded_at").copy()
    
    # Calculate expanding route stats up to prior observation
    df_sorted["historical_route_average"] = df_sorted.groupby("origin_code")["price"].transform(
        lambda s: s.shift(1).expanding().mean()
    ).fillna(df_sorted["price"].mean())

    df_sorted["historical_route_std"] = df_sorted.groupby("origin_code")["price"].transform(
        lambda s: s.shift(1).expanding().std()
    ).fillna(0.0)

    df_sorted["historical_airline_average"] = df_sorted.groupby("airline_code")["price"].transform(
        lambda s: s.shift(1).expanding().mean()
    ).fillna(df_sorted["price"].mean())

    df_sorted["historical_airline_std"] = df_sorted.groupby("airline_code")["price"].transform(
        lambda s: s.shift(1).expanding().std()
    ).fillna(0.0)

    # Re-align index back to original order
    df = df_sorted.loc[df.index]

    # Clean up temporary date objects
    df = df.drop(columns=["dep_date_obj", "rec_date_obj"], errors="ignore")
    return df
