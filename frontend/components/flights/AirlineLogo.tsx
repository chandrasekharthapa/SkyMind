"use client";

import { useState } from "react";

// ─── Air India official color palette ────────────────────────────────
const AIRLINE_COLORS: Record<string, { bg: string; text: string; accent?: string }> = {
  AI:   { bg: "#E11D48", text: "#fff" },      // Air India — brand red
  "6E": { bg: "#1B2F6E", text: "#fff" },      // IndiGo — navy
  SG:   { bg: "#FF0000", text: "#fff" },      // SpiceJet
  UK:   { bg: "#4A235A", text: "#fff" },      // Vistara (now Air India)
  IX:   { bg: "#C8102E", text: "#fff" },      // Air India Express
  QP:   { bg: "#E85D04", text: "#fff" },      // Akasa Air
  S5:   { bg: "#002868", text: "#fff" },      // Star Air
  EK:   { bg: "#D4A017", text: "#000" },      // Emirates
  SQ:   { bg: "#003B5C", text: "#fff" },      // Singapore Airlines
  QR:   { bg: "#5C0632", text: "#fff" },      // Qatar Airways
  EY:   { bg: "#BD8B13", text: "#fff" },      // Etihad
  BA:   { bg: "#075AAA", text: "#fff" },      // British Airways
  TK:   { bg: "#C8102E", text: "#fff" },      // Turkish
  FZ:   { bg: "#E42C2E", text: "#fff" },      // flydubai
  G9:   { bg: "#E52628", text: "#fff" },      // Air Arabia
};

const AIRLINE_DOMAINS: Record<string, string> = {
  AI:   "airindia.com",
  "6E": "goindigo.in",
  SG:   "spicejet.com",
  UK:   "airvistara.com",
  IX:   "airindiaexpress.in",
  QP:   "akasaair.com",
  EK:   "emirates.com",
  SQ:   "singaporeair.com",
  QR:   "qatarairways.com",
  EY:   "etihad.com",
  BA:   "britishairways.com",
  TK:   "turkishairlines.com",
  FZ:   "flydubai.com",
  G9:   "airarabia.com",
};

function getLogoSources(iata: string): string[] {
  const code = iata.toUpperCase();
  const sources: string[] = [];
  sources.push(`https://content.airhex.com/content/logos/airlines_${code}_200_200_s.png`);
  const domain = AIRLINE_DOMAINS[code];
  if (domain) {
    sources.push(`https://img.logo.dev/${domain}?token=pk_X3FZt3VfT4ShbQi5lJ91nw&format=png&size=48`);
    sources.push(`https://logo.clearbit.com/${domain}`);
  }
  return sources;
}

interface AirlineLogoProps {
  code: string;
  name: string;
  size?: number;
  className?: string;
}

/**
 * AirlineLogo — renders airline logo with graceful fallback.
 * For Air India (AI), uses brand-red background with "AI" monogram.
 * All logos display with consistent sizing on the 8px grid.
 */
export default function AirlineLogo({ code, name, size = 42, className }: AirlineLogoProps) {
  const iata = code.toUpperCase();
  const sources = getLogoSources(iata);
  const [srcIndex, setSrcIndex] = useState(0);
  const [failed, setFailed] = useState(false);
  const colors = AIRLINE_COLORS[iata] || { bg: "#1E293B", text: "#fff" };

  const boxStyle: React.CSSProperties = {
    width: `${size}px`,
    height: `${size}px`,
    flexShrink: 0,
    border: "1px solid #E2E8F0",
    overflow: "hidden",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: "8px",
  };

  const handleError = () => {
    const next = srcIndex + 1;
    if (next < sources.length) setSrcIndex(next);
    else setFailed(true);
  };

  // Fallback: branded monogram
  if (failed) {
    return (
      <div
        style={{ ...boxStyle, background: colors.bg, border: `1px solid ${colors.bg}` }}
        className={className}
        title={name}
      >
        <span style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: size > 38 ? "11px" : "9px",
          fontWeight: 800,
          color: colors.text,
          letterSpacing: "0.02em",
          textAlign: "center",
          userSelect: "none",
        }}>
          {iata.length <= 2 ? iata : iata.slice(0, 2)}
        </span>
      </div>
    );
  }

  return (
    <div
      style={{ ...boxStyle, background: "#F8FAFC", padding: "3px" }}
      className={className}
      title={name}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={sources[srcIndex]}
        alt={name}
        style={{ width: "100%", height: "100%", objectFit: "contain" }}
        onError={handleError}
        loading="lazy"
      />
    </div>
  );
}

export function AirlineLogoBanner({ code, name, height = 28 }: { code: string; name: string; height?: number }) {
  const iata = code.toUpperCase();
  const [failed, setFailed] = useState(false);
  const colors = AIRLINE_COLORS[iata] || { bg: "#1E293B", text: "#fff" };
  const src = `https://content.airhex.com/content/logos/airlines_${iata}_100_25_r.png`;

  if (failed) {
    return (
      <div style={{ height: `${height}px`, padding: "0 10px", background: colors.bg, display: "inline-flex", alignItems: "center", borderRadius: "4px" }}>
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "10px", fontWeight: 800, color: colors.text, letterSpacing: "0.06em" }}>
          {name.slice(0, 12)}
        </span>
      </div>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt={name}
      height={height}
      style={{ objectFit: "contain" }}
      onError={() => setFailed(true)}
      loading="lazy"
    />
  );
}
