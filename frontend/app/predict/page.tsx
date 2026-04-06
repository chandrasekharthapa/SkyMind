"use client";

import { useState, useEffect, useRef, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import dynamic from "next/dynamic";
import NavBar from "@/components/layout/NavBar";
import { usePrediction } from "@/hooks/usePrediction";
import { useAlerts } from "@/hooks/useAlerts";
import { searchAirports, resolveCityToIATA } from "@/lib/api";
import type { Trend } from "@/types";
import { toast } from "sonner";

const PriceChart = dynamic(
  () => import("@/components/charts/PriceChart").then((m) => m.PriceChart),
  { ssr: false, loading: () => <div className="h-64 flex items-center justify-center text-gray-400 text-sm">Loading chart…</div> }
);

const todayISO = new Date().toISOString().split("T")[0];

// ─── Trend config ─────────────────────────────────────────────────────
const TREND_CFG: Record<Trend, { bg: string; color: string; border: string; label: string; icon: string }> = {
  RISING:  { bg: "rgba(232,25,26,.07)",  color: "#e8191a", border: "rgba(232,25,26,.2)",   label: "↑ RISING",  icon: "📈" },
  FALLING: { bg: "rgba(22,163,74,.07)",  color: "#16a34a", border: "rgba(22,163,74,.2)",   label: "↓ FALLING", icon: "📉" },
  STABLE:  { bg: "rgba(37,99,235,.07)",  color: "#2563eb", border: "rgba(37,99,235,.2)",   label: "→ STABLE",  icon: "📊" },
};

const REC_CFG: Record<string, { bg: string; color: string; border: string; icon: string }> = {
  BOOK_NOW: { bg: "rgba(232,25,26,.08)", color: "#c01415", border: "rgba(232,25,26,.3)", icon: "🔥" },
  WAIT:     { bg: "rgba(234,179,8,.08)", color: "#854d0e", border: "rgba(234,179,8,.3)", icon: "⏳" },
  MONITOR:  { bg: "rgba(37,99,235,.08)", color: "#1d4ed8", border: "rgba(37,99,235,.3)", icon: "👁️" },
};

// ─── Confidence gauge ─────────────────────────────────────────────────
function ConfidenceGauge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 80 ? "#16a34a" : pct >= 60 ? "#d97706" : "#e8191a";
  const r = 36, cx = 44, cy = 44;
  const circ = 2 * Math.PI * r;
  const dash = (pct / 100) * circ;

  return (
    <div style={{ textAlign: "center" }}>
      <div style={{ position: "relative", width: 88, height: 88, margin: "0 auto" }}>
        <svg width={88} height={88} style={{ transform: "rotate(-90deg)" }}>
          <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--grey1)" strokeWidth={8} />
          <circle
            cx={cx} cy={cy} r={r}
            fill="none"
            stroke={color}
            strokeWidth={8}
            strokeDasharray={`${dash} ${circ - dash}`}
            strokeLinecap="round"
            style={{ transition: "stroke-dasharray 1s ease" }}
          />
        </svg>
        <div style={{
          position: "absolute", inset: 0,
          display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center",
        }}>
          <span style={{ fontFamily: "var(--fd)", fontSize: "1.3rem", color, lineHeight: 1 }}>{pct}</span>
          <span style={{ fontFamily: "var(--fm)", fontSize: ".5rem", color: "var(--grey3)", letterSpacing: ".08em" }}>%</span>
        </div>
      </div>
      <div style={{ fontFamily: "var(--fm)", fontSize: ".6rem", color: "var(--grey3)", marginTop: 6, letterSpacing: ".08em", textTransform: "uppercase" }}>
        Confidence
      </div>
    </div>
  );
}

// ─── Airport autocomplete field ───────────────────────────────────────
interface AirportFieldProps {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
}

function AirportField({ label, value, onChange, placeholder }: AirportFieldProps) {
  const [results, setResults] = useState<{ iata: string; label: string; airport: string }[]>([]);
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleChange = (q: string) => {
    onChange(q);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      if (q.length < 2) { setResults([]); setOpen(false); return; }
      const data = await searchAirports(q);
      setResults(data.slice(0, 8) as any);
      setOpen(data.length > 0);
    }, 280);
  };

  return (
    <div ref={wrapRef} style={{ position: "relative", marginBottom: 12 }}>
      <label className="field-label">{label}</label>
      <input
        className="inp"
        value={value}
        onChange={(e) => handleChange(e.target.value)}
        placeholder={placeholder}
        autoComplete="off"
        style={{ textTransform: value.length === 3 ? "uppercase" : "none" }}
      />
      {open && results.length > 0 && (
        <div style={{
          position: "absolute", top: "100%", left: 0, right: 0,
          background: "#fff", border: "1px solid var(--black)",
          borderTop: "none", zIndex: 500, maxHeight: 240, overflowY: "auto",
          boxShadow: "0 8px 24px rgba(19,18,16,.12)",
        }}>
          {results.map((a) => (
            <div
              key={a.iata}
              onClick={() => { onChange(a.iata); setOpen(false); }}
              style={{ padding: "10px 14px", cursor: "pointer", borderBottom: "1px solid var(--grey1)" }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "var(--off)")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "#fff")}
            >
              <strong style={{ fontFamily: "var(--fm)", color: "var(--red)", fontSize: ".78rem" }}>{a.iata}</strong>
              <span style={{ marginLeft: 8, fontSize: ".88rem" }}>{(a as any).city || a.label}</span>
              <div style={{ fontSize: ".72rem", color: "var(--grey3)" }}>{a.airport}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────
function PredictContent() {
  const searchParams = useSearchParams();
  const [origin, setOrigin] = useState(searchParams.get("origin") ?? "");
  const [destination, setDestination] = useState(searchParams.get("destination") ?? "");
  const [departureDate, setDepartureDate] = useState("");
  const [alertPrice, setAlertPrice] = useState("");
  const [alertEmail, setAlertEmail] = useState("");

  const { result, loading, error, predict, reset } = usePrediction();
  const { addAlert, loading: alertLoading } = useAlerts();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const org = resolveCityToIATA(origin);
    const dst = resolveCityToIATA(destination);
    if (!org || !dst) { toast.error("Please enter origin and destination."); return; }
    if (org === dst) { toast.error("Origin and destination cannot be the same."); return; }
    if (departureDate && departureDate < todayISO) { toast.error("Please select a future departure date."); return; }
    reset();
    predict({ origin: org, destination: dst, departure_date: departureDate || undefined });
  }

  async function handleSetAlert() {
    if (!origin || !destination) { toast.error("Fill in route first."); return; }
    if (!alertPrice || Number(alertPrice) < 500) { toast.error("Enter a valid target price (min ₹500)."); return; }
    const res = await addAlert({
      origin: resolveCityToIATA(origin),
      destination: resolveCityToIATA(destination),
      target_price: Number(alertPrice),
      departure_date: departureDate || undefined,
      notify_email: alertEmail || undefined,
    });
    if (res.ok) { toast.success(res.message); setAlertPrice(""); setAlertEmail(""); }
    else toast.error(res.message);
  }

  const trendCfg = result ? (TREND_CFG[result.trend] ?? TREND_CFG.STABLE) : null;
  const recCfg = result ? (REC_CFG[result.recommendation] ?? REC_CFG.MONITOR) : null;
  const recLabel = result ? result.recommendation.replace(/_/g, " ") : "";

  // Detect best booking window from forecast
  const bestDay = result?.forecast?.reduce((best, p) => (!best || p.price < best.price ? p : best), null as typeof result.forecast[0] | null);
  const worstDay = result?.forecast?.reduce((worst, p) => (!worst || p.price > worst.price ? p : worst), null as typeof result.forecast[0] | null);

  return (
    <div>
      <NavBar />
      <div style={{ paddingTop: 60 }}>

        {/* Hero */}
        <div className="predict-hero">
          <div className="wrap">
            <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", flexWrap: "wrap", gap: 16 }}>
              <div>
                <div className="label" style={{ color: "rgba(255,255,255,.4)", marginBottom: 12 }}>
                  AI Price Intelligence · 30-Day Forecast · 2026
                </div>
                <h1 className="predict-title">
                  PRICE<br />PREDICT<em>ion.</em>
                </h1>
              </div>
              <div style={{ color: "rgba(255,255,255,.4)", fontFamily: "var(--fm)", fontSize: ".68rem", maxWidth: 220, textAlign: "right", lineHeight: 1.6 }}>
                XGBoost ML · Route-seeded forecasts<br />Confidence intervals · Live market data
              </div>
            </div>
          </div>
        </div>

        <div className="wrap">
          <div className="predict-grid">

            {/* Left — Form + Results */}
            <div>

              {/* Search form */}
              <form
                onSubmit={handleSubmit}
                style={{ border: "1px solid var(--grey1)", padding: 20, marginBottom: 16, background: "var(--white)" }}
              >
                <div style={{ fontFamily: "var(--fm)", fontSize: ".65rem", fontWeight: 700, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--grey3)", marginBottom: 16 }}>
                  Route &amp; Date
                </div>
                <AirportField label="From" value={origin} onChange={setOrigin} placeholder="Delhi / DEL" />
                <AirportField label="To" value={destination} onChange={setDestination} placeholder="Mumbai / BOM" />
                <div style={{ marginBottom: 14 }}>
                  <label className="field-label">Departure Date (optional)</label>
                  <input
                    type="date" className="inp"
                    value={departureDate} min={todayISO}
                    onChange={(e) => setDepartureDate(e.target.value)}
                  />
                </div>
                <button type="submit" className="search-submit" disabled={loading} style={{ opacity: loading ? 0.7 : 1 }}>
                  {loading ? (
                    <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ width: 16, height: 16, border: "2px solid rgba(255,255,255,.3)", borderTop: "2px solid #fff", borderRadius: "50%", animation: "spin 0.8s linear infinite", display: "inline-block" }} />
                      Analysing fares with AI…
                    </span>
                  ) : "Predict Price →"}
                </button>
                {error && (
                  <div style={{ marginTop: 10, padding: "10px 14px", background: "rgba(232,25,26,.07)", border: "1px solid var(--red)", color: "var(--red)", fontSize: ".82rem" }}>
                    ⚠️ {error}
                  </div>
                )}
              </form>

              {/* Results */}
              {result && (
                <>
                  {/* Stat trio */}
                  <div className="stat-trio" style={{ marginBottom: 16 }}>
                    <div className="stat-trio-item">
                      <div className="sti-label">Predicted Price</div>
                      <div className="sti-val" style={{ color: "var(--black)" }}>
                        ₹{result.predicted_price.toLocaleString("en-IN")}
                      </div>
                      <div className="sti-sub">Today's AI estimate</div>
                    </div>
                    <div className="stat-trio-item">
                      <div className="sti-label">Confidence</div>
                      <div className="sti-val" style={{ color: result.confidence >= 0.8 ? "#16a34a" : result.confidence >= 0.6 ? "#d97706" : "#e8191a" }}>
                        {Math.round(result.confidence * 100)}%
                      </div>
                      <div className="sti-sub">Model certainty</div>
                    </div>
                    <div className="stat-trio-item">
                      <div className="sti-label">30-Day Δ</div>
                      <div className="sti-val" style={{ color: result.expected_change_percent >= 0 ? "var(--red)" : "#16a34a" }}>
                        {result.expected_change_percent >= 0 ? "+" : ""}{result.expected_change_percent}%
                      </div>
                      <div className="sti-sub">Expected change</div>
                    </div>
                  </div>

                  {/* Best / Worst booking window */}
                  {bestDay && worstDay && (
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 16 }}>
                      <div style={{ padding: "12px 14px", background: "rgba(22,163,74,.06)", border: "1px solid rgba(22,163,74,.2)", borderRadius: 0 }}>
                        <div style={{ fontFamily: "var(--fm)", fontSize: ".6rem", fontWeight: 700, letterSpacing: ".10em", textTransform: "uppercase", color: "#16a34a", marginBottom: 6 }}>📅 Best Day to Book</div>
                        <div style={{ fontFamily: "var(--fd)", fontSize: "1.1rem", color: "#16a34a" }}>
                          {new Date(bestDay.date).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
                        </div>
                        <div style={{ fontFamily: "var(--fm)", fontSize: ".72rem", color: "#16a34a", marginTop: 2 }}>
                          ₹{Math.round(bestDay.price).toLocaleString("en-IN")}
                        </div>
                      </div>
                      <div style={{ padding: "12px 14px", background: "rgba(232,25,26,.06)", border: "1px solid rgba(232,25,26,.2)", borderRadius: 0 }}>
                        <div style={{ fontFamily: "var(--fm)", fontSize: ".6rem", fontWeight: 700, letterSpacing: ".10em", textTransform: "uppercase", color: "var(--red)", marginBottom: 6 }}>⚠️ Peak Price Day</div>
                        <div style={{ fontFamily: "var(--fd)", fontSize: "1.1rem", color: "var(--red)" }}>
                          {new Date(worstDay.date).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
                        </div>
                        <div style={{ fontFamily: "var(--fm)", fontSize: ".72rem", color: "var(--red)", marginTop: 2 }}>
                          ₹{Math.round(worstDay.price).toLocaleString("en-IN")}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Chart */}
                  <div className="chart-area">
                    <div className="chart-title">30-Day Price Forecast</div>
                    <div className="chart-sub">
                      <span style={{ fontFamily: "var(--fm)", fontSize: ".7rem", color: "var(--grey4)", letterSpacing: ".04em" }}>
                        {origin.toUpperCase()} → {destination.toUpperCase()}
                      </span>
                      {trendCfg && (
                        <span style={{
                          marginLeft: 10, padding: "2px 8px",
                          background: trendCfg.bg, color: trendCfg.color,
                          border: `1px solid ${trendCfg.border}`,
                          fontFamily: "var(--fm)", fontSize: ".65rem", fontWeight: 700, letterSpacing: ".06em",
                        }}>
                          {trendCfg.icon} {trendCfg.label}
                        </span>
                      )}
                    </div>
                    <PriceChart forecast={result.forecast} trend={result.trend} />
                  </div>

                  {/* Alert form */}
                  <div style={{ border: "1px solid var(--grey1)", padding: 18, background: "var(--off)", marginTop: 16 }}>
                    <div style={{ fontFamily: "var(--fm)", fontSize: ".65rem", fontWeight: 700, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--grey3)", marginBottom: 14 }}>
                      🔔 Set Price Alert
                    </div>
                    <div className="form-2">
                      <div>
                        <label className="field-label">Target Price (₹)</label>
                        <input
                          className="inp" type="number" min="500"
                          value={alertPrice}
                          onChange={(e) => setAlertPrice(e.target.value)}
                          placeholder={`e.g. ${Math.round(result.predicted_price * 0.9).toLocaleString("en-IN")}`}
                        />
                      </div>
                      <div>
                        <label className="field-label">Email (optional)</label>
                        <input
                          className="inp" type="email"
                          value={alertEmail}
                          onChange={(e) => setAlertEmail(e.target.value)}
                          placeholder="you@example.com"
                        />
                      </div>
                    </div>
                    <button
                      onClick={handleSetAlert}
                      disabled={alertLoading}
                      className="btn btn-primary"
                      style={{ width: "100%", justifyContent: "center", marginTop: 4, opacity: alertLoading ? 0.7 : 1 }}
                    >
                      {alertLoading ? "Setting alert…" : "Set Alert →"}
                    </button>
                  </div>
                </>
              )}

              {/* Empty state */}
              {!result && !loading && (
                <div style={{ border: "1px solid var(--grey1)", padding: "40px 24px", textAlign: "center", background: "var(--off)", marginTop: 0 }}>
                  <div style={{ fontFamily: "var(--fd)", fontSize: "2rem", color: "var(--grey2)", marginBottom: 8, letterSpacing: ".04em" }}>AWAITING ROUTE</div>
                  <div style={{ fontSize: ".82rem", color: "var(--grey3)", lineHeight: 1.7, fontFamily: "var(--fm)" }}>
                    Enter a route and press<br /><strong style={{ color: "var(--black)" }}>Predict Price</strong> to see AI forecast
                  </div>
                </div>
              )}
            </div>

            {/* Right — Recommendation panel */}
            <div className="rec-panel">
              {result ? (
                <div className="rec-card">
                  {/* Header */}
                  <div className="rec-header">
                    <span className="rec-label">AI Recommendation</span>
                    {trendCfg && (
                      <span style={{
                        fontFamily: "var(--fm)", fontSize: ".65rem", fontWeight: 700,
                        color: trendCfg.color, background: trendCfg.bg,
                        padding: "2px 7px", border: `1px solid ${trendCfg.border}`,
                      }}>
                        {trendCfg.label}
                      </span>
                    )}
                  </div>

                  <div className="rec-body">
                    {/* Confidence Gauge */}
                    <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "12px 0 16px", borderBottom: "1px solid var(--grey1)", marginBottom: 16 }}>
                      <ConfidenceGauge value={result.confidence} />
                      <div style={{ flex: 1 }}>
                        {recCfg && (
                          <div style={{
                            padding: "8px 12px",
                            background: recCfg.bg,
                            border: `1px solid ${recCfg.border}`,
                            marginBottom: 8,
                          }}>
                            <div style={{ fontFamily: "var(--fd)", fontSize: "1.4rem", color: recCfg.color, lineHeight: 1 }}>
                              {recCfg.icon} {recLabel}
                            </div>
                          </div>
                        )}
                        <div style={{ fontFamily: "var(--fm)", fontSize: ".68rem", color: "var(--grey4)", lineHeight: 1.5 }}>
                          {result.reason}
                        </div>
                      </div>
                    </div>

                    {/* Stats */}
                    <div className="rec-stat">
                      <span className="rec-stat-label">Prob. of price increase</span>
                      <span className="rec-stat-val" style={{ color: result.probability_increase > 0.6 ? "var(--red)" : "#16a34a" }}>
                        {Math.round(result.probability_increase * 100)}%
                      </span>
                    </div>
                    <div className="rec-stat">
                      <span className="rec-stat-label">Model confidence</span>
                      <span className="rec-stat-val">{Math.round(result.confidence * 100)}%</span>
                    </div>
                    <div className="rec-stat">
                      <span className="rec-stat-label">30-day forecast</span>
                      <span className="rec-stat-val" style={{ color: result.expected_change_percent >= 0 ? "var(--red)" : "#16a34a" }}>
                        {result.expected_change_percent >= 0 ? "+" : ""}{result.expected_change_percent}%
                      </span>
                    </div>
                    <div className="rec-stat">
                      <span className="rec-stat-label">Current AI price</span>
                      <span className="rec-stat-val">₹{result.predicted_price.toLocaleString("en-IN")}</span>
                    </div>
                    <div className="rec-stat" style={{ borderBottom: "none" }}>
                      <span className="rec-stat-label">Trend</span>
                      <span className="rec-stat-val" style={{ color: trendCfg?.color }}>
                        {result.trend}
                      </span>
                    </div>

                    {/* Market alerts */}
                    <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 8 }}>
                      {result.probability_increase > 0.65 && (
                        <div style={{ padding: "8px 10px", background: "rgba(232,25,26,.06)", border: "1px solid rgba(232,25,26,.2)", fontSize: ".75rem", color: "#c01415", display: "flex", gap: 6 }}>
                          <span>🔥</span>
                          <span>High chance of price rise — consider booking soon.</span>
                        </div>
                      )}
                      {result.confidence >= 0.85 && (
                        <div style={{ padding: "8px 10px", background: "rgba(22,163,74,.06)", border: "1px solid rgba(22,163,74,.2)", fontSize: ".75rem", color: "#15803d", display: "flex", gap: 6 }}>
                          <span>✅</span>
                          <span>High confidence prediction — strong market signal.</span>
                        </div>
                      )}
                    </div>

                    {/* Quick search link */}
                    {origin && destination && (
                      <a
                        href={`/flights?origin=${resolveCityToIATA(origin)}&destination=${resolveCityToIATA(destination)}&departure_date=${departureDate || new Date(Date.now() + 7 * 86400000).toISOString().split("T")[0]}&adults=1&cabin_class=ECONOMY`}
                        className="btn btn-primary"
                        style={{ width: "100%", justifyContent: "center", marginTop: 16, textDecoration: "none" }}
                      >
                        Search Flights →
                      </a>
                    )}
                  </div>
                </div>
              ) : (
                <div style={{ border: "1px solid var(--grey1)", padding: "28px 20px", textAlign: "center", color: "var(--grey3)", fontFamily: "var(--fm)", fontSize: ".78rem", lineHeight: 1.7, background: "var(--white)" }}>
                  Enter a route and click<br />
                  <strong style={{ color: "var(--black)" }}>Predict Price</strong><br />
                  to see the AI forecast &amp; recommendation.
                </div>
              )}

              {/* How it works */}
              <div style={{ border: "1px solid var(--grey1)", padding: "16px 18px", marginTop: 16, background: "var(--off)" }}>
                <div style={{ fontFamily: "var(--fm)", fontSize: ".6rem", fontWeight: 700, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--grey3)", marginBottom: 12 }}>
                  How it works
                </div>
                {[
                  { n: "01", t: "XGBoost ML Model", d: "Trained on millions of fare datapoints with 2026 live weighting." },
                  { n: "02", t: "Route-Seeded Forecast", d: "Deterministic 30-day projection with confidence intervals." },
                  { n: "03", t: "Smart Recommendation", d: "Book Now, Wait, or Monitor — based on trend + probability." },
                ].map((s) => (
                  <div key={s.n} style={{ display: "flex", gap: 12, paddingBottom: 10, marginBottom: 10, borderBottom: "1px solid var(--grey1)" }}>
                    <span style={{ fontFamily: "var(--fm)", fontSize: ".6rem", color: "var(--red)", fontWeight: 700, flexShrink: 0, paddingTop: 2 }}>{s.n}</span>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: ".82rem", color: "var(--black)", marginBottom: 2 }}>{s.t}</div>
                      <div style={{ fontSize: ".75rem", color: "var(--grey4)", lineHeight: 1.5 }}>{s.d}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      <style jsx global>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}

export default function PredictPage() {
  return (
    <Suspense fallback={
      <div style={{ paddingTop: 120, textAlign: "center", color: "var(--grey3)", fontFamily: "var(--fm)", fontSize: ".85rem" }}>
        Loading…
      </div>
    }>
      <PredictContent />
    </Suspense>
  );
}
