"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import useSWR, { useSWRConfig } from "swr";
import { api, ApiError } from "@/lib/api";
import {
  Card,
  ErrorMessage,
  Loading,
  MutedLink,
  Pill,
  SectionTitle,
} from "@/components/ui";

function riskTone(level: string) {
  if (level === "high") return "danger" as const;
  if (level === "medium") return "warning" as const;
  return "neutral" as const;
}

export default function RecommendationDetail() {
  const params = useParams<{ id: string }>();
  const id = params.id ?? "";

  const { data, error, isLoading } = useSWR(
    ["recommendation", id],
    () => api.getRecommendation(id),
  );
  const { mutate } = useSWRConfig();

  const [approver, setApprover] = useState("");
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<unknown>(null);
  const [submitted, setSubmitted] = useState<string | null>(null);

  async function decide(decision: "approve" | "reject") {
    if (!approver.trim()) {
      setSubmitError(new Error("Approver name is required."));
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      const res = await api.decideRecommendation(id, {
        decision,
        approver: approver.trim(),
        comment: comment.trim() || undefined,
      });
      setSubmitted(res.status);
      // Refresh this recommendation + invalidate any list views.
      mutate(["recommendation", id]);
      mutate(
        (k) => Array.isArray(k) === false && typeof k === "string" && k.startsWith("recommendations:"),
      );
    } catch (e) {
      setSubmitError(e);
    } finally {
      setSubmitting(false);
    }
  }

  if (error) {
    if (error instanceof ApiError && error.status === 404) {
      return (
        <Card className="p-6">
          <p className="text-sm">Recommendation <span className="mono">{id}</span> not found.</p>
        </Card>
      );
    }
    return <ErrorMessage error={error} />;
  }
  if (isLoading || !data) return <Loading />;

  const isPending = data.status === "pending";

  return (
    <div className="space-y-8">
      <div>
        <div className="flex items-center gap-2 text-xs text-[var(--color-muted)] mono">
          <span>{id}</span>
        </div>
        <h1 className="text-2xl font-semibold tracking-tight mt-1">
          {data.title}
        </h1>
        <div className="flex items-center gap-2 mt-2">
          <Pill tone={riskTone(data.risk_level)}>{data.risk_level}</Pill>
          {typeof data.confidence === "number" ? (
            <Pill tone="neutral">
              {(data.confidence * 100).toFixed(0)}% confidence
            </Pill>
          ) : null}
          <Pill
            tone={
              data.status === "approved"
                ? "success"
                : data.status === "rejected"
                  ? "danger"
                  : "accent"
            }
          >
            {data.status}
          </Pill>
          <span className="text-xs text-[var(--color-muted)]">
            From run <MutedLink href={`/runs/${data.run_id}`}>{data.run_id.slice(0, 8)}</MutedLink>
          </span>
        </div>
      </div>

      <Card className="p-6">
        <SectionTitle title="Finding" />
        <p className="text-sm whitespace-pre-wrap leading-relaxed">{data.body}</p>
      </Card>

      <Card className="p-6">
        <SectionTitle title="Decision" />
        {!isPending ? (
          <p className="text-sm text-[var(--color-muted)]">
            This recommendation is already <strong>{data.status}</strong>. No
            further action available.
          </p>
        ) : (
          <div className="space-y-4">
            <label className="block">
              <span className="text-xs uppercase tracking-wider text-[var(--color-muted)]">
                Approver name
              </span>
              <input
                type="text"
                required
                value={approver}
                onChange={(e) => setApprover(e.target.value)}
                placeholder="e.g. claudio.vinci"
                className="mt-1 w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-sm mono focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
              />
            </label>
            <label className="block">
              <span className="text-xs uppercase tracking-wider text-[var(--color-muted)]">
                Comment (optional)
              </span>
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                rows={3}
                className="mt-1 w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
              />
            </label>
            {submitError ? <ErrorMessage error={submitError} /> : null}
            {submitted ? (
              <Pill tone="success">Decision recorded · status: {submitted}</Pill>
            ) : (
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => decide("approve")}
                  className="px-4 py-2 rounded-lg bg-[var(--color-success)] text-white font-medium disabled:opacity-50 hover:opacity-90"
                >
                  Approve
                </button>
                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => decide("reject")}
                  className="px-4 py-2 rounded-lg bg-[var(--color-danger)] text-white font-medium disabled:opacity-50 hover:opacity-90"
                >
                  Reject
                </button>
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
