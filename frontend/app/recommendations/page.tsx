"use client";

import { useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { ArrowRight, AlertOctagon, AlertTriangle, Info } from "lucide-react";
import { api } from "@/lib/api";
import {
  Card,
  Empty,
  ErrorMessage,
  Loading,
  Pill,
} from "@/components/ui";
import { PageHeader } from "@/components/page-header";
import { formatRelativeTime, friendlyStatus, statusTone } from "@/lib/labels";

type StatusFilter = "all" | "pending" | "approved" | "rejected";

const RISK_META = {
  high: {
    label: "Dringend",
    Icon: AlertOctagon,
    ring: "bg-[color-mix(in_oklch,var(--color-danger)_14%,var(--color-surface))] text-[var(--color-danger)]",
  },
  medium: {
    label: "Beachten",
    Icon: AlertTriangle,
    ring: "bg-[color-mix(in_oklch,var(--color-warning)_18%,var(--color-surface))] text-[var(--color-warning)]",
  },
  low: {
    label: "Hinweis",
    Icon: Info,
    ring: "bg-[var(--color-bg)] text-[var(--color-muted)]",
  },
} as const;

function riskMeta(level: string) {
  return RISK_META[level as keyof typeof RISK_META] ?? RISK_META.low;
}

export default function RecommendationsIndex() {
  const [filter, setFilter] = useState<StatusFilter>("all");

  const { data, error, isLoading } = useSWR(
    ["recommendations-index", filter],
    () => api.listRecommendations(filter, 100, ["test"]),
  );

  return (
    <div className="space-y-6 max-w-5xl">
      <PageHeader
        label="Handlungsempfehlungen"
        title="Empfehlungen"
        description="Alle vom Agenten erzeugten Empfehlungen — offen, freigegeben oder abgelehnt. Klicken Sie eine Karte, um die volle Beweisführung zu sehen und (falls offen) zu entscheiden."
        action={
          <div className="inline-flex rounded-full border border-[var(--color-border)] bg-[var(--color-bg)] p-1">
            {(
              [
                { v: "all", l: "Alle" },
                { v: "pending", l: "Offen" },
                { v: "approved", l: "Freigegeben" },
                { v: "rejected", l: "Abgelehnt" },
              ] as { v: StatusFilter; l: string }[]
            ).map((o) => {
              const active = filter === o.v;
              return (
                <button
                  key={o.v}
                  type="button"
                  onClick={() => setFilter(o.v)}
                  aria-pressed={active}
                  className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                    active
                      ? "bg-[var(--color-accent)] text-[var(--color-accent-fg)]"
                      : "text-[var(--color-muted)] hover:text-[var(--color-fg)]"
                  }`}
                >
                  {o.l}
                </button>
              );
            })}
          </div>
        }
      />

      {error ? (
        <ErrorMessage error={error} />
      ) : isLoading ? (
        <Loading />
      ) : !data || data.length === 0 ? (
        <Card className="p-6">
          <Empty>
            Keine Empfehlungen mit diesem Filter. Sobald der Agent etwas
            Bemerkenswertes findet, landet die Empfehlung hier.
          </Empty>
        </Card>
      ) : (
        <div className="text-sm text-[var(--color-muted)] mb-2">
          {data.length} {data.length === 1 ? "Empfehlung" : "Empfehlungen"}
        </div>
      )}

      {data && data.length > 0 ? (
        <ul className="space-y-3">
          {data.map((r) => {
            const meta = riskMeta(r.risk_level);
            const Icon = meta.Icon;
            return (
              <li key={r.rec_id}>
                <Link
                  href={`/recommendations/${r.rec_id}`}
                  className="group flex items-start gap-4 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-2xl p-5 hover:border-[var(--color-accent)] transition-colors"
                >
                  <span
                    className={`size-10 rounded-xl flex items-center justify-center shrink-0 ${meta.ring}`}
                  >
                    <Icon className="size-5" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-wider font-medium">
                      <span className="opacity-80">{meta.label}</span>
                      <span className="opacity-50">·</span>
                      <Pill tone={statusTone(r.status)}>
                        {friendlyStatus(r.status)}
                      </Pill>
                      <span className="opacity-60">
                        {formatRelativeTime(r.created_at)}
                      </span>
                    </div>
                    <h3 className="text-base font-semibold mt-1 leading-snug">
                      {r.title}
                    </h3>
                    <p className="text-sm text-[var(--color-muted)] mt-1.5 line-clamp-2 leading-relaxed">
                      {r.body}
                    </p>
                  </div>
                  <ArrowRight className="size-4 text-[var(--color-muted)] mt-1 shrink-0 group-hover:text-[var(--color-accent)] group-hover:translate-x-0.5 transition-all" />
                </Link>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
