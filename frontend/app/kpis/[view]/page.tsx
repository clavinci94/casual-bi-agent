"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
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

// Heuristic date defaults that line up with the Olist demo data + the
// deliberately-injected mobile_v2 anomaly in early May 2018.
const DEFAULT_START = "2018-03-01";
const DEFAULT_END = "2018-06-01";

const NUMERIC_FIELDS_PRIORITY = [
  "conversion_rate",
  "aov",
  "gross_margin",
  "delivery_time_p95_days",
  "review_score_avg",
  "refund_rate",
  "repeat_rate",
  "churn_rate",
];

export default function KpiDetail() {
  const params = useParams<{ view: string }>();
  const view = decodeURIComponent(params.view ?? "");
  const [start, setStart] = useState(DEFAULT_START);
  const [end, setEnd] = useState(DEFAULT_END);
  const [groupBy, setGroupBy] = useState<string>("device");

  const { data, error, isLoading } = useKpiQuery(view, {
    start,
    end,
    group_by: groupBy ? [groupBy] : [],
  });

  const { dateCol, valueCol, series } = useMemo(() => {
    if (!data?.rows?.length)
      return { dateCol: null, valueCol: null, series: [] };

    const row = data.rows[0] as Record<string, unknown>;
    const keys = Object.keys(row);
    const dateCol = keys.includes("day") ? "day" : keys.includes("week") ? "week" : null;
    if (!dateCol)
      return { dateCol: null, valueCol: null, series: [] };

    const valueCol =
      NUMERIC_FIELDS_PRIORITY.find((c) => keys.includes(c)) ??
      keys.find((k) => typeof row[k] === "number") ??
      null;
    if (!valueCol) return { dateCol, valueCol: null, series: [] };

    // Group by the chosen dimension if it's present in the rows.
    const hasDim = groupBy && keys.includes(groupBy);
    if (!hasDim) {
      return {
        dateCol,
        valueCol,
        series: [
          {
            name: valueCol,
            x: data.rows.map((r) => String((r as Record<string, unknown>)[dateCol])),
            y: data.rows.map((r) => {
              const v = (r as Record<string, unknown>)[valueCol];
              return typeof v === "number" ? v : null;
            }),
          },
        ],
      };
    }

    const byDim = new Map<string, { x: string[]; y: (number | null)[] }>();
    for (const r of data.rows as Record<string, unknown>[]) {
      const dim = String(r[groupBy] ?? "unknown");
      if (!byDim.has(dim)) byDim.set(dim, { x: [], y: [] });
      const bucket = byDim.get(dim)!;
      bucket.x.push(String(r[dateCol]));
      const v = r[valueCol];
      bucket.y.push(typeof v === "number" ? v : null);
    }
    return {
      dateCol,
      valueCol,
      series: Array.from(byDim.entries())
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([name, s]) => ({ name, ...s })),
    };
  }, [data, groupBy]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight mono">{view}</h1>
        <p className="text-sm text-[var(--color-muted)] mt-1">
          Time series from <span className="mono">kpi.{view}</span>.
        </p>
      </div>

      <Card className="p-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col text-xs uppercase tracking-wider text-[var(--color-muted)]">
            Start
            <input
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className="mt-1 px-2 py-1 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm mono"
            />
          </label>
          <label className="flex flex-col text-xs uppercase tracking-wider text-[var(--color-muted)]">
            End (exclusive)
            <input
              type="date"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              className="mt-1 px-2 py-1 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm mono"
            />
          </label>
          <label className="flex flex-col text-xs uppercase tracking-wider text-[var(--color-muted)]">
            Group by
            <select
              value={groupBy}
              onChange={(e) => setGroupBy(e.target.value)}
              className="mt-1 px-2 py-1 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm mono"
            >
              <option value="">(none)</option>
              <option value="device">device</option>
              <option value="channel">channel</option>
              <option value="category">category</option>
            </select>
          </label>
          <div className="ml-auto flex items-center gap-2 text-xs text-[var(--color-muted)]">
            {data ? (
              <>
                <Pill tone="neutral">{data.row_count ?? 0} rows</Pill>
                {valueCol ? <Pill tone="accent">{valueCol}</Pill> : null}
              </>
            ) : null}
          </div>
        </div>
      </Card>

      <Card className="p-4 min-h-[360px]">
        <SectionTitle
          title="Time series"
          hint={dateCol ? `x: ${dateCol} · y: ${valueCol ?? "—"}` : undefined}
        />
        {error ? (
          <ErrorMessage error={error} />
        ) : isLoading ? (
          <Loading />
        ) : !data?.rows?.length ? (
          <Empty>
            {data?.note ?? "No rows. Widen the date range or pick another KPI."}
          </Empty>
        ) : !valueCol ? (
          <Empty>No numeric column to plot in this view.</Empty>
        ) : (
          <TimeSeries
            series={series}
            yLabel={valueCol}
            height={360}
          />
        )}
      </Card>
    </div>
  );
}
