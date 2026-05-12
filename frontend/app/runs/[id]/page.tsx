"use client";

import { useParams } from "next/navigation";
import { useRun } from "@/lib/hooks";
import type { AgentStep, ToolCall } from "@/lib/types";
import {
  Card,
  Empty,
  ErrorMessage,
  Loading,
  Pill,
  SectionTitle,
} from "@/components/ui";

function StepRow({ step, calls }: { step: AgentStep; calls: ToolCall[] }) {
  const isTool = step.action.startsWith("tool::");
  const isPlan = step.action === "plan";
  const tone = isTool ? "accent" : isPlan ? "warning" : "neutral";
  const callsForStep = calls.filter((c) => {
    // tool_calls aren't directly attached to a step in the API payload,
    // but every tool-call step has exactly one matching tool_name.
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

export default function RunDetail() {
  const params = useParams<{ id: string }>();
  const id = params.id ?? "";
  const { data, error, isLoading } = useRun(id);

  if (error) return <ErrorMessage error={error} />;
  if (isLoading || !data) return <Loading />;

  return (
    <div className="space-y-8">
      <div>
        <div className="flex items-center gap-2 text-xs text-[var(--color-muted)] mono">
          <span>{id}</span>
        </div>
        <h1 className="text-2xl font-semibold tracking-tight mt-1">
          {data.run.prompt ?? "(no prompt)"}
        </h1>
        <div className="flex items-center gap-2 mt-2">
          <Pill tone="neutral">{data.run.trigger}</Pill>
          <Pill tone={data.run.status === "ok" ? "success" : "neutral"}>
            {data.run.status}
          </Pill>
          <span className="text-xs text-[var(--color-muted)]">
            started {new Date(data.run.started_at).toLocaleString()}
          </span>
        </div>
      </div>

      <section>
        <SectionTitle
          title="Audit trail"
          hint={`${data.steps.length} steps · ${data.tool_calls.length} tool calls`}
        />
        <Card>
          {data.steps.length === 0 ? (
            <Empty>No steps recorded.</Empty>
          ) : (
            <ul className="divide-y divide-[var(--color-border)]">
              {data.steps.map((s) => (
                <StepRow key={s.step_id} step={s} calls={data.tool_calls} />
              ))}
            </ul>
          )}
        </Card>
      </section>
    </div>
  );
}
