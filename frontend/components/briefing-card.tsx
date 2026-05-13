"use client";

import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import {
  AlertOctagon,
  AlertTriangle,
  BarChart3,
  CalendarClock,
  Info,
  LineChart,
  Newspaper,
  RefreshCw,
  Search,
  ShoppingBag,
  Sun,
  type LucideIcon,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Card, ErrorMessage } from "@/components/ui";
import type { BriefingSignal } from "@/lib/types";

const URGENCY_META: Record<
  BriefingSignal["urgency"],
  { label: string; ring: string; icon: LucideIcon; iconColor: string }
> = {
  high: {
    label: "Dringend",
    ring: "bg-[color-mix(in_oklch,var(--color-danger)_14%,var(--color-surface))] text-[var(--color-danger)]",
    icon: AlertOctagon,
    iconColor: "text-[var(--color-danger)]",
  },
  medium: {
    label: "Beachten",
    ring: "bg-[color-mix(in_oklch,var(--color-warning)_18%,var(--color-surface))] text-[var(--color-warning)]",
    icon: AlertTriangle,
    iconColor: "text-[var(--color-warning)]",
  },
  low: {
    label: "Hinweis",
    ring: "bg-[var(--color-bg)] text-[var(--color-muted)]",
    icon: Info,
    iconColor: "text-[var(--color-muted)]",
  },
};

const SOURCE_META: Record<string, { label: string; icon: LucideIcon }> = {
  markets: { label: "Markt", icon: LineChart },
  shopify_status: { label: "Shopify-Plattform", icon: ShoppingBag },
  commerce_calendar: { label: "Kalender", icon: CalendarClock },
  news: { label: "Presse", icon: Newspaper },
  trends: { label: "Suchinteresse", icon: Search },
  kpis: { label: "Eigene Zahlen", icon: BarChart3 },
};

function sourceLabel(source: string) {
  return SOURCE_META[source]?.label ?? source;
}

function formatBriefingTime(iso: string | null): string {
  if (!iso) return "soeben";
  try {
    const dt = new Date(iso);
    const today = new Date();
    const sameDay =
      dt.getFullYear() === today.getFullYear() &&
      dt.getMonth() === today.getMonth() &&
      dt.getDate() === today.getDate();
    if (sameDay) {
      return `heute ${dt.toLocaleTimeString("de-CH", { hour: "2-digit", minute: "2-digit" })} Uhr`;
    }
    return dt.toLocaleString("de-CH", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function BriefingCard() {
  const { mutate } = useSWRConfig();
  const { data, error, isLoading } = useSWR(
    ["briefing", "today"],
    () => api.briefingToday(),
    { revalidateOnFocus: false },
  );
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<unknown>(null);

  async function refresh() {
    setRefreshing(true);
    setRefreshError(null);
    try {
      const fresh = await api.briefingRefresh();
      mutate(["briefing", "today"], fresh, { revalidate: false });
    } catch (e) {
      setRefreshError(e);
    } finally {
      setRefreshing(false);
    }
  }

  return (
    <Card className="p-6">
      <Header
        generatedAt={data?.generated_at ?? null}
        fromCache={data?.from_cache ?? false}
        refreshing={refreshing}
        onRefresh={refresh}
      />

      {isLoading ? (
        <LoadingState />
      ) : error ? (
        <BriefingError error={error} />
      ) : !data ? (
        <EmptyState />
      ) : (
        <BriefingBody briefing={data.briefing} />
      )}

      {refreshError ? (
        <div className="mt-3">
          <ErrorMessage error={refreshError} />
        </div>
      ) : null}
    </Card>
  );
}

function Header({
  generatedAt,
  fromCache,
  refreshing,
  onRefresh,
}: {
  generatedAt: string | null;
  fromCache: boolean;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  return (
    <div className="flex items-start justify-between gap-3 mb-3">
      <div className="flex items-center gap-2 min-w-0">
        <span className="size-9 rounded-xl bg-[var(--color-accent)] text-white flex items-center justify-center shrink-0">
          <Sun className="size-5" />
        </span>
        <div className="min-w-0">
          <div className="text-xs uppercase tracking-wider text-[var(--color-muted)] font-medium">
            Tagesbriefing
          </div>
          <h2 className="text-lg font-semibold">Was Sie heute angeht</h2>
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <span className="hidden sm:inline text-xs text-[var(--color-muted)]">
          {generatedAt
            ? `${fromCache ? "Erstellt" : "Aktualisiert"} ${formatBriefingTime(generatedAt)}`
            : "Wird gerade erstellt …"}
        </span>
        <button
          type="button"
          onClick={onRefresh}
          disabled={refreshing}
          title="Briefing neu erzeugen"
          aria-label="Briefing neu erzeugen"
          className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs border border-[var(--color-border)] text-[var(--color-muted)] hover:text-[var(--color-fg)] hover:bg-[var(--color-bg)] disabled:opacity-50"
        >
          <RefreshCw className={`size-3.5 ${refreshing ? "animate-spin" : ""}`} />
          <span>{refreshing ? "läuft" : "Aktualisieren"}</span>
        </button>
      </div>
    </div>
  );
}

function BriefingBody({ briefing }: { briefing: { headline: string; signals: BriefingSignal[] } }) {
  if (!briefing.signals?.length) {
    return (
      <>
        <Headline text={briefing.headline} />
        <EmptyState />
      </>
    );
  }

  return (
    <>
      <Headline text={briefing.headline} />
      <ol className="space-y-3.5 mt-4">
        {briefing.signals.map((s, i) => (
          <SignalRow key={i} signal={s} />
        ))}
      </ol>
    </>
  );
}

function Headline({ text }: { text: string }) {
  return (
    <p className="text-[17px] font-medium leading-snug">
      {text}
    </p>
  );
}

function SignalRow({ signal }: { signal: BriefingSignal }) {
  const urg = URGENCY_META[signal.urgency] ?? URGENCY_META.low;
  const src = SOURCE_META[signal.source] ?? { label: signal.source, icon: Info };
  const UrgIcon = urg.icon;
  const SrcIcon = src.icon;

  return (
    <li className="flex gap-3.5">
      <span
        className={`size-9 rounded-xl flex items-center justify-center shrink-0 ${urg.ring}`}
        aria-label={`Dringlichkeit: ${urg.label}`}
        title={`Dringlichkeit: ${urg.label}`}
      >
        <UrgIcon className={`size-4 ${urg.iconColor}`} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-[11px] uppercase tracking-wider text-[var(--color-muted)] font-medium flex items-center gap-1.5">
          <SrcIcon className="size-3" aria-hidden />
          {sourceLabel(signal.source)}
        </div>
        <p className="text-[15px] leading-snug mt-0.5">{signal.what}</p>
        <p className="text-sm text-[var(--color-muted)] mt-1.5 leading-relaxed">
          {signal.why_for_you}
        </p>
        <p className="text-sm leading-relaxed mt-1.5">
          <span className="text-xs uppercase tracking-wider text-[var(--color-accent)] font-medium mr-1.5">
            Vorschlag
          </span>
          {signal.action}
        </p>
      </div>
    </li>
  );
}

function LoadingState() {
  return (
    <div className="mt-3 space-y-3 animate-pulse">
      <div className="h-5 w-3/4 rounded bg-[var(--color-bg)]" />
      <div className="space-y-2">
        {[0, 1, 2].map((i) => (
          <div key={i} className="flex gap-3">
            <div className="size-9 rounded-xl bg-[var(--color-bg)] shrink-0" />
            <div className="flex-1 space-y-1.5">
              <div className="h-3 w-1/4 rounded bg-[var(--color-bg)]" />
              <div className="h-3 w-5/6 rounded bg-[var(--color-bg)]" />
              <div className="h-3 w-2/3 rounded bg-[var(--color-bg)]" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <p className="text-sm text-[var(--color-muted)] leading-relaxed mt-2">
      Heute keine relevanten Signale identifiziert — das interne Geschäft
      ist stabil und draussen passiert nichts, das diesen Shop konkret
      angeht. Sie können den Tag ohne Sondermassnahmen angehen.
    </p>
  );
}

function BriefingError({ error }: { error: unknown }) {
  if (error instanceof ApiError && error.status === 503) {
    return (
      <p className="text-sm text-[var(--color-muted)] leading-relaxed mt-2">
        Tagesbriefing ist derzeit nicht verfügbar — der Anthropic-Schlüssel
        fehlt im Backend. Eintragen unter <code>.env</code> (Variable
        <code> ANTHROPIC_API_KEY</code>), dann Backend neu starten.
      </p>
    );
  }
  return (
    <div className="mt-3">
      <ErrorMessage error={error} />
    </div>
  );
}
