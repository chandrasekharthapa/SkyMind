from dataclasses import dataclass
from typing import List

@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    dtype: str
    category: str
    description: str
    feature_set_version: str
    owner_generator: str

# `dtype` is documentation, not a contract — nothing coerces to it. Every numeric
# feature here is emitted as float64 so that "unknown" can be NaN; the calendar
# fields were `int` with a -1 sentinel until 2026-08, which is why several say
# "float" for a quantity that only ever takes whole values.
#
# Existing 16 legacy features
LEGACY_FEATURE_SET: List[FeatureDefinition] = [
    FeatureDefinition("origin_code", "str", "route", "IATA departure code", "legacy", "RouteGenerator"),
    FeatureDefinition("destination_code", "str", "route", "IATA destination code", "legacy", "RouteGenerator"),
    FeatureDefinition("airline_code", "str", "airline", "Operating airline code", "legacy", "AirlineGenerator"),
    FeatureDefinition("days_until_dep", "float", "temporal", "Whole days from the observation to departure; null if the departure precedes it", "legacy", "TemporalGenerator"),
    FeatureDefinition("urgency", "float", "temporal", "1 / (days_until_dep + 1)", "legacy", "TemporalGenerator"),
    FeatureDefinition("day_of_week", "float", "temporal", "Departure weekday, Monday 0 to Sunday 6", "legacy", "TemporalGenerator"),
    FeatureDefinition("month", "float", "temporal", "Departure month (1-12)", "legacy", "TemporalGenerator"),
    FeatureDefinition("week_of_year", "float", "temporal", "ISO week of the departure date", "legacy", "TemporalGenerator"),
    FeatureDefinition("hour_of_day", "float", "temporal", "Departure hour, read from the departure_time column captured at ingest; null for rows written before that column existed", "legacy", "TemporalGenerator"),
    FeatureDefinition("is_peak_hour", "float", "temporal", "1.0 if the departure hour is 7-10 or 17-20, null if the hour is unknown", "legacy", "TemporalGenerator"),
    FeatureDefinition("seats_available", "float", "booking_curve", "Remaining seat count", "legacy", "BookingCurveGenerator"),
    FeatureDefinition("price_change_1d", "float", "booking_curve", "Fare minus the as-of fare one day earlier on the same curve", "legacy", "BookingCurveGenerator"),
    FeatureDefinition("price_change_3d", "float", "booking_curve", "Fare minus the as-of fare three days earlier on the same curve", "legacy", "BookingCurveGenerator"),
    FeatureDefinition("demand_score", "float", "market", "Never computed: null on both paths", "legacy", "MarketGenerator"),
    FeatureDefinition("seasonality_factor", "float", "market", "Never computed: null on both paths", "legacy", "MarketGenerator"),
    FeatureDefinition("is_live", "bool", "market", "Indicates if the query is a live query", "legacy", "MarketGenerator")
]

# Expanded feature set v1
FEATURE_SET_V1: List[FeatureDefinition] = [
    # Route Identity & Stats. Every statistic below is AS-OF: computed from the
    # observations on the same route recorded at or before this row's own
    # timestamp, and from nothing else. They were whole-corpus
    # `groupby(route).transform(...)` calls until 2026-08, which put the row's own
    # label inside its own feature window.
    FeatureDefinition("origin_code", "str", "route", "IATA departure code", "feature_set_v1", "RouteGenerator"),
    FeatureDefinition("destination_code", "str", "route", "IATA destination code", "feature_set_v1", "RouteGenerator"),
    FeatureDefinition("historical_average_fare", "float", "route", "Mean of the route's fares observed at or before this row's timestamp", "feature_set_v1", "RouteGenerator"),
    FeatureDefinition("historical_median_fare", "float", "route", "Median of the route's fares observed at or before this row's timestamp", "feature_set_v1", "RouteGenerator"),
    FeatureDefinition("historical_minimum_fare", "float", "route", "Cheapest fare the route has shown at or before this row's timestamp", "feature_set_v1", "RouteGenerator"),
    FeatureDefinition("historical_maximum_fare", "float", "route", "Dearest fare the route has shown at or before this row's timestamp", "feature_set_v1", "RouteGenerator"),
    FeatureDefinition("historical_price_std", "float", "route", "As-of sample std (ddof=1) of the route's fares; null below 2 observations", "feature_set_v1", "RouteGenerator"),
    FeatureDefinition("airline_count", "float", "route", "Distinct airlines the route has shown at or before this row's timestamp", "feature_set_v1", "RouteGenerator"),
    FeatureDefinition("average_booking_lead", "float", "route", "As-of mean of the booking horizon (departure date minus observation date) over the route's observations; null where no observation has one", "feature_set_v1", "RouteGenerator"),
    FeatureDefinition("observation_density", "float", "route", "Count of priced observations on the route at or before this row's timestamp. Not a rate: no time or volume divides it", "feature_set_v1", "RouteGenerator"),

    # Airline Identity & Stats. As-of on the same rule, and keyed on
    # (route, airline) rather than airline alone — except airline_route_share,
    # whose denominator is deliberately the whole market's route count.
    FeatureDefinition("airline_code", "str", "airline", "Operating airline code", "feature_set_v1", "AirlineGenerator"),
    FeatureDefinition("airline_average_fare", "float", "airline", "As-of mean of this airline's fares on this route", "feature_set_v1", "AirlineGenerator"),
    FeatureDefinition("airline_market_share", "float", "airline", "This airline's as-of observation count on the route over the route's as-of observation count", "feature_set_v1", "AirlineGenerator"),
    FeatureDefinition("airline_route_share", "float", "airline", "Distinct routes this airline has been seen on over distinct routes ANY airline has been seen on, both as-of", "feature_set_v1", "AirlineGenerator"),
    FeatureDefinition("airline_price_rank", "float", "airline", "Rank of this airline's as-of mean fare among the airlines seen on the route so far, 1 = cheapest; last-quote carried forward", "feature_set_v1", "AirlineGenerator"),
    FeatureDefinition("airline_volatility", "float", "airline", "As-of sample std (ddof=1) of this airline's fares on this route; null below 2 observations", "feature_set_v1", "AirlineGenerator"),
    FeatureDefinition("airline_observation_count", "float", "airline", "Count of this airline's priced observations on the route at or before this row's timestamp", "feature_set_v1", "AirlineGenerator"),

    # Temporal
    FeatureDefinition("departure_day_of_week", "float", "temporal", "Departure weekday, Monday 0 to Sunday 6", "feature_set_v1", "TemporalGenerator"),
    FeatureDefinition("departure_month", "float", "temporal", "Departure month (1-12)", "feature_set_v1", "TemporalGenerator"),
    FeatureDefinition("departure_quarter", "float", "temporal", "Departure calendar quarter (1-4)", "feature_set_v1", "TemporalGenerator"),
    FeatureDefinition("departure_week", "float", "temporal", "ISO departure week", "feature_set_v1", "TemporalGenerator"),
    FeatureDefinition("is_weekend", "float", "temporal", "Departure falls on Saturday/Sunday; null if the departure date is unreadable", "feature_set_v1", "TemporalGenerator"),
    FeatureDefinition("is_holiday", "float", "temporal", "Departure falls on one of five fixed-date Indian public holidays", "feature_set_v1", "TemporalGenerator"),
    FeatureDefinition("is_long_weekend", "float", "temporal", "Departure is a Friday or Monday that is itself a fixed-date holiday", "feature_set_v1", "TemporalGenerator"),
    FeatureDefinition("days_until_departure", "float", "temporal", "Whole days from the observation to departure; null if the departure precedes it", "feature_set_v1", "TemporalGenerator"),

    # Booking Curve. The curve is the five-part key including flight_number, so
    # these are one flight's own price history. An observation that does not name
    # all five is on no curve and every feature in this block is null for it —
    # including `observation_count`, which is a position along a curve and not a
    # count over an empty window. The `rolling_*` windows are the last 10
    # OBSERVATIONS including this one, not the last 10 days; the `price_change_*`
    # lags are the opposite — real days, resolved as-of.
    FeatureDefinition("days_since_first_observation", "float", "booking_curve", "Fractional days from this curve's first observation to this one", "feature_set_v1", "BookingCurveGenerator"),
    FeatureDefinition("observation_count", "float", "booking_curve", "This observation's 1-based position along the curve", "feature_set_v1", "BookingCurveGenerator"),
    FeatureDefinition("booking_curve_progress", "float", "booking_curve", "days_since_first_observation / (it + days_until_dep), clamped to [0,1]; 1.0 if that span is 0; null if either term is unknown", "feature_set_v1", "BookingCurveGenerator"),
    FeatureDefinition("rolling_mean_price", "float", "booking_curve", "Mean of the last 10 observations of this curve, this one included", "feature_set_v1", "BookingCurveGenerator"),
    FeatureDefinition("rolling_median_price", "float", "booking_curve", "Median of the last 10 observations of this curve", "feature_set_v1", "BookingCurveGenerator"),
    FeatureDefinition("rolling_min_price", "float", "booking_curve", "Cheapest of the last 10 observations of this curve", "feature_set_v1", "BookingCurveGenerator"),
    FeatureDefinition("rolling_max_price", "float", "booking_curve", "Dearest of the last 10 observations of this curve", "feature_set_v1", "BookingCurveGenerator"),
    FeatureDefinition("rolling_price_std", "float", "booking_curve", "Sample std (ddof=1) of the last 10 observations; null below 2", "feature_set_v1", "BookingCurveGenerator"),
    FeatureDefinition("price_change_1d", "float", "booking_curve", "Fare minus the latest fare on this curve at or before t-1d, within a 0.5d staleness tolerance; null if none qualifies", "feature_set_v1", "BookingCurveGenerator"),
    FeatureDefinition("price_change_3d", "float", "booking_curve", "Fare minus the latest fare on this curve at or before t-3d, within a 1.5d staleness tolerance; null if none qualifies", "feature_set_v1", "BookingCurveGenerator"),
    FeatureDefinition("price_change_7d", "float", "booking_curve", "Fare minus the latest fare on this curve at or before t-7d, within a 3.5d staleness tolerance; null if none qualifies", "feature_set_v1", "BookingCurveGenerator"),
    FeatureDefinition("price_slope", "float", "booking_curve", "Fare minus the immediately preceding observation's, over the real days between them (denominator floored at 0.1d); null with no predecessor", "feature_set_v1", "BookingCurveGenerator"),
    FeatureDefinition("price_acceleration", "float", "booking_curve", "price_slope minus the previous pair's slope, over the same elapsed days; null below 3 observations", "feature_set_v1", "BookingCurveGenerator"),
    FeatureDefinition("seats_available", "float", "booking_curve", "Remaining seat count", "feature_set_v1", "BookingCurveGenerator"),

    # Live Market. Cross-sectional: one route at one search timestamp, which at
    # serve time is the live snapshot and in training is the group of rows sharing
    # the resolved ordering timestamp.
    FeatureDefinition("lowest_fare", "float", "market", "Lowest fare in the snapshot", "feature_set_v1", "MarketGenerator"),
    FeatureDefinition("highest_fare", "float", "market", "Highest fare in the snapshot", "feature_set_v1", "MarketGenerator"),
    FeatureDefinition("average_fare", "float", "market", "Mean fare in the snapshot", "feature_set_v1", "MarketGenerator"),
    FeatureDefinition("median_fare", "float", "market", "Median fare in the snapshot", "feature_set_v1", "MarketGenerator"),
    FeatureDefinition("fare_spread", "float", "market", "Highest minus lowest fare in the snapshot", "feature_set_v1", "MarketGenerator"),
    FeatureDefinition("price_std_dev", "float", "market", "Sample std (ddof=1) of the snapshot's fares; null below 2 priced flights", "feature_set_v1", "MarketGenerator"),
    FeatureDefinition("total_live_flights", "float", "market", "Flights in the snapshot, priced or not", "feature_set_v1", "MarketGenerator"),
    FeatureDefinition("direct_ratio", "float", "market", "Direct flights over flights whose stop count is KNOWN; null if none is", "feature_set_v1", "MarketGenerator"),
    FeatureDefinition("connecting_ratio", "float", "market", "Connecting flights over flights whose stop count is KNOWN; null if none is", "feature_set_v1", "MarketGenerator"),
    FeatureDefinition("airline_diversity", "float", "market", "Distinct airlines in the snapshot", "feature_set_v1", "MarketGenerator"),
    FeatureDefinition("snapshot_quality", "float", "market", "1.0, times 0.8 if under 80% of flights are priced, times 0.9 if under 3 are", "feature_set_v1", "MarketGenerator"),
    FeatureDefinition("snapshot_completeness", "float", "market", "Priced flights over total flights in the snapshot", "feature_set_v1", "MarketGenerator"),
    FeatureDefinition("is_live", "bool", "market", "Passed through from the observation in training, True at serve time", "feature_set_v1", "MarketGenerator"),

    # Volatility. Every window below is counted in OBSERVATIONS, not days: on a
    # curve scraped twice a day a 10-observation window spans five days.
    FeatureDefinition("rolling_volatility", "float", "volatility", "Sample std (ddof=1) of the last 10 observations of this flight's fare; null below 2", "feature_set_v1", "VolatilityGenerator"),
    FeatureDefinition("coefficient_of_variation", "float", "volatility", "rolling_volatility divided by the mean of the same window", "feature_set_v1", "VolatilityGenerator"),
    FeatureDefinition("rolling_price_range", "float", "volatility", "Max minus min over the last 10 observations", "feature_set_v1", "VolatilityGenerator"),
    FeatureDefinition("rolling_iqr", "float", "volatility", "75th minus 25th percentile over the last 10 observations", "feature_set_v1", "VolatilityGenerator"),
    FeatureDefinition("volatility_trend", "float", "volatility", "Std of the last 5 observations divided by std of the last 15", "feature_set_v1", "VolatilityGenerator"),

    # Trend
    FeatureDefinition("ema_7", "float", "trend", "EMA of this flight's fare, span 7 OBSERVATIONS (not days), adjust=False", "feature_set_v1", "TrendGenerator"),
    FeatureDefinition("ema_14", "float", "trend", "EMA of this flight's fare, span 14 OBSERVATIONS (not days), adjust=False", "feature_set_v1", "TrendGenerator"),
    FeatureDefinition("rolling_median_7", "float", "trend", "Median of the last 7 observations (not days)", "feature_set_v1", "TrendGenerator"),
    FeatureDefinition("rolling_mean_14", "float", "trend", "Mean of the last 14 observations (not days)", "feature_set_v1", "TrendGenerator"),
    FeatureDefinition("trend_direction", "float", "trend", "sign(ema_7 - ema_14): -1, 0 or 1; null when either EMA is unknown", "feature_set_v1", "TrendGenerator"),
    # Not an R-squared, whatever this line said until 2026-08. There is no
    # regression anywhere in `trend_features` to fit one against.
    FeatureDefinition("trend_strength", "float", "trend", "abs(ema_7 - ema_14) / (rolling_volatility + 1.0)", "feature_set_v1", "TrendGenerator"),
    FeatureDefinition("trend_duration", "float", "trend", "Consecutive OBSERVATIONS (not days) with the current trend_direction sign", "feature_set_v1", "TrendGenerator")
]
