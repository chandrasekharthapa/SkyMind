import { createClient } from "@supabase/supabase-js";

const supabaseUrl =
  process.env.NEXT_PUBLIC_SUPABASE_URL || "https://placeholder.supabase.co";
const supabaseAnonKey =
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "placeholder-key";

export const supabase = createClient(supabaseUrl, supabaseAnonKey);

// ── Typed DB helpers ──────────────────────────────────────────────────

export async function searchAirportsFromDB(query: string) {
  if (!query || query.length < 2) return [];
  if (supabaseUrl.includes("placeholder")) return [];

  const q = query.toUpperCase().trim();
  try {
    const { data, error } = await supabase
      .from("airports")
      .select("iata_code, name, city, state, region, country, country_code, is_domestic, is_international")
      .eq("is_active", true)
      .or(`iata_code.ilike.${q}%,city.ilike.%${query}%,name.ilike.%${query}%`)
      .order("is_international", { ascending: false })
      .limit(10);

    if (error) return [];
    return data || [];
  } catch {
    return [];
  }
}

export async function getRouteMinPrice(
  origin: string,
  destination: string
): Promise<number | null> {
  if (supabaseUrl.includes("placeholder")) return null;
  try {
    const { data } = await supabase
      .from("routes")
      .select("min_price_inr")
      .eq("origin_code", origin)
      .eq("destination_code", destination)
      .single();
    return data?.min_price_inr ?? null;
  } catch {
    return null;
  }
}
