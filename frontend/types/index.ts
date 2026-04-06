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
  airport: string;
  country: string;
  state?: string | null;
}

// ─── Flight Search ────────────────────────────────────────────────────
export interface FlightSegment {
  flight_number: string;
  airline_code: string;
  airline_name: string;
  airline_logo: string;
  airline_logo_rect: string;
  aircraft?: string;
  origin: string;
  destination: string;
  departure_time: string;
  arrival_time: string;
  duration: string;
  cabin: CabinClass;
  stops: number;
  terminal_departure?: string | null;
  terminal_arrival?: string | null;
}

export interface FlightItinerary {
  duration: string;
  segments: FlightSegment[];
}

export interface FlightPrice {
  total: number;
  base?: number;
  currency: string;
  fees?: unknown[];
  grand_total?: number;
}

export interface FlightOffer {
  id: string;
  source: string;
  price: FlightPrice;
  itineraries: FlightItinerary[];
  validating_airlines?: string[];
  primary_airline: string;
  primary_airline_name: string;
  primary_airline_logo: string;
  traveler_pricings?: unknown[];
  last_ticketing_date?: string | null;
  seats_available?: number | null;
  instant_ticketing?: boolean;
  // ML enrichment fields
  ai_price?: number;
  trend?: string;
  recommendation?: string;
  decision?: string;
  advice?: string;
  predicted_price?: number;
  trend_direction?: string;
  prediction_confidence?: string;
}

export interface FlightSearchParams {
  origin: string;
  destination: string;
  departure_date: string;
  return_date?: string;
  adults?: number;
  cabin_class?: CabinClass;
  currency?: string;
  max_results?: number;
}

export interface FlightSearchResponse {
  flights: FlightOffer[];
  count: number;
  origin_iata: string;
  destination_iata: string;
  data_source?: string;
  search_params?: Record<string, unknown>;
}

// ─── Price Prediction (2026 — matches POST /predict response) ─────────
export interface ForecastPoint {
  day: number;
  date: string;
  price: number;
  lower: number;
  upper: number;
}

/**
 * The backend /predict endpoint returns this shape directly (flat, no wrapper).
 * The /ai/price GET endpoint wraps inside { status, data: {...} }.
 */
export interface PredictionResult {
  predicted_price: number;
  forecast: ForecastPoint[];
  trend: Trend;
  probability_increase: number;
  confidence: number;
  recommendation: Recommendation;
  reason: string;
  expected_change_percent: number;
}

export interface PredictRequest {
  origin: string;
  destination: string;
  departure_date?: string;
}

// ─── Booking ──────────────────────────────────────────────────────────
export interface Passenger {
  type: PassengerType;
  title?: string;
  first_name: string;
  last_name: string;
  date_of_birth?: string | null;
  gender?: string | null;
  nationality?: string;
  passport_number?: string | null;
  passport_expiry?: string | null;
  passport_country?: string;
  aadhaar_number?: string | null;
  seat_number?: string | null;
  seat_preference?: string;
  meal_preference?: string;
  baggage_allowance?: number;
  ff_number?: string | null;
  ff_airline?: string | null;
  special_request?: string | null;
}

export interface CreateBookingRequest {
  flight_offer_id: string;
  flight_data: FlightOffer;
  passengers: Passenger[];
  contact_email: string;
  contact_phone: string;
  cabin_class?: CabinClass;
  currency?: string;
  user_id?: string | null;
  coupon_code?: string | null;
}

export interface CreateBookingResponse {
  success: boolean;
  booking_id: string;
  booking_reference: string;
  total_price: number;
  message: string;
}

export interface Booking {
  id: string;
  booking_reference: string;
  pnr?: string | null;
  status: BookingStatus;
  payment_status: PaymentStatus;
  total_price: number;
  base_fare?: number;
  taxes?: number;
  discount_amount?: number;
  currency: string;
  cabin_class: CabinClass;
  num_passengers: number;
  contact_email: string;
  contact_phone?: string;
  confirmation_sent?: boolean;
  checkin_notif_sent?: boolean;
  created_at: string;
  cancelled_at?: string | null;
  refund_amount?: number | null;
  refund_status?: string | null;
  flight_offer_data?: FlightOffer | null;
  origin_code?: string;
  destination_code?: string;
}

// ─── Payment ──────────────────────────────────────────────────────────
export interface CreateOrderRequest {
  amount: number;
  currency?: string;
  booking_id: string;
  booking_reference: string;
}

export interface CreateOrderResponse {
  order_id: string;
  amount: number;
  currency: string;
  key: string;
}

export interface VerifyPaymentRequest {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
  booking_id: string;
}

export interface VerifyPaymentResponse {
  success: boolean;
  payment_id: string;
  message: string;
}

// ─── Price Alerts ─────────────────────────────────────────────────────
export interface AlertRecord {
  id: string;
  origin: string;
  destination: string;
  target_price: number;
  departure_date?: string;
  user_label?: string;
  created_at: string;
  triggered: boolean;
  current_price?: number;
  savings?: number;
  trend?: Trend;
  recommendation?: Recommendation;
}

export interface SetAlertRequest {
  origin: string;
  destination: string;
  target_price: number;
  departure_date?: string;
  user_label?: string;
  user_id?: string;
  notify_email?: string;
  notify_phone?: string;
}

export interface SetAlertResponse {
  success: boolean;
  alert_id: string;
  message: string;
}

export interface CheckAlertsResponse {
  alerts: AlertRecord[];
  triggered: AlertRecord[];
  triggered_count: number;
}

// ─── User / Profile ───────────────────────────────────────────────────
export interface UserProfile {
  id: string;
  auth_user_id?: string | null;
  email: string;
  full_name?: string | null;
  display_name?: string | null;
  phone?: string | null;
  phone_verified?: boolean;
  email_verified?: boolean;
  date_of_birth?: string | null;
  gender?: string | null;
  nationality?: string;
  preferred_currency?: string;
  preferred_cabin?: CabinClass;
  avatar_url?: string | null;
  notify_email?: boolean;
  notify_sms?: boolean;
  notify_whatsapp?: boolean;
  preferred_airlines?: string[];
  preferred_seat?: string;
  meal_preference?: string;
  skymind_points?: number;
  tier?: LoyaltyTier;
  total_bookings?: number;
  total_spent?: number;
  last_login?: string | null;
  created_at?: string;
  updated_at?: string;
}

// ─── API helpers ──────────────────────────────────────────────────────
export interface ApiErrorShape {
  detail: string;
  status?: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}
