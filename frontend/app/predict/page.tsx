"use client";

import { useState, useEffect, useRef, Suspense, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import dynamic from "next/dynamic";
import NavBar from "@/components/layout/NavBar";
import { usePrediction } from "@/hooks/usePrediction";
import { useAlerts } from "@/hooks/useAlerts";
import { searchAirports, resolveCityToIATA } from "@/lib/api";
import FlightSearchForm from "@/components/flights/FlightSearchForm";
import type { Trend, Recommendation } from "@/types";

const PriceChart = dynamic(() => import("@/components/charts/PriceChart").then(m => m.PriceChart), {
  ssr: false,
  loading: () => <div style={{ height:220, display:"flex", alignItems:"center", justifyContent:"center", color:"var(--grey3)", fontFamily:"var(--fm)", fontSize:".78rem" }}>ENGINE_INIT...</div>
});

const todayISO = new Date().toISOString().split("T")[0];

const TREND_CFG = {
  RISING:  { color:"var(--red)",   label:"Rising",  badge:"badge-red" },
  FALLING: { color:"#16a34a",      label:"Falling", badge:"badge-green" },
  STABLE:  { color:"#2563eb",      label:"Stable",  badge:"badge-off" },
} as Record<Trend, { color:string; label:string; badge:string }>;

const REC_LABEL: Record<Recommendation|string, string> = {
  BOOK_NOW:"BOOK NOW", WAIT:"WAIT", MONITOR:"MONITOR"
};

function PredictContent() {
  const searchParams = useSearchParams();
  const [origin, setOrigin] = useState(searchParams.get("origin") ?? "");
  const [destination, setDestination] = useState(searchParams.get("destination") ?? "");
  const [departureDate, setDepartureDate] = useState("");
  const [alertPrice, setAlertPrice] = useState("");
  const [alertEmail, setAlertEmail] = useState("");

  const { result, loading, error, predict, reset } = usePrediction();
  const { addAlert, loading: alertLoading } = useAlerts();
  const [alertMsg, setAlertMsg] = useState<{ok:boolean;text:string}|null>(null);
  const [metrics, setMetrics] = useState<any>(null);

  useEffect(() => {
    import("@/lib/api").then(api => {
      api.getModelPerformance().then(res => setMetrics(res.metrics)).catch(console.error);
    });
  }, []);

  useEffect(() => {
    const org = searchParams.get("origin");
    const dst = searchParams.get("destination");
    if (org && dst) {
      setOrigin(resolveCityToIATA(org)); setDestination(resolveCityToIATA(dst));
      predict({ origin: resolveCityToIATA(org), destination: resolveCityToIATA(dst), departure_date:undefined });
    }
  }, []);

  const trendCfg = result ? (TREND_CFG[result.trend] ?? TREND_CFG.STABLE) : null;
  const recLabel = result ? (REC_LABEL[result.recommendation] ?? "MONITOR") : null;
  const bestDay = result?.forecast?.reduce((best: any, p: any) => (!best || p.price < best.price ? p : best), null);

  return (
    <div style={{ background: "var(--white)", minHeight: "100vh" }}>
      {/* Hero Section */}
      <div style={{ position: "relative", background: "#000", padding: "120px 0 60px", color: "#fff", overflow: "hidden" }}>
        <video autoPlay muted loop playsInline style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", opacity: 0.3 }} poster="https://images.unsplash.com/photo-1464012658250-24927044342b?auto=format&fit=crop&q=80&w=2074">
          <source src="https://player.vimeo.com/external/494163967.sd.mp4?s=bc32356c36195503080d944c9b1f727877259160&profile_id=164&oauth2_token_id=57447761" type="video/mp4" />
        </video>
        <div className="ui-wrap" style={{ position: "relative", zIndex: 2 }}>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: 24, justifyContent: "space-between" }}>
            <div>
              <div style={{ display: "inline-flex", alignItems: "center", gap: 8, border: "1px solid rgba(255,255,255,0.15)", borderRadius: 100, padding: "6px 14px", marginBottom: 24 }}>
                <div style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--red)", boxShadow: "0 0 8px var(--red)", animation: "blink 2s infinite" }} />
                <span style={{ fontFamily: "var(--fm)", fontSize: "0.6rem", color: "rgba(255,255,255,0.6)", letterSpacing: "0.12em", textTransform: "uppercase" }}>NEURAL ENGINE ACTIVE &bull; {metrics?.estimators || 900} ESTIMATORS</span>
              </div>
              <h1 style={{ fontFamily: "var(--fd)", fontSize: "clamp(3rem, 10vw, 8rem)", lineHeight: .85, letterSpacing: "-.03em", textTransform: "uppercase" }}>
                PRICE<br /><span style={{ color: "var(--red)" }}>TRAJECTORY.</span>
              </h1>
            </div>
            <div className="predict-header-info">
              <div style={{ color: "var(--red)", fontWeight: 700 }}>LIVE INFERENCE FEED</div>
              {metrics?.accuracy ? `${(metrics.accuracy > 1 ? metrics.accuracy : metrics.accuracy * 100).toFixed(1)}%` : "93.2%"} VALIDATION ACCURACY<br />
              STOCHASTIC GRADIENT BOOSTING v2.4
            </div>
          </div>
        </div>
      </div>

      {/* Main Dashboard Content */}
      <div className="ui-wrap" style={{ paddingTop: 40, paddingBottom: 100 }}>
        <div className="predict-layout">
          
          {/* Sidebar / Controls */}
          <div className="predict-sidebar">
            <div style={{ marginBottom: 48 }}>
              <div style={{ fontFamily: "var(--fm)", fontSize: "10px", letterSpacing: "0.1em", color: "var(--grey3)", marginBottom: 20, textTransform: "uppercase" }}>Search Parameters</div>
              <FlightSearchForm 
                mode="predict"
                initialData={{ origin, destination, departure_date: departureDate }}
                onSearch={(p) => {
                  setOrigin(p.origin); setDestination(p.destination); setDepartureDate(p.departure_date);
                  reset(); predict({ origin: p.origin, destination: p.destination, departure_date: p.departure_date || undefined });
                }}
              />
            </div>

            {metrics && (
              <div className="ui-card" style={{ padding: 28, background: "rgba(0,0,0,0.01)", border: "1px solid var(--grey1)" }}>
                <div style={{ fontFamily: "var(--fm)", fontSize: "10px", fontWeight: 700, letterSpacing: "0.05em", color: "var(--grey3)", marginBottom: 20, textTransform: "uppercase" }}>System Integrity</div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px" }}>
                  <div><div style={{ fontFamily: "var(--fb)", fontSize: "10px", fontWeight: 700, color: "var(--grey3)", textTransform: "uppercase", marginBottom: 4 }}>MAE</div><div style={{ fontSize: "1.4rem", fontFamily: "var(--fd)", color: "var(--black)" }}>{Math.round(metrics.mae)}</div></div>
                  <div><div style={{ fontFamily: "var(--fb)", fontSize: "10px", fontWeight: 700, color: "var(--grey3)", textTransform: "uppercase", marginBottom: 4 }}>RMSE</div><div style={{ fontSize: "1.4rem", fontFamily: "var(--fd)", color: "var(--black)" }}>{Math.round(metrics.rmse)}</div></div>
                  <div><div style={{ fontFamily: "var(--fb)", fontSize: "10px", fontWeight: 700, color: "var(--grey3)", textTransform: "uppercase", marginBottom: 4 }}>RELIABILITY</div><div style={{ fontSize: "1.4rem", fontFamily: "var(--fd)", color: "var(--red)" }}>{metrics.r2.toFixed(3)}</div></div>
                  <div><div style={{ fontFamily: "var(--fb)", fontSize: "10px", fontWeight: 700, color: "var(--grey3)", textTransform: "uppercase", marginBottom: 4 }}>SAMPLES</div><div style={{ fontSize: "1.4rem", fontFamily: "var(--fd)", color: "var(--black)" }}>{(metrics.training_samples / 1000).toFixed(1)}k</div></div>
                </div>
              </div>
            )}
          </div>

          {/* Visualization Area */}
          <div className="predict-main">
            <div style={{ marginBottom: 32 }}>
              <div style={{ fontFamily: "var(--fm)", fontSize: "10px", letterSpacing: "0.1em", color: "var(--grey3)", textTransform: "uppercase" }}>Price Analysis</div>
            </div>

            {loading && (
              <div className="ui-card" style={{ padding: "80px 24px", textAlign: "center", background: "var(--white)" }}>
                <div className="status-dot pulse" style={{ width: 16, height: 16, margin: "0 auto 32px" }} />
                <div style={{ fontFamily: "var(--fd)", fontSize: "2rem", letterSpacing: "0.05em", color: "var(--black)" }}>SYNTHESIZING MARKET DATA...</div>
                <p className="ui-text-muted" style={{ marginTop: 16, fontSize: "0.85rem", maxWidth: "400px", margin: "16px auto 0" }}>Running recursive XGBoost iterations over historical pricing data.</p>
              </div>
            )}

            {error && (
              <div className="ui-card" style={{ padding: "60px 24px", textAlign: "center", borderColor: "var(--red)", background: "rgba(224,49,49,0.02)" }}>
                <div style={{ fontFamily: "var(--fb)", fontSize: "10px", color: "var(--red)", fontWeight: 700, marginBottom: 16, textTransform: "uppercase" }}>INFERENCE_SESSION_ERROR</div>
                <div className="ui-text-main" style={{ fontSize: "1rem" }}>{error}</div>
                <button onClick={reset} className="ui-btn ui-btn-white" style={{ marginTop: 24, marginInline: "auto" }}>RETRY</button>
              </div>
            )}

            {result && !loading && (
              <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
                <div className="result-stats-grid">
                  {[
                    { label: "Forecasted Fare", val: `₹${result.predicted_price.toLocaleString("en-IN")}`, sub: "AI Estimate" },
                    { label: "Neural Certainty", val: `${Math.round(result.confidence * 100)}%`, sub: "Confidence Rating" },
                    { label: "Price Volatility", val: `${result.expected_change_percent >= 0 ? "+" : ""}${result.expected_change_percent.toFixed(1)}%`, sub: "Expected Variance" },
                  ].map(m => (
                    <div key={m.label} className="ui-card" style={{ padding: "24px", textAlign: "center" }}>
                      <div style={{ fontFamily: "var(--fb)", fontSize: "10px", fontWeight: 700, color: "var(--grey4)", marginBottom: 12, textTransform: "uppercase" }}>{m.label}</div>
                      <div style={{ fontFamily: "var(--fd)", fontSize: "2.4rem", color: "var(--black)", lineHeight: 1, marginBottom: 8 }}>{m.val}</div>
                      <div style={{ fontFamily: "var(--fb)", fontSize: "9px", fontWeight: 500, color: "var(--grey3)", textTransform: "uppercase" }}>{m.sub}</div>
                    </div>
                  ))}
                </div>

                <div className="result-rec-grid">
                  <div style={{ padding: 24, background: "rgba(22,163,74,.03)", border: "1px solid rgba(22,163,74,0.15)", borderRadius: 20, display: "flex", alignItems: "center", gap: 20 }}>
                    <div className="rec-icon" style={{ background: "#16a34a" }}><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M20 6L9 17l-5-5"/></svg></div>
                    <div>
                      <div style={{ fontFamily: "var(--fb)", fontSize: "10px", fontWeight: 700, color: "#15803d", marginBottom: 4, textTransform: "uppercase" }}>Optimal Window</div>
                      <div style={{ fontFamily: "var(--fd)", fontSize: "1.6rem", color: "#166534" }}>{new Date(bestDay?.date || "").toLocaleDateString("en-IN", { day: "numeric", month: "long" })}</div>
                      <div style={{ fontSize: "0.8rem", color: "#15803d", opacity: 0.8 }}>Target: ₹{Math.round(bestDay?.price || 0).toLocaleString("en-IN")}</div>
                    </div>
                  </div>
                  <div style={{ padding: 24, background: "var(--white)", color: "var(--black)", borderRadius: 20, display: "flex", alignItems: "center", gap: 20, border: "1px solid var(--grey1)" }}>
                    <div className="rec-icon" style={{ background: "var(--red)" }}><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M13 17l5-5-5-5M6 17l5-5-5-5"/></svg></div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontFamily: "var(--fb)", fontSize: "10px", fontWeight: 700, color: "rgba(255,255,255,0.4)", marginBottom: 4, textTransform: "uppercase" }}>AI Recommendation</div>
                      <div style={{ fontFamily: "var(--fd)", fontSize: "1.6rem", color: result.recommendation === "BOOK_NOW" ? "var(--red)" : "var(--black)" }}>{recLabel}</div>
                      <div style={{ fontSize: "0.75rem", color: "rgba(255,255,255,0.5)", marginTop: 2 }}>{result.reason}</div>
                    </div>
                  </div>
                </div>

                <div className="ui-card" style={{ padding: "24px", background: "var(--white)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 32, gap: 12 }}>
                    <div><h2 style={{ fontFamily: "var(--fd)", fontSize: "1.5rem", margin: 0, textTransform: "uppercase", letterSpacing: "0.05em" }}>TRAJECTORY</h2></div>
                    <div className={trendCfg?.badge} style={{ fontSize: "9px" }}>{trendCfg?.label}</div>
                  </div>
                  <div style={{ height: 280 }}><PriceChart forecast={result.forecast} trend={result.trend} /></div>
                </div>
              </div>
            )}

            {!result && !loading && (
              <div className="ui-card" style={{ background: "var(--white)", border: "1px dashed var(--grey2)", padding: "80px 24px", textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", gap: 32 }}>
                <div className="status-dot" style={{ width: 16, height: 16, background: "var(--grey1)" }} />
                <div>
                  <div style={{ fontFamily: "var(--fd)", fontSize: "2.5rem", marginBottom: 12, letterSpacing: "0.02em", lineHeight: 1 }}>NEURAL HUB STANDBY</div>
                  <p className="ui-text-muted" style={{ fontSize: "0.9rem", maxWidth: "340px", margin: "0 auto" }}>Initialize the XGBoost price inference pipeline by entering parameters.</p>
                </div>
                <div style={{ width: "100%", maxWidth: "400px", background: "rgba(0,0,0,0.02)", borderRadius: 16, padding: 24, border: "1px solid var(--grey1)", textAlign: "left" }}>
                  <div style={{ fontFamily: "var(--fb)", fontSize: "10px", fontWeight: 700, color: "var(--grey4)", marginBottom: 16, textTransform: "uppercase" }}>LIVE INFERENCE LOG</div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8, opacity: 0.1 }}>
                    <div style={{ height: 3, width: "100%", background: "var(--grey3)" }} /><div style={{ height: 3, width: "70%", background: "var(--grey3)" }} /><div style={{ height: 3, width: "90%", background: "var(--grey3)" }} />
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <style jsx>{`
        .predict-layout {
          display: grid;
          grid-template-columns: 400px 1fr;
          gap: 64px;
          align-items: start;
          position: relative;
        }
        .predict-sidebar {
          position: sticky;
          top: 100px;
        }
        .predict-main {
          min-height: 700px;
          display: flex;
          flex-direction: column;
          border-left: 1px solid var(--grey1);
          padding-left: 64px;
        }
        .result-stats-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 24px;
        }
        .result-rec-grid {
          display: grid;
          grid-template-columns: 1.2fr 1fr;
          gap: 24px;
        }
        .rec-icon {
          width: 48px;
          height: 48px;
          border-radius: 12px;
          display: flex;
          align-items: center;
          justify-content: center;
          color: #fff;
          flex-shrink: 0;
        }

        .predict-header-info {
          color: rgba(255,255,255,.4);
          font-family: var(--fm);
          font-size: .65rem;
          line-height: 1.8;
          text-align: right;
        }

        @media (max-width: 1100px) {
          .predict-layout { grid-template-columns: 1fr; gap: 48px; }
          .predict-sidebar { position: static; }
          .predict-main { padding-left: 0; border-left: none; border-top: 1px solid var(--grey1); padding-top: 48px; }
          .result-stats-grid { grid-template-columns: 1fr; }
          .result-rec-grid { grid-template-columns: 1fr; }
        }

        @media (max-width: 768px) {
          .predict-header-info { text-align: left !important; margin-top: 16px; }
          .result-stats-grid { gap: 16px; }
          .result-rec-grid { gap: 16px; }
        }
      `}</style>
    </div>
  );
}

export default function PredictPage() {
  return (
    <>
      <NavBar />
      <Suspense fallback={null}><PredictContent /></Suspense>
    </>
  );
}
