"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import NavBar from "@/components/layout/NavBar";
import AirlineLogo from "@/components/flights/AirlineLogo";
import { searchFlights, formatDuration, resolveCityToIATA } from "@/lib/api";
import type { FlightOffer } from "@/types";
import { format, addDays } from "date-fns";

// ─── SVG Icons (no emojis) ────────────────────────────────────────────
const PlaneIcon = ({ size = 11, color = "#E11D48" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={color}>
    <path d="M17.8 19.2L16 11l3.5-3.5C21 6 21 4 19.5 2.5S18 2 16.5 3.5L13 7 4.8 6.2c-.5-.1-.9.1-1.1.5L2 8.9c-.2.4-.1.9.2 1.2l4.6 4.1-1.5 6.4 2.8 2.8 5.3-3.2 4.1 4.6c.3.4.8.5 1.2.2l1.1-1.2c.4-.2.6-.6.5-1.1z" />
  </svg>
);

const SearchIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
    <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" />
  </svg>
);

const TrendUpIcon = ({ size = 11 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
    <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
    <polyline points="16 7 22 7 22 13" />
  </svg>
);

const TrendDownIcon = ({ size = 11 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
    <polyline points="22 17 13.5 8.5 8.5 13.5 2 7" />
    <polyline points="16 17 22 17 22 11" />
  </svg>
);

const RadarIcon = ({ size = 11 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <circle cx="12" cy="12" r="2" />
    <path d="M16.24 7.76a6 6 0 010 8.49m-8.48-.01a6 6 0 010-8.49m11.31-2.82a10 10 0 010 14.14m-14.14 0a10 10 0 010-14.14" />
  </svg>
);

const ChevronRightIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
    <path d="M9 18l6-6-6-6" />
  </svg>
);

const ChevronLeftIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
    <path d="M15 18l-6-6 6-6" />
  </svg>
);

// ─── Status badge helper (replaces emoji badges) ──────────────────────
function RecommendationBadge({ rec }: { rec?: string }) {
  if (!rec) return null;
  const r = rec.toUpperCase();

  if (r.includes("BOOK NOW") || r.includes("BOOK_NOW")) {
    return (
      <span style={{
        display: "inline-flex", alignItems: "center", gap: "4px",
        padding: "3px 10px", borderRadius: "9999px",
        background: "#E11D48", color: "#fff",
        fontFamily: "'JetBrains Mono', monospace", fontSize: "10px", fontWeight: 700, letterSpacing: "0.06em",
      }}>
        <TrendUpIcon size={10} /> Book Now
      </span>
    );
  }
  if (r.includes("WAIT")) {
    return (
      <span style={{
        display: "inline-flex", alignItems: "center", gap: "4px",
        padding: "3px 10px", borderRadius: "9999px",
        background: "#FEF3C7", color: "#92400E", border: "1px solid #FDE68A",
        fontFamily: "'JetBrains Mono', monospace", fontSize: "10px", fontWeight: 700, letterSpacing: "0.06em",
      }}>
        <TrendDownIcon size={10} /> Wait
      </span>
    );
  }
  if (r.includes("FAIR") || r.includes("STABLE")) {
    return (
      <span style={{
        display: "inline-flex", alignItems: "center", gap: "4px",
        padding: "3px 10px", borderRadius: "9999px",
        background: "#F1F5F9", color: "#64748B", border: "1px solid #E2E8F0",
        fontFamily: "'JetBrains Mono', monospace", fontSize: "10px", fontWeight: 700, letterSpacing: "0.06em",
      }}>
        <RadarIcon size={10} /> Price Stable
      </span>
    );
  }
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: "4px",
      padding: "3px 10px", borderRadius: "9999px",
      background: "#F1F5F9", color: "#64748B", border: "1px solid #E2E8F0",
      fontFamily: "'JetBrains Mono', monospace", fontSize: "10px", fontWeight: 700, letterSpacing: "0.06em",
    }}>
      <RadarIcon size={10} /> Monitor
    </span>
  );
}

function FlightsContent() {
  const router = useRouter();
  const params = useSearchParams();
  const defaultDate = format(addDays(new Date(), 7), "yyyy-MM-dd");
  const tomorrow    = format(addDays(new Date(), 1), "yyyy-MM-dd");

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
    if (s === "Price") arr.sort((a, b) => a.price.total - b.price.total);
    if (s === "Duration") arr.sort((a, b) => (a.itineraries[0]?.duration || "").localeCompare(b.itineraries[0]?.duration || ""));
    if (s === "Departure") arr.sort((a, b) =>
      (a.itineraries[0]?.segments[0]?.departure_time || "").localeCompare(b.itineraries[0]?.segments[0]?.departure_time || "")
    );
    return arr;
  };

  const doSearch = async (currentForm = form, currentSort = sort) => {
    const org = resolveCityToIATA(currentForm.origin.trim());
    const dst = resolveCityToIATA(currentForm.destination.trim());

    if (!org || !dst) { setError("Please enter origin and destination."); return; }
    if (org === dst) { setError("Origin and destination cannot be the same."); return; }
    if (currentForm.departure_date < tomorrow) { setError("Please select a future departure date."); return; }

    setLoading(true);
    setError("");
    setSearched(true);

    try {
      const res = await searchFlights({
        origin: org,
        destination: dst,
        departure_date: currentForm.departure_date,
        adults: Number(currentForm.adults),
        cabin_class: currentForm.cabin_class as any,
        max_results: 20,
      });
      setFlights(sortFlights(res.flights || [], currentSort));
      setDataSource((res as any).data_source || "");
    } catch (e: any) {
      const msg = e.message || "";
      if (msg.toLowerCase().includes("network") || msg.includes("0")) {
        setError(`Cannot connect to backend. Make sure it's running.`);
      } else {
        setError(msg || "Search failed. Please try again.");
      }
      setFlights([]);
    }
    setLoading(false);
  };

  useEffect(() => {
    if (params.get("origin")) doSearch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSort = (s: string) => {
    setSort(s);
    setFlights((prev) => sortFlights(prev, s));
  };

  const sourceLabel: Record<string, string> = {
    AMADEUS: "Live Amadeus GDS",
    SKYMIND_SYNTHETIC: "SkyMind Synthetic",
    DATABASE: "Cached Data",
  };

  return (
    <div>
      <NavBar />
      <div style={{ paddingTop: "60px" }}>

        {/* ── Search Strip ─────────────────────────────────────── */}
        <div className="search-strip">
          <div className="wrap">
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginBottom: "10px" }}>
              <div>
                <label className="field-label">From</label>
                <input
                  className="inp"
                  value={form.origin}
                  onChange={(e) => setForm((f) => ({ ...f, origin: e.target.value.toUpperCase() }))}
                  placeholder="DEL or Delhi"
                  style={{ textTransform: "uppercase", fontFamily: "var(--font-mono)", fontWeight: 600 }}
                />
              </div>
              <div>
                <label className="field-label">To</label>
                <input
                  className="inp"
                  value={form.destination}
                  onChange={(e) => setForm((f) => ({ ...f, destination: e.target.value.toUpperCase() }))}
                  placeholder="BOM or Mumbai"
                  style={{ textTransform: "uppercase", fontFamily: "var(--font-mono)", fontWeight: 600 }}
                />
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr auto", gap: "10px", alignItems: "end" }}>
              <div>
                <label className="field-label">Date</label>
                <input type="date" className="inp" value={form.departure_date} min={tomorrow} onChange={(e) => setForm((f) => ({ ...f, departure_date: e.target.value }))} />
              </div>
              <div>
                <label className="field-label">Passengers</label>
                <select className="inp" value={form.adults} onChange={(e) => setForm((f) => ({ ...f, adults: e.target.value }))}>
                  {[1, 2, 3, 4, 5, 6].map((n) => (
                    <option key={n} value={n}>{n} {n === 1 ? "Adult" : "Adults"}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="field-label">Class</label>
                <select className="inp" value={form.cabin_class} onChange={(e) => setForm((f) => ({ ...f, cabin_class: e.target.value }))}>
                  <option value="ECONOMY">Economy</option>
                  <option value="PREMIUM_ECONOMY">Prem Economy</option>
                  <option value="BUSINESS">Business</option>
                  <option value="FIRST">First Class</option>
                </select>
              </div>
              <button
                className="btn btn-red"
                onClick={() => doSearch()}
                disabled={loading}
                style={{ height: "44px", fontSize: "13px", gap: "6px" }}
              >
                <SearchIcon /> {loading ? "Searching..." : "Search"}
              </button>
            </div>
          </div>
        </div>

        {/* ── Results ──────────────────────────────────────────── */}
        <div className="wrap" style={{ paddingTop: "28px", paddingBottom: "60px" }}>
          <div className="results-bar">
            <div>
              <div className="results-title">
                <span style={{ fontFamily: "var(--font-mono)", fontWeight: 700 }}>{form.origin}</span>
                <span style={{ color: "var(--grey-2)" }}> → </span>
                <span style={{ fontFamily: "var(--font-mono)", fontWeight: 700 }}>{form.destination}</span>
                <span className="badge badge-dark" style={{ marginLeft: "8px", fontSize: "9px" }}>{form.departure_date}</span>
              </div>
              <div className="results-count" style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap", marginTop: "4px" }}>
                {loading ? "Searching live fares..." : searched ? `${flights.length} flight${flights.length !== 1 ? "s" : ""} found` : "Enter your route and search"}
                {dataSource && !loading && (
                  <span style={{ fontSize: "10px", color: "var(--grey-2)" }}>
                    · {sourceLabel[dataSource] || dataSource}
                  </span>
                )}
              </div>
            </div>
            <div className="sort-strip">
              {["Price", "Duration", "Departure"].map((s) => (
                <button key={s} className={`sort-btn${sort === s ? " active" : ""}`} onClick={() => handleSort(s)}>{s}</button>
              ))}
            </div>
          </div>

          {/* Error */}
          {error && (
            <div style={{
              border: "1.5px solid rgba(225,29,72,0.2)",
              padding: "16px 20px",
              background: "#FFF1F2",
              marginBottom: "16px",
              borderRadius: "12px",
              borderLeft: "4px solid #E11D48",
            }}>
              <div style={{ fontWeight: 700, color: "#E11D48", marginBottom: "6px", fontSize: "14px", letterSpacing: "-0.01em" }}>SEARCH FAILED</div>
              <div style={{ fontSize: "13px", color: "var(--grey-4)", marginBottom: "10px" }}>{error}</div>
              <button className="btn btn-primary" onClick={() => doSearch()} style={{ fontSize: "12px", padding: "8px 16px" }}>Try again</button>
            </div>
          )}

          {/* Loading skeletons */}
          {loading && Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flight-card" style={{ marginBottom: "12px", padding: "20px" }}>
              <div style={{ display: "grid", gridTemplateColumns: "160px 1fr 140px", gap: "20px" }}>
                <div>
                  <div className="skel" style={{ height: "40px", width: "40px", marginBottom: "10px" }} />
                  <div className="skel" style={{ height: "12px", width: "80%", marginBottom: "6px" }} />
                  <div className="skel" style={{ height: "10px", width: "60%" }} />
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
                  <div className="skel" style={{ height: "28px", width: "70px" }} />
                  <div className="skel" style={{ height: "1px", flex: 1 }} />
                  <div className="skel" style={{ height: "28px", width: "70px" }} />
                </div>
                <div>
                  <div className="skel" style={{ height: "28px", width: "90%", marginBottom: "8px" }} />
                  <div className="skel" style={{ height: "32px", width: "100%" }} />
                </div>
              </div>
            </div>
          ))}

          {/* No results */}
          {!loading && searched && flights.length === 0 && !error && (
            <div style={{ border: "1.5px solid var(--grey-0)", padding: "60px 24px", textAlign: "center", borderRadius: "16px", background: "var(--white)" }}>
              <div style={{ fontWeight: 800, fontSize: "1.8rem", letterSpacing: "-0.04em", color: "var(--charcoal)", marginBottom: "8px" }}>NO FLIGHTS FOUND</div>
              <div style={{ fontSize: "14px", color: "var(--grey-4)", marginBottom: "20px" }}>
                Try: DEL→BOM, BOM→BLR, DEL→BLR, DEL→HYD
              </div>
              <button className="btn btn-primary" onClick={() => doSearch()}>Search again</button>
            </div>
          )}

          {/* ── Flight Cards ──────────────────────────────────── */}
          {flights.map((f, i) => {
            const itin      = f.itineraries[0];
            const seg       = itin?.segments[0];
            const lastSeg   = itin?.segments[itin.segments.length - 1];
            const stops     = (itin?.segments.length || 1) - 1;
            const dep       = seg?.departure_time
              ? new Date(seg.departure_time).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false })
              : "--:--";
            const arr       = lastSeg?.arrival_time
              ? new Date(lastSeg.arrival_time).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false })
              : "--:--";
            const dur       = formatDuration(itin?.duration || "");
            const isFirst   = i === 0;
            const airlineCode = f.primary_airline || seg?.airline_code || "AI";
            const airlineName = f.primary_airline_name || seg?.airline_name || airlineCode;
            const price     = Math.round(f.price.total);
            const aiPrice   = f.ai_price ? Math.round(f.ai_price) : null;
            const aiDiff    = aiPrice ? aiPrice - price : null;

            return (
              <div
                key={f.id}
                className={`flight-card${isFirst ? " best" : ""}`}
                style={{ animation: `fadeUp 0.35s ${Math.min(i * 0.05, 0.3)}s ease both` }}
                onClick={() => {
                  if (typeof window !== "undefined") {
                    sessionStorage.setItem("selected_flight", JSON.stringify(f));
                    sessionStorage.setItem("search_params", JSON.stringify(form));
                  }
                  router.push("/booking");
                }}
              >
                {isFirst && <div className="best-tag">Best value</div>}

                <div className="flight-top" style={{ borderTop: isFirst ? "2px solid #E11D48" : undefined }}>

                  {/* ── Airline column ─────────────────────────── */}
                  <div className="flight-airline">
                    <AirlineLogo code={airlineCode} name={airlineName} size={42} />
                    <div style={{ minWidth: 0 }}>
                      <div className="airline-name-txt">{airlineName}</div>
                      <div className="airline-num-txt">{seg?.flight_number || "--"}</div>
                      {stops > 0 && (
                        <div style={{ fontSize: "10px", color: "var(--grey-3)", fontFamily: "var(--font-mono)", marginTop: "2px" }}>
                          via {itin?.segments.slice(0, -1).map((s) => s.destination).join(", ")}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* ── Timeline column ────────────────────────── */}
                  <div className="flight-timeline">
                    {/* Departure */}
                    <div className="t-endpoint">
                      <div className="t-time">{dep}</div>
                      <div className="t-iata">{seg?.origin || form.origin}</div>
                    </div>

                    {/* Path */}
                    <div className="t-path">
                      <div className="t-dur">{dur}</div>
                      <div className="t-line">
                        <div className="t-plane-icon">
                          <PlaneIcon size={11} color="#E11D48" />
                        </div>
                      </div>
                      <div className={`t-stop ${stops === 0 ? "direct" : "one-stop"}`}>
                        {stops === 0 ? "Non-stop" : `${stops} stop${stops > 1 ? "s" : ""}`}
                      </div>
                    </div>

                    {/* Arrival */}
                    <div className="t-endpoint right">
                      <div className="t-time">{arr}</div>
                      <div className="t-iata">{lastSeg?.destination || form.destination}</div>
                    </div>
                  </div>

                  {/* ── Price column ───────────────────────────── */}
                  <div className="flight-price-col">
                    <div style={{ textAlign: "right" }}>
                      <div className="f-price">₹{price.toLocaleString("en-IN")}</div>
                      <div className="f-price-per">per person</div>
                      {f.seats_available && f.seats_available <= 5 && (
                        <div className="f-seats">{f.seats_available} left</div>
                      )}

                      {/* Intelligence Insight row */}
                      {aiPrice && aiDiff !== null && (
                        <div className={`f-insight ${aiDiff > 0 ? "up" : "down"}`}>
                          {aiDiff > 0 ? <TrendUpIcon size={10} /> : <TrendDownIcon size={10} />}
                          AI: ₹{aiPrice.toLocaleString("en-IN")}
                        </div>
                      )}
                    </div>

                    <button
                      className="btn btn-primary"
                      style={{ fontSize: "13px", padding: "8px 16px", letterSpacing: "-0.01em" }}
                      onClick={(e) => {
                        e.stopPropagation();
                        if (typeof window !== "undefined") {
                          sessionStorage.setItem("selected_flight", JSON.stringify(f));
                          sessionStorage.setItem("search_params", JSON.stringify(form));
                        }
                        router.push("/booking");
                      }}
                    >
                      Select <ChevronRightIcon />
                    </button>
                  </div>
                </div>

                {/* ── Footer row ─────────────────────────────── */}
                <div className="flight-bottom">
                  <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
                    <RecommendationBadge rec={f.recommendation} />
                    {f.advice && (
                      <span style={{ fontSize: "12px", color: "var(--grey-3)", maxWidth: "320px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {f.advice}
                      </span>
                    )}
                    <Link
                      href={`/predict?origin=${form.origin}&destination=${form.destination}`}
                      onClick={(e) => e.stopPropagation()}
                      style={{ fontSize: "12px", color: "var(--red)", textDecoration: "underline", textUnderlineOffset: "2px", whiteSpace: "nowrap", fontFamily: "var(--font-mono)" }}
                    >
                      30-day forecast
                    </Link>
                  </div>
                  <span style={{ fontSize: "11px", color: "var(--grey-2)", fontFamily: "var(--font-mono)", whiteSpace: "nowrap" }}>
                    {form.cabin_class === "ECONOMY" ? "Economy" : form.cabin_class}
                  </span>
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
    <Suspense fallback={
      <div style={{ paddingTop: "120px", textAlign: "center", color: "var(--grey-3)", fontFamily: "var(--font-mono)", fontSize: "13px" }}>
        Loading...
      </div>
    }>
      <FlightsContent />
    </Suspense>
  );
}
