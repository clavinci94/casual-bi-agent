import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  // Plotly + its mathjax dep bloat the bundle if we let webpack walk into them.
  // We import plotly.js-dist-min directly via react-plotly.js's factory.
  webpack: (cfg) => {
    cfg.resolve.alias = {
      ...(cfg.resolve.alias ?? {}),
      "plotly.js/dist/plotly": "plotly.js-dist-min",
    };
    return cfg;
  },
};

export default config;
