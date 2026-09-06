"use client";

import React, { useState } from "react";
import type { PredictionResult } from "@/types";
import { formatCurrency, formatDate } from "@/lib/formatters";

interface MarketSignalsProps {
  result: PredictionResult;
  devMetrics?: any;
}

export default function MarketSignals({ result, devMetrics }: MarketSignalsProps) {
  const [showDevMode, setShowDevMode] = useState(false);

  if (!result) return null;

  const { search_metadata, recommendation } = result;

  // Only the reasons the backend actually returned. The previous fallback
  // invented three model-sounding factors ("Live market volatility indicates
  // stable price trajectory.") and showed them under the same heading as real
  // ones, so an empty response was indistinguishable from a reasoned decision.
  const factors: string[] = recommendation?.reasons || [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "24px", marginBottom: "24px" }}>
      {/* Explanation ("Why this recommendation?") */}
      <div
        className="ui-card"
        style={{
          padding: "24px",
          background: "var(--white)",
          border: "1px solid var(--grey1)",
          borderRadius: "16px"
        }}
      >
        <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--grey3)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "16px" }}>
          Recommendation Factors
        </div>

        <ul style={{ paddingLeft: "18px", margin: 0, display: "flex", flexDirection: "column", gap: "8px" }}>
          {factors.length === 0 ? (
            <li style={{ fontSize: "0.875rem", color: "var(--grey3)", lineHeight: 1.5 }}>
              No factors were returned for this recommendation.
            </li>
          ) : (
            factors.map((factor, idx) => (
              <li key={idx} style={{ fontSize: "0.875rem", color: "var(--black)", lineHeight: 1.5 }}>
                {factor.replace(/^✓\s*/, "")}
              </li>
            ))
          )}
        </ul>
      </div>

      {/* Market Information Panel (User-Facing) */}
      <div
        className="ui-card"
        style={{
          padding: "24px",
          background: "var(--white)",
          border: "1px solid var(--grey1)",
          borderRadius: "16px",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
          gap: "20px"
        }}
      >
        <div>
          <div style={{ fontSize: "11px", color: "var(--grey3)", fontWeight: 500, marginBottom: "4px" }}>Historical Accuracy</div>
          <div style={{ fontFamily: "var(--fd)", fontSize: "1.25rem", color: "var(--black)", fontWeight: 700 }}>
            {devMetrics?.mape != null ? `${(100 - devMetrics.mape).toFixed(1)}%` : "—"}
          </div>
          <div style={{ fontSize: "10px", color: "var(--grey3)", marginTop: "2px" }}>
            {devMetrics?.mape != null ? "100 − MAPE, as reported by the model" : "Not reported by the model"}
          </div>
        </div>

        <div>
          <div style={{ fontSize: "11px", color: "var(--grey3)", fontWeight: 500, marginBottom: "4px" }}>Model Last Updated</div>
          <div style={{ fontFamily: "var(--fd)", fontSize: "1.25rem", color: "var(--black)", fontWeight: 700 }}>
            {devMetrics?.training_date ? formatDate(devMetrics.training_date) : "—"}
          </div>
          <div style={{ fontSize: "10px", color: "var(--grey3)", marginTop: "2px" }}>Chronological Retraining</div>
        </div>

        <div>
          <div style={{ fontSize: "11px", color: "var(--grey3)", fontWeight: 500, marginBottom: "4px" }}>Market Freshness</div>
          <div style={{ fontFamily: "var(--fd)", fontSize: "1.25rem", color: "var(--black)", fontWeight: 700 }}>
            {search_metadata?.snapshot_age != null ? `${search_metadata.snapshot_age.toFixed(0)}s ago` : "—"}
          </div>
          <div style={{ fontSize: "10px", color: "var(--grey3)", marginTop: "2px" }}>
            {search_metadata?.cache_hit ? "Served from Cache" : "Not served from cache"}
          </div>
        </div>

        <div>
          <div style={{ fontSize: "11px", color: "var(--grey3)", fontWeight: 500, marginBottom: "4px" }}>Data Provider</div>
          <div style={{ fontFamily: "var(--fd)", fontSize: "1.1rem", color: "var(--black)", fontWeight: 600, textOverflow: "ellipsis", overflow: "hidden", whiteSpace: "nowrap" }}>
            {search_metadata?.provider || "—"}
          </div>
          <div style={{ fontSize: "10px", color: "var(--grey3)", marginTop: "2px" }}>MCP Ingestion</div>
        </div>
      </div>

      {/* Developer Diagnostics Toggle */}
      <div style={{ textAlign: "right" }}>
        <button
          type="button"
          onClick={() => setShowDevMode(!showDevMode)}
          style={{
            background: "none",
            border: "none",
            color: "var(--grey3)",
            fontSize: "11px",
            fontFamily: "var(--fm)",
            cursor: "pointer",
            textDecoration: "underline"
          }}
        >
          {showDevMode ? "Hide Developer Diagnostics" : "Developer Diagnostics"}
        </button>

        {showDevMode && (
          <div
            className="ui-card"
            style={{
              marginTop: "16px",
              padding: "24px",
              background: "rgba(0,0,0,0.01)",
              border: "1px solid var(--grey1)",
              borderRadius: "16px",
              textAlign: "left",
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
              gap: "20px"
            }}
          >
            <div>
              <div style={{ fontSize: "10px", fontWeight: 600, color: "var(--grey3)", textTransform: "uppercase", marginBottom: "4px" }}>MAE</div>
              <div style={{ fontFamily: "var(--fd)", fontSize: "1.25rem", color: "var(--black)" }}>
                {devMetrics?.mae != null ? `₹${Math.round(devMetrics.mae)}` : "—"}
              </div>
            </div>
            <div>
              <div style={{ fontSize: "10px", fontWeight: 600, color: "var(--grey3)", textTransform: "uppercase", marginBottom: "4px" }}>RMSE</div>
              <div style={{ fontFamily: "var(--fd)", fontSize: "1.25rem", color: "var(--black)" }}>
                {devMetrics?.rmse != null ? `₹${Math.round(devMetrics.rmse)}` : "—"}
              </div>
            </div>
            <div>
              <div style={{ fontSize: "10px", fontWeight: 600, color: "var(--grey3)", textTransform: "uppercase", marginBottom: "4px" }}>R² Score</div>
              <div style={{ fontFamily: "var(--fd)", fontSize: "1.25rem", color: "var(--black)" }}>
                {devMetrics?.r2 != null ? devMetrics.r2.toFixed(3) : "—"}
              </div>
            </div>
            <div>
              <div style={{ fontSize: "10px", fontWeight: 600, color: "var(--grey3)", textTransform: "uppercase", marginBottom: "4px" }}>Training Rows</div>
              <div style={{ fontFamily: "var(--fd)", fontSize: "1.25rem", color: "var(--black)" }}>
                {devMetrics?.training_samples != null ? Number(devMetrics.training_samples).toLocaleString() : "—"}
              </div>
            </div>
            <div>
              <div style={{ fontSize: "10px", fontWeight: 600, color: "var(--grey3)", textTransform: "uppercase", marginBottom: "4px" }}>Model</div>
              <div style={{ fontFamily: "var(--fd)", fontSize: "1.1rem", color: "var(--black)" }}>
                {devMetrics?.model_name || "—"}
              </div>
            </div>
            <div>
              <div style={{ fontSize: "10px", fontWeight: 600, color: "var(--grey3)", textTransform: "uppercase", marginBottom: "4px" }}>Feature Set</div>
              <div style={{ fontFamily: "var(--fd)", fontSize: "1.1rem", color: "var(--black)" }}>
                {devMetrics?.feature_set_version || "—"}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
