"use client";

import { useState } from "react";
import useSWR from "swr";
import {
  Search,
  Newspaper,
  TrendingUp,
  LineChart,
  ExternalLink,
  Sparkles,
} from "lucide-react";
import { api } from "@/lib/api";
import { Card, ErrorMessage, Empty, Pill } from "@/components/ui";
import { Sparkline } from "@/components/sparkline";

function fmt(n: number, digits = 2): string {
  return n.toLocaleString("de-CH", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function fmtSignedPct(p: number | null): string {
  if (p == null || !Number.isFinite(p)) return "—";
  const sign = p > 0 ? "+" : p < 0 ? "−" : "";
  return `${sign}${Math.abs(p).toFixed(2)} %`;
}

export default function MarktRadarPage() {
  return (
    <div className="space-y-8">
      <header className="max-w-3xl">
        <h1 className="text-2xl font-semibold tracking-tight">Markt-Radar</h1>
        <p className="text-sm text-[var(--color-muted)] mt-1 leading-relaxed">
          Was draussen passiert, das Ihre Geschäftslage beeinflussen
          könnte: aktuelle Nachrichten, Trend-Bewegungen bei
          Konsumenten-Suchen, Börsen- und Wechselkurs-Daten, und eine
          Klartext-Web-Suche. Der Agent zieht dieselben Quellen heran,
          wenn er Anomalien erklärt — hier sehen Sie sie roh.
        </p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <MarketWidget />
        <NewsWidget />
        <SearchWidget />
        <TrendsWidget />
      </div>
    </div>
  );
}

// -------------------------------------------------------------------- Markets

function MarketWidget() {
  const { data, error, isLoading } = useSWR(["external-market", "1mo"], () =>
    api.externalMarket({ period: "1mo" }),
  );

  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 mb-3">
        <span className="size-8 rounded-lg bg-[var(--color-bg)] flex items-center justify-center">
          <LineChart className="size-4" />
        </span>
        <div>
          <div className="text-xs uppercase tracking-wider text-[var(--color-muted)] font-medium">
            Börsen &amp; Devisen
          </div>
          <h2 className="text-base font-semibold">Märkte heute</h2>
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
  const { data, error, isLoading } = useSWR(
    ["external-news", query],
    () => api.externalNews({ q: query, max: 8 }),
  );

  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 mb-3">
        <span className="size-8 rounded-lg bg-[var(--color-bg)] flex items-center justify-center">
          <Newspaper className="size-4" />
        </span>
        <div className="flex-1">
          <div className="text-xs uppercase tracking-wider text-[var(--color-muted)] font-medium">
            Wirtschaftspresse
          </div>
          <h2 className="text-base font-semibold">Aktuelle Schlagzeilen</h2>
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

// --------------------------------------------------------------------- Search

function SearchWidget() {
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const { data, error, isLoading } = useSWR(
    query ? ["external-search", query] : null,
    () => api.externalSearch({ q: query, max: 5 }),
  );

  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 mb-3">
        <span className="size-8 rounded-lg bg-[var(--color-bg)] flex items-center justify-center">
          <Search className="size-4" />
        </span>
        <div>
          <div className="text-xs uppercase tracking-wider text-[var(--color-muted)] font-medium">
            Web-Suche
          </div>
          <h2 className="text-base font-semibold">Frag das Internet</h2>
        </div>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(draft.trim());
        }}
        className="flex gap-2 mb-3"
      >
        <input
          type="search"
          placeholder='z.B. "Schweizer E-Commerce-Marktanteile 2026"'
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="flex-1 px-3 py-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
        />
        <button
          type="submit"
          className="px-3 py-2 rounded-md bg-[var(--color-accent)] text-[var(--color-accent-fg)] text-sm font-medium hover:opacity-90"
        >
          Suchen
        </button>
      </form>

      {!query ? (
        <Empty>Geben Sie eine Frage ein und drücken Sie Enter.</Empty>
      ) : error ? (
        <ErrorMessage error={error} />
      ) : isLoading ? (
        <div className="text-sm text-[var(--color-muted)] animate-pulse">
          Suche läuft …
        </div>
      ) : data?.error ? (
        <div className="text-xs space-y-2">
          <Pill tone="warning">nicht konfiguriert</Pill>
          <div className="text-[var(--color-muted)] leading-relaxed">
            {data.error.includes("TAVILY")
              ? "Tavily-API-Schlüssel fehlt im Backend. In .env eintragen (TAVILY_API_KEY=tvly-…) und Backend neu starten."
              : data.error}
          </div>
        </div>
      ) : !data?.results?.length ? (
        <Empty>Keine Treffer.</Empty>
      ) : (
        <div className="space-y-3 max-h-[340px] overflow-y-auto pr-1">
          {data.answer ? (
            <div className="bg-[var(--color-bg)] rounded-md p-3 border border-[var(--color-border)]">
              <div className="text-[11px] uppercase tracking-wider text-[var(--color-accent)] font-medium flex items-center gap-1 mb-1">
                <Sparkles className="size-3" /> KI-Zusammenfassung
              </div>
              <p className="text-sm leading-relaxed">{data.answer}</p>
            </div>
          ) : null}
          {data.results.map((r, idx) => (
            <div key={`${r.url ?? idx}`} className="text-sm">
              <a
                href={r.url ?? "#"}
                target="_blank"
                rel="noopener noreferrer"
                className="font-medium hover:underline text-[var(--color-fg)]"
              >
                {r.title ?? "(ohne Titel)"}
                <ExternalLink className="inline size-3 ml-1 opacity-60" />
              </a>
              {r.content ? (
                <p className="text-xs text-[var(--color-muted)] mt-0.5 line-clamp-3">
                  {r.content}
                </p>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

// --------------------------------------------------------------------- Trends

function TrendsWidget() {
  const [draft, setDraft] = useState("sneaker, adidas");
  const [keywords, setKeywords] = useState<string[]>([]);
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

