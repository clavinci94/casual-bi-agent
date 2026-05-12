"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { Card, ErrorMessage, SectionTitle } from "@/components/ui";

const EXAMPLES = [
  "What happened to mobile conversion rate in early May 2018?",
  "Are there any anomalies in delivery time across regions in April 2018?",
  "Why did the average order value drop in the second half of May 2018?",
];

export default function InvestigatePage() {
  const router = useRouter();
  const [question, setQuestion] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const [model, setModel] = useState("");
  const [maxIterations, setMaxIterations] = useState(10);
  const [advanced, setAdvanced] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = question.trim();
    if (trimmed.length < 5) {
      setError(new Error("Question must be at least 5 characters."));
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.startLlmInvestigation({
        question: trimmed,
        model: model.trim() || undefined,
        max_iterations: maxIterations,
      });
      router.push(`/runs/${res.run_id}`);
    } catch (e) {
      setError(e);
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          New investigation
        </h1>
        <p className="text-sm text-[var(--color-muted)] mt-1">
          Ask the agent a business question. It plans, queries KPIs, runs
          causal inference where appropriate, and writes a finding to the
          audit log. You will land on the run detail page where steps stream
          in as they happen.
        </p>
      </div>

      <Card className="p-6">
        <form onSubmit={submit} className="space-y-4">
          <label className="block">
            <span className="text-xs uppercase tracking-wider text-[var(--color-muted)]">
              Question
            </span>
            <textarea
              autoFocus
              required
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              rows={4}
              placeholder="e.g. Mobile conversion rate dropped in early May 2018 — find the cause and recommend an action."
              className="mt-1 w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] resize-y"
            />
          </label>

          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={() => setAdvanced((v) => !v)}
              className="text-xs text-[var(--color-muted)] hover:text-[var(--color-fg)]"
            >
              {advanced ? "Hide" : "Show"} advanced options
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="px-4 py-2 rounded-lg bg-[var(--color-accent)] text-[var(--color-accent-fg)] font-medium hover:opacity-90 disabled:opacity-50"
            >
              {submitting ? "Starting…" : "Start investigation"}
            </button>
          </div>

          {advanced ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-3 border-t border-[var(--color-border)]">
              <label className="block">
                <span className="text-xs uppercase tracking-wider text-[var(--color-muted)]">
                  Model override
                </span>
                <input
                  type="text"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  placeholder="claude-sonnet-4-6 (default)"
                  className="mt-1 w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-sm mono"
                />
              </label>
              <label className="block">
                <span className="text-xs uppercase tracking-wider text-[var(--color-muted)]">
                  Max tool iterations
                </span>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={maxIterations}
                  onChange={(e) => setMaxIterations(parseInt(e.target.value) || 10)}
                  className="mt-1 w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-sm mono"
                />
              </label>
            </div>
          ) : null}

          {error ? (
            <ErrorMessage
              error={
                error instanceof ApiError && error.status === 503
                  ? new Error(
                      "ANTHROPIC_API_KEY is not configured on the backend. Set it and restart `make api-serve`.",
                    )
                  : error
              }
            />
          ) : null}
        </form>
      </Card>

      <section>
        <SectionTitle title="Examples" />
        <div className="grid gap-2">
          {EXAMPLES.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => setQuestion(q)}
              className="text-left p-3 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] hover:border-[var(--color-accent)] text-sm"
            >
              {q}
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
