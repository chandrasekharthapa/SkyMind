"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { format, addDays } from "date-fns";
import { searchAirports, resolveCityToIATA } from "@/lib/api";
import type { AirportResult } from "@/lib/api";

// ─── Static fallback airports (domestic focus) ────────────────────────
const ALL_AIRPORTS: AirportResult[] = [
  { iata: "DEL", city: "New Delhi",        name: "Indira Gandhi International",        country: "India" },
  { iata: "BOM", city: "Mumbai",           name: "Chhatrapati Shivaji Maharaj Intl",   country: "India" },
  { iata: "BLR", city: "Bengaluru",        name: "Kempegowda International",           country: "India" },
  { iata: "MAA", city: "Chennai",          name: "Chennai International",              country: "India" },
  { iata: "HYD", city: "Hyderabad",        name: "Rajiv Gandhi International",         country: "India" },
  { iata: "CCU", city: "Kolkata",          name: "Netaji Subhas Chandra Bose Intl",    country: "India" },
  { iata: "COK", city: "Kochi",            name: "Cochin International",               country: "India" },
  { iata: "GOI", city: "Goa",              name: "Goa International Airport",          country: "India" },
  { iata: "AMD", city: "Ahmedabad",        name: "Sardar Vallabhbhai Patel Intl",      country: "India" },
  { iata: "JAI", city: "Jaipur",           name: "Jaipur International",               country: "India" },
  { iata: "LKO", city: "Lucknow",          name: "Chaudhary Charan Singh Intl",        country: "India" },
  { iata: "PNQ", city: "Pune",             name: "Pune Airport",                       country: "India" },
  { iata: "ATQ", city: "Amritsar",         name: "Sri Guru Ram Dass Jee Intl",         country: "India" },
  { iata: "BBI", city: "Bhubaneswar",      name: "Biju Patnaik International",         country: "India" },
  { iata: "IXR", city: "Ranchi",           name: "Birsa Munda Airport",                country: "India" },
  { iata: "PAT", city: "Patna",            name: "Jay Prakash Narayan Intl",           country: "India" },
  { iata: "VNS", city: "Varanasi",         name: "Lal Bahadur Shastri Intl",           country: "India" },
  { iata: "IDR", city: "Indore",           name: "Devi Ahilyabai Holkar Airport",      country: "India" },
  { iata: "BHO", city: "Bhopal",           name: "Raja Bhoj Airport",                  country: "India" },
  { iata: "TRV", city: "Thiruvananthapuram", name: "Trivandrum International",         country: "India" },
  { iata: "CCJ", city: "Kozhikode",        name: "Calicut International",              country: "India" },
  { iata: "CJB", city: "Coimbatore",       name: "Coimbatore International",           country: "India" },
  { iata: "GAU", city: "Guwahati",         name: "Lokpriya Gopinath Bordoloi Intl",    country: "India" },
  { iata: "IXE", city: "Mangalore",        name: "Mangalore International",            country: "India" },
  { iata: "SXR", city: "Srinagar",         name: "Sheikh ul-Alam International",       country: "India" },
  { iata: "IXL", city: "Leh",              name: "Kushok Bakula Rimpochhe Airport",    country: "India" },
];

function searchLocal(q: string): AirportResult[] {
  const lower = q.toLowerCase();
  return ALL_AIRPORTS.filter((a) =>
    a.iata.toLowerCase().includes(lower) ||
    a.city.toLowerCase().includes(lower) ||
    a.name.toLowerCase().includes(lower)
  ).slice(0, 10);
}

// ─── SVG Icons ────────────────────────────────────────────────────────
const PlaneIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <path d="M17.8 19.2L16 11l3.5-3.5C21 6 21 4 19.5 2.5S18 2 16.5 3.5L13 7 4.8 6.2c-.5-.1-.9.1-1.1.5L2 8.9c-.2.4-.1.9.2 1.2l4.6 4.1-1.5 6.4 2.8 2.8 5.3-3.2 4.1 4.6c.3.4.8.5 1.2.2l1.1-1.2c.4-.2.6-.6.5-1.1z" />
  </svg>
);

const ArrowUpDown = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <path d="M7 16V4m0 0L3 8m4-4l4 4M17 8v12m0 0l4-4m-4 4l-4-4" />
  </svg>
);

const SearchIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
    <circle cx="11" cy="11" r="8" />
    <path d="M21 21l-4.35-4.35" />
  </svg>
);

const ChevronDown = () => (
  <svg width="10" height="6" viewBox="0 0 10 6" fill="none">
    <path d="M1 1L5 5L9 1" stroke="#94A3B8" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

const XIcon = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
    <path d="M1 1l10 10M11 1L1 11" stroke="#94A3B8" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

// ─── Airport Dropdown Field ───────────────────────────────────────────
interface AirportFieldProps {
  label: string;
  value: string;
  displayValue: string;
  onChange: (iata: string, display: string) => void;
  placeholder: string;
}

function AirportField({ label, value, displayValue, onChange, placeholder }: AirportFieldProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<AirportResult[]>([]);
  const [apiLoading, setApiLoading] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const fn = (e: MouseEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", fn);
    return () => document.removeEventListener("mousedown", fn);
  }, []);

  const doSearch = useCallback(async (q: string) => {
    if (!q) {
      setResults(ALL_AIRPORTS.slice(0, 12));
      return;
    }
    const local = searchLocal(q);
    setResults(local);
    setApiLoading(true);
    try {
      const api = await searchAirports(q);
      if (api.length > 0) setResults(api.slice(0, 12));
    } catch { /* keep local */ } finally { setApiLoading(false); }
  }, []);

  useEffect(() => {
    if (!open) return;
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => doSearch(query), 200);
  }, [query, open, doSearch]);

  const openDrop = () => {
    setOpen(true);
    setQuery("");
    setResults(ALL_AIRPORTS.slice(0, 12));
    setTimeout(() => inputRef.current?.focus(), 60);
  };

  const select = (ap: AirportResult) => {
    onChange(ap.iata, `${ap.city} (${ap.iata})`);
    setOpen(false);
    setQuery("");
  };

  return (
    <div ref={wrap} style={{ position: "relative" }}>
      <label className="field-label">{label}</label>

      {/* Trigger button */}
      <button
        type="button"
        onClick={openDrop}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          gap: "10px",
          padding: "10px 14px",
          background: "#fff",
          border: open ? "1.5px solid #E11D48" : "1.5px solid #E2E8F0",
          boxShadow: open ? "0 0 0 3px rgba(225,29,72,0.08)" : "none",
          cursor: "pointer",
          textAlign: "left",
          fontFamily: "'Plus Jakarta Sans', sans-serif",
          transition: "border-color 120ms, box-shadow 120ms",
          minHeight: "44px",
          borderRadius: "8px",
        }}
      >
        {value ? (
          <span style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: "11px",
            fontWeight: 700,
            color: "#E11D48",
            background: "#FFF1F2",
            padding: "2px 8px",
            borderRadius: "4px",
            border: "1px solid rgba(225,29,72,0.15)",
            flexShrink: 0,
            letterSpacing: "0.06em",
          }}>
            {value}
          </span>
        ) : (
          <span style={{ color: "#CBD5E1", flexShrink: 0 }}><PlaneIcon /></span>
        )}
        <div style={{ flex: 1, minWidth: 0, textAlign: "left" }}>
          {displayValue ? (
            <div style={{ fontSize: "14px", fontWeight: 600, color: "#1E293B", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", letterSpacing: "-0.01em" }}>
              {displayValue}
            </div>
          ) : (
            <div style={{ fontSize: "14px", color: "#CBD5E1", fontWeight: 400 }}>{placeholder}</div>
          )}
        </div>
        <ChevronDown />
      </button>

      {/* Dropdown */}
      {open && (
        <div style={{
          position: "absolute",
          top: "calc(100% + 4px)",
          left: 0,
          right: 0,
          zIndex: 500,
          background: "#fff",
          border: "1.5px solid #E11D48",
          borderRadius: "12px",
          boxShadow: "0 16px 40px rgba(30,41,59,0.15)",
          maxHeight: "320px",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}>
          {/* Search input */}
          <div style={{ padding: "10px 12px", borderBottom: "1px solid #F1F5F9", display: "flex", alignItems: "center", gap: "8px", flexShrink: 0, background: "#F8FAFC" }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#94A3B8" strokeWidth="2" style={{ flexShrink: 0 }}>
              <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" />
            </svg>
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="City or IATA code..."
              style={{
                width: "100%",
                border: "none",
                outline: "none",
                fontSize: "14px",
                color: "#1E293B",
                background: "transparent",
                fontFamily: "'Plus Jakarta Sans', sans-serif",
                fontWeight: 500,
              }}
            />
            {query && (
              <button onClick={() => setQuery("")} style={{ background: "none", border: "none", cursor: "pointer", padding: "2px", flexShrink: 0, display: "flex" }}>
                <XIcon />
              </button>
            )}
          </div>

          {!query && (
            <div style={{ padding: "8px 12px 4px", fontFamily: "'JetBrains Mono', monospace", fontSize: "10px", fontWeight: 600, letterSpacing: "0.10em", textTransform: "uppercase", color: "#CBD5E1", flexShrink: 0 }}>
              Popular airports
            </div>
          )}

          <div style={{ overflowY: "auto", flex: 1 }}>
            {apiLoading && (
              <div style={{ padding: "14px", fontSize: "13px", color: "#94A3B8", textAlign: "center", fontFamily: "'JetBrains Mono', monospace" }}>Searching...</div>
            )}
            {!apiLoading && results.length === 0 && query && (
              <div style={{ padding: "14px", fontSize: "13px", color: "#94A3B8", textAlign: "center" }}>No airports found for "{query}"</div>
            )}
            {results.map((ap) => (
              <button
                key={ap.iata}
                type="button"
                onClick={() => select(ap)}
                style={{
                  width: "100%",
                  textAlign: "left",
                  padding: "10px 12px",
                  display: "flex",
                  alignItems: "center",
                  gap: "12px",
                  background: ap.iata === value ? "#F8FAFC" : "transparent",
                  border: "none",
                  borderBottom: "1px solid #F8FAFC",
                  cursor: "pointer",
                  fontFamily: "'Plus Jakarta Sans', sans-serif",
                  transition: "background 100ms",
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "#F8FAFC")}
                onMouseLeave={(e) => (e.currentTarget.style.background = ap.iata === value ? "#F8FAFC" : "transparent")}
              >
                <div style={{
                  width: "44px",
                  height: "32px",
                  background: ap.iata === value ? "#1E293B" : "#F1F5F9",
                  border: "1px solid #E2E8F0",
                  borderRadius: "6px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                }}>
                  <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "11px", fontWeight: 700, color: ap.iata === value ? "#fff" : "#E11D48", letterSpacing: "0.04em" }}>
                    {ap.iata}
                  </span>
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: "14px", fontWeight: 600, color: "#1E293B", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", letterSpacing: "-0.01em" }}>
                    {ap.city}
                  </div>
                  <div style={{ fontSize: "11px", color: "#94A3B8", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontFamily: "'JetBrains Mono', monospace" }}>
                    {ap.name}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main Search Form ─────────────────────────────────────────────────
export default function FlightSearchForm({ compact = false }: { compact?: boolean }) {
  const router = useRouter();
  const defaultDate = format(addDays(new Date(), 7), "yyyy-MM-dd");
  const tomorrow    = format(addDays(new Date(), 1), "yyyy-MM-dd");

  const [form, setForm] = useState({
    originIata:       "DEL",
    originDisplay:    "New Delhi (DEL)",
    destinationIata:  "BOM",
    destinationDisplay: "Mumbai (BOM)",
    departure_date: defaultDate,
    return_date:    "",
    adults:         1,
    cabin_class:    "ECONOMY",
    trip_type:      "ONE_WAY" as "ONE_WAY" | "ROUND_TRIP",
  });
  const [swapping, setSwapping] = useState(false);
  const [error, setError] = useState("");

  const swap = () => {
    setSwapping(true);
    setTimeout(() => setSwapping(false), 300);
    setForm((f) => ({
      ...f,
      originIata: f.destinationIata, originDisplay: f.destinationDisplay,
      destinationIata: f.originIata, destinationDisplay: f.originDisplay,
    }));
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!form.originIata || !form.destinationIata) {
      setError("Please select origin and destination airports.");
      return;
    }
    if (form.originIata === form.destinationIata) {
      setError("Origin and destination cannot be the same city.");
      return;
    }
    const p = new URLSearchParams({
      origin: form.originIata,
      destination: form.destinationIata,
      departure_date: form.departure_date,
      adults: String(form.adults),
      cabin_class: form.cabin_class,
      ...(form.return_date ? { return_date: form.return_date } : {}),
    });
    router.push(`/flights?${p}`);
  };

  return (
    <form onSubmit={submit}>
      {/* Trip type toggle */}
      <div className="trip-tabs">
        {(["One Way", "Round Trip"] as const).map((t) => (
          <button
            key={t}
            type="button"
            className={`trip-tab${form.trip_type === (t === "Round Trip" ? "ROUND_TRIP" : "ONE_WAY") ? " active" : ""}`}
            onClick={() => setForm((f) => ({
              ...f,
              trip_type: t === "Round Trip" ? "ROUND_TRIP" : "ONE_WAY",
              return_date: t === "One Way" ? "" : f.return_date,
            }))}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Origin / Swap / Destination */}
      <div className="form-grid-2" style={{ marginBottom: "16px" }}>
        <AirportField
          label="From"
          value={form.originIata}
          displayValue={form.originDisplay}
          onChange={(iata, display) => setForm((f) => ({ ...f, originIata: iata, originDisplay: display }))}
          placeholder="New Delhi (DEL)"
        />
        <div className="swap-col">
          <button
            type="button"
            className="swap-btn"
            onClick={swap}
            title="Swap airports"
            style={{ transform: swapping ? "rotate(180deg)" : "none", transition: "transform 0.3s ease" }}
          >
            <ArrowUpDown />
          </button>
        </div>
        <AirportField
          label="To"
          value={form.destinationIata}
          displayValue={form.destinationDisplay}
          onChange={(iata, display) => setForm((f) => ({ ...f, destinationIata: iata, destinationDisplay: display }))}
          placeholder="Mumbai (BOM)"
        />
      </div>

      {/* Date / Passengers / Class */}
      <div className="form-grid-4" style={{ marginBottom: "18px" }}>
        <div>
          <label className="field-label">Departure</label>
          <input
            type="date"
            className="inp"
            value={form.departure_date}
            min={tomorrow}
            required
            onChange={(e) => setForm((f) => ({ ...f, departure_date: e.target.value }))}
          />
        </div>
        <div>
          <label className="field-label">
            Return{" "}
            {form.trip_type === "ONE_WAY" && (
              <span style={{ color: "#CBD5E1", fontWeight: 400, fontSize: "9px" }}>optional</span>
            )}
          </label>
          <input
            type="date"
            className="inp"
            value={form.return_date}
            min={form.departure_date}
            onChange={(e) => setForm((f) => ({ ...f, return_date: e.target.value }))}
          />
        </div>
        <div>
          <label className="field-label">Passengers</label>
          <select
            className="inp"
            value={form.adults}
            onChange={(e) => setForm((f) => ({ ...f, adults: +e.target.value }))}
          >
            {[1, 2, 3, 4, 5, 6].map((n) => (
              <option key={n} value={n}>{n} {n === 1 ? "Adult" : "Adults"}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="field-label">Class</label>
          <select
            className="inp"
            value={form.cabin_class}
            onChange={(e) => setForm((f) => ({ ...f, cabin_class: e.target.value }))}
          >
            <option value="ECONOMY">Economy</option>
            <option value="PREMIUM_ECONOMY">Prem Economy</option>
            <option value="BUSINESS">Business</option>
            <option value="FIRST">First Class</option>
          </select>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div style={{
          padding: "10px 14px",
          background: "#FFF1F2",
          border: "1px solid rgba(225,29,72,0.2)",
          borderRadius: "8px",
          color: "#E11D48",
          fontSize: "13px",
          marginBottom: "12px",
          fontFamily: "'JetBrains Mono', monospace",
        }}>
          {error}
        </div>
      )}

      {/* Submit */}
      <button type="submit" className="search-submit">
        <SearchIcon />
        SEARCH FLIGHTS
      </button>
    </form>
  );
}
