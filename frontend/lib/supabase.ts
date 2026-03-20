import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

export const supabase = createClient(supabaseUrl, supabaseAnonKey)

// ── Types matching our DB schema ─────────────────────────────────
export interface Airport {
  iata_code: string
  name: string
  city: string
  state: string | null
  region: string
  country: string
  country_code: string
  latitude: number
  longitude: number
  is_domestic: boolean
  is_international: boolean
  is_active: boolean
  aai_category: string | null
}

export interface Airline {
  iata_code: string
  name: string
  short_name: string
  country: string
  is_domestic: boolean
  is_lowcost: boolean
  hub_airport: string | null
  is_active: boolean
}

export interface Route {
  id: string
  origin_code: string
  destination_code: string
  distance_km: number
  avg_duration_min: number
  airlines: string[]
  min_price_inr: number
  avg_price_inr: number
  max_price_inr: number
  flights_per_day: number
  is_popular: boolean
}

export interface Booking {
  id: string
  booking_reference: string
  pnr: string | null
  status: string
  payment_status: string
  total_price: number
  base_fare: number
  taxes: number
  discount_amount: number
  currency: string
  cabin_class: string
  num_passengers: number
  contact_email: string
  contact_phone: string
  confirmation_sent: boolean
  checkin_notif_sent: boolean
  created_at: string
  cancelled_at: string | null
  refund_amount: number | null
  refund_status: string | null
  flight_offer_data: any
}

export interface PriceAlert {
  id: string
  origin_code: string
  destination_code: string
  departure_date: string
  cabin_class: string
  target_price: number
  is_active: boolean
  notify_email: boolean
  notify_sms: boolean
  last_price: number | null
  lowest_seen: number | null
  triggered_count: number
  created_at: string
}

export interface Profile {
  id: string
  email: string
  full_name: string | null
  display_name: string | null
  phone: string | null
  skymind_points: number
  tier: string
  total_bookings: number
  total_spent: number
  notify_email: boolean
  notify_sms: boolean
  notify_whatsapp: boolean
  preferred_cabin: string
  meal_preference: string
}

// ── Airport search (from DB) ─────────────────────────────────────
export async function searchAirportsFromDB(query: string): Promise<Airport[]> {
  if (!query || query.length < 2) return []
  const q = query.toUpperCase().trim()
  const { data, error } = await supabase
    .from('airports')
    .select('*')
    .eq('is_active', true)
    .or(
      `iata_code.ilike.${q}%,city.ilike.%${query}%,name.ilike.%${query}%,state.ilike.%${query}%`
    )
    .order('is_international', { ascending: false })
    .limit(10)
  if (error) throw error
  return data || []
}

// ── Popular routes from DB ────────────────────────────────────────
export async function getPopularRoutes(limit = 6) {
  const { data, error } = await supabase
    .from('v_domestic_routes')
    .select('*')
    .eq('is_popular', true)
    .order('flights_per_day', { ascending: false })
    .limit(limit)
  if (error) {
    // fallback — get any top routes
    const { data: fallback } = await supabase
      .from('v_domestic_routes')
      .select('*')
      .order('flights_per_day', { ascending: false })
      .limit(limit)
    return fallback || []
  }
  return data || []
}

// ── User's bookings ───────────────────────────────────────────────
export async function getUserBookings(profileId: string): Promise<Booking[]> {
  const { data, error } = await supabase
    .from('bookings')
    .select('*')
    .eq('user_id', profileId)
    .order('created_at', { ascending: false })
  if (error) throw error
  return data || []
}

// ── User's price alerts ───────────────────────────────────────────
export async function getUserAlerts(profileId: string): Promise<PriceAlert[]> {
  const { data, error } = await supabase
    .from('price_alerts')
    .select('*')
    .eq('user_id', profileId)
    .eq('is_active', true)
    .order('created_at', { ascending: false })
  if (error) throw error
  return data || []
}

// ── Current user's profile ────────────────────────────────────────
export async function getCurrentProfile(): Promise<Profile | null> {
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return null
  const { data, error } = await supabase
    .from('profiles')
    .select('*')
    .eq('auth_user_id', user.id)
    .single()
  if (error) return null
  return data
}

// ── Route min price helper ─────────────────────────────────────────
export async function getRouteMinPrice(
  origin: string,
  destination: string
): Promise<number | null> {
  const { data } = await supabase
    .from('routes')
    .select('min_price_inr')
    .eq('origin_code', origin)
    .eq('destination_code', destination)
    .single()
  return data?.min_price_inr ?? null
}

// ── All airports for search dropdown ──────────────────────────────
export async function getAllActiveAirports(): Promise<Airport[]> {
  const { data } = await supabase
    .from('airports')
    .select('iata_code,name,city,state,region,country,country_code,is_domestic,is_international,is_active,latitude,longitude,aai_category')
    .eq('is_active', true)
    .order('city')
  return data || []
}
