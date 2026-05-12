"use client";

import { useState } from "react";
import { useInsights } from "@/lib/hooks";
import { Card, Empty, ErrorMessage, Loading, Pill } from "@/components/ui";
import {
  formatRelativeTime,
  friendlyKpi,
  friendlySeverity,
  insightSentence,
  severityTone,
} from "@/lib/labels";

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
            Das organisationale Gedächtnis des Systems. Jede signifikante
            Beobachtung wird hier festgehalten — gemeinsam mit der
            anschliessenden Entscheidung und dem gemessenen Ergebnis. So
            entsteht über Zeit eine durchsuchbare Historie: „Haben wir das
            schon einmal gesehen, und was hat damals funktioniert?“
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

      <Card>
        {error ? (
          <div className="p-4">
            <ErrorMessage error={error} />
          </div>
        ) : isLoading ? (
          <div className="p-4">
            <Loading />
          </div>
        ) : !data || data.length === 0 ? (
          <Empty>
            Noch keine Beobachtungen. Sobald eine Empfehlung freigegeben
            oder eine Auffälligkeit erkannt wird, erscheint sie hier.
          </Empty>
        ) : (
          <ul className="divide-y divide-[var(--color-border)]">
            {data.map((i, idx) => {
              const p = i.properties ?? {};
              const sentence = insightSentence({
                kpi: p.kpi as string | undefined,
                component: (p.component as string | null) ?? null,
                relative_change: p.relative_change as number | undefined,
                period_start: p.period_start as string | undefined,
                period_end: p.period_end as string | undefined,
              });
              return (
                <li key={i.insight_id ?? idx} className="p-4">
                  <div className="flex flex-wrap items-center gap-2 mb-1.5">
                    {p.severity ? (
                      <Pill tone={severityTone(p.severity)}>
                        {friendlySeverity(p.severity)}
                      </Pill>
                    ) : null}
                    {p.kpi ? (
                      <span className="text-xs text-[var(--color-muted)]">
                        Kennzahl: {friendlyKpi(p.kpi as string)}
                      </span>
                    ) : null}
                    <span className="text-xs text-[var(--color-muted)] ml-auto">
                      Festgehalten {formatRelativeTime(i.created_at)}
                    </span>
                  </div>
                  <div className="text-[15px] leading-relaxed">{sentence}</div>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}
