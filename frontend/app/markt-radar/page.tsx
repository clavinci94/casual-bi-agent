"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import {
  Newspaper,
  TrendingUp,
  LineChart,
  ExternalLink,
} from "lucide-react";
import { api } from "@/lib/api";
import { Card, ErrorMessage, Empty } from "@/components/ui";
import { PageHeader } from "@/components/page-header";
import { Sparkline } from "@/components/sparkline";
import { BriefingCard } from "@/components/briefing-card";
import { ShopifyStatusWidget } from "@/components/shopify-status-widget";
import { CommerceCalendarWidget } from "@/components/commerce-calendar-widget";
import { CorrelationCard } from "@/components/correlation-card";

// Curated symbol sets — split so DACH-focused merchants see local
// indices / FX side-by-side, separately from the global macro picture.
const DACH_SYMBOLS = [
  "^SSMI",
  "^GDAXI",
  "^ATX",
  "EURCHF=X",
  "USDCHF=X",
  "CHFEUR=X",
];

const GLOBAL_SYMBOLS = [
  "^GSPC",
  "DX-Y.NYB",
  "CL=F",
  "GC=F",
  "SHOP",
  "BTC-USD",
];

function fmt(n: number, digits = 2): string {
  return n.toLocaleString("de-CH", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function fmtSignedPct(p: number | null): string {
  if (p == null || !Number.isFinite(p)) return "—";
  const sign = p > 0 ? "+" : p < 0 ? "-" : "";
  return `${sign}${Math.abs(p).toFixed(2)} %`;
}

export default function MarktRadarPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        label="Aussenwelt"
        title="Markt-Radar"
        description="Was draussen passiert und was es für Ihren Shop heute bedeutet. Der Agent fasst oben das Wichtigste in Klartext zusammen, darunter zeigen wir die Roh-Signale aus Markt, Plattform und Konsumenten-Interesse — und unten können Sie eigene Kennzahlen gegen externe Reihen prüfen."
      />

      {/* 1 — Tagesbriefing (full width, top) */}
      <BriefingCard />

      {/* 2-3 — Märkte: Schweiz/DACH neben Global */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <MarketWidget
          title="Schweiz &amp; DACH"
          subtitle="Indizes &amp; Wechselkurse"
          symbols={DACH_SYMBOLS}
        />
        <MarketWidget
          title="Globale Märkte"
          subtitle="Leitindex, Öl, Gold, Shopify-Aktie"
          symbols={GLOBAL_SYMBOLS}
        />
      </section>

      {/* 4 — Plattform-Kontext (Shopify-Status + Commerce-Kalender) */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ShopifyStatusWidget />
        <CommerceCalendarWidget />
      </section>

      {/* 5-6 — Aussenwelt: DACH-News neben Trends */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <NewsWidget />
        <TrendsWidget />
      </section>

      {/* 7 — Korrelation (full width, bottom) */}
      <CorrelationCard />
    </div>
  );
}

// -------------------------------------------------------------------- Markets

function MarketWidget({
  title,
  subtitle,
  symbols,
}: {
  title: string;
  subtitle: string;
  symbols: string[];
}) {
  const { data, error, isLoading } = useSWR(
    ["external-market", symbols.join(",")],
    () => api.externalMarket({ period: "1mo", symbols }),
    { revalidateOnFocus: false },
  );

  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 mb-3">
        <span className="size-8 rounded-lg bg-[var(--color-bg)] flex items-center justify-center">
          <LineChart className="size-4" />
        </span>
        <div>
          <div className="text-xs uppercase tracking-wider text-[var(--color-muted)] font-medium">
            {subtitle}
          </div>
          <h2 className="text-base font-semibold">{title}</h2>
        </div>
      </div>

      {error ? (
        <ErrorMessage error={error} />
      ) : isLoading ? (
        <div className="text-sm text-[var(--color-muted)] animate-pulse">
          Lade Marktdaten …
        </div>
      ) : data?.error ? (
        <div className="text-xs text-[var(--color-muted)]">{data.error}</div>
      ) : !data?.items?.length ? (
        <Empty>Keine Marktdaten verfügbar.</Empty>
      ) : (
        <ul className="divide-y divide-[var(--color-border)]">
          {data.items.map((m) => {
            const trend =
              m.change_pct == null
                ? "flat"
                : m.change_pct > 0.1
                  ? "up"
                  : m.change_pct < -0.1
                    ? "down"
                    : "flat";
            const color =
              trend === "up"
                ? "text-[var(--color-success)]"
                : trend === "down"
                  ? "text-[var(--color-danger)]"
                  : "text-[var(--color-muted)]";
            return (
              <li
                key={m.symbol}
                className="py-2.5 flex items-center justify-between gap-3"
              >
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium">{m.name}</div>
                  <div className="text-[11px] text-[var(--color-muted)] mono">
                    {m.symbol}
                  </div>
                </div>
                <div className={color}>
                  <Sparkline
                    values={m.history.map((h) => h.close)}
                    width={80}
                    height={28}
                  />
                </div>
                <div className="text-right tabular-nums">
                  <div className="text-sm font-semibold">{fmt(m.last, 2)}</div>
                  <div className={`text-xs ${color}`}>
                    {fmtSignedPct(m.change_pct)}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <div className="mt-3 text-[11px] text-[var(--color-muted)]">
        Quelle Yahoo Finance · letzte 30 Tage
      </div>
    </Card>
  );
}

// ----------------------------------------------------------------------- News

function NewsWidget() {
  const [query, setQuery] = useState("");
  const [region, setRegion] = useState<"dach" | "default">("dach");
  const { data, error, isLoading } = useSWR(
    ["external-news", query, region],
    () => api.externalNews({ q: query, max: 8, region }),
  );

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="size-8 rounded-lg bg-[var(--color-bg)] flex items-center justify-center shrink-0">
            <Newspaper className="size-4" />
          </span>
          <div className="min-w-0">
            <div className="text-xs uppercase tracking-wider text-[var(--color-muted)] font-medium">
              {region === "dach" ? "DACH-Wirtschaftspresse" : "Internationale Presse"}
            </div>
            <h2 className="text-base font-semibold">Aktuelle Schlagzeilen</h2>
          </div>
        </div>
        <div className="inline-flex rounded-md border border-[var(--color-border)] overflow-hidden shrink-0">
          {(["dach", "default"] as const).map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setRegion(r)}
              className={`px-2.5 py-1 text-xs font-medium ${
                r === region
                  ? "bg-[var(--color-accent)] text-[var(--color-accent-fg)]"
                  : "text-[var(--color-muted)] hover:bg-[var(--color-bg)]"
              }`}
              aria-pressed={r === region}
            >
              {r === "dach" ? "DACH" : "Welt"}
            </button>
          ))}
        </div>
      </div>

      <input
        type="search"
        placeholder='Suchbegriff (z.B. "Inflation"), leer = Top-News'
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="w-full mb-3 px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
      />

      {error ? (
        <ErrorMessage error={error} />
      ) : isLoading ? (
        <div className="text-sm text-[var(--color-muted)] animate-pulse">
          Lade Nachrichten …
        </div>
      ) : data?.error ? (
        <div className="text-xs text-[var(--color-muted)]">{data.error}</div>
      ) : !data?.results?.length ? (
        <Empty>Keine Treffer.</Empty>
      ) : (
        <ul className="space-y-3 max-h-[360px] overflow-y-auto pr-1">
          {data.results.map((n, idx) => (
            <li key={`${n.url ?? idx}`} className="text-sm">
              {n.url ? (
                <a
                  href={n.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium hover:underline text-[var(--color-fg)]"
                >
                  {n.title ?? "(ohne Titel)"}
                  <ExternalLink className="inline size-3 ml-1 opacity-60" />
                </a>
              ) : (
                <span className="font-medium">{n.title ?? "(ohne Titel)"}</span>
              )}
              <div className="text-xs text-[var(--color-muted)] mt-0.5">
                {n.source ?? "—"}
                {n.published_at ? ` · ${formatDate(n.published_at)}` : ""}
              </div>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-3 text-[11px] text-[var(--color-muted)]">
        Quelle {data?.provider === "newsapi" ? "NewsAPI" : "Public RSS"} · live
      </div>
    </Card>
  );
}

// --------------------------------------------------------------------- Trends

function TrendsWidget() {
  // Load the shop's top revenue-generating categories once on mount and
  // use them as both the initial keywords and a clickable suggestion list.
  // Falls back gracefully if the shop has no orders yet.
  const { data: topCats } = useSWR(
    ["shopify-top-categories"],
    () => api.shopifyTopCategories({ limit: 5, window_days: 90 }),
    { revalidateOnFocus: false },
  );
  const suggestions: string[] = (topCats?.categories ?? [])
    .map((c) => c.product_type.toLowerCase())
    .slice(0, 5);

  const [draft, setDraft] = useState("");
  const [keywords, setKeywords] = useState<string[]>([]);
  const [autoApplied, setAutoApplied] = useState(false);

  // When the shop's categories arrive, seed both the input and the active
  // query — but only once, so the user can still type their own values.
  useEffect(() => {
    if (autoApplied) return;
    if (suggestions.length === 0) return;
    setDraft(suggestions.join(", "));
    setKeywords(suggestions);
    setAutoApplied(true);
  }, [autoApplied, suggestions]);

  const { data, error, isLoading } = useSWR(
    keywords.length ? ["external-trends", keywords.join(",")] : null,
    () => api.externalTrends({ keywords, geo: "CH", timeframe: "today 3-m" }),
  );

  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 mb-3">
        <span className="size-8 rounded-lg bg-[var(--color-bg)] flex items-center justify-center">
          <TrendingUp className="size-4" />
        </span>
        <div>
          <div className="text-xs uppercase tracking-wider text-[var(--color-muted)] font-medium">
            Konsumenten-Interesse
          </div>
          <h2 className="text-base font-semibold">Such-Trends (Schweiz)</h2>
        </div>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          setKeywords(
            draft
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean)
              .slice(0, 5),
          );
        }}
        className="flex gap-2 mb-3"
      >
        <input
          type="text"
          placeholder="Begriffe mit Komma getrennt (1–5)"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="flex-1 px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
        />
        <button
          type="submit"
          className="px-3 py-2 rounded-md bg-[var(--color-accent)] text-[var(--color-accent-fg)] text-sm font-medium hover:opacity-90"
        >
          Anzeigen
        </button>
      </form>

      {suggestions.length > 0 ? (
        <div className="-mt-1 mb-3 flex flex-wrap items-center gap-1.5 text-[11px] text-[var(--color-muted)]">
          <span>Ihre Top-Kategorien:</span>
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => {
                setDraft(s);
                setKeywords([s]);
              }}
              className="px-2 py-0.5 rounded-full border border-[var(--color-border)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]"
            >
              {s}
            </button>
          ))}
        </div>
      ) : null}

      {!keywords.length ? (
        <Empty>Begriffe eingeben und Enter drücken.</Empty>
      ) : error ? (
        <ErrorMessage error={error} />
      ) : isLoading ? (
        <div className="text-sm text-[var(--color-muted)] animate-pulse">
          Lade Trends …
        </div>
      ) : data?.error ? (
        <div className="text-xs text-[var(--color-muted)]">
          Google liefert gerade nichts (Rate-Limit). Bitte gleich nochmals
          versuchen.
        </div>
      ) : !data?.timeline?.length ? (
        <Empty>Keine Daten.</Empty>
      ) : (
        <div className="space-y-3">
          {keywords.map((kw) => {
            const values = (data.timeline ?? []).map((row) => {
              const v = row[kw];
              return typeof v === "number" ? v : null;
            });
            const max = Math.max(0, ...values.filter((v): v is number => v != null));
            return (
              <div key={kw}>
                <div className="flex items-center justify-between text-sm mb-1">
                  <span className="font-medium">{kw}</span>
                  <span className="text-xs text-[var(--color-muted)] tabular-nums">
                    Spitze {max} / 100
                  </span>
                </div>
                <div className="text-[var(--color-accent)]">
                  <Sparkline values={values} width={400} height={36} />
                </div>
              </div>
            );
          })}

          {data.related_topics?.length ? (
            <div className="pt-2 border-t border-[var(--color-border)]">
              <div className="text-[11px] uppercase tracking-wider text-[var(--color-muted)] mb-1">
                Verwandte Themen
              </div>
              <div className="flex flex-wrap gap-1">
                {data.related_topics.slice(0, 8).map((t) => (
                  <span
                    key={t}
                    className="text-xs px-2 py-0.5 rounded-full bg-[var(--color-bg)] text-[var(--color-muted)]"
                  >
                    {t}
                  </span>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      )}

      <div className="mt-3 text-[11px] text-[var(--color-muted)]">
        Quelle Google Trends · Werte 0–100 relativ zur Spitze des Zeitraums
      </div>
    </Card>
  );
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString("de-CH", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

