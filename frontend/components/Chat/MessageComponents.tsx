import React from "react";
import { Bot, User, AlertCircle, RefreshCw } from "lucide-react";
import AirlineLogo from "../flights/AirlineLogo";

// ─── Typing Message ──────────────────────────────────────────────────
export const TypingMessage: React.FC = () => (
  <div style={{ display: "flex", gap: "12px", alignSelf: "flex-start" }}>
    <div style={{ width: 28, height: 28, borderRadius: "50%", background: "var(--red-solid)", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center" }}>
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
// Renders the subset of Markdown the assistant writes: headings, tables, bullet
// and numbered lists, **bold** and `code`. It builds React elements, never an
// HTML string. The previous version pasted model output into
// dangerouslySetInnerHTML after a few regex replacements, so a reply containing
// "<img src=x onerror=...>" (a prompt-injected or echoed string) would have run
// in the page; it also showed tables and "###" headings as raw text.

const codeStyle: React.CSSProperties = {
  background: "rgba(0,0,0,0.03)", padding: "2px 6px", borderRadius: 4,
  fontFamily: "var(--fm)", fontSize: "0.75rem", border: "1px solid var(--grey1)",
};

function renderInline(text: string, keyPrefix: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = pattern.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const token = m[0];
    if (token.startsWith("**")) {
      out.push(<strong key={`${keyPrefix}-b${i++}`}>{token.slice(2, -2)}</strong>);
    } else {
      out.push(<code key={`${keyPrefix}-c${i++}`} style={codeStyle}>{token.slice(1, -1)}</code>);
    }
    last = m.index + token.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const isTableLine = (line: string) => {
  const t = line.trim();
  return t.startsWith("|") && t.endsWith("|") && t.length > 1;
};
const splitRow = (line: string) => line.trim().slice(1, -1).split("|").map((c) => c.trim());
const isDivider = (cells: string[]) => cells.every((c) => /^:?-{2,}:?$/.test(c));

export const MarkdownMessage: React.FC<{ content: string }> = ({ content }) => {
  const lines = (content || "").replace(/\r\n/g, "\n").split("\n");
  const blocks: React.ReactNode[] = [];
  let i = 0;
  let k = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed) { i++; continue; }

    // Table: consecutive |...| lines.
    if (isTableLine(line)) {
      const rows: string[][] = [];
      while (i < lines.length && isTableLine(lines[i])) {
        const cells = splitRow(lines[i]);
        if (!isDivider(cells)) rows.push(cells);
        i++;
      }
      const [head, ...body] = rows;
      blocks.push(
        <div key={`t${k++}`} style={{ overflowX: "auto", margin: "8px 0" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.75rem", border: "1px solid var(--grey1)" }}>
            {head && (
              <thead>
                <tr style={{ background: "rgba(0,0,0,0.03)" }}>
                  {head.map((c, ci) => (
                    <th key={ci} style={{ padding: "6px 8px", textAlign: "left", fontWeight: 700, borderBottom: "1px solid var(--grey1)", whiteSpace: "nowrap" }}>
                      {renderInline(c, `h${k}-${ci}`)}
                    </th>
                  ))}
                </tr>
              </thead>
            )}
            <tbody>
              {body.map((r, ri) => (
                <tr key={ri} style={{ borderBottom: "1px solid var(--grey1)" }}>
                  {r.map((c, ci) => (
                    <td key={ci} style={{ padding: "6px 8px", whiteSpace: "nowrap" }}>{renderInline(c, `r${k}-${ri}-${ci}`)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }

    // Heading: #, ## or ###.
    const h = trimmed.match(/^(#{1,6})\s+(.*)$/);
    if (h) {
      const size = h[1].length <= 2 ? "0.95rem" : "0.88rem";
      blocks.push(
        <div key={`h${k++}`} style={{ fontWeight: 700, fontSize: size, margin: "6px 0 4px" }}>
          {renderInline(h[2].replace(/:$/, ""), `hd${k}`)}
        </div>
      );
      i++;
      continue;
    }

    // Lists: "- item", "* item" or "1. item".
    const listItem = (l: string) => l.trim().match(/^(?:[-*•]|\d+[.)])\s+(.*)$/);
    if (listItem(line)) {
      const ordered = /^\d+[.)]/.test(trimmed);
      const items: string[] = [];
      while (i < lines.length && listItem(lines[i]) && /^\d+[.)]/.test(lines[i].trim()) === ordered) {
        items.push(listItem(lines[i])![1]);
        i++;
      }
      const ListTag = ordered ? "ol" : "ul";
      blocks.push(
        <ListTag key={`l${k++}`} style={{ margin: "4px 0", paddingLeft: 20, listStyleType: ordered ? "decimal" : "disc" }}>
          {items.map((it, ii) => <li key={ii} style={{ marginTop: 2 }}>{renderInline(it, `li${k}-${ii}`)}</li>)}
        </ListTag>
      );
      continue;
    }

    // Paragraph: lines up to the next blank line or block.
    const para: string[] = [];
    while (
      i < lines.length && lines[i].trim() && !isTableLine(lines[i]) &&
      !/^#{1,6}\s/.test(lines[i].trim()) && !listItem(lines[i])
    ) {
      para.push(lines[i].trim());
      i++;
    }
    blocks.push(
      <p key={`p${k++}`} style={{ margin: "4px 0" }}>
        {para.map((pl, pi) => (
          <React.Fragment key={pi}>
            {pi > 0 && <br />}
            {renderInline(pl, `p${k}-${pi}`)}
          </React.Fragment>
        ))}
      </p>
    );
  }

  return <div style={{ fontSize: "0.85rem", lineHeight: 1.5 }}>{blocks}</div>;
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
