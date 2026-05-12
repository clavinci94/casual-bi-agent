"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useKpiQuery } from "@/lib/hooks";
import { TimeSeries } from "@/components/plot";
import {
  Card,
  Empty,
  ErrorMessage,
  Loading,
  Pill,
  SectionTitle,
} from "@/components/ui";
import {
  demoAnchorDate,
  formatDelta,
  formatKpi,
  isoDaysBack,
  summarise,
  trendTone,
} from "@/lib/kpi-format";
import { metaFor, type GroupOption } from "@/lib/kpi-metadata";

const PRESETS: { label: string; days: number }[] = [
  { label: "Last 7 days", days: 7 },
  { label: "Last 30 days", days: 30 },
  { label: "Last 90 days", days: 90 },
  { label: "Last 6 months", days: 180 },
];

export default function KpiDetail() {
  const params = useParams<{ view: string }>();
  const view = decodeURIComponent(params.view ?? "");
  const meta = metaFor(view);

  // Demo data is in 2018 — anchor against that so the page actually has data.
  const anchor = demoAnchorDate();
  const anchorISO = anchor.toISOString().slice(0, 10);

  const [rangeDays, setRangeDays] = useState(meta?.defaultRangeDays ?? 30);
  const [compareBy, setCompareBy] = useState<GroupOption | null>(null);

  const start = isoDaysBack(rangeDays, anchor);
  const end = anchorISO;

  const { data, error, isLoading } = useKpiQuery(view, {
    start,
    end,
    group_by: compareBy ? [compareBy.field] : [],
  });

  // Headline summary (always against the un-grouped flat view).
  const headlineSeries = useMemo(() => {
    if (!data?.rows?.length || !meta) return [];
    return aggregateToDaily(data.rows, meta);
  }, [data, meta]);

  const summary = summarise(headlineSeries.map((p) => p.value));
  const tone = meta
    ? trendTone(summary.delta, meta.higherIsBetter)
    : "flat";

  // Chart series — possibly broken down by the chosen "Compare by" option.
  const chartSeries = useMemo(() => {
    if (!data?.rows?.length || !meta)
      return [] as { name: string; x: string[]; y: (number | null)[] }[];

    const dateField = meta.dateField;
    const valueField = meta.valueField;
    const dim = compareBy?.field ?? null;

    if (!dim) {
      return [
        {
          name: meta.title,
          x: headlineSeries.map((p) => p.date),
          y: headlineSeries.map((p) => p.value),
        },
      ];
    }

    const buckets = new Map<
      string,
      { x: string[]; y: (number | null)[] }
    >();
    for (const r of data.rows as Record<string, unknown>[]) {
      const d = r[dateField];
      const v = r[valueField];
      const k = r[dim];
      if (typeof d !== "string") continue;
      const seriesName = String(k ?? "unknown");
      if (!buckets.has(seriesName)) buckets.set(seriesName, { x: [], y: [] });
      const b = buckets.get(seriesName)!;
      b.x.push(d);
      b.y.push(typeof v === "number" ? v : null);
    }
    return [...buckets.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([name, s]) => ({ name, ...s }));
  }, [data, headlineSeries, compareBy, meta]);

  if (!meta) {
    return (
      <div className="space-y-4 max-w-2xl">
        <h1 className="text-2xl font-semibold tracking-tight mono">{view}</h1>
        <p className="text-sm text-[var(--color-muted)]">
          No UX metadata for this view yet. Add it to{" "}
          <span className="mono">lib/kpi-metadata.ts</span> to render it
          here, or use the API directly:
        </p>
        <code className="block bg-[var(--color-bg)] border border-[var(--color-border)] rounded-md p-3 text-xs mono">
          GET /api/kpis/{view}?start=…&end=…
        </code>
        <Link href="/kpis" className="text-sm text-[var(--color-accent)]">
          ← Back to KPIs
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Breadcrumb */}
      <Link
        href="/kpis"
        className="text-sm text-[var(--color-muted)] hover:text-[var(--color-fg)] inline-flex items-center gap-1"
      >
        ← All KPIs
      </Link>

      {/* Headline */}
      <header>
        <div className="text-xs uppercase tracking-wider text-[var(--color-muted)] font-medium">
          {meta.owner}
        </div>
        <h1 className="text-3xl font-semibold tracking-tight mt-0.5">
          {meta.title}
        </h1>
        <p className="text-base text-[var(--color-muted)] mt-2 max-w-2xl leading-relaxed">
          {meta.description}
        </p>
      </header>

      {/* Headline value tiles */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <HeadlineTile
          label="Current"
          value={formatKpi(summary.current, meta.unit)}
          loading={isLoading}
        />
        <HeadlineTile
          label="Prior period"
          value={formatKpi(summary.previous, meta.unit)}
          loading={isLoading}
          muted
        />
        <HeadlineTile
          label="Change"
          value={formatDelta(summary.delta)}
          tone={tone}
          loading={isLoading}
        />
      </div>

      {/* Controls */}
      <Card className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-1">
            {PRESETS.map((p) => (
              <button
                key={p.label}
                type="button"
                onClick={() => setRangeDays(p.days)}
                className={`px-3 py-1.5 rounded-md text-sm transition-colors ${
                  rangeDays === p.days
                    ? "bg-[var(--color-accent)] text-[var(--color-accent-fg)] font-medium"
                    : "text-[var(--color-muted)] hover:text-[var(--color-fg)] hover:bg-[var(--color-bg)]"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>

          {meta.groupOptions.length > 0 ? (
            <div className="flex items-center gap-1">
              <span className="text-xs text-[var(--color-muted)] mr-1">
                Compare:
              </span>
              <button
                type="button"
                onClick={() => setCompareBy(null)}
                className={`px-2 py-1 rounded-md text-xs ${
                  compareBy == null
                    ? "bg-[var(--color-bg)] text-[var(--color-fg)] font-medium"
                    : "text-[var(--color-muted)] hover:text-[var(--color-fg)]"
                }`}
              >
                Overall
              </button>
              {meta.groupOptions.map((g) => (
                <button
                  key={g.field}
                  type="button"
                  onClick={() => setCompareBy(g)}
                  className={`px-2 py-1 rounded-md text-xs ${
                    compareBy?.field === g.field
                      ? "bg-[var(--color-bg)] text-[var(--color-fg)] font-medium"
                      : "text-[var(--color-muted)] hover:text-[var(--color-fg)]"
                  }`}
                >
                  {g.label}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      </Card>

      {/* Chart */}
      <Card className="p-4 min-h-[400px]">
        <SectionTitle
          title={compareBy ? `Trend · ${compareBy.label.toLowerCase()}` : "Trend"}
          hint={`${start} → ${end}`}
        />
        {error ? (
          <ErrorMessage error={error} />
        ) : isLoading ? (
          <Loading />
        ) : !data?.rows?.length ? (
          <Empty>
            {data?.note ?? "No data in this window. Try a wider range."}
          </Empty>
        ) : (
          <TimeSeries
            series={chartSeries}
            yLabel={meta.title}
            height={400}
          />
        )}
      </Card>

      {/* Caveat / what to watch for */}
      {meta.caveat ? (
        <Card className="p-4 border-dashed">
          <SectionTitle title="What to keep in mind" />
          <p className="text-sm text-[var(--color-muted)]">{meta.caveat}</p>
        </Card>
      ) : null}
    </div>
  );
}

function HeadlineTile({
  label,
  value,
  loading,
  tone,
  muted,
}: {
  label: string;
  value: string;
  loading: boolean;
  tone?: "good" | "bad" | "flat";
  muted?: boolean;
}) {
  const valueColor =
    tone === "good"
      ? "text-[var(--color-success)]"
      : tone === "bad"
        ? "text-[var(--color-danger)]"
        : muted
          ? "text-[var(--color-muted)]"
          : "text-[var(--color-fg)]";
  return (
    <Card className="px-5 py-4">
      <div className="text-[11px] uppercase tracking-wider text-[var(--color-muted)] font-medium">
        {label}
      </div>
      <div className={`text-3xl font-semibold mt-1 tabular-nums ${valueColor}`}>
        {loading ? (
          <span className="inline-block w-24 h-7 bg-[var(--color-bg)] animate-pulse rounded" />
        ) : (
          value
        )}
      </div>
    </Card>
  );
}

// Re-used aggregator from the tile component — kept local to avoid circular
// imports and to allow the detail view to evolve independently if needed.
type Point = { date: string; value: number | null };

function aggregateToDaily(
  rows: Record<string, unknown>[],
  meta: NonNullable<ReturnType<typeof metaFor>>,
): Point[] {
  if (rows.length === 0) return [];
  const dateField = meta.dateField;
  const valueField = meta.valueField;
  const sumOrMean = meta.unit === "currency_chf" || meta.unit === "count";
  const buckets = new Map<string, number[]>();
  for (const r of rows) {
    const d = r[dateField];
    const v = r[valueField];
    if (typeof d !== "string") continue;
    if (typeof v !== "number" || Number.isNaN(v)) continue;
    if (!buckets.has(d)) buckets.set(d, []);
    buckets.get(d)!.push(v);
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
