"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import NavBar from "@/components/layout/NavBar";
import PopularDestinations from "@/components/flights/PopularDestinations";
import { resolveCityToIATA } from "@/lib/api";
import { format, addDays } from "date-fns";

/* ── Animated counter ──────────────────────────────── */
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
    }, { threshold: .5 });
    if (ref.current) obs.observe(ref.current);
    return () => obs.disconnect();
  }, [to]);
  return <div ref={ref}>{val}<span className="unit">{suf}</span></div>;
}

/* ── Passenger Dropdown ────────────────────────────── */
function PassengerDropdown({
  adults, children, infants,
  onChange,
}: {
  adults: number; children: number; infants: number;
  onChange: (a: number, c: number, i: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const fn = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", fn);
    return () => document.removeEventListener("mousedown", fn);
  }, []);

  const total = adults + children + infants;
  const label = `${total} Passenger${total !== 1 ? "s" : ""}`;

  const update = (type: "adults" | "children" | "infants", delta: number) => {
    const next = { adults, children, infants };
    next[type] = Math.max(type === "adults" ? 1 : 0, Math.min(9, next[type] + delta));
    onChange(next.adults, next.children, next.infants);
  };

  return (
    <div ref={wrapRef} className="pax-dropdown">
      <label className="field-label">Passengers</label>
      <button
        type="button"
        className={`pax-trigger${open ? " open" : ""}`}
        onClick={() => setOpen(o => !o)}
      >
        <span style={{ fontWeight: 600 }}>{label}</span>
        <svg width="10" height="6" viewBox="0 0 10 6" fill="none"
          style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform .2s", flexShrink: 0 }}>
          <path d="M1 1L5 5L9 1" stroke="#9b9890" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </button>
      {open && (
        <div className="pax-panel">
          {[
            { key: "adults" as const, label: "Adults", sub: "Age 12+", val: adults, min: 1 },
            { key: "children" as const, label: "Children", sub: "Age 2–11", val: children, min: 0 },
            { key: "infants" as const, label: "Infants", sub: "Under 2", val: infants, min: 0 },
          ].map(r => (
            <div key={r.key} className="pax-row">
              <div>
                <div className="pax-label">{r.label}</div>
                <div className="pax-sub">{r.sub}</div>
              </div>
              <div className="pax-counter">
                <button type="button" className="pax-btn"
                  disabled={r.val <= r.min}
                  onClick={() => update(r.key, -1)}>−</button>
                <span className="pax-num">{r.val}</span>
                <button type="button" className="pax-btn"
                  disabled={total >= 9}
                  onClick={() => update(r.key, 1)}>+</button>
              </div>
            </div>
          ))}
          <button type="button" onClick={() => setOpen(false)}
            style={{ width: "100%", marginTop: 10, padding: "9px", background: "var(--black)", color: "#fff", border: "none", cursor: "pointer", fontFamily: "var(--fb)", fontWeight: 700, fontSize: ".78rem", letterSpacing: ".04em" }}>
            Done
          </button>
        </div>
      )}
    </div>
  );
}

const TICKER_ITEMS = [
  "Amadeus GDS", "XGBoost Analytics", "Supabase", "Razorpay PCI-DSS",
  "FastAPI", "90+ Indian Airports", "APScheduler", "scikit-learn 1.5",
  "XGBoost 2.0.3", "MAE ₹840 · Accuracy 88.1%",
];

export default function HomePage() {
  const router = useRouter();
  const defaultDate = format(addDays(new Date(), 7), "yyyy-MM-dd");
  const tomorrow    = format(addDays(new Date(), 1), "yyyy-MM-dd");

  const [form, setForm] = useState({
    from:       "New Delhi (DEL)",
    to:         "Mumbai (BOM)",
    date:       defaultDate,
    returnDate: "",
    adults:     1,
    children:   0,
    infants:    0,
    cabin:      "Economy",
    tripType:   "one-way",
  });
  const [swapping, setSwapping] = useState(false);

  const swap = () => {
    setSwapping(true);
    setTimeout(() => setSwapping(false), 320);
    setForm(f => ({ ...f, from: f.to, to: f.from }));
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const origin = resolveCityToIATA(form.from.replace(/\s*\(.*\)/, "").trim()) || "DEL";
    const dest   = resolveCityToIATA(form.to.replace(/\s*\(.*\)/, "").trim()) || "BOM";
    const cabinParam = form.cabin.toUpperCase().replace(" ", "_");
    const qs = new URLSearchParams({
      origin,
      destination: dest,
      departure_date: form.date,
      adults: String(form.adults),
      cabin_class: cabinParam,
      ...(form.tripType === "round-trip" && form.returnDate
        ? { return_date: form.returnDate }
        : {}),
    });
    router.push(`/flights?${qs}`);
  };

  return (
    <div>
      <NavBar />

      {/* ── HERO ── */}
      <div className="hero">
        {/* Left column */}
        <div className="hero-left a1">
          <div className="hero-issue">Vol. 4 — XGBoost Analytics Platform</div>
          <h1 className="hero-title">
            FLY<br />SMARTER
            <span className="red-line">with machine<br />intelligence.</span>
          </h1>
          <p className="hero-desc">
            AI-powered fare predictions across 90+ Indian airports.
            Live Amadeus GDS, 30-day price trajectories, and smart alerts — all in one interface.
          </p>
          <div className="hero-ctas">
            <Link href="/flights" className="btn-primary">
              Search flights
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </Link>
            <Link href="/predict" className="btn-outline">AI forecast</Link>
          </div>
          <div className="hero-stats">
            {[
              { to: 2,  suf: "M+", label: "Fares analysed" },
              { to: 38, suf: "%",  label: "Avg savings" },
              { to: 94, suf: "%",  label: "Model accuracy" },
            ].map(s => (
              <div key={s.label} className="hero-stat">
                <div className="hero-stat-num"><Counter to={s.to} suf={s.suf} /></div>
                <div className="hero-stat-label">{s.label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Search panel */}
        <div className="hero-right a2">
          <div className="hero-right-label">Find your flight — XGBoost-optimised</div>

          <div className="search-box">
            {/* ── Trip type — CENTRED ── */}
            <div className="trip-tabs-wrap">
              <div className="trip-tabs">
                {[
                  { key: "one-way",    label: "One Way" },
                  { key: "round-trip", label: "Round Trip" },
                ].map(t => (
                  <button
                    key={t.key}
                    className={`trip-tab${form.tripType === t.key ? " active" : ""}`}
                    type="button"
                    onClick={() =>
                      setForm(f => ({
                        ...f,
                        tripType: t.key,
                        returnDate: t.key === "one-way" ? "" : f.returnDate,
                      }))
                    }
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>

            <form onSubmit={handleSearch}>
              {/* Origin / Swap / Destination */}
              <div className="route-row">
                <div>
                  <label className="field-label">From</label>
                  <input
                    className="inp"
                    value={form.from}
                    onChange={e => setForm(f => ({ ...f, from: e.target.value }))}
                    placeholder="New Delhi (DEL)"
                  />
                </div>
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
                <div>
                  <label className="field-label">To</label>
                  <input
                    className="inp"
                    value={form.to}
                    onChange={e => setForm(f => ({ ...f, to: e.target.value }))}
                    placeholder="Mumbai (BOM)"
                  />
                </div>
              </div>

              {/* Dates — shows return only for round-trip */}
              <div className={`dates-row${form.tripType === "round-trip" ? " round-trip" : ""}`}>
                <div>
                  <label className="field-label">Departure</label>
                  <input
                    type="date"
                    className="inp"
                    value={form.date}
                    min={tomorrow}
                    required
                    onChange={e => setForm(f => ({ ...f, date: e.target.value }))}
                  />
                </div>
                {form.tripType === "round-trip" && (
                  <div>
                    <label className="field-label">Return</label>
                    <input
                      type="date"
                      className="inp"
                      value={form.returnDate}
                      min={form.date || tomorrow}
                      onChange={e => setForm(f => ({ ...f, returnDate: e.target.value }))}
                    />
                  </div>
                )}
              </div>

              {/* Passengers + Class */}
              <div className="pax-class-row">
                <PassengerDropdown
                  adults={form.adults}
                  children={form.children}
                  infants={form.infants}
                  onChange={(a, c, i) => setForm(f => ({ ...f, adults: a, children: c, infants: i }))}
                />
                <div>
                  <label className="field-label">Class</label>
                  <select
                    className="inp"
                    value={form.cabin}
                    onChange={e => setForm(f => ({ ...f, cabin: e.target.value }))}
                  >
                    <option>Economy</option>
                    <option>Business</option>
                    <option>First</option>
                  </select>
                </div>
              </div>

              <button type="submit" className="search-submit">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" />
                </svg>
                Search Flights
              </button>
            </form>
          </div>

          {/* Model badge */}
          <div style={{
            display: "flex", alignItems: "center", gap: 12, padding: 14,
            background: "rgba(19,18,16,.03)", border: "1px solid var(--grey1)",
          }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--red)" strokeWidth="2">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
            </svg>
            <div>
              <div style={{ fontSize: ".72rem", fontWeight: 700, color: "var(--black)", letterSpacing: ".04em" }}>
                XGBoost Analytics Active
              </div>
              <div style={{ fontSize: ".6rem", color: "var(--grey3)", fontFamily: "var(--fm)", marginTop: 2 }}>
                900 estimators · 94.1% accuracy · POST /predict
              </div>
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
            <span className="label label-red">03 systems</span>
          </div>
          <div className="how-grid" style={{ marginTop: 40 }}>
            <div className="how-left">
              <h2 style={{ fontFamily: "var(--fd)", fontSize: "clamp(2.2rem,6vw,4.5rem)", letterSpacing: ".02em", lineHeight: .95, color: "var(--black)", marginBottom: 18 }}>
                NOT<br />JUST<br />SEARCH.
              </h2>
              <p style={{ fontSize: ".88rem", color: "var(--grey4)", lineHeight: 1.7, maxWidth: 340, marginBottom: 28 }}>
                SkyMind layers XGBoost ML on top of live Amadeus GDS fare data
                to surface the optimal booking window before prices move.
              </p>
              {[
                { n: "01", title: "Live fare ingestion", desc: "Amadeus GDS feeds pulled on demand across 90+ Indian airports and international hubs." },
                { n: "02", title: "XGBoost inference", desc: "900-estimator gradient boosting. Urgency, seasonality, demand scoring — confidence-weighted." },
                { n: "03", title: "30-day trajectory", desc: "Deterministic forecast with confidence intervals. Best day, peak day — before you commit." },
              ].map(s => (
                <div key={s.n} className="how-step">
                  <span className="how-step-num">{s.n}</span>
                  <div>
                    <div className="how-step-title">{s.title}</div>
                    <div className="how-step-desc">{s.desc}</div>
                  </div>
                </div>
              ))}
              <div style={{ display: "flex", gap: 10, marginTop: 24, flexWrap: "wrap" }}>
                <Link href="/flights" className="btn-primary">
                  Search flights
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M5 12h14M12 5l7 7-7 7" /></svg>
                </Link>
                <Link href="/predict" className="btn-outline">AI forecast</Link>
              </div>
            </div>
            <div className="how-right">
              <div className="label" style={{ marginBottom: 14 }}>Live predictions</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
                {[
                  { route: "DEL → BOM", label: "Domestic", price: "₹4,850", conf: 78, trend: "Rising", color: "var(--red)", bClass: "badge-red" },
                  { route: "BOM → GOI", label: "Beach",    price: "₹3,290", conf: 62, trend: "Falling", color: "#16a34a", bClass: "badge-green" },
                  { route: "DEL → BLR", label: "Tech",     price: "₹5,100", conf: 85, trend: "Stable",  color: "#2563eb", bClass: "badge-off" },
                ].map(item => (
                  <div key={item.route} style={{ background: "var(--white)", border: "1px solid var(--grey1)", padding: 14, display: "flex", alignItems: "center", justifyContent: "space-between", transition: "border-color .2s, transform .2s" }}
                    onMouseEnter={e => { const el = e.currentTarget as HTMLElement; el.style.borderColor = "var(--black)"; el.style.transform = "translateY(-1px)"; }}
                    onMouseLeave={e => { const el = e.currentTarget as HTMLElement; el.style.borderColor = "var(--grey1)"; el.style.transform = "none"; }}>
                    <div>
                      <div style={{ fontFamily: "var(--fm)", fontSize: ".6rem", color: "var(--grey3)", marginBottom: 5 }}>{item.route} · {item.label}</div>
                      <div style={{ fontFamily: "var(--fd)", fontSize: "1.5rem", letterSpacing: ".03em", color: "var(--black)" }}>{item.price}</div>
                      <div className="conf-bar-wrap" style={{ width: 100 }}>
                        <div className="conf-bar-fill" style={{ width: `${item.conf}%`, background: item.color }} />
                      </div>
                      <div style={{ fontSize: ".58rem", color: "var(--grey3)", fontFamily: "var(--fm)", marginTop: 2 }}>{item.conf}% confidence</div>
                    </div>
                    <span className={`badge ${item.bClass}`}>{item.trend}</span>
                  </div>
                ))}
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 1, background: "var(--grey1)", border: "1px solid var(--grey1)", overflow: "hidden" }}>
                {[["Avg saving","₹1,200"],["Accuracy","94.1%"],["Routes","240+"]].map(([l,v]) => (
                  <div key={l} style={{ background: "var(--white)", padding: 14 }}>
                    <div style={{ fontFamily: "var(--fm)", fontSize: ".56rem", color: "var(--grey3)", textTransform: "uppercase", letterSpacing: ".08em", marginBottom: 5 }}>{l}</div>
                    <div style={{ fontFamily: "var(--fd)", fontSize: "1.3rem", letterSpacing: ".03em", color: "var(--black)" }}>{v}</div>
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
          <div className="section-eyebrow" style={{ marginBottom: 28 }}>
            <span className="label">Core capabilities</span>
            <div className="section-eyebrow-line" />
            <span className="label label-red">04 systems</span>
          </div>
          <div className="feat-grid">
            {[
              { n: "01", title: "ML Price Intelligence",  desc: "XGBoost trained on millions of fare datapoints. Confidence scores, recommendation, market status.", icon: <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg> },
              { n: "02", title: "30-Day Price Forecast",  desc: "Full trajectory with confidence bands. Best and worst booking windows — before you commit.", icon: <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg> },
              { n: "03", title: "Smart Price Alerts",     desc: "Set a target price. We monitor 24/7 and notify via Email + SMS the moment it's reached.", icon: <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></svg> },
              { n: "04", title: "Seamless Booking",       desc: "Full Razorpay integration — UPI, cards, netbanking. Instant confirmation and email receipt.", icon: <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg> },
            ].map(f => (
              <div key={f.n} className="feat-card">
                <div className="feat-num">0{f.n.slice(-1)} / {f.title.split(" ")[0].toUpperCase()}</div>
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
          <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", flexWrap: "wrap", gap: 12, marginBottom: 24 }}>
            <div>
              <div className="section-eyebrow" style={{ marginBottom: 6 }}>
                <span className="label">Trending now</span>
                <div className="section-eyebrow-line" style={{ maxWidth: 50 }} />
              </div>
              <h2 style={{ fontFamily: "var(--fd)", fontSize: "clamp(1.6rem,5vw,3rem)", letterSpacing: ".03em", color: "var(--black)" }}>POPULAR ROUTES</h2>
            </div>
            <Link href="/flights" className="btn-outline" style={{ fontSize: ".8rem", minHeight: 38, padding: "0 16px" }}>
              All routes
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M5 12h14M12 5l7 7-7 7" /></svg>
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
              <div className="label" style={{ color: "rgba(255,255,255,.3)", marginBottom: 14 }}>SkyMind — AI Flight Platform</div>
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
              <Link href="/flights"   className="footer-link">Search</Link>
              <Link href="/predict"   className="footer-link">Predict</Link>
              <Link href="/dashboard" className="footer-link">Dashboard</Link>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
