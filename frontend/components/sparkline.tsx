"use client";

/**
 * Minimal SVG sparkline. ~40 lines of code, zero dependencies, renders
 * fine on a card without the Plotly overhead.
 */
export function Sparkline({
  values,
  width = 120,
  height = 36,
  stroke = "currentColor",
  fill = "currentColor",
  fillOpacity = 0.08,
}: {
  values: (number | null)[];
  width?: number;
  height?: number;
  stroke?: string;
  fill?: string;
  fillOpacity?: number;
}) {
  const cleaned = values.map((v) => (v == null || Number.isNaN(v) ? null : v));
  const finite = cleaned.filter((v): v is number => v != null);
  if (finite.length < 2) {
    return (
      <svg width={width} height={height} aria-hidden="true">
        <line
          x1="0"
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke="currentColor"
          strokeOpacity="0.2"
          strokeDasharray="2 3"
        />
      </svg>
    );
  }

  const min = Math.min(...finite);
  const max = Math.max(...finite);
  const range = max - min || 1;
  const stepX = width / Math.max(cleaned.length - 1, 1);

  const points: Array<[number, number] | null> = cleaned.map((v, i) => {
    if (v == null) return null;
    const x = i * stepX;
    const y = height - ((v - min) / range) * (height - 2) - 1;
    return [x, y];
  });

  // Build a single path skipping null segments.
  let d = "";
  let pen = false;
  for (const p of points) {
    if (p == null) {
      pen = false;
      continue;
    }
    d += (pen ? "L" : "M") + p[0].toFixed(1) + "," + p[1].toFixed(1) + " ";
    pen = true;
  }

  // Area-fill polygon (closed at the baseline) — drawn first under the line.
  const firstFinite = points.find((p) => p != null) as [number, number];
  const lastFinite = [...points].reverse().find((p) => p != null) as [
    number,
    number,
  ];
  const area =
    `M${firstFinite[0]},${height} ` +
    d.replace(/M/g, "L") +
    `L${lastFinite[0]},${height} Z`;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden="true"
    >
      <path d={area} fill={fill} opacity={fillOpacity} stroke="none" />
      <path
        d={d}
        fill="none"
        stroke={stroke}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
