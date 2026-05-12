import type { KpiUnit } from "./kpi-metadata";

/**
 * Format a raw numeric KPI value for display.
 *
 * - "percent": inputs are decimals (0.041 → "4.1 %"). 1 decimal place.
 * - "currency_chf": CHF, no fractional rappen for headline numbers.
 * - "days": one decimal, suffix "d".
 * - "score": one decimal, suffix " / 5".
 * - "count": locale-formatted integer.
 */
export function formatKpi(value: number | null | undefined, unit: KpiUnit): string {
  if (value == null || Number.isNaN(value)) return "—";
  switch (unit) {
    case "percent":
      return `${(value * 100).toFixed(1)} %`;
    case "currency_chf":
      return new Intl.NumberFormat("de-CH", {
        style: "currency",
        currency: "CHF",
        maximumFractionDigits: 0,
      }).format(value);
    case "days":
      return `${value.toFixed(1)} d`;
    case "score":
      return `${value.toFixed(2)} / 5`;
    case "count":
      return new Intl.NumberFormat("de-CH").format(Math.round(value));
  }
}

/**
 * Signed percentage delta, e.g. "+12.3 %" or "−38.4 %".
 * (Uses minus-sign U+2212 for proper typography, not a hyphen.)
 */
export function formatDelta(deltaFraction: number | null): string {
  if (deltaFraction == null || !Number.isFinite(deltaFraction)) return "—";
  const pct = deltaFraction * 100;
  const sign = pct > 0 ? "+" : pct < 0 ? "−" : "";
  return `${sign}${Math.abs(pct).toFixed(1)} %`;
}

/**
 * Decide which Tailwind color tone to use for a trend arrow given the
 * delta direction and whether higher values are good for this KPI.
 */
export function trendTone(
  deltaFraction: number | null,
  higherIsBetter: boolean,
): "good" | "bad" | "flat" {
  if (deltaFraction == null || !Number.isFinite(deltaFraction)) return "flat";
  if (Math.abs(deltaFraction) < 0.005) return "flat"; // <0.5% = noise
  const positive = deltaFraction > 0;
  if (positive === higherIsBetter) return "good";
  return "bad";
}

/**
 * Reduce a series of {x, y} points to one number for headline display +
 * one number for delta-vs-previous-period.
 *
 * Splits the series in half:
 *   - "current" = mean of the second half (latest)
 *   - "previous" = mean of the first half
 * Delta = (current - previous) / previous
 *
 * Using a mean (not just the last point) smooths weekend noise so the
 * card doesn't lie when the latest day was a Sunday.
 */
export function summarise(values: (number | null)[]): {
  current: number | null;
  previous: number | null;
  delta: number | null;
} {
  const clean = values.filter((v): v is number => v != null);
  if (clean.length === 0) return { current: null, previous: null, delta: null };
  if (clean.length === 1) {
    return { current: clean[0], previous: null, delta: null };
  }

  const mid = Math.floor(clean.length / 2);
  const previous = mean(clean.slice(0, mid));
  const current = mean(clean.slice(mid));
  const delta = previous && previous !== 0 ? (current - previous) / previous : null;
  return { current, previous, delta };
}

function mean(arr: number[]): number {
  return arr.reduce((a, b) => a + b, 0) / arr.length;
}

/**
 * ISO date N days back from today, suitable for backend's `start` / `end`
 * query params.
 */
export function isoDaysBack(days: number, anchor: Date = new Date()): string {
  const d = new Date(anchor);
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

export function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

/**
 * For the demo dataset that lives in 2018, "today" isn't useful. We anchor
 * default ranges at the last known data point (May 2018). The catch is we
 * don't know that here — so we just push the anchor back 7 years for
 * datasets older than current-year. Adjust to the actual freshness when
 * real-time data arrives.
 */
export function demoAnchorDate(): Date {
  return new Date("2018-05-10T00:00:00Z");
}
