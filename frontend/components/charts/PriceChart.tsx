"use client";

import React, { useMemo } from "react";
import type { ForecastPoint, Trend } from "@/types";

const TREND_COLOURS: Record<Trend, { line: string; fill: string; dash: string }> = {
  RISING:  { line: "#e8191a", fill: "rgba(232,25,26,0.08)",  dash: "rgba(232,25,26,0.30)" },
  FALLING: { line: "#166534", fill: "rgba(22,101,52,0.08)",  dash: "rgba(22,101,52,0.30)" },
  STABLE:  { line: "#2563eb", fill: "rgba(37,99,235,0.08)",  dash: "rgba(37,99,235,0.30)" },
};

interface PriceChartProps {
  forecast: ForecastPoint[];
  trend: Trend;
}

function lerp(v: number, a: number, b: number, c: number, d: number): number {
  if (b === a) return (c + d) / 2;
  return ((v - a) / (b - a)) * (d - c) + c;
}

function fmtINR(n: number): string {
  return "₹" + Math.round(n).toLocaleString("en-IN");
}

export function PriceChart({ forecast, trend }: PriceChartProps) {
  const W = 660, H = 240;
  const PAD = { top: 16, right: 16, bottom: 40, left: 72 };
  const iW = W - PAD.left - PAD.right;
  const iH = H - PAD.top - PAD.bottom;
  const colours = TREND_COLOURS[trend] ?? TREND_COLOURS.STABLE;

  const paths = useMemo(() => {
    if (!forecast?.length) return null;
    const n = forecast.length;
    const all = forecast.flatMap(p => [p.lower, p.price, p.upper]);
    const mn = Math.min(...all), mx = Math.max(...all);
    const rng = mx - mn || 1;
    const yMin = mn - rng * 0.06;
    const yMax = mx + rng * 0.06;

    const px = (i: number) => PAD.left + lerp(i, 0, n - 1, 0, iW);
    const py = (v: number) => PAD.top + lerp(v, yMax, yMin, 0, iH);

    const toPath = (vals: number[]) =>
      vals.map((v, i) => `${i === 0 ? "M" : "L"}${px(i).toFixed(1)} ${py(v).toFixed(1)}`).join(" ");

    const upPts  = forecast.map((p, i) => `${px(i).toFixed(1)},${py(p.upper).toFixed(1)}`);
    const loPts  = [...forecast].reverse().map((p, i) => `${px(n - 1 - i).toFixed(1)},${py(p.lower).toFixed(1)}`);

    const xTicks = forecast
      .filter((_, i) => i === 0 || (i + 1) % 7 === 0 || i === n - 1)
      .map(p => ({
        x: px(p.day - 1),
        label: new Date(p.date).toLocaleDateString("en-IN", { day: "numeric", month: "short" }),
      }));

    const yTicks = Array.from({ length: 5 }, (_, i) => {
      const value = yMin + ((yMax - yMin) * i) / 4;
      return { value, y: py(value) };
    });

    const dots = forecast
      .filter((_, i) => i % 5 === 0 || i === n - 1)
      .map(p => ({ cx: px(p.day - 1), cy: py(p.price) }));

    return {
      price: toPath(forecast.map(p => p.price)),
      fill: `M ${upPts.join(" L ")} L ${loPts.join(" L ")} Z`,
      upperPath: toPath(forecast.map(p => p.upper)),
      lowerPath: toPath(forecast.map(p => p.lower)),
      dots, xTicks, yTicks,
    };
  }, [forecast, iW, iH, PAD.left, PAD.top]);

  if (!paths) {
    return (
      <div style={{ height: "200px", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--grey3)", fontSize: ".82rem" }}>
        No forecast data
      </div>
    );
  }

  return (
    <div style={{ width: "100%", overflowX: "auto" }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: "block", fontFamily: "var(--fm)" }}>
        {/* Grid lines */}
        {paths.yTicks.map((t, i) => (
          <line key={i} x1={PAD.left} x2={PAD.left + iW} y1={t.y} y2={t.y} stroke="var(--grey1)" strokeWidth={1} />
        ))}

        {/* CI fill */}
        <path d={paths.fill} fill={colours.fill} />

        {/* CI dashed edges */}
        <path d={paths.upperPath} fill="none" stroke={colours.dash} strokeWidth={1} strokeDasharray="4 4" />
        <path d={paths.lowerPath} fill="none" stroke={colours.dash} strokeWidth={1} strokeDasharray="4 4" />

        {/* Main price line */}
        <path d={paths.price} fill="none" stroke={colours.line} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />

        {/* Dots every 5 days */}
        {paths.dots.map((d, i) => (
          <circle key={i} cx={d.cx} cy={d.cy} r={4} fill={colours.line} stroke="white" strokeWidth={2} />
        ))}

        {/* Axes */}
        <line x1={PAD.left} x2={PAD.left + iW} y1={PAD.top + iH} y2={PAD.top + iH} stroke="var(--grey2)" strokeWidth={1} />
        <line x1={PAD.left} x2={PAD.left} y1={PAD.top} y2={PAD.top + iH} stroke="var(--grey2)" strokeWidth={1} />

        {/* X labels */}
        {paths.xTicks.map((t, i) => (
          <text key={i} x={t.x} y={PAD.top + iH + 16} textAnchor="middle" fontSize={9} fill="var(--grey3)">{t.label}</text>
        ))}

        {/* Y labels */}
        {paths.yTicks.map((t, i) => (
          <text key={i} x={PAD.left - 6} y={t.y + 4} textAnchor="end" fontSize={9} fill="var(--grey3)">{fmtINR(t.value)}</text>
        ))}

        {/* Legend */}
        <g transform={`translate(${PAD.left + 4},${H - 10})`}>
          <line x1={0} x2={14} y1={0} y2={0} stroke={colours.line} strokeWidth={2.5} />
          <text x={18} y={4} fontSize={9} fill="var(--grey3)">Forecast Price</text>
          <line x1={110} x2={124} y1={0} y2={0} stroke={colours.dash} strokeWidth={1} strokeDasharray="4 4" />
          <text x={128} y={4} fontSize={9} fill="var(--grey3)">Confidence Interval</text>
        </g>
      </svg>
    </div>
  );
}

export default PriceChart;
