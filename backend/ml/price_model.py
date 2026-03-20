"""
AI Price Prediction Engine.
Uses scikit-learn + Prophet for flight price forecasting.
"""

import os
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
import joblib
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
os.makedirs(MODEL_DIR, exist_ok=True)


class FlightPricePredictor:
    """
    Gradient Boosting model for flight price prediction.
    
    Features:
    - days_until_departure
    - day_of_week (0=Mon ... 6=Sun)
    - month
    - is_weekend
    - is_holiday (approx)
    - airline_encoded
    - origin_encoded
    - destination_encoded
    """

    def __init__(self, route_key: Optional[str] = None):
        self.route_key = route_key or "global"
        self.model: Optional[GradientBoostingRegressor] = None
        self.airline_encoder = LabelEncoder()
        self.origin_encoder = LabelEncoder()
        self.dest_encoder = LabelEncoder()
        self._trained = False

    def _engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Transform raw data into ML features."""
        df = df.copy()
        df["days_until_departure"] = pd.to_numeric(df["days_until_departure"], errors="coerce").fillna(30)
        df["day_of_week"] = pd.to_numeric(df.get("day_of_week", 0), errors="coerce").fillna(0)
        df["month"] = pd.to_numeric(df.get("month", 6), errors="coerce").fillna(6)
        df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)
        df["is_near_departure"] = (df["days_until_departure"] <= 7).astype(int)
        df["is_advance_booking"] = (df["days_until_departure"] >= 60).astype(int)
        # Log-transform days to capture non-linear relationship
        df["log_days"] = np.log1p(df["days_until_departure"])
        return df

    def train(self, df: pd.DataFrame) -> dict:
        """Train model on historical price data."""
        if len(df) < 10:
            logger.warning("Not enough data to train model, using synthetic data")
            df = self._generate_synthetic_data()

        df = self._engineer_features(df)

        # Encode categoricals
        df["airline_enc"] = self.airline_encoder.fit_transform(
            df.get("airline_code", pd.Series(["AI"] * len(df))).fillna("AI")
        )
        df["origin_enc"] = self.origin_encoder.fit_transform(
            df.get("origin_code", pd.Series(["DEL"] * len(df))).fillna("DEL")
        )
        df["dest_enc"] = self.dest_encoder.fit_transform(
            df.get("destination_code", pd.Series(["BOM"] * len(df))).fillna("BOM")
        )

        feature_cols = [
            "days_until_departure", "day_of_week", "month",
            "is_weekend", "is_near_departure", "is_advance_booking",
            "log_days", "airline_enc", "origin_enc", "dest_enc",
        ]

        X = df[feature_cols].values
        y = df["price"].values

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        self.model = GradientBoostingRegressor(
            n_estimators=200,
            learning_rate=0.05,
            max_depth=4,
            subsample=0.8,
            random_state=42,
        )
        self.model.fit(X_train, y_train)

        preds = self.model.predict(X_test)
        mae = mean_absolute_error(y_test, preds)
        self._trained = True

        # Save model
        self._save()
        logger.info(f"Model trained. MAE: ₹{mae:.2f}")
        return {"mae": mae, "samples": len(df)}

    def predict(
        self,
        days_until_departure: int,
        departure_date: datetime,
        airline_code: str = "AI",
        origin_code: str = "DEL",
        destination_code: str = "BOM",
    ) -> dict:
        """Predict price and recommendation for a given flight."""
        self._load_if_needed()

        # If no trained model, use heuristic
        if not self._trained or self.model is None:
            return self._heuristic_prediction(days_until_departure, departure_date)

        row = pd.DataFrame([{
            "days_until_departure": days_until_departure,
            "day_of_week": departure_date.weekday(),
            "month": departure_date.month,
            "airline_code": airline_code,
            "origin_code": origin_code,
            "destination_code": destination_code,
        }])
        row = self._engineer_features(row)

        # Handle unseen labels
        def safe_transform(enc, val):
            try:
                return enc.transform([val])[0]
            except ValueError:
                return 0

        row["airline_enc"] = safe_transform(self.airline_encoder, airline_code)
        row["origin_enc"] = safe_transform(self.origin_encoder, origin_code)
        row["dest_enc"] = safe_transform(self.dest_encoder, destination_code)

        feature_cols = [
            "days_until_departure", "day_of_week", "month",
            "is_weekend", "is_near_departure", "is_advance_booking",
            "log_days", "airline_enc", "origin_enc", "dest_enc",
        ]
        pred_price = float(self.model.predict(row[feature_cols])[0])

        return self._build_recommendation(pred_price, days_until_departure)

    def forecast_30_days(
        self,
        origin: str,
        destination: str,
        base_price: float = 5000.0,
    ) -> list[dict]:
        """Generate 30-day price forecast for a route."""
        today = datetime.now()
        forecast = []

        for i in range(30):
            future_date = today + timedelta(days=i)
            days_until = 30 - i if i < 30 else 1
            pred = self.predict(
                days_until_departure=days_until,
                departure_date=future_date,
                origin_code=origin,
                destination_code=destination,
            )

            # Add realistic noise
            noise = np.random.normal(0, base_price * 0.05)
            price = max(pred["predicted_price"] + noise, base_price * 0.5)

            forecast.append({
                "date": future_date.strftime("%Y-%m-%d"),
                "price": round(price, 2),
                "confidence_low": round(price * 0.9, 2),
                "confidence_high": round(price * 1.1, 2),
                "recommendation": pred["recommendation"],
            })

        return forecast

    def _build_recommendation(self, pred_price: float, days_until: int) -> dict:
        """Build structured recommendation from prediction."""
        # Price trend analysis
        if days_until > 60:
            recommendation = "WAIT"
            reason = "Prices typically drop 60+ days before departure. Monitor prices."
            trend = "NEUTRAL"
        elif days_until > 21:
            recommendation = "BOOK_SOON"
            reason = "Good window to book. Prices may rise in coming weeks."
            trend = "RISING"
        elif days_until > 7:
            recommendation = "BOOK_NOW"
            reason = "Prices are rising rapidly. Book immediately."
            trend = "RISING_FAST"
        else:
            recommendation = "LAST_MINUTE"
            reason = "Last minute prices. Book if you must travel."
            trend = "HIGH"

        # Probability of price increase
        prob_increase = min(0.95, max(0.05, 1 - (days_until / 90)))

        return {
            "predicted_price": round(pred_price, 2),
            "recommendation": recommendation,
            "reason": reason,
            "price_trend": trend,
            "probability_increase": round(prob_increase, 2),
            "confidence": 0.78,
        }

    def _heuristic_prediction(self, days_until: int, departure_date: datetime) -> dict:
        """Fallback heuristic when model isn't trained."""
        base = 8000
        # Scarcity multiplier
        if days_until <= 3:
            multiplier = 2.5
        elif days_until <= 7:
            multiplier = 1.8
        elif days_until <= 14:
            multiplier = 1.4
        elif days_until <= 30:
            multiplier = 1.1
        elif days_until <= 60:
            multiplier = 0.95
        else:
            multiplier = 0.85

        # Weekend premium
        if departure_date.weekday() in [4, 5, 6]:  # Fri-Sun
            multiplier *= 1.15

        # Month seasonality
        month_mult = {12: 1.3, 1: 1.2, 6: 1.15, 7: 1.15, 10: 1.1}.get(
            departure_date.month, 1.0
        )
        pred_price = base * multiplier * month_mult
        return self._build_recommendation(pred_price, days_until)

    def _generate_synthetic_data(self) -> pd.DataFrame:
        """Generate synthetic training data for demo purposes."""
        np.random.seed(42)
        n = 1000
        airlines = ["AI", "6E", "SG", "UK"]
        origins = ["DEL", "BOM", "BLR", "MAA"]
        dests = ["DXB", "LHR", "SIN", "BKK"]

        days = np.random.randint(1, 120, n)
        months = np.random.randint(1, 13, n)
        dow = np.random.randint(0, 7, n)

        base_price = 8000
        prices = (
            base_price
            + (1 / (days + 1)) * 15000
            + np.where(dow >= 5, 1500, 0)
            + np.where(months.isin([12, 1, 6, 7]) if hasattr(months, 'isin') else np.isin(months, [12, 1, 6, 7]), 2000, 0)
            + np.random.normal(0, 800, n)
        )
        prices = np.maximum(prices, 3000)

        return pd.DataFrame({
            "days_until_departure": days,
            "month": months,
            "day_of_week": dow,
            "price": prices,
            "airline_code": np.random.choice(airlines, n),
            "origin_code": np.random.choice(origins, n),
            "destination_code": np.random.choice(dests, n),
        })

    def _save(self):
        path = os.path.join(MODEL_DIR, f"{self.route_key}_model.pkl")
        joblib.dump({
            "model": self.model,
            "airline_encoder": self.airline_encoder,
            "origin_encoder": self.origin_encoder,
            "dest_encoder": self.dest_encoder,
        }, path)

    def _load_if_needed(self):
        if self._trained:
            return
        path = os.path.join(MODEL_DIR, f"{self.route_key}_model.pkl")
        if os.path.exists(path):
            saved = joblib.load(path)
            self.model = saved["model"]
            self.airline_encoder = saved["airline_encoder"]
            self.origin_encoder = saved["origin_encoder"]
            self.dest_encoder = saved["dest_encoder"]
            self._trained = True


# ============================================================
# Hidden Route Finder — Dijkstra Algorithm
# ============================================================

import heapq


class HiddenRouteFinder:
    """
    Find cheaper multi-stop routes using Dijkstra's algorithm
    on a graph of flight prices between airports.
    """

    def __init__(self):
        # Graph: {airport: [(price, dest, via)]}
        self.graph: dict[str, list] = {}

    def add_route(self, origin: str, destination: str, price: float, via: str = ""):
        if origin not in self.graph:
            self.graph[origin] = []
        self.graph[origin].append((price, destination, via))

    def find_cheapest_path(
        self, origin: str, destination: str, max_stops: int = 2
    ) -> Optional[dict]:
        """Find cheapest route using Dijkstra with stop constraint."""
        if not self.graph:
            return None

        # Priority queue: (cost, current_airport, path, stops)
        pq = [(0, origin, [origin], 0)]
        visited = {}

        while pq:
            cost, airport, path, stops = heapq.heappop(pq)

            if airport == destination:
                return {
                    "path": path,
                    "total_price": cost,
                    "stops": stops - 1,
                    "savings_vs_direct": None,  # Set by caller
                }

            state = (airport, stops)
            if state in visited and visited[state] <= cost:
                continue
            visited[state] = cost

            if stops >= max_stops + 1:
                continue

            for next_price, next_airport, via in self.graph.get(airport, []):
                if next_airport not in path:  # No cycles
                    heapq.heappush(
                        pq,
                        (cost + next_price, next_airport, path + [next_airport], stops + 1),
                    )

        return None

    def find_hidden_routes(
        self, origin: str, destination: str, direct_price: float
    ) -> list[dict]:
        """Find all hidden cheaper routes and compare to direct."""
        results = []

        # Try common hub airports
        hubs = ["DXB", "IST", "SIN", "DOH", "FRA", "AMS", "CDG", "LHR", "BKK"]
        for hub in hubs:
            if hub == origin or hub == destination:
                continue
            path = self.find_cheapest_path(origin, destination, max_stops=2)
            if path and path["total_price"] < direct_price:
                savings = direct_price - path["total_price"]
                path["savings_vs_direct"] = round(savings, 2)
                path["savings_percent"] = round(savings / direct_price * 100, 1)
                results.append(path)

        return sorted(results, key=lambda x: x["total_price"])


# Singleton predictor
_predictor = FlightPricePredictor(route_key="global")


def get_predictor() -> FlightPricePredictor:
    return _predictor
