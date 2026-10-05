"use client";

type ForecastPoint = {
  day: number;
  date: string;
  price: number;
  lower?: number;
  upper?: number;
};

type Props = {
  forecast: ForecastPoint[];
};

function formatPrice(value: number): string {
  return `INR ${Math.round(value).toLocaleString("en-IN")}`;
}

export default function ForecastChart({ forecast }: Props) {
  if (!forecast.length) {
    return <div className="forecast-chart__empty">No forecast available</div>;
  }

  const width = 720;
  const height = 260;
  const pad = { top: 24, right: 24, bottom: 40, left: 64 };
  const innerWidth = width - pad.left - pad.right;
  const innerHeight = height - pad.top - pad.bottom;
  const prices = forecast.map((point) => point.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = Math.max(1, max - min);

  const x = (index: number) => pad.left + (index / Math.max(1, forecast.length - 1)) * innerWidth;
  const y = (price: number) => pad.top + ((max + range * 0.12 - price) / (range * 1.24)) * innerHeight;
  const linePath = forecast
    .map((point, index) => `${index === 0 ? "M" : "L"} ${x(index).toFixed(1)} ${y(point.price).toFixed(1)}`)
    .join(" ");
  const best = forecast.reduce((winner, point) => (point.price < winner.price ? point : winner), forecast[0]);

  return (
    <section className="forecast-chart" aria-label="30 day price forecast">
      <div className="forecast-chart__header">
        <span>30-Day Forecast</span>
        <strong>{formatPrice(best.price)} best fare</strong>
      </div>

      <svg viewBox={`0 0 ${width} ${height}`} role="img">
        {[0, 1, 2, 3].map((tick) => {
          const value = min + (range * tick) / 3;
          return (
            <g key={tick}>
              <line x1={pad.left} x2={width - pad.right} y1={y(value)} y2={y(value)} />
              <text x={pad.left - 10} y={y(value) + 4}>
                {formatPrice(value)}
              </text>
            </g>
          );
        })}

        <path d={linePath} className="forecast-chart__line" />
        {forecast.map((point, index) => (
          <circle
            key={point.date}
            className={point.date === best.date ? "forecast-chart__dot forecast-chart__dot--best" : "forecast-chart__dot"}
            cx={x(index)}
            cy={y(point.price)}
            r={point.date === best.date ? 5 : 3}
          />
        ))}

        {forecast.filter((_, index) => index === 0 || (index + 1) % 7 === 0).map((point) => (
          <text key={point.date} x={x(point.day - 1)} y={height - 14} className="forecast-chart__date">
            {new Date(point.date).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}
          </text>
        ))}
      </svg>
    </section>
  );
}
