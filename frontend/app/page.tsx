"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import NavBar from "@/components/layout/NavBar";
import FlightSearchForm from "@/components/flights/FlightSearchForm";
import PopularDestinations from "@/components/flights/PopularDestinations";

function Counter({ to, suf }: { to: number; suf: string }) {
  const [val, setVal] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const obs = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) {
        let v = 0;
        const step = to / 55;
        const t = setInterval(() => {
          v = Math.min(v + step, to);
          setVal(Math.round(v));
          if (v >= to) clearInterval(t);
        }, 20);
      }
    }, { threshold: 0.5 });
    if (ref.current) obs.observe(ref.current);
    return () => obs.disconnect();
  }, [to]);
  return <div ref={ref}>{val}<span className="unit">{suf}</span></div>;
}

const TICKER = ["Amadeus GDS", "Prophet ML", "Supabase", "Razorpay PCI-DSS", "scikit-learn", "FastAPI", "XGBoost", "90+ Indian Airports", "Vercel Edge", "APScheduler"];

export default function HomePage() {
  return (
    <div>
      <NavBar />

      {/* ── HERO ── */}
      <div className="hero">
        <div className="hero-left a1">
          <div className="hero-issue">Vol. 1 — AI Flight Intelligence Platform</div>
          <h1 className="hero-title">
            FLY<br />SMARTER
            <span className="red-line">with artificial<br />intelligence.</span>
          </h1>
          <p className="hero-desc">ML models predict the exact moment to book. XGBoost + deterministic forecasting finds the best fare windows across 90+ Indian airports.</p>
          <div className="hero-ctas">
            <Link href="/flights" className="btn btn-primary">
              Search flights
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M5 12h14M12 5l7 7-7 7" /></svg>
            </Link>
            <Link href="/predict" className="btn btn-outline">View AI forecast</Link>
          </div>
          <div className="hero-stats">
            {[{ to: 2, suf: "M+", label: "Fares analysed" }, { to: 38, suf: "%", label: "Average savings" }, { to: 94, suf: "%", label: "AI accuracy" }].map(s => (
              <div key={s.label} className="hero-stat">
                <div className="hero-stat-num"><Counter to={s.to} suf={s.suf} /></div>
                <div className="hero-stat-label">{s.label}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="hero-right a2">
          <div className="hero-right-header">
            <div className="hero-right-title">FIND YOUR FLIGHT</div>
            <div className="hero-right-sub">Powered by Amadeus GDS + SkyMind AI</div>
          </div>
          <FlightSearchForm />
          <div style={{ marginTop: "16px", display: "flex", alignItems: "center", gap: "12px" }}>
            <div style={{ height: "1px", flex: 1, background: "var(--grey2)" }} />
            <span style={{ fontSize: ".7rem", color: "var(--grey3)", letterSpacing: ".06em", textTransform: "uppercase", fontFamily: "var(--fm)" }}>AI-enhanced · XGBoost ML</span>
            <div style={{ height: "1px", flex: 1, background: "var(--grey2)" }} />
          </div>
        </div>
      </div>

      {/* ── TICKER ── */}
      <div className="ticker-wrap">
        <div className="ticker-inner">
          {[...TICKER, ...TICKER, ...TICKER].map((t, i) => <div key={i} className="ticker-item">{t}</div>)}
        </div>
      </div>

      {/* ── HOW IT WORKS ── */}
      <div className="how-section">
        <div className="wrap">
          <div className="section-eyebrow" style={{ marginBottom: "40px" }}>
            <span className="label">How SkyMind works</span>
            <div className="section-eyebrow-line" />
            <span className="label-red">03 systems</span>
          </div>
          <div className="how-grid">
            <div className="how-left">
              <h2 style={{ fontFamily: "var(--fd)", fontSize: "clamp(2.8rem,5vw,4.5rem)", letterSpacing: ".02em", lineHeight: ".95", color: "var(--black)", marginBottom: "24px" }}>
                NOT JUST<br />SEARCH.<br /><span style={{ fontFamily: "var(--fi)", fontStyle: "italic", color: "var(--red)", fontSize: ".65em" }}>Intelligence.</span>
              </h2>
              <p style={{ fontSize: ".9rem", color: "var(--grey4)", lineHeight: "1.75", marginBottom: "36px", maxWidth: "400px" }}>SkyMind layers three AI systems on top of live Amadeus fare data to surface deals that ordinary booking engines leave on the table.</p>
              {[
                { n: "01 —", title: "Live fare ingestion",    text: "Amadeus GDS feeds pulled on demand across 90+ Indian airports and key international hubs." },
                { n: "02 —", title: "XGBoost scoring engine", text: "scikit-learn + XGBoost model scores each fare: Book Now, Wait, or Set Alert. 94% accuracy on test set." },
                { n: "03 —", title: "30-Day price forecast",  text: "Deterministic route-seeded forecast with confidence intervals so you see price trajectory before booking." },
              ].map(s => (
                <div key={s.n} className="how-step">
                  <span className="how-step-num">{s.n}</span>
                  <div className="how-step-text"><span className="how-step-title">{s.title}</span>{s.text}</div>
                </div>
              ))}
              <div style={{ display: "flex", gap: "10px", marginTop: "28px", flexWrap: "wrap" }}>
                <Link href="/flights" className="btn btn-primary">Search flights →</Link>
                <Link href="/predict" className="btn btn-outline">See AI forecast</Link>
              </div>
            </div>
            <div className="how-right">
              <div className="viz-wrap" style={{ marginBottom: 0 }}>
                <svg viewBox="0 0 400 200" width="100%" height="240" preserveAspectRatio="xMidYMid meet">
                  <line x1="60" y1="20" x2="60" y2="180" stroke="#efefed" strokeWidth="1" />
                  <line x1="200" y1="20" x2="200" y2="180" stroke="#efefed" strokeWidth="1" />
                  <line x1="340" y1="20" x2="340" y2="180" stroke="#efefed" strokeWidth="1" />
                  <path d="M60,145 Q200,25 340,145" stroke="#131210" strokeWidth="2" fill="none" strokeDasharray="700" strokeDashoffset="700" style={{ animation: "drawLine 1.4s .6s ease forwards" }} />
                  <path d="M60,145 Q130,80 200,115" stroke="#d8d6d2" strokeWidth="1.5" fill="none" strokeDasharray="4,5" />
                  <path d="M200,115 Q270,65 340,145" stroke="#d8d6d2" strokeWidth="1.5" fill="none" strokeDasharray="4,5" />
                  <rect x="46" y="131" width="28" height="28" fill="#131210" />
                  <text x="60" y="150" textAnchor="middle" fill="#fff" fontSize="9" fontFamily="Martian Mono,monospace" fontWeight="700">DEL</text>
                  <circle cx="200" cy="115" r="12" fill="white" stroke="#d8d6d2" strokeWidth="1.5" />
                  <text x="200" y="119" textAnchor="middle" fill="#131210" fontSize="8" fontFamily="Martian Mono,monospace" fontWeight="700">BOM</text>
                  <rect x="326" y="131" width="28" height="28" fill="#e8191a" />
                  <text x="340" y="150" textAnchor="middle" fill="#fff" fontSize="9" fontFamily="Martian Mono,monospace" fontWeight="700">DXB</text>
                  <text x="130" y="90" fill="#9b9890" fontSize="8.5" fontFamily="Martian Mono,monospace">via BOM — save 22%</text>
                </svg>
              </div>
              <div className="route-savings">
                {[{ label: "Direct DEL→DXB", val: "₹28,500", color: "var(--grey4)" }, { label: "Via Mumbai", val: "₹22,200", color: "#166534" }, { label: "You save", val: "₹6,300", color: "var(--red)" }].map(r => (
                  <div key={r.label} className="route-saving-item">
                    <div className="route-saving-label">{r.label}</div>
                    <div className="route-saving-val" style={{ color: r.color }}>{r.val}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── FEATURES ── */}
      <div className="feat-section">
        <div className="wrap">
          <div className="section-eyebrow" style={{ marginBottom: "32px" }}>
            <span className="label">Core capabilities</span>
            <div className="section-eyebrow-line" />
            <span className="label-red">04 systems</span>
          </div>
          <div className="feat-grid">
            {[
              { num: "01 / INTELLIGENCE", title: "ML Price Intelligence", desc: "XGBoost trained on millions of fare datapoints. Predicts price movements with 94% accuracy.", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12" /></svg> },
              { num: "02 / FORECAST",     title: "30-Day Price Forecast",  desc: "Full price trajectory with confidence bands. See the best and worst booking windows before you commit.", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" /></svg> },
              { num: "03 / ALERTS",       title: "Smart Price Alerts",     desc: "Set a target price. Our scheduler monitors 24/7 and fires Email + SMS + WhatsApp the moment it's reached.", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" /></svg> },
              { num: "04 / BOOKING",      title: "Seamless Booking",       desc: "Full Razorpay integration — UPI, cards, netbanking. Instant confirmation with email + SMS notifications.", icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="1" y="4" width="22" height="16" rx="2" /><line x1="1" y1="10" x2="23" y2="10" /></svg> },
            ].map((f, i) => (
              <div key={f.num} className="feat-card" style={{ borderRight: i < 3 ? "1px solid var(--grey1)" : "none" }}>
                <div className="feat-num">{f.num}</div>
                <div className="feat-icon">{f.icon}</div>
                <div className="feat-title">{f.title}</div>
                <div className="feat-desc">{f.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── POPULAR DESTINATIONS ── */}
      <div className="dest-section">
        <div className="wrap">
          <div className="dest-header">
            <div>
              <div className="section-eyebrow" style={{ marginBottom: "8px" }}>
                <span className="label">Trending now</span>
                <div className="section-eyebrow-line" style={{ maxWidth: "60px" }} />
              </div>
              <h2 style={{ fontFamily: "var(--fd)", fontSize: "clamp(2rem,4vw,3.2rem)", letterSpacing: ".03em", color: "var(--black)" }}>POPULAR ROUTES</h2>
            </div>
            <Link href="/flights" className="btn btn-outline" style={{ fontSize: ".8rem" }}>All routes →</Link>
          </div>
          <PopularDestinations />
        </div>
      </div>

      {/* ── CTA BAND ── */}
      <div className="cta-band">
        <div className="cta-inner">
          <div>
            <div className="cta-eyebrow">SkyMind — AI Flight Platform</div>
            <div className="cta-title">READY TO FLY<em>smarter than ever?</em></div>
          </div>
          <div className="cta-btns">
            <Link href="/flights" className="btn btn-white">Search flights</Link>
            <Link href="/predict" className="btn btn-white-outline">View predictions</Link>
          </div>
        </div>
      </div>

      {/* ── FOOTER ── */}
      <footer>
        <div className="footer-inner">
          <div className="footer-logo">SKY<em>MIND</em></div>
          <span className="footer-copy">© 2026 SkyMind · AI Flight Intelligence</span>
          <div className="footer-links">
            <Link href="/flights"   className="footer-link">Search</Link>
            <Link href="/predict"   className="footer-link">Predict</Link>
            <Link href="/dashboard" className="footer-link">Dashboard</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
