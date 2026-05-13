"use client";

import { useState } from "react";
import useSWR from "swr";
import {
  GitCompareArrows,
  HelpCircle,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { api } from "@/lib/api";
import { Card, ErrorMessage } from "@/components/ui";
import { Sparkline } from "@/components/sparkline";
import type { CorrelationStats } from "@/lib/types";

// --- option catalogs ----------------------------------------------------

type InternalOption = { name: string; label: string };

const INTERNAL_OPTIONS: InternalOption[] = [
  { name: "shopify_revenue", label: "Tagesumsatz (alle Kanäle)" },
  { name: "shopify_orders", label: "Bestellungen / Tag (alle Kanäle)" },
  { name: "shopify_aov", label: "Durchschnittlicher Bestellwert / Tag" },
  { name: "shopify_revenue_mobile", label: "Umsatz / Tag — Mobile" },
  { name: "shopify_revenue_desktop", label: "Umsatz / Tag — Desktop" },
  { name: "shopify_revenue_pos", label: "Umsatz / Tag — Point of Sale" },
  { name: "shopify_orders_mobile", label: "Bestellungen / Tag — Mobile" },
  { name: "shopify_orders_desktop", label: "Bestellungen / Tag — Desktop" },
  { name: "shopify_orders_pos", label: "Bestellungen / Tag — Point of Sale" },
];

type ExternalOption = {
  key: string;
  kind: "market" | "trends";
  label: string;
};

const EXTERNAL_OPTIONS: ExternalOption[] = [
  { key: "EURCHF=X", kind: "market", label: "Euro / Franken" },
  { key: "USDCHF=X", kind: "market", label: "US-Dollar / Franken" },
  { key: "CHFEUR=X", kind: "market", label: "Franken / Euro" },
  { key: "^SSMI", kind: "market", label: "SMI (Swiss Market Index)" },
  { key: "^GDAXI", kind: "market", label: "DAX" },
  { key: "^GSPC", kind: "market", label: "S&P 500" },
  { key: "GC=F", kind: "market", label: "Gold (Spot)" },
  { key: "CL=F", kind: "market", label: "Rohöl (WTI)" },
  { key: "SHOP", kind: "market", label: "Shopify Aktie (NYSE)" },
];

const WINDOW_OPTIONS: { value: number; label: string }[] = [
  { value: 30, label: "30 Tage" },
  { value: 90, label: "90 Tage" },
  { value: 180, label: "180 Tage" },
  { value: 365, label: "1 Jahr" },
];

// --- significance bucketing --------------------------------------------

type SigBucket = "strong" | "moderate" | "weak" | "none";

function bucketStats(stats: CorrelationStats): SigBucket {
  const r = stats.pearson_r;
  const p = stats.pearson_p;
  if (r == null || p == null) return "none";
  const ar = Math.abs(r);
  if (p < 0.05 && ar >= 0.5) return "strong";
  if (p < 0.05 && ar >= 0.3) return "moderate";
  if (p < 0.1 && ar >= 0.2) return "weak";
  return "none";
}

const BUCKET_META: Record<
  SigBucket,
  { label: string; tone: "ok" | "warn" | "info" | "neutral" }
> = {
  strong: { label: "Starker Zusammenhang", tone: "ok" },
  moderate: { label: "Moderater Zusammenhang", tone: "warn" },
  weak: { label: "Schwacher Hinweis", tone: "info" },
  none: { label: "Kein belastbarer Zusammenhang", tone: "neutral" },
};

function fmt(n: number | null, digits = 2): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return n.toLocaleString("de-CH", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

// --- component ----------------------------------------------------------

export function CorrelationCard() {
  const [internal, setInternal] = useState("shopify_revenue");
  const [externalKey, setExternalKey] = useState("EURCHF=X");
  const [days, setDays] = useState(90);

  const externalOpt = EXTERNAL_OPTIONS.find((o) => o.key === externalKey) ?? EXTERNAL_OPTIONS[0];

  const { data, error, isLoading } = useSWR(
    ["correlation", internal, externalOpt.key, days],
    () =>
      api.externalCorrelateWithShop({
        internal,
        external_kind: externalOpt.kind,
        external_key: externalOpt.key,
        days,
      }),
    { revalidateOnFocus: false },
  );

  return (
    <Card className="p-6">
      <header className="flex items-start justify-between gap-3 mb-4">
        <div className="flex items-center gap-2 min-w-0">
          <span className="size-9 rounded-xl bg-[var(--color-bg)] flex items-center justify-center shrink-0">
            <GitCompareArrows className="size-5" />
          </span>
          <div className="min-w-0">
            <div className="text-xs uppercase tracking-wider text-[var(--color-muted)] font-medium">
              Zusammenhang prüfen
            </div>
            <h2 className="text-lg font-semibold">
              Bewegt sich Ihre Kennzahl mit dem Markt?
            </h2>
          </div>
        </div>
        <HelpHint />
      </header>

      <Controls
        internal={internal}
        externalKey={externalKey}
        days={days}
        onInternal={setInternal}
        onExternalKey={setExternalKey}
        onDays={setDays}
      />

      <div className="mt-5">
        {isLoading ? (
          <LoadingState />
        ) : error ? (
          <ErrorMessage error={error} />
        ) : !data ? (
          <p className="text-sm text-[var(--color-muted)]">Keine Daten.</p>
        ) : (
          <Result data={data} />
        )}
      </div>
    </Card>
  );
}

function Controls({
  internal,
  externalKey,
  days,
  onInternal,
  onExternalKey,
  onDays,
}: {
  internal: string;
  externalKey: string;
  days: number;
  onInternal: (v: string) => void;
  onExternalKey: (v: string) => void;
  onDays: (v: number) => void;
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
      <label className="md:col-span-5">
        <span className="text-xs uppercase tracking-wider text-[var(--color-muted)] block mb-1">
          Ihre Kennzahl
        </span>
        <select
          value={internal}
          onChange={(e) => onInternal(e.target.value)}
          className="w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
        >
          {INTERNAL_OPTIONS.map((o) => (
            <option key={o.name} value={o.name}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
      <label className="md:col-span-5">
        <span className="text-xs uppercase tracking-wider text-[var(--color-muted)] block mb-1">
          Vergleichen mit
        </span>
        <select
          value={externalKey}
          onChange={(e) => onExternalKey(e.target.value)}
          className="w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
        >
          {EXTERNAL_OPTIONS.map((o) => (
            <option key={o.key} value={o.key}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
      <label className="md:col-span-2">
        <span className="text-xs uppercase tracking-wider text-[var(--color-muted)] block mb-1">
          Fenster
        </span>
        <select
          value={days}
          onChange={(e) => onDays(Number(e.target.value))}
          className="w-full px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
        >
          {WINDOW_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}

function HelpHint() {
  return (
    <div className="group relative shrink-0">
      <button
        type="button"
        className="text-[var(--color-muted)] hover:text-[var(--color-fg)]"
        aria-label="Was bedeutet Korrelation?"
      >
        <HelpCircle className="size-4" />
      </button>
      <div className="absolute right-0 top-full mt-1 w-72 hidden group-hover:block group-focus-within:block z-10">
        <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg shadow-lg p-3 text-xs leading-relaxed text-[var(--color-fg)]">
          <p className="font-semibold mb-1">Korrelation = Gleichlauf</p>
          <p className="text-[var(--color-muted)]">
            Wir prüfen, ob Ihre Kennzahl und der externe Wert sich im
            betrachteten Zeitraum gemeinsam nach oben oder unten bewegen.
            <br />
            <strong>r</strong> liegt zwischen −1 und +1: nahe 0 = kein
            Gleichlauf, +1/−1 = perfekt gleich/gegensätzlich.
            <br />
            <strong>p</strong> sagt, wie wahrscheinlich der gemessene Wert
            durch Zufall entstanden sein könnte; <strong>p &lt; 0.05</strong>
            heißt: eher kein Zufall.
            <br />
            Wichtig: ein Zusammenhang ist <em>nicht</em> automatisch eine
            Ursache.
          </p>
        </div>
      </div>
    </div>
  );
}

function Result({
  data,
}: {
  data: {
    internal: { name: string; label: string; unit: string };
    external: { kind: string; key: string; label: string };
    window_days: number;
    stats: CorrelationStats;
    series: { date: string; internal: number; external: number }[];
    narrative: string | null;
  };
}) {
  const internalValues = data.series.map((p) => p.internal);
  const externalValues = data.series.map((p) => p.external);
  const bucket = bucketStats(data.stats);
  const meta = BUCKET_META[bucket];

  return (
    <div className="space-y-5">
      <StatsBanner
        stats={data.stats}
        bucket={bucket}
        bucketLabel={meta.label}
        tone={meta.tone}
      />

      <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-center">
        <SeriesRow
          label={data.internal.label}
          unit={data.internal.unit}
          values={internalValues}
          accent
        />
        <SeriesRow
          label={data.external.label}
          unit="Wert"
          values={externalValues}
        />
      </div>

      {data.narrative ? (
        <div className="rounded-lg bg-[var(--color-bg)] border border-[var(--color-border)] p-3.5">
          <div className="text-[11px] uppercase tracking-wider text-[var(--color-accent)] font-medium mb-1">
            Einschätzung
          </div>
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{data.narrative}</p>
        </div>
      ) : null}
    </div>
  );
}

function StatsBanner({
  stats,
  bucket,
  bucketLabel,
  tone,
}: {
  stats: CorrelationStats;
  bucket: SigBucket;
  bucketLabel: string;
  tone: "ok" | "warn" | "info" | "neutral";
}) {
  const ringClass =
    tone === "ok"
      ? "bg-[color-mix(in_oklch,var(--color-success)_12%,var(--color-surface))] text-[var(--color-success)]"
      : tone === "warn"
        ? "bg-[color-mix(in_oklch,var(--color-warning)_16%,var(--color-surface))] text-[var(--color-warning)]"
        : tone === "info"
          ? "bg-[color-mix(in_oklch,var(--color-accent)_12%,var(--color-surface))] text-[var(--color-accent)]"
          : "bg-[var(--color-bg)] text-[var(--color-muted)]";

  const direction =
    stats.pearson_r != null && stats.pearson_r > 0 ? TrendingUp : TrendingDown;
  const DirIcon = direction;

  return (
    <div className={`rounded-xl px-4 py-3 flex items-center gap-3 ${ringClass}`}>
      <DirIcon className="size-5 shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="font-semibold text-sm">{bucketLabel}</div>
        <div className="text-xs opacity-80 tabular-nums">
          r = {fmt(stats.pearson_r, 3)} · p = {fmt(stats.pearson_p, 3)} ·
          n = {stats.n}
          {bucket === "none" ? " · nicht handlungsleitend" : ""}
        </div>
      </div>
    </div>
  );
}

function SeriesRow({
  label,
  unit,
  values,
  accent,
}: {
  label: string;
  unit: string;
  values: number[];
  accent?: boolean;
}) {
  const last = values.length ? values[values.length - 1] : null;
  return (
    <>
      <div className="md:col-span-4">
        <div className="text-xs uppercase tracking-wider text-[var(--color-muted)] font-medium">
          {accent ? "Ihre Kennzahl" : "Externer Wert"}
        </div>
        <div className="text-sm font-medium leading-snug mt-0.5">{label}</div>
        <div className="text-[11px] text-[var(--color-muted)] mt-0.5 tabular-nums">
          Aktuell: {fmt(last, 2)} {unit}
        </div>
      </div>
      <div
        className={`md:col-span-8 ${
          accent ? "text-[var(--color-accent)]" : "text-[var(--color-muted)]"
        }`}
      >
        <Sparkline values={values} width={520} height={60} fillOpacity={0.12} />
      </div>
    </>
  );
}

function LoadingState() {
  return (
    <div className="space-y-3 animate-pulse">
      <div className="h-14 rounded-xl bg-[var(--color-bg)]" />
      <div className="h-14 rounded-lg bg-[var(--color-bg)]" />
      <div className="h-14 rounded-lg bg-[var(--color-bg)]" />
      <div className="h-20 rounded-lg bg-[var(--color-bg)]" />
    </div>
  );
}
