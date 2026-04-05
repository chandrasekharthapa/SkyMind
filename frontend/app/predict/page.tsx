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
  { ssr: false }
);

const todayISO = new Date().toISOString().split("T")[0];

// ─────────────────────────────────────────────────────────────────────
// Sub-component: airport autocomplete field
// ─────────────────────────────────────────────────────────────────────

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
      if (q.length < 2) { setResults([]); return; }
      const data = await searchAirports(q);
      setResults(data.slice(0, 8));
      setOpen(data.length > 0);
    }, 280);
  };

  return (
    <div ref={wrapRef} style={{ position: "relative", marginBottom: "12px" }}>
      <label className="field-label">{label}</label>
      <input
        className="inp"
        value={value}
        onChange={(e) => handleChange(e.target.value)}
        placeholder={placeholder}
        autoComplete="off"
      />
      {open && results.length > 0 && (
        <div style={{
          position: "absolute", top: "100%", left: 0, right: 0,
          background: "#fff", border: "1px solid var(--black)", borderTop: "none",
          zIndex: 500, maxHeight: "240px", overflowY: "auto",
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
              <strong style={{ fontFamily: "var(--fm)", color: "var(--red)", fontSize: ".78rem" }}>
                {a.iata}
              </strong>
              <span style={{ marginLeft: "8px", fontSize: ".88rem" }}>{a.label}</span>
              <div style={{ fontSize: ".72rem", color: "var(--grey3)" }}>{a.airport}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Trend badge
// ─────────────────────────────────────────────────────────────────────

const TREND_BADGE: Record<Trend, { bg: string; color: string; label: string }> = {
  RISING:  { bg: "rgba(232,25,26,.08)", color: "var(--red)",    label: "↑ RISING" },
  FALLING: { bg: "rgba(22,101,52,.08)", color: "#166534",       label: "↓ FALLING" },
  STABLE:  { bg: "rgba(37,99,235,.08)", color: "#2563eb",       label: "→ STABLE" },
};

// ─────────────────────────────────────────────────────────────────────
// Main page content
// ─────────────────────────────────────────────────────────────────────

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
    reset();
    predict({ origin: org, destination: dst, departure_date: departureDate });
  }

  async function handleSetAlert() {
    if (!origin || !destination || !alertPrice) {
      toast.error("Fill in route and target price first.");
      return;
    }
    const res = await addAlert({
      origin: resolveCityToIATA(origin),
      destination: resolveCityToIATA(destination),
      target_price: Number(alertPrice),
      departure_date: departureDate || undefined,
      notify_email: alertEmail || undefined,
    });
    if (res.ok) {
      toast.success(res.message);
      setAlertPrice("");
      setAlertEmail("");
    } else {
      toast.error(res.message);
    }
  }

  const trendCfg = result ? (TREND_BADGE[result.trend] ?? TREND_BADGE.STABLE) : null;

  return (
    <div>
      <NavBar />
      <div style={{ paddingTop: "60px" }}>

        {/* Hero */}
        <div className="predict-hero">
          <div className="wrap">
            <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", flexWrap: "wrap", gap: "16px" }}>
              <div>
                <div className="label" style={{ color: "rgba(255,255,255,.4)", marginBottom: "12px" }}>AI Price Intelligence · 30-Day Forecast</div>
                <h1 className="predict-title">PRICE<br />PREDICT<em>ion.</em></h1>
              </div>
              <div style={{ color: "rgba(255,255,255,.5)", fontFamily: "var(--fm)", fontSize: ".72rem", maxWidth: "240px", textAlign: "right" }}>
                Deterministic ML model · Route-seeded forecasts · Confidence bands
              </div>
            </div>
          </div>
        </div>

        <div className="wrap">
          <div className="predict-grid">

            {/* Left — Form + Result */}
            <div>

              {/* Form */}
              <form onSubmit={handleSubmit} style={{ border: "1px solid var(--grey1)", padding: "20px", marginBottom: "16px", background: "var(--white)" }}>
                <div style={{ fontFamily: "var(--fm)", fontSize: ".65rem", fontWeight: 700, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--grey3)", marginBottom: "16px" }}>Route</div>
                <AirportField label="From" value={origin} onChange={setOrigin} placeholder="Delhi / DEL" />
                <AirportField label="To" value={destination} onChange={setDestination} placeholder="Mumbai / BOM" />
                <div style={{ marginBottom: "14px" }}>
                  <label className="field-label">Departure Date (optional)</label>
                  <input
                    type="date"
                    className="inp"
                    value={departureDate}
                    min={todayISO}
                    onChange={(e) => setDepartureDate(e.target.value)}
                  />
                </div>
                <button type="submit" className="search-submit" disabled={loading}>
                  {loading ? "Analysing fares with AI…" : "Predict Price →"}
                </button>
                {error && (
                  <div style={{ marginTop: "10px", padding: "10px 14px", background: "rgba(232,25,26,.07)", border: "1px solid var(--red)", color: "var(--red)", fontSize: ".82rem" }}>
                    ⚠️ {error}
                  </div>
                )}
              </form>

              {/* Result card */}
              {result && (
                <>
                  {/* Stat trio */}
                  <div className="stat-trio" style={{ marginBottom: "16px" }}>
                    <div className="stat-trio-item">
                      <div className="sti-label">Predicted Price</div>
                      <div className="sti-val" style={{ color: "var(--black)" }}>
                        ₹{result.predicted_price.toLocaleString("en-IN")}
                      </div>
                      <div className="sti-sub">Today's estimate</div>
                    </div>
                    <div className="stat-trio-item">
                      <div className="sti-label">Confidence</div>
                      <div className="sti-val">{Math.round(result.confidence * 100)}%</div>
                      <div className="sti-sub">Model certainty</div>
                    </div>
                    <div className="stat-trio-item">
                      <div className="sti-label">Expected Δ</div>
                      <div className="sti-val" style={{ color: result.expected_change_percent >= 0 ? "var(--red)" : "#166534" }}>
                        {result.expected_change_percent >= 0 ? "+" : ""}{result.expected_change_percent}%
                      </div>
                      <div className="sti-sub">30-day change</div>
                    </div>
                  </div>

                  {/* Chart */}
                  <div className="chart-area">
                    <div className="chart-title">30-Day Price Forecast</div>
                    <div className="chart-sub">
                      {origin.toUpperCase()} → {destination.toUpperCase()}
                      {trendCfg && (
                        <span style={{ marginLeft: "10px", padding: "2px 8px", background: trendCfg.bg, color: trendCfg.color, fontFamily: "var(--fm)", fontSize: ".65rem", fontWeight: 700, letterSpacing: ".06em" }}>
                          {trendCfg.label}
                        </span>
                      )}
                    </div>
                    <PriceChart forecast={result.forecast} trend={result.trend} />
                  </div>

                  {/* Price alert form */}
                  <div style={{ border: "1px solid var(--grey1)", padding: "18px", background: "var(--off)" }}>
                    <div style={{ fontFamily: "var(--fm)", fontSize: ".65rem", fontWeight: 700, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--grey3)", marginBottom: "14px" }}>
                      🔔 Set Price Alert
                    </div>
                    <div className="form-2">
                      <div>
                        <label className="field-label">Target Price (₹)</label>
                        <input
                          className="inp"
                          type="number"
                          min="500"
                          value={alertPrice}
                          onChange={(e) => setAlertPrice(e.target.value)}
                          placeholder="e.g. 4500"
                        />
                      </div>
                      <div>
                        <label className="field-label">Email (optional)</label>
                        <input
                          className="inp"
                          type="email"
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
                      style={{ width: "100%", justifyContent: "center", marginTop: "4px" }}
                    >
                      {alertLoading ? "Setting alert…" : "Set Alert →"}
                    </button>
                  </div>
                </>
              )}
            </div>

            {/* Right — Recommendation panel */}
            <div className="rec-panel">
              {result ? (
                <div className="rec-card">
                  <div className="rec-header">
                    <span className="rec-label">AI Recommendation</span>
                    {trendCfg && (
                      <span style={{ fontFamily: "var(--fm)", fontSize: ".65rem", fontWeight: 700, color: trendCfg.color }}>
                        {trendCfg.label}
                      </span>
                    )}
                  </div>
                  <div className="rec-body">
                    <div className="rec-rec" style={{ color: result.recommendation === "BOOK_NOW" ? "var(--red)" : result.recommendation === "WAIT" ? "#166534" : "var(--black)" }}>
                      {result.recommendation.replace(/_/g, " ")}
                    </div>
                    <div className="rec-reason">{result.reason}</div>

                    <div className="rec-stat">
                      <span className="rec-stat-label">Probability of increase</span>
                      <span className="rec-stat-val">{Math.round(result.probability_increase * 100)}%</span>
                    </div>
                    <div className="rec-stat">
                      <span className="rec-stat-label">Confidence</span>
                      <span className="rec-stat-val">{Math.round(result.confidence * 100)}%</span>
                    </div>
                    <div className="rec-stat">
                      <span className="rec-stat-label">30-day forecast</span>
                      <span className="rec-stat-val" style={{ color: result.expected_change_percent >= 0 ? "var(--red)" : "#166534" }}>
                        {result.expected_change_percent >= 0 ? "+" : ""}{result.expected_change_percent}%
                      </span>
                    </div>
                    <div className="rec-stat" style={{ borderBottom: "none" }}>
                      <span className="rec-stat-label">Predicted price now</span>
                      <span className="rec-stat-val">₹{result.predicted_price.toLocaleString("en-IN")}</span>
                    </div>
                  </div>
                </div>
              ) : (
                <div style={{ border: "1px solid var(--grey1)", padding: "28px 20px", textAlign: "center", color: "var(--grey3)", fontFamily: "var(--fm)", fontSize: ".78rem", lineHeight: 1.7 }}>
                  Enter a route and click<br />
                  <strong>Predict Price</strong><br />
                  to see the AI forecast.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function PredictPage() {
  return (
    <Suspense fallback={
      <div style={{ paddingTop: "120px", textAlign: "center", color: "var(--grey3)", fontFamily: "var(--fm)", fontSize: ".85rem" }}>
        Loading…
      </div>
    }>
      <PredictContent />
    </Suspense>
  );
}
