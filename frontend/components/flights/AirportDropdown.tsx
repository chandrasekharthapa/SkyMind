"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { searchAirports } from "@/lib/api";
import type { AirportSuggestion } from "@/types";

const PlaneIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <path d="M17.8 19.2L16 11l3.5-3.5C21 6 21 4 19.5 2.5S18 2 16.5 3.5L13 7 4.8 6.2c-.5-.1-.9.1-1.1.5L2 8.9c-.2.4-.1.9.2 1.2l4.6 4.1-1.5 6.4 2.8 2.8 5.3-3.2 4.1 4.6c.3.4.8.5 1.2.2l1.1-1.2c.4-.2.6-.6.5-1.1z" />
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

interface AirportDropdownProps {
  label: string;
  value: string;
  displayValue: string;
  onChange: (iata: string, display: string) => void;
  placeholder: string;
}
export default function AirportDropdown({ label, value, displayValue, onChange, placeholder }: AirportDropdownProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<AirportSuggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [focusedIndex, setFocusedIndex] = useState(-1);

  useEffect(() => {
    const fn = (e: MouseEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", fn);
    return () => document.removeEventListener("mousedown", fn);
  }, []);

  const fetchResults = useCallback(async (q: string) => {
    if (q.length < 2) { setResults([]); return; }
    setLoading(true);
    try {
      const data = await searchAirports(q);
      setResults(data);
    } catch { setResults([]); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => fetchResults(query), 300);
    return () => clearTimeout(t);
  }, [query, fetchResults]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!open) return;
    if (e.key === "ArrowDown") {
      setFocusedIndex(i => (i + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      setFocusedIndex(i => (i - 1 + results.length) % results.length);
    } else if (e.key === "Enter" && focusedIndex >= 0) {
      select(results[focusedIndex]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  useEffect(() => {
    setFocusedIndex(-1);
  }, [results]);

  const select = (ap: AirportSuggestion) => {
    onChange(ap.iata, `${ap.city} (${ap.iata})`);
    setOpen(false);
    setQuery("");
  };

  return (
    <div ref={wrap} style={{ position: "relative", width: "100%" }}>
      <label className="ui-field-label">{label}</label>
      <button
        type="button"
        onClick={() => { setOpen(true); setTimeout(() => inputRef.current?.focus(), 50); }}
        className="ui-input"
        style={{ display: "flex", alignItems: "center", gap: 12, textAlign: "left", cursor: "pointer", border: open ? "2px solid var(--red)" : "1px solid var(--grey2)" }}
      >
        <span style={{ color: "var(--red)" }}><PlaneIcon /></span>
        <div style={{ flex: 1, minWidth: 0 }}>
          {displayValue ? (
            <div style={{ fontWeight: 700, color: "var(--black)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {displayValue}
            </div>
          ) : (
            <div style={{ color: "var(--grey3)" }}>{placeholder}</div>
          )}
        </div>
        <ChevronDown />
      </button>

      {open && (
        <div className="ui-card" style={{
          position: "absolute", top: "calc(100% + 8px)", left: 0, right: 0, zIndex: 600,
          padding: 0, overflow: "hidden", animation: "fadeUp 0.2s ease"
        }}>
          <div style={{ padding: "12px", background: "var(--off)", borderBottom: "1px solid var(--grey1)", display: "flex", alignItems: "center", gap: 12 }}>
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type city or airport code..."
              style={{ width: "100%", border: "none", outline: "none", background: "transparent", fontSize: "14px", fontFamily: "var(--fm)" }}
            />
            {query && (
              <button 
                onClick={() => setQuery("")} 
                style={{ background: "none", border: "none", cursor: "pointer", display: "flex" }}
              >
                <XIcon />
              </button>
            )}
          </div>
          
          <div style={{ maxHeight: 300, overflowY: "auto" }}>
            {loading && (
              <div style={{ padding: 32, textAlign: "center" }}>
                <div className="status-dot" style={{ margin: "0 auto 12px", animation: "blink 1s infinite" }} />
                <div className="ui-label">Scanning database...</div>
              </div>
            )}
            
            {!loading && results.map((ap, idx) => (
              <div
                key={ap.iata}
                onClick={() => select(ap)}
                onMouseEnter={() => setFocusedIndex(idx)}
                style={{
                  padding: "12px 16px", cursor: "pointer", borderBottom: "1px solid var(--grey1)",
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  background: focusedIndex === idx ? "var(--off)" : "transparent",
                  transition: "background 0.15s"
                }}
              >
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: "14px", fontWeight: 700, color: "var(--black)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{ap.city}</div>
                  <div className="ui-label" style={{ fontSize: "11px", color: "var(--grey3)" }}>{ap.name}</div>
                </div>
                <div style={{ fontSize: "12px", fontWeight: 800, fontFamily: "var(--fm)", color: "var(--red)", background: "var(--red-mist)", padding: "4px 8px", borderRadius: 4, marginLeft: 12 }}>
                  {ap.iata}
                </div>
              </div>
            ))}
            
            {!loading && query.length >= 2 && results.length === 0 && (
              <div style={{ padding: 32, textAlign: "center", color: "var(--grey3)", fontSize: "13px" }}>
                No airports found for "{query}"
              </div>
            )}
            
            {query.length < 2 && !loading && (
              <div style={{ padding: 24, textAlign: "center", color: "var(--grey3)", fontSize: "12px" }}>
                Enter at least 2 characters to search
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
