"use client";

import Link from "next/link";
import { useKpiList } from "@/lib/hooks";
import { Card, ErrorMessage, Loading, SectionTitle } from "@/components/ui";

export default function KpisIndex() {
  const { data, error, isLoading } = useKpiList();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">KPIs</h1>
        <p className="text-sm text-[var(--color-muted)] mt-1">
          Governed semantic-layer views — the same surface agents read from.
        </p>
      </div>

      <SectionTitle title="Available views" />
      {error ? (
        <ErrorMessage error={error} />
      ) : isLoading ? (
        <Loading />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {data?.views.map((view) => (
            <Link key={view} href={`/kpis/${encodeURIComponent(view)}`}>
              <Card className="p-4 hover:border-[var(--color-accent)] transition-colors cursor-pointer">
                <div className="font-medium mono text-sm">{view}</div>
                <div className="text-xs text-[var(--color-muted)] mt-1">
                  open time-series
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
