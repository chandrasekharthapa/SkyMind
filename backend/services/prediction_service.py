"""Prediction Orchestration Service.

Coordinates prediction validations, model registry lookups, schema validators,
live market snapshot retrievals, pure inference runs, and Observability instrumentation.
"""

import time
import math
import logging
from datetime import datetime, date, timezone
from typing import Dict, Any, Optional, List
import numpy as np

from opentelemetry import metrics

from backend.services.market_snapshot_provider import MarketSnapshotProvider, market_snapshot_provider as default_snapshot_provider
from backend.services.model_registry import ModelRegistry, model_registry as default_registry
from backend.services.model_schema_validator import ModelSchemaValidator as default_validator
from backend.services.prediction_formatter import PredictionFormatter as default_formatter
from backend.services.consistency_validator import PredictionConsistencyValidator as default_consistency_validator
from backend.services.ingestion_controller import MarketDataController
from backend.utils.exceptions import PredictionUnavailable
from backend.domain.domain_events import DomainEvent, event_dispatcher
from backend.ml.price_model import get_predictor
from backend.database.flight_repository import flight_repository
from backend.services.recommendation_policy import recommendation_policy as default_recommendation_policy
from backend.services.event_publisher import EventPublisher, AuditLogEventPublisher
from backend.services.forecast_engine import ForecastEngine
from backend.services.recommendation_engine import RecommendationEngine
from backend.services.confidence_policy import metrics_for_horizon, resolve_published_accuracy

logger = logging.getLogger(__name__)

# OpenTelemetry meters setup
meter = metrics.get_meter("skymind.predict")

predict_latency_hist = meter.create_histogram(
    name="prediction_latency_seconds",
    description="Measures E2E prediction pipeline latency"
)
ml_inference_latency_hist = meter.create_histogram(
    name="ml_inference_latency_seconds",
    description="Measures ML model predict latency"
)
forecast_latency_hist = meter.create_histogram(
    name="forecast_generation_latency_seconds",
    description="Measures forecast generation latency"
)
rec_latency_hist = meter.create_histogram(
    name="recommendation_generation_latency_seconds",
    description="Measures recommendation engine latency"
)
# `prediction_deviation_rupees` was declared here and set from the validator's own
# `deviation` figure, duplicating `prediction_market_deviation_rupees`, which the
# validator emits with route and provider labels. Removed rather than kept as an
# unlabelled second copy of the same quantity.
missing_features_counter = meter.create_counter(
    name="prediction_missing_features_total",
    description="Tracks the count of missing features in prediction payloads"
)
prediction_failures_counter = meter.create_counter(
    name="prediction_failures_total",
    description="Tracks total predict failures"
)

# How many recorded observations of *one booking curve* the movement features are
# computed from, newest first.
#
# This was the bare literal `100` passed to `get_price_history_cache`, and it
# capped the wrong population: the query filtered on route and departure date
# only, so on a route with several carriers a day the 100 newest rows could hold
# nought to two observations of the flight being quoted — the narrowing to a
# single curve happens later, in `price_changes_from_records`. The features then
# came out NaN and the refusal blamed the route's observation count. The query
# below now carries the resolved flight's identity, so this bounds the curve the
# features are about.
CURVE_HISTORY_ROW_CAP = 100

class PredictionValidator:
    @staticmethod
    def validate_request(origin: str, destination: str, departure_date: str, airline_code: Optional[str] = None) -> None:
        """Validate input parameters before running predictions."""
        if origin == destination:
            raise ValueError("Origin and destination must differ.")
        
        # Valid IATA codes
        if len(origin) != 3 or not origin.isalpha():
            raise ValueError("Origin IATA code must be exactly 3 alphabetic letters.")
        if len(destination) != 3 or not destination.isalpha():
            raise ValueError("Destination IATA code must be exactly 3 alphabetic letters.")

        # Valid airline code
        if airline_code and (len(airline_code) < 2 or len(airline_code) > 3 or not airline_code.isalnum()):
            raise ValueError("Airline code must be 2-3 alphanumeric characters.")

        # Future departure date
        try:
            dep_date = datetime.strptime(departure_date, "%Y-%m-%d").date()
            if dep_date < date.today():
                raise ValueError("Departure date must be in the future.")
        except ValueError as e:
            if "future" in str(e):
                raise e
            raise ValueError("Departure date must match YYYY-MM-DD format.")

    @staticmethod
    def validate_outputs(price: float, confidence: Optional[float], forecast: List[Dict[str, Any]]) -> None:
        """Validate predictions, confidence ranges, and forecast sequences."""
        if not math.isfinite(price) or price <= 0:
            raise ValueError("Predicted price must be a finite positive number.")

        if confidence is not None:
            if not (0.0 <= confidence <= 100.0):
                raise ValueError("Confidence percentage must be between 0 and 100.")

        for day in forecast:
            p = day.get("price")
            l = day.get("lower")
            u = day.get("upper")
            if p is None or l is None or u is None or not (l <= p <= u):
                raise ValueError("Forecast day prices must be valid and conform to lower <= price <= upper bounds.")

class PredictionService:
    def __init__(
        self,
        market_snapshot_provider: Optional[MarketSnapshotProvider] = None,
        model_registry: Optional[ModelRegistry] = None,
        model_schema_validator: Optional[Any] = None,
        predictor: Optional[Any] = None,
        formatter: Optional[Any] = None,
        consistency_validator: Optional[Any] = None,
        forecast_engine: Optional[ForecastEngine] = None,
        recommendation_engine: Optional[RecommendationEngine] = None,
        recommendation_policy: Optional[Any] = None,
        event_publisher: Optional[EventPublisher] = None
    ):
        # Dependency Injection mappings
        self.market_snapshot_provider = market_snapshot_provider or default_snapshot_provider
        self.model_registry = model_registry or default_registry
        self.model_schema_validator = model_schema_validator or default_validator
        # There was a `self.feature_builder = feature_builder or default_feature_builder`
        # here, and a `feature_builder` constructor parameter above it. Nothing read
        # the attribute: features come from `feature_engineering_pipeline.build(...)`
        # further down, and `PredictionFeatureBuilder` — a fourth hand-maintained
        # copy of the legacy 16-name contract — had no production caller at all. The
        # injection point advertised a seam that did not exist, so a test double
        # passed here would have been accepted and ignored. Both are gone with the
        # module.
        self.predictor = predictor or get_predictor()
        self.formatter = formatter or default_formatter
        self.consistency_validator = consistency_validator or default_consistency_validator

        self.event_publisher = event_publisher or AuditLogEventPublisher()
        # Was `self.policy = recommendation_policy or recommendation_policy`. The
        # constructor parameter shadows the module-level import of the same name, so
        # both sides of the `or` read the parameter and `self.policy` was None
        # whenever nothing was injected — which is every production construction.
        # It was invisible because the only consumer, `RecommendationEngine`, does
        # `self.policy = recommendation_policy or default_policy` and quietly
        # supplied the same module this line meant to reach. The import is now
        # aliased, so the fallback names a different object than the parameter.
        self.policy = recommendation_policy or default_recommendation_policy
        self.forecast_engine = forecast_engine or ForecastEngine(
            model_registry=self.model_registry,
            model_schema_validator=self.model_schema_validator,
            predictor=self.predictor,
            formatter=self.formatter,
            event_publisher=self.event_publisher
        )
        self.recommendation_engine = recommendation_engine or RecommendationEngine(
            recommendation_policy=self.policy,
            event_publisher=self.event_publisher
        )
        self.repository = flight_repository

        # Publish ModelLoaded event
        self.event_publisher.publish("ModelLoaded", {
            "model_version": self.model_registry.model_version,
            "feature_schema_version": self.model_registry.feature_schema_version,
            "supported_horizons": self.model_registry.supported_horizons
        })

    async def predict(self, origin: str, destination: str, departure_date: str, airline_code: Optional[str] = None) -> Dict[str, Any]:
        """Orchestrates the entire aligned prediction and forecasting workflow."""
        start_time = time.time()
        
        try:
            # 1. Input Validation
            PredictionValidator.validate_request(origin, destination, departure_date, airline_code)

            # 1b. Capability precondition, checked before any work is done.
            #
            # `ForecastEngine.run_forecast` raises this same refusal, but it runs at
            # step 6 — after a market snapshot has been fetched over the network,
            # features built, and `predictor.predict()` called. So a request the
            # active model provably cannot serve paid for a scrape and an inference
            # first, and whichever of those failed first decided the error the
            # client saw: with no artifact on disk the caller got
            # `FileNotFoundError` from step 5 rather than the capability refusal
            # this method's own contract names. Checked here, the answer is the same
            # whether or not a model happens to be loadable.
            if not self.model_registry.supports_forecasting:
                raise PredictionUnavailable(
                    "Prediction unavailable: Active model does not support forecasting.")

            # 2. Get Market Snapshot (caching and resilience policies handled inside snapshot provider)
            market_snapshot = await self.market_snapshot_provider.get_market_snapshot(origin, destination, departure_date)

            # The one place liveness is decided. This used to be computed at the
            # bottom of the method, after the recommendation engine had already
            # run and after the assembler had derived its own rival definition, so
            # the recommendation was scored without it. It is established here,
            # immediately after the snapshot is observed, and every consumer below
            # is handed this value rather than re-deriving one.
            is_live_avail = (
                market_snapshot.total_live_flights > 0
                and not math.isnan(market_snapshot.lowest_fare)
            )

            # Resolve parameters using snapshot context
            #
            # Which flight this prediction is about, established once, here, from
            # the snapshot — fare, carrier and flight number together. Three
            # separate guesses used to stand in for it:
            #
            #   * `resolved_airline` came from `list(airline_distribution.keys())[0]`
            #     when the caller named no airline — an arbitrary carrier in
            #     provider insertion order, so the airline features described one
            #     flight while `current_price` was another's fare;
            #   * the flight number was never resolved at all, so the five-part
            #     booking-curve key could match no stored observation and all
            #     fourteen curve features, plus volatility and trend, were computed
            #     over a window one observation long — the quoted fare's own;
            #   * `current_price` was the market's `lowest_fare` even when the caller
            #     named a carrier, so a request about AI was answered with 6E's
            #     fare if 6E happened to be cheaper.
            #
            # A named carrier is quoted its own cheapest flight. A carrier the
            # snapshot does not contain has no live fare, and gets none: the
            # existing NaN handling below then reports the prediction as
            # historical-only rather than inventing a price.
            by_airline = market_snapshot.cheapest_by_airline or {}
            resolved_airline = airline_code
            if resolved_airline:
                quoted = by_airline.get(resolved_airline) or {}
                quoted_fare = quoted.get("fare", np.nan)
                resolved_flight_number = quoted.get("flight_number")
                # Read out of the same mapping as the fare, so the seat count and
                # the departure hour describe the flight being quoted rather than
                # the route. See the note below for what stood in for them.
                seats_available = quoted.get("seats_available")
                departure_time_str = quoted.get("departure_time")
                if not quoted:
                    logger.warning(
                        "No live fare for %s on %s-%s in this snapshot; the "
                        "market's lowest fare belongs to another carrier and is "
                        "not quoted as this one's.",
                        resolved_airline, origin, destination,
                    )
            else:
                resolved_airline = market_snapshot.cheapest_airline
                resolved_flight_number = market_snapshot.cheapest_flight_number
                quoted_fare = market_snapshot.lowest_fare
                seats_available = market_snapshot.cheapest_seats_available
                departure_time_str = market_snapshot.cheapest_departure_time

            # Named `quoted_` and not `lowest_`: it is the fare of the one flight
            # this prediction is about, which is the market minimum only when the
            # caller named no carrier.
            quoted_fare_val = float(quoted_fare) if quoted_fare is not None else np.nan
            if math.isnan(quoted_fare_val):
                logger.warning("Live market snapshot fare unavailable (MCP/Search offline or degraded). Continuing prediction using historical feature context.")

            # `seats_available` and `departure_time_str` are the quoted flight's own,
            # resolved above beside its fare. Both name per-flight columns of
            # `price_history`, so the model was fitted on one flight's seat count and
            # one flight's departure hour. What stood here instead:
            #
            #     seats_available = None
            #     if market_snapshot.seat_information:
            #         seats_available = int(round(
            #             market_snapshot.seat_information.get("average", 15.0)))
            #
            #     # Derive departure_time_str from snapshot time distributions to
            #     # prevent fabrication
            #     departure_time_str = None
            #     if market_snapshot.departure_distribution.get("morning", 0) > 0:
            #         departure_time_str = f"{departure_date}T08:00:00"
            #     elif market_snapshot.departure_distribution.get("afternoon", 0) > 0:
            #         departure_time_str = f"{departure_date}T14:00:00"
            #     elif market_snapshot.departure_distribution.get("evening", 0) > 0:
            #         departure_time_str = f"{departure_date}T20:00:00"
            #
            # The first sent a route-wide *mean* under a per-flight feature name, and
            # sent `15` whenever `seat_information` existed without an `average` key
            # — a seat count with no source at all. The second reconstructed a
            # departure time out of a three-bucket histogram: every flight leaving
            # between 05:00 and 11:59 was served to the model as 08:00, the bucket
            # chosen by an `if/elif` chain that stops at the first non-empty one, so
            # on a route with morning departures the answer was `T08` no matter when
            # the quoted flight actually left. `hour_of_day` and `is_peak_hour` were
            # then computed from the invented hour. The comment claimed the block
            # existed "to prevent fabrication".
            #
            # The provider was reading a real per-flight `departure_time` all along
            # and discarding it into the histogram; it now carries it, and the mean
            # seat count stays where it belongs, in `seat_information`.
            #
            # None when the provider reported neither, which the generators turn into
            # NaN. A missing seat count is not the route's average, and a flight
            # whose departure time nobody reported does not leave at eight.
            if seats_available is not None:
                try:
                    seats_available = int(seats_available)
                except (TypeError, ValueError):
                    logger.warning(
                        "Snapshot reported an unreadable seat count (%r) for %s %s; "
                        "sending no seat count rather than a substitute.",
                        seats_available, resolved_airline, resolved_flight_number,
                    )
                    seats_available = None

            # Put the departure time into the shape the trained column has.
            #
            # `TemporalFeatureGenerator` reads `hour_of_day` from
            # `price_history.departure_time` during training via
            # `pd.to_datetime(...).dt.hour`, and at serve time from this string via
            # `split("T")[1]`. Every stored value carries a "T" because
            # `normalize_departure_time` put it there at ingest — but the live
            # provider is not normalised, and reports whatever the site rendered. A
            # provider giving "06:00" would therefore have been NaN here while the
            # row ingested from the same provider trained as hour 6: the two paths
            # would disagree for no reason other than which one had passed through
            # ingestion. Calling the same function means one definition of this
            # column exists, and it is the one the model was fitted on.
            #
            # Still None for anything the function cannot parse — it combines a bare
            # time with the departure date and returns None otherwise, rather than
            # guessing a plausible-looking datetime.
            if departure_time_str is not None:
                normalized_dep_time = MarketDataController.normalize_departure_time(
                    departure_time_str, departure_date
                )
                if normalized_dep_time is None:
                    logger.warning(
                        "Snapshot reported an unparseable departure time (%r) for "
                        "%s %s; sending none rather than a substitute.",
                        departure_time_str, resolved_airline, resolved_flight_number,
                    )
                departure_time_str = normalized_dep_time

            # 3. Prediction Feature Engineering Context & Pipeline
            from backend.ml.feature_context import FeatureContext
            from backend.ml.feature_engineering_pipeline import feature_engineering_pipeline
            
            # Newest-first observations of the one booking curve this prediction is
            # about. The identity resolved above is passed into the query so the cap
            # bounds that curve; see `CURVE_HISTORY_ROW_CAP` for what the route-wide
            # version of this call truncated. The filter is only as narrow as the
            # identity the snapshot supplied: no flight number filters on the carrier
            # alone, and no carrier is route-wide, as before.
            hist_records = self.repository.get_price_history_cache(
                origin, destination, departure_date, CURVE_HISTORY_ROW_CAP,
                airline_code=resolved_airline,
                flight_number=resolved_flight_number,
            ) or []
            
            ctx = FeatureContext(
                historical_data=hist_records,
                market_snapshot=market_snapshot,
                prediction_context={
                    "origin": origin,
                    "destination": destination,
                    "airline": resolved_airline,
                    # The fifth component of the booking-curve key. Without it the
                    # key rendered its missing part as the string `"NONE"`, matched
                    # nothing in `hist_records`, and every curve, volatility and
                    # trend feature was computed from `current_price` alone:
                    # `observation_count` 1.0, `days_since_first_observation` 0.0,
                    # `booking_curve_progress` 0.0, each `rolling_*` equal to the
                    # quoted fare, `rolling_price_range` and `rolling_iqr` 0.0.
                    # Measured on a five-day curve, 11 of the 14 curve features
                    # differed from what training computes under the same names.
                    # None when the provider named no flight, and the generators
                    # then return NaN rather than a one-observation window.
                    "flight_number": resolved_flight_number,
                    "departure_date": departure_date,
                    "departure_time": departure_time_str,
                    "seats_available": seats_available,
                    "current_price": quoted_fare_val if not math.isnan(quoted_fare_val) else None
                },
                route_statistics={},
                airline_statistics={},
                booking_statistics={},
                current_timestamp=datetime.now(timezone.utc)
            )
            
            # The feature-set version selects which builder runs, so it decides what
            # the model is fed. This block used to be:
            #
            #     from unittest.mock import MagicMock
            #     if isinstance(fs_version, MagicMock):
            #         ...
            #         fs_version = "legacy" if len(expected_cols) <= 16 else "feature_set_v1"
            #
            # i.e. the production serving path branched on whether its own injected
            # dependency was a test double, and in that branch chose the feature-set
            # version by counting the mock's `expected_features`. `ModelRegistry`
            # always returns a `str` here, so the branch was unreachable for a real
            # registry and existed solely to make two mock-registry tests get further
            # than they should. A registry that cannot name its feature set cannot be
            # served from, so say that instead of guessing.
            fs_version = self.model_registry.feature_set_version
            if not isinstance(fs_version, str) or not fs_version:
                raise PredictionUnavailable(
                    f"Model registry {type(self.model_registry).__name__} reported no "
                    f"feature-set version ({fs_version!r}), so there is no way to know "
                    f"which feature vector the deployed model expects."
                )

            feature_vector = feature_engineering_pipeline.build(ctx, fs_version)
            features = feature_vector.features
            
            # Count missing features for observability
            missing_count = sum(1 for col in features if isinstance(features[col], float) and math.isnan(features[col]))
            missing_features_counter.add(missing_count)

            # 4. Strict Model Schema Validation (Fails fast if features do not match expected deployed model features list)
            expected_features = self.model_registry.expected_features
            try:
                self.model_schema_validator.validate_schema(features, expected_features, fs_version)
            except ValueError as val_err:
                self.event_publisher.publish("SchemaValidationFailed", {
                    "error": str(val_err),
                    "schema": expected_features
                })
                event_dispatcher.dispatch(DomainEvent(
                    event_type="SchemaValidationFailed",
                    metadata={"error": str(val_err), "schema": expected_features}
                ))
                raise val_err

            # 5. Pure inference using PricePredictor (XGBoost) - NO modifications or scaling applied to outputs
            #
            # The horizon is resolved once, here, and the same value is used for the
            # point prediction, for selecting the forecast point that becomes the
            # published price, and for choosing whose accuracy figure is published
            # beside it. This call was `self.predictor.predict(features)`, taking
            # `predict()`'s default of 3, while the response was labelled with
            # `model_registry.prediction_horizon` read further down. Those agreed
            # only because that property was a hardcoded 3; with the horizon now
            # derived from the artifacts actually loaded, a 1d-only build would have
            # predicted 3d and labelled it 1d.
            horizon_day = self.model_registry.prediction_horizon
            if horizon_day is None:
                # `prediction_horizon` is None exactly when no artifact is loaded.
                # Reaching here in that state should be impossible — the guards above
                # refuse first — so this is a fail-closed backstop rather than a
                # branch with a known trigger. It matters because the property used
                # to substitute the smallest declared horizon instead of None, which
                # would have made this line predict at 1d and label the response 1d
                # with nothing loaded to predict with.
                raise PredictionUnavailable(
                    "Prediction unavailable: no model artifact is loaded, so there is "
                    "no horizon to predict at."
                )
            ml_start = time.time()
            predicted_price = self.predictor.predict(features, horizon=horizon_day)
            ml_inference_latency_hist.record(time.time() - ml_start)
            
            event_dispatcher.dispatch(DomainEvent(
                event_type="PredictionGenerated",
                metadata={"predicted_price": round(float(predicted_price), 2), "route": f"{origin}-{destination}"}
            ))

            # 6. Run Forecast Engine (delegates to injected ForecastEngine)
            forecast_start = time.time()
            snapshot_ctx = {
                "origin": origin,
                "destination": destination,
                "airline": resolved_airline,
                # `PricePredictor.forecast` rebuilds its own feature vector per
                # horizon out of this dict — it does not consume `features` — and the
                # point it publishes for `horizon_day` is what this response reports
                # (see the assignment below). So the curve path needs the same flight
                # identity the point path was given above, and had none of it:
                # without `flight_number` the five-part booking-curve key matched no
                # stored observation and all fourteen curve features were computed
                # over a window one observation long; without `departure_time`,
                # `hour_of_day` and `is_peak_hour` were NaN for a flight whose
                # departure time the provider did report; and `seats_available` was
                # hardcoded to `np.nan` inside `forecast()` regardless of what the
                # snapshot knew.
                "flight_number": resolved_flight_number,
                "departure_date": departure_date,
                "departure_time": departure_time_str,
                "seats_available": seats_available,
                # `else None`, not `else predicted_price`.
                #
                # When the live fare was unavailable this handed the model's own
                # step-5 output back as the market price, and `forecast()` reads this
                # key as the booking curve's anchor and appends it as the curve's
                # latest observation — so every movement feature was measured against
                # the model's own guess, the model was conditioned on itself, and the
                # "you would save ₹X against today's fare" line compared the model to
                # itself. Line 294 above already used None for the same quantity;
                # the two disagreed about what `current_price` means.
                #
                # None, and `forecast()` refuses with "not enough data yet" rather
                # than producing a curve anchored to a number nobody quoted.
                "current_price": quoted_fare_val if not math.isnan(quoted_fare_val) else None,
                "days_until_departure": features["days_until_dep"],
                "demand_score": np.nan,
                "seasonality_factor": np.nan
            }
            formatted_forecast = self.forecast_engine.run_forecast(snapshot_ctx, features)
            forecast_latency_hist.record(time.time() - forecast_start)
            
            # The published `predicted_price` is the forecast curve's own point at
            # the prediction horizon, so the headline number and the curve cannot
            # disagree. `horizon_day` is resolved above and reused here rather than
            # re-read, which is how the two came to be able to differ.
            #
            # This point is guaranteed to exist: `horizon_day` is the shortest
            # horizon with a loaded model and `forecast()` publishes a point for
            # every loaded horizon. If it is nonetheless absent, the curve is not the
            # curve this response claims to describe, and silently keeping the
            # step-5 number under the same label is the failure mode this refuses —
            # the two are different quantities (one prices a booking made today, the
            # other a booking made `horizon_day` days from now).
            target_point = next((f for f in formatted_forecast if f["day"] == horizon_day), None)
            if not target_point or "price" not in target_point:
                raise PredictionUnavailable(
                    f"Forecast published no point for horizon {horizon_day}d "
                    f"(points: {[f.get('day') for f in formatted_forecast]}), so there "
                    f"is no {horizon_day}d price to publish."
                )
            predicted_price = float(target_point["price"])

            # Format trend for event publisher
            trend, change_percent, prob_increase = self.formatter.calculate_trend([
                {"day": f["day"], "date": f["date"], "price": f["price"], "lower": f["lower"], "upper": f["upper"]}
                for f in formatted_forecast
            ])

            event_dispatcher.dispatch(DomainEvent(
                event_type="ForecastCompleted",
                metadata={"days": len(formatted_forecast), "trend": trend}
            ))

            # 7. Recommendation Engine (Booking decision delegates to injected RecommendationEngine)
            rec_start = time.time()
            current_lowest = quoted_fare_val if (not math.isnan(quoted_fare_val) and quoted_fare_val > 0) else None
            
            # This used to read:
            #
            #     model_acc = 95.0
            #     try:
            #         ...
            #         if isinstance(m_metrics, dict) and "accuracy" in m_metrics:
            #             acc_val = float(m_metrics["accuracy"])
            #             model_acc = acc_val * 100.0 if 0.0 < acc_val <= 1.0 else (
            #                 acc_val if acc_val > 1.0 else 95.0)
            #     except Exception:
            #         model_acc = 95.0
            #
            # Every exit that was not a successful read landed on 95.0, including
            # the bare `except`, and a recorded accuracy of exactly 0.0 also became
            # 95.0 through the final conditional. The published figure could
            # therefore be its highest possible value precisely when the model was
            # at its worst or unmeasured.
            #
            # None now means unmeasured, and the request is refused rather than
            # answered with an invented number.
            model_acc = resolve_published_accuracy(
                metrics_for_horizon(self.predictor, horizon_day)
            )
            if model_acc is None:
                raise PredictionUnavailable(
                    f"Prediction unavailable: no evaluation metrics are recorded for "
                    f"the {horizon_day}-day model, so its confidence cannot be "
                    f"reported. Train and accept a model for this horizon first."
                )

            formatted_decision = self.recommendation_engine.generate_recommendation(
                current_lowest=current_lowest,
                formatted_forecast=formatted_forecast,
                prediction_horizon=horizon_day,
                predicted_price=predicted_price,
                origin=origin,
                destination=destination,
                snapshot_quality=market_snapshot.snapshot_quality,
                model_accuracy=model_acc,
                is_live_market=is_live_avail
            )
            rec_latency_hist.record(time.time() - rec_start)
            
            event_dispatcher.dispatch(DomainEvent(
                event_type="RecommendationGenerated",
                metadata={"decision": formatted_decision["decision"], "confidence": formatted_decision["confidence"]}
            ))

            # 8. Observational Consistency Validator (Emits drift telemetry without modifying prediction)
            try:
                validator_res = self.consistency_validator.validate_consistency(
                    predicted_price=predicted_price,
                    market_snapshot=market_snapshot,
                    forecast=formatted_forecast,
                    route=f"{origin}-{destination}",
                )
                if not isinstance(validator_res, dict):
                    validator_res = {"anomalous": False, "reasons": []}
            except Exception as v_exc:
                logger.warning(f"Consistency validator notice: {v_exc}")
                validator_res = {"anomalous": False, "reasons": []}

            # Publish ForecastValidated event.
            #
            # The `metrics` key is gone: the validator used to return MAE, RMSE,
            # MAPE, bias and drift fixed at 0.0, and this event published that
            # perfect-accuracy block for every prediction. Forecast error is
            # measured after the horizon elapses — see `forecast_evaluator`.
            self.event_publisher.publish("ForecastValidated", {
                "predicted_price": predicted_price,
                "anomalous": validator_res.get("anomalous", False),
                "reasons": validator_res.get("reasons", []),
            })

            # The deviation was recorded here as `prediction_deviation_rupees` and
            # by the validator as `prediction_market_deviation_rupees` — the same
            # number under two metric names, and only the validator's carries the
            # route and provider labels. One quantity, one series.

            # 9. Schema Validation on outputs
            PredictionValidator.validate_outputs(predicted_price, formatted_decision["confidence"], formatted_forecast)

            # 10. Persist forecasts in ForecastStore
            try:
                import uuid
                from backend.services.forecast_store import forecast_store
                now_str = datetime.now(timezone.utc).isoformat()
                
                # Build metadata context recommendation representation
                #
                # These five keys are the booking-curve identity
                # (`booking_curve_definition.BOOKING_CURVE_KEYS`) and they are the
                # whole reason the row is worth storing: without them the forecast
                # cannot be matched to the fare that later realised, so no
                # out-of-sample error can ever be computed from it.
                rec_payload = {
                    "decision": formatted_decision["decision"],
                    "confidence": formatted_decision["confidence"],
                    "origin": origin,
                    "destination": destination,
                    "airline": resolved_airline,
                    # The per-flight component of the identity. This was
                    # `resolved_flight_number` until 2026-09-03, and before that
                    # `features.get("flight_number")` — the latter always absent
                    # because the flight number identifies the curve rather than
                    # being one of the model's features. The former is always None
                    # for a different reason: Google Flights does not publish a
                    # flight number, so there is nothing to resolve. Either way no
                    # stored forecast could be matched back to the flight it was
                    # about, and `forecast_evaluation_scheduler` refused every one.
                    #
                    # `departure_time_str` is the quoted flight's own scheduled
                    # departure, read out of the same snapshot entry as its fare,
                    # so it names the flight this forecast is about and not the
                    # route. It is null when the snapshot had no live entry for the
                    # carrier, and a forecast stored without it is correctly
                    # unevaluable rather than matched to a sibling departure.
                    "departure_time": departure_time_str,
                    # Retained for the record, not as identity: it is what a
                    # provider publishing flight numbers would populate, and its
                    # persistent emptiness is the finding.
                    "flight_number": resolved_flight_number,
                    # The departure date being forecast. It was not stored at all,
                    # which is why `forecast_evaluation_scheduler` matched outcomes
                    # on `departure_date = forecast_timestamp + horizon` — flights
                    # departing on the day the horizon elapsed, a different flight
                    # entirely. It had nothing else to match on.
                    "departure_date": departure_date,
                }
                
                for f in formatted_forecast:
                    forecast_store.save_forecast(
                        forecast_id=str(uuid.uuid4()),
                        prediction_timestamp=now_str,
                        horizon=f["day"],
                        predicted_price=f["price"],
                        model_version=self.model_registry.model_version,
                        dataset_version=self.model_registry.dataset_version,
                        recommendation=rec_payload
                    )
            except Exception as store_err:
                logger.warning(f"Failed to persist generated forecasts: {store_err}")

            predict_latency_hist.record(time.time() - start_time)

            # `is_live_avail` was established once, above, where the snapshot was
            # observed. It is not recomputed here.
            pred_mode = "live" if is_live_avail else "historical_only"
            prov_status = "ONLINE" if is_live_avail else "DEGRADED"

            def safe_float(val: float) -> Optional[float]:
                if val is None or math.isnan(val):
                    return None
                return round(float(val), 2)

            # `eff_quality` used to be `market_snapshot.snapshot_quality if
            # is_live_avail else 0.85`, and the assembler then re-derived liveness
            # for itself as `current_fare is not None and current_fare > 0`. Two
            # definitions of the same fact, disagreeing whenever a fare came from
            # recorded history with no live flights in the snapshot. The observed
            # quality is now passed through unmodified and liveness is stated once,
            # here, by the code that looked at the market.
            eff_quality = market_snapshot.snapshot_quality

            from backend.services.forecast.canonical_forecast_service import canonical_forecast_service
            from backend.mappers.forecast_mapper import ForecastMapper

            c_domain = canonical_forecast_service.build_canonical_forecast(
                formatted_forecast=formatted_forecast,
                current_fare=current_lowest,
                model_accuracy=model_acc,
                snapshot_quality=eff_quality,
                is_live_market=is_live_avail
            )
            canonical_dto = ForecastMapper.to_dto(c_domain)

            # The published figure and its breakdown are now one computation.
            #
            # This block used to be:
            #
            #     "confidence": formatted_decision["confidence"],
            #     "confidence_breakdown": {
            #         "model_validation_score": round(model_acc, 2),
            #         "market_data_quality": round(eff_quality, 2),
            #         "prediction_reliability": round(formatted_decision["confidence"], 2)
            #     },
            #
            # which re-derived the breakdown here from the raw inputs while the
            # total came from the recommendation engine and `c_domain` computed a
            # third copy. `market_data_quality` reported the raw snapshot quality
            # rather than the multiplier actually applied, so the parts did not
            # multiply out to the total. Mirroring `c_domain` means the numbers on
            # the wire are the ones the arithmetic was done with, and nothing here
            # calls round() on a value that is now legitimately None.
            rec_conf = formatted_decision.get("confidence")
            if rec_conf != c_domain.confidence_score:
                logger.warning(
                    "Confidence divergence: recommendation engine published %s, "
                    "canonical forecast published %s. Both read confidence_policy, "
                    "so this means they were handed different inputs.",
                    rec_conf, c_domain.confidence_score
                )

            return {
                "schema_version": "1.0.0",
                "api_version": "v1",
                "backend_version": "11.0.0",
                "prediction_version": "2.0.0",
                "predicted_price": round(float(predicted_price), 2),
                "canonical_forecast": canonical_dto,
                "current_market": {
                    "lowest_fare": safe_float(market_snapshot.lowest_fare),
                    "average_fare": safe_float(market_snapshot.average_fare),
                    "snapshot_timestamp": market_snapshot.retrieval_timestamp,
                    "provider": market_snapshot.provider
                },
                "forecast": formatted_forecast,
                "recommendation": formatted_decision,
                "optimal_booking": formatted_decision.get("optimal_booking"),
                "confidence": c_domain.confidence_score,
                "confidence_breakdown": dict(c_domain.confidence_breakdown),
                "search_metadata": {
                    "provider": market_snapshot.provider,
                    "retrieval_time": market_snapshot.retrieval_timestamp,
                    "search_latency": safe_float(market_snapshot.search_duration),
                    "flight_count": market_snapshot.total_live_flights,
                    # What was searched for. The response carried no route at all,
                    # so a client holding two predictions could not tell them
                    # apart, and `test_route_isolation` "checked" the route by
                    # reading a key that has never existed and falling back to the
                    # literal it was asserting — a test that could not fail.
                    "origin": origin,
                    "destination": destination,
                    "departure_date": departure_date,
                    "market_freshness": safe_float(market_snapshot.snapshot_age),
                    "cache_hit": market_snapshot.cache_hit,
                    "cache_miss": market_snapshot.cache_miss,
                    "refresh_reason": market_snapshot.refresh_reason,
                    "snapshot_age": safe_float(market_snapshot.snapshot_age),
                    "prediction_mode": pred_mode,
                    "provider_status": prov_status,
                    "market_snapshot_available": is_live_avail
                },
                "market_snapshot": {
                    "total_live_flights": market_snapshot.total_live_flights,
                    "average_fare": safe_float(market_snapshot.average_fare),
                    "lowest_fare": safe_float(market_snapshot.lowest_fare),
                    "highest_fare": safe_float(market_snapshot.highest_fare),
                    "connecting_flight_count": market_snapshot.connecting_flight_count,
                    "direct_flight_count": market_snapshot.direct_flight_count
                },
                # Which flight `predicted_price` is about. `current_market.lowest_fare`
                # is the market's minimum and was the only fare on the wire, so a
                # caller who named a carrier had no way to see that the forecast was
                # computed from a different flight's fare — and no way to see that
                # an unnamed flight means the model had none of its price history.
                "quoted_flight": {
                    "airline": resolved_airline,
                    "flight_number": resolved_flight_number,
                    "fare": safe_float(quoted_fare_val),
                    "has_booking_curve": bool(resolved_airline and resolved_flight_number)
                },
                "prediction_horizon": self.model_registry.prediction_horizon
            }

        except Exception as e:
            prediction_failures_counter.add(1, {"error": str(type(e).__name__)})
            logger.error(f"Prediction Service execution failed: {e}")
            raise e

prediction_service = PredictionService()
