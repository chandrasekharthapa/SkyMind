/**
 * SkyMind — Shared TypeScript Types (2026 Production)
 * Mirrors Pydantic V2 models in FastAPI backend exactly.
 * All dates use ISO-8601 strings.
 */

// ─── Enums / Literals ────────────────────────────────────────────────
export type CabinClass = "ECONOMY" | "PREMIUM_ECONOMY" | "BUSINESS" | "FIRST";
export type BookingStatus = "PENDING" | "CONFIRMED" | "CANCELLED" | "REFUND_PENDING";
export type PaymentStatus = "UNPAID" | "PAID" | "REFUND_PENDING" | "REFUNDED" | "VOID";
export type PassengerType = "ADULT" | "CHILD" | "INFANT";
export type Trend = "RISING" | "FALLING" | "STABLE";
export type Recommendation = "BOOK_NOW" | "WAIT" | "MONITOR";
export type MarketStatus = "VOLATILE" | "STABLE";
export type NotificationChannel = "EMAIL" | "SMS" | "WHATSAPP";
export type LoyaltyTier = "BLUE" | "SILVER" | "GOLD" | "PLATINUM";

// ─── Canonical Forecast Contracts ────────────────────────────────────
export interface TimelinePointDTO {
  horizon_days: number;
  booking_date: string;
  predicted_price: number;
  lower_bound: number;
  upper_bound: number;
  /**
   * Null when no training run recorded a metric for this horizon, and null on the
   * day-0 point because an observed fare is a fare rather than a prediction.
   * "Unmeasured" is a different claim from "measured low", so render the two
   * differently — `?? 0` would publish a 0% for a figure that does not exist.
   */
  confidence_score: number | null;
  is_optimal?: boolean;
  metadata?: Record<string, any>;
}

export interface ForecastDiagnosticsDTO {
  invariants_passed: boolean;
  violations: string[];
  execution_time_ms: number;
}

export interface CanonicalForecastDTO {
  current_fare: number | null;
  expected_minimum_fare: number;
  optimal_booking_horizon: number;
  optimal_booking_date: string;
  recommendation_decision: "BOOK_NOW" | "WAIT" | "MONITOR";
  recommendation_reasons: string[];
  calculated_savings: number;
  percentage_savings: number;
  /** Null when the loaded model records no evaluation metric for any horizon. */
  confidence_score: number | null;
  confidence_breakdown: Record<string, number | null>;
  timeline: TimelinePointDTO[];
  diagnostics: ForecastDiagnosticsDTO;
  forecast_metadata?: Record<string, any>;
  is_valid: boolean;
}

// ─── Airport ─────────────────────────────────────────────────────────
export interface Airport {
  iata_code: string;
  icao_code?: string | null;
  name: string;
  city: string;
  state?: string | null;
  region?: string | null;
  country: string;
  country_code: string;
  latitude?: number | null;
  longitude?: number | null;
  timezone?: string;
  is_domestic: boolean;
  is_international: boolean;
  is_active: boolean;
}

export interface AirportSuggestion {
  iata: string;
  label: string;
  city: string;
  name: string;
  airport: string;
  country: string;
  state?: string | null;
}

// ─── Flight Search ────────────────────────────────────────────────────
export interface FlightSegment {
  flight_number: string | null;
  airline_code: string | null;
  airline_name: string | null;
  airline_logo: string;
  airline_logo_rect: string;
  aircraft?: string;
  origin: string;
  destination: string;
  departure_time: string | null;
  arrival_time: string | null;
  duration: string | null;
  cabin: CabinClass;
  stops: number;
  terminal_departure?: string | null;
  terminal_arrival?: string | null;
}

export interface FlightItinerary {
  duration: string | null;
  segments: FlightSegment[];
}

export interface FlightPrice {
  total: number;
  base?: number;
  // Null when the provider quoted a fare without a readable unit. Typed `string`
  // until AUDIT-FIXES.md §48, which was a lie about the wire format in both
  // directions: the backend defaulted the field to "INR" so the type held, and
  // the UI ignored it and printed ₹ regardless.
  currency: string | null;
  fees?: unknown[];
  grand_total?: number;
}

export interface FlightOffer {
  id: string;
  source: string;
  price: FlightPrice;
  itineraries: FlightItinerary[];
  validating_airlines?: string[];
  primary_airline: string | null;
  primary_airline_name: string | null;
  primary_airline_logo: string;
  flight_number?: string | null;
  origin?: string;
  destination?: string;
  provenance?: string;
  traveler_pricings?: unknown[];
  last_ticketing_date?: string | null;
  seats_available?: number | null;
  instant_ticketing?: boolean;
  // ML enrichment fields. Every one is optional because every one is now
  // genuinely absent when no model spoke: `to_presentation` no longer defaults
  // `ai_price` to the listed fare, nor `trend`/`decision` to STABLE/FAIR.
  // `ml_available` is the field to branch on — `ai_price === undefined` and
  // `ml_available === false` mean the same thing, but only one of them says so.
  ml_available?: boolean;
  ai_price?: number;
  trend?: string;
  recommendation?: string;
  decision?: string;
  advice?: string;
  predicted_price?: number;
  trend_direction?: string;
  prediction_confidence?: string;
}

// ─── Prediction · POST /api/v1/predict ───────────────────────────────
// Mirrors backend/services/prediction_presentation.py, which is the
// response_model on the route. Anything the service returns that is absent
// from that model is stripped before it reaches the browser — noted below.

export interface PredictRequest {
  origin: string;
  destination: string;
  /** Optional: the client sends "" when omitted. Backend expects YYYY-MM-DD. */
  departure_date?: string;
  airline_code?: string;
}

/**
 * The `recommendation` object on a prediction. Distinct from `Recommendation`,
 * which is the string union of its `decision` values.
 */
export interface RecommendationDetail {
  decision: Recommendation;
  reasons: string[];
  confidence?: number | null;
}

/** Minimal chart point: the fields PriceChart actually plots. */
export interface ForecastPoint {
  day: number;
  date: string;
  price: number;
  lower: number;
  upper: number;
  is_optimal?: boolean;
}

/** A full forecast row as returned by /predict and normalized in lib/api.ts. */
export interface ForecastDay extends ForecastPoint {
  forecast_price: number;
  forecast_timestamp: string;
  prediction_horizon: number;
  confidence: number;
  model_version: string;
  feature_schema_version: string;
}

export interface CurrentMarket {
  lowest_fare: number | null;
  average_fare: number | null;
  snapshot_timestamp: string;
  provider: string;
}

export interface ConfidenceBreakdown {
  model_validation_score: number;
  market_data_quality: number;
  prediction_reliability: number;
}

export interface SearchMetadata {
  provider: string;
  retrieval_time: string;
  search_latency: number;
  flight_count: number;
  /**
   * The route and date the prediction is for. Optional because the backend
   * declares all three `Optional[str]`, not because the mapper skips them —
   * lib/api.ts#predictPrice populates each one. Two predictions held side by
   * side were previously indistinguishable without them.
   */
  origin?: string | null;
  destination?: string | null;
  departure_date?: string | null;
  market_freshness: number;
  cache_hit: boolean;
  cache_miss: boolean;
  refresh_reason: string;
  snapshot_age: number;
  /** "live" | "historical_only" */
  prediction_mode: string;
  /** "ONLINE" | "DEGRADED" | "OFFLINE" */
  provider_status: string;
  market_snapshot_available: boolean;
}

export interface MarketSnapshotSummary {
  total_live_flights: number;
  average_fare: number | null;
  lowest_fare: number | null;
  highest_fare: number | null;
  connecting_flight_count: number;
  direct_flight_count: number;
}

/**
 * The single flight a prediction is about. `current_market.lowest_fare` is the
 * whole market's minimum, so without this a caller who named an airline could
 * not tell which flight `predicted_price` referred to. `fare` is the number the
 * forecast was computed from; it equals `lowest_fare` only when no airline was
 * named.
 *
 * `has_booking_curve: false` means the flight is not identified well enough to
 * have a price history, so the model saw none of this flight's own past fares.
 * Read it before presenting the forecast as flight-specific.
 */
export interface QuotedFlight {
  airline?: string | null;
  flight_number?: string | null;
  fare?: number | null;
  has_booking_curve: boolean;
}

/**
 * Read by DecisionCard and app/predict. NOT part of the /predict response
 * model, so it is stripped server-side and is never populated by
 * lib/api.ts#predictPrice — every consumer must supply a fallback.
 */
export interface OptimalBooking {
  booking_date: string;
  prediction_horizon: number;
  expected_price: number;
  estimated_savings: number;
  percentage_savings: number;
  /** Free-form label; call sites use both "BUY NOW" and the Recommendation values. */
  recommendation: string;
}

export interface PredictionResult {
  predicted_price: number;
  confidence: number;
  forecast: ForecastDay[];
  recommendation: RecommendationDetail;
  current_market: CurrentMarket;
  search_metadata: SearchMetadata;
  market_snapshot: MarketSnapshotSummary;
  /**
   * Unlike the two stripped fields below, this one IS on the response model and
   * IS populated by lib/api.ts#predictPrice. Null when the service could not
   * identify a single flight for the request.
   */
  quoted_flight?: QuotedFlight | null;
  prediction_horizon: number;
  confidence_breakdown?: ConfidenceBreakdown;
  /** Stripped by the response model; see OptimalBooking. */
  optimal_booking?: OptimalBooking;
  /** Also stripped by the response model — the canonical-forecast UI is unreachable today. */
  canonical_forecast?: CanonicalForecastDTO | null;
}

// ─── Flight search · POST /live-search ────────────────────────────────
export interface FlightSearchParams {
  origin: string;
  destination: string;
  departure_date: string;
  adults: number;
  children: number;
  infants: number;
  cabin_class: CabinClass;
  /** Only sent for round trips. */
  return_date?: string;
  currency?: string;
}

export interface FlightSearchResponse {
  flights: FlightOffer[];
  count: number;
  origin_iata: string;
  destination_iata: string;
  data_source: string;
  search_params: {
    origin: string;
    destination: string;
    departure_date: string;
  };
}

// ─── Price alerts · /alerts ───────────────────────────────────────────
export interface SetAlertRequest {
  origin: string;
  destination: string;
  target_price: number;
  departure_date?: string;
  user_label?: string;
  /**
   * `user_id` was here and is gone for the same reason it left
   * `CreateBookingRequest`: the alert's owner is the bearer token's subject. No
   * caller ever set it, which is what made the field harmful — the backend wrote
   * `user_id` only when the body supplied it, so every alert was stored ownerless
   * and neither the list nor the delete endpoint could see it again.
   */
  currency?: string;
  cabin_class?: string;
  email?: string;
  phone?: string;
  notify_email?: string;
  notify_phone?: string;
  notify_sms?: boolean;
  notify_whatsapp?: boolean;
}

export interface SetAlertResponse {
  success: boolean;
  alert_id: string;
  message: string;
}

export interface AlertRecord {
  id: string;
  origin: string;
  destination: string;
  target_price: number;
  created_at: string;
  /** Backend sends bool(triggered_count) — a flag, not a count. */
  triggered: boolean;
  departure_date?: string;
  user_label?: string;
  current_price?: number | null;
  savings?: number | null;
}

export interface CheckAlertsResponse {
  alerts: AlertRecord[];
  triggered: AlertRecord[];
  triggered_count: number;
  count?: number;
}

// ─── Booking · /booking ───────────────────────────────────────────────
export interface Passenger {
  type: PassengerType;
  first_name: string;
  last_name: string;
  title?: string | null;
  date_of_birth?: string | null;
  gender?: string | null;
  nationality?: string | null;
  passport_number?: string | null;
  passport_expiry?: string | null;
  passport_country?: string | null;
  aadhaar_number?: string | null;
  seat_number?: string | null;
  seat_preference?: string | null;
  /** Form values are VEG | NON_VEG | VEGAN but arrive as a plain string. */
  meal_preference?: string;
  baggage_allowance?: number;
  ff_number?: string | null;
  ff_airline?: string | null;
  special_request?: string | null;
}

export interface CreateBookingRequest {
  flight_offer_id: string;
  flight_data: FlightOffer | Record<string, unknown>;
  passengers: Passenger[];
  contact_email: string;
  contact_phone: string;
  cabin_class?: CabinClass | string;
  currency?: string;
  /**
   * Removed, not renamed: booking ownership is derived from the bearer token on the
   * server. The field used to be written straight into `bookings.user_id`, so a
   * request body could claim any account. It is not part of the contract any more —
   * sign in and the token carries the identity.
   */
  coupon_code?: string | null;
}

export interface CreateBookingResponse {
  success: boolean;
  booking_id: string;
  booking_reference: string;
  total_price: number;
  message: string;
}

/**
 * A booking as the checkout page sees it: the create-booking response spread
 * together with locally held form data, persisted to sessionStorage. Every
 * field is optional because the page reads it back after a JSON round-trip
 * with no runtime validation.
 */
export interface Booking {
  id?: string;
  booking_reference?: string;
  booking_id?: string;
  status?: BookingStatus | string;
  payment_status?: PaymentStatus | string;
  total_price?: number;
  currency?: string;
  cabin_class?: CabinClass | string;
  num_passengers?: number;
  contact_email?: string | null;
  contact_phone?: string | null;
  passengers?: Passenger[];
  flight_offer_data?: Record<string, unknown> | null;
  /** Written by the client only — not a column on public.bookings. */
  origin_code?: string | null;
  destination_code?: string | null;
  departure_date?: string | null;
  pnr?: string | null;
  payment_id?: string | null;
  razorpay_order_id?: string | null;
  created_at?: string;
  updated_at?: string;
}

// ─── Payment · /payment (Razorpay) ────────────────────────────────────
export interface CreateOrderRequest {
  amount: number;
  booking_id: string;
  booking_reference: string;
  currency?: string;
}

/**
 * Two server shapes share this endpoint: a created order, and an
 * already-paid short-circuit that returns only { message, order_id: null }.
 */
export interface CreateOrderResponse {
  order_id: string | null;
  amount?: number;
  currency?: string;
  /** Razorpay key id. The JSON field is "key", not "key_id". */
  key?: string;
  message?: string;
}

export interface VerifyPaymentRequest {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
  booking_id: string;
}

export interface VerifyPaymentResponse {
  success: boolean;
  /** Absent on the idempotent-replay path. */
  payment_id?: string;
  message?: string;
}

// ─── Error envelope ───────────────────────────────────────────────────
// Every backend error goes through the handlers in backend/main.py and uses
// this shape — not FastAPI's default { detail: ... }.
export interface ApiErrorEnvelope {
  success: false;
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}

