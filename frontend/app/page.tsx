"use client";

import Link from "next/link";
import useSWR from "swr";
import {
  AlertTriangle,
  AlertCircle,
  Info,
  CheckCircle2,
  ArrowRight,
  LineChart,
  TrendingUp,
  TrendingDown,
  Minus,
} from "lucide-react";
import { api } from "@/lib/api";
import { useReadiness, useRecommendations, useRuns } from "@/lib/hooks";
import { Card, ErrorMessage, Loading, MutedLink, Pill } from "@/components/ui";
import { formatRelativeTime } from "@/lib/labels";

/**
 * Heuristic: prompts that look like background scans, smoke checks, or
 * developer pokes don't belong on a manager dashboard. We keep them out
 * of the activity strip — they're still visible in /runs ("Aktivität").
 */
function isBackgroundOrTestPrompt(prompt: string | null): boolean {
  if (!prompt) return true;
  const p = prompt.toLowerCase();
  // Routine monitoring runs from the anomaly detector (German) and its
  // legacy English title.
  if (p.startsWith("routine-überwachung")) return true;
  if (p.startsWith("scan ") && p.includes("anomal")) return true;
  // Obviously-test shapes (CLI test runs, smoke prompts, evals).
  return (
    p.includes("budget test") ||
    p.includes("smoke") ||
    p.includes("noop") ||
    p.endsWith(" test") ||
    p === "test"
  );
}

function riskMeta(level: string) {
  if (level === "high")
    return {
      label: "Dringend",
      icon: AlertTriangle,
      ring: "ring-red-200 bg-red-50 text-red-700",
      dot: "bg-[var(--color-danger)]",
    } as const;
  if (level === "medium")
    return {
      label: "Beachten",
      icon: AlertCircle,
      ring: "ring-amber-200 bg-amber-50 text-amber-700",
      dot: "bg-[var(--color-warning)]",
    } as const;
  return {
    label: "Hinweis",
    icon: Info,
    ring: "ring-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-muted)]",
    dot: "bg-[var(--color-muted)]",
  } as const;
}

export default function Dashboard() {
  const ready = useReadiness();
  // Hide pytest fixtures from the dashboard so managers only see real work.
  // Power users can still drop the filter on /runs (which keeps everything).
  const pending = useRecommendations("pending", ["test"]);
  const runs = useRuns(20, ["test"]);
  // Also hide the automatic background scans + obvious test-shaped
  // prompts ("budget test", "noop"); they're noise on an exec view.
  // Keep up to 5 meaningful entries.
  const meaningfulRuns = (runs.data ?? [])
    .filter((r) => !isBackgroundOrTestPrompt(r.prompt))
    .slice(0, 5);

  return (
    <div className="space-y-10">
      {/* Enterprise hero — what the platform does + business value. */}
      <section className="relative overflow-hidden rounded-[2rem] bg-aurora p-10 sm:p-14">
        <div className="max-w-3xl">
          <div className="label-micro">Aktueller Plan</div>

          <h1 className="text-5xl sm:text-6xl font-semibold tracking-tight mt-3 leading-[1.05]">
            Causal BI
          </h1>

          <p className="mt-5 text-base sm:text-lg text-[var(--color-fg)] leading-relaxed max-w-2xl">
            Causal BI überwacht Ihre Geschäftskennzahlen autonom, erkennt
            Anomalien proaktiv und beweist mit statistischer Kausalanalyse,{" "}
            <em>warum</em> sie auftreten. Jede Empfehlung kommt mit Effektgrösse,
            Konfidenzintervall und Sensitivitätsanalyse — und durchläuft Ihre
            Freigabe, bevor sie wirksam wird.
          </p>

          <p className="mt-3 text-sm text-[var(--color-muted)] leading-relaxed max-w-2xl">
            Klassische BI zeigt Zahlen, generative AI rät. Diese Plattform
            liefert nachvollziehbare, revisionssichere Entscheidungs­grundlagen —
            und lernt aus jeder Entscheidung weiter.
          </p>

          <div className="mt-7 flex flex-wrap items-center gap-3">
            <a
              href="/investigate"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-[var(--color-accent)] text-[var(--color-accent-fg)] text-sm font-medium hover:opacity-90"
            >
              Untersuchung starten
              <span aria-hidden="true">→</span>
            </a>
            <a
              href="/kpis"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full border border-[var(--color-border)] text-sm text-[var(--color-fg)] hover:bg-[var(--color-surface-sunken)]"
            >
              Kennzahlen ansehen
            </a>
          </div>
        </div>
      </section>

      {/* Situation-at-a-glance — auto-summary of what the manager should know. */}
      <SituationBanner
        pendingCount={pending.data?.length ?? 0}
        topRisk={
          pending.data?.find((r) => r.risk_level === "high")?.risk_level ??
          pending.data?.find((r) => r.risk_level === "medium")?.risk_level ??
          (pending.data && pending.data.length > 0 ? "low" : null)
        }
        loading={pending.isLoading}
      />

      {/* Pending recommendations as memo cards with icons + CTA */}
      <section>
        <div className="mb-4 flex items-baseline justify-between gap-2">
          <h2 className="text-lg font-semibold tracking-tight">
            Empfehlungen zur Freigabe
            {pending.data && pending.data.length > 0 ? (
              <span className="ml-2 text-sm font-normal text-[var(--color-muted)]">
                · {pending.data.length} offen
              </span>
            ) : null}
          </h2>
          {pending.data && pending.data.length > 0 ? (
            <MutedLink href="/recommendations">Alle anzeigen →</MutedLink>
          ) : null}
        </div>
        {pending.error ? (
          <ErrorMessage error={pending.error} />
        ) : pending.isLoading ? (
          <Loading />
        ) : !pending.data || pending.data.length === 0 ? (
          <Card className="p-6 flex items-start gap-3 border-dashed">
            <CheckCircle2 className="size-5 text-[var(--color-success)] shrink-0 mt-0.5" />
            <div>
              <div className="font-medium">Alles im grünen Bereich.</div>
              <div className="text-sm text-[var(--color-muted)] mt-0.5">
                Es liegen aktuell keine offenen Empfehlungen vor. Das System
                meldet sich, sobald es etwas Auffälliges erkennt.
              </div>
            </div>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {pending.data.slice(0, 6).map((r) => (
              <RecommendationMemo key={r.rec_id} rec={r} />
            ))}
          </div>
        )}
      </section>

      {/* Markt-Schlaglichter — quick external context */}
      <MarketHighlights />

      {/* Activity strip — what the agent has been doing */}
      <section>
        <div className="mb-4 flex items-baseline justify-between gap-2">
          <h2 className="text-lg font-semibold tracking-tight">Aktivität</h2>
          <MutedLink href="/runs">Alle anzeigen →</MutedLink>
        </div>
        {runs.error ? (
          <ErrorMessage error={runs.error} />
        ) : runs.isLoading ? (
          <Loading />
        ) : !runs.data || meaningfulRuns.length === 0 ? (
          <Card className="p-6 text-sm text-[var(--color-muted)] border-dashed">
            Noch keine Aktivität.
          </Card>
        ) : (
          <Card>
            <ul className="divide-y divide-[var(--color-border)]">
              {meaningfulRuns.map((r) => (
                <ActivityRow key={r.run_id} run={r} />
              ))}
            </ul>
          </Card>
        )}
      </section>

      {/* Discreet system status footer */}
      <section className="pt-4 border-t border-[var(--color-border)]">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-[var(--color-muted)]">
          <SystemDot
            label="Plattform"
            ok={ready.data?.status === "ok"}
            loading={ready.isLoading}
          />
          <SystemDot
            label="Datenbank"
            ok={ready.data?.db === "ok"}
            loading={ready.isLoading}
          />
          <SystemDot
            label="Statistik-Service"
            ok={ready.data?.r_service === "ok"}
            loading={ready.isLoading}
          />
          {ready.data?.version ? (
            <span className="ml-auto mono">v{ready.data.version}</span>
          ) : null}
        </div>
      </section>
    </div>
  );
}

/** Top-line banner: tells the manager what state the business is in. */
function SituationBanner({
  pendingCount,
  topRisk,
  loading,
}: {
  pendingCount: number;
  topRisk: string | null;
  loading: boolean;
}) {
  if (loading) {
    return (
      <Card className="p-5">
        <Loading label="Lage wird ermittelt …" />
      </Card>
    );
  }
  if (pendingCount === 0) {
    return (
      <Card className="p-5 flex items-start gap-3 bg-emerald-50 border-emerald-200">
        <CheckCircle2 className="size-6 text-emerald-600 shrink-0" />
        <div>
          <div className="font-semibold text-emerald-900">
            Keine offenen Punkte
          </div>
          <div className="text-sm text-emerald-800 mt-0.5">
            Das System überwacht Ihre Kennzahlen im Hintergrund. Sie werden
            informiert, sobald etwas Bemerkenswertes auffällt.
          </div>
        </div>
      </Card>
    );
  }
  const meta = riskMeta(topRisk ?? "low");
  const Icon = meta.icon;
  const subject =
    topRisk === "high"
      ? "Dringende Empfehlung"
      : topRisk === "medium"
        ? "Empfehlung zur Prüfung"
        : "Information";

  return (
    <Card
      className={`p-5 flex items-start gap-3 ring-1 ${meta.ring} border-transparent`}
    >
      <Icon className="size-6 shrink-0 mt-0.5" />
      <div className="flex-1">
        <div className="font-semibold">
          {pendingCount === 1
            ? `${subject} wartet auf Sie`
            : `${pendingCount} Empfehlungen warten auf Sie`}
        </div>
        <div className="text-sm mt-0.5 opacity-90">
          {topRisk === "high"
            ? "Mindestens eine davon ist als dringend eingestuft. Prüfen Sie sie zuerst."
            : "Bitte unten durchsehen und freigeben oder ablehnen."}
        </div>
      </div>
    </Card>
  );
}

function RecommendationMemo({
  rec,
}: {
  rec: import("@/lib/types").Recommendation;
}) {
  const meta = riskMeta(rec.risk_level);
  const Icon = meta.icon;
  return (
    <Link
      href={`/recommendations/${rec.rec_id}`}
      className="group block bg-[var(--color-surface)] border border-[var(--color-border)] rounded-2xl p-5 hover:border-[var(--color-accent)] transition-colors"
    >
      <div className="flex items-start gap-3">
        <div
          className={`size-10 rounded-xl flex items-center justify-center shrink-0 ${meta.ring}`}
        >
          <Icon className="size-5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[11px] uppercase tracking-wider font-medium opacity-80">
            {meta.label} · {formatRelativeTime(rec.created_at)}
          </div>
          <h3 className="text-base font-semibold mt-0.5 leading-snug">
            {rec.title}
          </h3>
          <p className="text-sm text-[var(--color-muted)] mt-2 line-clamp-3 leading-relaxed">
            {rec.body}
          </p>
          <div className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-[var(--color-accent)] group-hover:gap-2 transition-all">
            Ansehen und entscheiden
            <ArrowRight className="size-4" />
          </div>
        </div>
      </div>
    </Link>
  );
}

function ActivityRow({ run }: { run: import("@/lib/types").AgentRun }) {
  // Wenn eine Empfehlung aus diesem Run entstanden ist, linken wir
  // direkt darauf — der Manager sieht das Ergebnis statt nur den
  // Status. Ohne Empfehlung führt der Klick auf die Run-Detail-
  // Seite (die volle Beweiskette).
  const top = run.top_recommendation;
  const href = top ? `/recommendations/${top.rec_id}` : `/runs/${run.run_id}`;
  const statusDot =
    run.status === "ok"
      ? "bg-[var(--color-success)]"
      : run.status === "running"
        ? "bg-[var(--color-accent)] animate-pulse"
        : run.status === "error"
          ? "bg-[var(--color-danger)]"
          : "bg-[var(--color-muted)]";

  const riskTone =
    top?.risk_level === "high"
      ? "danger"
      : top?.risk_level === "medium"
        ? "warning"
        : top
          ? "accent"
          : "neutral";

  return (
    <li className="px-4 py-3 hover:bg-[var(--color-bg)]">
      <Link href={href} className="flex items-start gap-3">
        <span className={`size-2 rounded-full shrink-0 mt-2 ${statusDot}`} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-sm font-medium text-[var(--color-fg)]">
            <span className="truncate">{run.prompt ?? "(ohne Titel)"}</span>
          </div>
          {top ? (
            <div className="mt-1 flex items-baseline gap-2">
              <Pill tone={riskTone}>{riskLabelShort(top.risk_level)}</Pill>
              <span className="text-xs text-[var(--color-muted)] truncate">
                {top.title}
              </span>
            </div>
          ) : run.status === "ok" ? (
            <div className="mt-1 text-xs text-[var(--color-muted)]">
              Keine Empfehlung — Lage unauffällig.
            </div>
          ) : null}
        </div>
        <span className="text-xs text-[var(--color-muted)] shrink-0 mt-1">
          {formatRelativeTime(run.started_at)}
        </span>
      </Link>
    </li>
  );
}

function riskLabelShort(level: string) {
  if (level === "high") return "Dringend";
  if (level === "medium") return "Beachten";
  return "Hinweis";
}

function MarketHighlights() {
  const { data, isLoading } = useSWR(
    ["dashboard-market", "5d"],
    () =>
      api.externalMarket({
        period: "5d",
        symbols: ["^SSMI", "EURCHF=X", "USDCHF=X"],
      }),
    { revalidateOnFocus: false },
  );

  return (
    <section>
      <div className="mb-4 flex items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold tracking-tight">
          Markt-Schlaglichter
        </h2>
        <MutedLink href="/markt-radar">Markt-Radar öffnen →</MutedLink>
      </div>
      <Card className="p-5">
        {isLoading ? (
          <Loading label="Lade Marktdaten …" />
        ) : data?.error ? (
          <div className="text-sm text-[var(--color-muted)] flex items-center gap-2">
            <LineChart className="size-4" />
            Externe Daten gerade nicht verfügbar.
          </div>
        ) : !data?.items?.length ? (
          <div className="text-sm text-[var(--color-muted)]">
            Keine Marktdaten verfügbar.
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
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
              const Icon =
                trend === "up" ? TrendingUp : trend === "down" ? TrendingDown : Minus;
              return (
                <div key={m.symbol} className="flex items-center gap-3">
                  <div className={`shrink-0 ${color}`}>
                    <Icon className="size-5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium leading-tight">
                      {m.name}
                    </div>
                    <div className={`text-xs ${color} tabular-nums`}>
                      {m.last.toLocaleString("de-CH", {
                        maximumFractionDigits: 4,
                      })}
                      {m.change_pct != null
                        ? ` · ${m.change_pct > 0 ? "+" : ""}${m.change_pct.toFixed(2)} %`
                        : ""}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </section>
  );
}

function SystemDot({
  label,
  ok,
  loading,
}: {
  label: string;
  ok: boolean;
  loading: boolean;
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={`size-1.5 rounded-full ${
          loading
            ? "bg-[var(--color-muted)] animate-pulse"
            : ok
              ? "bg-[var(--color-success)]"
              : "bg-[var(--color-danger)]"
        }`}
      />
      {label}
    </span>
  );
}

