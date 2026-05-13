"use client";

import { useState } from "react";
import useSWR from "swr";
import {
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  ShoppingBag,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { api } from "@/lib/api";
import { Card, ErrorMessage, Pill } from "@/components/ui";
import type {
  ShopifyComponent,
  ShopifyIncident,
  ShopifyOverallIndicator,
  ShopifyStatusResponse,
} from "@/lib/types";

// statuspage.io component-status → German label + colour token
const COMPONENT_STATUS: Record<
  string,
  { label: string; dot: string; tone: "ok" | "warn" | "danger" | "info" }
> = {
  operational: { label: "Normal", dot: "bg-[var(--color-success)]", tone: "ok" },
  degraded_performance: {
    label: "Eingeschränkt",
    dot: "bg-[var(--color-warning)]",
    tone: "warn",
  },
  partial_outage: {
    label: "Teilstörung",
    dot: "bg-[var(--color-warning)]",
    tone: "warn",
  },
  major_outage: {
    label: "Schwere Störung",
    dot: "bg-[var(--color-danger)]",
    tone: "danger",
  },
  under_maintenance: {
    label: "Wartung",
    dot: "bg-[var(--color-accent)]",
    tone: "info",
  },
};

const OVERALL_META: Record<
  ShopifyOverallIndicator,
  { label: string; icon: LucideIcon; tone: "success" | "warning" | "danger" }
> = {
  none: { label: "Alle Systeme grün", icon: CheckCircle2, tone: "success" },
  minor: { label: "Kleinere Einschränkungen", icon: AlertTriangle, tone: "warning" },
  major: { label: "Grössere Störung aktiv", icon: AlertOctagon, tone: "danger" },
  critical: { label: "Kritische Störung", icon: AlertOctagon, tone: "danger" },
};

function formatSince(iso: string | null): string {
  if (!iso) return "";
  try {
    const dt = new Date(iso);
    const diffMs = Date.now() - dt.getTime();
    const diffMin = Math.floor(diffMs / 60_000);
    if (diffMin < 60) return `seit ${diffMin} Min.`;
    const diffH = Math.floor(diffMin / 60);
    if (diffH < 48) return `seit ${diffH} h`;
    const diffD = Math.floor(diffH / 24);
    return `seit ${diffD} Tagen`;
  } catch {
    return iso;
  }
}

function statusMeta(status: string) {
  return (
    COMPONENT_STATUS[status] ?? {
      label: status,
      dot: "bg-[var(--color-muted)]",
      tone: "info" as const,
    }
  );
}

export function ShopifyStatusWidget() {
  const { data, error, isLoading } = useSWR(
    ["shopify-status"],
    () => api.externalShopifyStatus(),
    { revalidateOnFocus: false, refreshInterval: 5 * 60_000 },
  );

  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 mb-3">
        <span className="size-8 rounded-lg bg-[var(--color-bg)] flex items-center justify-center">
          <ShoppingBag className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-xs uppercase tracking-wider text-[var(--color-muted)] font-medium">
            Plattform
          </div>
          <h2 className="text-base font-semibold">Shopify-Status</h2>
        </div>
      </div>

      {isLoading ? (
        <div className="text-sm text-[var(--color-muted)] animate-pulse">
          Lade Plattform-Status …
        </div>
      ) : error ? (
        <ErrorMessage error={error} />
      ) : !data || data.error ? (
        <div className="text-xs text-[var(--color-muted)]">
          Status nicht abrufbar. {data?.error ?? ""}
        </div>
      ) : (
        <Body data={data} />
      )}

      <div className="mt-4 text-[11px] text-[var(--color-muted)]">
        Quelle status.shopify.com · alle 5 Min. aktualisiert
      </div>
    </Card>
  );
}

function Body({ data }: { data: ShopifyStatusResponse }) {
  const overall = OVERALL_META[data.overall.indicator] ?? OVERALL_META.none;
  const OverallIcon = overall.icon;

  const critical = data.components.filter((c) => c.is_critical);
  const others = data.components.filter((c) => !c.is_critical);

  return (
    <div className="space-y-4">
      <Banner
        tone={overall.tone}
        title={overall.label}
        subtitle={data.overall.description}
        Icon={OverallIcon}
      />

      {data.active_incidents.length > 0 ? (
        <IncidentList incidents={data.active_incidents} title="Aktive Störungen" />
      ) : null}

      {data.scheduled_maintenances.length > 0 ? (
        <IncidentList
          incidents={data.scheduled_maintenances}
          title="Geplante Wartungsfenster"
          subtle
        />
      ) : null}

      {critical.length > 0 ? <ComponentGrid title="Kernsysteme" components={critical} /> : null}

      {others.length > 0 ? (
        <OthersDisclosure components={others} />
      ) : null}
    </div>
  );
}

function Banner({
  tone,
  title,
  subtitle,
  Icon,
}: {
  tone: "success" | "warning" | "danger";
  title: string;
  subtitle: string;
  Icon: LucideIcon;
}) {
  const ringClass =
    tone === "success"
      ? "bg-[color-mix(in_oklch,var(--color-success)_10%,var(--color-surface))] text-[var(--color-success)]"
      : tone === "warning"
        ? "bg-[color-mix(in_oklch,var(--color-warning)_14%,var(--color-surface))] text-[var(--color-warning)]"
        : "bg-[color-mix(in_oklch,var(--color-danger)_14%,var(--color-surface))] text-[var(--color-danger)]";

  return (
    <div className={`rounded-xl px-3.5 py-3 flex items-center gap-3 ${ringClass}`}>
      <Icon className="size-5 shrink-0" />
      <div className="min-w-0">
        <div className="font-semibold text-sm">{title}</div>
        <div className="text-xs opacity-80">{subtitle}</div>
      </div>
    </div>
  );
}

function IncidentList({
  incidents,
  title,
  subtle,
}: {
  incidents: ShopifyIncident[];
  title: string;
  subtle?: boolean;
}) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-[var(--color-muted)] font-medium mb-1.5">
        {title}
      </div>
      <ul className="space-y-2">
        {incidents.map((inc, i) => (
          <li
            key={inc.id ?? i}
            className="rounded-lg border border-[var(--color-border)] p-2.5 text-sm"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <div className="font-medium leading-snug">
                  {inc.url ? (
                    <a
                      href={inc.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:underline"
                    >
                      {inc.name}
                      <ExternalLink className="inline size-3 ml-1 opacity-60" />
                    </a>
                  ) : (
                    inc.name
                  )}
                </div>
                <div className="text-xs text-[var(--color-muted)] mt-1">
                  {inc.components.length ? inc.components.join(" · ") : "—"}
                  {inc.started_at ? ` · ${formatSince(inc.started_at)}` : ""}
                </div>
              </div>
              <div className="flex flex-col items-end gap-1">
                {!subtle ? <ImpactPill impact={inc.impact} /> : null}
                <span className="text-[11px] text-[var(--color-muted)]">{inc.status}</span>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ImpactPill({ impact }: { impact: string }) {
  const tone =
    impact === "critical" || impact === "major"
      ? "danger"
      : impact === "minor"
        ? "warning"
        : "neutral";
  const label =
    impact === "critical"
      ? "kritisch"
      : impact === "major"
        ? "schwer"
        : impact === "minor"
          ? "leicht"
          : "kein";
  return <Pill tone={tone}>{label}</Pill>;
}

function ComponentGrid({
  title,
  components,
}: {
  title: string;
  components: ShopifyComponent[];
}) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-[var(--color-muted)] font-medium mb-1.5">
        {title}
      </div>
      <ul className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
        {components.map((c) => (
          <ComponentRow key={c.name} c={c} />
        ))}
      </ul>
    </div>
  );
}

function ComponentRow({ c }: { c: ShopifyComponent }) {
  const meta = statusMeta(c.status);
  const label =
    c.status === "operational" ? null : (
      <span className="text-xs text-[var(--color-muted)]">{meta.label}</span>
    );
  const showWrench = c.status === "under_maintenance";

  return (
    <li className="flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-md hover:bg-[var(--color-bg)]">
      <div className="flex items-center gap-2 min-w-0">
        <span
          className={`size-2 rounded-full ${meta.dot} shrink-0`}
          aria-hidden
        />
        <span className="text-sm truncate">{c.name}</span>
        {showWrench ? (
          <Wrench className="size-3 text-[var(--color-accent)]" aria-hidden />
        ) : null}
      </div>
      {label}
    </li>
  );
}

function OthersDisclosure({ components }: { components: ShopifyComponent[] }) {
  const [open, setOpen] = useState(false);
  const allOk = components.every((c) => c.status === "operational");

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between text-left text-xs uppercase tracking-wider text-[var(--color-muted)] font-medium hover:text-[var(--color-fg)]"
      >
        <span>
          Weitere Komponenten ({components.length})
          {allOk ? " · alle normal" : ""}
        </span>
        {open ? (
          <ChevronUp className="size-4" />
        ) : (
          <ChevronDown className="size-4" />
        )}
      </button>
      {open ? (
        <ul className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-1.5">
          {components.map((c) => (
            <ComponentRow key={c.name} c={c} />
          ))}
        </ul>
      ) : null}
    </div>
  );
}
