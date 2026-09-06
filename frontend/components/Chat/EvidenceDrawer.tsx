"use client";

import React, { useState } from "react";
import { ChevronDown, ChevronUp, ShieldCheck, Clock, ExternalLink } from "lucide-react";

export interface EvidenceData {
  verificationStatus?: string;
  confidenceScore?: number;
  lastUpdated?: string;
  sourceCount?: number;
  sources?: string[];
  summaryText?: string;
}

interface EvidenceDrawerProps {
  evidence?: EvidenceData;
}

export const EvidenceDrawer: React.FC<EvidenceDrawerProps> = ({ evidence }) => {
  const [isOpen, setIsOpen] = useState(false);

  if (!evidence) return null;

  // Every field used to have a confident fallback: an absent confidenceScore
  // rendered as "98%", an absent status as "Verified Flight Intelligence", and
  // absent sources as ["Direct GDS Scraper", "ML Forecast Engine"] under the
  // heading "Provenanced Sources". So a caller that passed an empty object got
  // a verification badge and two citations, none of which existed. There is no
  // honest default for a provenance panel: with nothing to show, show nothing.
  const confidence =
    typeof evidence.confidenceScore === "number"
      ? Math.round(evidence.confidenceScore * 100)
      : null;
  const status = evidence.verificationStatus || null;
  const updated = evidence.lastUpdated || null;
  const sources = evidence.sources || [];

  if (!status && confidence == null && !updated && sources.length === 0) return null;

  return (
    <div
      className="evidence-drawer"
      style={{
        marginTop: "8px",
        border: "1px solid var(--grey1, #e2e8f0)",
        borderRadius: "8px",
        background: "#fafafa",
        fontSize: "0.78rem"
      }}
    >
      <button
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "6px 10px",
          background: "transparent",
          border: "none",
          cursor: "pointer",
          color: "var(--black, #0f172a)",
          fontWeight: 500
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <ShieldCheck size={14} style={{ color: "#16a34a" }} />
          <span>{status || "Sources"}</span>
          {confidence != null && (
            <span
              style={{
                background: "#dcfce7",
                color: "#15803d",
                padding: "2px 6px",
                borderRadius: "10px",
                fontSize: "0.7rem",
                fontWeight: 600
              }}
            >
              {confidence}% Confidence
            </span>
          )}
        </div>
        {isOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      {isOpen && (
        <div
          style={{
            padding: "8px 10px 10px",
            borderTop: "1px solid var(--grey1, #e2e8f0)",
            color: "#475569",
            display: "flex",
            flexDirection: "column",
            gap: "6px"
          }}
        >
          {updated && (
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <Clock size={12} />
              <span>Updated: {updated}</span>
            </div>
          )}

          {sources.length > 0 && (
            <div>
              <span style={{ fontWeight: 600 }}>Sources:</span>
              <ul style={{ margin: "4px 0 0 16px", padding: 0 }}>
                {sources.map((src, i) => (
                  <li key={i} style={{ listStyleType: "disc" }}>
                    {src}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
