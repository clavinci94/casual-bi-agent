"use client";

import { useKpiList } from "@/lib/hooks";
import { ErrorMessage, Loading, SectionTitle } from "@/components/ui";
import { KpiTile } from "@/components/kpi-tile";
import {
  metaFor,
  OWNER_LABELS,
  OWNER_ORDER,
  type KpiOwner,
} from "@/lib/kpi-metadata";

export default function KpisIndex() {
  const { data, error, isLoading } = useKpiList();

  if (error) return <ErrorMessage error={error} />;
  if (isLoading) return <Loading />;

  const views = data?.views ?? [];

  // Group views by their owner, dropping any view we haven't given UX
  // metadata yet (don't render technical-only entries to managers).
  const byOwner = new Map<KpiOwner, string[]>();
  for (const v of views) {
    const meta = metaFor(v);
    if (!meta) continue;
    if (!byOwner.has(meta.owner)) byOwner.set(meta.owner, []);
    byOwner.get(meta.owner)!.push(v);
  }

  const unknownCount = views.length - [...byOwner.values()].flat().length;

  return (
    <div className="space-y-10">
      <div className="max-w-3xl">
        <h1 className="text-2xl font-semibold tracking-tight">Kennzahlen</h1>
        <p className="text-sm text-[var(--color-muted)] mt-1 leading-relaxed">
          Aktuelle Werte aller Geschäftskennzahlen, gruppiert nach
          zuständigem Team. Pfeil rauf bedeutet besser, Pfeil runter
          schlechter — die Farbe folgt der Geschäftslogik (sinkende
          Rückgabequote ist grün, sinkende Conversion-Rate rot).
          Klicken Sie eine Karte für den vollständigen Verlauf, Aufschlüsselungen
          und die zugehörigen Findings.
        </p>
      </div>

      {OWNER_ORDER.filter((o) => byOwner.has(o)).map((owner) => (
        <section key={owner}>
          <SectionTitle title={OWNER_LABELS[owner]} />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {byOwner.get(owner)!.map((view) => {
              const meta = metaFor(view)!;
              return <KpiTile key={view} view={view} meta={meta} />;
            })}
          </div>
        </section>
      ))}

      {unknownCount > 0 ? (
        <p className="text-xs text-[var(--color-muted)] pt-4 border-t border-[var(--color-border)]">
          {unknownCount} weitere View(s) verfügbar, aber noch ohne
          Klartext-Beschreibung. Eintrag in{" "}
          <span className="mono">lib/kpi-metadata.ts</span> hinzufügen, um
          sie hier sichtbar zu machen.
        </p>
      ) : null}
    </div>
  );
}
