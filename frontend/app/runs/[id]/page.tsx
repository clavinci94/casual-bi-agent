"use client";

import { useMemo } from "react";
import { useParams } from "next/navigation";
import useSWR from "swr";
import { api } from "@/lib/api";
import type { AgentStep, RunDetail, ToolCall } from "@/lib/types";
import {
  Card,
  Empty,
  ErrorMessage,
  Loading,
  MutedLink,
  Pill,
} from "@/components/ui";
import {
  formatRelativeTime,
  friendlyStatus,
  friendlyTrigger,
  statusTone,
} from "@/lib/labels";

const POLL_MS = 2000;

// User-facing names for the tools the investigator calls. Anything not in
// the map falls back to its raw name — mostly fine for power users.
const TOOL_DESCRIPTIONS: Record<string, string> = {
  kpi_query: "Kennzahlen abgefragt",
  releases_in_window: "Release-Historie geprüft",
  campaigns_in_window: "Marketing-Kampagnen geprüft",
  kg_lookup_past_decisions: "Frühere Entscheidungen nachgeschlagen",
  causal_impact_conversion: "Kausalanalyse durchgeführt",
  evalue: "Robustheit (E-Value) bestimmt",
  power_test: "Statistische Power geprüft",
  record_finding: "Empfehlung festgehalten",
};

function TechnicalStepRow({
  step,
  calls,
}: {
  step: AgentStep;
  calls: ToolCall[];
}) {
  const isTool = step.action.startsWith("tool::");
  const isPlan = step.action === "plan";
  const tone = isTool ? "accent" : isPlan ? "warning" : "neutral";
  const callsForStep = calls.filter((c) => {
    if (!isTool) return false;
    const expected = step.action.replace("tool::", "");
    return c.tool_name === expected;
  });

  return (
    <li className="px-4 py-3">
      <div className="flex items-center gap-2 text-sm">
        <span className="mono text-xs text-[var(--color-muted)] w-6 text-right">
          {step.seq}.
        </span>
        <Pill tone={tone}>{step.agent_name}</Pill>
        <span className="mono text-sm">{step.action}</span>
        {step.latency_ms != null ? (
          <span className="text-xs text-[var(--color-muted)] mono ml-auto">
            {step.latency_ms} ms
          </span>
        ) : null}
      </div>

      {isPlan && step.output && typeof step.output.plan === "string" ? (
        <pre className="mt-2 ml-8 text-xs bg-[var(--color-bg)] border border-[var(--color-border)] rounded-md p-3 whitespace-pre-wrap mono">
          {step.output.plan as string}
        </pre>
      ) : null}

      {callsForStep.length > 0 ? (
        <div className="mt-2 ml-8 space-y-1">
          {callsForStep.map((c) => (
            <div
              key={c.call_id}
              className="text-xs bg-[var(--color-bg)] border border-[var(--color-border)] rounded-md p-2"
            >
              <div className="flex items-center gap-2">
                <span className="mono">{c.tool_name}</span>
                {c.error ? (
                  <Pill tone="danger">error</Pill>
                ) : (
                  <Pill tone="success">{c.rows_returned} rows</Pill>
                )}
              </div>
              <pre className="mt-1 mono whitespace-pre-wrap text-[var(--color-muted)] break-all">
                {JSON.stringify(c.params)}
              </pre>
              {c.error ? (
                <pre className="mt-1 mono text-[var(--color-danger)] whitespace-pre-wrap">
                  {c.error}
                </pre>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      {!isTool && !isPlan && step.output ? (
        <pre className="mt-2 ml-8 text-xs bg-[var(--color-bg)] border border-[var(--color-border)] rounded-md p-2 whitespace-pre-wrap mono text-[var(--color-muted)] break-all">
          {JSON.stringify(step.output, null, 2)}
        </pre>
      ) : null}
    </li>
  );
}

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id ?? "";

  const { data, error, isLoading } = useSWR<RunDetail>(
    id ? ["run", id] : null,
    () => api.getRun(id),
    {
      refreshInterval: (latest) =>
        latest?.run?.status === "running" ? POLL_MS : 0,
    },
  );

  // Surface the agent's plan + any recommendations recorded during the
  // run as the manager-readable summary. The full audit trail stays in
  // the collapsible section below.
  const summary = useMemo(() => {
    if (!data) return null;
    const planStep = data.steps.find((s) => s.action === "plan");
    const plan =
      planStep?.output && typeof planStep.output.plan === "string"
        ? (planStep.output.plan as string)
        : null;
    const toolsUsed = Array.from(
      new Set(
        data.tool_calls
          .map((c) => TOOL_DESCRIPTIONS[c.tool_name] ?? c.tool_name)
          .filter((s) => s !== "Empfehlung festgehalten"),
      ),
    );
    const findingCount = data.tool_calls.filter(
      (c) => c.tool_name === "record_finding" && !c.error,
    ).length;
    return { plan, toolsUsed, findingCount };
  }, [data]);

  if (error) return <ErrorMessage error={error} />;
  if (isLoading || !data) return <Loading />;

  const isRunning = data.run.status === "running";

  return (
    <div className="space-y-6 max-w-4xl">
      <MutedLink href="/runs">← Zurück zur Übersicht</MutedLink>

      {/* Header */}
      <header>
        <div className="text-xs uppercase tracking-wider text-[var(--color-muted)] font-medium">
          Analyse
        </div>
        <h1 className="text-2xl font-semibold tracking-tight mt-1 leading-tight">
          {data.run.prompt ?? "(ohne Titel)"}
        </h1>
        <div className="flex flex-wrap items-center gap-2 mt-3">
          <Pill tone={statusTone(data.run.status)}>
            {friendlyStatus(data.run.status)}
          </Pill>
          <span className="text-xs text-[var(--color-muted)]">
            {friendlyTrigger(data.run.trigger)} ·{" "}
            {formatRelativeTime(data.run.started_at)}
          </span>
          {isRunning ? (
            <span className="text-xs text-[var(--color-muted)] flex items-center gap-1 ml-2">
              <span className="size-1.5 rounded-full bg-[var(--color-accent)] animate-pulse" />
              aktualisiert alle {POLL_MS / 1000} s
            </span>
          ) : null}
        </div>
      </header>

      {/* Manager-readable summary */}
      <Card className="p-6">
        <h2 className="text-xs uppercase tracking-wider text-[var(--color-muted)] font-medium mb-3">
          Was das System gemacht hat
        </h2>

        {summary?.toolsUsed.length ? (
          <div className="mb-4">
            <div className="text-xs text-[var(--color-muted)] mb-2">
              Durchgeführte Schritte
            </div>
            <ul className="space-y-1.5">
              {summary.toolsUsed.map((t, i) => (
                <li key={i} className="flex items-start gap-2 text-sm">
                  <span className="text-[var(--color-success)] mt-0.5">✓</span>
                  <span>{t}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : isRunning ? (
          <p className="text-sm text-[var(--color-muted)]">
            Der Agent erstellt gerade den Untersuchungsplan…
          </p>
        ) : (
          <p className="text-sm text-[var(--color-muted)]">
            Keine Schritte ausgeführt.
          </p>
        )}

        {summary?.findingCount ? (
          <div className="mt-4 pt-4 border-t border-[var(--color-border)] text-sm">
            <strong>{summary.findingCount}</strong>{" "}
            {summary.findingCount === 1 ? "Empfehlung" : "Empfehlungen"}{" "}
            festgehalten — zu finden im Dashboard unter „Empfehlungen mit
            offener Freigabe“.
          </div>
        ) : null}

        {summary?.plan ? (
          <details className="mt-4 pt-4 border-t border-[var(--color-border)]">
            <summary className="cursor-pointer text-sm font-medium text-[var(--color-muted)] hover:text-[var(--color-fg)]">
              Untersuchungsplan anzeigen
            </summary>
            <pre className="mt-3 text-xs bg-[var(--color-bg)] border border-[var(--color-border)] rounded-md p-3 whitespace-pre-wrap">
              {summary.plan}
            </pre>
          </details>
        ) : null}
      </Card>

      {/* Full audit trail, collapsed by default */}
      <details className="group">
        <summary className="cursor-pointer text-sm text-[var(--color-muted)] hover:text-[var(--color-fg)] select-none">
          <span className="font-medium">Technische Details</span> ·{" "}
          {data.steps.length} Schritte, {data.tool_calls.length} Tool-Aufrufe
        </summary>
        <Card className="mt-3">
          {data.steps.length === 0 ? (
            <Empty>
              {isRunning
                ? "Warte auf den ersten Schritt …"
                : "Keine Schritte protokolliert."}
            </Empty>
          ) : (
            <ul className="divide-y divide-[var(--color-border)]">
              {data.steps.map((s) => (
                <TechnicalStepRow
                  key={s.step_id}
                  step={s}
                  calls={data.tool_calls}
                />
              ))}
            </ul>
          )}
        </Card>
        <p className="mt-3 text-xs text-[var(--color-muted)]">
          Diese Sicht ist für technische Reviews — sie zeigt jeden einzelnen
          LLM-Call, jeden SQL-Query und jedes statistische Verfahren mit
          den exakten Parametern.
        </p>
      </details>
    </div>
  );
}

