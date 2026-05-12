"use client";

import Link from "next/link";
import useSWR from "swr";
import { api } from "@/lib/api";
import { Sparkline } from "@/components/sparkline";
import {
  demoAnchorDate,
  formatDelta,
  formatKpi,
  isoDaysBack,
  summarise,
  trendTone,
} from "@/lib/kpi-format";
import { OWNER_LABELS, type KpiMeta } from "@/lib/kpi-metadata";

/**
 * A single KPI card. Fetches its own data so the index page can render
 * 8 of them concurrently — SWR dedups identical requests and caches
 * results between navigations.
 */
export function KpiTile({ view, meta }: { view: string; meta: KpiMeta }) {
  // Demo data lives in 2018; anchor against that so cards aren't empty.
  const anchor = demoAnchorDate();
  const end = anchor.toISOString().slice(0, 10);
  const start = isoDaysBack(meta.defaultRangeDays, anchor);

  const { data, error, isLoading } = useSWR(
    ["kpi-tile", view, start, end],
    () => api.queryKpi(view, { start, end }),
  );

  // Reduce to a single value-series, aggregating across the date column if
  // there are multiple rows per day (e.g. by device — sum or average).
  const series = aggregateToDaily(data?.rows ?? [], meta);
  const summary = summarise(series.map((p) => p.value));
  const tone = trendTone(summary.delta, meta.higherIsBetter);

  return (
    <Link href={`/kpis/${encodeURIComponent(view)}`}>
      <div className="group relative h-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-2xl p-5 hover:border-[var(--color-accent)] transition-colors cursor-pointer">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="text-[11px] uppercase tracking-wider text-[var(--color-muted)] font-medium">
              {OWNER_LABELS[meta.owner]}
            </div>
            <h3 className="text-base font-semibold mt-0.5 leading-tight">
              {meta.title}
            </h3>
          </div>
          <TrendArrow tone={tone} />
        </div>

        <div className="mt-4 flex items-end justify-between gap-3">
          <div>
            <div className="text-3xl font-semibold tabular-nums">
              {isLoading ? (
                <span className="inline-block w-20 h-7 bg-[var(--color-bg)] animate-pulse rounded" />
              ) : error ? (
                <span className="text-base text-[var(--color-danger)] mono">
                  err
                </span>
              ) : (
                formatKpi(summary.current, meta.unit)
              )}
            </div>
            <DeltaText delta={summary.delta} tone={tone} />
          </div>
          <div
            className={
              tone === "good"
                ? "text-[var(--color-success)]"
                : tone === "bad"
                  ? "text-[var(--color-danger)]"
                  : "text-[var(--color-muted)]"
            }
          >
            <Sparkline values={series.map((p) => p.value)} />
          </div>
        </div>

        <p className="mt-4 text-xs text-[var(--color-muted)] line-clamp-2">
          {meta.description}
        </p>
      </div>
    </Link>
  );
}

function TrendArrow({ tone }: { tone: "good" | "bad" | "flat" }) {
  const color =
    tone === "good"
      ? "text-[var(--color-success)]"
      : tone === "bad"
        ? "text-[var(--color-danger)]"
        : "text-[var(--color-muted)]";
  const symbol = tone === "good" ? "▲" : tone === "bad" ? "▼" : "■";
  return (
    <div className={`text-sm font-bold ${color}`} aria-hidden="true">
      {symbol}
    </div>
  );
}

function DeltaText({
  delta,
  tone,
}: {
  delta: number | null;
  tone: "good" | "bad" | "flat";
}) {
  const color =
    tone === "good"
      ? "text-[var(--color-success)]"
      : tone === "bad"
        ? "text-[var(--color-danger)]"
        : "text-[var(--color-muted)]";
  return (
    <div className={`text-xs mt-1 ${color} tabular-nums`}>
      {formatDelta(delta)} ggü. Vorperiode
    </div>
  );
}

// --- Aggregation -------------------------------------------------------

type Point = { date: string; value: number | null };

/**
 * Collapse rows (which may include extra dimensions like device or
 * channel) into one value per day. For ratio metrics we average,
 * for monetary metrics we sum — driven by the KPI unit.
 */
function aggregateToDaily(
  rows: Record<string, unknown>[],
  meta: KpiMeta,
): Point[] {
  const dateField = meta.dateField;
  const valueField = meta.valueField;
  if (rows.length === 0) return [];

  const sumOrMean = meta.unit === "currency_chf" || meta.unit === "count";

  const scale = meta.valueScale ?? 1;
  const buckets = new Map<string, number[]>();
  for (const r of rows) {
    const d = r[dateField];
    const raw = r[valueField];
    if (typeof d !== "string") continue;
    // Postgres numeric arrives as a string from psycopg's default codec —
    // coerce here so we don't drop every row silently.
    const num =
      typeof raw === "number"
        ? raw
        : typeof raw === "string"
          ? Number(raw)
          : Number.NaN;
    if (!Number.isFinite(num)) continue;
    if (!buckets.has(d)) buckets.set(d, []);
    buckets.get(d)!.push(num * scale);
  }

  return [...buckets.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, vs]) => ({
      date,
      value: sumOrMean
        ? vs.reduce((a, b) => a + b, 0)
        : vs.reduce((a, b) => a + b, 0) / vs.length,
    }));
}
