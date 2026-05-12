"use client";

import dynamic from "next/dynamic";
import type { PlotParams } from "react-plotly.js";

// Plotly is a 3 MB bundle — load it client-side only. SSR rendering would
// blow up because plotly.js touches `document` at import time.
const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

export function TimeSeries({
  series,
  yLabel,
  height = 320,
}: {
  series: Array<{ name: string; x: string[]; y: (number | null)[] }>;
  yLabel?: string;
  height?: number;
}) {
  const data: PlotParams["data"] = series.map((s) => ({
    type: "scatter",
    mode: "lines+markers",
    name: s.name,
    x: s.x,
    y: s.y,
    line: { width: 2 },
    marker: { size: 4 },
  }));

  const layout: PlotParams["layout"] = {
    height,
    margin: { l: 50, r: 16, t: 8, b: 40 },
    plot_bgcolor: "rgba(0,0,0,0)",
    paper_bgcolor: "rgba(0,0,0,0)",
    font: { family: "system-ui, sans-serif", size: 12 },
    legend: { orientation: "h", y: -0.15 },
    xaxis: { gridcolor: "#eee", zerolinecolor: "#eee" },
    yaxis: { title: { text: yLabel ?? "" }, gridcolor: "#eee", zerolinecolor: "#eee" },
    hovermode: "x unified",
  };

  return (
    <Plot
      data={data}
      layout={layout}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%" }}
    />
  );
}
