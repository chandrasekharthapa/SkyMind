"use client";

import { useState, useEffect, useRef, Suspense, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import dynamic from "next/dynamic";
import { motion, AnimatePresence } from "framer-motion";
import NavBar from "@/components/layout/NavBar";
import { usePrediction } from "@/hooks/usePrediction";
import { useAlerts } from "@/hooks/useAlerts";
import { searchAirports, resolveCityToIATA } from "@/lib/api";
import type { Trend, Recommendation } from "@/types";
import { toast } from "sonner";

const PriceChart = dynamic(
  () => import("@/components/charts/PriceChart").then((m) => m.PriceChart),
  {
    ssr: false,
    loading: () => (
      <div style={{
        height: 260,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: "var(--slate)",
        fontFamily: "var(--font-mono)",
        fontSize: 12,
        gap: 8,
      }}>
        <span style={{ width: 16, height: 16, border: "2px solid var(--bone)", borderTop: "2px solid var(--crimson)", borderRadius: "50%", animation: "spin 0.8s linear infinite", display: "inline-block" }} />
        Loading chart...
      </div>
    ),
  }
);

const todayISO = new Date().toISOString().split("T")[0];

// ── Trend config ─────────────────────────────────────────────────────
const TREND_CFG: Record<Trend, {
  bg: string; color: string; border: string; label: string; indicator: string;
  cardBg: string; accent: string;
}> = {
  RISING: {
    bg: "rgba(225,29,72,0.08)", color: "#E11D48", border: "rgba(225,29,72,0.2)",
    label: "Rising", indicator: "↑",
    cardBg: "rgba(225,29,72,0.03)", accent: "#BE123C",
  },
  FALLING: {
    bg: "rgba(22,163,74,0.08)", color: "#16A34A", border: "rgba(22,163,74,0.2)",
    label: "Falling", indicator: "↓",
    cardBg: "rgba(22,163,74,0.03)", accent: "#15803D",
  },
  STABLE: {
    bg: "rgba(37,99,235,0.08)", color: "#2563EB", border: "rgba(37,99,235,0.2)",
    label: "Stable", indicator: "→",
    cardBg: "rgba(37,99,235,0.03)", accent: "#1D4ED8",
  },
};

const REC_CFG: Record<Recommendation | "MONITOR", {
  bg: string; color: string; border: string; label: string;
}> = {
  BOOK_NOW: { bg: "rgba(225,29,72,0.08)", color: "#BE123C", border: "rgba(225,29,72,0.25)", label: "Book Now" },
  WAIT:     { bg: "rgba(234,179,8,0.08)",  color: "#854D0E", border: "rgba(234,179,8,0.25)",  label: "Wait" },
  MONITOR:  { bg: "rgba(37,99,235,0.08)",  color: "#1D4ED8", border: "rgba(37,99,235,0.25)",  label: "Monitor" },
};

// ── Framer Motion variants ────────────────────────────────────────────
const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  show: (i = 0) => ({
    opacity: 1, y: 0,
    transition: { duration: 0.45, delay: i * 0.08, ease: [0.0, 0.0, 0.2, 1] },
  }),
};

const stagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08 } },
};

// ── Confidence Gauge (SVG arc with gradient) ─────────────────────────
function ConfidenceGauge({ value }: { value: number }) {
  // value is already 0–1 from the hook
  const pct = Math.min(100, Math.max(0, Math.round(value * 100)));
  const color = pct >= 80 ? "#16A34A" : pct >= 60 ? "#D97706" : "#E11D48";

  const r = 38;
  const cx = 46;
  const cy = 46;
  // Arc: 270° sweep starting at -225° (bottom-left), going clockwise
  const startAngle = -225 * (Math.PI / 180);
  const sweep = 270 * (Math.PI / 180);
  const endAngle = startAngle + (pct / 100) * sweep;

  const x1 = cx + r * Math.cos(startAngle);
  const y1 = cy + r * Math.sin(startAngle);
  const x2 = cx + r * Math.cos(endAngle);
  const y2 = cy + r * Math.sin(endAngle);
  const largeArc = (pct / 100) * 270 > 180 ? 1 : 0;

  // Full track arc
  const trackEnd = startAngle + sweep;
  const tx = cx + r * Math.cos(trackEnd);
  const ty = cy + r * Math.sin(trackEnd);
  const trackPath = `M ${cx + r * Math.cos(startAngle)} ${cy + r * Math.sin(startAngle)} A ${r} ${r} 0 1 1 ${tx} ${ty}`;
  const valuePath = pct > 0
    ? `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`
    : "";

  return (
    <div style={{ textAlign: "center", flexShrink: 0, width: 92 }}>
      <div style={{ position: "relative", width: 92, height: 92 }}>
        <svg width={92} height={92} viewBox="0 0 92 92">
          <defs>
            <linearGradient id={`gauge-grad-${pct}`} x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor={pct >= 80 ? "#22C55E" : pct >= 60 ? "#F59E0B" : "#F43F5E"} />
              <stop offset="100%" stopColor={color} />
            </linearGradient>
          </defs>
          {/* Track */}
          <path d={trackPath} fill="none" stroke="var(--bone)" strokeWidth="7" strokeLinecap="round" />
          {/* Value arc */}
          {valuePath && (
            <path
              d={valuePath}
              fill="none"
              stroke={`url(#gauge-grad-${pct})`}
              strokeWidth="7"
              strokeLinecap="round"
              style={{
                strokeDasharray: `${(pct / 100) * 270 * (Math.PI / 180) * r} 1000`,
                transition: "stroke-dasharray 1.2s cubic-bezier(0.34, 1.56, 0.64, 1)",
              }}
            />
          )}
        </svg>
        <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", paddingBottom: 8 }}>
          <span style={{
            fontFamily: "var(--font-serif)",
            fontStyle: "italic",
            fontSize: "1.5rem",
            color,
            lineHeight: 1,
            fontWeight: 400,
          }}>
            {pct}
          </span>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.5rem", color: "var(--slate)", letterSpacing: ".1em" }}>%</span>
        </div>
      </div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: "0.58rem", color: "var(--slate)", marginTop: 4, letterSpacing: ".1em", textTransform: "uppercase" }}>
        Confidence
      </div>
    </div>
  );
}

// ── Airport Autocomplete Field ────────────────────────────────────────
interface AirportFieldProps {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  disabled?: boolean;
}

function AirportField({ label, value, onChange, placeholder, disabled }: AirportFieldProps) {
  const [results, setResults] = useState<{ iata: string; label: string; city?: string; airport?: string }[]>([]);
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

  const handleChange = useCallback((q: string) => {
    onChange(q);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      if (q.length < 2) { setResults([]); setOpen(false); return; }
      try {
        const data = await searchAirports(q);
        setResults(data.slice(0, 8) as unknown as typeof results);
        setOpen(data.length > 0);
      } catch {
        setOpen(false);
      }
    }, 280);
  }, [onChange]);

  return (
    <div ref={wrapRef} style={{ position: "relative", marginBottom: 12 }}>
      <label className="field-label">{label}</label>
      <input
        className="inp"
        value={value}
        onChange={(e) => handleChange(e.target.value)}
        placeholder={placeholder}
        autoComplete="off"
        disabled={disabled}
      />
      <AnimatePresence>
        {open && results.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.15 }}
            style={{
              position: "absolute", top: "100%", left: 0, right: 0,
              background: "var(--bg-raised)",
              border: "1.5px solid var(--crimson)",
              borderTop: "none",
              zIndex: 500,
              maxHeight: 240,
              overflowY: "auto",
              boxShadow: "0 12px 32px rgba(28,25,23,0.12)",
              borderRadius: "0 0 10px 10px",
            }}
          >
            {results.map((a) => (
              <div
                key={a.iata}
                onClick={() => { onChange(a.iata); setOpen(false); }}
                style={{ padding: "10px 14px", cursor: "pointer", borderBottom: "1px solid var(--bone)", transition: "background 100ms" }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "var(--ivory)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "var(--bg-raised)")}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ fontFamily: "var(--font-mono)", color: "var(--crimson)", fontSize: ".78rem", fontWeight: 700, minWidth: 32 }}>{a.iata}</span>
                  <div>
                    <div style={{ fontSize: ".88rem", fontWeight: 600, color: "var(--charcoal)" }}>{(a as unknown as Record<string, string>).city || a.label}</div>
                    {(a as unknown as Record<string, string>).airport && (
                      <div style={{ fontSize: ".72rem", color: "var(--slate)" }}>{(a as unknown as Record<string, string>).airport}</div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── Loading Skeleton ──────────────────────────────────────────────────
function PredictionSkeleton() {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 1, background: "var(--bone)", border: "1.5px solid var(--bone)", borderRadius: 16, overflow: "hidden", marginBottom: 16 }}>
        {[0, 1, 2].map(i => (
          <div key={i} style={{ background: "var(--bg-raised)", padding: 16 }}>
            <div className="skel" style={{ height: 10, width: "60%", marginBottom: 12 }} />
            <div className="skel" style={{ height: 28, width: "80%", marginBottom: 6 }} />
            <div className="skel" style={{ height: 10, width: "50%" }} />
          </div>
        ))}
      </div>
      <div style={{ background: "var(--bg-raised)", border: "1.5px solid var(--bone)", borderRadius: 16, padding: 24, marginBottom: 16 }}>
        <div className="skel" style={{ height: 14, width: "40%", marginBottom: 18 }} />
        <div className="skel" style={{ height: 220 }} />
      </div>
    </motion.div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────
function PredictContent() {
  const searchParams = useSearchParams();

  const [origin, setOrigin] = useState(searchParams.get("origin") ?? "");
  const [destination, setDestination] = useState(searchParams.get("destination") ?? "");
  const [departureDate, setDepartureDate] = useState("");
  const [alertPrice, setAlertPrice] = useState("");
  const [alertEmail, setAlertEmail] = useState("");
  const [searchedRoute, setSearchedRoute] = useState({ origin: "", destination: "" });

  const { result, loading, error, predict, reset } = usePrediction();
  const { addAlert, loading: alertLoading } = useAlerts();

  // Auto-search from URL params
  useEffect(() => {
    const org = searchParams.get("origin");
    const dst = searchParams.get("destination");
    if (org && dst) {
      const resolvedOrg = resolveCityToIATA(org);
      const resolvedDst = resolveCityToIATA(dst);
      setOrigin(resolvedOrg);
      setDestination(resolvedDst);
      setSearchedRoute({ origin: resolvedOrg, destination: resolvedDst });
      predict({ origin: resolvedOrg, destination: resolvedDst, departure_date: undefined });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    const org = resolveCityToIATA(origin.trim());
    const dst = resolveCityToIATA(destination.trim());
    if (!org || !dst) { toast.error("Please enter origin and destination."); return; }
    if (org === dst) { toast.error("Origin and destination cannot be the same."); return; }
    if (departureDate && departureDate < todayISO) { toast.error("Please select a future date."); return; }
    reset();
    setSearchedRoute({ origin: org, destination: dst });
    predict({ origin: org, destination: dst, departure_date: departureDate || undefined });
  }, [origin, destination, departureDate, predict, reset]);

  const handleSetAlert = useCallback(async () => {
    if (!origin || !destination) { toast.error("Fill in a route first."); return; }
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
  }, [origin, destination, alertPrice, alertEmail, departureDate, addAlert]);

  // Derived values — all safe because predictPrice() in api.ts guarantees types
  const trendCfg = result ? (TREND_CFG[result.trend] ?? TREND_CFG.STABLE) : null;
  const recKey = result?.recommendation ?? "MONITOR";
  const recCfg = REC_CFG[recKey as keyof typeof REC_CFG] ?? REC_CFG.MONITOR;

  const bestDay = result?.forecast?.reduce<typeof result.forecast[0] | null>(
    (best, p) => (!best || p.price < best.price ? p : best), null
  );
  const worstDay = result?.forecast?.reduce<typeof result.forecast[0] | null>(
    (worst, p) => (!worst || p.price > worst.price ? p : worst), null
  );

  return (
    <div>
      <NavBar />
      <div style={{ paddingTop: 60 }}>

        {/* ── Hero ── */}
        <div className="predict-hero">
          <div className="wrap">
            <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", flexWrap: "wrap", gap: 16 }}>
              <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: ".65rem", fontWeight: 600, letterSpacing: ".16em", textTransform: "uppercase", color: "rgba(255,255,255,.3)", marginBottom: 14 }}>
                  AI Price Intelligence · 30-Day Forecast
                </div>
                <h1 className="predict-title">
                  PRICE<br />PREDICT<em>ion.</em>
                </h1>
              </motion.div>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.3, duration: 0.6 }}
                style={{ color: "rgba(255,255,255,.3)", fontFamily: "var(--font-mono)", fontSize: ".62rem", maxWidth: 200, textAlign: "right", lineHeight: 1.8 }}
              >
                XGBoost ML · Real-time inference<br />
                Confidence bands · Live market data
              </motion.div>
            </div>
          </div>
        </div>

        {/* ── Grid ── */}
        <div className="wrap">
          <div className="predict-grid">

            {/* ── Left Column ── */}
            <div>
              {/* Search Form */}
              <motion.form
                onSubmit={handleSubmit}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.45 }}
                style={{
                  background: "rgba(255,255,255,0.88)",
                  border: "1px solid rgba(225,29,72,0.10)",
                  borderRadius: 16,
                  padding: 24,
                  marginBottom: 16,
                  backdropFilter: "blur(12px)",
                  WebkitBackdropFilter: "blur(12px)",
                  boxShadow: "0 4px 24px rgba(28,25,23,0.06)",
                }}
              >
                <div style={{ fontFamily: "var(--font-mono)", fontSize: ".6rem", fontWeight: 700, letterSpacing: ".14em", textTransform: "uppercase", color: "var(--slate)", marginBottom: 18 }}>
                  Route & Date
                </div>
                <AirportField label="From" value={origin} onChange={setOrigin} placeholder="Delhi / DEL" disabled={loading} />
                <AirportField label="To" value={destination} onChange={setDestination} placeholder="Mumbai / BOM" disabled={loading} />
                <div style={{ marginBottom: 18 }}>
                  <label className="field-label">
                    Departure Date{" "}
                    <span style={{ color: "var(--ash)", fontWeight: 400 }}>(optional)</span>
                  </label>
                  <input
                    type="date"
                    className="inp"
                    value={departureDate}
                    min={todayISO}
                    onChange={(e) => setDepartureDate(e.target.value)}
                    disabled={loading}
                  />
                </div>
                <button type="submit" className="search-submit" disabled={loading}>
                  {loading ? (
                    <>
                      <span style={{ width: 16, height: 16, border: "2px solid rgba(255,255,255,.35)", borderTop: "2px solid #fff", borderRadius: "50%", animation: "spin 0.75s linear infinite", display: "inline-block", flexShrink: 0 }} />
                      Analysing fares...
                    </>
                  ) : "Predict Price →"}
                </button>
                <AnimatePresence>
                  {error && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      style={{ marginTop: 12, padding: "10px 14px", background: "rgba(225,29,72,.07)", border: "1px solid var(--crimson)", color: "var(--crimson)", fontSize: ".82rem", borderRadius: 8 }}
                    >
                      {error}
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.form>

              {/* Results */}
              <AnimatePresence mode="wait">
                {loading && (
                  <motion.div key="skeleton" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                    <PredictionSkeleton />
                  </motion.div>
                )}

                {result && !loading && (
                  <motion.div
                    key="results"
                    variants={stagger}
                    initial="hidden"
                    animate="show"
                  >
                    {/* Stat Trio */}
                    <motion.div variants={fadeUp} custom={0} className="stat-trio" style={{ marginBottom: 16 }}>
                      <div className="stat-trio-item">
                        <div className="sti-label">Predicted Price</div>
                        <div className="sti-val" style={{ color: "var(--charcoal)" }}>
                          ₹{result.predicted_price.toLocaleString("en-IN")}
                        </div>
                        <div className="sti-sub">AI estimate</div>
                      </div>
                      <div className="stat-trio-item">
                        <div className="sti-label">Confidence</div>
                        <div className="sti-val" style={{
                          color: result.confidence >= 0.8 ? "#16A34A" : result.confidence >= 0.6 ? "#D97706" : "#E11D48"
                        }}>
                          {Math.round(result.confidence * 100)}%
                        </div>
                        <div className="sti-sub">Model certainty</div>
                      </div>
                      <div className="stat-trio-item">
                        <div className="sti-label">30-Day Change</div>
                        <div className="sti-val" style={{ color: result.expected_change_percent >= 0 ? "var(--crimson)" : "#16A34A" }}>
                          {result.expected_change_percent >= 0 ? "+" : ""}{result.expected_change_percent.toFixed(2)}%
                        </div>
                        <div className="sti-sub">Expected shift</div>
                      </div>
                    </motion.div>

                    {/* Best / Worst Day */}
                    {bestDay && worstDay && (
                      <motion.div variants={fadeUp} custom={1} style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 16 }}>
                        <div style={{ padding: "14px 16px", background: "rgba(22,163,74,.05)", border: "1px solid rgba(22,163,74,.2)", borderRadius: 12 }}>
                          <div style={{ fontFamily: "var(--font-mono)", fontSize: ".58rem", fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: "#16A34A", marginBottom: 6 }}>
                            Best Day to Book
                          </div>
                          <div style={{ fontFamily: "var(--font-serif)", fontStyle: "italic", fontSize: "1.2rem", color: "#16A34A", fontWeight: 400 }}>
                            {new Date(bestDay.date).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
                          </div>
                          <div style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", color: "#16A34A", marginTop: 2 }}>
                            ₹{Math.round(bestDay.price).toLocaleString("en-IN")}
                          </div>
                        </div>
                        <div style={{ padding: "14px 16px", background: "rgba(225,29,72,.05)", border: "1px solid rgba(225,29,72,.2)", borderRadius: 12 }}>
                          <div style={{ fontFamily: "var(--font-mono)", fontSize: ".58rem", fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: "var(--crimson)", marginBottom: 6 }}>
                            Peak Price Day
                          </div>
                          <div style={{ fontFamily: "var(--font-serif)", fontStyle: "italic", fontSize: "1.2rem", color: "var(--crimson)", fontWeight: 400 }}>
                            {new Date(worstDay.date).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
                          </div>
                          <div style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", color: "var(--crimson)", marginTop: 2 }}>
                            ₹{Math.round(worstDay.price).toLocaleString("en-IN")}
                          </div>
                        </div>
                      </motion.div>
                    )}

                    {/* Chart */}
                    <motion.div variants={fadeUp} custom={2} className="chart-area">
                      <div className="chart-title">30-Day Price Forecast</div>
                      <div className="chart-sub">
                        <span style={{ fontFamily: "var(--font-mono)", fontSize: ".68rem", color: "var(--graphite)", letterSpacing: ".04em" }}>
                          {searchedRoute.origin} → {searchedRoute.destination}
                        </span>
                        {trendCfg && (
                          <span style={{
                            padding: "2px 10px",
                            background: trendCfg.bg,
                            color: trendCfg.color,
                            border: `1px solid ${trendCfg.border}`,
                            fontFamily: "var(--font-mono)",
                            fontSize: ".62rem",
                            fontWeight: 700,
                            letterSpacing: ".06em",
                            borderRadius: 4,
                          }}>
                            {trendCfg.indicator} {trendCfg.label.toUpperCase()}
                          </span>
                        )}
                      </div>
                      <PriceChart forecast={result.forecast} trend={result.trend} />
                    </motion.div>

                    {/* Price Alert Form */}
                    <motion.div
                      variants={fadeUp}
                      custom={3}
                      style={{
                        border: "1px solid rgba(225,29,72,0.12)",
                        padding: 20,
                        background: "rgba(225,29,72,0.02)",
                        marginTop: 16,
                        borderRadius: 16,
                      }}
                    >
                      <div style={{ fontFamily: "var(--font-mono)", fontSize: ".6rem", fontWeight: 700, letterSpacing: ".14em", textTransform: "uppercase", color: "var(--slate)", marginBottom: 14 }}>
                        Set Price Alert
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
                            placeholder={result ? `e.g. ${Math.round(result.predicted_price * 0.9).toLocaleString("en-IN")}` : "e.g. 4500"}
                          />
                        </div>
                        <div>
                          <label className="field-label">Email <span style={{ color: "var(--ash)" }}>(optional)</span></label>
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
                        style={{ width: "100%", justifyContent: "center", marginTop: 4, opacity: alertLoading ? 0.7 : 1 }}
                      >
                        {alertLoading ? "Setting alert..." : "Set Price Alert →"}
                      </button>
                    </motion.div>
                  </motion.div>
                )}

                {!result && !loading && (
                  <motion.div
                    key="empty"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    style={{
                      border: "1.5px solid var(--bone)",
                      padding: "52px 24px",
                      textAlign: "center",
                      background: "var(--bg-raised)",
                      borderRadius: 16,
                    }}
                  >
                    <div style={{ width: 56, height: 56, background: "var(--ivory)", border: "1px solid var(--bone)", borderRadius: 16, display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 20px" }}>
                      <svg width={22} height={22} viewBox="0 0 24 24" fill="none" stroke="var(--ash)" strokeWidth={1.5}>
                        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                      </svg>
                    </div>
                    <div style={{ fontFamily: "var(--font-sans)", fontWeight: 700, fontSize: "1.1rem", color: "var(--charcoal)", marginBottom: 8, letterSpacing: "-0.02em" }}>
                      No prediction yet
                    </div>
                    <div style={{ fontSize: ".82rem", color: "var(--slate)", lineHeight: 1.7, fontFamily: "var(--font-mono)" }}>
                      Enter a route and press Predict Price<br />
                      to see the 30-day AI forecast
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* ── Right Column — Recommendation Panel ── */}
            <div className="rec-panel">
              <AnimatePresence mode="wait">
                {result && !loading ? (
                  <motion.div
                    key="rec-result"
                    initial={{ opacity: 0, x: 12 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 12 }}
                    transition={{ duration: 0.4, ease: [0.0, 0.0, 0.2, 1] }}
                  >
                    <div className="rec-card">
                      {/* Header */}
                      <div className="rec-header">
                        <span className="rec-label">AI Recommendation</span>
                        {trendCfg && (
                          <span style={{
                            fontFamily: "var(--font-mono)", fontSize: ".62rem", fontWeight: 700,
                            color: trendCfg.color, background: trendCfg.bg,
                            padding: "2px 10px", border: `1px solid ${trendCfg.border}`, borderRadius: 4,
                          }}>
                            {trendCfg.indicator} {trendCfg.label.toUpperCase()}
                          </span>
                        )}
                      </div>

                      <div className="rec-body">
                        {/* Gauge + Recommendation */}
                        <div style={{ display: "flex", alignItems: "center", gap: 16, paddingBottom: 16, borderBottom: "1px solid var(--bone)", marginBottom: 16 }}>
                          <ConfidenceGauge value={result.confidence} />
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{
                              padding: "10px 14px",
                              background: recCfg.bg,
                              border: `1px solid ${recCfg.border}`,
                              borderRadius: 10,
                              marginBottom: 10,
                            }}>
                              <div style={{ fontFamily: "var(--font-sans)", fontWeight: 800, fontSize: "1.15rem", color: recCfg.color, lineHeight: 1, letterSpacing: "-0.02em" }}>
                                {recCfg.label}
                              </div>
                            </div>
                            <div style={{ fontFamily: "var(--font-mono)", fontSize: ".68rem", color: "var(--graphite)", lineHeight: 1.65 }}>
                              {result.reason}
                            </div>
                          </div>
                        </div>

                        {/* Stats */}
                        <div className="rec-stat">
                          <span className="rec-stat-label">Prob. of price increase</span>
                          <span className="rec-stat-val" style={{ color: result.probability_increase > 0.6 ? "var(--crimson)" : "#16A34A" }}>
                            {Math.round(result.probability_increase * 100)}%
                          </span>
                        </div>
                        <div className="rec-stat">
                          <span className="rec-stat-label">Model confidence</span>
                          <span className="rec-stat-val">{Math.round(result.confidence * 100)}%</span>
                        </div>
                        <div className="rec-stat">
                          <span className="rec-stat-label">30-day forecast</span>
                          <span className="rec-stat-val" style={{ color: result.expected_change_percent >= 0 ? "var(--crimson)" : "#16A34A" }}>
                            {result.expected_change_percent >= 0 ? "+" : ""}{result.expected_change_percent.toFixed(2)}%
                          </span>
                        </div>
                        <div className="rec-stat">
                          <span className="rec-stat-label">Current AI price</span>
                          <span className="rec-stat-val">₹{result.predicted_price.toLocaleString("en-IN")}</span>
                        </div>
                        <div className="rec-stat" style={{ borderBottom: "none" }}>
                          <span className="rec-stat-label">Trend</span>
                          <span className="rec-stat-val" style={{ color: trendCfg?.color }}>
                            {trendCfg?.indicator} {result.trend}
                          </span>
                        </div>

                        {/* Signal Banners */}
                        <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 8 }}>
                          {result.probability_increase > 0.65 && (
                            <motion.div
                              initial={{ opacity: 0, y: 6 }}
                              animate={{ opacity: 1, y: 0 }}
                              style={{ padding: "10px 12px", background: "rgba(225,29,72,.05)", border: "1px solid rgba(225,29,72,.18)", fontSize: ".75rem", color: "#BE123C", display: "flex", gap: 8, borderRadius: 8, alignItems: "flex-start" }}
                            >
                              <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} style={{ flexShrink: 0, marginTop: 1 }}>
                                <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" /><polyline points="17 6 23 6 23 12" />
                              </svg>
                              <span>High probability of price rise — consider booking now to lock in a lower fare.</span>
                            </motion.div>
                          )}
                          {result.confidence >= 0.85 && (
                            <motion.div
                              initial={{ opacity: 0, y: 6 }}
                              animate={{ opacity: 1, y: 0 }}
                              transition={{ delay: 0.1 }}
                              style={{ padding: "10px 12px", background: "rgba(22,163,74,.05)", border: "1px solid rgba(22,163,74,.18)", fontSize: ".75rem", color: "#15803D", display: "flex", gap: 8, borderRadius: 8, alignItems: "flex-start" }}
                            >
                              <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} style={{ flexShrink: 0, marginTop: 1 }}>
                                <polyline points="20 6 9 17 4 12" />
                              </svg>
                              <span>High confidence prediction — strong market signal from the XGBoost model.</span>
                            </motion.div>
                          )}
                        </div>

                        {/* Search Flights CTA */}
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
                  </motion.div>
                ) : loading ? (
                  <motion.div
                    key="rec-loading"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    style={{ border: "1.5px solid var(--bone)", borderRadius: 16, overflow: "hidden" }}
                  >
                    <div style={{ background: "var(--charcoal)", padding: "14px 20px", display: "flex", alignItems: "center", gap: 10 }}>
                      <div className="live-dot" />
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: ".62rem", color: "rgba(255,255,255,.4)", letterSpacing: ".1em", textTransform: "uppercase" }}>
                        Analysing intelligence...
                      </span>
                    </div>
                    <div style={{ padding: 20 }}>
                      {[80, 55, 70, 45, 65].map((w, i) => (
                        <div key={i} className="skel" style={{ height: 12, width: `${w}%`, marginBottom: 14 }} />
                      ))}
                    </div>
                  </motion.div>
                ) : (
                  <motion.div
                    key="rec-empty"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    style={{
                      border: "1px solid var(--bone)",
                      padding: "32px 20px",
                      textAlign: "center",
                      color: "var(--slate)",
                      fontFamily: "var(--font-mono)",
                      fontSize: ".75rem",
                      lineHeight: 1.7,
                      background: "var(--bg-raised)",
                      borderRadius: 16,
                    }}
                  >
                    <div style={{ width: 44, height: 44, background: "var(--ivory)", border: "1px solid var(--bone)", borderRadius: 12, display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 16px" }}>
                      <svg width={18} height={18} viewBox="0 0 24 24" fill="none" stroke="var(--ash)" strokeWidth={1.5}>
                        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                      </svg>
                    </div>
                    Enter a route and click<br />
                    <strong style={{ color: "var(--charcoal)", fontWeight: 700 }}>Predict Price</strong><br />
                    to see the AI forecast &amp; recommendation.
                  </motion.div>
                )}
              </AnimatePresence>

              {/* How It Works */}
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2, duration: 0.45 }}
                style={{ border: "1.5px solid var(--bone)", padding: "16px 18px", marginTop: 16, background: "var(--bg-raised)", borderRadius: 16 }}
              >
                <div style={{ fontFamily: "var(--font-mono)", fontSize: ".58rem", fontWeight: 700, letterSpacing: ".14em", textTransform: "uppercase", color: "var(--slate)", marginBottom: 14 }}>
                  How it works
                </div>
                {[
                  { n: "01", t: "XGBoost ML Model", d: "Trained on real fare data. 2026 live weighting prioritises recent market signals." },
                  { n: "02", t: "Route-Seeded Forecast", d: "Deterministic 30-day projection with statistical confidence intervals." },
                  { n: "03", t: "Smart Recommendation", d: "Book Now, Wait, or Monitor — derived from trend direction and probability score." },
                ].map((s, idx, arr) => (
                  <div key={s.n} style={{ display: "flex", gap: 12, paddingBottom: idx < arr.length - 1 ? 12 : 0, marginBottom: idx < arr.length - 1 ? 12 : 0, borderBottom: idx < arr.length - 1 ? "1px solid var(--bone)" : "none" }}>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: ".58rem", color: "var(--crimson)", fontWeight: 700, flexShrink: 0, paddingTop: 2 }}>{s.n}</span>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: ".82rem", color: "var(--charcoal)", marginBottom: 2 }}>{s.t}</div>
                      <div style={{ fontSize: ".72rem", color: "var(--graphite)", lineHeight: 1.6 }}>{s.d}</div>
                    </div>
                  </div>
                ))}
              </motion.div>
            </div>
          </div>
        </div>
      </div>

      <style jsx global>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes fadeUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes livePulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
        @keyframes radialPulse {
          0% { box-shadow: 0 0 0 0 rgba(225, 29, 72, 0.5); }
          70% { box-shadow: 0 0 0 8px rgba(225, 29, 72, 0); }
          100% { box-shadow: 0 0 0 0 rgba(225, 29, 72, 0); }
        }
      `}</style>
    </div>
  );
}

export default function PredictPage() {
  return (
    <Suspense fallback={
      <div style={{ paddingTop: 120, textAlign: "center", color: "var(--slate)", fontFamily: "var(--font-mono)", fontSize: ".8rem" }}>
        Loading...
      </div>
    }>
      <PredictContent />
    </Suspense>
  );
}
