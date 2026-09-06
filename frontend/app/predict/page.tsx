"use client";

export const dynamic = "force-dynamic";

import { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import nextDynamic from "next/dynamic";
import NavBar from "@/components/layout/NavBar";
import { usePrediction } from "@/hooks/usePrediction";
import { resolveCityToIATA, trendFromDecision } from "@/lib/api";
import FlightSearchForm from "@/components/flights/FlightSearchForm";
import { formatCurrency, formatConfidence, formatDate } from "@/lib/formatters";

import ForecastDebugPanel from "@/components/debug/ForecastDebugPanel";

const PriceChart = nextDynamic(() => import("@/components/charts/PriceChart"), {
  ssr: false,
  loading: () => <div style={{ height: 220, display: "flex", alignItems: "center", justifyContent: "center", color: "#888", fontSize: "13px" }}>Loading forecast chart...</div>
});

const LOADING_STEPS = [
  "Searching live market fares...",
  "Analyzing price trends...",
  "Generating feature vectors...",
  "Running AI forecast model...",
  "Formulating recommendation..."
];

function PredictContent() {
  const searchParams = useSearchParams();
  const [origin, setOrigin] = useState(searchParams.get("origin") ?? "");
  const [destination, setDestination] = useState(searchParams.get("destination") ?? "");
  const [departureDate, setDepartureDate] = useState("");
  const [devMetrics, setDevMetrics] = useState<any>(null);
  const [loadingStepIdx, setLoadingStepIdx] = useState(0);
  const [showDevMode, setShowDevMode] = useState(false);

  const { result, loading, error, errorStatus, predict, reset } = usePrediction();

  // A 503 from /predict is the fail-closed path, not a fault: the model refused
  // rather than invented. It must not be dressed as an error with a Retry button
  // that cannot succeed — the same request will be declined identically until an
  // artifact clears the acceptance gate. Any other status, and a network failure
  // (errorStatus null), is a real error and keeps the red card.
  const refusedByDesign = Boolean(error) && errorStatus === 503;

  useEffect(() => {
    import("@/lib/api").then(api => {
      api.getModelPerformance().then(res => setDevMetrics(res.metrics)).catch(console.error);
    });
  }, []);

  useEffect(() => {
    let interval: any;
    if (loading) {
      setLoadingStepIdx(0);
      interval = setInterval(() => {
        setLoadingStepIdx(prev => (prev < LOADING_STEPS.length - 1 ? prev + 1 : prev));
      }, 700);
    }
    return () => clearInterval(interval);
  }, [loading]);

  useEffect(() => {
    const org = searchParams.get("origin");
    const dst = searchParams.get("destination");
    if (org && dst) {
      setOrigin(resolveCityToIATA(org));
      setDestination(resolveCityToIATA(dst));
      predict({ origin: resolveCityToIATA(org), destination: resolveCityToIATA(dst), departure_date: undefined });
    }
  }, [searchParams, predict]);

  // Single Source of Truth from backend canonical_forecast
  const cForecast = result?.canonical_forecast;
  const lowestFare = cForecast ? cForecast.current_fare : result?.current_market?.lowest_fare;
  const hasLive = lowestFare != null && typeof lowestFare === "number" && lowestFare > 0;
  
  const expectedMinFare = cForecast ? cForecast.expected_minimum_fare : (result?.predicted_price ?? 0);
  const confPct = formatConfidence(cForecast ? cForecast.confidence_score : result?.confidence);

  // A forecast exists only if the backend returned one. Without it there is no
  // decision, no horizon and no optimal date, so each is absent rather than
  // defaulted — the previous defaults ("BOOK_NOW", horizon 0, today's date)
  // rendered a confident "BUY NOW (Today)" recommendation out of no data at all.
  const hasForecast = Boolean(cForecast) || result?.optimal_booking != null || result?.recommendation != null;

  const recDecision = cForecast ? cForecast.recommendation_decision : (result?.recommendation?.decision ?? "MONITOR");
  const recHorizon = cForecast
    ? cForecast.optimal_booking_horizon
    : (result?.optimal_booking?.prediction_horizon ?? null);
  const recTitle = !hasForecast
    ? "NO FORECAST"
    : recDecision === "BOOK_NOW" || recHorizon === 0
      ? "BUY NOW"
      : `WAIT ${recHorizon} DAY${(recHorizon ?? 0) > 1 ? "S" : ""}`;

  const savings = cForecast ? cForecast.calculated_savings : (result?.optimal_booking?.estimated_savings ?? 0);
  const savingsPct = cForecast ? cForecast.percentage_savings.toFixed(1) : (result?.optimal_booking?.percentage_savings?.toFixed(1) ?? "0.0");
  const optDateStr = cForecast ? cForecast.optimal_booking_date : (result?.optimal_booking?.booking_date ?? null);

  const explanation = cForecast?.recommendation_reasons?.[0] ?? (
    !hasForecast
      ? "No forecast is available for this route yet."
      : recHorizon === 0
        ? "Today's live fare is already the lowest expected price across all forecast horizons. Booking now minimises total cost."
        : `The AI model forecasts the lowest fare in approximately ${recHorizon} day(s). Waiting is expected to save approximately ${formatCurrency(savings)}.`
  );

  // Compute "savings vs waiting" — how much you save booking now vs predicted future minimum
  // This is the INVERSE of the standard savings formula when current < forecast
  const savingsVsWaiting = (lowestFare != null && expectedMinFare != null && lowestFare < expectedMinFare)
    ? Math.round(expectedMinFare - lowestFare)
    : 0;
  const savingsVsWaitingPct = (lowestFare != null && lowestFare > 0 && savingsVsWaiting > 0)
    ? ((savingsVsWaiting / expectedMinFare) * 100).toFixed(1)
    : "0.0";
  const alreadyCheapest = savingsVsWaiting > 0 && savings <= 0;

  // Risk level: derived from confidence, and unrated when there is no confidence to
  // derive it from. A null score means no evaluation metric is recorded for this
  // horizon — which is not the same as a bad one. Falling through to "High risk /
  // Low confidence" would report a measurement that does not exist.
  const confText = confPct == null ? "Not measured" : `${confPct}%`;
  const riskLevel = confPct == null ? "Unrated" : confPct >= 88 ? "Low" : confPct >= 70 ? "Medium" : "High";
  const riskColor = confPct == null ? "#64748b" : confPct >= 88 ? "#16a34a" : confPct >= 70 ? "#d97706" : "#dc2626";

  // Confidence label
  const confLabel = confPct == null
    ? "No evaluation metric recorded for this horizon"
    : confPct >= 88 ? "High confidence" : confPct >= 70 ? "Moderate confidence" : "Low confidence — treat as indicative";

  const timelinePoints = cForecast?.timeline ? cForecast.timeline.map((pt: any) => ({
    day: pt.horizon_days,
    date: pt.booking_date,
    price: pt.predicted_price,
    lower: pt.lower_bound,
    upper: pt.upper_bound,
    is_optimal: pt.is_optimal
  })) : (result?.forecast ?? []);

  const searchAgain = (p: any) => {
    setOrigin(p.origin); setDestination(p.destination); setDepartureDate(p.departure_date);
    reset();
    predict({ origin: p.origin, destination: p.destination, departure_date: p.departure_date || undefined });
  };

  return (
    <div style={{ background: "#fff", minHeight: "100vh", paddingTop: 80 }}>
      <div className="page-wrap">
        <div className="layout">

          {/* ── Left Sidebar ─────────────────────────────────────── */}
          <aside className="sidebar" aria-label="Search and System Metadata Sidebar">
            <section className="sidebar-section">
              <h2 className="section-label">SEARCH PARAMETERS</h2>
              <FlightSearchForm
                mode="predict"
                initialData={{ origin, destination, departure_date: departureDate }}
                onSearch={searchAgain}
              />
            </section>

            {/* Data & Model Info */}
            <section className="sidebar-section" style={{ marginTop: 24 }}>
              <h2 className="section-label">DATA &amp; MODEL INFORMATION</h2>
              <div className="info-table">
                <div className="info-row">
                  <span className="info-key">Historical Accuracy</span>
                  <span className="info-val green">
                    {devMetrics?.mape != null ? `${(100 - devMetrics.mape).toFixed(1)}%` : "—"}
                  </span>
                </div>
                <div className="info-row">
                  <span className="info-key">Market Freshness</span>
                  <span className="info-val">
                    {result?.search_metadata?.snapshot_age != null
                      ? `${Math.round(result.search_metadata.snapshot_age)} mins ago`
                      : "—"}
                  </span>
                </div>
                <div className="info-row">
                  <span className="info-key">Data Provider</span>
                  <span className="info-val">{result?.search_metadata?.provider || "—"}</span>
                </div>
                <div className="info-row">
                  <span className="info-key">Last Updated</span>
                  <span className="info-val">
                    {devMetrics?.training_date ? formatDate(devMetrics.training_date) : "—"}
                  </span>
                </div>

                {/* Collapsible Technical Details for Developer Mode */}
                {showDevMode && (
                  <>
                    <div className="info-row dev-row">
                      <span className="info-key">Model Version</span>
                      <span className="info-val">{devMetrics?.model_name ?? "—"}</span>
                    </div>
                    <div className="info-row dev-row">
                      <span className="info-key">Schema Version</span>
                      <span className="info-val">{devMetrics?.feature_set_version ?? "—"}</span>
                    </div>
                    <div className="info-row dev-row">
                      <span className="info-key">Algorithm</span>
                      <span className="info-val">Gradient Boosted Trees</span>
                    </div>
                  </>
                )}
              </div>
              <button 
                onClick={() => setShowDevMode(!showDevMode)}
                aria-expanded={showDevMode}
                className="btn-dev-toggle"
              >
                {showDevMode ? "Hide Technical Details" : "Show Technical Details"}
              </button>
            </section>
          </aside>

          {/* ── Main Content ─────────────────────────────────────── */}
          <main className="main" aria-label="AI Flight Price Forecast Results">

            {/* Loading State */}
            {loading && (
              <div className="card state-card">
                <div className="loading-label">{LOADING_STEPS[loadingStepIdx]}</div>
                <div className="progress-track">
                  <div className="progress-fill" style={{ width: `${((loadingStepIdx + 1) / LOADING_STEPS.length) * 100}%` }} />
                </div>
              </div>
            )}

            {/* Refused-by-design State: the backend declined, and said why. */}
            {refusedByDesign && !loading && (
              <div className="card state-card state-notice" role="status">
                <div className="state-notice-label">Forecast Not Available Yet</div>
                <div className="description" style={{ marginTop: 8 }}>{error}</div>
                <div className="description" style={{ marginTop: 12, fontSize: "12px", color: "#777" }}>
                  SkyMind refuses a forecast rather than showing an estimate it cannot
                  stand behind. Live fare search on the Search page is unaffected.
                </div>
              </div>
            )}

            {/* Error State */}
            {error && !refusedByDesign && !loading && (
              <div className="card state-card state-error">
                <div className="state-error-label">Inference Session Error</div>
                <div className="description" style={{ marginTop: 8 }}>{error}</div>
                <button onClick={reset} className="btn-secondary" style={{ marginTop: 16 }}>Retry Inference</button>
              </div>
            )}

            {/* Standby State */}
            {!result && !loading && !error && (
              <div className="card state-card" style={{ textAlign: "center", padding: "48px 24px" }}>
                <h3 style={{ fontSize: "15px", fontWeight: 600, color: "#111", marginBottom: 8 }}>Enter Search Parameters</h3>
                <p className="description">Select origin and destination airports to run the AI forecast model.</p>
              </div>
            )}

            {/* Prediction Output */}
            {result && !loading && (
              <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
                
                {/* Degradation Banner */}
                {(result.search_metadata?.provider_status === "DEGRADED" || !result.search_metadata?.market_snapshot_available) && (
                  <div className="banner-warn" role="alert">
                    Live market data was not confirmed for this search, so the figures below may not
                    reflect the current market.
                  </div>
                )}

                {/* ① Price Analysis Grid */}
                <section aria-labelledby="section-price-analysis">
                  <h2 id="section-price-analysis" className="section-label">PRICE ANALYSIS</h2>
                  <div className="metric-grid">
                    <div className="card metric-card">
                      <div className="card-label">CURRENT LIVE FARE</div>
                      <div className="primary-price">{hasLive ? formatCurrency(lowestFare) : "—"}</div>
                      <div className="metadata">
                        Lowest fare returned by {result.search_metadata?.provider || "the search provider"}
                      </div>
                    </div>

                    <div className="card metric-card">
                      <div className="card-label">AI FORECAST PRICE</div>
                      <div className="primary-price">{formatCurrency(expectedMinFare)}</div>
                      <div className="metadata">Model-predicted fare · may differ from live price</div>
                    </div>

                    <div className="card metric-card">
                      <div className="card-label">
                        {alreadyCheapest ? "BOOKING NOW SAVES" : "POTENTIAL SAVINGS"}
                      </div>
                      <div className={`primary-price ${savings > 0 || alreadyCheapest ? "green" : ""}`}>
                        {alreadyCheapest
                          ? formatCurrency(savingsVsWaiting)
                          : savings > 0
                            ? formatCurrency(savings)
                            : "₹0"}
                      </div>
                      <div className="metadata">
                        {alreadyCheapest
                          ? `${savingsVsWaitingPct}% cheaper than AI forecast — book now`
                          : hasLive
                            ? `${savingsPct}% expected savings by waiting`
                            : "Live market required for savings estimate"}
                      </div>
                    </div>

                    <div className="card metric-card">
                      <div className="card-label">FORECAST CONFIDENCE</div>
                      <div className="primary-price">{confText}</div>
                      <div className="metadata">{confLabel}</div>
                    </div>
                  </div>
                </section>

                {/* ② Structured Recommendation Card */}
                <section aria-labelledby="section-recommendation">
                  <div className="card rec-card">
                    
                    {/* Recommendation Title & Explanation */}
                    <div className="rec-col">
                      <div className="card-label">RECOMMENDATION</div>
                      <div className={`rec-title ${recHorizon === 0 ? "green" : "amber"}`}>{recTitle}</div>
                      <p className="rec-explanation">{explanation}</p>
                    </div>

                    {/* Target Booking Details */}
                    <div className="rec-col border-left">
                      <div className="rec-item">
                        <div className="card-label">RECOMMENDED BOOKING DATE</div>
                        <div className="secondary-value">
                          {optDateStr ? formatDate(optDateStr) : "—"}
                          {recHorizon === 0 && <span className="today-badge">(Today)</span>}
                        </div>
                      </div>
                      <div className="rec-item">
                        <div className="card-label">AI FORECAST PRICE</div>
                        <div className="secondary-value">{formatCurrency(expectedMinFare)}</div>
                      </div>
                    </div>

                    {/* Savings & Risk Metrics */}
                    <div className="rec-col border-left">
                      <div className="rec-item">
                        <div className="card-label">
                          {alreadyCheapest ? "BOOKING NOW SAVES" : "ESTIMATED SAVINGS"}
                        </div>
                        <div className="secondary-value green">
                          {alreadyCheapest ? (
                            <>{formatCurrency(savingsVsWaiting)} <span className="metadata" style={{ fontWeight: 400 }}>({savingsVsWaitingPct}%)</span></>
                          ) : savings > 0 ? (
                            <>{formatCurrency(savings)} <span className="metadata" style={{ fontWeight: 400 }}>({savingsPct}%)</span></>
                          ) : "₹0 (0.0%)"}
                        </div>
                      </div>
                      <div className="rec-row-flex">
                        <div className="rec-item">
                          <div className="card-label">RISK LEVEL</div>
                          <div className="secondary-value" style={{ fontSize: "14px", color: riskColor }}>{riskLevel}</div>
                        </div>
                        <div className="rec-item">
                          <div className="card-label">CONFIDENCE</div>
                          <div className="secondary-value" style={{ fontSize: "14px" }}>{confText}</div>
                        </div>
                      </div>
                    </div>

                  </div>
                </section>

                {/* ③ Forecast Timeline */}
                <section aria-labelledby="section-timeline">
                  <h2 id="section-timeline" className="section-label">FORECAST TIMELINE</h2>
                  <div className="timeline-grid">
                    
                    {/* Observed Live Fare Baseline */}
                    <div className="card timeline-card baseline">
                      <div className="card-label">Current Live Fare</div>
                      <div className="metadata">{formatDate(new Date().toISOString())}</div>
                      <div className="tl-price">{formatCurrency(lowestFare)}</div>
                      <div className="metadata">Observed market fare</div>
                    </div>

                    {/* Forecast Horizon Cards */}
                    {timelinePoints.map((pt: any) => {
                      const isRec = pt.is_optimal || pt.day === recHorizon;
                      const labels: Record<number, string> = { 0: "AI Estimate · Today", 1: "Tomorrow", 3: "3 Days", 7: "7 Days" };
                      const periodLabel = labels[pt.day] ?? `${pt.day} Days`;
                      const dateLabel = formatDate(pt.date);
                      // Detect if AI estimate for today diverges significantly from live price
                      const isToday = pt.day === 0;
                      const divergent = isToday && hasLive && lowestFare != null && Math.abs(pt.price - lowestFare) / lowestFare > 0.10;

                      return (
                        <div key={pt.day} className={`card timeline-card ${isRec ? "tl-selected" : ""}`}>
                          <div className="card-label" style={{ fontWeight: isRec ? 600 : 500 }}>{periodLabel}</div>
                          <div className="metadata">{dateLabel}</div>
                          <div className={`tl-price ${isRec ? "green" : ""}`}>{formatCurrency(pt.price)}</div>
                          {(pt.lower != null && pt.upper != null) && (
                            <div className="metadata">Range: {formatCurrency(pt.lower)} – {formatCurrency(pt.upper)}</div>
                          )}
                          {divergent && (
                            <div className="metadata" style={{ color: "#d97706", marginTop: 2 }}>Model estimate · live: {formatCurrency(lowestFare)}</div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                  <div className="metadata" style={{ marginTop: 8 }}>
                    All future prices are expected fares predicted by the machine learning model. Actual market fares may vary.
                  </div>
                </section>

                {/* ④ Why This Recommendation */}
                <section aria-labelledby="section-why">
                  <div className="card why-card">
                    <h2 id="section-why" className="section-label" style={{ marginBottom: 12 }}>WHY THIS RECOMMENDATION?</h2>
                    <ul className="why-list">
                      {(result.recommendation?.reasons ?? []).length > 0
                        ? result.recommendation.reasons.map((r: string, i: number) => (
                            <li key={i}>{r.replace(/^✓\s*/, "")}</li>
                          ))
                        : [
                            "Today's expected fare is already the lowest forecast across all booking windows.",
                            "Historical price volatility on this route remains low.",
                            "Demand trend and booking pace indicate a stable pricing trajectory.",
                            "Booking today minimizes expected total flight cost."
                          ].map((r, i) => <li key={i}>{r}</li>)
                      }
                    </ul>
                  </div>
                </section>

                {/* ⑤ Developer Debug & Invariant Audit Panel */}
                <ForecastDebugPanel rawResult={result} canonicalForecast={cForecast} />

                {/* ⑤ Booking Curve Interactive Forecast Chart */}
                <section aria-labelledby="section-chart">
                  <div className="card chart-card">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                      <h2 id="section-chart" className="section-label" style={{ marginBottom: 0 }}>BOOKING CURVE FORECAST CHART</h2>
                      <div className="metadata">
                        Snapshot: {formatDate(result.search_metadata?.retrieval_time)}
                      </div>
                    </div>
                    <div style={{ height: 260 }}>
                      <PriceChart forecast={result.forecast} trend={trendFromDecision(result.recommendation?.decision)} />
                    </div>
                  </div>
                </section>

              </div>
            )}
          </main>
        </div>
      </div>

      <style jsx>{`
        .page-wrap {
          max-width: 1280px;
          margin: 0 auto;
          padding: 24px 24px 64px;
        }

        .layout {
          display: grid;
          grid-template-columns: 300px 1fr;
          gap: 32px;
          align-items: start;
        }

        .sidebar {
          position: sticky;
          top: 96px;
        }

        .sidebar-section {
          background: #fff;
        }

        .section-label {
          font-size: 13px;
          font-weight: 500;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: #666;
          margin: 0 0 12px 0;
        }

        .card {
          background: #fff;
          border: 1px solid #EAEAEA;
          border-radius: 12px;
          padding: 20px;
          box-shadow: none;
        }

        .info-table {
          display: flex;
          flex-direction: column;
          border: 1px solid #EAEAEA;
          border-radius: 10px;
          overflow: hidden;
        }

        .info-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 10px 14px;
          border-bottom: 1px solid #F0F0F0;
        }
        .info-row:last-child { border-bottom: none; }
        .dev-row { background: #FAFAFA; }

        .info-key {
          font-size: 12px;
          font-weight: 400;
          color: #666;
        }

        .info-val {
          font-size: 12px;
          font-weight: 500;
          color: #111;
          text-align: right;
        }
        .info-val.green { color: #16a34a; }

        .btn-dev-toggle {
          margin-top: 8px;
          font-size: 11px;
          font-weight: 500;
          color: #666;
          background: none;
          border: none;
          cursor: pointer;
          padding: 4px 0;
          text-align: left;
        }
        .btn-dev-toggle:hover { color: #111; text-decoration: underline; }

        .card-label {
          font-size: 13px;
          font-weight: 500;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          color: #666;
          margin-bottom: 4px;
        }

        .primary-price {
          font-size: 32px;
          font-weight: 700;
          color: #111;
          line-height: 1.1;
          margin-bottom: 4px;
        }
        .primary-price.green { color: #16a34a; }
        .primary-price.red-text { color: #dc2626; }

        .secondary-value {
          font-size: 15px;
          font-weight: 600;
          color: #111;
          line-height: 1.2;
        }
        .secondary-value.green { color: #16a34a; }

        .description {
          font-size: 14px;
          font-weight: 400;
          color: #444;
          line-height: 1.5;
          margin: 0;
        }

        .metadata {
          font-size: 12px;
          font-weight: 400;
          color: #888;
        }

        .metric-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 16px;
        }

        .metric-card {
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          min-height: 100px;
        }

        .rec-card {
          display: grid;
          grid-template-columns: 1.2fr 1fr 1fr;
          gap: 20px;
          align-items: center;
        }

        .rec-col {
          display: flex;
          flex-direction: column;
        }

        .rec-col.border-left {
          border-left: 1px solid #F0F0F0;
          padding-left: 20px;
          gap: 12px;
        }

        .rec-title {
          font-size: 28px;
          font-weight: 600;
          line-height: 1.1;
          margin-bottom: 6px;
        }
        .rec-title.green { color: #16a34a; }
        .rec-title.amber { color: #d97706; }

        .rec-explanation {
          font-size: 14px;
          font-weight: 400;
          color: #444;
          line-height: 1.5;
          max-width: 480px;
          margin: 0;
        }

        .rec-item {
          display: flex;
          flex-direction: column;
        }

        .today-badge {
          font-size: 12px;
          font-weight: 400;
          color: #666;
          margin-left: 4px;
        }

        .rec-row-flex {
          display: flex;
          gap: 20px;
        }

        .timeline-grid {
          display: grid;
          grid-template-columns: repeat(5, 1fr);
          gap: 12px;
        }

        .timeline-card {
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          min-height: 100px;
          padding: 16px;
        }

        .timeline-card.baseline {
          background: #FAFAFA;
        }

        .timeline-card.tl-selected {
          border: 2px solid #16a34a;
          background: rgba(22, 163, 74, 0.03);
        }

        .tl-price {
          font-size: 20px;
          font-weight: 600;
          color: #111;
          margin-top: 4px;
          margin-bottom: 2px;
        }
        .tl-price.green { color: #16a34a; }

        .why-card {
          padding: 20px;
        }

        .why-list {
          margin: 0;
          padding-left: 18px;
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .why-list li {
          font-size: 14px;
          font-weight: 400;
          color: #333;
          line-height: 1.5;
        }

        .chart-card {
          padding: 20px;
        }

        .state-card {
          padding: 40px 20px;
        }

        .state-error {
          border-color: #FCA5A5;
          background: #FFF8F8;
        }

        .state-error-label {
          font-size: 12px;
          font-weight: 600;
          color: #DC2626;
          text-transform: uppercase;
        }

        /* Neutral, not alarming: a declined forecast is the design working. */
        .state-notice {
          border-color: #E5E7EB;
          background: #FAFAFA;
        }

        .state-notice-label {
          font-size: 12px;
          font-weight: 600;
          color: #52525B;
          text-transform: uppercase;
        }

        .btn-secondary {
          height: 40px;
          padding: 0 16px;
          border-radius: 8px;
          background: #fff;
          border: 1px solid #EAEAEA;
          color: #333;
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
        }
        .btn-secondary:hover { background: #F9F9F9; }

        .loading-label {
          font-size: 15px;
          font-weight: 600;
          color: #111;
          margin-bottom: 16px;
        }

        .progress-track {
          width: 220px;
          height: 3px;
          background: #EAEAEA;
          border-radius: 100px;
          margin: 0 auto;
          overflow: hidden;
        }

        .progress-fill {
          height: 100%;
          background: #E11D48;
          border-radius: 100px;
          transition: width 0.4s ease;
        }

        .banner-warn {
          background: rgba(202, 138, 4, 0.06);
          border: 1px solid rgba(202, 138, 4, 0.2);
          border-radius: 10px;
          padding: 12px 16px;
          font-size: 13px;
          color: #92400E;
        }

        @media (max-width: 1200px) {
          .metric-grid { grid-template-columns: repeat(2, 1fr); }
          .rec-card { grid-template-columns: 1fr; gap: 16px; }
          .rec-col.border-left { border-left: none; padding-left: 0; border-top: 1px solid #F0F0F0; padding-top: 14px; }
          .timeline-grid { grid-template-columns: repeat(3, 1fr); }
        }

        @media (max-width: 900px) {
          .layout { grid-template-columns: 1fr; gap: 24px; }
          .sidebar { position: static; }
        }

        @media (max-width: 600px) {
          .page-wrap { padding: 16px 16px 40px; }
          .metric-grid { grid-template-columns: 1fr; }
          .timeline-grid { grid-template-columns: repeat(2, 1fr); overflow-x: auto; }
        }
      `}</style>
    </div>
  );
}

export default function PredictPage() {
  return (
    <>
      <NavBar />
      <Suspense fallback={<div style={{ paddingTop: 120, textAlign: "center", color: "#666", fontSize: "13px" }}>Loading forecast dashboard...</div>}>
        <PredictContent />
      </Suspense>
    </>
  );
}
