"use client";

import useSWR from "swr";
import { api } from "@/lib/api";
import type { HealthStatus } from "@/lib/types";

function DataSourceIndicator() {
  const { data } = useSWR(
    ["system-settings"],
    () => api.getSystemSettings(),
    { refreshInterval: 60_000, revalidateOnFocus: false },
  );
  if (!data) return null;
  const isLive = data.data_source === "live";
  const className = isLive
    ? "bg-[var(--color-accent)] text-[var(--color-accent-fg)]"
    : "bg-[color-mix(in_oklch,var(--color-warning)_18%,var(--color-surface))] text-[oklch(0.38_0.13_75)]";
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium ${className}`}
      title={isLive ? "Echte Shopify-Daten" : "Simulierter Demo-Datensatz"}
    >
      <span className="size-1.5 rounded-full bg-current opacity-70" aria-hidden />
      {isLive ? "Live-Daten" : "Demo-Daten"}
    </span>
  );
}

/**
 * Slim top bar above the page content. Mirrors Tavily's pattern of an
 * "Operational" / status pill in the top-right with optional secondary
 * actions (theme toggle, support link). Light by default — we don't
 * have a dark theme yet, so the toggle is omitted until we do.
 */
export function TopBar() {
  const { data } = useSWR<HealthStatus>(
    ["healthz"],
    () => api.health(),
    { refreshInterval: 60_000, revalidateOnFocus: false },
  );

  const ok = data?.status === "ok";

  return (
    <div className="flex items-center justify-end gap-2 px-6 py-3 border-b border-[var(--color-border)] bg-[var(--color-bg)]">
      <DataSourceIndicator />
      <StatusPill ok={ok} loading={!data} />
    </div>
  );
}

function StatusPill({ ok, loading }: { ok: boolean; loading: boolean }) {
  const label = loading ? "Prüfung …" : ok ? "Operational" : "Beeinträchtigt";
  const dot = loading
    ? "bg-[var(--color-muted)] animate-pulse"
    : ok
      ? "bg-[var(--color-success)]"
      : "bg-[var(--color-danger)]";
  const ring = ok
    ? "bg-[color-mix(in_oklch,var(--color-success)_14%,var(--color-surface))] text-[oklch(0.35_0.10_150)]"
    : "bg-[color-mix(in_oklch,var(--color-danger)_14%,var(--color-surface))] text-[var(--color-danger)]";

  return (
    <span
      className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium ${ring}`}
      title={loading ? "Verbindungsprüfung läuft" : ok ? "Backend erreichbar" : "Backend nicht erreichbar"}
    >
      <span className={`size-1.5 rounded-full ${dot}`} aria-hidden />
      {label}
    </span>
  );
}
