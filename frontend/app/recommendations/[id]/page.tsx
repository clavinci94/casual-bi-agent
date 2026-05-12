"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import useSWR, { useSWRConfig } from "swr";
import { api, ApiError } from "@/lib/api";
import { Card, ErrorMessage, Loading, MutedLink, Pill } from "@/components/ui";
import {
  fmtConfidence,
  formatRelativeTime,
  friendlyStatus,
  statusTone,
} from "@/lib/labels";

function riskTone(level: string) {
  if (level === "high") return "danger" as const;
  if (level === "medium") return "warning" as const;
  return "neutral" as const;
}

function riskLabel(level: string) {
  if (level === "high") return "Hohes Risiko";
  if (level === "medium") return "Mittleres Risiko";
  return "Niedriges Risiko";
}

export default function RecommendationDetail() {
  const params = useParams<{ id: string }>();
  const id = params.id ?? "";

  const { data, error, isLoading } = useSWR(["recommendation", id], () =>
    api.getRecommendation(id),
  );
  const { mutate } = useSWRConfig();

  const [approver, setApprover] = useState("");
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<unknown>(null);
  const [submitted, setSubmitted] = useState<string | null>(null);

  async function decide(decision: "approve" | "reject") {
    if (!approver.trim()) {
      setSubmitError(new Error("Bitte tragen Sie Ihren Namen ein."));
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
      mutate(["recommendation", id]);
      mutate(
        (k) =>
          Array.isArray(k) === false &&
          typeof k === "string" &&
          k.startsWith("recommendations:"),
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
          <p className="text-sm">
            Empfehlung nicht gefunden.{" "}
            <MutedLink href="/">Zurück zum Dashboard</MutedLink>
          </p>
        </Card>
      );
    }
    return <ErrorMessage error={error} />;
  }
  if (isLoading || !data) return <Loading />;

  const isPending = data.status === "pending";

  return (
    <div className="space-y-6 max-w-3xl">
      <MutedLink href="/">← Zurück zum Dashboard</MutedLink>

      {/* Executive-memo style header */}
      <header>
        <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-[var(--color-muted)] font-medium">
          Empfehlung
        </div>
        <h1 className="text-2xl font-semibold tracking-tight mt-1 leading-tight">
          {data.title}
        </h1>
        <div className="flex flex-wrap items-center gap-2 mt-3">
          <Pill tone={riskTone(data.risk_level)}>
            {riskLabel(data.risk_level)}
          </Pill>
          {fmtConfidence(data.confidence) ? (
            <Pill tone="neutral">{fmtConfidence(data.confidence)}</Pill>
          ) : null}
          <Pill tone={statusTone(data.status)}>
            {friendlyStatus(data.status)}
          </Pill>
          <span className="text-xs text-[var(--color-muted)]">
            {formatRelativeTime(data.created_at)}
          </span>
        </div>
      </header>

      {/* The actual finding — generous typography for an executive read */}
      <Card className="p-6">
        <h2 className="text-xs uppercase tracking-wider text-[var(--color-muted)] font-medium mb-2">
          Befund und Begründung
        </h2>
        <p className="text-[15px] whitespace-pre-wrap leading-relaxed">
          {data.body}
        </p>
        <div className="mt-4 pt-4 border-t border-[var(--color-border)] text-xs text-[var(--color-muted)]">
          Vollständige Beweiskette in der{" "}
          <MutedLink href={`/runs/${data.run_id}`}>
            zugehörigen Analyse
          </MutedLink>
          .
        </div>
      </Card>

      {/* Decision form */}
      <Card className="p-6">
        <h2 className="text-xs uppercase tracking-wider text-[var(--color-muted)] font-medium mb-3">
          Ihre Entscheidung
        </h2>
        {!isPending ? (
          <p className="text-sm">
            Diese Empfehlung wurde bereits{" "}
            <strong>{friendlyStatus(data.status)}</strong>. Keine weitere
            Aktion erforderlich.
          </p>
        ) : (
          <div className="space-y-4">
            <p className="text-sm text-[var(--color-muted)] leading-relaxed">
              Mit Ihrer Freigabe wird die Empfehlung als <em>angenommen</em>{" "}
              protokolliert — revisionssicher und mit Ihrer Identität
              verknüpft. Eine Ablehnung wird ebenfalls festgehalten und
              fliesst in das Lernen des Systems ein.
            </p>
            <label className="block">
              <span className="text-xs uppercase tracking-wider text-[var(--color-muted)]">
                Ihr Name (Freigabe-Identität)
              </span>
              <input
                type="text"
                required
                value={approver}
                onChange={(e) => setApprover(e.target.value)}
                placeholder="z.B. C. Vinci"
                className="mt-1 w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
              />
            </label>
            <label className="block">
              <span className="text-xs uppercase tracking-wider text-[var(--color-muted)]">
                Bemerkung (optional)
              </span>
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                rows={3}
                placeholder="z.B. Rollback bestätigt, Marketing informiert"
                className="mt-1 w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
              />
            </label>
            {submitError ? <ErrorMessage error={submitError} /> : null}
            {submitted ? (
              <Pill tone="success">
                Entscheidung protokolliert · Status: {friendlyStatus(submitted)}
              </Pill>
            ) : (
              <div className="flex gap-2 pt-1">
                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => decide("approve")}
                  className="px-5 py-2 rounded-lg bg-[var(--color-success)] text-white font-medium disabled:opacity-50 hover:opacity-90"
                >
                  Freigeben
                </button>
                <button
                  type="button"
                  disabled={submitting}
                  onClick={() => decide("reject")}
                  className="px-5 py-2 rounded-lg bg-[var(--color-danger)] text-white font-medium disabled:opacity-50 hover:opacity-90"
                >
                  Ablehnen
                </button>
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}
