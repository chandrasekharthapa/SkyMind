"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import NavBar from "@/components/layout/NavBar";
import { searchFlights, formatDuration, resolveCityToIATA } from "@/lib/api";
import type { FlightOffer } from "@/types";
import { format, addDays } from "date-fns";

function RecommendationBadge({ rec }: { rec?: string }) {
  if (!rec) return null;
  const r = rec.toUpperCase();
  if (r.includes("BOOK NOW") || r.includes("BOOK_NOW")) return <span className="badge badge-red">Book Now 🔥</span>;
  if (r.includes("WAIT")) return <span className="badge badge-amber">Wait ⏳</span>;
  if (r.includes("FAIR") || r.includes("STABLE")) return <span className="badge badge-off">Fair Price ✅</span>;
  return <span className="badge badge-off">Monitor</span>;
}

function FlightsContent() {
  const router = useRouter();
  const params = useSearchParams();
  const tomorrow = format(addDays(new Date(), 1), "yyyy-MM-dd");
  const defaultDate = format(addDays(new Date(), 7), "yyyy-MM-dd");

  const [form, setForm] = useState({
    origin:         params.get("origin") || "DEL",
    destination:    params.get("destination") || "BOM",
    departure_date: params.get("departure_date") || defaultDate,
    adults:         params.get("adults") || "1",
    cabin_class:    params.get("cabin_class") || "ECONOMY",
  });
  const [flights, setFlights] = useState<FlightOffer[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sort, setSort] = useState("Price");
  const [searched, setSearched] = useState(false);
  const [dataSource, setDataSource] = useState("");

  const sortFlights = (list: FlightOffer[], s: string) => {
    const arr = [...list];
    if (s === "Price") arr.sort((a,b) => a.price.total - b.price.total);
    if (s === "Duration") arr.sort((a,b) => (a.itineraries[0]?.duration||"").localeCompare(b.itineraries[0]?.duration||""));
    if (s === "Departure") arr.sort((a,b) => (a.itineraries[0]?.segments[0]?.departure_time||"").localeCompare(b.itineraries[0]?.segments[0]?.departure_time||""));
    return arr;
  };

  const doSearch = async (f = form, s = sort) => {
    const org = resolveCityToIATA(f.origin.trim());
    const dst = resolveCityToIATA(f.destination.trim());
    if (!org || !dst) { setError("Enter origin and destination."); return; }
    if (org === dst) { setError("Origin and destination cannot be the same."); return; }
    if (f.departure_date < tomorrow) { setError("Please select a future date."); return; }
    setLoading(true); setError(""); setSearched(true);
    try {
      const res = await searchFlights({ origin:org, destination:dst, departure_date:f.departure_date, adults:Number(f.adults), cabin_class:f.cabin_class as any, max_results:20 });
      setFlights(sortFlights(res.flights || [], s));
      setDataSource((res as any).data_source || "");
    } catch (e: any) {
      setError(e.message || "Search failed.");
      setFlights([]);
    }
    setLoading(false);
  };

  useEffect(() => { if (params.get("origin")) doSearch(); }, []);

  return (
    <div style={{ paddingTop:60 }}>

      {/* Search strip */}
      <div className="search-strip">
        <div className="wrap">
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:10, marginBottom:10 }}>
            <div>
              <label className="field-label">From</label>
              <input className="inp" value={form.origin} onChange={e => setForm(f=>({...f,origin:e.target.value.toUpperCase()}))} placeholder="DEL" style={{ fontFamily:"var(--fm)", fontWeight:700 }} />
            </div>
            <div>
              <label className="field-label">To</label>
              <input className="inp" value={form.destination} onChange={e => setForm(f=>({...f,destination:e.target.value.toUpperCase()}))} placeholder="BOM" style={{ fontFamily:"var(--fm)", fontWeight:700 }} />
            </div>
          </div>
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr auto", gap:10, alignItems:"end" }}>
            <div>
              <label className="field-label">Date</label>
              <input type="date" className="inp" value={form.departure_date} min={tomorrow} onChange={e => setForm(f=>({...f,departure_date:e.target.value}))} />
            </div>
            <div>
              <label className="field-label">Passengers</label>
              <select className="inp" value={form.adults} onChange={e => setForm(f=>({...f,adults:e.target.value}))}>
                {[1,2,3,4,5,6].map(n => <option key={n} value={n}>{n} {n===1?"Adult":"Adults"}</option>)}
              </select>
            </div>
            <div>
              <label className="field-label">Class</label>
              <select className="inp" value={form.cabin_class} onChange={e => setForm(f=>({...f,cabin_class:e.target.value}))}>
                <option value="ECONOMY">Economy</option>
                <option value="PREMIUM_ECONOMY">Prem Economy</option>
                <option value="BUSINESS">Business</option>
                <option value="FIRST">First Class</option>
              </select>
            </div>
            <button className="btn-red-full" onClick={() => doSearch()} disabled={loading} style={{ height:44, fontSize:".82rem", gap:6 }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
              {loading ? "Searching…" : "Search"}
            </button>
          </div>
        </div>
      </div>

      {/* Results */}
      <div className="wrap" style={{ paddingTop:28, paddingBottom:60 }}>
        <div className="results-bar">
          <div>
            <div className="results-title">
              <span style={{ fontFamily:"var(--fm)", fontWeight:700 }}>{form.origin}</span>
              <span style={{ color:"var(--grey3)" }}> → </span>
              <span style={{ fontFamily:"var(--fm)", fontWeight:700 }}>{form.destination}</span>
              <span className="badge badge-black" style={{ marginLeft:8, fontSize:"9px" }}>{form.departure_date}</span>
            </div>
            <div className="results-count">
              {loading ? "Searching live fares…" : searched ? `${flights.length} flight${flights.length!==1?"s":""} found` : "Enter your route and search"}
              {dataSource && !loading && <span style={{ marginLeft:8 }}>· {dataSource === "AMADEUS" ? "Live Amadeus GDS" : "SkyMind Synthetic"}</span>}
            </div>
          </div>
          <div className="sort-strip">
            {["Price","Duration","Departure"].map(s => (
              <button key={s} className={`sort-btn${sort===s?" active":""}`} onClick={() => { setSort(s); setFlights(prev => sortFlights(prev,s)); }}>{s}</button>
            ))}
          </div>
        </div>

        {error && (
          <div className="error-state" style={{ marginBottom:16 }}>
            <div style={{ fontWeight:700, color:"var(--red)", marginBottom:6, fontFamily:"var(--fm)", fontSize:".8rem" }}>SEARCH FAILED</div>
            <div style={{ fontSize:".85rem", color:"var(--grey4)", marginBottom:10 }}>{error}</div>
            <button className="btn-primary" onClick={() => doSearch()} style={{ fontSize:".78rem", padding:"8px 16px" }}>Try again</button>
          </div>
        )}

        {/* Skeletons */}
        {loading && Array.from({length:4}).map((_,i) => (
          <div key={i} className="flight-card" style={{ marginBottom:12, padding:20 }}>
            <div style={{ display:"grid", gridTemplateColumns:"160px 1fr 140px", gap:20 }}>
              <div><div className="skel" style={{ height:40, width:40, marginBottom:10 }} /><div className="skel" style={{ height:12, width:"80%", marginBottom:6 }} /><div className="skel" style={{ height:10, width:"60%" }} /></div>
              <div style={{ display:"flex", alignItems:"center", gap:16 }}><div className="skel" style={{ height:28, width:70 }} /><div className="skel" style={{ height:1, flex:1 }} /><div className="skel" style={{ height:28, width:70 }} /></div>
              <div><div className="skel" style={{ height:28, marginBottom:8 }} /><div className="skel" style={{ height:32 }} /></div>
            </div>
          </div>
        ))}

        {!loading && searched && flights.length === 0 && !error && (
          <div className="empty-state">
            <div style={{ fontFamily:"var(--fd)", fontSize:"2rem", letterSpacing:".04em", color:"var(--black)", marginBottom:8 }}>NO FLIGHTS FOUND</div>
            <div style={{ fontSize:".85rem", color:"var(--grey4)", marginBottom:20 }}>Try: DEL→BOM, BOM→BLR, DEL→BLR</div>
            <button className="btn-primary" onClick={() => doSearch()}>Search again</button>
          </div>
        )}

        {flights.map((f, i) => {
          const itin = f.itineraries[0];
          const seg = itin?.segments[0];
          const lastSeg = itin?.segments[itin.segments.length-1];
          const stops = (itin?.segments.length||1)-1;
          const dep = seg?.departure_time ? new Date(seg.departure_time).toLocaleTimeString("en-IN",{hour:"2-digit",minute:"2-digit",hour12:false}) : "--:--";
          const arr = lastSeg?.arrival_time ? new Date(lastSeg.arrival_time).toLocaleTimeString("en-IN",{hour:"2-digit",minute:"2-digit",hour12:false}) : "--:--";
          const dur = formatDuration(itin?.duration || "");
          const airlineCode = f.primary_airline || seg?.airline_code || "AI";
          const airlineName = f.primary_airline_name || seg?.airline_name || airlineCode;
          const price = Math.round(f.price.total);
          const aiPrice = f.ai_price ? Math.round(f.ai_price) : null;
          const isFirst = i === 0;

          return (
            <div key={f.id} className={`flight-card${isFirst?" best-card":""}`}
              style={{ animation:`fadeUp 0.35s ${Math.min(i*.05,.3)}s ease both` }}
              onClick={() => { if (typeof window !== "undefined") { sessionStorage.setItem("selected_flight", JSON.stringify(f)); sessionStorage.setItem("search_params", JSON.stringify(form)); } router.push("/booking"); }}
            >
              {isFirst && <div className="best-tag">Best value</div>}
              <div className="flight-top" style={{ borderTop: isFirst ? "2px solid var(--red)" : undefined }}>

                {/* Airline */}
                <div className="flight-airline">
                  <div className="airline-logo-box">
                    <img src={`https://content.airhex.com/content/logos/airlines_${airlineCode}_200_200_s.png`} alt={airlineName} onError={e => { (e.target as HTMLImageElement).style.display="none"; }} />
                    {airlineCode}
                  </div>
                  <div>
                    <div className="airline-name-txt">{airlineName}</div>
                    <div className="airline-num-txt">{seg?.flight_number || "--"}</div>
                  </div>
                </div>

                {/* Timeline */}
                <div className="flight-timeline">
                  <div style={{ textAlign:"center", flexShrink:0 }}>
                    <div className="t-time">{dep}</div>
                    <div className="t-iata">{seg?.origin || form.origin}</div>
                  </div>
                  <div className="t-mid">
                    <div className="t-dur">{dur}</div>
                    <div className="fline" style={{ width:"100%" }}>
                      <div className="fline-dot" />
                      <div className="fline-track" style={{ flex:1 }}>
                        <div className="fline-plane">
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="var(--red)"><path d="M17.8 19.2L16 11l3.5-3.5C21 6 21 4 19.5 2.5S18 2 16.5 3.5L13 7 4.8 6.2c-.5-.1-.9.1-1.1.5L2 8.9c-.2.4-.1.9.2 1.2l4.6 4.1-1.5 6.4 2.8 2.8 5.3-3.2 4.1 4.6c.3.4.8.5 1.2.2l1.1-1.2c.4-.2.6-.6.5-1.1z"/></svg>
                        </div>
                      </div>
                      <div className="fline-dot" />
                    </div>
                    <div className={`t-stop${stops===0?" direct":" one-stop"}`}>{stops===0?"Non-stop":`${stops} stop${stops>1?"s":""}`}</div>
                  </div>
                  <div style={{ textAlign:"center", flexShrink:0 }}>
                    <div className="t-time">{arr}</div>
                    <div className="t-iata">{lastSeg?.destination || form.destination}</div>
                  </div>
                </div>

                {/* Price */}
                <div className="flight-price-col">
                  <div style={{ textAlign:"right" }}>
                    <div className="f-price">₹{price.toLocaleString("en-IN")}</div>
                    <div className="f-price-per">per person</div>
                    {f.seats_available && f.seats_available <= 5 && <div className="f-seats">{f.seats_available} left</div>}
                    {aiPrice && (
                      <div className="f-ai-badge" style={{ marginTop:4 }}>
                        AI: ₹{aiPrice.toLocaleString("en-IN")}
                      </div>
                    )}
                  </div>
                  <button className="btn-primary" style={{ fontSize:".78rem", padding:"8px 16px" }}
                    onClick={e => { e.stopPropagation(); if (typeof window !== "undefined") { sessionStorage.setItem("selected_flight", JSON.stringify(f)); sessionStorage.setItem("search_params", JSON.stringify(form)); } router.push("/booking"); }}>
                    Select →
                  </button>
                </div>
              </div>

              {/* Footer row */}
              <div className="flight-bottom">
                <div style={{ display:"flex", alignItems:"center", gap:10, flexWrap:"wrap" }}>
                  <RecommendationBadge rec={f.recommendation} />
                  {f.advice && <span style={{ fontSize:".78rem", color:"var(--grey3)", maxWidth:320, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{f.advice}</span>}
                  <Link href={`/predict?origin=${form.origin}&destination=${form.destination}`}
                    onClick={e => e.stopPropagation()}
                    style={{ fontSize:".75rem", color:"var(--red)", textDecoration:"underline", textUnderlineOffset:2, whiteSpace:"nowrap", fontFamily:"var(--fm)" }}>
                    30-day forecast
                  </Link>
                </div>
                <span style={{ fontSize:".72rem", color:"var(--grey3)", fontFamily:"var(--fm)" }}>{form.cabin_class === "ECONOMY" ? "Economy" : form.cabin_class}</span>
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
      <Suspense fallback={<div style={{ paddingTop:120, textAlign:"center", color:"var(--grey3)", fontFamily:"var(--fm)", fontSize:".8rem" }}>Loading…</div>}>
        <FlightsContent />
      </Suspense>
    </>
  );
}
