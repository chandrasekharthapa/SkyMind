/**
 * SkyMind — Unified API Client
 *
 * All network calls go through `apiRequest` which:
 * • Reads base URL from NEXT_PUBLIC_API_BASE_URL
 * • Attaches Content-Type header
 * • Throws typed ApiError on non-2xx responses
 * • Uses async/await with proper try/catch patterns
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

// Re-export commonly used types for convenience
export type {
  AirportSuggestion as AirportResult,
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

// ─────────────────────────────────────────────────────────────────────
// Config
// ─────────────────────────────────────────────────────────────────────

function getApiBase(): string {
  const url =
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://localhost:8000";
  return url.endsWith("/") ? url.slice(0, -1) : url;
}

// ─────────────────────────────────────────────────────────────────────
// Error class
// ─────────────────────────────────────────────────────────────────────

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

// ─────────────────────────────────────────────────────────────────────
// Core fetch helper
// ─────────────────────────────────────────────────────────────────────

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

  const res = await fetch(url, { ...options, headers });

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

// ─────────────────────────────────────────────────────────────────────
// City → IATA (client-side map; backend also resolves these)
// ─────────────────────────────────────────────────────────────────────

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
  dubai: "DXB",
  london: "LHR",
  singapore: "SIN",
  doha: "DOH",
  bangkok: "BKK",
  istanbul: "IST",
  tokyo: "NRT",
  "abu dhabi": "AUH",
  "kuala lumpur": "KUL",
};

export function resolveCityToIATA(input: string): string {
  const lower = input.trim().toLowerCase();
  return CITY_TO_IATA[lower] ?? input.trim().toUpperCase();
}

// ─────────────────────────────────────────────────────────────────────
// Airport Search
// ─────────────────────────────────────────────────────────────────────

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

// ─────────────────────────────────────────────────────────────────────
// Flight Search
// ─────────────────────────────────────────────────────────────────────

export async function searchFlights(
  params: FlightSearchParams
): Promise<FlightSearchResponse> {
  const qs = new URLSearchParams({
    origin: resolveCityToIATA(params.origin),
    destination: resolveCityToIATA(params.destination),
    departure_date: params.departure_date,
    adults: String(params.adults ?? 1),
    cabin_class: params.cabin_class ?? "ECONOMY",
    currency: params.currency ?? "INR",
    max_results: String(params.max_results ?? 20),
    ...(params.return_date ? { return_date: params.return_date } : {}),
  });

  return apiRequest<FlightSearchResponse>(`/flights/search?${qs}`);
}

// ─────────────────────────────────────────────────────────────────────
// Price Prediction  (POST /predict)
// ─────────────────────────────────────────────────────────────────────

export async function predictPrice(
  req: PredictRequest
): Promise<PredictionResult> {
  // PATCH: Handle the "data" wrapper from the backend response
  const res = await apiRequest<{ status: string; data: PredictionResult }>("/predict", {
    method: "POST",
    body: JSON.stringify({
      ...req,
      origin: resolveCityToIATA(req.origin),
      destination: resolveCityToIATA(req.destination),
    }),
  });

  return res.data;
}

// ─────────────────────────────────────────────────────────────────────
// Price Alerts
// ─────────────────────────────────────────────────────────────────────

export async function setAlert(
  req: SetAlertRequest
): Promise<SetAlertResponse> {
  return apiRequest<SetAlertResponse>("/alerts/subscribe", {
    method: "POST",
    body: JSON.stringify({
      ...req,
      origin_code: resolveCityToIATA(req.origin),
      destination_code: resolveCityToIATA(req.destination),
    }),
  });
}

export async function checkAlerts(userId?: string): Promise<CheckAlertsResponse> {
  const qs = userId ? `?user_id=${encodeURIComponent(userId)}` : "";
  try {
    const data = await apiRequest<{ alerts: unknown[]; count: number }>(
      `/alerts/user/${userId ?? "anonymous"}${qs}`
    );
    const alerts = (data.alerts ?? []) as CheckAlertsResponse["alerts"];
    const triggered = alerts.filter((a) => (a as { triggered?: boolean }).triggered);
    return { alerts, triggered, triggered_count: triggered.length };
  } catch {
    return { alerts: [], triggered: [], triggered_count: 0 };
  }
}

export async function deleteAlert(
  alertId: string
): Promise<{ success: boolean; message: string }> {
  return apiRequest(`/alerts/${alertId}`, { method: "DELETE" });
}

// ─────────────────────────────────────────────────────────────────────
// Booking
// ─────────────────────────────────────────────────────────────────────

export async function createBooking(
  req: CreateBookingRequest
): Promise<CreateBookingResponse> {
  return apiRequest<CreateBookingResponse>("/booking/create", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

// ─────────────────────────────────────────────────────────────────────
// Payment (Razorpay)
// ─────────────────────────────────────────────────────────────────────

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

// ─────────────────────────────────────────────────────────────────────
// Health
// ─────────────────────────────────────────────────────────────────────

export async function healthCheck(): Promise<{
  status: string;
  model: string;
  time: string;
}> {
  return apiRequest("/health");
}

// ─────────────────────────────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────────────────────────────

export function formatDuration(iso: string): string {
  if (!iso) return "--";
  const match = iso.match(/PT(?:(\d+)H)?(?:(\d+)M)?/);
  if (!match) return iso;
  const h = match[1] ? `${match[1]}h` : "";
  const m = match[2] ? `${match[2]}m` : "";
  return [h, m].filter(Boolean).join(" ") || iso;
}

export function getAirlineLogo(iataCode: string): string {
  return `https://content.airhex.com/content/logos/airlines_${iataCode.toUpperCase()}_200_200_s.png`;
}

export function getAirlineLogoRect(iataCode: string): string {
  return `https://content.airhex.com/content/logos/airlines_${iataCode.toUpperCase()}_100_25_r.png`;
}