"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import NavBar from "@/components/layout/NavBar";
import FlightSearchForm from "@/components/flights/FlightSearchForm";
import PopularDestinations from "@/components/flights/PopularDestinations";

// ─── Counter animation ────────────────────────────────────────────────
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
        }, 18);
      }
    }, { threshold: 0.5 });
    if (ref.current) obs.observe(ref.current);
    return () => obs.disconnect();
  }, [to]);
  return <div ref={ref}>{val}<span style={{ color: "var(--red)" }}>{suf}</span></div>;
}

// ─── Ticker items ─────────────────────────────────────────────────────
const TICKER = [
  "Amadeus GDS", "XGBoost ML", "Air India Routes", "Live Fare Data",
  "90+ Indian Airports", "FastAPI Backend", "Supabase", "Razorpay PCI-DSS",
  "scikit-learn", "Vercel Edge", "APScheduler", "Price Intelligence",
];

// ─── SVG Icons ────────────────────────────────────────────────────────
const ArrowRight = ({ size = 14 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
    <path d="M5 12h14M12 5l7 7-7 7" />
  </svg>
);

const TrendingUpIcon = ({ size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
    <polyline points="16 7 22 7 22 13" />
  </svg>
);

const BarChartIcon = ({ size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="20" x2="18" y2="10" />
    <line x1="12" y1="20" x2="12" y2="4" />
    <line x1="6" y1="20" x2="6" y2="14" />
  </svg>
);

const BellIcon = ({ size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" />
    <path d="M13.73 21a2 2 0 01-3.46 0" />
  </svg>
);

const CreditCardIcon = ({ size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="1" y="4" width="22" height="16" rx="2" />
    <line x1="1" y1="10" x2="23" y2="10" />
  </svg>
);

const PlaneIcon = ({ size = 11, color = "var(--red)" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={color}>
    <path d="M17.8 19.2L16 11l3.5-3.5C21 6 21 4 19.5 2.5S18 2 16.5 3.5L13 7 4.8 6.2c-.5-.1-.9.1-1.1.5L2 8.9c-.2.4-.1.9.2 1.2l4.6 4.1-1.5 6.4 2.8 2.8 5.3-3.2 4.1 4.6c.3.4.8.5 1.2.2l1.1-1.2c.4-.2.6-.6.5-1.1z" />
  </svg>
);

export default function HomePage() {
  return (
    <div>
      <NavBar />

      {/* ── HERO ── */}
      <div className="hero">
        {/* Left: Headline + stats */}
        <div className="hero-left a1">
          <div className="hero-issue">Vol. 1 — AI Flight Intelligence Platform</div>

          <h1 className="hero-title">
            FLY<br />
            SMARTER
            <span className="serif-line">
              with artificial<br />intelligence.
            </span>
          </h1>

          <p className="hero-desc">
            XGBoost ML predicts the exact moment to book across 90+ Indian airports.
            Live Amadeus GDS fares, 30-day price forecasts, and smart alerts — built for India.
          </p>

          <div className="hero-ctas">
            <Link href="/flights" className="btn btn-primary">
              Search flights <ArrowRight />
            </Link>
            <Link href="/predict" className="btn btn-outline">
              View AI forecast
            </Link>
          </div>

          {/* Stats */}
          <div className="hero-stats">
            {[
              { to: 2, suf: "M+", label: "Fares analysed" },
              { to: 38, suf: "%",  label: "Average savings" },
              { to: 94, suf: "%",  label: "AI accuracy" },
            ].map((s) => (
              <div key={s.label} className="hero-stat">
                <div className="hero-stat-num">
                  <Counter to={s.to} suf={s.suf} />
                </div>
                <div className="hero-stat-label">{s.label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Right: Search form */}
        <div className="hero-right a2">
          <div className="hero-right-title">FIND YOUR FLIGHT</div>
          <div className="hero-right-sub" style={{ fontFamily: "var(--font-mono)" }}>
            Powered by Amadeus GDS + SkyMind AI
          </div>
          <FlightSearchForm />
          <div style={{ marginTop: "16px", display: "flex", alignItems: "center", gap: "12px" }}>
            <div style={{ height: "1px", flex: 1, background: "var(--grey-0)" }} />
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--grey-2)", letterSpacing: "0.10em", textTransform: "uppercase" }}>
              AI-enhanced · XGBoost ML
            </span>
            <div style={{ height: "1px", flex: 1, background: "var(--grey-0)" }} />
          </div>
        </div>
      </div>

      {/* ── TICKER ── */}
      <div className="ticker-wrap">
        <div className="ticker-inner">
          {[...TICKER, ...TICKER, ...TICKER].map((t, i) => (
            <div key={i} className="ticker-item">{t}</div>
          ))}
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
            {/* Left: Copy */}
            <div className="how-left">
              <h2 style={{
                fontFamily: "var(--font-sans)",
                fontWeight: 800,
                fontSize: "clamp(2.5rem,5vw,4rem)",
                letterSpacing: "-0.04em",
                lineHeight: 0.92,
                color: "var(--charcoal)",
                marginBottom: "20px",
              }}>
                NOT JUST<br />SEARCH.
                <span style={{ display: "block", fontFamily: "var(--font-serif)", fontStyle: "italic", color: "var(--red)", fontSize: "clamp(1.4rem,3.2vw,2.8rem)", marginTop: "6px", fontWeight: 400, lineHeight: 1.2 }}>
                  Intelligence.
                </span>
              </h2>

              <p style={{ fontSize: "14px", color: "var(--grey-4)", lineHeight: "1.75", marginBottom: "32px", maxWidth: "400px" }}>
                SkyMind layers three AI systems on top of live Amadeus fare data
                to surface deals that ordinary booking engines leave on the table.
              </p>

              {[
                { n: "01", title: "Live fare ingestion",    text: "Amadeus GDS feeds pulled on demand across 90+ Indian airports and key international hubs." },
                { n: "02", title: "XGBoost scoring engine", text: "scikit-learn + XGBoost model scores each fare: Book Now, Wait, or Monitor. 94% accuracy on test set." },
                { n: "03", title: "30-Day price forecast",  text: "Deterministic route-seeded forecast with confidence intervals — see price trajectory before booking." },
              ].map((s) => (
                <div key={s.n} className="how-step">
                  <span className="how-step-num">{s.n}</span>
                  <div className="how-step-text">
                    <span className="how-step-title">{s.title}</span>
                    {s.text}
                  </div>
                </div>
              ))}

              <div style={{ display: "flex", gap: "10px", marginTop: "28px", flexWrap: "wrap" }}>
                <Link href="/flights" className="btn btn-primary">Search flights <ArrowRight /></Link>
                <Link href="/predict" className="btn btn-outline">See AI forecast</Link>
              </div>
            </div>

            {/* Right: Visualization — DOMESTIC ONLY (DEL→BOM→CCU) */}
            <div className="how-right">
              <div className="viz-wrap">
                <svg viewBox="0 0 400 200" width="100%" height="220" preserveAspectRatio="xMidYMid meet">
                  {/* Grid lines */}
                  {[60, 200, 340].map((x) => (
                    <line key={x} x1={x} y1="20" x2={x} y2="180" stroke="#E2E8F0" strokeWidth="1" />
                  ))}

                  {/* Direct route */}
                  <path
                    d="M60,145 Q200,25 340,145"
                    stroke="#1E293B"
                    strokeWidth="2"
                    fill="none"
                    strokeDasharray="700"
                    strokeDashoffset="700"
                    style={{ animation: "drawLine 1.4s 0.5s ease forwards" }}
                  />

                  {/* Via BOM dashed */}
                  <path d="M60,145 Q130,80 200,110" stroke="#CBD5E1" strokeWidth="1.5" fill="none" strokeDasharray="4,5" />
                  <path d="M200,110 Q270,65 340,145" stroke="#CBD5E1" strokeWidth="1.5" fill="none" strokeDasharray="4,5" />

                  {/* DEL */}
                  <rect x="44" y="131" width="32" height="28" rx="4" fill="#1E293B" />
                  <text x="60" y="150" textAnchor="middle" fill="#fff" fontSize="9" fontFamily="JetBrains Mono, monospace" fontWeight="700">DEL</text>

                  {/* BOM (via stop) */}
                  <circle cx="200" cy="110" r="14" fill="white" stroke="#E2E8F0" strokeWidth="1.5" />
                  <text x="200" y="114" textAnchor="middle" fill="#1E293B" fontSize="8" fontFamily="JetBrains Mono, monospace" fontWeight="700">BOM</text>

                  {/* CCU */}
                  <rect x="324" y="131" width="32" height="28" rx="4" fill="#E11D48" />
                  <text x="340" y="150" textAnchor="middle" fill="#fff" fontSize="9" fontFamily="JetBrains Mono, monospace" fontWeight="700">CCU</text>

                  {/* Label */}
                  <text x="150" y="82" fill="#94A3B8" fontSize="8.5" fontFamily="JetBrains Mono, monospace">via BOM — save 18%</text>
                </svg>
              </div>

              {/* Savings comparison — DOMESTIC */}
              <div className="route-savings">
                {[
                  { label: "Direct DEL→CCU", val: "₹5,800", color: "var(--grey-4)" },
                  { label: "Via Mumbai",     val: "₹4,750", color: "#059669" },
                  { label: "You save",       val: "₹1,050", color: "var(--red)" },
                ].map((r) => (
                  <div key={r.label} className="route-saving-item">
                    <div className="route-saving-label">{r.label}</div>
                    <div className="route-saving-val" style={{ color: r.color }}>{r.val}</div>
                  </div>
                ))}
              </div>

              {/* Domestic badge */}
              <div style={{ marginTop: "12px", display: "flex", justifyContent: "center" }}>
                <span className="badge badge-off" style={{ fontSize: "10px" }}>
                  <PlaneIcon size={10} color="var(--grey-3)" />
                  Domestic India routes · Air India
                </span>
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
              {
                num: "01 / INTELLIGENCE",
                title: "ML Price Intelligence",
                desc: "XGBoost trained on millions of fare datapoints. Predicts price movements with 94% accuracy across Air India domestic routes.",
                icon: <TrendingUpIcon size={18} />,
              },
              {
                num: "02 / FORECAST",
                title: "30-Day Price Forecast",
                desc: "Full price trajectory with confidence bands. See the best and worst booking windows before you commit.",
                icon: <BarChartIcon size={18} />,
              },
              {
                num: "03 / ALERTS",
                title: "Smart Price Alerts",
                desc: "Set a target price. Our scheduler monitors 24/7 and notifies via Email + SMS the moment it's reached.",
                icon: <BellIcon size={18} />,
              },
              {
                num: "04 / BOOKING",
                title: "Seamless Booking",
                desc: "Full Razorpay integration — UPI, cards, netbanking. Instant confirmation with email notifications.",
                icon: <CreditCardIcon size={18} />,
              },
            ].map((f, i) => (
              <div key={f.num} className="feat-card">
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
              <h2 style={{ fontWeight: 800, fontSize: "clamp(1.8rem,4vw,3rem)", letterSpacing: "-0.04em", color: "var(--charcoal)" }}>
                POPULAR ROUTES
              </h2>
            </div>
            <Link href="/flights" className="btn btn-outline" style={{ fontSize: "13px" }}>
              All routes <ArrowRight size={13} />
            </Link>
          </div>
          <PopularDestinations />
        </div>
      </div>

      {/* ── CTA BAND ── */}
      <div className="cta-band">
        <div className="cta-inner">
          <div>
            <div className="cta-eyebrow">SkyMind — AI Flight Platform</div>
            <div className="cta-title">
              READY TO FLY
              <em>smarter than ever?</em>
            </div>
          </div>
          <div className="cta-btns">
            <Link href="/flights" className="btn-white" style={{ borderRadius: "8px", letterSpacing: "-0.01em", fontFamily: "var(--font-sans)" }}>Search flights</Link>
            <Link href="/predict" className="btn-white-outline" style={{ borderRadius: "8px", letterSpacing: "-0.01em", fontFamily: "var(--font-sans)" }}>View predictions</Link>
          </div>
        </div>
      </div>

      {/* ── FOOTER ── */}
      <footer>
        <div className="footer-inner">
          <div className="footer-logo">SKY<em>MIND</em></div>
          <span className="footer-copy">© 2026 SkyMind · AI Flight Intelligence · India</span>
          <div className="footer-links">
            <Link href="/flights"    className="footer-link">Search</Link>
            <Link href="/predict"   className="footer-link">Predict</Link>
            <Link href="/dashboard" className="footer-link">Dashboard</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
