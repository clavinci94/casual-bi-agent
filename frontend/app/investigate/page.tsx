"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { Card, ErrorMessage, SectionTitle } from "@/components/ui";

const EXAMPLES = [
  "Was ist mit der Mobile Conversion Rate Anfang Mai 2018 passiert?",
  "Gibt es Auffälligkeiten bei den Lieferzeiten zwischen Regionen im April 2018?",
  "Warum ist der durchschnittliche Bestellwert in der zweiten Maihälfte 2018 gefallen?",
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
      setError(new Error("Bitte mindestens 5 Zeichen eingeben."));
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
          Neue Untersuchung
        </h1>
        <p className="text-sm text-[var(--color-muted)] mt-1 leading-relaxed">
          Stellen Sie eine geschäftliche Frage. Das System plant die
          Untersuchung, fragt Kennzahlen ab, führt bei Bedarf
          Kausalanalysen durch und hinterlegt das Ergebnis als
          freigabefähige Empfehlung. Sie landen anschliessend direkt auf
          der Detailseite, wo der Fortschritt live mitläuft.
        </p>
      </div>

      <Card className="p-6">
        <form onSubmit={submit} className="space-y-4">
          <label className="block">
            <span className="text-xs uppercase tracking-wider text-[var(--color-muted)]">
              Frage
            </span>
            <textarea
              autoFocus
              required
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              rows={4}
              placeholder="z.B. Die Mobile Conversion Rate ist Anfang Mai 2018 gefallen — Ursache finden und Massnahme vorschlagen."
              className="mt-1 w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] resize-y"
            />
          </label>

          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={() => setAdvanced((v) => !v)}
              className="text-xs text-[var(--color-muted)] hover:text-[var(--color-fg)]"
            >
              {advanced ? "Erweiterte Optionen ausblenden" : "Erweiterte Optionen anzeigen"}
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="px-4 py-2 rounded-lg bg-[var(--color-accent)] text-[var(--color-accent-fg)] font-medium hover:opacity-90 disabled:opacity-50"
            >
              {submitting ? "Wird gestartet …" : "Untersuchung starten"}
            </button>
          </div>

          {advanced ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-3 border-t border-[var(--color-border)]">
              <label className="block">
                <span className="text-xs uppercase tracking-wider text-[var(--color-muted)]">
                  Modell überschreiben
                </span>
                <input
                  type="text"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  placeholder="claude-sonnet-4-6 (Standard)"
                  className="mt-1 w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] text-sm mono"
                />
              </label>
              <label className="block">
                <span className="text-xs uppercase tracking-wider text-[var(--color-muted)]">
                  Max. Werkzeug-Iterationen
                </span>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={maxIterations}
                  onChange={(e) =>
                    setMaxIterations(parseInt(e.target.value) || 10)
                  }
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
                      "ANTHROPIC_API_KEY ist im Backend nicht gesetzt. Bitte in der .env hinterlegen und `make api-serve` neu starten.",
                    )
                  : error
              }
            />
          ) : null}
        </form>
      </Card>

      <section>
        <SectionTitle title="Beispiel-Fragen" />
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
