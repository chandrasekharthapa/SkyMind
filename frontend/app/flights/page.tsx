"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import NavBar from "@/components/layout/NavBar";
import AirlineLogo from "@/components/flights/AirlineLogo";
import { searchFlights, formatDuration, resolveCityToIATA } from "@/lib/api";
import type { FlightOffer } from "@/types";
import { format, addDays } from "date-fns";

// Static airport fallback for the search bar
const POPULAR_AIRPORTS = [
  "DEL", "BOM", "BLR", "MAA", "HYD", "CCU", "COK", "GOI",
  "AMD", "JAI", "BBI", "DXB", "LHR", "SIN", "DOH",
];

function FlightsContent() {
  const router = useRouter();
  const params = useSearchParams();
  const defaultDate = format(addDays(new Date(), 7), "yyyy-MM-dd");
  const tomorrow = format(addDays(new Date(), 1), "yyyy-MM-dd");

  const [form, setForm] = useState({
    origin: params.get("origin") || "DEL",
    destination: params.get("destination") || "BOM",
    departure_date: params.get("departure_date") || defaultDate,
    adults: params.get("adults") || "1",
    cabin_class: params.get("cabin_class") || "ECONOMY",
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
    if (s === "Duration") arr.sort((a, b) =>
      (a.itineraries[0]?.duration || "").localeCompare(b.itineraries[0]?.duration || "")
    );
    if (s === "Departure") arr.sort((a, b) =>
      (a.itineraries[0]?.segments[0]?.departure_time || "").localeCompare(
        b.itineraries[0]?.segments[0]?.departure_time || ""
      )
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
      if (msg.toLowerCase().includes("network") || msg.toLowerCase().includes("fetch") || msg.includes("0")) {
        setError(`Cannot connect to backend at ${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"}. Make sure it's running.`);
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

  const recBadge = (rec?: string) => {
    if (!rec) return null;
    const r = rec.toUpperCase();
    if (r.includes("BOOK NOW") || r.includes("BOOK_NOW")) return { cls: "badge-red", label: "BOOK NOW 🔥" };
    if (r.includes("WAIT")) return { cls: "badge-amber", label: "WAIT ⏳" };
    if (r.includes("FAIR")) return { cls: "badge-black", label: "FAIR ✅" };
    return { cls: "badge-off", label: "MONITOR" };
  };

  const sourceLabel: Record<string, string> = {
    AMADEUS: "🟢 Live Amadeus GDS",
    SKYMIND_SYNTHETIC: "🟡 SkyMind AI Synthetic",
    DATABASE: "🔵 Cached Data",
  };

  return (
    <div>
      <NavBar />
      <div style={{ paddingTop: 60 }}>

        {/* Search strip */}
        <div className="search-strip">
          <div className="wrap">
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
              <div>
                <label className="field-label">From</label>
                <input
                  className="inp" value={form.origin}
                  onChange={(e) => setForm((f) => ({ ...f, origin: e.target.value.toUpperCase() }))}
                  placeholder="DEL or Delhi"
                  style={{ textTransform: "uppercase" }}
                />
              </div>
              <div>
                <label className="field-label">To</label>
                <input
                  className="inp" value={form.destination}
                  onChange={(e) => setForm((f) => ({ ...f, destination: e.target.value.toUpperCase() }))}
                  placeholder="BOM or Mumbai"
                  style={{ textTransform: "uppercase" }}
                />
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr auto", gap: 10, alignItems: "end" }}>
              <div>
                <label className="field-label">Date</label>
                <input
                  type="date" className="inp"
                  value={form.departure_date} min={tomorrow}
                  onChange={(e) => setForm((f) => ({ ...f, departure_date: e.target.value }))}
                />
              </div>
              <div>
                <label className="field-label">Passengers</label>
                <select
                  className="inp" value={form.adults}
                  onChange={(e) => setForm((f) => ({ ...f, adults: e.target.value }))}
                >
                  {[1, 2, 3, 4, 5, 6].map((n) => (
                    <option key={n} value={n}>{n} {n === 1 ? "Adult" : "Adults"}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="field-label">Class</label>
                <select
                  className="inp" value={form.cabin_class}
                  onChange={(e) => setForm((f) => ({ ...f, cabin_class: e.target.value }))}
                >
                  <option value="ECONOMY">Economy</option>
                  <option value="PREMIUM_ECONOMY">Prem Economy</option>
                  <option value="BUSINESS">Business</option>
                  <option value="FIRST">First Class</option>
                </select>
              </div>
              <button className="btn btn-red-full" onClick={() => doSearch()} disabled={loading}>
                {loading ? "…" : "Search"}
              </button>
            </div>
          </div>
        </div>

        <div className="wrap" style={{ paddingTop: 24, paddingBottom: 60 }}>

          {/* Results bar */}
          <div className="results-bar">
            <div>
              <div className="results-title">
                <span style={{ fontFamily: "var(--fm)", fontWeight: 700 }}>{form.origin}</span>
                <span style={{ color: "var(--grey3)" }}> → </span>
                <span style={{ fontFamily: "var(--fm)", fontWeight: 700 }}>{form.destination}</span>
                <span className="badge badge-black" style={{ marginLeft: 8, fontSize: ".6rem" }}>
                  {form.departure_date}
                </span>
              </div>
              <div className="results-count" style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                {loading
                  ? "Searching live fares…"
                  : searched
                  ? `${flights.length} flight${flights.length !== 1 ? "s" : ""} found`
                  : "Enter your route and search"}
                {dataSource && !loading && (
                  <span style={{ fontSize: ".65rem", color: "var(--grey3)", fontFamily: "var(--fm)" }}>
                    · {sourceLabel[dataSource] || dataSource}
                  </span>
                )}
              </div>
            </div>
            <div className="sort-strip">
              {["Price", "Duration", "Departure"].map((s) => (
                <button key={s} className={`sort-btn${sort === s ? " active" : ""}`} onClick={() => handleSort(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>

          {/* Error */}
          {error && (
            <div style={{ border: "1px solid var(--red)", padding: "16px 20px", background: "rgba(232,25,26,.04)", marginBottom: 16, borderLeft: "4px solid var(--red)" }}>
              <div style={{ fontWeight: 700, color: "var(--red)", marginBottom: 6, fontFamily: "var(--fd)", fontSize: "1.1rem" }}>SEARCH FAILED</div>
              <div style={{ fontSize: ".875rem", color: "var(--grey4)", marginBottom: 8 }}>{error}</div>
              <button className="btn btn-primary" onClick={() => doSearch()} style={{ fontSize: ".78rem", padding: "8px 16px" }}>
                Try again
              </button>
            </div>
          )}

          {/* Loading skeletons */}
          {loading && Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flight-card" style={{ marginBottom: 8 }}>
              <div style={{ display: "grid", gridTemplateColumns: "160px 1fr 140px" }}>
                <div style={{ padding: 20, borderRight: "1px solid var(--grey1)" }}>
                  <div className="skel" style={{ height: 42, width: 42, marginBottom: 10 }} />
                  <div className="skel" style={{ height: 12, width: "80%", marginBottom: 6 }} />
                  <div className="skel" style={{ height: 10, width: "60%" }} />
                </div>
                <div style={{ padding: "20px 24px", display: "flex", alignItems: "center", gap: 16 }}>
                  <div className="skel" style={{ height: 28, width: 70 }} />
                  <div className="skel" style={{ height: 1, flex: 1 }} />
                  <div className="skel" style={{ height: 28, width: 70 }} />
                </div>
                <div style={{ padding: 20, borderLeft: "1px solid var(--grey1)" }}>
                  <div className="skel" style={{ height: 28, width: "90%", marginBottom: 8 }} />
                  <div className="skel" style={{ height: 32, width: "100%" }} />
                </div>
              </div>
            </div>
          ))}

          {/* No results */}
          {!loading && searched && flights.length === 0 && !error && (
            <div style={{ border: "1px solid var(--grey1)", padding: "60px 24px", textAlign: "center" }}>
              <div style={{ fontFamily: "var(--fd)", fontSize: "2rem", color: "var(--black)", marginBottom: 8, letterSpacing: ".04em" }}>NO FLIGHTS FOUND</div>
              <div style={{ fontSize: ".875rem", color: "var(--grey4)", marginBottom: 20 }}>
                Try popular routes: DEL→BOM, BOM→BLR, DEL→BLR, DEL→DXB
              </div>
              <button className="btn btn-primary" onClick={() => doSearch()}>Search again</button>
            </div>
          )}

          {/* Flight cards */}
          {flights.map((f, i) => {
            const itin = f.itineraries[0];
            const seg = itin?.segments[0];
            const lastSeg = itin?.segments[itin.segments.length - 1];
            const stops = (itin?.segments.length || 1) - 1;
            const dep = seg?.departure_time
              ? new Date(seg.departure_time).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false })
              : "--:--";
            const arr = lastSeg?.arrival_time
              ? new Date(lastSeg.arrival_time).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false })
              : "--:--";
            const dur = formatDuration(itin?.duration || "");
            const rec = recBadge(f.recommendation);
            const isFirst = i === 0;
            const airlineCode = f.primary_airline || seg?.airline_code || "AI";
            const airlineName = f.primary_airline_name || seg?.airline_name || airlineCode;
            const price = Math.round(f.price.total);

            return (
              <div
                key={f.id}
                className="flight-card"
                style={{
                  borderColor: isFirst ? "var(--black)" : undefined,
                  animation: `fadeUp .35s ${Math.min(i * 0.05, 0.3)}s ease both`,
                  cursor: "pointer",
                }}
                onClick={() => {
                  if (typeof window !== "undefined") {
                    sessionStorage.setItem("selected_flight", JSON.stringify(f));
                    sessionStorage.setItem("search_params", JSON.stringify(form));
                  }
                  router.push("/booking");
                }}
              >
                {isFirst && <div className="best-tag">Best value</div>}
                <div className="flight-top" style={{ borderTop: isFirst ? "2px solid var(--red)" : undefined }}>

                  {/* Airline */}
                  <div className="flight-airline">
                    <AirlineLogo code={airlineCode} name={airlineName} size={42} />
                    <div style={{ minWidth: 0 }}>
                      <div className="airline-name-txt">{airlineName}</div>
                      <div className="airline-num-txt">{seg?.flight_number || "--"}</div>
                      {stops > 0 && (
                        <div style={{ fontSize: ".65rem", color: "var(--grey3)", fontFamily: "var(--fm)", marginTop: 2 }}>
                          via {itin?.segments.slice(0, -1).map((s) => s.destination).join(", ")}
                        </div>
                      )}
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
                      <div style={{ height: 1, width: "100%", background: "var(--grey2)", position: "relative" }}>
                        <div style={{
                          position: "absolute", top: "50%", left: "50%",
                          transform: "translate(-50%,-50%)",
                          background: "white", padding: "0 4px", color: "var(--red)",
                        }}>
                          <svg width={11} height={11} viewBox="0 0 24 24" fill="currentColor">
                            <path d="M17.8 19.2L16 11l3.5-3.5C21 6 21 4 19.5 2.5S18 2 16.5 3.5L13 7 4.8 6.2c-.5-.1-.9.1-1.1.5L2 8.9c-.2.4-.1.9.2 1.2l4.6 4.1-1.5 6.4 2.8 2.8 5.3-3.2 4.1 4.6c.3.4.8.5 1.2.2l1.1-1.2c.4-.2.6-.6.5-1.1z" />
                          </svg>
                        </div>
                      </div>
                      <div className={`t-stop ${stops === 0 ? "direct" : "one-stop"}`}>
                        {stops === 0 ? "Non-stop" : `${stops} stop${stops > 1 ? "s" : ""}`}
                      </div>
                    </div>
                    <div style={{ flexShrink: 0, textAlign: "right" }}>
                      <div className="t-time">{arr}</div>
                      <div className="t-iata">{lastSeg?.destination || form.destination}</div>
                    </div>
                  </div>

                  {/* Price */}
                  <div className="flight-price-col">
                    <div>
                      <div className="f-price">₹{price.toLocaleString("en-IN")}</div>
                      <div className="f-price-per">per person</div>
                      {f.seats_available && f.seats_available <= 5 && (
                        <div className="f-seats">{f.seats_available} left!</div>
                      )}
                      {f.ai_price && f.ai_price > price * 1.05 && (
                        <div style={{ fontSize: ".65rem", color: "#16a34a", marginTop: 2, fontFamily: "var(--fm)" }}>
                          AI: ₹{Math.round(f.ai_price).toLocaleString("en-IN")} ↑
                        </div>
                      )}
                    </div>
                    <button
                      className="btn btn-primary"
                      style={{ fontSize: ".75rem", padding: "8px 14px" }}
                      onClick={(e) => {
                        e.stopPropagation();
                        if (typeof window !== "undefined") {
                          sessionStorage.setItem("selected_flight", JSON.stringify(f));
                          sessionStorage.setItem("search_params", JSON.stringify(form));
                        }
                        router.push("/booking");
                      }}
                    >
                      Select →
                    </button>
                  </div>
                </div>

                {/* Footer */}
                <div className="flight-bottom">
                  <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    {rec && <span className={`badge ${rec.cls}`}>{rec.label}</span>}
                    {f.advice && (
                      <span style={{ fontSize: ".75rem", color: "var(--grey4)", maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {f.advice}
                      </span>
                    )}
                    <Link
                      href={`/predict?origin=${form.origin}&destination=${form.destination}`}
                      onClick={(e) => e.stopPropagation()}
                      style={{ fontSize: ".75rem", color: "var(--red)", textDecoration: "underline", textUnderlineOffset: 2, whiteSpace: "nowrap" }}
                    >
                      30-day forecast →
                    </Link>
                  </div>
                  <span style={{ fontSize: ".7rem", color: "var(--grey3)", fontFamily: "var(--fm)", whiteSpace: "nowrap" }}>
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
      <div style={{ paddingTop: 120, textAlign: "center", color: "var(--grey3)", fontFamily: "var(--fm)", fontSize: ".85rem" }}>
        Loading…
      </div>
    }>
      <FlightsContent />
    </Suspense>
  );
}
