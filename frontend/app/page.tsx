"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import NavBar from "@/components/layout/NavBar";
import PopularDestinations from "@/components/flights/PopularDestinations";
import FlightSearchForm from "@/components/flights/FlightSearchForm";
import FlightNetwork from "@/components/home/FlightNetwork";
import { formatConfidence } from "@/lib/formatters";

// Every item here describes something the product actually does.
const TICKER_ITEMS = [
  "Fares collected every day",
  "XGBoost Prediction Engine",
  "56 domestic routes tracked",
  "14 Indian airports",
  "1, 3 and 7-day fare forecasts",
  "Book now or wait signals",
  "Price history per route",
  "Target-price alerts",
  "Confidence shown on every forecast"
];

export default function HomePage() {
  const router = useRouter();
  const [metrics, setMetrics] = useState<any>(null);
  const [samples, setSamples] = useState<any[]>([]);

  useEffect(() => {
    import("@/lib/api").then(api => {
      api.getModelPerformance().then(res => setMetrics(res.metrics)).catch(console.error);

      // Fetch real live prediction data for sample cards
      const date = new Date();
      date.setDate(date.getDate() + 7);
      const depDate = date.toISOString().split("T")[0];

      const fetchRoute = (origin: string, destination: string, label: string) => {
        return api.predictPrice({ origin, destination, departure_date: depDate, airline_code: "6E" })
          .then(p => {
            // `p.trend` does not exist on the response — see trendFromDecision.
            const trend = api.trendFromDecision(p.recommendation?.decision);
            const color = trend === "RISING" ? "var(--red)" : trend === "FALLING" ? "#16a34a" : "#2563eb";
            const badgeClass = trend === "RISING" ? "badge-red" : trend === "FALLING" ? "badge-green" : "badge-off";
            const confPct = formatConfidence(p.confidence);
            return {
              route: `${origin} to ${destination}`,
              label,
              price: `₹${Math.round(p.predicted_price).toLocaleString("en-IN")}`,
              conf: confPct,
              trend,
              color,
              badgeClass,
              available: true
            };
          })
          .catch(e => {
            console.error(`Prediction unavailable for ${origin}-${destination}:`, e);
            // This used to substitute a hardcoded price and confidence, which
            // rendered identically to a real prediction. Say "unavailable"
            // instead of inventing a number.
            return {
              route: `${origin} to ${destination}`,
              label,
              price: "Unavailable",
              conf: null,
              trend: "STABLE",
              color: "var(--grey2)",
              badgeClass: "badge-off",
              available: false
            };
          });
      };

      Promise.all([
        fetchRoute("DEL", "BOM", "Domestic"),
        fetchRoute("BOM", "GOI", "Beach"),
        fetchRoute("DEL", "BLR", "Tech")
      ]).then(res => setSamples(res));
    });
  }, []);

  const handleSearch = (p: any) => {
    const url = new URLSearchParams();
    Object.entries(p).forEach(([k, v]) => url.set(k, String(v)));
    router.push(`/flights?${url.toString()}`);
  };

  return (
    <div style={{ background: "var(--white)" }}>
      <NavBar />

      {/* ══════════════════════════════════════════
          HERO — cinematic, left-aligned, premium
          ══════════════════════════════════════════ */}
      <section className="home-hero" style={{ position: "relative", minHeight: "100vh", background: "#000", display: "flex", flexDirection: "column", justifyContent: "center", overflow: "hidden" }}>
        {/* Animated flight network (drawn in code; see FlightNetwork) */}
        <div aria-hidden="true" style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse 60% 70% at 52% 50%, rgba(255,255,255,0.05), transparent 70%), #000" }} />
        <FlightNetwork className="hero-network" />
        <div aria-hidden="true" className="hero-scrim" />

        {/* Hero content */}
        <div className="ui-wrap" style={{ position: "relative", zIndex: 10, paddingTop: 120, paddingBottom: 64 }}>
          <div className="hero-split">

            {/* LEFT: copy */}
            <div className="hero-copy">
              {/* Badge */}
              <div style={{ display: "inline-flex", alignItems: "center", gap: 8, border: "1px solid rgba(255,255,255,0.15)", borderRadius: 100, padding: "6px 14px", marginBottom: 32 }}>
                <div style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--red)", boxShadow: "0 0 8px var(--red)" }} />
                <span style={{ fontFamily: "var(--fm)", fontSize: "0.6rem", color: "rgba(255,255,255,0.5)", letterSpacing: "0.12em", textTransform: "uppercase" }}>AI-Powered · XGBoost</span>
              </div>

              {/* Main title */}
              <h1 style={{ fontFamily: "var(--fd)", fontSize: "clamp(3.8rem, 13vw, 10rem)", lineHeight: 0.88, color: "#fff", textTransform: "uppercase", letterSpacing: "-0.03em", marginBottom: 24 }}>
                Fly<br />
                <span style={{ color: "var(--red)" }}>Smarter</span>
              </h1>

              {/* Subtitle */}
              <p style={{ fontFamily: "var(--fb)", fontSize: "clamp(0.95rem, 2vw, 1.15rem)", color: "rgba(255,255,255,0.6)", lineHeight: 1.65, maxWidth: 420, marginBottom: 40 }}>
                Domestic flight fares across India, collected every day and forecast with XGBoost. Know when prices will rise — before they do.
              </p>

              {/* CTAs */}
              <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                <Link href="/flights" className="ui-btn ui-btn-red">
                  Search Flights
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M5 12h14M12 5l7 7-7 7" /></svg>
                </Link>
                <Link href="/predict" className="ui-btn ui-btn-outline" style={{ backdropFilter: "blur(8px)", color: "#fff", borderColor: "rgba(255,255,255,0.3)" }}>
                  AI Price Forecast
                </Link>
              </div>

              {/* Mini stats row.
                  These three used to read "14.5K+", "92.4%" and "18.5%" whenever
                  the metrics call had not resolved — and for the last two, that
                  was always: `metrics.accuracy` and `metrics.avg_saving_pct` are
                  not fields /system/model/metadata returns, so the fallbacks were
                  the permanent values. "Avg Savings" is gone entirely because
                  nothing in the backend measures a saving; the slot now shows
                  mean absolute error, which the model does report. */}
              {metrics && (metrics.training_samples || metrics.mape != null || metrics.mae != null) && (
              <div className="hero-stats-row" style={{ display: "flex", gap: 32, marginTop: 56, paddingTop: 32, borderTop: "1px solid rgba(255,255,255,0.08)", flexWrap: "wrap" }}>
                {[
                  { val: metrics?.training_samples ? `${(metrics.training_samples / 1000).toFixed(1)}K` : "—", label: "Training Rows" },
                  { val: metrics?.mape != null ? `${(100 - metrics.mape).toFixed(1)}%` : "—", label: "Accuracy (100−MAPE)" },
                  { val: metrics?.mae != null ? `₹${Math.round(metrics.mae).toLocaleString("en-IN")}` : "—", label: "Mean Abs. Error" },
                ].filter(s => s.val !== "—").map(s => (
                  <div key={s.label}>
                    <div style={{ fontFamily: "var(--fd)", fontSize: "clamp(1.4rem, 4vw, 2.2rem)", color: "#fff", lineHeight: 1 }}>{s.val}</div>
                    <div style={{ fontFamily: "var(--fm)", fontSize: "0.6rem", color: "rgba(255,255,255,0.55)", textTransform: "uppercase", letterSpacing: "0.1em", marginTop: 4 }}>{s.label}</div>
                  </div>
                ))}
              </div>
              )}
            </div>

            {/* RIGHT: search form (desktop only) */}
            <div className="hero-form-desktop">
              <FlightSearchForm onSearch={handleSearch} />
            </div>
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════
          MOBILE SEARCH — clean white card
          ══════════════════════════════════════════ */}
      <div className="hero-form-mobile" style={{ background: "var(--off)", borderBottom: "1px solid var(--grey1)" }}>
        <div className="ui-wrap" style={{ padding: "28px var(--ui-space-md)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16, fontFamily: "var(--fm)", fontSize: "0.6rem", color: "var(--grey3)", letterSpacing: "0.1em" }}>
            SEARCH FLIGHTS
          </div>
          <FlightSearchForm onSearch={handleSearch} />
        </div>
      </div>

      {/* ══════════════════════════════════════════
          TICKER
          ══════════════════════════════════════════ */}
      <div className="ticker-strip">
        <div className="ticker-wrap">
          {TICKER_ITEMS.concat(TICKER_ITEMS).map((item, idx) => (
            <div key={idx} className="ticker-item">
              <span className="ticker-dot" />
              {item}
            </div>
          ))}
        </div>
      </div>

      {/* ══════════════════════════════════════════
          HOW IT WORKS
          ══════════════════════════════════════════ */}
      <section className="ui-section ui-section-white">
        <div className="ui-wrap">
          <div className="ui-eyebrow">
            <span className="ui-label">How SkyMind works</span>
            <div className="ui-eyebrow-line" />
            <span className="ui-label-red">03 systems</span>
          </div>

          <div className="how-grid" style={{ marginTop: "var(--ui-space-2xl)" }}>
            <div>
              <h2 className="ui-title-lg" style={{ marginBottom: 20 }}>NOT<br />JUST<br />SEARCH.</h2>
              <p className="ui-text-main" style={{ maxWidth: 340, marginBottom: 32 }}>
                SkyMind keeps every fare it sees and trains an XGBoost model on
                them, so forecasts are built from prices that were really quoted,
                not from estimates.
              </p>
              {[
                { n: "01", title: "Daily fare collection", desc: "Every morning SkyMind looks up fares on 56 domestic routes, for the coming week and for dates up to three months out, and saves each price with the time it was seen." },
                { n: "02", title: "XGBoost inference", desc: "A gradient-boosted model learns how fares on a route move as departure gets closer, by weekday and by season, and returns a price with a confidence score." },
                { n: "03", title: "30-day trajectory", desc: "For your date, see where the fare is likely heading, with a range around it, and whether booking now or waiting looks better." },
              ].map((s, i) => (
                <div key={s.n} className={`how-step a${i + 1}`}>
                  <span className="how-step-number">{s.n}</span>
                  <div>
                    <div className="how-step-title">{s.title}</div>
                    <div className="how-step-desc">{s.desc}</div>
                  </div>
                </div>
              ))}
            </div>

            <div>
              <div className="ui-label" style={{ marginBottom: 14 }}>Sample XGBoost predictions</div>
              {samples.length > 0 && samples.every(x => !x.available) ? (
                <div className="ui-card" style={{ padding: "var(--ui-space-lg)", marginBottom: 16, cursor: "default" }}>
                  <div className="ui-title-md" style={{ marginBottom: 8 }}>Forecasts are warming up</div>
                  <p className="ui-text-muted" style={{ marginBottom: 20 }}>
                    The prediction server takes up to a minute to wake after a quiet spell.
                    Try a route of your own on the forecast page.
                  </p>
                  <Link href="/predict" className="ui-btn ui-btn-red">Open fare forecast</Link>
                </div>
              ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
                {(samples.length > 0 ? samples.filter(x => x.available) : [
                  // Placeholders shown only until the live calls resolve. These
                  // used to carry concrete prices and "95% confidence", which
                  // was indistinguishable from a real prediction.
                  { route: "DEL to BOM", label: "Domestic", price: "Loading…", conf: null, trend: "STABLE", color: "var(--grey2)", badgeClass: "badge-off", available: false },
                  { route: "BOM to GOI", label: "Beach", price: "Loading…", conf: null, trend: "STABLE", color: "var(--grey2)", badgeClass: "badge-off", available: false },
                  { route: "DEL to BLR", label: "Tech", price: "Loading…", conf: null, trend: "STABLE", color: "var(--grey2)", badgeClass: "badge-off", available: false },
                ]).map(item => (
                  <div key={item.route} className="ui-card" style={{ padding: "var(--ui-space-md)", cursor: "default" }}>
                    <div className="ui-flex-between">
                      <div>
                        <div className="ui-label" style={{ marginBottom: 6 }}>{item.route} | {item.label}</div>
                        <div className="ui-title-md">{item.price}</div>
                        {item.available !== false && (
                          <>
                            {/* A null confidence is "no metric recorded", not 0%. Rendering
                                the bar at all would show a measured-zero, so say it in words. */}
                            {item.conf == null ? (
                              <div className="ui-label" style={{ marginTop: 8, opacity: 0.6 }}>Confidence not measured</div>
                            ) : (
                              <>
                                <div className="conf-bar-wrap" style={{ width: 120, marginTop: 8 }}>
                                  <div className="conf-bar-fill" style={{ width: `${item.conf}%`, background: item.color || "var(--blue)" }} />
                                </div>
                                <div className="ui-label" style={{ marginTop: 4, opacity: 0.6 }}>{item.conf}% confidence</div>
                              </>
                            )}
                          </>
                        )}
                      </div>
                      {item.available !== false && (
                        <span className={`badge ${item.badgeClass}`}>{String(item.trend).charAt(0).toUpperCase() + String(item.trend).slice(1).toLowerCase()}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              )}

              {metrics && (metrics.model_name || metrics.mape != null || metrics.training_samples != null) && (
              <div style={{ display: "flex", gap: 1, background: "var(--grey1)", borderRadius: "var(--ui-radius-lg)", overflow: "hidden", border: "1px solid var(--grey1)" }}>
                {/* Was: "Avg saving INR 1,200", "XGBoost acc. 93.2%", "Routes 240+".
                    No component measures a saving, the accuracy fallback always
                    fired (and disagreed with the hero's own 92.4%), and no route
                    count exists anywhere. All three now come from the model
                    metadata endpoint or show as unknown. */}
                {[
                  { label: "Model", val: metrics?.model_name || "—" },
                  { label: "Accuracy", val: metrics?.mape != null ? `${(100 - metrics.mape).toFixed(1)}%` : "—" },
                  { label: "Training rows", val: metrics?.training_samples != null ? Number(metrics.training_samples).toLocaleString("en-IN") : "—" },
                ].map(c => (
                  <div key={c.label} style={{ flex: 1, background: "var(--white)", padding: "16px 8px", textAlign: "center" }}>
                    <div className="ui-label" style={{ marginBottom: 6, display: "block", fontSize: "0.65rem", whiteSpace: "nowrap" }}>{c.label}</div>
                    <div className="ui-title-md" style={{ fontSize: "clamp(1.1rem, 3vw, 1.4rem)" }}>{c.val}</div>
                  </div>
                ))}
              </div>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════
          FEATURES
          ══════════════════════════════════════════ */}
      <section className="ui-section ui-section-off">
        <div className="ui-wrap">
          <div className="ui-eyebrow">
            <span className="ui-label">Core capabilities</span>
            <div className="ui-eyebrow-line" />
            <span className="ui-label-red">04 systems</span>
          </div>
          <div className="feat-grid" style={{ marginTop: "var(--ui-space-2xl)" }}>
            {[
              { n: "01 / INTELLIGENCE", title: "ML Price Intelligence", desc: "XGBoost trained on fares collected every day from live listings. Every prediction comes with a confidence score.", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17" /><polyline points="16 7 22 7 22 13" /></svg> },
              { n: "02 / FORECAST", title: "30-Day Price Forecast", desc: "Fare trajectory for your date with confidence bands. See the cheaper and pricier booking windows before you commit.", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" /></svg> },
              { n: "03 / ALERTS", title: "Smart Price Alerts", desc: "Set a target price for a route. SkyMind checks the fare every day and lets you know once it drops below your target.", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 01-3.46 0" /></svg> },
              { n: "04 / BOOKING", title: "Demo Booking", desc: "Try the full booking flow with Razorpay in test mode. No real payment is taken and no airline ticket is issued.", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="1" y="4" width="22" height="16" rx="2" /><line x1="1" y1="10" x2="23" y2="10" /></svg> },
            ].map(f => (
              <div key={f.n} className="ui-card ui-card-hover">
                <div className="ui-label-red" style={{ marginBottom: 20 }}>{f.n}</div>
                <div className="feat-icon-wrap" style={{ color: "var(--red)", marginBottom: 16 }}>{f.icon}</div>
                <div className="ui-title-md" style={{ marginBottom: 12 }}>{f.title}</div>
                <p className="ui-text-muted">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════
          POPULAR DESTINATIONS
          ══════════════════════════════════════════ */}
      <section className="ui-section ui-section-white">
        <div className="ui-wrap">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 16, marginBottom: 32 }}>
            <div>
              <div className="ui-eyebrow">
                <span className="ui-label">Trending now</span>
                <div className="ui-eyebrow-line" style={{ maxWidth: 60 }} />
              </div>
              <h2 className="ui-title-lg" style={{ fontSize: "clamp(1.8rem,4vw,3rem)" }}>POPULAR ROUTES</h2>
            </div>
            <Link href="/flights" className="ui-btn ui-btn-white">
              All routes <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M5 12h14M12 5l7 7-7 7" /></svg>
            </Link>
          </div>
          <PopularDestinations />
        </div>
      </section>

      {/* ══════════════════════════════════════════
          CTA BAND
          ══════════════════════════════════════════ */}
      <section className="cta-band">
        <div className="ui-wrap">
          <div className="cta-inner">
            <div>
              <div className="ui-label" style={{ color: "rgba(255,255,255,.3)", marginBottom: 16 }}>SkyMind — AI Flight Platform</div>
              <div className="cta-title">
                READY TO FLY
                <em>smarter than ever?</em>
              </div>
            </div>
            <div className="cta-btns">
              <Link href="/flights" className="ui-btn ui-btn-white">Search flights</Link>
              <Link href="/predict" className="ui-btn ui-btn-outline">View predictions</Link>
            </div>
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════
          FOOTER
          ══════════════════════════════════════════ */}
      <footer style={{ borderTop: "1px solid var(--grey1)", background: "var(--white)", padding: "var(--ui-space-xl) 0" }}>
        <div className="ui-wrap">
          <div className="footer-inner">
            <div className="footer-logo">SKY<em>MIND</em></div>
            <span className="ui-text-muted" style={{ fontSize: "0.75rem" }}>2026 SkyMind | AI Flight Intelligence | India</span>
            <div className="ui-flex" style={{ gap: "var(--ui-space-lg)" }}>
              <Link href="/flights" className="footer-link">Search</Link>
              <Link href="/predict" className="footer-link">Predict</Link>
              <Link href="/dashboard" className="footer-link">Dashboard</Link>
            </div>
          </div>
        </div>
      </footer>

      <style jsx>{`
        .hero-split {
          display: grid;
          grid-template-columns: 1.1fr 0.9fr;
          gap: 60px;
          align-items: center;
        }
        .hero-copy { max-width: 600px; }
        :global(.hero-network) { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
        .hero-scrim {
          position: absolute; inset: 0; pointer-events: none;
          /* Dims the animation behind the headline and copy only, so the text
             stays easy to read while planes stay bright everywhere else. */
          background: radial-gradient(ellipse 30% 46% at 29% 57%, rgba(0,0,0,0.86) 0%, rgba(0,0,0,0.62) 55%, rgba(0,0,0,0) 100%);
        }
        @media (max-width: 1100px) {
          .hero-scrim { background: rgba(0,0,0,0.62); }
        }
        .hero-form-desktop { display: block; }
        .hero-form-mobile { display: none; }
        
        .how-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 80px; align-items: start; }
        .how-step { display: flex; gap: 16px; margin-bottom: 32px; }
        .how-step-number { font-family: var(--fm); font-size: 0.8rem; font-weight: 700; color: var(--red); margin-top: 4px; min-width: 24px; }
        .how-step-title { font-family: var(--fb); font-weight: 700; font-size: 1.15rem; color: var(--black); margin-bottom: 4px; line-height: 1.3; }
        .how-step-desc { font-family: var(--fb); font-size: 0.95rem; color: var(--grey4); line-height: 1.6; }

        @media (max-width: 1100px) {
          .home-hero { min-height: auto !important; }
          .hero-split { grid-template-columns: 1fr; gap: 48px; padding: 80px 0 60px; }
          .hero-form-desktop { display: none; }
          .hero-form-mobile { display: block; }
          .how-grid { grid-template-columns: 1fr; gap: 48px; }
        }

        @media (max-width: 768px) {
          .hero-split { padding: 8px 0 24px; }
          .ui-title-lg { font-size: 2.8rem !important; }
          .how-step-title { font-size: 1.1rem; }
          .how-step-desc { font-size: 0.9rem; }
        }

        @media (max-width: 640px) {
          .hero-copy h1 { letter-spacing: -0.02em; }
        }
      `}</style>
    </div>
  );
}
