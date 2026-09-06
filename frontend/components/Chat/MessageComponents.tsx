import React from "react";
import { Bot, User, AlertCircle, RefreshCw } from "lucide-react";
import AirlineLogo from "../flights/AirlineLogo";

// ─── Typing Message ──────────────────────────────────────────────────
export const TypingMessage: React.FC = () => (
  <div style={{ display: "flex", gap: "12px", alignSelf: "flex-start" }}>
    <div style={{ width: 28, height: 28, borderRadius: "50%", background: "var(--red)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <Bot size={14} />
    </div>
    <div style={{ background: "var(--white)", border: "1px solid var(--grey1)", borderRadius: "12px", padding: "10px 14px", display: "flex", alignItems: "center", gap: 4 }}>
      <span className="dot pulse" style={{ width: 6, height: 6, background: "var(--grey3)", borderRadius: "50%" }}></span>
      <span className="dot pulse" style={{ width: 6, height: 6, background: "var(--grey3)", borderRadius: "50%", animationDelay: "0.2s" }}></span>
      <span className="dot pulse" style={{ width: 6, height: 6, background: "var(--grey3)", borderRadius: "50%", animationDelay: "0.4s" }}></span>
    </div>
  </div>
);

// ─── Markdown Message ────────────────────────────────────────────────
export const MarkdownMessage: React.FC<{ content: string }> = ({ content }) => {
  let html = content;
  // Bold
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code style="background:rgba(0,0,0,0.03);padding:2px 6px;border-radius:4px;font-family:var(--fm);font-size:0.75rem;border:1px solid var(--grey1)">$1</code>');
  // Lists
  html = html.replace(/^\s*[-*]\s+(.+)$/gm, '<li style="margin-left:16px;list-style-type:disc;font-size:0.8rem;margin-top:4px">$1</li>');
  // Newlines
  html = html.replace(/\n/g, "<br/>");
  
  return <div dangerouslySetInnerHTML={{ __html: html }} style={{ fontSize: "0.85rem", lineHeight: "1.5" }} />;
};

// ─── Table Message ───────────────────────────────────────────────────
export const TableMessage: React.FC<{ content: string }> = ({ content }) => {
  const lines = content.split('\n');
  const rows: string[][] = [];
  
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      const cells = trimmed.split('|').map(c => c.trim()).filter((_, idx, arr) => idx > 0 && idx < arr.length - 1);
      if (cells.every(c => /^[-:]+$/.test(c))) continue; // skip dividers
      rows.push(cells);
    }
  }

  if (rows.length === 0) return null;

  return (
    <div style={{ overflowX: "auto", margin: "12px 0" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.75rem", border: "1px solid var(--grey1)" }}>
        <tbody>
          {rows.map((row, rIdx) => {
            const isHeader = rIdx === 0;
            return (
              <tr key={rIdx} style={{ borderBottom: "1px solid var(--grey1)", background: isHeader ? "rgba(0,0,0,0.02)" : "transparent" }}>
                {row.map((cell, cIdx) => (
                  <td key={cIdx} style={{ padding: "8px", borderRight: "1px solid var(--grey1)", fontWeight: isHeader ? "700" : "500" }}>
                    {cell}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

// ─── Flight Card ─────────────────────────────────────────────────────
export interface FlightCardProps {
  airlineCode: string;
  airlineName: string;
  flightNumber: string;
  departure: string;
  arrival: string;
  duration: string;
  price: number;
}
export const FlightCard: React.FC<FlightCardProps> = ({
  airlineCode,
  airlineName,
  flightNumber,
  departure,
  arrival,
  duration,
  price
}) => (
  <div className="ui-card" style={{ padding: 16, background: "var(--white)", border: "1px solid var(--grey1)", borderRadius: 12, display: "flex", flexDirection: "column", gap: 12, margin: "8px 0" }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <div style={{ width: 24, height: 24 }}><AirlineLogo code={airlineCode} name={airlineName} /></div>
        <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>{airlineName} ({flightNumber})</span>
      </div>
      <span style={{ fontFamily: "var(--fd)", fontWeight: 700, fontSize: "1.1rem", color: "var(--red)" }}>
        ₹{Math.round(price).toLocaleString("en-IN")}
      </span>
    </div>
    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem", color: "var(--grey4)" }}>
      <div><strong>DEP:</strong> {departure}</div>
      <div><strong>DUR:</strong> {duration}</div>
      <div><strong>ARR:</strong> {arrival}</div>
    </div>
  </div>
);

// ─── Prediction Card ─────────────────────────────────────────────────
export interface PredictionCardProps {
  predictedPrice: number;
  currentPrice: number;
  expectedChange: string;
  confidence: number;
}
export const PredictionCard: React.FC<PredictionCardProps> = ({
  predictedPrice,
  currentPrice,
  expectedChange,
  confidence
}) => (
  <div className="ui-card" style={{ padding: 16, background: "var(--white)", border: "1px solid var(--grey1)", borderRadius: 12, margin: "8px 0" }}>
    <div style={{ fontFamily: "var(--fb)", fontSize: "9px", fontWeight: 700, color: "var(--red)", textTransform: "uppercase", marginBottom: 8 }}>
      XGBoost price Prediction
    </div>
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, fontSize: "0.8rem" }}>
      <div><span style={{ color: "var(--grey3)" }}>Predicted Price:</span> <strong style={{ color: "var(--black)" }}>₹{Math.round(predictedPrice).toLocaleString("en-IN")}</strong></div>
      <div><span style={{ color: "var(--grey3)" }}>Current Price:</span> <strong style={{ color: "var(--grey4)" }}>₹{Math.round(currentPrice).toLocaleString("en-IN")}</strong></div>
      <div><span style={{ color: "var(--grey3)" }}>Expected Change:</span> <strong style={{ color: expectedChange.includes("-") ? "var(--green)" : "var(--red)" }}>{expectedChange}</strong></div>
      <div><span style={{ color: "var(--grey3)" }}>Confidence:</span> <strong style={{ color: "var(--black)" }}>{Math.round(confidence * 100)}%</strong></div>
    </div>
  </div>
);

// ─── Recommendation Card ─────────────────────────────────────────────
export interface RecommendationCardProps {
  decision: string;
  reasons: string[];
}
export const RecommendationCard: React.FC<RecommendationCardProps> = ({ decision, reasons }) => (
  <div className="ui-card" style={{ padding: 16, background: "var(--white)", border: "1px solid var(--grey1)", borderRadius: 12, margin: "8px 0" }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
      <span style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--grey4)" }}>Booking Strategy</span>
      <span className="ui-badge badge-red" style={{ fontSize: "9px", fontWeight: 700 }}>{decision}</span>
    </div>
    <ul style={{ margin: 0, paddingLeft: 16, fontSize: "0.75rem", color: "var(--grey3)" }}>
      {reasons.map((r, i) => <li key={i} style={{ marginTop: 4 }}>{r}</li>)}
    </ul>
  </div>
);

// ─── Validation Card ─────────────────────────────────────────────────
export interface ValidationCardProps {
  overallStatus: string;
  readinessScore: number;
  timestamp: string;
}
export const ValidationCard: React.FC<ValidationCardProps> = ({ overallStatus, readinessScore, timestamp }) => (
  <div className="ui-card" style={{ padding: 16, background: "var(--white)", border: "1px solid var(--grey1)", borderRadius: 12, margin: "8px 0", display: "flex", gap: 16, alignItems: "center" }}>
    <RefreshCw size={24} style={{ color: "var(--red)" }} />
    <div>
      <div style={{ fontSize: "0.85rem", fontWeight: 700 }}>Model Validation Audit</div>
      <div style={{ fontSize: "0.75rem", color: "var(--grey3)", marginTop: 2 }}>
        Status: <strong style={{ color: overallStatus === "PASS" ? "var(--green)" : "var(--red)" }}>{overallStatus}</strong> | Score: <strong>{readinessScore}%</strong>
      </div>
      <div style={{ fontSize: "9px", color: "var(--grey3)", marginTop: 2 }}>{new Date(timestamp).toLocaleString("en-IN")}</div>
    </div>
  </div>
);

// ─── System Card ─────────────────────────────────────────────────────
export interface SystemCardProps {
  backendVersion: string;
  model_version: string;
  featureSetVersion: string;
}
export const SystemCard: React.FC<SystemCardProps> = ({ backendVersion, model_version, featureSetVersion }) => (
  <div className="ui-card" style={{ padding: 16, background: "var(--white)", border: "1px solid var(--grey1)", borderRadius: 12, margin: "8px 0" }}>
    <div style={{ fontSize: "0.85rem", fontWeight: 700, marginBottom: 8 }}>SkyMind Specs</div>
    <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: "0.75rem", color: "var(--grey4)" }}>
      <div><span style={{ color: "var(--grey3)" }}>Backend Version:</span> {backendVersion}</div>
      <div><span style={{ color: "var(--grey3)" }}>Model Version:</span> {model_version}</div>
      <div><span style={{ color: "var(--grey3)" }}>Feature Schema:</span> {featureSetVersion}</div>
    </div>
  </div>
);

// ─── Error Card ──────────────────────────────────────────────────────
export interface ErrorCardProps {
  code: string;
  message: string;
}
export const ErrorCard: React.FC<ErrorCardProps> = ({ code, message }) => (
  <div className="ui-card" style={{ padding: 16, background: "rgba(220, 38, 38, 0.02)", border: "1px solid rgba(220, 38, 38, 0.15)", borderRadius: 12, margin: "8px 0", display: "flex", gap: 12, alignItems: "center" }}>
    <AlertCircle size={20} style={{ color: "var(--red)", flexShrink: 0 }} />
    <div>
      <div style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--red)" }}>{code}</div>
      <div style={{ fontSize: "0.75rem", color: "var(--black)", marginTop: 2 }}>{message}</div>
    </div>
  </div>
);

// ─── Chart Message ───────────────────────────────────────────────────
export const ChartMessage: React.FC<{ label: string; value: number }> = ({ label, value }) => (
  <div style={{ margin: "12px 0" }}>
    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", color: "var(--grey4)", marginBottom: 4 }}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
    <div style={{ height: 8, background: "var(--grey1)", borderRadius: 4, overflow: "hidden" }}>
      <div style={{ height: "100%", width: `${Math.min(100, value)}%`, background: "var(--red)", borderRadius: 4 }} />
    </div>
  </div>
);
