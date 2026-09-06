"use client";

import { useState, useEffect, Suspense, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import NavBar from "@/components/layout/NavBar";
import FlightSearchForm from "@/components/flights/FlightSearchForm";
import { searchFlights, predictPrice, formatDuration, resolveCityToIATA } from "@/lib/api";
import AirlineLogo from "@/components/flights/AirlineLogo";
import type { FlightOffer, CabinClass, PredictionResult } from "@/types";
import { formatCurrency, formatFare, formatConfidence, formatDate } from "@/lib/formatters";
import { format, addDays } from "date-fns";

const REC_LABEL: Record<string, string> = {
  BOOK_NOW: "BUY NOW",
  WAIT: "WAIT",
  MONITOR: "MONITOR"
};

const REC_COLOR: Record<string, string> = {
  BOOK_NOW: "#16a34a",
  WAIT: "#d97706",
  MONITOR: "#666666"
};

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

  // Route prediction state
  const [routePrediction, setRoutePrediction] = useState<PredictionResult | null>(null);
  const [predLoading, setPredLoading] = useState(false);
  const [predError, setPredError] = useState(false);

  // Expanded card state
  const [expandedCardId, setExpandedCardId] = useState<string | null>(null);

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
    
    if (org === dst) { 
      setError("Origin and destination cannot be the same."); 
      return; 
    }
    
    setLoading(true); 
    setError(""); 
    setSearched(true);
    setRoutePrediction(null);
    setPredError(false);
    setPredLoading(true);

    // Run route prediction in parallel
    predictPrice({ origin: org, destination: dst, departure_date: f.departure_date })
      .then(res => {
        setRoutePrediction(res);
        setPredLoading(false);
      })
      .catch(err => {
        console.error("Prediction load failed:", err);
        setPredError(true);
        setPredLoading(false);
      });

    try {
      const res = await searchFlights({
        origin: org,
        destination: dst,
        departure_date: f.departure_date,
        return_date: f.return_date || undefined,
        adults: f.adults,
        children: f.children,
        // The form collects infants but this call used to drop them, so an
        // infant in the party never reached /live-search.
        infants: f.infants ?? 0,
        cabin_class: f.cabin_class as CabinClass,
      });
      setFlights(sortFlights(res.flights || [], sort));
      setDataSource((res as any).data_source || "");
    } catch (e: any) {
      setError(e.message || "Search failed.");
      setFlights([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { 
    if (params.get("origin")) {
      doSearch(searchParams); 
    }
  }, [params]);

  const filteredFlights = useMemo(() => {
    if (timeFilter === "ALL") return flights;
    return flights.filter(f => {
      const depTime = f.itineraries?.[0]?.segments?.[0]?.departure_time;
      if (!depTime) return true; // Do not discard itineraries without explicit schedule times
      const hour = new Date(depTime).getHours();
      if (timeFilter === "MORNING") return hour >= 6 && hour < 12;
      if (timeFilter === "AFTERNOON") return hour >= 12 && hour < 18;
      if (timeFilter === "EVENING") return hour >= 18 && hour < 24;
      if (timeFilter === "NIGHT") return hour >= 0 && hour < 6;
      return true;
    });
  }, [flights, timeFilter]);

  // Derived prediction values.
  // With no routePrediction there is nothing to recommend and no confidence to
  // report, so both fall back to a neutral/absent state rather than to
  // "BOOK_NOW" at 95% — a default that told every visitor to buy immediately
  // on the strength of a number no model produced.
  const corpusLowestFare = routePrediction?.current_market?.lowest_fare ?? null;
  const lowestFare = corpusLowestFare ?? (flights[0]?.price?.total || null);
  // Rupees when the figure came from the stored corpus, which admits no other
  // currency; otherwise the live card's own unit, which may be absent (§48).
  const lowestFareCurrency = corpusLowestFare != null
    ? "INR"
    : (flights[0]?.price?.currency ?? null);
  const predictedPrice = routePrediction?.predicted_price ?? null;
  const optBooking = routePrediction?.optimal_booking;
  const confPct = routePrediction ? formatConfidence(routePrediction.confidence) : null;
  const recDecision = routePrediction?.recommendation?.decision ?? "MONITOR";
  const recLabel = REC_LABEL[recDecision] ?? "MONITOR";
  // Both sides must be in the same unit for the difference to mean anything, and
  // the prediction is always in rupees. Subtracting a dollar fare from it would
  // produce a savings figure ~83x too large, presented in rupees.
  const priceChange = (lowestFare != null && predictedPrice != null
                       && lowestFareCurrency === "INR")
    ? predictedPrice - lowestFare
    : null;

  return (
    <div style={{ background: "#fff", minHeight: "100vh", paddingTop: 80 }}>
      
      {/* Search Header */}
      <div style={{ background: "#fff", borderBottom: "1px solid #EAEAEA", padding: "24px 0" }}>
        <div className="page-wrap">
          <div className="card" style={{ padding: "20px" }}>
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

      <div className="page-wrap" style={{ paddingTop: 24, paddingBottom: 64 }}>
        
        {/* 4-Column Route Prediction Summary Banner (Requirement #1, #3, #7, #8, #10) */}
        {routePrediction && (
          <div className="card summary-banner" style={{ marginBottom: 24, padding: "20px" }}>
            <div className="banner-grid">
              
              <div className="banner-col">
                <div className="card-label">Current Live Fare</div>
                <div className="banner-value">{formatFare(lowestFare, lowestFareCurrency)}</div>
                <div className="metadata">Lowest observed market fare</div>
              </div>

              <div className="banner-col">
                <div className="card-label">Predicted Fare</div>
                <div className="banner-value">{formatCurrency(predictedPrice)}</div>
                <div className="metadata">Target model forecast</div>
              </div>

              <div className="banner-col">
                <div className="card-label">Recommendation</div>
                <div className="banner-value" style={{ color: REC_COLOR[recDecision] }}>{recLabel}</div>
                <div className="metadata">
                  {priceChange != null && priceChange < 0
                    ? `Potential savings: ${formatCurrency(Math.abs(priceChange))}`
                    : "Optimal booking window"}
                </div>
              </div>

              <div className="banner-col">
                <div className="card-label">Forecast Confidence</div>
                <div className="banner-value">{confPct != null ? `${confPct}%` : "—"}</div>
                <div className="metadata">
                  {confPct != null ? "Model-reported confidence" : "No forecast for this route yet"}
                </div>
              </div>

            </div>
          </div>
        )}

        {predLoading && (
          <div className="card" style={{ padding: 16, marginBottom: 24, textAlign: "center" }}>
            <span className="metadata">Loading route forecast signals...</span>
          </div>
        )}

        {/* Results Toolbar */}
        <div className="toolbar" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <div>
            <h1 className="route-title" style={{ fontSize: "24px", fontWeight: 600, color: "#111", margin: 0 }}>
              {searchParams.origin} → {searchParams.destination}
            </h1>
            <div className="metadata" style={{ marginTop: 4 }}>
              {loading
                ? "Searching flights..."
                : `${filteredFlights.length} flight options found`}
            </div>
          </div>
          
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span className="card-label" style={{ marginBottom: 0 }}>SORT BY</span>
            <div style={{ display: "flex", background: "#F5F5F5", padding: "3px", borderRadius: "8px" }}>
              {["Price", "Duration", "Departure"].map(s => (
                <button 
                  key={s} 
                  onClick={() => { setSort(s); setFlights(prev => sortFlights(prev, s)); }}
                  style={{
                    padding: "6px 14px",
                    fontSize: "12px",
                    fontWeight: 500,
                    borderRadius: "6px",
                    border: "none",
                    background: sort === s ? "#fff" : "transparent",
                    color: sort === s ? "#111" : "#666",
                    cursor: "pointer",
                    boxShadow: sort === s ? "0 1px 3px rgba(0,0,0,0.08)" : "none"
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Time Filters */}
        <div className="filter-row" style={{ display: "flex", gap: 12, overflowX: "auto", marginBottom: 24 }}>
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
              className="card"
              style={{
                flex: "0 0 140px",
                padding: "12px 14px",
                cursor: "pointer",
                textAlign: "left",
                borderColor: timeFilter === f.id ? "#16a34a" : "#EAEAEA",
                background: timeFilter === f.id ? "rgba(22,163,74,0.03)" : "#fff"
              }}
            >
              <div style={{ fontSize: "13px", fontWeight: 500, color: timeFilter === f.id ? "#16a34a" : "#111" }}>{f.label}</div>
              <div className="metadata" style={{ marginTop: 2 }}>{f.sub || "Anytime"}</div>
            </button>
          ))}
        </div>

        {/* Error State */}
        {error && (
          <div className="card" style={{ padding: 32, textAlign: "center", borderColor: "#FCA5A5", background: "#FFF8F8" }}>
            <div style={{ fontSize: "13px", fontWeight: 600, color: "#DC2626", marginBottom: 8 }}>SEARCH ERROR</div>
            <div style={{ fontSize: "14px", color: "#444", marginBottom: 16 }}>{error}</div>
            <button className="btn-secondary" onClick={() => doSearch(searchParams)}>Retry Search</button>
          </div>
        )}

        {/* Loading State */}
        {loading && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="card" style={{ height: "120px", padding: "20px", display: "flex", alignItems: "center" }}>
                <div style={{ width: "100%", height: "32px", background: "#F5F5F5", borderRadius: 6 }} />
              </div>
            ))}
          </div>
        )}

        {/* Empty State */}
        {!loading && searched && filteredFlights.length === 0 && !error && (
          <div className="card" style={{ padding: 48, textAlign: "center" }}>
            <h3 style={{ fontSize: "16px", fontWeight: 600, marginBottom: 8 }}>No flights found</h3>
            <p className="metadata" style={{ marginBottom: 20 }}>No available flights match your selected search criteria for this route.</p>
            <button className="btn-secondary" onClick={() => doSearch(searchParams)}>Refresh Search</button>
          </div>
        )}

        {/* Flight Cards Grid */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {filteredFlights.map((f, i) => {
            const itin = f.itineraries?.[0];
            const segments = itin?.segments ?? [];
            const seg = segments[0];
            const lastSeg = segments[segments.length - 1];
            const stops = seg?.stops != null ? seg.stops : Math.max(0, segments.length - 1);
            
            const dep = seg?.departure_time ? new Date(seg.departure_time).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false }) : "Schedule Unavailable";
            const arr = lastSeg?.arrival_time ? new Date(lastSeg.arrival_time).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false }) : "Schedule Unavailable";
            const dur = itin?.duration ? formatDuration(itin.duration) : "Duration Unavailable";
            
            const airlineCode = f.primary_airline || seg?.airline_code || "UNKNOWN";
            const airlineName = f.primary_airline_name || seg?.airline_name || (airlineCode !== "UNKNOWN" ? airlineCode : "Unknown Airline");
            
            // Flight number: use real value from provider, or a neutral label if unavailable
            const rawFlNum = f.flight_number || seg?.flight_number || null;
            const flNumStr = rawFlNum || null;
            
            const price = f.price.total;
            const isBest = i === 0 && timeFilter === "ALL";
            const isExpanded = expandedCardId === f.id;
            
            // Value badges logic
            //
            // "Cheapest" is a comparison, and a comparison needs one unit. FX
            // conversion in flight_data_service runs only when a rate is
            // configured, so a list can genuinely mix currencies — and 58 dollars
            // would take the badge from a 5,000-rupee fare. With more than one
            // unit present, no fare is claimed to be cheapest (§48).
            const fareUnits = new Set(filteredFlights.map(x => x.price.currency ?? "UNSTATED"));
            const minPriceInList = Math.min(...filteredFlights.map(x => x.price.total));
            const isCheapest = fareUnits.size === 1 && price === minPriceInList;

            return (
              <div 
                key={f.id} 
                className="card flight-card" 
                style={{ 
                  padding: 20, 
                  borderColor: isCheapest ? "#16a34a" : "#EAEAEA",
                  background: "#fff",
                  position: "relative"
                }}
              >
                {/* Visual Top Badges Row */}
                <div style={{ display: "flex", gap: 8, marginBottom: 12, alignItems: "center" }}>
                  {isCheapest && (
                    <span style={{ fontSize: "11px", fontWeight: 700, background: "#DCFCE7", color: "#15803D", padding: "2px 8px", borderRadius: 4, letterSpacing: "0.5px" }}>
                      CHEAPEST FARE
                    </span>
                  )}
                  <span style={{
                    fontSize: "11px",
                    fontWeight: 600,
                    background: f.provenance === "REAL_PROVIDER" ? "#EFF6FF" : "#F3F4F6",
                    color: f.provenance === "REAL_PROVIDER" ? "#1D4ED8" : "#4B5563",
                    padding: "2px 8px",
                    borderRadius: 4
                  }}>
                    {/* This badge used to read "LIVE · GOOGLE FLIGHTS" or, for
                        everything else, "VERIFIED MARKET DATA" — a verification
                        claim for a row that is simply a cached price_history
                        observation, and a provider name this page never receives.
                        Say which of the three the row actually is. */}
                    {f.provenance === "REAL_PROVIDER"
                      ? "LIVE PROVIDER"
                      : f.provenance === "VERIFIED_MARKET_SNAPSHOT"
                        ? "CACHED SNAPSHOT"
                        : "SOURCE UNKNOWN"}
                  </span>
                </div>

                <div className="flight-row">
                  
                  {/* Airline Info */}
                  <div className="col-airline">
                    <div style={{ width: 42, height: 42, borderRadius: 8, background: "#F8FAFC", border: "1px solid #E2E8F0", display: "flex", alignItems: "center", justifyContent: "center" }}>
                      <AirlineLogo code={airlineCode} name={airlineName} />
                    </div>
                    <div>
                      <div style={{ fontSize: "15px", fontWeight: 600, color: "#0F172A" }}>{airlineName}</div>
                      {flNumStr && (
                        <div className="metadata" style={{ fontSize: "12px", color: "#64748B" }}>{flNumStr}</div>
                      )}
                    </div>
                  </div>

                  {/* Flight Times & Duration */}
                  <div className="col-timeline">
                    <div style={{ textAlign: "left" }}>
                      <div style={{ fontSize: dep === "Schedule Unavailable" ? "13px" : "20px", fontWeight: 700, color: dep === "Schedule Unavailable" ? "#64748B" : "#0F172A" }}>{dep}</div>
                      <div className="metadata" style={{ fontSize: "12px", fontWeight: 600, color: "#475569" }}>{seg?.origin}</div>
                    </div>
                    
                    <div style={{ flex: 1, textAlign: "center", padding: "0 16px" }}>
                      <div className="metadata" style={{ marginBottom: 4, fontSize: "12px", fontWeight: 500, color: "#64748B" }}>{dur}</div>
                      <div style={{ height: 2, background: "#CBD5E1", position: "relative" }}>
                        <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#16a34a", position: "absolute", top: "50%", left: "50%", transform: "translate(-50%, -50%)" }} />
                      </div>
                      <div className="metadata" style={{ marginTop: 4, fontSize: "12px", fontWeight: 600, color: stops === 0 ? "#16a34a" : "#475569" }}>
                        {stops == null ? "Stops Unavailable" : stops === 0 ? "Direct Flight" : `${stops} Stop`}
                      </div>
                    </div>

                    <div style={{ textAlign: "right" }}>
                      <div style={{ fontSize: arr === "Schedule Unavailable" ? "13px" : "20px", fontWeight: 700, color: arr === "Schedule Unavailable" ? "#64748B" : "#0F172A" }}>{arr}</div>
                      <div className="metadata" style={{ fontSize: "12px", fontWeight: 600, color: "#475569" }}>{lastSeg?.destination}</div>
                    </div>
                  </div>

                  {/* Price & Action Buttons */}
                  <div className="col-action">
                    <div style={{ fontSize: "26px", fontWeight: 800, color: "#0F172A", marginBottom: 12, letterSpacing: "-0.5px" }}>
                      {formatFare(price, f.price.currency)}
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      <button 
                        onClick={(e) => {
                          e.stopPropagation();
                          setExpandedCardId(isExpanded ? null : f.id);
                        }}
                        style={{
                          width: "100%",
                          height: 36,
                          borderRadius: 8,
                          background: isExpanded ? "#F1F5F9" : "#fff",
                          border: `1px solid ${isExpanded ? "#94A3B8" : "#CBD5E1"}`,
                          color: isExpanded ? "#334155" : "#475569",
                          fontSize: "12px",
                          fontWeight: 600,
                          cursor: "pointer",
                          transition: "all 0.15s",
                          letterSpacing: "0.02em",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          gap: 6,
                        }}
                      >
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                          {isExpanded
                            ? <path d="M18 15l-6-6-6 6"/>
                            : <path d="M6 9l6 6 6-6"/>}
                        </svg>
                        {isExpanded ? "Hide Details" : "Flight Details"}
                      </button>
                      <button 
                        onClick={() => {
                          if (typeof window !== "undefined") { 
                            sessionStorage.setItem("selected_flight", JSON.stringify(f)); 
                            sessionStorage.setItem("search_params", JSON.stringify(searchParams)); 
                          } 
                          router.push("/booking"); 
                        }}
                        style={{
                          width: "100%",
                          height: 36,
                          borderRadius: 8,
                          background: "#E11D48",
                          border: "none",
                          color: "#fff",
                          fontSize: "12px",
                          fontWeight: 700,
                          cursor: "pointer",
                          transition: "background 0.15s",
                          letterSpacing: "0.06em",
                          textTransform: "uppercase",
                        }}
                        onMouseEnter={e => (e.currentTarget.style.background = "#BE123C")}
                        onMouseLeave={e => (e.currentTarget.style.background = "#E11D48")}
                      >
                        Book Now
                      </button>
                    </div>
                  </div>

                </div>

                {/* Expandable Flight Details Panel */}
                {isExpanded && (
                  <div style={{
                    marginTop: 16,
                    paddingTop: 16,
                    borderTop: "1px solid #E2E8F0",
                    background: "#F8FAFC",
                    borderRadius: 8,
                    padding: 16,
                  }}>
                    {/* Segments breakdown */}
                    {segments.length > 0 && (
                      <div style={{ marginBottom: segments.length > 1 ? 16 : 0 }}>
                        <div style={{ fontSize: "11px", fontWeight: 700, color: "#64748B", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 10 }}>FLIGHT SEGMENTS</div>
                        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                          {segments.map((s: any, idx: number) => (
                            <div key={idx} style={{ display: "flex", alignItems: "center", gap: 12, fontSize: "13px", background: "#fff", border: "1px solid #E2E8F0", borderRadius: 6, padding: "10px 14px" }}>
                              <span style={{ fontWeight: 700, color: "#0F172A", minWidth: 60 }}>{s.airline_code || airlineCode} {s.flight_number || ""}</span>
                              <span style={{ color: "#475569" }}>{s.origin} → {s.destination}</span>
                              <span style={{ color: "#64748B", marginLeft: "auto" }}>
                                {s.departure_time ? new Date(s.departure_time).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false }) : "--:--"}
                                {" → "}
                                {s.arrival_time ? new Date(s.arrival_time).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false }) : "--:--"}
                              </span>
                              {s.duration && (
                                <span style={{ color: "#94A3B8", fontSize: "11px" }}>{formatDuration(s.duration)}</span>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Metadata row */}
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 16, marginTop: segments.length > 0 ? 12 : 0 }}>
                      <div>
                        <div style={{ fontSize: "11px", fontWeight: 700, color: "#64748B", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>ROUTE & STOPS</div>
                        <div style={{ fontSize: "13px", fontWeight: 600, color: "#0F172A" }}>{seg?.origin} → {lastSeg?.destination}</div>
                        <div style={{ fontSize: "12px", color: "#64748B" }}>
                          {stops === 0 ? "Non-stop direct flight" : `${stops} stop${stops > 1 ? "s" : ""}`}
                        </div>
                      </div>
                      <div>
                        <div style={{ fontSize: "11px", fontWeight: 700, color: "#64748B", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>DATA SOURCE & PROVENANCE</div>
                        <div style={{ fontSize: "13px", fontWeight: 600, color: f.provenance === "REAL_PROVIDER" ? "#16a34a" : "#2563EB" }}>
                          {f.provenance === "REAL_PROVIDER"
                            ? "Live provider fetch"
                            : f.provenance === "VERIFIED_MARKET_SNAPSHOT"
                              ? "Cached market snapshot"
                              : "Source not stated"}
                        </div>
                        <div style={{ fontSize: "12px", color: "#64748B" }}>
                          {f.provenance === "REAL_PROVIDER"
                            ? "Fetched for this search via the MCP scraper"
                            : f.provenance === "VERIFIED_MARKET_SNAPSHOT"
                              ? "Recorded by an earlier scrape, not re-checked just now"
                              : "The backend did not report where this fare came from"}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

              </div>
            );
          })}
        </div>

      </div>

      <style jsx>{`
        /* ── Standard Design System ──────────────────────────── */
        .page-wrap {
          max-width: 1280px;
          margin: 0 auto;
          padding: 0 24px;
        }

        .card {
          background: #fff;
          border: 1px solid #EAEAEA;
          border-radius: 12px;
          box-shadow: none;
        }

        .card-label {
          font-size: 11px;
          font-weight: 500;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          color: #666;
          margin-bottom: 4px;
        }

        .metadata {
          font-size: 11px;
          font-weight: 400;
          color: #888;
        }

        /* 4-Column Banner */
        .banner-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 20px;
        }

        .banner-col {
          display: flex;
          flex-direction: column;
        }

        .banner-value {
          font-size: 24px;
          font-weight: 600;
          color: #111;
          margin-bottom: 2px;
        }

        /* Flight Row Layout */
        .flight-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 24px;
        }

        .col-airline {
          display: flex;
          align-items: center;
          gap: 12px;
          flex: 0 0 200px;
        }

        .col-timeline {
          display: flex;
          align-items: center;
          gap: 16px;
          flex: 1;
          justify-content: center;
          max-width: 400px;
        }

        .col-action {
          text-align: right;
          flex: 0 0 180px;
          min-width: 160px;
        }

        /* Responsive Breakpoints (Requirement #13) */
        @media (max-width: 1024px) {
          .banner-grid { grid-template-columns: repeat(2, 1fr); }
          .details-grid { grid-template-columns: repeat(2, 1fr); }
        }

        @media (max-width: 768px) {
          .flight-row { flex-direction: column; align-items: stretch; gap: 16px; }
          .col-airline, .col-timeline, .col-action { flex: auto; max-width: none; text-align: left; }
          .col-action { text-align: left; }
        }
      `}</style>
    </div>
  );
}

export default function FlightsPage() {
  return (
    <>
      <NavBar />
      <Suspense fallback={<div style={{ paddingTop: 120, textAlign: "center", color: "#666", fontSize: "13px" }}>Loading search results...</div>}>
        <FlightsContent />
      </Suspense>
    </>
  );
}
