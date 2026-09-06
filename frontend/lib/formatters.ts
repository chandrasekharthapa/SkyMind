/**
 * Production Formatters & Utility Functions (Milestone 1, 5).
 * Standardized locale-aware currency, date, percentage, and confidence rating formatters.
 */

/**
 * A figure derived from the stored corpus, in rupees.
 *
 * The rupee symbol is correct here by construction: since AUDIT-FIXES.md §48 the
 * ingest screen refuses any fare that does not declare itself as INR, so every
 * number computed from `price_history` — predictions, market aggregates, savings —
 * is rupee-denominated. Use `formatFare` for a fare quoted by the provider, whose
 * unit is data rather than an invariant.
 */
export function formatCurrency(amount: number | null | undefined): string {
  if (amount == null || isNaN(amount)) return "Unavailable";
  return `₹${Math.round(amount).toLocaleString("en-IN")}`;
}

/**
 * A provider-quoted fare, rendered in the currency it was actually quoted in.
 *
 * Nothing on the live search path consulted the currency before §48: this module
 * had one formatter, it stamped `₹` unconditionally, and `NormalizedFlight`
 * defaulted the field to `"INR"` besides. Google Flights serves the page in
 * dollars for some sessions, and the 156 such fares recorded on 2026-07-19
 * therefore displayed as ₹58–₹105 — cheap-looking rupee fares rather than
 * visibly wrong numbers, which is why they went unnoticed for weeks.
 *
 * A null currency renders the bare number. Naming a unit nobody measured is the
 * fabrication this removes; showing the digits alone states exactly what is known.
 */
export function formatFare(
  amount: number | null | undefined,
  currency: string | null | undefined,
): string {
  if (amount == null || isNaN(amount)) return "Unavailable";
  const digits = Math.round(amount).toLocaleString("en-IN");
  if (currency == null) return digits;
  if (currency === "INR") return `₹${digits}`;
  if (currency === "USD") return `$${amount.toFixed(2)}`;
  return `${digits} ${currency}`;
}

/**
 * Confidence as a whole percentage, or null when there is no figure to show.
 *
 * This used to return 0 for a missing figure, which published a measurement —
 * "0% confident" — for a model nobody had measured. The backend now sends
 * `confidence_score: null` for exactly that case, so the absence has to survive
 * formatting: render it as text, never as a number.
 */
export function formatConfidence(rawConfidence: number | null | undefined): number | null {
  if (rawConfidence == null || isNaN(rawConfidence)) return null;
  // Convert once only: if > 1 (e.g. 95.0), treat as percentage. If <= 1 (e.g. 0.95), convert from ratio.
  const pct = rawConfidence > 1 ? rawConfidence : rawConfidence * 100;
  return Math.min(100, Math.max(0, Math.round(pct)));
}

export function formatConfidenceString(rawConfidence: number | null | undefined): string {
  const pct = formatConfidence(rawConfidence);
  return pct == null ? "Not measured" : `${pct}%`;
}

export function formatPercentage(pct: number | null | undefined): string {
  if (pct == null || isNaN(pct)) return "0.0%";
  return `${pct.toFixed(1)}%`;
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "N/A";
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  } catch {
    return dateStr;
  }
}

export interface ConfidenceRating {
  stars: string;
  label: string;
  tooltipText: string;
}

export function getConfidenceRating(rawConfidence: number | null | undefined): ConfidenceRating {
  const pct = formatConfidence(rawConfidence);

  // No recorded metric is not a low score. A star rating is a claim about how well
  // the model was validated, so with nothing to claim it must say so rather than
  // fall through to "Low Confidence" on a 0 it invented.
  if (pct == null) {
    return {
      stars: "—",
      label: "Not measured",
      tooltipText: "No evaluation metric is recorded for this forecast horizon, so no confidence can be reported."
    };
  }

  let stars = "★★★★★";
  let label = "Very High Confidence";

  if (pct < 50) {
    stars = "★★☆☆☆";
    label = "Low Confidence";
  } else if (pct < 75) {
    stars = "★★★☆☆";
    label = "Moderate Confidence";
  } else if (pct < 90) {
    stars = "★★★★☆";
    label = "High Confidence";
  }

  return {
    stars,
    label,
    tooltipText: "This confidence is based on historical model validation and current market quality."
  };
}
