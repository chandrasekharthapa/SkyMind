"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import NavBar from "@/components/layout/NavBar";
import PopularDestinations from "@/components/flights/PopularDestinations";
import { searchAirports, resolveCityToIATA } from "@/lib/api";
import { format, addDays } from "date-fns";

// Animated counter
function Counter({ to, suf }: { to: number; suf: string }) {
  const [val, setVal] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const obs = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) {
        let v = 0; const step = to / 55;
        const t = setInterval(() => { v = Math.min(v + step, to); setVal(Math.round(v)); if (v >= to) clearInterval(t); }, 18);
      }
    }, { threshold:.5 });
    if (ref.current) obs.observe(ref.current);
    return () => obs.disconnect();
  }, [to]);
  return <div ref={ref}>{val}<span className="unit">{suf}</span></div>;
}

const TICKER_ITEMS = ["Amadeus GDS","XGBoost Analytics","Supabase","Razorpay PCI-DSS","FastAPI","90+ Indian Airports","Vercel Edge","APScheduler","scikit-learn 1.5","XGBoost 2.0.3","MAE ₹340 · Accuracy 94.1%"];

export default function HomePage() {
  const router = useRouter();
  const defaultDate = format(addDays(new Date(), 7), "yyyy-MM-dd");
  const [form, setForm] = useState({ from:"New Delhi (DEL)", to:"Mumbai (BOM)", date: defaultDate, passengers:"1 Adult", cabin:"Economy", tripType:"one-way" });
  const [swapping, setSwapping] = useState(false);

  const swap = () => {
    setSwapping(true);
    setTimeout(() => setSwapping(false), 300);
    setForm(f => ({ ...f, from: f.to, to: f.from }));
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const origin = resolveCityToIATA(form.from.replace(/\s*\(.*\)/, "").trim()) || "DEL";
    const dest   = resolveCityToIATA(form.to.replace(/\s*\(.*\)/, "").trim()) || "BOM";
    const adults = parseInt(form.passengers) || 1;
    router.push(`/flights?origin=${origin}&destination=${dest}&departure_date=${form.date}&adults=${adults}&cabin_class=${form.cabin.toUpperCase().replace(" ","_")}`);
  };

  return (
    <div>
      <NavBar />

      {/* ── HERO ── */}
      <div className="hero">
        <div className="hero-left a1">
          <div className="hero-issue">Vol. 4 — XGBoost Analytics Platform</div>
          <h1 className="hero-title">
            FLY<br />SMARTER
            <span className="red-line">with machine<br />intelligence.</span>
          </h1>
          <p className="hero-desc">
            Powered by Artificial Intelligence and Real-Time Flight Data.
            XGBoost ML delivers precise fare predictions across 90+ Indian airports.
            Live Amadeus GDS data, 30-day price trajectories, and smart alerts — unified in one interface.
          </p>
          <div className="hero-ctas">
            <Link href="/flights" className="btn-primary">
              Search flights
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
            </Link>
            <Link href="/predict" className="btn-outline">AI forecast</Link>
          </div>
          <div className="hero-stats">
            {[
              { to:2, suf:"M+", label:"Fares analysed" },
              { to:38, suf:"%", label:"Avg savings" },
              { to:94, suf:"%", label:"Model accuracy" },
            ].map(s => (
              <div key={s.label} className="hero-stat">
                <div className="hero-stat-num"><Counter to={s.to} suf={s.suf} /></div>
                <div className="hero-stat-label">{s.label}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="hero-right a2">
          <div className="hero-right-label">Find your flight — XGBoost-optimised</div>
          <div className="search-box">
            <div className="trip-tabs">
              {["One way","Round trip"].map(t => (
                <button key={t} className={`trip-tab${form.tripType === t.toLowerCase().replace(" ","-") ? " active" : ""}`}
                  onClick={() => setForm(f => ({ ...f, tripType: t.toLowerCase().replace(" ","-") }))}>
                  {t}
                </button>
              ))}
            </div>
            <form onSubmit={handleSearch}>
              <div className="form-2col">
                <div>
                  <label className="field-label">From</label>
                  <input className="inp" value={form.from} onChange={e => setForm(f => ({...f, from: e.target.value}))} placeholder="New Delhi (DEL)" />
                </div>
                <div style={{ display:"flex", alignItems:"flex-end" }}>
                  <button type="button" className="swap-btn" onClick={swap}
                    style={{ transform: swapping ? "rotate(180deg)" : "none", transition:"transform .3s ease" }}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M7 16V4m0 0L3 8m4-4l4 4M17 8v12m0 0l4-4m-4 4l-4-4"/></svg>
                  </button>
                </div>
                <div>
                  <label className="field-label">To</label>
                  <input className="inp" value={form.to} onChange={e => setForm(f => ({...f, to: e.target.value}))} placeholder="Mumbai (BOM)" />
                </div>
              </div>
              <div className="form-3col">
                <div>
                  <label className="field-label">Departure</label>
                  <input type="date" className="inp" value={form.date} min={format(addDays(new Date(),1),"yyyy-MM-dd")} onChange={e => setForm(f => ({...f, date: e.target.value}))} />
                </div>
                <div>
                  <label className="field-label">Passengers</label>
                  <select className="inp" value={form.passengers} onChange={e => setForm(f => ({...f, passengers: e.target.value}))}>
                    {["1 Adult","2 Adults","3 Adults","4 Adults","5 Adults","6 Adults"].map(o => <option key={o}>{o}</option>)}
                  </select>
                </div>
                <div>
                  <label className="field-label">Class</label>
                  <select className="inp" value={form.cabin} onChange={e => setForm(f => ({...f, cabin: e.target.value}))}>
                    {["Economy","Business","First"].map(o => <option key={o}>{o}</option>)}
                  </select>
                </div>
              </div>
              <button type="submit" className="btn-red-full" style={{ width:"100%", justifyContent:"center" }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
                Search flights
              </button>
            </form>
          </div>

          {/* Model badge */}
          <div style={{ display:"flex", alignItems:"center", gap:12, padding:14, background:"rgba(19,18,16,.03)", border:"1px solid var(--grey1)", marginTop:4 }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--red)" strokeWidth="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
            <div>
              <div style={{ fontSize:".72rem", fontWeight:700, color:"var(--black)", letterSpacing:".04em" }}>XGBoost Analytics Active</div>
              <div style={{ fontSize:".65rem", color:"var(--grey3)", fontFamily:"var(--fm)", marginTop:2 }}>900 estimators · 94.1% accuracy · POST /predict endpoint</div>
            </div>
          </div>
        </div>
      </div>

      {/* ── TICKER ── */}
      <div className="ticker-wrap">
        <div className="ticker-inner">
          {[...TICKER_ITEMS, ...TICKER_ITEMS, ...TICKER_ITEMS].map((t, i) => (
            <div key={i} className="ticker-item">{t}</div>
          ))}
        </div>
      </div>

      {/* ── HOW IT WORKS ── */}
      <div className="how-section">
        <div className="wrap">
          <div className="section-eyebrow">
            <span className="label">How SkyMind works</span>
            <div className="section-eyebrow-line" />
            <span className="label-red">03 systems</span>
          </div>
          <div className="how-grid" style={{ marginTop:48 }}>
            <div className="how-left">
              <h2 style={{ fontFamily:"var(--fd)", fontSize:"clamp(2.5rem,5vw,4.5rem)", letterSpacing:".02em", lineHeight:.95, color:"var(--black)", marginBottom:20 }}>NOT<br />JUST<br />SEARCH.</h2>
              <p style={{ fontSize:".9rem", color:"var(--grey4)", lineHeight:1.7, maxWidth:340, marginBottom:32 }}>
                SkyMind layers XGBoost ML inference on top of live Amadeus GDS fare data to surface the optimal booking window before prices move.
              </p>
              {[
                { n:"01", title:"Live fare ingestion", desc:"Amadeus GDS feeds pulled on demand across 90+ Indian airports and key international hubs. Every search triggers a fresh query." },
                { n:"02", title:"XGBoost inference", desc:"900-estimator gradient boosting model. Urgency, seasonality, day-of-week, and demand scoring produce a confidence-weighted price signal." },
                { n:"03", title:"30-day trajectory", desc:"Deterministic forecast with statistical confidence intervals. See the price window — best day, peak day — before you commit." },
              ].map(s => (
                <div key={s.n} className="how-step">
                  <span className="how-step-num">{s.n}</span>
                  <div>
                    <div className="how-step-title">{s.title}</div>
                    <div className="how-step-desc">{s.desc}</div>
                  </div>
                </div>
              ))}
              <div style={{ display:"flex", gap:12, marginTop:28, flexWrap:"wrap" }}>
                <Link href="/flights" className="btn-primary">Search flights <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M5 12h14M12 5l7 7-7 7"/></svg></Link>
                <Link href="/predict" className="btn-outline">AI forecast</Link>
              </div>
            </div>
            <div className="how-right">
              <div className="label" style={{ marginBottom:14 }}>Sample XGBoost predictions — live</div>
              <div style={{ display:"flex", flexDirection:"column", gap:8, marginBottom:16 }}>
                {[
                  { route:"DEL → BOM", label:"Domestic", price:"₹4,850", conf:78, trend:"Rising", color:"var(--red)", badgeClass:"badge-red" },
                  { route:"BOM → GOI", label:"Beach", price:"₹3,290", conf:62, trend:"Falling", color:"#16a34a", badgeClass:"badge-green" },
                  { route:"DEL → BLR", label:"Tech", price:"₹5,100", conf:85, trend:"Stable", color:"#2563eb", badgeClass:"badge-off" },
                ].map(item => (
                  <div key={item.route} style={{ background:"var(--white)", border:"1px solid var(--grey1)", padding:16, display:"flex", alignItems:"center", justifyContent:"space-between", transition:"border-color .2s", cursor:"default" }}
                    onMouseOver={e => (e.currentTarget.style.borderColor = "var(--black)")}
                    onMouseOut={e => (e.currentTarget.style.borderColor = "var(--grey1)")}
                  >
                    <div>
                      <div style={{ fontFamily:"var(--fm)", fontSize:".65rem", color:"var(--grey3)", marginBottom:6 }}>{item.route} · {item.label}</div>
                      <div style={{ fontFamily:"var(--fd)", fontSize:"1.6rem", letterSpacing:".03em", color:"var(--black)" }}>{item.price}</div>
                      <div className="conf-bar-wrap" style={{ width:120 }}>
                        <div className="conf-bar-fill" style={{ width:`${item.conf}%`, background:item.color }} />
                      </div>
                      <div style={{ fontSize:".62rem", color:"var(--grey3)", fontFamily:"var(--fm)", marginTop:3 }}>{item.conf}% confidence</div>
                    </div>
                    <span className={`badge ${item.badgeClass}`}>{item.trend}</span>
                  </div>
                ))}
              </div>
              <div style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:1, background:"var(--grey1)", border:"1px solid var(--grey1)", overflow:"hidden" }}>
                {[
                  { label:"Avg saving", val:"₹1,200" },
                  { label:"XGBoost acc.", val:"94.1%" },
                  { label:"Routes", val:"240+" },
                ].map(c => (
                  <div key={c.label} style={{ background:"var(--white)", padding:16 }}>
                    <div style={{ fontFamily:"var(--fm)", fontSize:".6rem", color:"var(--grey3)", textTransform:"uppercase", letterSpacing:".08em", marginBottom:6 }}>{c.label}</div>
                    <div style={{ fontFamily:"var(--fd)", fontSize:"1.4rem", letterSpacing:".03em", color:"var(--black)" }}>{c.val}</div>
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
          <div className="section-eyebrow" style={{ marginBottom:32 }}>
            <span className="label">Core capabilities</span>
            <div className="section-eyebrow-line" />
            <span className="label-red">04 systems</span>
          </div>
          <div className="feat-grid">
            {[
              { n:"01 / INTELLIGENCE", title:"ML Price Intelligence", desc:"XGBoost trained on millions of fare datapoints. Real-time confidence scores, recommendation, and market status.", icon:<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg> },
              { n:"02 / FORECAST", title:"30-Day Price Forecast", desc:"POST /predict generates a full trajectory with confidence bands. See the best and worst booking windows before you commit.", icon:<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg> },
              { n:"03 / ALERTS", title:"Smart Price Alerts", desc:"Set a target price. Our scheduler monitors 24/7 and notifies via Email + SMS the moment it's reached.", icon:<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></svg> },
              { n:"04 / BOOKING", title:"Seamless Booking", desc:"Full Razorpay integration — UPI, cards, netbanking. Instant confirmation with email notifications.", icon:<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg> },
            ].map(f => (
              <div key={f.n} className="feat-card">
                <div className="feat-num">{f.n}</div>
                <div className="feat-icon-wrap">{f.icon}</div>
                <div className="feat-title">{f.title}</div>
                <div className="feat-desc">{f.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── DESTINATIONS ── */}
      <div className="dest-section">
        <div className="wrap">
          <div style={{ display:"flex", alignItems:"flex-end", justifyContent:"space-between", flexWrap:"wrap", gap:16, marginBottom:32 }}>
            <div>
              <div className="section-eyebrow" style={{ marginBottom:8 }}>
                <span className="label">Trending now</span>
                <div className="section-eyebrow-line" style={{ maxWidth:60 }} />
              </div>
              <h2 style={{ fontFamily:"var(--fd)", fontSize:"clamp(1.8rem,4vw,3rem)", letterSpacing:".03em", color:"var(--black)" }}>POPULAR ROUTES</h2>
            </div>
            <Link href="/flights" className="btn-outline" style={{ fontSize:".82rem" }}>
              All routes <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
            </Link>
          </div>
          <PopularDestinations />
        </div>
      </div>

      {/* ── CTA ── */}
      <div className="cta-band">
        <div className="wrap">
          <div className="cta-inner">
            <div>
              <div className="label" style={{ color:"rgba(255,255,255,.3)", marginBottom:16 }}>SkyMind — AI Flight Platform</div>
              <div className="cta-title">
                READY TO FLY
                <em>smarter than ever?</em>
              </div>
            </div>
            <div className="cta-btns">
              <Link href="/flights" className="btn-white">Search flights</Link>
              <Link href="/predict" className="btn-white-outline">View predictions</Link>
            </div>
          </div>
        </div>
      </div>

      {/* ── FOOTER ── */}
      <footer>
        <div className="wrap">
          <div className="footer-inner">
            <div className="footer-logo">SKY<em>MIND</em></div>
            <span className="footer-copy">© 2026 SkyMind · AI Flight Intelligence · India</span>
            <div className="footer-links">
              <Link href="/flights" className="footer-link">Search</Link>
              <Link href="/predict" className="footer-link">Predict</Link>
              <Link href="/dashboard" className="footer-link">Dashboard</Link>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
