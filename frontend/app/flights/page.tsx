"use client";

import { useState, useEffect, Suspense, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import NavBar from "@/components/layout/NavBar";
import FlightSearchForm from "@/components/flights/FlightSearchForm";
import { searchFlights, formatDuration, resolveCityToIATA } from "@/lib/api";
import AirlineLogo from "@/components/flights/AirlineLogo";
import type { FlightOffer, CabinClass } from "@/types";
import { format, addDays } from "date-fns";

function RecommendationBadge({ rec }: { rec?: string }) {
  if (!rec) return null;
  const r = rec.toUpperCase();
  if (r.includes("BOOK NOW") || r.includes("BOOK_NOW")) return <span className="badge badge-red">Book Now</span>;
  if (r.includes("WAIT")) return <span className="badge badge-amber">Wait</span>;
  if (r.includes("FAIR") || r.includes("STABLE")) return <span className="badge badge-off">Fair Price</span>;
  return <span className="badge badge-off">Monitor</span>;
}

function FlightsContent() {
  const router = useRouter();
  const params = useSearchParams();
  const defaultDate = format(addDays(new Date(), 7), "yyyy-MM-dd");

  const [searchParams, setSearchParams] = useState({
    origin:         params.get("origin") || "DEL",
    destination:    params.get("destination") || "BOM",
    departure_date: params.get("departure_date") || defaultDate,
    return_date:    params.get("return_date") || "",
    adults:         Number(params.get("adults") || 1),
    children:       Number(params.get("children") || 0),
    cabin_class:    (params.get("cabin_class") as CabinClass) || "ECONOMY",
  });

  const [flights, setFlights] = useState<FlightOffer[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sort, setSort] = useState("Price");
  const [searched, setSearched] = useState(false);
  const [dataSource, setDataSource] = useState("");
  const [timeFilter, setTimeFilter] = useState<string>("ALL");

  const sortFlights = (list: FlightOffer[], s: string) => {
    const arr = [...list];
    if (s === "Price") arr.sort((a,b) => (a.price?.total || 0) - (b.price?.total || 0));
    if (s === "Duration") arr.sort((a,b) => (a.itineraries?.[0]?.duration || "").localeCompare(b.itineraries?.[0]?.duration || ""));
    if (s === "Departure") arr.sort((a,b) => (a.itineraries?.[0]?.segments?.[0]?.departure_time || "").localeCompare(b.itineraries?.[0]?.segments?.[0]?.departure_time || ""));
    return arr;
  };

  const doSearch = async (f: any) => {
    setSearchParams(f);
    const org = resolveCityToIATA(f.origin);
    const dst = resolveCityToIATA(f.destination);
    
    if (org === dst) { setError("Origin and destination cannot be the same."); return; }
    
    setLoading(true); setError(""); setSearched(true);
    try {
      const res = await searchFlights({ 
        origin: org, 
        destination: dst, 
        departure_date: f.departure_date, 
        return_date: f.return_date || undefined,
        adults: f.adults, 
        children: f.children,
        cabin_class: f.cabin_class as any, 
        max_results: 30 
      });
      setFlights(sortFlights(res.flights || [], sort));
      setDataSource((res as any).data_source || "");
    } catch (e: any) {
      setError(e.message || "Search failed.");
      setFlights([]);
    }
    setLoading(false);
  };

  useEffect(() => { if (params.get("origin")) doSearch(searchParams); }, []);

  const filteredFlights = useMemo(() => {
    if (timeFilter === "ALL") return flights;
    return flights.filter(f => {
      const depTime = f.itineraries?.[0]?.segments?.[0]?.departure_time;
      if (!depTime) return false;
      const hour = new Date(depTime).getHours();
      if (timeFilter === "MORNING") return hour >= 6 && hour < 12;
      if (timeFilter === "AFTERNOON") return hour >= 12 && hour < 18;
      if (timeFilter === "EVENING") return hour >= 18 && hour < 24;
      if (timeFilter === "NIGHT") return hour >= 0 && hour < 6;
      return true;
    });
  }, [flights, timeFilter]);

  return (
    <div className="ui-page">
      {/* Search Header V2 */}
      <div className="ui-results-header" style={{ background: "var(--white)", borderBottom: "1px solid var(--grey1)", paddingTop: "100px", paddingBottom: "40px" }}>
        <div className="ui-wrap">
          <div className="ui-card" style={{ padding: "var(--ui-space-lg)", border: "1px solid var(--grey1)", borderRadius: "var(--ui-radius-xl)", boxShadow: "0 4px 20px rgba(0,0,0,0.03)" }}>
            <FlightSearchForm 
              initialData={searchParams} 
              onSearch={(p) => {
                const url = new URLSearchParams();
                Object.entries(p).forEach(([k,v]) => url.set(k, String(v)));
                router.replace(`/flights?${url.toString()}`, { scroll: false });
                doSearch(p);
              }} 
            />
          </div>
        </div>
      </div>

      <div className="ui-wrap" style={{ paddingBottom: "100px" }}>
        
        {/* Results Toolbar */}
        <div className="results-toolbar">
          <div>
            <h1 className="ui-title-lg" style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", fontSize: "clamp(1.4rem, 5vw, 3rem)" }}>
              {searchParams.origin} <span style={{ color: "var(--red)" }}>→</span> {searchParams.destination}
            </h1>
            <div className="ui-label" style={{ color: "var(--grey3)", marginTop: "4px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {loading ? "SCANNING AIRWAVES..." : `${filteredFlights.length} OPTIONS DISCOVERED`}
              {dataSource && ` • ${dataSource.replace(/_/g, " ")} ENGINE`}
            </div>
          </div>
          
          <div className="sort-row">
            <span className="ui-label" style={{ color: "var(--grey3)", whiteSpace: "nowrap" }}>SORT BY</span>
            <div style={{ display: "flex", background: "var(--off)", padding: "4px", borderRadius: "8px", border: "1px solid var(--grey1)", flexShrink: 0 }}>
              {["Price","Duration","Departure"].map(s => (
                <button key={s} 
                  className="ui-btn"
                  style={{ 
                    padding: "6px 10px", fontSize: "11px", height: "auto",
                    background: sort === s ? "var(--white)" : "transparent",
                    color: sort === s ? "var(--black)" : "var(--grey3)",
                    boxShadow: sort === s ? "var(--shadow-sm)" : "none",
                    border: "none"
                  }}
                  onClick={() => { setSort(s); setFlights(prev => sortFlights(prev,s)); }}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Time Filters */}
        <div className="ui-flex" style={{ gap: "12px", overflowX: "auto", paddingBottom: "24px" }}>
          {[
            { id: "ALL", label: "All Flights" },
            { id: "MORNING", label: "Morning", sub: "06:00 - 12:00" },
            { id: "AFTERNOON", label: "Afternoon", sub: "12:00 - 18:00" },
            { id: "EVENING", label: "Evening", sub: "18:00 - 00:00" },
            { id: "NIGHT", label: "Night", sub: "00:00 - 06:00" },
          ].map(f => (
            <button
              key={f.id}
              onClick={() => setTimeFilter(f.id)}
              className="ui-card"
              style={{
                flex: "0 0 160px", padding: "16px", cursor: "pointer", textAlign: "left",
                borderColor: timeFilter === f.id ? "var(--red)" : "var(--grey1)",
                background: timeFilter === f.id ? "var(--red-mist)" : "var(--white)",
                transition: "all 0.2s"
              }}
            >
              <div className="ui-label" style={{ color: timeFilter === f.id ? "var(--red)" : "var(--black)" }}>{f.label}</div>
              <div style={{ fontSize: "10px", color: "var(--grey3)", marginTop: "4px" }}>{f.sub || "Anytime"}</div>
            </button>
          ))}
        </div>

        {error && (
          <div className="ui-card" style={{ padding: "40px", textAlign: "center", borderColor: "var(--red)" }}>
            <div className="ui-label" style={{ color: "var(--red)", marginBottom: "12px" }}>SEARCH_ERROR</div>
            <div className="ui-text-main" style={{ marginBottom: "24px" }}>{error}</div>
            <button className="ui-btn ui-btn-red" onClick={() => doSearch(searchParams)}>RETRY SEARCH</button>
          </div>
        )}

        {/* Cinematic Skeletons */}
        {loading && (
          <div className="ui-results-grid">
            {Array.from({length:3}).map((_,i) => (
              <div key={i} className="ui-flight-card" style={{ height: "180px", padding: "24px" }}>
                <div className="skel" style={{ height: "100%", width: "100%", borderRadius: "12px" }} />
              </div>
            ))}
          </div>
        )}

        {!loading && searched && filteredFlights.length === 0 && !error && (
          <div className="ui-card" style={{ padding: "80px", textAlign: "center", background: "var(--off)", borderStyle: "dashed" }}>
            <div className="ui-title-lg" style={{ marginBottom: "12px" }}>NO FLIGHTS FOUND</div>
            <p className="ui-text-main" style={{ marginBottom: "32px" }}>Try adjusting your filters or search for a different time window.</p>
            <button className="ui-btn ui-btn-black" onClick={() => setTimeFilter("ALL")}>SHOW ALL OPTIONS</button>
          </div>
        )}

        <div className="ui-results-grid">
          {filteredFlights.map((f, i) => {
            const itin = f.itineraries?.[0];
            const segments = itin?.segments ?? [];
            const seg = segments[0];
            const lastSeg = segments[segments.length - 1];
            const stops = Math.max(0, segments.length - 1);
            const dep = seg?.departure_time ? new Date(seg.departure_time).toLocaleTimeString("en-IN",{hour:"2-digit",minute:"2-digit",hour12:false}) : "--:--";
            const arr = lastSeg?.arrival_time ? new Date(lastSeg.arrival_time).toLocaleTimeString("en-IN",{hour:"2-digit",minute:"2-digit",hour12:false}) : "--:--";
            const dur = formatDuration(itin?.duration || "");
            const airlineCode = f.primary_airline || seg?.airline_code || "AI";
            const airlineName = f.primary_airline_name || seg?.airline_name || airlineCode;
            const price = Math.round(f.price.total);
            const isBest = i === 0 && timeFilter === "ALL";

            return (
              <div key={f.id} className={`ui-flight-card ${isBest ? "best" : ""}`}
                onClick={() => { 
                  if (typeof window !== "undefined") { 
                    sessionStorage.setItem("selected_flight", JSON.stringify(f)); 
                    sessionStorage.setItem("search_params", JSON.stringify(searchParams)); 
                  } 
                  router.push("/booking"); 
                }}
              >
                <div className="fc-main">
                  <div className="fc-airline">
                    <div className="fc-logo-box"><AirlineLogo code={airlineCode} name={airlineName} /></div>
                    <div>
                      <div className="ui-text-main" style={{ fontWeight: 700 }}>{airlineName}</div>
                      <div className="ui-label" style={{ color: "var(--grey3)" }}>{seg?.flight_number}</div>
                    </div>
                  </div>

                  <div className="fc-timeline">
                    <div style={{ textAlign: "left" }}>
                      <div className="ui-title-lg" style={{ fontSize: "1.8rem" }}>{dep}</div>
                      <div className="ui-label">{seg?.origin}</div>
                    </div>
                    <div className="fc-mid">
                      <div className="ui-label" style={{ fontSize: "10px" }}>{dur}</div>
                      <div className="fc-line">
                        <div className="fc-plane">
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M21,16V14L13,9V3.5A1.5,1.5 0 0,0 11.5,2A1.5,1.5 0 0,0 10,3.5V9L2,14V16L10,13.5V19L8,20.5V22L11.5,21L15,22V20.5L13,19V13.5L21,16Z" /></svg>
                        </div>
                      </div>
                      <div className="ui-label" style={{ color: stops === 0 ? "var(--green)" : "var(--grey3)" }}>{stops === 0 ? "DIRECT" : `${stops} STOP${stops>1?"S":""}`}</div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div className="ui-title-lg" style={{ fontSize: "1.8rem" }}>{arr}</div>
                      <div className="ui-label">{lastSeg?.destination}</div>
                    </div>
                  </div>

                  <div className="fc-price-col">
                    <div className="fc-price-val">₹{price.toLocaleString("en-IN")}</div>
                    <div className="ui-label" style={{ color: "var(--grey3)", marginBottom: "12px" }}>TOTAL FARE</div>
                    <button className="ui-btn ui-btn-red" style={{ width: "100%", height: "40px" }}>SELECT</button>
                  </div>
                </div>

                <div className="fc-footer">
                  <div className="ui-flex" style={{ gap: "16px" }}>
                    <div className="ui-flex" style={{ gap: "6px", alignItems: "center" }}>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                      <span className="ui-label" style={{ color: "var(--grey4)" }}>XGBOOST VERIFIED</span>
                    </div>
                  </div>
                  <RecommendationBadge rec={f.recommendation} />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default function FlightsPage() {
  return (
    <>
      <NavBar />
      <Suspense fallback={<div style={{ paddingTop:120, textAlign:"center", color:"var(--grey3)", fontFamily:"var(--fm)", fontSize:".8rem" }}>ENGINE_INIT...</div>}>
        <FlightsContent />
      </Suspense>
    </>
  );
}
