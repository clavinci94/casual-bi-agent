"use client";

import { useState } from "react";
import {
  Lightbulb,
  TrendingDown,
  TrendingUp,
  Clock,
  ShieldCheck,
} from "lucide-react";
import { useInsights } from "@/lib/hooks";
import { Card, ErrorMessage, Loading } from "@/components/ui";
import {
  formatRelativeTime,
  friendlyComponent,
  friendlyKpi,
  insightSentence,
} from "@/lib/labels";

function severityBg(
  severity: string | null | undefined,
): "danger" | "warning" | "neutral" {
  if (severity === "high") return "danger";
  if (severity === "medium") return "warning";
  return "neutral";
}

const SEVERITY_RING: Record<"danger" | "warning" | "neutral", string> = {
  danger: "bg-red-50 text-red-700 ring-red-200",
  warning: "bg-amber-50 text-amber-700 ring-amber-200",
  neutral:
    "bg-[var(--color-bg)] text-[var(--color-muted)] ring-[var(--color-border)]",
};

const SEVERITY_LABEL: Record<string, string> = {
  high: "Dringend",
  medium: "Beachten",
  low: "Hinweis",
};

export default function InsightsPage() {
  const [showTests, setShowTests] = useState(false);
  const { data, error, isLoading } = useInsights(
    50,
    showTests ? [] : ["test"],
  );

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="max-w-3xl">
          <h1 className="text-2xl font-semibold tracking-tight">
            Lernerfahrungen
          </h1>
          <p className="text-sm text-[var(--color-muted)] mt-1 leading-relaxed">
            Hier sammelt das System, was es über Ihr Geschäft gelernt hat —
            jede wichtige Beobachtung, Ihre Entscheidung dazu, und das
            gemessene Ergebnis. Mit der Zeit wächst daraus ein durchsuchbares
            Erfahrungswissen: „Hatten wir das schon mal? Was hat damals
            geholfen?"
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm text-[var(--color-muted)] cursor-pointer select-none shrink-0">
          <input
            type="checkbox"
            checked={showTests}
            onChange={(e) => setShowTests(e.target.checked)}
            className="accent-[var(--color-accent)]"
          />
          Test-Einträge einblenden
        </label>
      </div>

      {error ? (
        <ErrorMessage error={error} />
      ) : isLoading ? (
        <Loading />
      ) : !data || data.length === 0 ? (
        <Card className="p-8 text-center border-dashed">
          <Lightbulb className="size-8 text-[var(--color-muted)] mx-auto mb-3" />
          <div className="font-medium">Noch keine Erfahrungen gesammelt.</div>
          <div className="text-sm text-[var(--color-muted)] mt-1">
            Sobald die erste Empfehlung freigegeben oder eine Auffälligkeit
            erkannt wird, erscheint sie hier.
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {data.map((i, idx) => {
            const p = i.properties ?? {};
            const severity = (p.severity as string | null) ?? null;
            const tone = severityBg(severity);
            const change = p.relative_change as number | undefined;
            const direction =
              change != null && Number.isFinite(change)
                ? change > 0
                  ? "up"
                  : change < 0
                    ? "down"
                    : "flat"
                : "flat";

            return (
              <div
                key={i.insight_id ?? idx}
                className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-2xl p-5"
              >
                <div className="flex items-start gap-3">
                  <div
                    className={`size-10 rounded-xl flex items-center justify-center shrink-0 ring-1 ${SEVERITY_RING[tone]}`}
                  >
                    {direction === "down" ? (
                      <TrendingDown className="size-5" />
                    ) : direction === "up" ? (
                      <TrendingUp className="size-5" />
                    ) : (
                      <Lightbulb className="size-5" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-[11px] uppercase tracking-wider font-medium opacity-80 flex flex-wrap items-center gap-2">
                      <span>
                        {severity
                          ? SEVERITY_LABEL[severity] ?? severity
                          : "Beobachtung"}
                      </span>
                      {p.component ? (
                        <>
                          <span className="text-[var(--color-muted)]">·</span>
                          <span>{friendlyComponent(String(p.component))}</span>
                        </>
                      ) : null}
                    </div>
                    <p className="text-[15px] font-medium mt-1 leading-snug">
                      {insightSentence({
                        kpi: p.kpi as string | undefined,
                        component: (p.component as string | null) ?? null,
                        relative_change: change,
                        period_start: p.period_start as string | undefined,
                        period_end: p.period_end as string | undefined,
                      })}
                    </p>

                    <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
                      <div className="flex items-start gap-1.5">
                        <ShieldCheck className="size-3.5 text-[var(--color-muted)] mt-0.5 shrink-0" />
                        <div>
                          <div className="text-[var(--color-muted)]">
                            Entscheidung
                          </div>
                          <div className="font-medium">
                            Noch nicht freigegeben
                          </div>
                        </div>
                      </div>
                      <div className="flex items-start gap-1.5">
                        <Clock className="size-3.5 text-[var(--color-muted)] mt-0.5 shrink-0" />
                        <div>
                          <div className="text-[var(--color-muted)]">
                            Wirkung
                          </div>
                          <div className="font-medium">
                            Wird nach Freigabe gemessen
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="mt-3 text-[11px] text-[var(--color-muted)]">
                      Festgehalten {formatRelativeTime(i.created_at)} ·{" "}
                      Kennzahl{" "}
                      <span className="font-medium">
                        {friendlyKpi(p.kpi as string | undefined)}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
