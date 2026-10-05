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

// ── Profiles ──────────────────────────────────────────────────────────
// A profile row is linked to the signed-in user by `auth_user_id` (its own
// `id` is a separate UUID; see handle_new_user in skymind_complete.sql). The
// dashboard and nav used to look it up with `.eq("id", user.id)`, which
// matches nothing, so names never showed. Older databases created the row
// with id = auth uid, so that is tried second.
export type Profile = {
  id: string;
  auth_user_id?: string | null;
  email?: string | null;
  full_name?: string | null;
  display_name?: string | null;
  phone?: string | null;
};

export async function loadProfile(authUserId: string): Promise<Profile | null> {
  for (const column of ["auth_user_id", "id"] as const) {
    const { data, error } = await supabase.from("profiles").select("*").eq(column, authUserId).maybeSingle();
    if (!error && data) return data as Profile;
  }
  return null;
}

export async function saveProfile(
  authUserId: string,
  existing: Profile | null,
  fields: { display_name?: string | null; full_name?: string | null; phone?: string | null; email?: string | null },
): Promise<{ error: string | null }> {
  const query = existing
    ? supabase.from("profiles").update(fields).eq("id", existing.id)
    : supabase.from("profiles").insert({ auth_user_id: authUserId, ...fields });
  const { error } = await query;
  return { error: error ? error.message : null };
}
