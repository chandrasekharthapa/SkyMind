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
  ForecastPoint,
  Trend,
  Recommendation,
} from "@/types";

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
};
export type AirportResult = {
  iata: string;
  city: string;
  name: string;
  country: string;
};

// ─── Config ───────────────────────────────────────────────────────────
function getApiBase(): string {
  const url =
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://localhost:8000";
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
async function apiRequest<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const base = getApiBase();
  const url = path.startsWith("http") ? path : `${base}${path}`;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
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
      message = body?.detail ?? message;
      detail = body;
    } catch {
      // non-JSON body
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
  const lower = input.trim().toLowerCase();
  return CITY_TO_IATA[lower] ?? input.trim().toUpperCase();
}

// ─── Forecast normalization ───────────────────────────────────────────
function normalizeForecast(raw: unknown): ForecastPoint[] {
  if (!Array.isArray(raw) || raw.length === 0) return [];
  return raw.map((p: unknown) => {
    const point = p as Record<string, unknown>;
    return {
      day:
        typeof point.day === "number"
          ? point.day
          : parseInt(String(point.day ?? "0"), 10) || 0,
      date: String(point.date ?? ""),
      price: safePrice(point.price),
      lower: safePrice(point.lower),
      upper: safePrice(point.upper),
    };
  });
}

/**
 * Generates a deterministic synthetic forecast when the backend doesn't
 * return one (e.g. when route has no DB entry). Uses sine-wave seasonality
 * seeded from the base price so it's stable across re-renders.
 */
function generateSyntheticForecast(
  basePrice: number,
  trend: Trend
): ForecastPoint[] {
  const slope =
    trend === "RISING" ? 0.006 : trend === "FALLING" ? -0.004 : 0.001;
  const std = basePrice * 0.04;

  return Array.from({ length: 30 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() + i + 1);
    const trendComponent = basePrice * slope * i;
    const seasonality =
      basePrice * 0.025 * Math.sin((2 * Math.PI * (i + 3)) / 7);
    const price = Math.max(800, basePrice + trendComponent + seasonality);
    return {
      day: i + 1,
      date: d.toISOString().split("T")[0],
      price: Math.round(price),
      lower: Math.round(price - std),
      upper: Math.round(price + std),
    };
  });
}

/**
 * Maps Python `market_status` ("VOLATILE" | "STABLE") plus `prob_increase`
 * to our UI Trend type ("RISING" | "FALLING" | "STABLE").
 *
 * FIX: renamed from "deriveтrend" (contained Cyrillic т) to "deriveTrend".
 */
function deriveTrend(marketStatus: string, probIncrease: number): Trend {
  const status = (marketStatus ?? "").toUpperCase();
  if (status === "VOLATILE") {
    return probIncrease > 0.5 ? "RISING" : "FALLING";
  }
  if (probIncrease > 0.65) return "RISING";
  if (probIncrease < 0.35) return "FALLING";
  return "STABLE";
}

/**
 * Maps Python recommendation string to our canonical Recommendation type.
 * Handles: "BUY_NOW", "WAIT", "OPTIMIZED PRICE", "NEUTRAL", "MONITOR"
 */
function mapRecommendation(raw: string): Recommendation {
  const r = (raw ?? "").toUpperCase().replace(/[\s-]/g, "_");
  if (r.includes("BUY") || r.includes("BOOK")) return "BOOK_NOW";
  if (r.includes("WAIT")) return "WAIT";
  return "MONITOR";
}

/**
 * Derives a human-readable reason from intelligence fields.
 */
function deriveReason(
  recommendation: Recommendation,
  probIncrease: number,
  confidence: number,
  peakSeason: boolean
): string {
  const pct = Math.round(probIncrease * 100);
  const conf = Math.round(confidence * 100);
  const peak = peakSeason ? " Peak season demand is elevated." : "";

  if (recommendation === "BOOK_NOW") {
    return `${pct}% probability of price increase detected. Model confidence: ${conf}%.${peak} Lock in this fare now.`;
  }
  if (recommendation === "WAIT") {
    return `Prices may soften — only ${pct}% chance of an increase. Model confidence: ${conf}%.${peak} Consider waiting a few days.`;
  }
  return `Market is stable with ${pct}% probability of increase. Model confidence: ${conf}%.${peak} Monitor and book when ready.`;
}

// ─── Airport Search ───────────────────────────────────────────────────
export async function searchAirports(q: string): Promise<AirportSuggestion[]> {
  if (!q || q.length < 2) return [];
  try {
    const data = await apiRequest<AirportSuggestion[]>(
      `/airports?q=${encodeURIComponent(q)}`
    );
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

export const searchAirportsAPI = searchAirports;

// ─── Flight Search ────────────────────────────────────────────────────
export async function searchFlights(
  params: FlightSearchParams
): Promise<FlightSearchResponse> {
  const qs = new URLSearchParams({
    origin: resolveCityToIATA(params.origin),
    destination: resolveCityToIATA(params.destination),
    departure_date: params.departure_date,
    adults: String(params.adults ?? 1),
    children: String(params.children ?? 0),
    infants: String(params.infants ?? 0),
    cabin_class: params.cabin_class ?? "ECONOMY",
    currency: params.currency ?? "INR",
    max_results: String(params.max_results ?? 20),
    ...(params.return_date ? { return_date: params.return_date } : {}),
  });

  return apiRequest<FlightSearchResponse>(`/flights/search?${qs}`);
}

// ─── Price Prediction (POST /predict) ────────────────────────────────
/**
 * This is the SINGLE source of truth for mapping the backend response.
 * The hook (usePrediction.ts) calls this and gets a fully-typed PredictionResult.
 * No mapping logic exists anywhere else.
 */
export async function predictPrice(req: PredictRequest): Promise<PredictionResult> {
  const rawResponse = await apiRequest<any>("/predict", {
    method: "POST",
    body: JSON.stringify({
      origin: resolveCityToIATA(req.origin),
      destination: resolveCityToIATA(req.destination),
      departure_date: req.departure_date ?? "",
    }),
  });

  // Handle both flat response and nested { status, data: {...} } response
  const d = rawResponse?.data ? rawResponse.data : rawResponse;

  const intel = d?.intelligence || {};
  const meta = d?.meta || {};

  // PRICE
  const predictedPrice = safePrice(d?.predicted_price);

  // CONFIDENCE: backend returns 0–100, normalize to 0–1
  const confidence = Math.min(
    1,
    Math.max(0, safePrice(intel?.confidence) / 100)
  );

  // PROBABILITY: already 0–1
  const probabilityIncrease = Math.min(
    1,
    Math.max(0, safePrice(intel?.prob_increase))
  );

  // TREND: read from d.trend directly (it's at data root, not inside intelligence)
  let trend: Trend = "STABLE";
  if (d?.trend === "FALLING") trend = "FALLING";
  else if (d?.trend === "RISING") trend = "RISING";
  // If trend is absent, derive from market_status + prob_increase
  else if (intel?.market_status) {
    trend = deriveTrend(intel.market_status, probabilityIncrease);
  }

  // RECOMMENDATION
  let recommendation: Recommendation = "MONITOR";
  if (intel?.recommendation) {
    recommendation = mapRecommendation(intel.recommendation);
  }

  // CHANGE %
  const expectedChangePercent = safePrice(d?.change_percent);

  // FORECAST: use backend data if ≥7 points, otherwise synthesize
  const rawForecast = normalizeForecast(d?.forecast);
  const forecast =
    rawForecast.length >= 7
      ? rawForecast
      : generateSyntheticForecast(predictedPrice || 5000, trend);

  // REASON
  const reason = deriveReason(
    recommendation,
    probabilityIncrease,
    confidence,
    Boolean(meta?.peak_season)
  );

  return {
    predicted_price: predictedPrice,
    forecast,
    trend,
    probability_increase: probabilityIncrease,
    confidence,
    recommendation,
    reason,
    expected_change_percent: expectedChangePercent,
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
export async function healthCheck(): Promise<{
  status: string;
  model: string;
  time: string;
  version: string;
}> {
  return apiRequest("/health");
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