"""Recommendation Policy Configuration.

Defines configurable policy limits and thresholds for flight booking recommendation decisions.
"""

class RecommendationPolicy:
    def __init__(
        self,
        book_threshold_percent: float = 5.0,
        wait_threshold_percent: float = -5.0,
        monitor_range_percent: float = 5.0,
        min_expected_savings: float = 100.0,
        max_acceptable_risk: float = 0.15,
        domestic_policy: dict = None,
        international_policy: dict = None,
        business_routes: list = None,
        holiday_routes: list = None
    ):
        self.BOOK_THRESHOLD_PERCENT = book_threshold_percent
        self.WAIT_THRESHOLD_PERCENT = wait_threshold_percent
        self.MONITOR_RANGE_PERCENT = monitor_range_percent
        self.MIN_EXPECTED_SAVINGS = min_expected_savings
        self.MAX_ACCEPTABLE_RISK = max_acceptable_risk
        
        self.domestic_policy = domestic_policy or {
            "BOOK_THRESHOLD_PERCENT": 4.0,
            "WAIT_THRESHOLD_PERCENT": -4.0,
            "MONITOR_RANGE_PERCENT": 4.0
        }
        self.international_policy = international_policy or {
            "BOOK_THRESHOLD_PERCENT": 6.0,
            "WAIT_THRESHOLD_PERCENT": -6.0,
            "MONITOR_RANGE_PERCENT": 6.0
        }
        self.business_routes = business_routes or ["DEL-BOM", "BOM-DEL"]
        self.holiday_routes = holiday_routes or ["DEL-GOI", "BOM-GOI"]
        
    def get_thresholds(self, origin: str, destination: str) -> dict:
        route = f"{origin.upper()}-{destination.upper()}"
        if route in self.business_routes:
            return {
                "BOOK_THRESHOLD_PERCENT": 3.0,
                "WAIT_THRESHOLD_PERCENT": -3.0,
                "MONITOR_RANGE_PERCENT": 3.0
            }
        elif route in self.holiday_routes:
            return {
                "BOOK_THRESHOLD_PERCENT": 7.0,
                "WAIT_THRESHOLD_PERCENT": -7.0,
                "MONITOR_RANGE_PERCENT": 7.0
            }
        # Fallback to domestic/international (heuristic: if IATA codes look international, but DEL-BOM is domestic)
        # For simplicity, we fallback to defaults unless classified
        return {
            "BOOK_THRESHOLD_PERCENT": self.BOOK_THRESHOLD_PERCENT,
            "WAIT_THRESHOLD_PERCENT": self.WAIT_THRESHOLD_PERCENT,
            "MONITOR_RANGE_PERCENT": self.MONITOR_RANGE_PERCENT
        }

# Default policy singleton instance
recommendation_policy = RecommendationPolicy()
