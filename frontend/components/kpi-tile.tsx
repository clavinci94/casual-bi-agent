"use client";

import Link from "next/link";
import useSWR from "swr";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { api } from "@/lib/api";
import { KpiIcon } from "@/components/kpi-icon";
import { Sparkline } from "@/components/sparkline";
import {
  demoAnchorDate,
  formatDelta,
  formatKpi,
  isoDaysBack,
  summarise,
  trendTone,
} from "@/lib/kpi-format";
import { type KpiMeta } from "@/lib/kpi-metadata";

/**
 * Manager-facing KPI card. Visual hierarchy: icon → name → subtitle →
 * big number → trend → sparkline. No metric jargon, no technical column
 * names. The card fetches its own data so the index can render all of
 * them in parallel.
 */
export function KpiTile({ view, meta }: { view: string; meta: KpiMeta }) {
  const anchor = demoAnchorDate();
  const end = anchor.toISOString().slice(0, 10);
  const start = isoDaysBack(meta.defaultRangeDays, anchor);

  const { data, error, isLoading } = useSWR(
    ["kpi-tile", view, start, end],
    () => api.queryKpi(view, { start, end }),
  );

  const series = aggregateToDaily(data?.rows ?? [], meta);
  const summary = summarise(series.map((p) => p.value));
  const tone = trendTone(summary.delta, meta.higherIsBetter);

  const accent =
    tone === "good"
      ? "text-[var(--color-success)]"
      : tone === "bad"
        ? "text-[var(--color-danger)]"
        : "text-[var(--color-muted)]";

  return (
    <Link href={`/kpis/${encodeURIComponent(view)}`}>
      <div className="group h-full bg-[var(--color-surface)] border border-[var(--color-border)] rounded-2xl p-5 hover:border-[var(--color-accent)] transition-colors cursor-pointer">
        <div className="flex items-start gap-3">
          <div className="size-10 rounded-xl bg-[var(--color-bg)] flex items-center justify-center text-[var(--color-fg)] shrink-0">
            <KpiIcon name={meta.icon} className="size-5" />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="text-base font-semibold leading-tight">
              {meta.title}
            </h3>
            <p className="text-xs text-[var(--color-muted)] mt-0.5 line-clamp-2">
              {meta.subtitle}
            </p>
          </div>
        </div>

        <div className="mt-4 flex items-end justify-between gap-3">
          <div>
            <div className="text-3xl font-semibold tabular-nums leading-none">
              {isLoading ? (
                <span className="inline-block w-20 h-7 bg-[var(--color-bg)] animate-pulse rounded" />
              ) : error ? (
                <span className="text-base text-[var(--color-danger)]">—</span>
              ) : (
                formatKpi(summary.current, meta.unit)
              )}
            </div>
            <div className={`text-xs mt-2 flex items-center gap-1 ${accent} tabular-nums`}>
              <TrendIcon tone={tone} />
              <span>{formatDelta(summary.delta)}</span>
              <span className="text-[var(--color-muted)]">ggü. Vorperiode</span>
            </div>
          </div>
          <div className={accent}>
            <Sparkline values={series.map((p) => p.value)} />
          </div>
        </div>
      </div>
    </Link>
  );
}

function TrendIcon({ tone }: { tone: "good" | "bad" | "flat" }) {
  if (tone === "good") return <TrendingUp className="size-3.5" />;
  if (tone === "bad") return <TrendingDown className="size-3.5" />;
  return <Minus className="size-3.5" />;
}

// --- Aggregation -------------------------------------------------------

type Point = { date: string; value: number | null };

function aggregateToDaily(
  rows: Record<string, unknown>[],
  meta: KpiMeta,
): Point[] {
  const dateField = meta.dateField;
  const valueField = meta.valueField;
  if (rows.length === 0) return [];

  const scale = meta.valueScale ?? 1;
  const sumOrMean = meta.unit === "currency_chf" || meta.unit === "count";

  const buckets = new Map<string, number[]>();
  for (const r of rows) {
    const d = r[dateField];
    const raw = r[valueField];
    if (typeof d !== "string") continue;
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
