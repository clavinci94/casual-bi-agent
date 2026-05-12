"use client";

import { useRuns } from "@/lib/hooks";
import {
  Card,
  Empty,
  ErrorMessage,
  Loading,
  MutedLink,
  Pill,
} from "@/components/ui";

function fmtDuration(startISO: string, endISO: string | null): string {
  if (!endISO) return "running";
  const ms = new Date(endISO).getTime() - new Date(startISO).getTime();
  if (ms < 1000) return `${ms} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  return `${(ms / 60_000).toFixed(1)} min`;
}

export default function RunsIndex() {
  const { data, error, isLoading } = useRuns(100);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Investigations</h1>
        <p className="text-sm text-[var(--color-muted)] mt-1">
          Every agent run, with full audit trail.
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
          <Empty>No runs yet.</Empty>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-wider text-[var(--color-muted)] border-b border-[var(--color-border)]">
              <tr>
                <th className="text-left px-4 py-2">When</th>
                <th className="text-left px-4 py-2">Trigger</th>
                <th className="text-left px-4 py-2">Prompt</th>
                <th className="text-left px-4 py-2">Status</th>
                <th className="text-right px-4 py-2">Duration</th>
                <th className="text-right px-4 py-2">Cost</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {data.map((r) => (
                <tr key={r.run_id} className="hover:bg-[var(--color-bg)]">
                  <td className="px-4 py-2 whitespace-nowrap text-[var(--color-muted)] text-xs">
                    {new Date(r.started_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-2">
                    <Pill tone="neutral">{r.trigger}</Pill>
                  </td>
                  <td className="px-4 py-2 max-w-md truncate">
                    <MutedLink href={`/runs/${r.run_id}`}>
                      {r.prompt ?? "(no prompt)"}
                    </MutedLink>
                  </td>
                  <td className="px-4 py-2">
                    <Pill tone={r.status === "ok" ? "success" : "neutral"}>
                      {r.status}
                    </Pill>
                  </td>
                  <td className="px-4 py-2 text-right text-xs mono">
                    {fmtDuration(r.started_at, r.finished_at)}
                  </td>
                  <td className="px-4 py-2 text-right text-xs mono">
                    {r.cost_usd != null ? `$${r.cost_usd.toFixed(3)}` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
