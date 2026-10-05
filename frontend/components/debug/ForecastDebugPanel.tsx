"use client";

import React, { useState } from "react";
import type { CanonicalForecastDTO } from "@/types";

interface Props {
  rawResult: any;
  canonicalForecast?: CanonicalForecastDTO | null;
}

export default function ForecastDebugPanel({ rawResult, canonicalForecast }: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<"canonical" | "invariants" | "timeline" | "raw">("canonical");

  if (!rawResult) return null;

  const diagnostics = canonicalForecast?.diagnostics;
  const isPassed = diagnostics?.invariants_passed ?? true;
  const violations = diagnostics?.violations ?? [];

  return (
    <div style={{ marginTop: 24, border: "1px solid var(--grey2,#d8d6d2)", borderRadius: 12, background: "var(--surface-2)", overflow: "hidden" }}>
      <div 
        onClick={() => setIsOpen(!isOpen)}
        style={{ 
          padding: "12px 16px", 
          background: isPassed ? "var(--ok-bg)" : "var(--bad-bg)", 
          borderBottom: isOpen ? "1px solid var(--line)" : "none",
          display: "flex", 
          justifyContent: "space-between", 
          alignItems: "center", 
          cursor: "pointer" 
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: isPassed ? "var(--ok)" : "var(--bad)" }}>
            {isPassed ? "[PASS] Forecast Debug Diagnostics" : "[WARN] Invariant Violations Detected"}
          </span>
        </div>
        <button style={{ background: "none", border: "none", fontSize: 12, fontWeight: 600, color: "var(--ink-2)", cursor: "pointer" }}>
          {isOpen ? "Hide Audit Panel ▲" : "Show Audit Panel ▼"}
        </button>
      </div>

      {isOpen && (
        <div style={{ padding: 16 }}>
          {/* Tab Selection */}
          <div style={{ display: "flex", gap: 8, borderBottom: "1px solid var(--line)", paddingBottom: 8, marginBottom: 16 }}>
            <button 
              onClick={() => setActiveTab("canonical")}
              style={{ padding: "6px 12px", borderRadius: 6, border: "none", background: activeTab === "canonical" ? "var(--info)" : "var(--surface-2)", color: activeTab === "canonical" ? "#fff" : "var(--ink-2)", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
            >
              Canonical Forecast
            </button>
            <button 
              onClick={() => setActiveTab("invariants")}
              style={{ padding: "6px 12px", borderRadius: 6, border: "none", background: activeTab === "invariants" ? "var(--info)" : "var(--surface-2)", color: activeTab === "invariants" ? "#fff" : "var(--ink-2)", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
            >
              Invariants ({violations.length})
            </button>
            <button 
              onClick={() => setActiveTab("timeline")}
              style={{ padding: "6px 12px", borderRadius: 6, border: "none", background: activeTab === "timeline" ? "var(--info)" : "var(--surface-2)", color: activeTab === "timeline" ? "#fff" : "var(--ink-2)", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
            >
              Timeline Points ({canonicalForecast?.timeline?.length ?? 0})
            </button>
            <button 
              onClick={() => setActiveTab("raw")}
              style={{ padding: "6px 12px", borderRadius: 6, border: "none", background: activeTab === "raw" ? "var(--info)" : "var(--surface-2)", color: activeTab === "raw" ? "#fff" : "var(--ink-2)", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
            >
              Raw API Payload
            </button>
          </div>

          {/* Tab 1: Canonical Forecast */}
          {activeTab === "canonical" && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, fontSize: 12 }}>
              <div style={{ background: "var(--surface)", padding: 12, borderRadius: 8, border: "1px solid var(--line)" }}>
                <h4 style={{ margin: "0 0 8px 0", fontSize: 12, color: "var(--ink)" }}>Recommendation &amp; Savings</h4>
                <div><strong>Decision:</strong> {canonicalForecast?.recommendation_decision ?? "N/A"}</div>
                <div><strong>Optimal Horizon:</strong> Day {canonicalForecast?.optimal_booking_horizon ?? 0} ({canonicalForecast?.optimal_booking_date})</div>
                <div><strong>Expected Minimum Fare:</strong> ₹{canonicalForecast?.expected_minimum_fare ?? 0}</div>
                <div><strong>Calculated Savings:</strong> ₹{canonicalForecast?.calculated_savings ?? 0} ({canonicalForecast?.percentage_savings}%)</div>
              </div>

              <div style={{ background: "var(--surface)", padding: 12, borderRadius: 8, border: "1px solid var(--line)" }}>
                <h4 style={{ margin: "0 0 8px 0", fontSize: 12, color: "var(--ink)" }}>Confidence &amp; Quality</h4>
                <div><strong>Confidence Score:</strong> {canonicalForecast?.confidence_score ?? "null"}</div>
                <div><strong>Model Validation Score:</strong> {canonicalForecast?.confidence_breakdown?.model_validation_score ?? "null"}</div>
                <div><strong>Market Quality:</strong> {canonicalForecast?.confidence_breakdown?.market_data_quality ?? "null"}</div>
                <div><strong>Execution Latency:</strong> {diagnostics?.execution_time_ms ?? 0} ms</div>
              </div>
            </div>
          )}

          {/* Tab 2: Invariants */}
          {activeTab === "invariants" && (
            <div style={{ fontSize: 12 }}>
              {violations.length === 0 ? (
                <div style={{ color: "var(--ok)", padding: 12, background: "var(--ok-bg)", borderRadius: 8 }}>
                  ✓ All 4 mathematical forecast invariants satisfied cleanly!
                </div>
              ) : (
                <div style={{ color: "var(--bad)", padding: 12, background: "var(--bad-bg)", borderRadius: 8 }}>
                  <strong>Invariants Failed:</strong>
                  <ul style={{ margin: "8px 0 0 16px", padding: 0 }}>
                    {violations.map((v, i) => <li key={i}>{v}</li>)}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* Tab 3: Timeline */}
          {activeTab === "timeline" && (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", fontSize: 11, borderCollapse: "collapse", textAlign: "left" }}>
                <thead>
                  <tr style={{ background: "var(--surface-2)" }}>
                    <th style={{ padding: 6 }}>Horizon</th>
                    <th style={{ padding: 6 }}>Date</th>
                    <th style={{ padding: 6 }}>Predicted Fare</th>
                    <th style={{ padding: 6 }}>Lower Bound</th>
                    <th style={{ padding: 6 }}>Upper Bound</th>
                    <th style={{ padding: 6 }}>Optimal</th>
                  </tr>
                </thead>
                <tbody>
                  {canonicalForecast?.timeline?.map((pt, i) => (
                    <tr key={i} style={{ borderBottom: "1px solid var(--line)", background: pt.is_optimal ? "var(--ok-bg)" : "transparent" }}>
                      <td style={{ padding: 6 }}>Day {pt.horizon_days}</td>
                      <td style={{ padding: 6 }}>{pt.booking_date}</td>
                      <td style={{ padding: 6, fontWeight: 700 }}>₹{pt.predicted_price}</td>
                      <td style={{ padding: 6 }}>₹{pt.lower_bound}</td>
                      <td style={{ padding: 6 }}>₹{pt.upper_bound}</td>
                      <td style={{ padding: 6 }}>{pt.is_optimal ? "YES (MIN)" : "No"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Tab 4: Raw API Payload */}
          {activeTab === "raw" && (
            <pre style={{ background: "#1e293b", color: "#f8fafc", padding: 12, borderRadius: 8, fontSize: 11, maxHeight: 250, overflowY: "auto" }}>
              {JSON.stringify(rawResult, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
