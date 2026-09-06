"use client";

import React from "react";
import type { ForecastDay } from "@/types";
import { formatCurrency, formatDate } from "@/lib/formatters";

interface Props {
  forecast: ForecastDay[];
  currentFare?: number | null;
  recommendedHorizon?: number;
}

export default function ForecastTimeline({ forecast, currentFare, recommendedHorizon = 0 }: Props) {
  if (!forecast || forecast.length === 0) return null;

  return (
    <div
      className="ui-card"
      style={{
        padding: "24px",
        background: "var(--white)",
        borderRadius: "16px",
        border: "1px solid var(--grey1)",
        marginBottom: "24px"
      }}
    >
      <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--grey3)", letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: "16px" }}>
        Forecast Timeline
      </div>

      <div style={{ display: "flex", gap: "16px", overflowX: "auto", paddingBottom: "4px" }}>
        {forecast.map((point) => {
          const isRecommended = point.day === recommendedHorizon;
          const horizonLabel = point.day === 0 ? "Today" : point.day === 1 ? "1 Day Ahead" : `${point.day} Days Ahead`;

          return (
            <div
              key={point.day}
              style={{
                flex: "1 1 150px",
                minWidth: "150px",
                padding: "16px",
                background: isRecommended ? "rgba(22, 163, 74, 0.04)" : "var(--white)",
                border: isRecommended ? "2px solid #16a34a" : "1px solid var(--grey1)",
                borderRadius: "12px",
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between"
              }}
            >
              <div>
                <div style={{ fontSize: "12px", fontWeight: 600, color: isRecommended ? "#16a34a" : "var(--black)" }}>
                  {formatDate(point.date)}
                </div>
                <div style={{ fontSize: "11px", color: "var(--grey3)", marginTop: "2px" }}>
                  Forecast Period: {horizonLabel}
                </div>
              </div>

              <div style={{ marginTop: "16px" }}>
                <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--black)", fontFamily: "var(--fd)" }}>
                  {formatCurrency(point.price)}
                </div>
                <div style={{ fontSize: "10px", color: "var(--grey3)", marginTop: "4px" }}>
                  Range: {formatCurrency(point.lower)} – {formatCurrency(point.upper)}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
