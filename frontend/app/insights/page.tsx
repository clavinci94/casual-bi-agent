"use client";

import { useState } from "react";
import { useInsights } from "@/lib/hooks";
import { Card, Empty, ErrorMessage, Loading, Pill } from "@/components/ui";

function severityTone(s: string | null | undefined) {
  if (s === "high") return "danger" as const;
  if (s === "medium") return "warning" as const;
  if (s === "low") return "neutral" as const;
  return "neutral" as const;
}

function fmtPct(v: number | undefined) {
  if (v == null || !Number.isFinite(v)) return null;
  const pct = v * 100;
  const sign = pct > 0 ? "+" : pct < 0 ? "−" : "";
  return `${sign}${Math.abs(pct).toFixed(1)} %`;
}

export default function InsightsPage() {
  const [showTests, setShowTests] = useState(false);
  const { data, error, isLoading } = useInsights(
    50,
    showTests ? [] : ["test"],
  );

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Knowledge graph
          </h1>
          <p className="text-sm text-[var(--color-muted)] mt-1">
            What the system has learned. Each recommendation becomes an{" "}
            <span className="mono">Insight</span> node; HITL approvals create{" "}
            <span className="mono">Decision</span> edges; outcomes close the loop.
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm text-[var(--color-muted)] cursor-pointer select-none">
          <input
            type="checkbox"
            checked={showTests}
            onChange={(e) => setShowTests(e.target.checked)}
            className="accent-[var(--color-accent)]"
          />
          Show test insights
        </label>
      </div>

      <Card>
        {error ? (
          <div className="p-4">
            <ErrorMessage error={error} />
          </div>
        ) : isLoading ? (
          <div className="p-4">
            <Loading />
          </div>
        ) : !data || data.length === 0 ? (
          <Empty>
            No insights yet. Approving a recommendation creates the first
            Insight + Decision pair.
          </Empty>
        ) : (
          <ul className="divide-y divide-[var(--color-border)]">
            {data.map((i, idx) => {
              const p = i.properties ?? {};
              const title = p.title ?? "(untitled)";
              const delta = fmtPct(p.relative_change as number | undefined);
              const period =
                p.period_start && p.period_end
                  ? `${p.period_start} → ${p.period_end}`
                  : null;
              return (
                <li key={i.insight_id ?? idx} className="p-4">
                  <div className="flex flex-wrap items-center gap-2 mb-1">
                    <Pill tone="accent">Insight</Pill>
                    {p.severity ? (
                      <Pill tone={severityTone(p.severity)}>
                        {p.severity}
                      </Pill>
                    ) : null}
                    {p.component ? (
                      <Pill tone="neutral">{String(p.component)}</Pill>
                    ) : null}
                    {p.kpi ? (
                      <span className="text-xs text-[var(--color-muted)] mono">
                        {String(p.kpi)}
                      </span>
                    ) : null}
                    <span className="text-xs text-[var(--color-muted)] ml-auto">
                      {new Date(i.created_at).toLocaleString()}
                    </span>
                  </div>
                  <div className="font-medium">{title}</div>
                  <div className="flex flex-wrap gap-3 mt-1 text-xs text-[var(--color-muted)]">
                    {delta ? (
                      <span className="mono">change: {delta}</span>
                    ) : null}
                    {period ? <span className="mono">{period}</span> : null}
                    <span className="mono">{i.insight_id}</span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}
