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
  // Hide pytest fixtures from the dashboard so managers only see real work.
  // Power users can still drop the filter on /runs (which keeps everything).
  const pending = useRecommendations("pending", ["test"]);
  const runs = useRuns(8, ["test"]);

  return (
    <div className="space-y-10">
      {/* Enterprise hero — what the platform does + business value. */}
      <section className="relative overflow-hidden rounded-3xl border border-[var(--color-border)] bg-gradient-to-br from-[var(--color-surface)] via-[var(--color-surface)] to-[color-mix(in_oklch,var(--color-accent)_8%,var(--color-surface))] p-8 sm:p-10">
        <div className="max-w-3xl">
          <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-[var(--color-accent)] font-semibold">
            <span className="size-1.5 rounded-full bg-[var(--color-accent)]" />
            Agentic Business Intelligence
          </div>

          <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight mt-3 leading-tight">
            Vom <span className="text-[var(--color-muted)]">Was</span> zum{" "}
            <span className="text-[var(--color-accent)]">Warum</span> —
            in unter einer Minute.
          </h1>

          <p className="mt-4 text-base sm:text-lg text-[var(--color-fg)] leading-relaxed">
            Causal BI überwacht Ihre Geschäftskennzahlen autonom, erkennt
            Anomalien proaktiv und beweist mit statistischer Kausalanalyse,{" "}
            <em>warum</em> sie auftreten. Jede Empfehlung wird mit Effektgrösse,
            Konfidenzintervall und Sensitivitätsanalyse vorgelegt — und
            durchläuft Ihre Freigabe, bevor sie wirksam wird.
          </p>

          <p className="mt-3 text-sm text-[var(--color-muted)] leading-relaxed">
            Klassische BI-Tools zeigen Zahlen. Generative-AI-Tools formulieren
            Vermutungen. Diese Plattform liefert nachvollziehbare,
            revisionssichere Entscheidungsgrundlagen — und lernt aus jeder
            getroffenen Entscheidung weiter.
          </p>

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <a
              href="/investigate"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-[var(--color-accent)] text-[var(--color-accent-fg)] font-medium hover:opacity-90 shadow-sm"
            >
              Untersuchung starten
              <span aria-hidden="true">→</span>
            </a>
            <a
              href="/kpis"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg border border-[var(--color-border)] text-[var(--color-fg)] hover:bg-[var(--color-bg)]"
            >
              KPIs ansehen
            </a>
          </div>
        </div>
      </section>

      {/* Value pillars — three short cards making the proposition concrete. */}
      <section className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <ValuePillar
          title="Proaktive Anomalie-Erkennung"
          body="Das System scannt Ihre KPIs kontinuierlich und flaggt statistisch signifikante Abweichungen — ohne dass jemand nachfragen muss."
        />
        <ValuePillar
          title="Kausalanalyse statt Korrelation"
          body="Bayesian Structural Time Series und Sensitivitätstests trennen echte Wirkungsbeziehungen von Zufallseffekten. Sie sehen die Effektgrösse mit 95 %-Konfidenzintervall und p-Wert."
        />
        <ValuePillar
          title="Human-in-the-Loop"
          body="Keine Massnahme wird ohne Ihre Freigabe wirksam. Jede Empfehlung trägt die vollständige Beweiskette mit — revisionssicher dokumentiert."
        />
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

function ValuePillar({ title, body }: { title: string; body: string }) {
  return (
    <Card className="p-5">
      <h3 className="text-sm font-semibold tracking-tight">{title}</h3>
      <p className="mt-2 text-sm text-[var(--color-muted)] leading-relaxed">
        {body}
      </p>
    </Card>
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
