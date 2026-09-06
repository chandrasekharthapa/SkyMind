"use client";

import React from "react";
import type { PredictionResult } from "@/types";
import { formatCurrency, formatConfidenceString, formatDate } from "@/lib/formatters";

interface Props {
  result: PredictionResult;
}

export default function DecisionCard({ result }: Props) {
  if (!result) return null;

  const { recommendation, current_market, predicted_price, forecast, confidence, optimal_booking } = result;

  // Use backend optimal_booking if available
  const optBooking = optimal_booking || {
    booking_date: forecast?.[0]?.date || new Date().toISOString(),
    prediction_horizon: 0,
    expected_price: predicted_price,
    estimated_savings: 0,
    percentage_savings: 0.0,
    recommendation: "BUY NOW"
  };

  const horizon = optBooking.prediction_horizon;
  const lowestFare = current_market?.lowest_fare;

  let recTitle = "BUY NOW";
  if (horizon > 0) {
    recTitle = `WAIT ${horizon} DAY${horizon > 1 ? "S" : ""}`;
  }

  // Supporting explanation from backend decision object
  const explanation = recommendation?.reasons?.[0] || 
    (horizon === 0 
      ? "Today's expected fare matches the lowest predicted fare across all forecast horizons. Waiting is not expected to produce additional savings."
      : `The forecast indicates the lowest expected fare occurs in approximately ${horizon} day(s).`);

  const estimatedSavings = optBooking.estimated_savings || (lowestFare != null && lowestFare > optBooking.expected_price ? Math.round(lowestFare - optBooking.expected_price) : 0);
  const pctSavings = optBooking.percentage_savings || (lowestFare != null && lowestFare > 0 ? Number(((estimatedSavings / lowestFare) * 100).toFixed(1)) : 0.0);
  const savingsText = estimatedSavings > 0 ? `${formatCurrency(estimatedSavings)} (${pctSavings}%)` : "₹0 (0.0%)";

  const riskLevel = horizon === 0 ? "Low" : "Low";

  return (
    <div
      className="ui-card"
      style={{
        padding: "24px",
        background: "var(--white)",
        border: "1px solid var(--grey1)",
        borderRadius: "16px",
        marginBottom: "24px"
      }}
    >
      {/* Recommendation Header */}
      <div style={{ marginBottom: "16px" }}>
        <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--grey3)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "4px" }}>
          Recommendation
        </div>
        <div style={{ fontFamily: "var(--fd)", fontSize: "1.75rem", color: "var(--black)", fontWeight: 700, letterSpacing: "-0.01em" }}>
          {recTitle}
        </div>
        <p style={{ fontSize: "0.875rem", color: "var(--grey4)", marginTop: "8px", marginBottom: 0, lineHeight: 1.5 }}>
          {explanation}
        </p>
      </div>

      <hr style={{ border: "none", borderTop: "1px solid var(--grey1)", margin: "20px 0" }} />

      {/* Structured Metrics Grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
          gap: "20px"
        }}
      >
        <div>
          <div style={{ fontSize: "11px", color: "var(--grey3)", fontWeight: 500, marginBottom: "4px" }}>
            Recommended Booking Date
          </div>
          <div style={{ fontSize: "1.1rem", fontWeight: 600, color: "var(--black)" }}>
            {formatDate(optBooking.booking_date)}
          </div>
        </div>

        <div>
          <div style={{ fontSize: "11px", color: "var(--grey3)", fontWeight: 500, marginBottom: "4px" }}>
            Expected Fare
          </div>
          <div style={{ fontSize: "1.1rem", fontWeight: 600, color: "var(--black)" }}>
            {formatCurrency(optBooking.expected_price)}
          </div>
        </div>

        <div>
          <div style={{ fontSize: "11px", color: "var(--grey3)", fontWeight: 500, marginBottom: "4px" }}>
            Potential Savings
          </div>
          <div style={{ fontSize: "1.1rem", fontWeight: 600, color: estimatedSavings > 0 ? "#16a34a" : "var(--black)" }}>
            {savingsText}
          </div>
        </div>

        <div>
          <div style={{ fontSize: "11px", color: "var(--grey3)", fontWeight: 500, marginBottom: "4px" }}>
            Risk
          </div>
          <div style={{ fontSize: "1.1rem", fontWeight: 600, color: "var(--black)" }}>
            {riskLevel}
          </div>
        </div>

        <div>
          <div style={{ fontSize: "11px", color: "var(--grey3)", fontWeight: 500, marginBottom: "4px" }}>
            Forecast Confidence
          </div>
          <div style={{ fontSize: "1.1rem", fontWeight: 600, color: "var(--black)" }}>
            {formatConfidenceString(confidence)}
          </div>
        </div>
      </div>
    </div>
  );
}
