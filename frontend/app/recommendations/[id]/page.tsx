"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import useSWR, { useSWRConfig } from "swr";
import { ChevronDown, ChevronUp } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Card, ErrorMessage, Loading, MutedLink, Pill } from "@/components/ui";
import {
  fmtConfidence,
  formatRelativeTime,
  friendlyStatus,
  statusTone,
} from "@/lib/labels";
import { parseRecommendationBody } from "@/lib/recommendation-body";

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

// Preset reactions a manager can apply with one click. Wording is split into
// "lean approve" and "lean reject / clarify" so the chip itself already hints
// at the appropriate decision button.
type CommentSuggestion = {
  label: string;
  text: string;
  intent: "approve" | "reject" | "neutral";
};

const APPROVE_SUGGESTIONS: CommentSuggestion[] = [
  {
    label: "Sofort umsetzen",
    text: "Genehmigt. Umsetzung priorisieren, Status bis Ende der Woche zurückmelden.",
    intent: "approve",
  },
  {
    label: "Mit Auflagen",
    text: "Genehmigt mit Auflagen: bitte vor Umsetzung kurze Rückmeldung an mich.",
    intent: "approve",
  },
  {
    label: "Mit Marketing abstimmen",
    text: "Genehmigt, vorher bitte mit Marketing-Team abstimmen und Kommunikation vorbereiten.",
    intent: "approve",
  },
];

const REJECT_SUGGESTIONS: CommentSuggestion[] = [
  {
    label: "Mehr Daten",
    text: "Verschoben — mehr Daten und längeres Beobachtungsfenster nötig, bevor wir handeln.",
    intent: "reject",
  },
  {
    label: "Alternative gewünscht",
    text: "Abgelehnt — bitte alternative Lösung mit geringerem Risiko vorschlagen.",
    intent: "reject",
  },
  {
    label: "Eskalation",
    text: "An Geschäftsführung eskalieren bevor weitere Schritte erfolgen.",
    intent: "neutral",
  },
];

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
  const [showFull, setShowFull] = useState(false);

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
  const parsed = parseRecommendationBody(data.body);

  return (
    <div className="space-y-6 max-w-3xl">
      <MutedLink href="/">← Zurück zum Dashboard</MutedLink>

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

      {/* Kernaussage — what a manager needs in 5 seconds */}
      <Card className="p-6">
        <h2 className="text-xs uppercase tracking-wider text-[var(--color-muted)] font-medium mb-2">
          Kernaussage
        </h2>
        <p className="text-[17px] font-medium leading-snug">
          {parsed.kernaussage}
        </p>
      </Card>

      {/* Empfohlene Schritte — only when extracted */}
      {parsed.steps.length > 0 ? (
        <Card className="p-6">
          <h2 className="text-xs uppercase tracking-wider text-[var(--color-muted)] font-medium mb-3">
            Empfohlene Schritte
          </h2>
          <ol className="space-y-2.5">
            {parsed.steps.map((s, i) => (
              <li key={i} className="flex gap-3 text-[15px] leading-relaxed">
                <span className="size-6 shrink-0 rounded-full bg-[var(--color-accent)] text-white text-xs font-semibold flex items-center justify-center mt-0.5">
                  {i + 1}
                </span>
                <span>{s}</span>
              </li>
            ))}
          </ol>
        </Card>
      ) : null}

      {/* Vollständige Begründung — collapsed by default */}
      <Card className="p-6">
        <button
          type="button"
          onClick={() => setShowFull((v) => !v)}
          className="w-full flex items-center justify-between text-left"
        >
          <h2 className="text-xs uppercase tracking-wider text-[var(--color-muted)] font-medium">
            Vollständige Begründung
          </h2>
          {showFull ? (
            <ChevronUp className="size-4 text-[var(--color-muted)]" />
          ) : (
            <ChevronDown className="size-4 text-[var(--color-muted)]" />
          )}
        </button>
        {showFull ? (
          <>
            <p className="text-sm whitespace-pre-wrap leading-relaxed mt-3 text-[var(--color-muted)]">
              {parsed.fullBody}
            </p>
            <div className="mt-4 pt-4 border-t border-[var(--color-border)] text-xs text-[var(--color-muted)]">
              Vollständige Beweiskette in der{" "}
              <MutedLink href={`/runs/${data.run_id}`}>
                zugehörigen Analyse
              </MutedLink>
              .
            </div>
          </>
        ) : (
          <p className="text-xs text-[var(--color-muted)] mt-2">
            Klicken Sie, um die ausführliche Beweisführung des Agenten zu lesen.
          </p>
        )}
      </Card>

      {/* Decision form with comment suggestions */}
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

            <div>
              <span className="text-xs uppercase tracking-wider text-[var(--color-muted)] block mb-2">
                Vorgeschlagene Bemerkungen
              </span>
              <div className="space-y-3">
                <div>
                  <div className="text-[11px] text-[var(--color-muted)] mb-1.5">
                    Eher zustimmen
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {APPROVE_SUGGESTIONS.map((s) => (
                      <button
                        key={s.label}
                        type="button"
                        onClick={() => setComment(s.text)}
                        className="px-3 py-1.5 rounded-full text-xs font-medium border border-[var(--color-border)] bg-[var(--color-bg)] hover:border-[var(--color-success)] hover:text-[var(--color-success)] transition-colors"
                      >
                        {s.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="text-[11px] text-[var(--color-muted)] mb-1.5">
                    Eher prüfen / ablehnen
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {REJECT_SUGGESTIONS.map((s) => (
                      <button
                        key={s.label}
                        type="button"
                        onClick={() => setComment(s.text)}
                        className="px-3 py-1.5 rounded-full text-xs font-medium border border-[var(--color-border)] bg-[var(--color-bg)] hover:border-[var(--color-danger)] hover:text-[var(--color-danger)] transition-colors"
                      >
                        {s.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            <label className="block">
              <span className="text-xs uppercase tracking-wider text-[var(--color-muted)]">
                Bemerkung
              </span>
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                rows={3}
                placeholder="Klicken Sie oben einen Vorschlag oder schreiben Sie eigene Worte"
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
