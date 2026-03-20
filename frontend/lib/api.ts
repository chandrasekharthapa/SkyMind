/**
 * Typed API client for SkyMind backend.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

async function apiRequest<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const url = `${API_URL}${path}`
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(err.detail || `API error ${res.status}`)
  }
  return res.json()
}

// ===================== Flights =====================

export interface FlightSearchParams {
  origin: string
  destination: string
  departure_date: string
  return_date?: string
  adults?: number
  cabin_class?: string
  currency?: string
  max_results?: number
}

export interface FlightOffer {
  id: string
  price: {
    total: number
    base: number
    currency: string
    grand_total: number
  }
  itineraries: Array<{
    duration: string
    segments: Array<{
      flight_number: string
      airline_code: string
      airline_name: string
      aircraft: string
      origin: string
      destination: string
      departure_time: string
      arrival_time: string
      duration: string
      cabin: string
      stops: number
    }>
  }>
  validating_airlines: string[]
  seats_available?: number
  ai_insight?: {
    recommendation: string
    reason: string
    probability_increase: number
    trend: string
  }
}

export interface FlightSearchResponse {
  flights: FlightOffer[]
  count: number
  search_params: FlightSearchParams
}

export async function searchFlights(params: FlightSearchParams): Promise<FlightSearchResponse> {
  const query = new URLSearchParams({
    origin: params.origin,
    destination: params.destination,
    departure_date: params.departure_date,
    ...(params.return_date && { return_date: params.return_date }),
    adults: String(params.adults || 1),
    cabin_class: params.cabin_class || 'ECONOMY',
    currency: params.currency || 'INR',
    max_results: String(params.max_results || 20),
  })
  return apiRequest<FlightSearchResponse>(`/flights/search?${query}`)
}

export async function searchAirports(q: string) {
  return apiRequest<{ airports: Airport[] }>(`/flights/airports?q=${encodeURIComponent(q)}`)
}

export async function getFlightInspiration(origin: string, currency = 'INR') {
  return apiRequest(`/flights/inspiration?origin=${origin}&currency=${currency}`)
}

// ===================== Prediction =====================

export interface PricePrediction {
  predicted_price: number
  recommendation: string
  reason: string
  price_trend: string
  probability_increase: number
  confidence: number
  days_until_departure: number
}

export async function getPricePrediction(
  origin: string,
  destination: string,
  departure_date: string,
  airline_code = 'AI',
): Promise<PricePrediction> {
  return apiRequest(
    `/prediction/price?origin=${origin}&destination=${destination}&departure_date=${departure_date}&airline_code=${airline_code}`
  )
}

export interface ForecastDay {
  date: string
  price: number
  confidence_low: number
  confidence_high: number
  recommendation: string
}

export interface PriceForecast {
  origin: string
  destination: string
  forecast: ForecastDay[]
  best_day: ForecastDay
  worst_day: ForecastDay
}

export async function getPriceForecast(
  origin: string,
  destination: string,
  base_price = 8000,
): Promise<PriceForecast> {
  return apiRequest(
    `/prediction/forecast?origin=${origin}&destination=${destination}&base_price=${base_price}`
  )
}

export async function getHiddenRoutes(
  origin: string,
  destination: string,
  departure_date: string,
  direct_price: number,
) {
  return apiRequest(
    `/prediction/hidden-routes?origin=${origin}&destination=${destination}&departure_date=${departure_date}&direct_price=${direct_price}`
  )
}

// ===================== Booking =====================

export interface PassengerData {
  type: string
  first_name: string
  last_name: string
  date_of_birth?: string
  passport_number?: string
  meal_preference?: string
  baggage_allowance?: number
}

export interface CreateBookingRequest {
  flight_offer_id: string
  flight_data: FlightOffer
  passengers: PassengerData[]
  contact_email: string
  contact_phone: string
  cabin_class?: string
  currency?: string
  user_id?: string
}

export async function createBooking(data: CreateBookingRequest) {
  return apiRequest('/booking/create', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// ===================== Payment =====================

export async function createRazorpayOrder(data: {
  amount: number
  booking_id: string
  booking_reference: string
  currency?: string
}) {
  return apiRequest('/payment/create-order', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function verifyPayment(data: {
  razorpay_order_id: string
  razorpay_payment_id: string
  razorpay_signature: string
  booking_id: string
}) {
  return apiRequest('/payment/verify', { method: 'POST', body: JSON.stringify(data) })
}

// ===================== Alerts =====================

export async function subscribeAlert(data: {
  user_id: string
  origin_code: string
  destination_code: string
  departure_date: string
  target_price: number
}) {
  return apiRequest('/alerts/subscribe', { method: 'POST', body: JSON.stringify(data) })
}

// ===================== Types =====================

export interface Airport {
  iata: string
  city: string
  name: string
  country: string
}

// Format duration from ISO 8601 (PT2H30M → 2h 30m)
export function formatDuration(iso: string): string {
  if (!iso) return '--'
  const match = iso.match(/PT(?:(\d+)H)?(?:(\d+)M)?/)
  if (!match) return iso
  const h = match[1] ? `${match[1]}h` : ''
  const m = match[2] ? ` ${match[2]}m` : ''
  return `${h}${m}`.trim()
}

export function formatPrice(amount: number, currency = 'INR'): string {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
  }).format(amount)
}

export function getAirlineLogoUrl(code: string): string {
  return `https://content.airhex.com/content/logos/thumbnails_100_100_${code}_s_BC@2x.png`
}
