"use client";

import { useKpiList } from "@/lib/hooks";
import { ErrorMessage, Loading, SectionTitle } from "@/components/ui";
import { KpiTile } from "@/components/kpi-tile";
import { metaFor, OWNER_ORDER, type KpiOwner } from "@/lib/kpi-metadata";

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
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">KPIs</h1>
        <p className="text-sm text-[var(--color-muted)] mt-1">
          Latest values for every metric the agents and the business team
          share. Click a card for the full trend, breakdowns, and the
          related findings.
        </p>
      </div>

      {OWNER_ORDER.filter((o) => byOwner.has(o)).map((owner) => (
        <section key={owner}>
          <SectionTitle title={owner} />
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
          {unknownCount} additional view(s) available without a friendly
          name yet. Add them to <span className="mono">lib/kpi-metadata.ts</span>{" "}
          to surface them here.
        </p>
      ) : null}
    </div>
  );
}
