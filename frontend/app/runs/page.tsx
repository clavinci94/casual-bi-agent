"use client";

import { useState } from "react";
import { useRuns } from "@/lib/hooks";
import {
  Card,
  Empty,
  ErrorMessage,
  Loading,
  MutedLink,
  Pill,
} from "@/components/ui";
import { PageHeader } from "@/components/page-header";
import {
  formatRelativeTime,
  friendlyStatus,
  friendlyTrigger,
  statusTone,
} from "@/lib/labels";

function fmtDuration(startISO: string, endISO: string | null): string {
  if (!endISO) return "läuft …";
  const ms = new Date(endISO).getTime() - new Date(startISO).getTime();
  if (ms < 1000) return `${ms} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  return `${(ms / 60_000).toFixed(1)} min`;
}

export default function RunsIndex() {
  const [showTests, setShowTests] = useState(false);
  const { data, error, isLoading } = useRuns(
    100,
    showTests ? [] : ["test"],
  );

  return (
    <div className="space-y-6">
      <PageHeader
        label="Aktivität"
        title="Analysen"
        description="Vollständige Liste aller Untersuchungen, die das System durchgeführt hat — manuell oder automatisch. Jeder Eintrag führt zur kompletten Beweiskette inkl. abgefragter Kennzahlen, statistischer Tests und der finalen Empfehlung."
        action={
          <label className="flex items-center gap-2 text-sm text-[var(--color-muted)] cursor-pointer select-none">
            <input
              type="checkbox"
              checked={showTests}
              onChange={(e) => setShowTests(e.target.checked)}
              className="accent-[var(--color-accent)]"
            />
            Test-Läufe einblenden
          </label>
        }
      />

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
            Keine Analysen vorhanden. Starten Sie eine über „Neue
            Untersuchung“.
          </Empty>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-wider text-[var(--color-muted)] border-b border-[var(--color-border)]">
              <tr>
                <th className="text-left px-4 py-2">Frage / Anlass</th>
                <th className="text-left px-4 py-2">Quelle</th>
                <th className="text-left px-4 py-2">Status</th>
                <th className="text-left px-4 py-2">Wann</th>
                <th className="text-right px-4 py-2">Dauer</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {data.map((r) => (
                <tr key={r.run_id} className="hover:bg-[var(--color-bg)]">
                  <td className="px-4 py-3 max-w-xl">
                    <MutedLink href={`/runs/${r.run_id}`}>
                      <span className="font-medium text-[var(--color-fg)] hover:underline line-clamp-2">
                        {r.prompt ?? "(ohne Titel)"}
                      </span>
                    </MutedLink>
                  </td>
                  <td className="px-4 py-3 text-xs text-[var(--color-muted)]">
                    {friendlyTrigger(r.trigger)}
                  </td>
                  <td className="px-4 py-3">
                    <Pill tone={statusTone(r.status)}>
                      {friendlyStatus(r.status)}
                    </Pill>
                  </td>
                  <td className="px-4 py-3 text-xs text-[var(--color-muted)] whitespace-nowrap">
                    {formatRelativeTime(r.started_at)}
                  </td>
                  <td className="px-4 py-3 text-right text-xs mono whitespace-nowrap">
                    {fmtDuration(r.started_at, r.finished_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
