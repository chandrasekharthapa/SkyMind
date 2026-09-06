/**
 * SkyMind — Unified API Client (2026 Production)
 *
 * Data Contract (POST /predict response shape from Python):
 * {
 *   status: "success",
 *   data: {
 *     origin: string,
 *     destination: string,
 *     predicted_price: number,
 *     intelligence: {
 *       confidence: number,        // 0–100 (we normalize to 0–1)
 *       prob_increase: number,     // 0–1
 *       recommendation: string,    // "BUY_NOW" | "WAIT" | "OPTIMIZED PRICE" | "NEUTRAL"
 *       market_status: string,     // "VOLATILE" | "STABLE"
 *       days_to_go: number,
 *     },
 *     meta: {
 *       peak_season: boolean,
 *       weekend: boolean,
 *       timestamp: string,
 *     },
 *     forecast?: ForecastPoint[],  // only present when route data exists
 *   }
 * }
 *
 * ALL data transformation lives here. Hooks are typed pass-throughs only.
 */

import type {
  AirportSuggestion,
  FlightSearchParams,
  FlightSearchResponse,
  PredictRequest,
  PredictionResult,
  SetAlertRequest,
  SetAlertResponse,
  CheckAlertsResponse,
  CreateBookingRequest,
  CreateBookingResponse,
  CreateOrderRequest,
  CreateOrderResponse,
  VerifyPaymentRequest,
  VerifyPaymentResponse,
  FlightOffer,
  FlightItinerary,
  ForecastPoint,
  Trend,
  Recommendation,
  ForecastDay,
  RecommendationDetail,
} from "@/types";
import { supabase } from "@/lib/supabase";

// Re-export for convenience
export type {
  FlightSearchParams,
  FlightSearchResponse,
  FlightOffer,
  ForecastPoint,
  Trend,
  Recommendation,
  PredictRequest,
  PredictionResult,
  SetAlertRequest,
  SetAlertResponse,
  CheckAlertsResponse,
  CreateBookingRequest,
  CreateBookingResponse,
  CreateOrderRequest,
  CreateOrderResponse,
  VerifyPaymentRequest,
  VerifyPaymentResponse,
  ForecastDay,
  RecommendationDetail,
};
export type AirportResult = {
  iata: string;
  city: string;
  name: string;
  country: string;
};

// ─── Config ───────────────────────────────────────────────────────────
export function getApiBase(): string {
  const url =
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://127.0.0.1:8000";
  return url.endsWith("/") ? url.slice(0, -1) : url;
}

// ─── Error class ──────────────────────────────────────────────────────
export class ApiError extends Error {
  constructor(
    message: string,
    public readonly statusCode?: number,
    public readonly detail?: unknown
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ─── Safe numeric parser ──────────────────────────────────────────────
/**
 * Safely converts any value to a JS number.
 * Handles: Python Decimal strings "5183.35", percentage strings "87%",
 * null/undefined → 0, NaN → 0.
 */
export function safePrice(val: unknown): number {
  if (val === null || val === undefined) return 0;
  if (typeof val === "number") return isNaN(val) ? 0 : val;
  if (typeof val === "string") {
    const n = parseFloat(val.replace(/,/g, "").replace(/%/g, "").trim());
    return isNaN(n) ? 0 : n;
  }
  return 0;
}

// ─── Core fetch helper ────────────────────────────────────────────────
/**
 * Returns the current Supabase access token, or null when nobody is signed in.
 *
 * No call from this client used to carry an Authorization header. Eleven backend
 * endpoints across four routers hang off `Depends(get_current_user)`, so every one
 * of them was unreachable from the app. Reachability is worth stating precisely:
 * this module exports `setAlert`/`checkAlerts`/`deleteAlert` and `hooks/useAlerts`
 * calls them, but no page imports that hook, so the alert endpoints are reached
 * only by a caller written in future. Sending the header is additive: the backend's
 * CORS layer already lists `Authorization` in `allow_headers`, and an endpoint that
 * does not read it is unaffected.
 */
async function authHeader(): Promise<Record<string, string>> {
  try {
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    return token ? { Authorization: `Bearer ${token}` } : {};
  } catch {
    // Never let an auth-store hiccup take down an anonymous request that would
    // otherwise have succeeded.
    return {};
  }
}

async function apiRequest<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const base = getApiBase();
  const url = path.startsWith("http") ? path : `${base}${path}`;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(await authHeader()),
    ...(options.headers as Record<string, string> | undefined),
  };

  let res: Response;
  try {
    res = await fetch(url, { ...options, headers });
  } catch {
    throw new ApiError(
      `Network error — cannot reach API at ${base}. Make sure the backend is running.`,
      0
    );
  }

  if (!res.ok) {
    let message = `Request failed — HTTP ${res.status}`;
    let detail: unknown;
    try {
      const body = await res.json();
      // The backend's exception handlers emit
      // `{success:false, error:{code,message,details}}` — see the three
      // `@app.exception_handler` blocks in backend/main.py. This read only
      // `body?.detail`, which that shape does not have, so every backend error
      // reached the user as the bare "Request failed — HTTP 500" fallback and the
      // message the API had gone to the trouble of writing was discarded.
      // `body?.detail` is kept second because a FastAPI `HTTPException` raised
      // before those handlers run still uses it.
      message = body?.error?.message ?? body?.detail ?? message;
      detail = body;
    } catch {
      // A non-JSON body. Rejected CORS preflights land here: Starlette answers
      // with `text/plain`, and the browser blocks the response from JS anyway.
    }
    throw new ApiError(message, res.status, detail);
  }

  return res.json() as Promise<T>;
}

// ─── City → IATA resolver ─────────────────────────────────────────────
const CITY_TO_IATA: Record<string, string> = {
  delhi: "DEL",
  "new delhi": "DEL",
  mumbai: "BOM",
  bombay: "BOM",
  bangalore: "BLR",
  bengaluru: "BLR",
  hyderabad: "HYD",
  chennai: "MAA",
  madras: "MAA",
  kolkata: "CCU",
  calcutta: "CCU",
  kochi: "COK",
  cochin: "COK",
  goa: "GOI",
  ahmedabad: "AMD",
  jaipur: "JAI",
  lucknow: "LKO",
  pune: "PNQ",
  amritsar: "ATQ",
  guwahati: "GAU",
  varanasi: "VNS",
  patna: "PAT",
  bhubaneswar: "BBI",
  ranchi: "IXR",
  srinagar: "SXR",
  jammu: "IXJ",
  leh: "IXL",
  "port blair": "IXZ",
  mangalore: "IXE",
  coimbatore: "CJB",
  madurai: "IXM",
  tiruchirappalli: "TRZ",
  trichy: "TRZ",
  thiruvananthapuram: "TRV",
  trivandrum: "TRV",
  kozhikode: "CCJ",
  calicut: "CCJ",
  indore: "IDR",
  bhopal: "BHO",
  chandigarh: "IXC",
  dubai: "DXB",
  london: "LHR",
  singapore: "SIN",
  doha: "DOH",
  bangkok: "BKK",
  istanbul: "IST",
  tokyo: "NRT",
  "abu dhabi": "AUH",
  "kuala lumpur": "KUL",
  "new york": "JFK",
};

export function resolveCityToIATA(input: string): string {
  const trimmed = input.trim();
  if (!trimmed) return "";

  // 1. Check if input is already an IATA code (3 letters)
  if (/^[A-Z]{3}$/i.test(trimmed)) return trimmed.toUpperCase();

  // 2. Check for "City Name (IATA)" pattern
  const match = trimmed.match(/\(([^)]+)\)/);
  if (match && match[1].length === 3) return match[1].toUpperCase();

  // 3. Map city name to IATA
  const lower = trimmed.toLowerCase();
  return CITY_TO_IATA[lower] ?? trimmed.toUpperCase().substring(0, 3);
}

// ─── Forecast normalization ───────────────────────────────────────────
function normalizeForecast(raw: any[]): ForecastDay[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((p) => ({
    day: Number(p.day || 0),
    date: String(p.date || ""),
    price: safePrice(p.price),
    lower: safePrice(p.lower),
    upper: safePrice(p.upper),
    forecast_price: safePrice(p.forecast_price),
    forecast_timestamp: String(p.forecast_timestamp || ""),
    prediction_horizon: Number(p.prediction_horizon || 0),
    confidence: safePrice(p.confidence),
    model_version: String(p.model_version || ""),
    feature_schema_version: String(p.feature_schema_version || "")
  }));
}

// ─── Trend derivation ─────────────────────────────────────────────────
/**
 * The prediction endpoint has no `trend` field — PredictionResponse in
 * backend/services/prediction_presentation.py does not define one, so nothing
 * the server sends can populate it. The displayed trend is therefore derived
 * from `recommendation.decision`, the only directional signal the endpoint
 * returns. Kept here as one definition so separate pages cannot disagree
 * about what the same prediction means.
 */
export function trendFromDecision(decision?: string | null): Trend {
  if (decision === "BOOK_NOW") return "RISING";
  if (decision === "WAIT") return "FALLING";
  return "STABLE";
}

// ─── Price Prediction (POST /predict) ────────────────────────────────
/**
 * This is the SINGLE source of truth for mapping the backend response.
 * The hook (usePrediction.ts) calls this and gets a fully-typed PredictionResult.
 * No mapping logic exists anywhere else.
 */
export async function predictPrice(req: PredictRequest): Promise<PredictionResult> {
  const d = await apiRequest<any>("/api/v1/predict", {
    method: "POST",
    body: JSON.stringify({
      origin: resolveCityToIATA(req.origin),
      destination: resolveCityToIATA(req.destination),
      departure_date: req.departure_date ?? "",
    }),
  });

  return {
    predicted_price: safePrice(d?.predicted_price),
    current_market: {
      lowest_fare: d?.current_market?.lowest_fare != null ? safePrice(d.current_market.lowest_fare) : null,
      average_fare: d?.current_market?.average_fare != null ? safePrice(d.current_market.average_fare) : null,
      snapshot_timestamp: String(d?.current_market?.snapshot_timestamp || ""),
      provider: String(d?.current_market?.provider || ""),
    },
    forecast: normalizeForecast(d?.forecast),
    recommendation: {
      decision: d?.recommendation?.decision || "MONITOR",
      reasons: Array.isArray(d?.recommendation?.reasons) ? d.recommendation.reasons : [],
      confidence: d?.recommendation?.confidence != null ? safePrice(d.recommendation.confidence) : null,
    },
    confidence: safePrice(d?.confidence),
    confidence_breakdown: d?.confidence_breakdown ? {
      model_validation_score: safePrice(d.confidence_breakdown.model_validation_score),
      market_data_quality: safePrice(d.confidence_breakdown.market_data_quality),
      prediction_reliability: safePrice(d.confidence_breakdown.prediction_reliability),
    } : undefined,
    search_metadata: {
      provider: String(d?.search_metadata?.provider || ""),
      retrieval_time: String(d?.search_metadata?.retrieval_time || ""),
      search_latency: safePrice(d?.search_metadata?.search_latency),
      flight_count: Number(d?.search_metadata?.flight_count || 0),
      // The route and date this prediction is for. Null-preserving on purpose:
      // `String(x || "")` would report an absent origin as the empty string,
      // which reads as a route the server named rather than as one it did not.
      origin: d?.search_metadata?.origin != null ? String(d.search_metadata.origin) : null,
      destination: d?.search_metadata?.destination != null ? String(d.search_metadata.destination) : null,
      departure_date:
        d?.search_metadata?.departure_date != null ? String(d.search_metadata.departure_date) : null,
      market_freshness: safePrice(d?.search_metadata?.market_freshness),
      cache_hit: Boolean(d?.search_metadata?.cache_hit),
      cache_miss: Boolean(d?.search_metadata?.cache_miss),
      refresh_reason: String(d?.search_metadata?.refresh_reason || ""),
      snapshot_age: safePrice(d?.snapshot_age || d?.search_metadata?.snapshot_age),
      // These three used to assume the happy path when the field was absent:
      // an omitted prediction_mode became "live", an omitted provider_status
      // became "ONLINE", and an omitted market_snapshot_available became true,
      // which suppressed the degraded-provider banner. Absent now reads as
      // unknown, and the banner shows until the backend says otherwise.
      prediction_mode: String(d?.search_metadata?.prediction_mode || "unknown"),
      provider_status: String(d?.search_metadata?.provider_status || "UNKNOWN"),
      market_snapshot_available: Boolean(d?.search_metadata?.market_snapshot_available ?? false)
    },
    market_snapshot: {
      total_live_flights: Number(d?.market_snapshot?.total_live_flights || 0),
      average_fare: d?.market_snapshot?.average_fare != null ? safePrice(d.market_snapshot.average_fare) : null,
      lowest_fare: d?.market_snapshot?.lowest_fare != null ? safePrice(d.market_snapshot.lowest_fare) : null,
      highest_fare: d?.market_snapshot?.highest_fare != null ? safePrice(d.market_snapshot.highest_fare) : null,
      connecting_flight_count: Number(d?.market_snapshot?.connecting_flight_count || 0),
      direct_flight_count: Number(d?.market_snapshot?.direct_flight_count || 0),
    },
    // The one flight the forecast was computed from. `current_market.lowest_fare`
    // is the market minimum, so without this a caller who named an airline could
    // not tell which flight `predicted_price` describes. `has_booking_curve`
    // defaults false — absent must not read as "this flight has price history".
    quoted_flight: d?.quoted_flight
      ? {
          airline: d.quoted_flight.airline != null ? String(d.quoted_flight.airline) : null,
          flight_number:
            d.quoted_flight.flight_number != null ? String(d.quoted_flight.flight_number) : null,
          fare: d.quoted_flight.fare != null ? safePrice(d.quoted_flight.fare) : null,
          has_booking_curve: Boolean(d.quoted_flight.has_booking_curve),
        }
      : null,
    prediction_horizon: Number(d?.prediction_horizon || 0),
  };
}

export async function getValidationReport(): Promise<any> {
  return apiRequest<any>("/api/v1/system/validation");
}

export async function getValidationHistory(): Promise<any> {
  return apiRequest<any>("/api/v1/system/validation/history");
}

export async function getValidationReportByTimestamp(timestamp: string): Promise<any> {
  return apiRequest<any>(`/api/v1/system/validation/${encodeURIComponent(timestamp)}`);
}

// ─── Airport Search ───────────────────────────────────────────────────
export async function searchAirports(q: string): Promise<AirportSuggestion[]> {
  if (!q || q.length < 2) return [];
  try {
    const data = await apiRequest<any>(
      `/flights/airports?q=${encodeURIComponent(q)}`
    );
    // Backend returns { "airports": [...] }
    const list = data?.airports ?? [];
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

export const searchAirportsAPI = searchAirports;

export async function searchFlights(
  params: FlightSearchParams
): Promise<FlightSearchResponse> {
  const origin = resolveCityToIATA(params.origin);
  const destination = resolveCityToIATA(params.destination);
  const departure_date = params.departure_date;

  const raw = await apiRequest<any>("/live-search", {
    method: "POST",
    body: JSON.stringify({
      origin,
      destination,
      departure_date,
      return_date: params.return_date,
      adults: params.adults,
      children: params.children,
      infants: params.infants,
      cabin_class: params.cabin_class,
    }),
  });

  const mappedFlights: FlightOffer[] = (raw.flights || []).map((f: any, i: number) => {
    const itineraries: FlightItinerary[] = [];

    // Outbound legs
    if (f.legs && Array.isArray(f.legs) && f.legs.length > 0) {
      let totalDurMins = 0;
      const segments = f.legs.map((leg: any) => {
        const legDurMins = typeof leg.duration === 'number' ? leg.duration : null;
        if (legDurMins) totalDurMins += legDurMins;
        const durStr = legDurMins
          ? `PT${Math.floor(legDurMins/60)}H${legDurMins%60}M`
          : null;
        return {
          flight_number: leg.flight_number || f.flight_number || null,
          airline_code: leg.airline_code || f.airline_code || null,
          airline_name: leg.airline || f.airline_name || f.airline_code || null,
          airline_logo: getAirlineLogo(leg.airline_code || f.airline_code),
          airline_logo_rect: getAirlineLogoRect(leg.airline_code || f.airline_code),
          origin: leg.departure_airport || leg.origin || f.origin_code,
          destination: leg.arrival_airport || leg.destination || f.destination_code,
          departure_time: leg.departure_time || null,
          arrival_time: leg.arrival_time || null,
          duration: durStr,
          cabin: params.cabin_class ?? "ECONOMY",
          stops: leg.stops ?? 0,
        };
      });
      const totalDurStr = totalDurMins > 0
        ? `PT${Math.floor(totalDurMins/60)}H${totalDurMins%60}M`
        : null;
      itineraries.push({
        duration: totalDurStr,
        segments
      });
    }

    // Inbound legs (for round trips)
    if (f.return_legs && Array.isArray(f.return_legs) && f.return_legs.length > 0) {
      let totalDurMins = 0;
      const segments = f.return_legs.map((leg: any) => {
        const legDurMins = typeof leg.duration === 'number' ? leg.duration : null;
        if (legDurMins) totalDurMins += legDurMins;
        const durStr = legDurMins ? `PT${Math.floor(legDurMins/60)}H${legDurMins%60}M` : null;
        return {
          flight_number: leg.flight_number || f.flight_number || null,
          airline_code: leg.airline_code || f.airline_code || null,
          airline_name: leg.airline || f.airline_name || f.airline_code || null,
          airline_logo: getAirlineLogo(leg.airline_code || f.airline_code),
          airline_logo_rect: getAirlineLogoRect(leg.airline_code || f.airline_code),
          origin: leg.departure_airport || leg.origin || f.destination_code,
          destination: leg.arrival_airport || leg.destination || f.origin_code,
          departure_time: leg.departure_time || null,
          arrival_time: leg.arrival_time || null,
          duration: durStr,
          cabin: params.cabin_class ?? "ECONOMY",
          stops: leg.stops ?? 0,
        };
      });
      const totalDurStr = totalDurMins > 0
        ? `PT${Math.floor(totalDurMins/60)}H${totalDurMins%60}M`
        : null;
      itineraries.push({
        duration: totalDurStr,
        segments
      });
    }


    return {
      id: `live_${i}_${f.flight_number || f.airline_code || i}`,
      source: "live-search",
      price: {
        total: f.price,
        currency: params.currency ?? "INR",
      },
      itineraries: itineraries,
      primary_airline: f.airline_code || null,
      primary_airline_name: f.airline_name || f.airline_code || null,
      primary_airline_logo: getAirlineLogo(f.airline_code),
      flight_number: f.flight_number || null,
      origin: f.origin_code,
      destination: f.destination_code,
      // An absent provenance field used to become "REAL_PROVIDER", which the
      // results page renders as "LIVE · GOOGLE FLIGHTS". Defaulting to the
      // strongest possible claim means a row whose origin the backend did not
      // state is displayed as a live provider fetch. Absent now reads as
      // unknown.
      provenance: f.provenance || "UNKNOWN",
      seats_available: f.seats_available || null,
    } as FlightOffer;
  });

  return {
    flights: mappedFlights,
    count: mappedFlights.length,
    origin_iata: origin,
    destination_iata: destination,
    data_source: "LIVE_SEARCH",
    search_params: { origin, destination, departure_date },
  };
}

// ─── Price Alerts ─────────────────────────────────────────────────────
export async function setAlert(req: SetAlertRequest): Promise<SetAlertResponse> {
  return apiRequest<SetAlertResponse>("/alerts/subscribe", {
    method: "POST",
    body: JSON.stringify({
      ...req,
      origin_code: resolveCityToIATA(req.origin),
      destination_code: resolveCityToIATA(req.destination),
    }),
  });
}

export async function checkAlerts(
  userId?: string
): Promise<CheckAlertsResponse> {
  if (!userId) return { alerts: [], triggered: [], triggered_count: 0 };
  try {
    const data = await apiRequest<{
      alerts: CheckAlertsResponse["alerts"];
      triggered?: CheckAlertsResponse["alerts"];
      triggered_count?: number;
    }>(`/alerts/user/${encodeURIComponent(userId)}`);

    const alerts = data.alerts ?? [];
    const triggered =
      data.triggered ??
      alerts.filter(
        (a) => (a as unknown as Record<string, unknown>).triggered
      );
    return {
      alerts,
      triggered,
      triggered_count: data.triggered_count ?? triggered.length,
    };
  } catch {
    return { alerts: [], triggered: [], triggered_count: 0 };
  }
}

export async function deleteAlert(
  alertId: string
): Promise<{ success: boolean; message: string }> {
  return apiRequest(`/alerts/${alertId}`, { method: "DELETE" });
}

// ─── Booking ──────────────────────────────────────────────────────────
export async function createBooking(
  req: CreateBookingRequest
): Promise<CreateBookingResponse> {
  return apiRequest<CreateBookingResponse>("/booking/create", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

// ─── Payment ──────────────────────────────────────────────────────────
export async function createRazorpayOrder(
  params: CreateOrderRequest
): Promise<CreateOrderResponse> {
  return apiRequest<CreateOrderResponse>("/payment/create-order", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function verifyPayment(
  params: VerifyPaymentRequest
): Promise<VerifyPaymentResponse> {
  return apiRequest<VerifyPaymentResponse>("/payment/verify", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

// ─── Health Check ─────────────────────────────────────────────────────
// This dropped four of the fields `/health` publishes. Three of them are the
// only way a caller can tell *why* no model is serving: `model` is now
// "ready" | "failed" | "lazy" rather than the old "ready" | "lazy", and a
// "failed" state carries `model_load_error` plus one `refused_artifacts` entry
// per artifact the leak audit declined. Dropping them here meant the settings
// page rendered a directory of rejected artifacts as "LAZY / UNTRAINED", i.e.
// as a model nobody had asked for yet.
export interface HealthReport {
  status: string;            // "ok" | "degraded" | "offline" (client-side)
  model: string;             // "ready" | "failed" | "lazy" | "unknown"
  model_load_error: string | null;
  refused_artifacts: string[];
  degraded_capabilities: string[];
  data_source: string;
  time: string;
  version: string;
}

export async function healthCheck(): Promise<HealthReport> {
  const d = await apiRequest<any>("/api/v1/system/health");
  return {
    status: d.status,
    model: d.model,
    model_load_error: d.model_load_error ?? null,
    refused_artifacts: Array.isArray(d.refused_artifacts) ? d.refused_artifacts : [],
    degraded_capabilities: Array.isArray(d.degraded_capabilities) ? d.degraded_capabilities : [],
    data_source: d.data_source ?? "unknown",
    time: d.time,
    version: d.backend_version
  };
}

// The system-configuration surface, for the fields the settings page used to
// hardcode. `validation_status` is "UNAUDITED" when no validation report exists
// on disk, which is the honest answer to "is the leak guard enforced" on a
// deployment that has never run the validator.
export interface SystemInfo {
  model_version: string | null;
  feature_set_version: string | null;
  validator_version: string | null;
  training_timestamp: string | null;
  dataset_size: number | null;
  validation_status: string;
  last_validation_timestamp: string | null;
  trained: boolean;
  model_load_error: string | null;
  refused_artifacts: string[];
  unavailable: string[];
}

export async function getSystemInfo(): Promise<SystemInfo> {
  const d = await apiRequest<any>("/api/v1/system/info");
  return {
    model_version: d.model_version ?? null,
    feature_set_version: d.feature_set_version ?? null,
    validator_version: d.validator_version ?? null,
    training_timestamp: d.training_timestamp ?? null,
    dataset_size: typeof d.dataset_size === "number" ? d.dataset_size : null,
    validation_status: d.validation_status ?? "UNKNOWN",
    last_validation_timestamp: d.last_validation_timestamp ?? null,
    trained: Boolean(d.trained),
    model_load_error: d.model_load_error ?? null,
    refused_artifacts: Array.isArray(d.refused_artifacts) ? d.refused_artifacts : [],
    unavailable: Array.isArray(d.unavailable) ? d.unavailable : []
  };
}

// Every metric here is nullable, and that is the point. `/model/metadata` used
// to publish a hardcoded mae 481.0 / rmse 921.0 / r2 0.9855 whether or not a
// model had ever been trained; it now publishes `validation_metrics: null` and
// names the gap in `unavailable`. The declared type said `number`, so absence
// arrived as `undefined` and the settings page's `perf?.mae || 0` rendered it as
// ₹0 MAE and R² 0.0000 — which reads as a measurement, not as a missing one.
export interface ModelMetrics {
  mae: number | null;
  rmse: number | null;
  r2: number | null;
  mape: number | null;
  training_samples: number | null;
  model_name?: string;
  algorithm?: string;
  feature_set_version?: string | null;
  training_date?: string | null;
  unavailable: string[];
}

const _num = (v: unknown): number | null =>
  typeof v === "number" && Number.isFinite(v) ? v : null;

export async function getModelPerformance(): Promise<{ metrics: ModelMetrics }> {
  const d = await apiRequest<any>("/api/v1/system/model/metadata");
  const m = d.validation_metrics ?? {};
  return {
    metrics: {
      mae: _num(m.mae),
      rmse: _num(m.rmse),
      r2: _num(m.r2),
      mape: _num(m.mape),
      training_samples: _num(d.training_rows),
      model_name: d.model_name,
      algorithm: d.algorithm,
      feature_set_version: d.feature_set_version ?? null,
      training_date: d.training_date ?? null,
      unavailable: Array.isArray(d.unavailable) ? d.unavailable : []
    }
  };
}

// ─── Utilities ────────────────────────────────────────────────────────
export function formatDuration(iso: string): string {
  if (!iso) return "--";
  const match = iso.match(/PT(?:(\d+)H)?(?:(\d+)M)?/);
  if (!match) return iso;
  const h = match[1] ? `${match[1]}h` : "";
  const m = match[2] ? `${match[2]}m` : "";
  return [h, m].filter(Boolean).join(" ") || iso;
}

export function formatINR(amount: number): string {
  return `₹${Math.round(amount).toLocaleString("en-IN")}`;
}

export function getAirlineLogo(iataCode: string): string {
  return `https://content.airhex.com/content/logos/airlines_${iataCode.toUpperCase()}_200_200_s.png`;
}

export function getAirlineLogoRect(iataCode: string): string {
  return `https://content.airhex.com/content/logos/airlines_${iataCode.toUpperCase()}_100_25_r.png`;
}