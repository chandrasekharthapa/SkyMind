"use client";

import { useState, useEffect, useRef } from "react";

const UserIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
  </svg>
);

const ChevronDown = () => (
  <svg width="10" height="6" viewBox="0 0 10 6" fill="none">
    <path d="M1 1L5 5L9 1" stroke="#94A3B8" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

interface PassengerSelectorProps {
  adults: number;
  children: number;
  infants: number;
  onChange: (a: number, c: number, i: number) => void;
}

export default function PassengerSelector({ adults, children, infants, onChange }: PassengerSelectorProps) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const fn = (e: MouseEvent) => {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", fn);
    return () => document.removeEventListener("mousedown", fn);
  }, []);

  const total = adults + children + infants;
  const canAdd = total < 9;

  const update = (type: "a" | "c" | "i", inc: number) => {
    let nextA = adults, nextC = children, nextI = infants;
    if (type === "a") nextA = Math.max(1, Math.min(9, adults + inc));
    if (type === "c") nextC = Math.max(0, Math.min(9, children + inc));
    if (type === "i") nextI = Math.max(0, Math.min(nextA, infants + inc)); // Infant cannot exceed adults

    // Re-validate infant ratio if adults decreased
    if (nextI > nextA) nextI = nextA;
    
    // Total check
    if (nextA + nextC + nextI <= 9) {
      onChange(nextA, nextC, nextI);
    }
  };

  return (
    <div ref={wrap} style={{ position: "relative" }}>
      <label className="ui-field-label">Passengers</label>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="ui-input"
        style={{ display: "flex", alignItems: "center", gap: 12, textAlign: "left", cursor: "pointer" }}
      >
        <span style={{ color: "var(--red)" }}><UserIcon /></span>
        <div style={{ flex: 1, fontWeight: 600 }}>
          {adults} Adult{adults > 1 ? "s" : ""}
          {children > 0 ? `, ${children} Child${children > 1 ? "ren" : ""}` : ""}
          {infants > 0 ? `, ${infants} Infant${infants > 1 ? "s" : ""}` : ""}
        </div>
        <ChevronDown />
      </button>

      {open && (
        <div className="ui-card" style={{
          position: "absolute", top: "calc(100% + 8px)", right: 0, width: 280, zIndex: 600,
          padding: "var(--ui-space-lg)", animation: "fadeUp 0.2s ease"
        }}>
          {[
            { id: "a", label: "Adults", sub: "Ages 12+", val: adults, min: 1 },
            { id: "c", label: "Children", sub: "Ages 2-11", val: children, min: 0 },
            { id: "i", label: "Infants", sub: "Under 2 (on lap)", val: infants, min: 0 },
          ].map((row) => (
            <div key={row.id} className="ui-flex-between" style={{ marginBottom: row.id === "i" ? 0 : 20 }}>
              <div>
                <div style={{ fontSize: "14px", fontWeight: 700 }}>{row.label}</div>
                <div className="ui-label" style={{ fontSize: "10px" }}>{row.sub}</div>
              </div>
              <div className="ui-flex" style={{ gap: 16 }}>
                <button 
                  type="button" 
                  onClick={() => update(row.id as any, -1)}
                  disabled={row.val <= row.min}
                  style={{ width: 28, height: 28, borderRadius: "50%", border: "1px solid var(--grey2)", background: "var(--white)", cursor: row.val <= row.min ? "not-allowed" : "pointer", display: "flex", alignItems: "center", justifyContent: "center", opacity: row.val <= row.min ? 0.3 : 1 }}
                >
                  <svg width="12" height="2" viewBox="0 0 12 2" fill="none"><path d="M1 1h10" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/></svg>
                </button>
                <span style={{ fontSize: "15px", fontWeight: 700, minWidth: 12, textAlign: "center" }}>{row.val}</span>
                <button 
                  type="button" 
                  onClick={() => update(row.id as any, 1)}
                  disabled={!canAdd || (row.id === "i" && infants >= adults)}
                  style={{ width: 28, height: 28, borderRadius: "50%", border: "1px solid var(--grey2)", background: "var(--white)", cursor: (!canAdd || (row.id === "i" && infants >= adults)) ? "not-allowed" : "pointer", display: "flex", alignItems: "center", justifyContent: "center", opacity: (!canAdd || (row.id === "i" && infants >= adults)) ? 0.3 : 1 }}
                >
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M6 1v10M1 6h10" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/></svg>
                </button>
              </div>
            </div>
          ))}

          <div style={{ marginTop: 24, paddingTop: 16, borderTop: "1px solid var(--grey1)" }}>
             <button 
              type="button" 
              onClick={() => setOpen(false)}
              className="ui-btn ui-btn-red"
              style={{ width: "100%", height: 40 }}
             >
              Confirm
             </button>
          </div>
        </div>
      )}
    </div>
  );
}
