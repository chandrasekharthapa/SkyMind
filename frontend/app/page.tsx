"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import NavBar from "@/components/layout/NavBar";
import PopularDestinations from "@/components/flights/PopularDestinations";
import FlightSearchForm from "@/components/flights/FlightSearchForm";
import Counter from "@/components/ui/Counter";

const TICKER_ITEMS = ["Real-time Price Intelligence", "XGBoost Prediction Engine", "Market Volatility Analysis", "11+ Global Hubs", "Smart Fare Tracking", "30-day Price Trajectory", "Priority Fare Alerts", "Confidence-weighted Signals", "Autonomous Booking Intelligence"];

export default function HomePage() {
  const router = useRouter();
  const [metrics, setMetrics] = useState<any>(null);

  useEffect(() => {
    import("@/lib/api").then(api => {
      api.getModelPerformance().then(res => setMetrics(res.metrics)).catch(console.error);
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
      <section style={{ position: "relative", minHeight: "100vh", background: "#000", display: "flex", flexDirection: "column", justifyContent: "center", overflow: "hidden" }}>
        {/* Background video */}
        <video
          autoPlay muted loop playsInline
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", opacity: 0.45 }}
          poster="https://images.unsplash.com/photo-1436491865332-7a61a109cc05?auto=format&fit=crop&q=80&w=2074"
        >
          <source src="https://player.vimeo.com/external/434045526.sd.mp4?s=c27cf341d05d013975d233f0331f0d99049a6a01&profile_id=164&oauth2_token_id=57447761" type="video/mp4" />
        </video>

        {/* Hero content */}
        <div className="ui-wrap" style={{ position: "relative", zIndex: 10, paddingTop: 120, paddingBottom: 64 }}>
          <div className="hero-split">

            {/* LEFT: copy */}
            <div className="hero-copy">
              {/* Badge */}
              <div style={{ display: "inline-flex", alignItems: "center", gap: 8, border: "1px solid rgba(255,255,255,0.15)", borderRadius: 100, padding: "6px 14px", marginBottom: 32, animation: "fadeUp 0.6s ease forwards" }}>
                <div style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--red)", boxShadow: "0 0 8px var(--red)", animation: "blink 2s infinite" }} />
                <span style={{ fontFamily: "var(--fm)", fontSize: "0.6rem", color: "rgba(255,255,255,0.5)", letterSpacing: "0.12em", textTransform: "uppercase" }}>AI-Powered · XGBoost v2.4</span>
              </div>

              {/* Main title */}
              <h1 style={{ fontFamily: "var(--fd)", fontSize: "clamp(3.8rem, 13vw, 10rem)", lineHeight: 0.88, color: "#fff", textTransform: "uppercase", letterSpacing: "-0.03em", marginBottom: 24, animation: "fadeUp 0.7s 0.1s ease forwards", opacity: 0 }}>
                Fly<br />
                <span style={{ color: "var(--red)" }}>Smarter</span>
              </h1>

              {/* Subtitle */}
              <p style={{ fontFamily: "var(--fb)", fontSize: "clamp(0.95rem, 2vw, 1.15rem)", color: "rgba(255,255,255,0.6)", lineHeight: 1.65, maxWidth: 420, marginBottom: 40, animation: "fadeUp 0.7s 0.2s ease forwards", opacity: 0 }}>
                India's first XGBoost-powered flight intelligence platform. Know when prices will rise — before they do.
              </p>

              {/* CTAs */}
              <div style={{ display: "flex", gap: 12, flexWrap: "wrap", animation: "fadeUp 0.7s 0.3s ease forwards", opacity: 0 }}>
                <Link href="/flights" className="ui-btn ui-btn-red">
                  Search Flights
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M5 12h14M12 5l7 7-7 7" /></svg>
                </Link>
                <Link href="/predict" className="ui-btn ui-btn-outline" style={{ backdropFilter: "blur(8px)" }}>
                  AI Price Forecast
                </Link>
              </div>

              {/* Mini stats row */}
              <div className="hero-stats-row" style={{ display: "flex", gap: 32, marginTop: 56, paddingTop: 32, borderTop: "1px solid rgba(255,255,255,0.08)", flexWrap: "wrap", animation: "fadeUp 0.7s 0.4s ease forwards", opacity: 0 }}>
                {[
                  { val: metrics?.training_samples ? `${(metrics.training_samples / 1000).toFixed(1)}K+` : "14.5K+", label: "Training Samples" },
                  { val: metrics?.accuracy ? `${(metrics.accuracy > 1 ? metrics.accuracy : metrics.accuracy * 100).toFixed(1)}%` : "92.4%", label: "Model Accuracy" },
                  { val: metrics?.avg_saving_pct ? `${metrics.avg_saving_pct}%` : "18.5%", label: "Avg Savings" },
                ].map(s => (
                  <div key={s.label}>
                    <div style={{ fontFamily: "var(--fd)", fontSize: "clamp(1.4rem, 4vw, 2.2rem)", color: "#fff", lineHeight: 1 }}>{s.val}</div>
                    <div style={{ fontFamily: "var(--fm)", fontSize: "0.6rem", color: "rgba(255,255,255,0.35)", textTransform: "uppercase", letterSpacing: "0.1em", marginTop: 4 }}>{s.label}</div>
                  </div>
                ))}
              </div>
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
            <div className="status-dot" />
            XGBOOST ANALYTICS ACTIVE
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
                SkyMind layers XGBoost ML inference on top of a deterministic proprietary fare engine to surface the optimal booking window before prices move.
              </p>
              {/* Step Flow */}
              {[
                { n: "01", title: "Proprietary fare engine", desc: "A self-contained pricing model generates market-like fares from demand, inventory, seasonality, and airline variation." },
                { n: "02", title: "XGBoost inference", desc: "900-estimator gradient boosting model. Urgency, seasonality, day-of-week, and demand scoring produce a confidence-weighted price signal." },
                { n: "03", title: "30-day trajectory", desc: "Deterministic forecast with statistical confidence intervals. See the best and peak price windows before you commit." },
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
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
                {[
                  { route: "DEL to BOM", label: "Domestic", price: "INR 4,850", conf: 78, trend: "Rising", color: "var(--red)", badgeClass: "badge-red" },
                  { route: "BOM to GOI", label: "Beach", price: "INR 3,290", conf: 62, trend: "Falling", color: "#16a34a", badgeClass: "badge-green" },
                  { route: "DEL to BLR", label: "Tech", price: "INR 5,100", conf: 85, trend: "Stable", color: "#2563eb", badgeClass: "badge-off" },
                ].map(item => (
                  <div key={item.route} className="ui-card" style={{ padding: "var(--ui-space-md)", cursor: "default" }}>
                    <div className="ui-flex-between">
                      <div>
                        <div className="ui-label" style={{ marginBottom: 6 }}>{item.route} | {item.label}</div>
                        <div className="ui-title-md">{item.price}</div>
                        <div className="conf-bar-wrap" style={{ width: 120, marginTop: 8 }}>
                          <div className="conf-bar-fill" style={{ width: `${item.conf}%`, background: item.color }} />
                        </div>
                        <div className="ui-label" style={{ marginTop: 4, opacity: 0.6 }}>{item.conf}% confidence</div>
                      </div>
                      <span className={`badge ${item.badgeClass}`}>{item.trend}</span>
                    </div>
                  </div>
                ))}
              </div>

              <div style={{ display: "flex", gap: 1, background: "var(--grey1)", borderRadius: "var(--ui-radius-lg)", overflow: "hidden", border: "1px solid var(--grey1)" }}>
                {[
                  { label: "Avg saving", val: "INR 1,200" },
                  { label: "XGBoost acc.", val: metrics?.accuracy ? `${(metrics.accuracy > 1 ? metrics.accuracy : metrics.accuracy * 100).toFixed(1)}%` : "93.2%" },
                  { label: "Routes", val: "240+" },
                ].map(c => (
                  <div key={c.label} style={{ flex: 1, background: "var(--white)", padding: "16px 8px", textAlign: "center" }}>
                    <div className="ui-label" style={{ marginBottom: 6, display: "block", fontSize: "0.65rem", whiteSpace: "nowrap" }}>{c.label}</div>
                    <div className="ui-title-md" style={{ fontSize: "clamp(1.1rem, 3vw, 1.4rem)" }}>{c.val}</div>
                  </div>
                ))}
              </div>
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
              { n: "01 / INTELLIGENCE", title: "ML Price Intelligence", desc: "XGBoost trained on thousands of proprietary and real-world market signals. Real-time confidence scores and market status.", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17" /><polyline points="16 7 22 7 22 13" /></svg> },
              { n: "02 / FORECAST", title: "30-Day Price Forecast", desc: "Full trajectory with confidence bands. See the best and worst booking windows before you commit.", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" /></svg> },
              { n: "03 / ALERTS", title: "Smart Price Alerts", desc: "Set a target price. Our scheduler monitors 24/7 and notifies you the moment it's reached.", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 01-3.46 0" /></svg> },
              { n: "04 / BOOKING", title: "Seamless Booking", desc: "Razorpay checkout for UPI, cards, and netbanking. Instant confirmation with email notifications.", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="1" y="4" width="22" height="16" rx="2" /><line x1="1" y1="10" x2="23" y2="10" /></svg> },
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

      <style>{`
        .hero-split {
          display: grid;
          grid-template-columns: 1.1fr 0.9fr;
          gap: 60px;
          align-items: center;
        }
        .hero-copy { max-width: 600px; }
        .hero-form-desktop { display: block; }
        .hero-form-mobile { display: none; }
        
        .how-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 80px; align-items: start; }
        .how-step { display: flex; gap: 16px; margin-bottom: 32px; }
        .how-step-number { font-family: var(--fm); font-size: 0.8rem; font-weight: 700; color: var(--red); margin-top: 4px; min-width: 24px; }
        .how-step-title { font-family: var(--fb); font-weight: 700; font-size: 1.15rem; color: var(--black); margin-bottom: 4px; line-height: 1.3; }
        .how-step-desc { font-family: var(--fb); font-size: 0.95rem; color: var(--grey4); line-height: 1.6; }

        @media (max-width: 1100px) {
          .hero-split { grid-template-columns: 1fr; gap: 48px; padding: 80px 0 60px; }
          .hero-form-desktop { display: none; }
          .hero-form-mobile { display: block; }
          .how-grid { grid-template-columns: 1fr; gap: 48px; }
        }

        @media (max-width: 768px) {
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
