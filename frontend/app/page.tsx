"use client";

import { useReadiness, useRecommendations, useRuns } from "@/lib/hooks";
import {
  Card,
  Empty,
  ErrorMessage,
  Loading,
  MutedLink,
  Pill,
  SectionTitle,
} from "@/components/ui";

function fmtDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function riskTone(level: string) {
  if (level === "high") return "danger" as const;
  if (level === "medium") return "warning" as const;
  return "neutral" as const;
}

export default function Dashboard() {
  const ready = useReadiness();
  const pending = useRecommendations("pending");
  const runs = useRuns(8);

  return (
    <div className="space-y-10">
      <section className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Causal BI overview
          </h1>
          <p className="text-sm text-[var(--color-muted)] mt-1">
            Pending decisions, recent investigations, and system health.
          </p>
        </div>
        <a
          href="/investigate"
          className="shrink-0 px-4 py-2 rounded-lg bg-[var(--color-accent)] text-[var(--color-accent-fg)] font-medium hover:opacity-90"
        >
          + New investigation
        </a>
      </section>

      {/* Health row */}
      <section className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <HealthTile
          label="API"
          value={ready.data?.status}
          loading={ready.isLoading}
        />
        <HealthTile
          label="Database"
          value={ready.data?.db}
          loading={ready.isLoading}
        />
        <HealthTile
          label="R service"
          value={ready.data?.r_service}
          loading={ready.isLoading}
        />
        <HealthTile
          label="Version"
          value={ready.data?.version}
          loading={ready.isLoading}
          plain
        />
      </section>

      {/* Pending HITL queue */}
      <section>
        <SectionTitle
          title="Pending decisions"
          hint={pending.data ? `${pending.data.length} open` : undefined}
          action={<MutedLink href="/runs">View all runs →</MutedLink>}
        />
        <Card>
          {pending.error ? (
            <div className="p-4">
              <ErrorMessage error={pending.error} />
            </div>
          ) : pending.isLoading ? (
            <div className="p-4">
              <Loading />
            </div>
          ) : !pending.data || pending.data.length === 0 ? (
            <Empty>No pending recommendations — the queue is clear.</Empty>
          ) : (
            <ul className="divide-y divide-[var(--color-border)]">
              {pending.data.slice(0, 8).map((r) => (
                <li key={r.rec_id} className="p-4 hover:bg-[var(--color-bg)]">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <Pill tone={riskTone(r.risk_level)}>
                          {r.risk_level}
                        </Pill>
                        {typeof r.confidence === "number" ? (
                          <Pill tone="neutral">
                            {(r.confidence * 100).toFixed(0)}% confidence
                          </Pill>
                        ) : null}
                        <span className="text-xs text-[var(--color-muted)]">
                          {fmtDate(r.created_at)}
                        </span>
                      </div>
                      <MutedLink href={`/recommendations/${r.rec_id}`}>
                        <span className="font-medium text-[var(--color-fg)] hover:underline">
                          {r.title}
                        </span>
                      </MutedLink>
                      <p className="text-sm text-[var(--color-muted)] mt-1 line-clamp-2">
                        {r.body}
                      </p>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </section>

      {/* Recent runs */}
      <section>
        <SectionTitle
          title="Recent investigations"
          action={<MutedLink href="/runs">All runs →</MutedLink>}
        />
        <Card>
          {runs.error ? (
            <div className="p-4">
              <ErrorMessage error={runs.error} />
            </div>
          ) : runs.isLoading ? (
            <div className="p-4">
              <Loading />
            </div>
          ) : !runs.data || runs.data.length === 0 ? (
            <Empty>No runs yet. Trigger one with `make investigate Q=…`.</Empty>
          ) : (
            <ul className="divide-y divide-[var(--color-border)]">
              {runs.data.map((r) => (
                <li key={r.run_id} className="p-4 hover:bg-[var(--color-bg)]">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <Pill tone="neutral">{r.trigger}</Pill>
                        <Pill
                          tone={r.status === "ok" ? "success" : "neutral"}
                        >
                          {r.status}
                        </Pill>
                        <span className="text-xs text-[var(--color-muted)]">
                          {fmtDate(r.started_at)}
                        </span>
                      </div>
                      <MutedLink href={`/runs/${r.run_id}`}>
                        <span className="font-medium text-[var(--color-fg)] hover:underline">
                          {r.prompt ?? "(no prompt)"}
                        </span>
                      </MutedLink>
                    </div>
                    <span className="text-xs text-[var(--color-muted)] mono shrink-0">
                      {r.run_id.slice(0, 8)}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </section>
    </div>
  );
}

function HealthTile({
  label,
  value,
  loading,
  plain = false,
}: {
  label: string;
  value: string | undefined;
  loading: boolean;
  plain?: boolean;
}) {
  return (
    <Card className="px-4 py-3">
      <div className="text-xs uppercase tracking-wider text-[var(--color-muted)]">
        {label}
      </div>
      <div className="mt-1 flex items-center gap-2">
        {loading ? (
          <span className="text-sm text-[var(--color-muted)] animate-pulse">
            …
          </span>
        ) : plain ? (
          <span className="mono text-sm">{value ?? "—"}</span>
        ) : (
          <Pill tone={value === "ok" ? "success" : "danger"}>
            {value ?? "—"}
          </Pill>
        )}
      </div>
    </Card>
  );
}
