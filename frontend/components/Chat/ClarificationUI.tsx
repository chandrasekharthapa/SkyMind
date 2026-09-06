"use client";

import React from "react";
import { Calendar, MapPin, Plane, Users } from "lucide-react";

interface ClarificationUIProps {
  onSelect: (value: string) => void;
  type?: "date" | "airport" | "cabin" | "general";
}

export const ClarificationUI: React.FC<ClarificationUIProps> = ({ onSelect, type = "date" }) => {
  if (type === "date") {
    const dateOptions = [
      { label: "Tomorrow", value: "Find flights tomorrow" },
      { label: "In 3 Days", value: "Find flights in 3 days" },
      { label: "Next Weekend", value: "Find flights next weekend" },
    ];

    return (
      <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", margin: "8px 0" }}>
        {dateOptions.map((opt, i) => (
          <button
            key={i}
            onClick={() => onSelect(opt.value)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "4px",
              padding: "4px 10px",
              background: "#fff",
              border: "1px solid #cbd5e1",
              borderRadius: "16px",
              fontSize: "0.75rem",
              cursor: "pointer",
              color: "#334155",
              fontWeight: 500,
              transition: "all 0.15s ease"
            }}
          >
            <Calendar size={12} />
            <span>{opt.label}</span>
          </button>
        ))}
      </div>
    );
  }

  if (type === "airport") {
    const airportOptions = [
      { label: "Delhi (DEL)", value: "from DEL" },
      { label: "Mumbai (BOM)", value: "from BOM" },
      { label: "Bengaluru (BLR)", value: "from BLR" },
    ];

    return (
      <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", margin: "8px 0" }}>
        {airportOptions.map((opt, i) => (
          <button
            key={i}
            onClick={() => onSelect(opt.value)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "4px",
              padding: "4px 10px",
              background: "#fff",
              border: "1px solid #cbd5e1",
              borderRadius: "16px",
              fontSize: "0.75rem",
              cursor: "pointer",
              color: "#334155",
              fontWeight: 500
            }}
          >
            <MapPin size={12} />
            <span>{opt.label}</span>
          </button>
        ))}
      </div>
    );
  }

  return null;
};
