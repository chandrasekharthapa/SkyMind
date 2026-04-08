"use client";

import { useState, useEffect, useRef, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import dynamic from "next/dynamic";
import NavBar from "@/components/layout/NavBar";
import { usePrediction } from "@/hooks/usePrediction";
import { useAlerts } from "@/hooks/useAlerts";
import { searchAirports, resolveCityToIATA } from "@/lib/api";
import type { Trend, Recommendation } from "@/types";

const PriceChart = dynamic(
  () => import("@/components/charts/PriceChart").then(m => m.PriceChart),
  {
    ssr: false,
    loading: () => (
      <div style={{ height: 220, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--grey3)", fontFamily: "var(--fm)", fontSize: ".75rem" }}>
        Loading chart…
      </div>
    ),
  }
);

const todayISO = new Date().toISOString().split("T")[0];

const TREND_CFG = {
  RISING:  { color: "var(--red)",  label: "Rising",  icon: "↑", badge: "badge-red" },
  FALLING: { color: "#16a34a",     label: "Falling", icon: "↓", badge: "badge-green" },
  STABLE:  { color: "#2563eb",     label: "Stable",  icon: "→", badge: "badge-off" },
} as Record<Trend, { color: string; label: string; icon: string; badge: string }>;

const REC_LABEL: Record<string, string> = {
  BOOK_NOW: "BOOK NOW", WAIT: "WAIT", MONITOR: "MONITOR",
};

/* ── Airport Dropdown ──────────────────────────────── */
function AirportDropdown({
  label, value, onChange, placeholder,
}: { label: string; value: string; onChange: (v: string) => void; placeholder: string }) {
  const [results, setResults] = useState<any[]>([]);
  const [open, setOpen]       = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const debRef  = useRef<any>(null);

  useEffect(() => {
    const fn = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", fn);
    return () => document.removeEventListener("mousedown", fn);
  }, []);

  const handleChange = useCallback((q: string) => {
    onChange(q);
    if (debRef.current) clearTimeout(debRef.current);
    debRef.current = setTimeout(async () => {
      if (q.length < 2) { setResults([]); setOpen(false); return; }
      try {
        const d = await searchAirports(q);
        setResults(d.slice(0, 8));
        setOpen(d.length > 0);
      } catch { setOpen(false); }
    }, 280);
  }, [onChange]);

  return (
    <div ref={wrapRef} style={{ position: "relative" }}>
      <label className="field-label">{label}</label>
      <input
        className="inp"
        value={value}
        onChange={e => handleChange(e.target.value)}
        placeholder={placeholder}
        autoComplete="off"
      />
      {open && results.length > 0 && (
        <div style={{
          position: "absolute", top: "calc(100% + 2px)", left: 0, right: 0,
          background: "var(--white)", border: "1.5px solid var(--black)",
          borderTop: "2px solid var(--red)", zIndex: 500, maxHeight: 260,
          overflowY: "auto", boxShadow: "var(--shadow-lg)",
        }}>
          {results.map((a: any) => (
            <div key={a.iata}
              onClick={() => { onChange(a.iata); setOpen(false); }}
              style={{ padding: "10px 14px", cursor: "pointer", borderBottom: "1px solid var(--grey1)", display: "flex", alignItems: "center", gap: 10 }}
              onMouseEnter={e => (e.currentTarget.style.background = "var(--off)")}
              onMouseLeave={e => (e.currentTarget.style.background = "var(--white)")}
            >
              <span style={{ fontFamily: "var(--fm)", color: "var(--red)", fontSize: ".72rem", fontWeight: 700, minWidth: 30 }}>{a.iata}</span>
              <div>
                <div style={{ fontSize: ".85rem", fontWeight: 600 }}>{a.city || a.label}</div>
                {a.airport && <div style={{ fontSize: ".68rem", color: "var(--grey3)" }}>{a.airport}</div>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Predict Content ───────────────────────────────── */
function PredictContent() {
  const searchParams = useSearchParams();
  const [origin,        setOrigin]        = useState(searchParams.get("origin") ?? "");
  const [destination,   setDestination]   = useState(searchParams.get("destination") ?? "");
  const [departureDate, setDepartureDate] = useState("");
  const [alertPrice,    setAlertPrice]    = useState("");
  const [alertEmail,    setAlertEmail]    = useState("");
  const [swapping,      setSwapping]      = useState(false);

  const { result, loading, error, predict, reset } = usePrediction();
  const { addAlert, loading: alertLoading } = useAlerts();
  const [alertMsg, setAlertMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    const org = searchParams.get("origin");
    const dst = searchParams.get("destination");
    if (org && dst) {
      setOrigin(resolveCityToIATA(org));
      setDestination(resolveCityToIATA(dst));
      predict({ origin: resolveCityToIATA(org), destination: resolveCityToIATA(dst), departure_date: undefined });
    }
  }, []);

  const swap = () => {
    setSwapping(true);
    setTimeout(() => setSwapping(false), 320);
    setOrigin(destination);
    setDestination(origin);
  };

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    const org = resolveCityToIATA(origin.trim());
    const dst = resolveCityToIATA(destination.trim());
    if (!org || !dst || org === dst) return;
    if (departureDate && departureDate < todayISO) return;
    reset();
    predict({ origin: org, destination: dst, departure_date: departureDate || undefined });
  }, [origin, destination, departureDate, predict, reset]);

  const handleSetAlert = useCallback(async () => {
    if (!origin || !destination) { setAlertMsg({ ok: false, text: "Fill in a route first." }); return; }
    if (!alertPrice || Number(alertPrice) < 500) { setAlertMsg({ ok: false, text: "Enter a valid target price (min ₹500)." }); return; }
    const res = await addAlert({
      origin: resolveCityToIATA(origin),
      destination: resolveCityToIATA(destination),
      target_price: Number(alertPrice),
      departure_date: departureDate || undefined,
      notify_email: alertEmail || undefined,
    });
    setAlertMsg({ ok: res.ok, text: res.message });
    if (res.ok) { setAlertPrice(""); setAlertEmail(""); }
    setTimeout(() => setAlertMsg(null), 4000);
  }, [origin, destination, alertPrice, alertEmail, departureDate, addAlert]);

  const tCfg      = result ? (TREND_CFG[result.trend] ?? TREND_CFG.STABLE) : null;
  const recLabel  = result ? (REC_LABEL[result.recommendation] ?? "MONITOR") : null;
  const bestDay   = result?.forecast?.reduce<typeof result.forecast[0] | null>((b, p) => (!b || p.price < b.price ? p : b), null);
  const worstDay  = result?.forecast?.reduce<typeof result.forecast[0] | null>((w, p) => (!w || p.price > w.price ? p : w), null);
  const org       = resolveCityToIATA(origin);
  const dst       = resolveCityToIATA(destination);

  return (
    <div style={{ paddingTop: "var(--nav-h)" }}>

      {/* Hero */}
      <div className="predict-hero">
        <div className="wrap">
          <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
            <div>
              <div style={{ fontFamily: "var(--fm)", fontSize: ".6rem", fontWeight: 600, letterSpacing: ".16em", textTransform: "uppercase", color: "rgba(255,255,255,.3)", marginBottom: 12 }}>
                AI Price Intelligence · 30-Day Forecast
              </div>
              <h1 className="predict-title">
                PRICE<br />PREDICT<em>ion.</em>
              </h1>
            </div>
            <div style={{ color: "rgba(255,255,255,.2)", fontFamily: "var(--fm)", fontSize: ".58rem", maxWidth: 160, textAlign: "right", lineHeight: 1.8 }}>
              XGBoost ML · Real-time inference<br />
              POST /predict · CI bands
            </div>
          </div>
        </div>
      </div>

      {/* Grid */}
      <div className="wrap">
        <div className="predict-grid">

          {/* ── Left column ── */}
          <div>
            {/* Search form */}
            <div className="predict-form-box" style={{ marginBottom: 16 }}>
              <div className="label" style={{ marginBottom: 14 }}>Route &amp; Date</div>
              <form onSubmit={handleSubmit}>

                {/* Origin / Swap / Destination — in a row */}
                <div className="predict-route-row">
                  <AirportDropdown
                    label="From"
                    value={origin}
                    onChange={setOrigin}
                    placeholder="Delhi / DEL"
                  />
                  <div style={{ display: "flex", alignItems: "flex-end" }}>
                    <button
                      type="button"
                      className="swap-btn"
                      onClick={swap}
                      title="Swap airports"
                      style={{
                        transform: swapping ? "rotate(180deg)" : "none",
                        transition: "transform .32s ease",
                      }}
                    >
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M7 16V4m0 0L3 8m4-4l4 4M17 8v12m0 0l4-4m-4 4l-4-4" />
                      </svg>
                    </button>
                  </div>
                  <AirportDropdown
                    label="To"
                    value={destination}
                    onChange={setDestination}
                    placeholder="Mumbai / BOM"
                  />
                </div>

                {/* Date */}
                <div style={{ marginBottom: 16 }}>
                  <label className="field-label">
                    Departure Date <span style={{ color: "var(--grey3)", fontWeight: 400, textTransform: "none", letterSpacing: 0 }}>(optional)</span>
                  </label>
                  <input
                    type="date"
                    className="inp"
                    value={departureDate}
                    min={todayISO}
                    onChange={e => setDepartureDate(e.target.value)}
                  />
                </div>

                <button type="submit" className="search-submit" disabled={loading}
                  style={{ gap: 8 }}>
                  {loading ? (
                    <>
                      <span style={{ width: 15, height: 15, border: "2px solid rgba(255,255,255,.35)", borderTop: "2px solid #fff", borderRadius: "50%", animation: "spin .7s linear infinite", display: "inline-block", flexShrink: 0 }} />
                      Analysing fares…
                    </>
                  ) : (
                    <>
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                      </svg>
                      Predict Price
                    </>
                  )}
                </button>

                {error && (
                  <div style={{ marginTop: 10, padding: "10px 12px", background: "rgba(232,25,26,.07)", border: "1px solid var(--red-rim)", color: "var(--red)", fontSize: ".8rem" }}>
                    {error}
                  </div>
                )}
              </form>
            </div>

            {/* Loading skeleton */}
            {loading && (
              <div>
                <div className="stat-trio" style={{ marginBottom: 14 }}>
                  {[0, 1, 2].map(i => (
                    <div key={i} style={{ background: "var(--white)", padding: 16 }}>
                      <div className="skel" style={{ height: 10, width: "60%", marginBottom: 10 }} />
                      <div className="skel" style={{ height: 26, width: "80%", marginBottom: 6 }} />
                      <div className="skel" style={{ height: 10, width: "50%" }} />
                    </div>
                  ))}
                </div>
                <div className="chart-area">
                  <div className="skel" style={{ height: 12, width: "40%", marginBottom: 14 }} />
                  <div className="skel" style={{ height: 200 }} />
                </div>
              </div>
            )}

            {/* Results */}
            {result && !loading && (
              <div>
                {/* Stat trio */}
                <div className="stat-trio">
                  <div className="stat-trio-item">
                    <div className="sti-label">Predicted Price</div>
                    <div className="sti-val">₹{result.predicted_price.toLocaleString("en-IN")}</div>
                    <div className="sti-sub">AI estimate</div>
                  </div>
                  <div className="stat-trio-item">
                    <div className="sti-label">Confidence</div>
                    <div className="sti-val"
                      style={{ color: result.confidence >= .8 ? "#16a34a" : result.confidence >= .6 ? "#d97706" : "var(--red)" }}>
                      {Math.round(result.confidence * 100)}%
                    </div>
                    <div className="sti-sub">Model certainty</div>
                  </div>
                  <div className="stat-trio-item">
                    <div className="sti-label">30-Day Change</div>
                    <div className="sti-val"
                      style={{ color: result.expected_change_percent >= 0 ? "var(--red)" : "#16a34a" }}>
                      {result.expected_change_percent >= 0 ? "+" : ""}{result.expected_change_percent.toFixed(1)}%
                    </div>
                    <div className="sti-sub">Expected shift</div>
                  </div>
                </div>

                {/* Best / Worst days */}
                {bestDay && worstDay && (
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 14 }}>
                    <div style={{ padding: "14px", background: "rgba(22,163,74,.05)", border: "1px solid rgba(22,163,74,.18)" }}>
                      <div style={{ fontFamily: "var(--fm)", fontSize: ".6rem", fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: "#16a34a", marginBottom: 5 }}>Best Day to Book</div>
                      <div style={{ fontFamily: "var(--fi)", fontStyle: "italic", fontSize: "1.2rem", color: "#16a34a" }}>
                        {new Date(bestDay.date).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
                      </div>
                      <div style={{ fontFamily: "var(--fm)", fontSize: ".7rem", color: "#16a34a", marginTop: 2 }}>₹{Math.round(bestDay.price).toLocaleString("en-IN")}</div>
                    </div>
                    <div style={{ padding: "14px", background: "rgba(232,25,26,.05)", border: "1px solid var(--red-rim)" }}>
                      <div style={{ fontFamily: "var(--fm)", fontSize: ".6rem", fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: "var(--red)", marginBottom: 5 }}>Peak Price Day</div>
                      <div style={{ fontFamily: "var(--fi)", fontStyle: "italic", fontSize: "1.2rem", color: "var(--red)" }}>
                        {new Date(worstDay.date).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
                      </div>
                      <div style={{ fontFamily: "var(--fm)", fontSize: ".7rem", color: "var(--red)", marginTop: 2 }}>₹{Math.round(worstDay.price).toLocaleString("en-IN")}</div>
                    </div>
                  </div>
                )}

                {/* Chart */}
                <div className="chart-area">
                  <div className="chart-title">30-Day Price Forecast</div>
                  <div className="chart-sub">
                    <span>{org} → {dst}</span>
                    {tCfg && <span className={`badge ${tCfg.badge}`}>{tCfg.icon} {tCfg.label.toUpperCase()}</span>}
                  </div>
                  <PriceChart forecast={result.forecast} trend={result.trend} />
                </div>

                {/* Alert form */}
                <div style={{ border: "1px solid var(--red-rim)", padding: 18, background: "var(--red-mist)", marginTop: 14 }}>
                  <div className="label" style={{ marginBottom: 12 }}>Set Price Alert</div>
                  <div className="form-2">
                    <div>
                      <label className="field-label">Target Price (₹)</label>
                      <input className="inp" type="number" min="500" value={alertPrice}
                        onChange={e => setAlertPrice(e.target.value)}
                        placeholder={result ? `e.g. ${Math.round(result.predicted_price * .9).toLocaleString("en-IN")}` : "e.g. 4500"} />
                    </div>
                    <div>
                      <label className="field-label">Email <span style={{ color: "var(--grey3)", fontWeight: 400 }}>(optional)</span></label>
                      <input className="inp" type="email" value={alertEmail}
                        onChange={e => setAlertEmail(e.target.value)}
                        placeholder="you@example.com" />
                    </div>
                  </div>
                  <button onClick={handleSetAlert} disabled={alertLoading} className="search-submit"
                    style={{ marginTop: 6 }}>
                    {alertLoading ? "Setting alert…" : "Set Price Alert →"}
                  </button>
                  {alertMsg && (
                    <div style={{ marginTop: 8, padding: "8px 12px", background: alertMsg.ok ? "#dcfce7" : "rgba(232,25,26,.07)", border: `1px solid ${alertMsg.ok ? "#bbf7d0" : "var(--red-rim)"}`, fontSize: ".76rem", color: alertMsg.ok ? "#166534" : "var(--red)", fontFamily: "var(--fm)" }}>
                      {alertMsg.text}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Empty state */}
            {!result && !loading && (
              <div style={{ border: "1px solid var(--grey1)", padding: "48px 20px", textAlign: "center", background: "var(--white)" }}>
                <div style={{ width: 44, height: 44, background: "var(--off)", border: "1px solid var(--grey1)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 16px", color: "var(--grey3)" }}>
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
                </div>
                <div style={{ fontFamily: "var(--fd)", fontSize: "1.3rem", letterSpacing: ".04em", color: "var(--black)", marginBottom: 6 }}>NO PREDICTION YET</div>
                <div style={{ fontSize: ".78rem", color: "var(--grey3)", fontFamily: "var(--fm)", lineHeight: 1.7 }}>
                  Enter a route and press Predict Price<br />to see the 30-day AI forecast
                </div>
              </div>
            )}
          </div>

          {/* ── Right column — Recommendation Panel ── */}
          <div className="rec-panel">
            {result && !loading ? (
              <div className="rec-card">
                <div className="rec-header">
                  <span className="rec-label">AI Recommendation</span>
                  {tCfg && <span className={`badge ${tCfg.badge}`}>{tCfg.icon} {tCfg.label.toUpperCase()}</span>}
                </div>
                <div className="rec-body">
                  <div className="rec-rec"
                    style={{ color: result.recommendation === "BOOK_NOW" ? "var(--red)" : result.recommendation === "WAIT" ? "#854d0e" : "var(--black)" }}>
                    {recLabel}
                  </div>
                  <div className="rec-reason">{result.reason}</div>
                  {/* Confidence bar */}
                  <div style={{ marginBottom: 14 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                      <span style={{ fontFamily: "var(--fm)", fontSize: ".62rem", color: "var(--grey3)" }}>MODEL CONFIDENCE</span>
                      <span style={{ fontFamily: "var(--fm)", fontSize: ".62rem", fontWeight: 700, color: result.confidence >= .8 ? "#16a34a" : result.confidence >= .6 ? "#d97706" : "var(--red)" }}>
                        {Math.round(result.confidence * 100)}%
                      </span>
                    </div>
                    <div className="conf-bar-wrap" style={{ height: 4 }}>
                      <div className="conf-bar-fill"
                        style={{ width: `${result.confidence * 100}%`, background: result.confidence >= .8 ? "#16a34a" : result.confidence >= .6 ? "#d97706" : "var(--red)" }} />
                    </div>
                  </div>
                  <div className="rec-stat"><span className="rec-stat-label">Prob. price increase</span><span className="rec-stat-val" style={{ color: result.probability_increase > .6 ? "var(--red)" : "#16a34a" }}>{Math.round(result.probability_increase * 100)}%</span></div>
                  <div className="rec-stat"><span className="rec-stat-label">Model confidence</span><span className="rec-stat-val">{Math.round(result.confidence * 100)}%</span></div>
                  <div className="rec-stat"><span className="rec-stat-label">30-day forecast</span><span className="rec-stat-val" style={{ color: result.expected_change_percent >= 0 ? "var(--red)" : "#16a34a" }}>{result.expected_change_percent >= 0 ? "+" : ""}{result.expected_change_percent.toFixed(1)}%</span></div>
                  <div className="rec-stat"><span className="rec-stat-label">AI price</span><span className="rec-stat-val">₹{result.predicted_price.toLocaleString("en-IN")}</span></div>
                  <div className="rec-stat"><span className="rec-stat-label">Trend</span><span className="rec-stat-val" style={{ color: tCfg?.color }}>{tCfg?.icon} {result.trend}</span></div>
                  {origin && destination && (
                    <a href={`/flights?origin=${org}&destination=${dst}&departure_date=${departureDate || new Date(Date.now() + 7 * 86400000).toISOString().split("T")[0]}&adults=1&cabin_class=ECONOMY`}
                      className="search-submit" style={{ marginTop: 14, textDecoration: "none", display: "flex" }}>
                      Search Flights →
                    </a>
                  )}
                </div>
              </div>
            ) : loading ? (
              <div className="rec-card">
                <div className="rec-header"><span className="rec-label">Analysing…</span></div>
                <div style={{ padding: 18 }}>
                  {[80, 55, 70, 45, 65].map((w, i) => (
                    <div key={i} className="skel" style={{ height: 11, width: `${w}%`, marginBottom: 13 }} />
                  ))}
                </div>
              </div>
            ) : (
              <div style={{ border: "1px solid var(--grey1)", padding: "28px 18px", textAlign: "center", color: "var(--grey3)", fontFamily: "var(--fm)", fontSize: ".72rem", lineHeight: 1.8, background: "var(--white)" }}>
                Enter a route and click<br /><strong style={{ color: "var(--black)" }}>Predict Price</strong><br />to see the AI forecast.
              </div>
            )}

            {/* How it works */}
            <div style={{ border: "1px solid var(--grey1)", padding: "16px", marginTop: 14, background: "var(--white)" }}>
              <div className="label" style={{ marginBottom: 12 }}>How it works</div>
              {[
                { n: "01", t: "XGBoost ML Model",       d: "900-estimator model trained on real fare data with live weighting." },
                { n: "02", t: "Route-Seeded Forecast",   d: "Deterministic 30-day projection with confidence intervals." },
                { n: "03", t: "Smart Recommendation",    d: "Book Now, Wait, or Monitor — derived from trend and probability." },
              ].map((s, idx, arr) => (
                <div key={s.n} style={{ display: "flex", gap: 10, paddingBottom: idx < arr.length - 1 ? 11 : 0, marginBottom: idx < arr.length - 1 ? 11 : 0, borderBottom: idx < arr.length - 1 ? "1px solid var(--grey1)" : "none" }}>
                  <span style={{ fontFamily: "var(--fm)", fontSize: ".58rem", color: "var(--red)", fontWeight: 700, flexShrink: 0, paddingTop: 2 }}>{s.n}</span>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: ".8rem", color: "var(--black)", marginBottom: 2 }}>{s.t}</div>
                    <div style={{ fontSize: ".7rem", color: "var(--grey4)", lineHeight: 1.6 }}>{s.d}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

export default function PredictPage() {
  return (
    <>
      <NavBar />
      <Suspense fallback={
        <div style={{ paddingTop: 100, textAlign: "center", color: "var(--grey3)", fontFamily: "var(--fm)", fontSize: ".8rem" }}>
          Loading…
        </div>
      }>
        <PredictContent />
      </Suspense>
    </>
  );
}
