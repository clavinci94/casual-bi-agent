"use client";

import { useInsights } from "@/lib/hooks";
import {
  Card,
  Empty,
  ErrorMessage,
  Loading,
  Pill,
} from "@/components/ui";

export default function InsightsPage() {
  const { data, error, isLoading } = useInsights(50);

  return (
    <div className="space-y-6">
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
            {data.map((i, idx) => (
              <li key={i.node_id ?? idx} className="p-4">
                <div className="flex items-center gap-2 mb-1">
                  <Pill tone="accent">Insight</Pill>
                  {i.component ? (
                    <Pill tone="neutral">{String(i.component)}</Pill>
                  ) : null}
                  {i.created_at ? (
                    <span className="text-xs text-[var(--color-muted)]">
                      {new Date(String(i.created_at)).toLocaleString()}
                    </span>
                  ) : null}
                </div>
                <div className="font-medium">{i.title ?? "(untitled)"}</div>
                <div className="text-xs text-[var(--color-muted)] mono mt-1">
                  {i.node_id}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
