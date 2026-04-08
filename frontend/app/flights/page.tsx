"use client";

import { useState, useEffect, useCallback, useRef, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import NavBar from "@/components/layout/NavBar";
import { searchFlights, formatDuration, resolveCityToIATA } from "@/lib/api";
import type { FlightOffer } from "@/types";
import { format, addDays } from "date-fns";

/* ── Passenger dropdown ────────────────────────────── */
function PassengerDropdown({
  adults, children, infants, onChange,
}: { adults: number; children: number; infants: number; onChange: (a: number, c: number, i: number) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const fn = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", fn);
    return () => document.removeEventListener("mousedown", fn);
  }, []);
  const total = adults + children + infants;
  const upd = (t: "adults" | "children" | "infants", d: number) => {
    const n = { adults, children, infants };
    n[t] = Math.max(t === "adults" ? 1 : 0, Math.min(9, n[t] + d));
    onChange(n.adults, n.children, n.infants);
  };
  return (
    <div ref={ref} className="pax-dropdown">
      <label className="field-label">Passengers</label>
      <button type="button" className={`pax-trigger${open ? " open" : ""}`} onClick={() => setOpen(o => !o)}>
        <span style={{ fontWeight: 600 }}>{total} Passenger{total !== 1 ? "s" : ""}</span>
        <svg width="10" height="6" viewBox="0 0 10 6" fill="none" style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform .2s", flexShrink: 0 }}>
          <path d="M1 1L5 5L9 1" stroke="#9b9890" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </button>
      {open && (
        <div className="pax-panel">
          {[
            { k: "adults"   as const, l: "Adults",   s: "Age 12+",  v: adults,   m: 1 },
            { k: "children" as const, l: "Children", s: "Age 2–11", v: children, m: 0 },
            { k: "infants"  as const, l: "Infants",  s: "Under 2",  v: infants,  m: 0 },
          ].map(r => (
            <div key={r.k} className="pax-row">
              <div><div className="pax-label">{r.l}</div><div className="pax-sub">{r.s}</div></div>
              <div className="pax-counter">
                <button type="button" className="pax-btn" disabled={r.v <= r.m} onClick={() => upd(r.k, -1)}>−</button>
                <span className="pax-num">{r.v}</span>
                <button type="button" className="pax-btn" disabled={total >= 9} onClick={() => upd(r.k, 1)}>+</button>
              </div>
            </div>
          ))}
          <button type="button" onClick={() => setOpen(false)} style={{ width: "100%", marginTop: 10, padding: "9px", background: "var(--black)", color: "#fff", border: "none", cursor: "pointer", fontFamily: "var(--fb)", fontWeight: 700, fontSize: ".8rem" }}>Done</button>
        </div>
      )}
    </div>
  );
}

/* ── AI Insight bar ────────────────────────────────── */
function AIInsightBar({ origin, dest, flights }: { origin: string; dest: string; flights: FlightOffer[] }) {
  if (!flights.length) return null;
  const f = flights[0];
  const raw = (f.trend || "STABLE").toUpperCase();
  const tc = raw.includes("INCREAS") || raw.includes("RISING") ? "rising" : raw.includes("DECREAS") || raw.includes("FALLING") ? "falling" : "stable";
  return (
    <div className="ai-insight-bar">
      <div style={{ flexShrink: 0 }}>
        <div style={{ fontFamily: "var(--fm)", fontSize: "clamp(.65rem,1.7vw,.72rem)", fontWeight: 700, color: "var(--black)" }}>{origin} → {dest}</div>
        <div style={{ fontSize: "clamp(.55rem,1.4vw,.6rem)", color: "var(--grey3)", fontFamily: "var(--fm)", marginTop: 1 }}>AI Price Intelligence</div>
      </div>
      <div className={`ai-insight-trend ${tc}`}>{tc === "rising" ? "↑ RISING" : tc === "falling" ? "↓ FALLING" : "→ STABLE"}</div>
      {f.ai_price && (
        <div style={{ fontSize: "clamp(.68rem,1.7vw,.74rem)", color: "var(--grey4)", fontFamily: "var(--fm)", flexShrink: 0 }}>
          AI: <strong style={{ color: "var(--black)" }}>₹{Math.round(f.ai_price).toLocaleString("en-IN")}</strong>
        </div>
      )}
      <div className="ai-insight-text">{f.advice || "Prices are within normal range."}</div>
      <div className="ai-insight-ctas">
        <Link href={`/predict?origin=${origin}&destination=${dest}`}
          style={{ padding: "8px 14px", background: "transparent", color: "var(--black)", border: "1px solid var(--grey2)", fontFamily: "var(--fb)", fontWeight: 600, fontSize: "clamp(.7rem,1.8vw,.76rem)", textDecoration: "none", display: "inline-flex", alignItems: "center", minHeight: 36, whiteSpace: "nowrap" }}>
          Set Alert
        </Link>
      </div>
    </div>
  );
}

/* ── Filter bar ────────────────────────────────────── */
function FilterBar({ active, onChange }: { active: string; onChange: (f: string) => void }) {
  return (
    <div className="filter-bar">
      {[
        { id: "all", label: "All Flights" }, { id: "nonstop", label: "Non-stop" },
        { id: "cheapest", label: "Cheapest" }, { id: "fastest", label: "Fastest" },
        { id: "morning", label: "Morning" }, { id: "evening", label: "Evening" },
      ].map(f => (
        <button key={f.id} className={`filter-btn${active === f.id ? " active" : ""}`} onClick={() => onChange(f.id)}>{f.label}</button>
      ))}
    </div>
  );
}

/* ── Rec badge ─────────────────────────────────────── */
function RecBadge({ rec }: { rec?: string }) {
  if (!rec) return null;
  const r = rec.toUpperCase();
  if (r.includes("BOOK") || r.includes("NOW")) return <span className="badge badge-red">Book Now</span>;
  if (r.includes("WAIT")) return <span className="badge badge-amber">Wait</span>;
  if (r.includes("FAIR") || r.includes("STABLE")) return <span className="badge badge-green">Fair Price</span>;
  return null;
}

/* ── Skeleton card ─────────────────────────────────── */
function SkeletonCard() {
  return (
    <div className="flight-card" style={{ cursor: "default" }}>
      <div className="flight-top">
        <div className="flight-airline">
          <div className="skel" style={{ width: 42, height: 42, borderRadius: 4, flexShrink: 0 }} />
          <div style={{ flex: 1 }}>
            <div className="skel" style={{ height: 11, width: "80%", marginBottom: 7 }} />
            <div className="skel" style={{ height: 9, width: "55%" }} />
          </div>
        </div>
        <div className="flight-timeline">
          <div><div className="skel" style={{ height: 26, width: 60, marginBottom: 5 }} /><div className="skel" style={{ height: 9, width: 26 }} /></div>
          <div className="t-mid" style={{ flex: 1 }}><div className="skel" style={{ height: 1, width: "100%", margin: "14px 0" }} /></div>
          <div style={{ textAlign: "right" }}><div className="skel" style={{ height: 26, width: 60, marginBottom: 5 }} /><div className="skel" style={{ height: 9, width: 26 }} /></div>
        </div>
        <div className="flight-price-col">
          <div><div className="skel" style={{ height: 26, width: 80, marginBottom: 5 }} /><div className="skel" style={{ height: 9, width: 55 }} /></div>
          <div className="skel" style={{ height: 40, width: 110 }} />
        </div>
      </div>
      <div className="flight-bottom">
        <div className="skel" style={{ height: 18, width: 80 }} />
        <div className="skel" style={{ height: 12, width: 55 }} />
      </div>
    </div>
  );
}

/* ── Main content ──────────────────────────────────── */
function FlightsContent() {
  const router = useRouter();
  const params = useSearchParams();
  const tomorrow    = format(addDays(new Date(), 1), "yyyy-MM-dd");
  const defaultDate = format(addDays(new Date(), 7), "yyyy-MM-dd");

  const [tripType, setTripType] = useState<"one-way" | "round-trip">("one-way");
  const [form, setForm] = useState({
    origin:         params.get("origin")         || "DEL",
    destination:    params.get("destination")    || "BOM",
    departure_date: params.get("departure_date") || defaultDate,
    return_date:    params.get("return_date")    || "",
    adults:    parseInt(params.get("adults") || "1"),
    children:  0, infants: 0,
    cabin_class: params.get("cabin_class") || "ECONOMY",
  });
  const [swapping,     setSwapping]     = useState(false);
  const [flights,      setFlights]      = useState<FlightOffer[]>([]);
  const [allFlights,   setAllFlights]   = useState<FlightOffer[]>([]);
  const [loading,      setLoading]      = useState(false);
  const [error,        setError]        = useState("");
  const [sort,         setSort]         = useState("Price");
  const [activeFilter, setActiveFilter] = useState("all");
  const [searched,     setSearched]     = useState(false);
  const [dataSource,   setDataSource]   = useState("");

  const swap = () => {
    setSwapping(true);
    setTimeout(() => setSwapping(false), 320);
    setForm(f => ({ ...f, origin: f.destination, destination: f.origin }));
  };

  const applyFilter = useCallback((list: FlightOffer[], s: string, filter: string) => {
    let arr = [...list];
    if (filter === "nonstop")  arr = arr.filter(f => (f.itineraries[0]?.segments?.length ?? 1) === 1);
    else if (filter === "cheapest") arr.sort((a, b) => a.price.total - b.price.total);
    else if (filter === "fastest")  arr.sort((a, b) => (a.itineraries[0]?.duration || "").localeCompare(b.itineraries[0]?.duration || ""));
    else if (filter === "morning")  arr = arr.filter(f => { const h = new Date(f.itineraries[0]?.segments[0]?.departure_time || "").getHours(); return h >= 5 && h < 12; });
    else if (filter === "evening")  arr = arr.filter(f => { const h = new Date(f.itineraries[0]?.segments[0]?.departure_time || "").getHours(); return h >= 17 && h < 23; });
    if (s === "Price")     arr.sort((a, b) => a.price.total - b.price.total);
    else if (s === "Duration")  arr.sort((a, b) => (a.itineraries[0]?.duration || "").localeCompare(b.itineraries[0]?.duration || ""));
    else if (s === "Departure") arr.sort((a, b) => (a.itineraries[0]?.segments[0]?.departure_time || "").localeCompare(b.itineraries[0]?.segments[0]?.departure_time || ""));
    return arr;
  }, []);

  const doSearch = useCallback(async (f = form) => {
    const org = resolveCityToIATA(f.origin.trim());
    const dst = resolveCityToIATA(f.destination.trim());
    if (!org || !dst) { setError("Enter origin and destination."); return; }
    if (org === dst)  { setError("Origin and destination cannot be the same."); return; }
    if (f.departure_date < tomorrow) { setError("Please select a future date."); return; }
    setLoading(true); setError(""); setSearched(true); setActiveFilter("all");
    try {
      const res = await searchFlights({ origin: org, destination: dst, departure_date: f.departure_date, adults: f.adults, cabin_class: f.cabin_class as any, max_results: 20, ...(tripType === "round-trip" && f.return_date ? { return_date: f.return_date } : {}) });
      const sorted = applyFilter(res.flights || [], sort, "all");
      setAllFlights(res.flights || []);
      setFlights(sorted);
      setDataSource((res as any).data_source || "");
    } catch (e: any) {
      setError(e.message || "Search failed."); setFlights([]); setAllFlights([]);
    }
    setLoading(false);
  }, [form, sort, tomorrow, applyFilter, tripType]);

  useEffect(() => { if (params.get("origin")) doSearch(); }, []);

  const handleFilter = (f: string) => { setActiveFilter(f); setFlights(applyFilter(allFlights, sort, f)); };
  const handleSort   = (s: string) => { setSort(s); setFlights(applyFilter(allFlights, s, activeFilter)); };

  return (
    <div style={{ paddingTop: "var(--nav-h)" }}>

      {/* ══ SEARCH STRIP ══ */}
      <div className="search-strip">
        <div className="wrap">

          {/* Trip type toggle inside strip */}
          <div className="strip-trip-tabs">
            <div className="trip-tabs">
              {[
                { k: "one-way"    as const, l: "One Way" },
                { k: "round-trip" as const, l: "Round Trip" },
              ].map(t => (
                <button key={t.k} className={`trip-tab${tripType === t.k ? " active" : ""}`} type="button"
                  onClick={() => { setTripType(t.k); if (t.k === "one-way") setForm(f => ({ ...f, return_date: "" })); }}>
                  {t.l}
                </button>
              ))}
            </div>
          </div>

          {/* Route row */}
          <div className="strip-route">
            <div>
              <label className="field-label">From</label>
              <input className="inp" value={form.origin}
                onChange={e => setForm(f => ({ ...f, origin: e.target.value.toUpperCase() }))}
                placeholder="DEL" style={{ fontFamily: "var(--fm)", fontWeight: 700 }} />
            </div>
            <div style={{ display: "flex", alignItems: "flex-end" }}>
              <button type="button" className="swap-btn" onClick={swap}
                style={{ transform: swapping ? "rotate(180deg)" : "none", transition: "transform .32s ease" }}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M7 16V4m0 0L3 8m4-4l4 4M17 8v12m0 0l4-4m-4 4l-4-4" />
                </svg>
              </button>
            </div>
            <div>
              <label className="field-label">To</label>
              <input className="inp" value={form.destination}
                onChange={e => setForm(f => ({ ...f, destination: e.target.value.toUpperCase() }))}
                placeholder="BOM" style={{ fontFamily: "var(--fm)", fontWeight: 700 }} />
            </div>
          </div>

          {/* Bottom row: date(s) + pax + class + search */}
          <div className="strip-bottom">
            <div>
              <label className="field-label">Departure</label>
              <input type="date" className="inp" value={form.departure_date} min={tomorrow}
                onChange={e => setForm(f => ({ ...f, departure_date: e.target.value }))} />
            </div>

            {tripType === "round-trip" ? (
              <div>
                <label className="field-label">Return</label>
                <input type="date" className="inp" value={form.return_date} min={form.departure_date || tomorrow}
                  onChange={e => setForm(f => ({ ...f, return_date: e.target.value }))} />
              </div>
            ) : (
              /* Empty cell on one-way to keep grid aligned */
              <div style={{ display: "none" }} />
            )}

            <PassengerDropdown adults={form.adults} children={form.children} infants={form.infants}
              onChange={(a, c, i) => setForm(f => ({ ...f, adults: a, children: c, infants: i }))} />

            <div>
              <label className="field-label">Class</label>
              <select className="inp" value={form.cabin_class}
                onChange={e => setForm(f => ({ ...f, cabin_class: e.target.value }))}>
                <option value="ECONOMY">Economy</option>
                <option value="PREMIUM_ECONOMY">Prem Economy</option>
                <option value="BUSINESS">Business</option>
                <option value="FIRST">First</option>
              </select>
            </div>

            <div className="strip-search-btn">
              <label className="field-label" style={{ visibility: "hidden" }}>_</label>
              <button className="btn-search-inline" style={{ width: "100%", height: "var(--inp-h)" }} onClick={() => doSearch()} disabled={loading}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" />
                </svg>
                {loading ? "Searching…" : "Search"}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ══ RESULTS ══ */}
      <div className="wrap" style={{ paddingTop: "clamp(18px,3vw,24px)", paddingBottom: 60 }}>

        {error && (
          <div className="error-state">
            <div style={{ fontWeight: 700, color: "var(--red)", marginBottom: 5, fontFamily: "var(--fm)", fontSize: "clamp(.68rem,1.7vw,.75rem)" }}>SEARCH FAILED</div>
            <div style={{ fontSize: "clamp(.8rem,2vw,.86rem)", color: "var(--grey4)", marginBottom: 10 }}>{error}</div>
            <button className="btn-primary" onClick={() => doSearch()} style={{ fontSize: "clamp(.75rem,2vw,.8rem)" }}>Try again</button>
          </div>
        )}

        {(searched || loading) && (
          <div className="results-bar">
            <div>
              <div className="results-title">
                <span style={{ fontFamily: "var(--fm)", fontWeight: 700 }}>{form.origin}</span>
                <span style={{ color: "var(--grey3)" }}> → </span>
                <span style={{ fontFamily: "var(--fm)", fontWeight: 700 }}>{form.destination}</span>
                {tripType === "round-trip" && form.return_date && (
                  <span style={{ color: "var(--grey3)", fontFamily: "var(--fm)", fontSize: "clamp(.65rem,1.6vw,.7rem)" }}> · Return {form.return_date}</span>
                )}
                <span className="badge badge-black" style={{ marginLeft: 8, verticalAlign: "middle" }}>{form.departure_date}</span>
              </div>
              <div className="results-count">
                {loading ? "Searching live fares…" : `${flights.length} flight${flights.length !== 1 ? "s" : ""} found`}
                {dataSource && !loading && <span style={{ marginLeft: 6 }}>· {dataSource === "AMADEUS" ? "Live GDS" : "Synthetic"}</span>}
              </div>
            </div>
            <div className="sort-strip">
              {["Price", "Duration", "Departure"].map(s => (
                <button key={s} className={`sort-btn${sort === s ? " active" : ""}`} onClick={() => handleSort(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}

        {!loading && flights.length > 0 && <AIInsightBar origin={form.origin} dest={form.destination} flights={flights} />}
        {!loading && flights.length > 0 && <FilterBar active={activeFilter} onChange={handleFilter} />}

        {loading && Array.from({ length: 4 }).map((_, i) => (
          <div key={i} style={{ animation: `fadeUp .35s ${i * 0.06}s ease both` }}><SkeletonCard /></div>
        ))}

        {!loading && searched && flights.length === 0 && !error && (
          <div className="empty-state">
            <div style={{ width: 46, height: 46, background: "var(--off)", border: "1px solid var(--grey1)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 16px", color: "var(--grey3)" }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M17.8 19.2L16 11l3.5-3.5C21 6 21 4 19.5 2.5S18 2 16.5 3.5L13 7 4.8 6.2c-.5-.1-.9.1-1.1.5L2 8.9c-.2.4-.1.9.2 1.2l4.6 4.1-1.5 6.4 2.8 2.8 5.3-3.2 4.1 4.6c.3.4.8.5 1.2.2l1.1-1.2c.4-.2.6-.6.5-1.1z" /></svg>
            </div>
            <div style={{ fontFamily: "var(--fd)", fontSize: "clamp(1.4rem,4vw,1.7rem)", letterSpacing: ".04em", color: "var(--black)", marginBottom: 8 }}>NO FLIGHTS FOUND</div>
            <div style={{ fontSize: "clamp(.76rem,2vw,.84rem)", color: "var(--grey4)", marginBottom: 16, fontFamily: "var(--fm)" }}>
              {activeFilter !== "all" ? "Try removing filters" : "Try: DEL→BOM · BOM→BLR"}
            </div>
            <div style={{ display: "flex", gap: 10, justifyContent: "center", flexWrap: "wrap" }}>
              {activeFilter !== "all" && <button className="btn-outline" onClick={() => handleFilter("all")}>Clear Filters</button>}
              <button className="btn-primary" onClick={() => doSearch()}>Search Again</button>
            </div>
          </div>
        )}

        {!searched && !loading && (
          <div className="empty-state">
            <div style={{ width: 46, height: 46, background: "var(--off)", border: "1px solid var(--grey1)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 16px", color: "var(--grey3)" }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" /></svg>
            </div>
            <div style={{ fontFamily: "var(--fd)", fontSize: "clamp(1.4rem,4vw,1.7rem)", letterSpacing: ".04em", color: "var(--black)", marginBottom: 8 }}>SEARCH FLIGHTS</div>
            <div style={{ fontSize: "clamp(.76rem,2vw,.84rem)", color: "var(--grey4)", fontFamily: "var(--fm)", lineHeight: 1.7 }}>Enter your route and hit Search<br />to see AI-powered results</div>
          </div>
        )}

        {/* Flight cards */}
        {flights.map((f, i) => {
          const itin  = f.itineraries[0];
          const seg   = itin?.segments[0];
          const last  = itin?.segments[itin.segments.length - 1];
          const stops = (itin?.segments.length || 1) - 1;
          const dep   = seg?.departure_time ? new Date(seg.departure_time).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false }) : "--:--";
          const arr   = last?.arrival_time  ? new Date(last.arrival_time ).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false }) : "--:--";
          const dur   = formatDuration(itin?.duration || "");
          const code  = f.primary_airline || seg?.airline_code || "AI";
          const name  = f.primary_airline_name || seg?.airline_name || code;
          const price = Math.round(f.price.total);
          const aiP   = f.ai_price ? Math.round(f.ai_price) : null;
          const first = i === 0;
          const go = () => {
            if (typeof window !== "undefined") { sessionStorage.setItem("selected_flight", JSON.stringify(f)); sessionStorage.setItem("search_params", JSON.stringify(form)); }
            router.push("/booking");
          };
          return (
            <div key={f.id} className={`flight-card${first ? " best-card" : ""}`}
              style={{ animation: `fadeUp .4s ${Math.min(i * .06, .4)}s ease both` }}
              onClick={go}>
              {first && <div className="best-tag">Best value</div>}
              <div className="flight-top" style={{ borderTop: first ? "2px solid var(--red)" : undefined }}>
                {/* Airline */}
                <div className="flight-airline">
                  <div className="airline-logo-box">
                    <img src={`https://content.airhex.com/content/logos/airlines_${code}_200_200_s.png`} alt={name} onError={e => { (e.target as HTMLImageElement).style.display = "none"; }} />
                    {code}
                  </div>
                  <div>
                    <div className="airline-name-txt">{name}</div>
                    <div className="airline-num-txt">{seg?.flight_number || "--"}</div>
                  </div>
                </div>
                {/* Timeline */}
                <div className="flight-timeline">
                  <div style={{ flexShrink: 0 }}>
                    <div className="t-time">{dep}</div>
                    <div className="t-iata">{seg?.origin || form.origin}</div>
                  </div>
                  <div className="t-mid">
                    <div className="t-dur">{dur}</div>
                    <div className="fline" style={{ width: "100%", margin: "4px 0" }}>
                      <div className="fline-dot" />
                      <div className="fline-track" style={{ flex: 1 }}>
                        <div className="fline-plane"><svg width="11" height="11" viewBox="0 0 24 24" fill="var(--red)"><path d="M17.8 19.2L16 11l3.5-3.5C21 6 21 4 19.5 2.5S18 2 16.5 3.5L13 7 4.8 6.2c-.5-.1-.9.1-1.1.5L2 8.9c-.2.4-.1.9.2 1.2l4.6 4.1-1.5 6.4 2.8 2.8 5.3-3.2 4.1 4.6c.3.4.8.5 1.2.2l1.1-1.2c.4-.2.6-.6.5-1.1z" /></svg></div>
                      </div>
                      <div className="fline-dot" />
                    </div>
                    <div className={`t-stop${stops === 0 ? " direct" : " one-stop"}`}>{stops === 0 ? "Non-stop" : `${stops} stop${stops > 1 ? "s" : ""}`}</div>
                  </div>
                  <div style={{ flexShrink: 0, textAlign: "right" }}>
                    <div className="t-time">{arr}</div>
                    <div className="t-iata">{last?.destination || form.destination}</div>
                  </div>
                </div>
                {/* Price */}
                <div className="flight-price-col">
                  <div>
                    <div className="f-price">₹{price.toLocaleString("en-IN")}</div>
                    <div className="f-price-per">per person</div>
                    {f.seats_available && f.seats_available <= 5 && <div className="f-seats">{f.seats_available} left</div>}
                    {aiP && Math.abs(aiP - price) > 300 && <div className="f-ai-badge">AI: ₹{aiP.toLocaleString("en-IN")}</div>}
                  </div>
                  <button className="btn-select" onClick={e => { e.stopPropagation(); go(); }}>Select Flight →</button>
                </div>
              </div>
              {/* Footer */}
              <div className="flight-bottom">
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <RecBadge rec={f.recommendation} />
                  {f.advice && <span style={{ fontSize: "clamp(.66rem,1.7vw,.72rem)", color: "var(--grey3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 260 }}>{f.advice}</span>}
                  <Link href={`/predict?origin=${form.origin}&destination=${form.destination}`} onClick={e => e.stopPropagation()}
                    style={{ fontSize: "clamp(.62rem,1.6vw,.7rem)", color: "var(--red)", textDecoration: "underline", textUnderlineOffset: 2, whiteSpace: "nowrap", fontFamily: "var(--fm)" }}>
                    30-day forecast →
                  </Link>
                </div>
                <span style={{ fontSize: "clamp(.6rem,1.5vw,.66rem)", color: "var(--grey3)", fontFamily: "var(--fm)", flexShrink: 0 }}>
                  {form.cabin_class === "ECONOMY" ? "Economy" : form.cabin_class}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function FlightsPage() {
  return (
    <>
      <NavBar />
      <Suspense fallback={<div style={{ paddingTop: 100, textAlign: "center", color: "var(--grey3)", fontFamily: "var(--fm)", fontSize: "clamp(.72rem,2vw,.8rem)" }}>Loading…</div>}>
        <FlightsContent />
      </Suspense>
    </>
  );
}
