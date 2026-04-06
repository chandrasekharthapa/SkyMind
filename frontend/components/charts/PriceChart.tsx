"use client";

import React, { useMemo } from "react";
import type { ForecastPoint, Trend } from "@/types";

const TREND_COLOURS: Record<Trend, { line: string; fill: string; dash: string; glow: string }> = {
  RISING:  { line: "#e8191a", fill: "rgba(232,25,26,0.07)",   dash: "rgba(232,25,26,0.25)",  glow: "rgba(232,25,26,0.15)" },
  FALLING: { line: "#16a34a", fill: "rgba(22,163,74,0.07)",   dash: "rgba(22,163,74,0.25)",   glow: "rgba(22,163,74,0.15)" },
  STABLE:  { line: "#2563eb", fill: "rgba(37,99,235,0.07)",   dash: "rgba(37,99,235,0.25)",   glow: "rgba(37,99,235,0.15)" },
};

interface PriceChartProps {
  forecast: ForecastPoint[];
  trend: Trend;
  height?: number;
}

function lerp(v: number, a: number, b: number, c: number, d: number): number {
  if (b === a) return (c + d) / 2;
  return ((v - a) / (b - a)) * (d - c) + c;
}

function fmtINR(n: number): string {
  if (n >= 100000) return `₹${(n / 100000).toFixed(1)}L`;
  if (n >= 1000) return `₹${(n / 1000).toFixed(1)}k`;
  return `₹${Math.round(n)}`;
}

export function PriceChart({ forecast, trend, height = 260 }: PriceChartProps) {
  const W = 680;
  const H = height;
  const PAD = { top: 20, right: 20, bottom: 44, left: 68 };
  const iW = W - PAD.left - PAD.right;
  const iH = H - PAD.top - PAD.bottom;
  const colours = TREND_COLOURS[trend] ?? TREND_COLOURS.STABLE;

  const paths = useMemo(() => {
    if (!forecast?.length) return null;
    const n = forecast.length;
    const allPrices = forecast.flatMap((p) => [p.lower, p.price, p.upper]);
    const mn = Math.min(...allPrices);
    const mx = Math.max(...allPrices);
    const rng = mx - mn || 1;
    const yMin = mn - rng * 0.08;
    const yMax = mx + rng * 0.08;

    const px = (i: number) => PAD.left + lerp(i, 0, n - 1, 0, iW);
    const py = (v: number) => PAD.top + lerp(v, yMax, yMin, 0, iH);

    const toPath = (vals: number[]) =>
      vals.map((v, i) => `${i === 0 ? "M" : "L"}${px(i).toFixed(1)} ${py(v).toFixed(1)}`).join(" ");

    const upPts = forecast.map((p, i) => `${px(i).toFixed(1)},${py(p.upper).toFixed(1)}`);
    const loPts = [...forecast].reverse().map((p, i) =>
      `${px(n - 1 - i).toFixed(1)},${py(p.lower).toFixed(1)}`
    );

    // Every 7 days + first + last
    const xTicks = forecast
      .filter((_, i) => i === 0 || (i + 1) % 7 === 0 || i === n - 1)
      .map((p) => ({
        x: px(p.day - 1),
        label: new Date(p.date).toLocaleDateString("en-IN", { day: "numeric", month: "short" }),
      }));

    const yTicks = Array.from({ length: 5 }, (_, i) => {
      const value = yMin + ((yMax - yMin) * i) / 4;
      return { value, y: py(value) };
    });

    const dots = forecast
      .filter((_, i) => i % 5 === 0 || i === n - 1)
      .map((p) => ({ cx: px(p.day - 1), cy: py(p.price), price: p.price }));

    // Min/Max markers
    const prices = forecast.map((p) => p.price);
    const minIdx = prices.indexOf(Math.min(...prices));
    const maxIdx = prices.indexOf(Math.max(...prices));
    const minPt = { cx: px(minIdx), cy: py(prices[minIdx]), price: prices[minIdx] };
    const maxPt = { cx: px(maxIdx), cy: py(prices[maxIdx]), price: prices[maxIdx] };

    return {
      price: toPath(forecast.map((p) => p.price)),
      fill: `M ${upPts.join(" L ")} L ${loPts.join(" L ")} Z`,
      upperPath: toPath(forecast.map((p) => p.upper)),
      lowerPath: toPath(forecast.map((p) => p.lower)),
      dots,
      xTicks,
      yTicks,
      minPt,
      maxPt,
    };
  }, [forecast, iW, iH, PAD.left, PAD.top]);

  if (!paths) {
    return (
      <div className="flex items-center justify-center h-48 text-gray-400 text-sm">
        No forecast data available
      </div>
    );
  }

  return (
    <div className="w-full overflow-x-auto" style={{ WebkitOverflowScrolling: "touch" }}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        style={{ display: "block", minWidth: "320px", fontFamily: "var(--fm, monospace)" }}
      >
        <defs>
          <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <linearGradient id={`grad-${trend}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={colours.line} stopOpacity="0.12" />
            <stop offset="100%" stopColor={colours.line} stopOpacity="0.01" />
          </linearGradient>
        </defs>

        {/* Grid lines */}
        {paths.yTicks.map((t, i) => (
          <line
            key={i}
            x1={PAD.left}
            x2={PAD.left + iW}
            y1={t.y}
            y2={t.y}
            stroke="var(--grey1, #efefed)"
            strokeWidth={1}
            strokeDasharray={i === 0 ? "0" : "4 4"}
          />
        ))}

        {/* CI fill */}
        <path d={paths.fill} fill={`url(#grad-${trend})`} />

        {/* CI dashed edges */}
        <path
          d={paths.upperPath}
          fill="none"
          stroke={colours.dash}
          strokeWidth={1.5}
          strokeDasharray="5 5"
        />
        <path
          d={paths.lowerPath}
          fill="none"
          stroke={colours.dash}
          strokeWidth={1.5}
          strokeDasharray="5 5"
        />

        {/* Main price line with glow */}
        <path
          d={paths.price}
          fill="none"
          stroke={colours.glow}
          strokeWidth={6}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        <path
          d={paths.price}
          fill="none"
          stroke={colours.line}
          strokeWidth={2.5}
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {/* Dots every 5 days */}
        {paths.dots.map((d, i) => (
          <g key={i}>
            <circle cx={d.cx} cy={d.cy} r={5} fill={colours.line} opacity={0.15} />
            <circle cx={d.cx} cy={d.cy} r={3.5} fill={colours.line} stroke="white" strokeWidth={1.5} />
          </g>
        ))}

        {/* Min marker (green) */}
        <g>
          <circle cx={paths.minPt.cx} cy={paths.minPt.cy} r={6} fill="#dcfce7" stroke="#16a34a" strokeWidth={2} />
          <text
            x={paths.minPt.cx}
            y={paths.minPt.cy - 12}
            textAnchor="middle"
            fontSize={9}
            fill="#16a34a"
            fontWeight="700"
          >
            {fmtINR(paths.minPt.price)}
          </text>
        </g>

        {/* Max marker (red) */}
        <g>
          <circle cx={paths.maxPt.cx} cy={paths.maxPt.cy} r={6} fill="#fee2e2" stroke="#e8191a" strokeWidth={2} />
          <text
            x={paths.maxPt.cx}
            y={paths.maxPt.cy + 20}
            textAnchor="middle"
            fontSize={9}
            fill="#e8191a"
            fontWeight="700"
          >
            {fmtINR(paths.maxPt.price)}
          </text>
        </g>

        {/* Axes */}
        <line
          x1={PAD.left}
          x2={PAD.left + iW}
          y1={PAD.top + iH}
          y2={PAD.top + iH}
          stroke="var(--grey2, #d8d6d2)"
          strokeWidth={1.5}
        />
        <line
          x1={PAD.left}
          x2={PAD.left}
          y1={PAD.top}
          y2={PAD.top + iH}
          stroke="var(--grey2, #d8d6d2)"
          strokeWidth={1.5}
        />

        {/* X labels */}
        {paths.xTicks.map((t, i) => (
          <text
            key={i}
            x={t.x}
            y={PAD.top + iH + 18}
            textAnchor="middle"
            fontSize={9}
            fill="var(--grey3, #9b9890)"
          >
            {t.label}
          </text>
        ))}

        {/* Y labels */}
        {paths.yTicks.map((t, i) => (
          <text
            key={i}
            x={PAD.left - 8}
            y={t.y + 4}
            textAnchor="end"
            fontSize={9}
            fill="var(--grey3, #9b9890)"
          >
            {fmtINR(t.value)}
          </text>
        ))}

        {/* Legend */}
        <g transform={`translate(${PAD.left + 4},${H - 10})`}>
          <line x1={0} x2={14} y1={0} y2={0} stroke={colours.line} strokeWidth={2.5} />
          <text x={18} y={4} fontSize={9} fill="var(--grey3, #9b9890)">
            Forecast Price
          </text>
          <line x1={110} x2={124} y1={0} y2={0} stroke={colours.dash} strokeWidth={1.5} strokeDasharray="4 4" />
          <text x={128} y={4} fontSize={9} fill="var(--grey3, #9b9890)">
            Confidence Interval
          </text>
          <circle cx={240} cy={0} r={4} fill="#dcfce7" stroke="#16a34a" strokeWidth={1.5} />
          <text x={248} y={4} fontSize={9} fill="#16a34a">
            Best Price
          </text>
          <circle cx={310} cy={0} r={4} fill="#fee2e2" stroke="#e8191a" strokeWidth={1.5} />
          <text x={318} y={4} fontSize={9} fill="#e8191a">
            Peak Price
          </text>
        </g>
      </svg>
    </div>
  );
}

export default PriceChart;
