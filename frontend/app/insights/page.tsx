"use client";

import { useState } from "react";
import useSWR from "swr";
import {
  Lightbulb,
  TrendingDown,
  TrendingUp,
  Clock,
  ShieldCheck,
  Activity,
  Loader2,
} from "lucide-react";
import { useInsights } from "@/lib/hooks";
import { api } from "@/lib/api";
import { Card, ErrorMessage, Loading } from "@/components/ui";
import type { Insight } from "@/lib/types";
import {
  formatRelativeTime,
  friendlyComponent,
  friendlyKpi,
  insightSentence,
} from "@/lib/labels";

function severityBg(
  severity: string | null | undefined,
): "danger" | "warning" | "neutral" {
  if (severity === "high") return "danger";
  if (severity === "medium") return "warning";
  return "neutral";
}

const SEVERITY_RING: Record<"danger" | "warning" | "neutral", string> = {
  danger: "bg-red-50 text-red-700 ring-red-200",
  warning: "bg-amber-50 text-amber-700 ring-amber-200",
  neutral:
    "bg-[var(--color-bg)] text-[var(--color-muted)] ring-[var(--color-border)]",
};

const SEVERITY_LABEL: Record<string, string> = {
  high: "Dringend",
  medium: "Beachten",
  low: "Hinweis",
};

function fmtSignedPct(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const pct = v * 100;
  const sign = pct > 0 ? "+" : pct < 0 ? "−" : "";
  return `${sign}${Math.abs(pct).toFixed(1).replace(".", ",")} %`;
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("de-CH", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

export default function InsightsPage() {
  const [showTests, setShowTests] = useState(false);
  const { data, error, isLoading, mutate } = useInsights(
    50,
    showTests ? [] : ["test"],
  );

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="max-w-3xl">
          <h1 className="text-2xl font-semibold tracking-tight">
            Lernerfahrungen
          </h1>
          <p className="text-sm text-[var(--color-muted)] mt-1 leading-relaxed">
            Hier sammelt das System, was es über Ihr Geschäft gelernt hat —
            jede wichtige Beobachtung, Ihre Entscheidung dazu, und das
            gemessene Ergebnis. Mit der Zeit wächst daraus ein durchsuchbares
            Erfahrungswissen: „Hatten wir das schon mal? Was hat damals
            geholfen?"
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm text-[var(--color-muted)] cursor-pointer select-none shrink-0">
          <input
            type="checkbox"
            checked={showTests}
            onChange={(e) => setShowTests(e.target.checked)}
            className="accent-[var(--color-accent)]"
          />
          Test-Einträge einblenden
        </label>
      </div>

      {error ? (
        <ErrorMessage error={error} />
      ) : isLoading ? (
        <Loading />
      ) : !data || data.length === 0 ? (
        <Card className="p-8 text-center border-dashed">
          <Lightbulb className="size-8 text-[var(--color-muted)] mx-auto mb-3" />
          <div className="font-medium">Noch keine Erfahrungen gesammelt.</div>
          <div className="text-sm text-[var(--color-muted)] mt-1">
            Sobald die erste Empfehlung freigegeben oder eine Auffälligkeit
            erkannt wird, erscheint sie hier.
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {data.map((i, idx) => (
            <InsightCard
              key={i.insight_id ?? idx}
              insight={i}
              onMeasured={() => mutate()}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function InsightCard({
  insight,
  onMeasured,
}: {
  insight: Insight;
  onMeasured: () => void;
}) {
  const p = insight.properties ?? {};
  const severity = (p.severity as string | null) ?? null;
  const tone = severityBg(severity);
  const change = p.relative_change as number | undefined;
  const direction =
    change != null && Number.isFinite(change)
      ? change > 0
        ? "up"
        : change < 0
          ? "down"
          : "flat"
      : "flat";

  const sentence = insightSentence({
    kpi: p.kpi as string | undefined,
    component: (p.component as string | null) ?? null,
    relative_change: change,
    period_start: p.period_start as string | undefined,
    period_end: p.period_end as string | undefined,
  });

  return (
    <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-2xl p-5">
      <div className="flex items-start gap-3">
        <div
          className={`size-10 rounded-xl flex items-center justify-center shrink-0 ring-1 ${SEVERITY_RING[tone]}`}
        >
          {direction === "down" ? (
            <TrendingDown className="size-5" />
          ) : direction === "up" ? (
            <TrendingUp className="size-5" />
          ) : (
            <Lightbulb className="size-5" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[11px] uppercase tracking-wider font-medium opacity-80 flex flex-wrap items-center gap-2">
            <span>
              {severity ? SEVERITY_LABEL[severity] ?? severity : "Beobachtung"}
            </span>
            {p.component ? (
              <>
                <span className="text-[var(--color-muted)]">·</span>
                <span>{friendlyComponent(String(p.component))}</span>
              </>
            ) : null}
          </div>
          <p className="text-[15px] font-medium mt-1 leading-snug">
            {sentence}
          </p>

          <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
            <DecisionField insight={insight} />
            <OutcomeField insight={insight} onMeasured={onMeasured} />
          </div>

          <div className="mt-3 text-[11px] text-[var(--color-muted)]">
            Festgehalten {formatRelativeTime(insight.created_at)} · Kennzahl{" "}
            <span className="font-medium">
              {friendlyKpi(p.kpi as string | undefined)}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

function DecisionField({ insight }: { insight: Insight }) {
  const d = insight.decision ?? null;
  if (!d) {
    return (
      <FieldRow
        icon={ShieldCheck}
        label="Entscheidung"
        value="Noch nicht freigegeben"
      />
    );
  }
  const dLabel =
    d.decision === "approve"
      ? "Freigegeben"
      : d.decision === "reject"
        ? "Abgelehnt"
        : d.decision === "modify"
          ? "Geändert"
          : d.decision;
  const who = d.approver ? ` durch ${d.approver}` : "";
  const when = d.decided_at ? ` ${formatRelativeTime(d.decided_at)}` : "";
  return (
    <FieldRow
      icon={ShieldCheck}
      label="Entscheidung"
      value={`${dLabel}${who}${when}`}
    />
  );
}

function OutcomeField({
  insight,
  onMeasured,
}: {
  insight: Insight;
  onMeasured: () => void;
}) {
  const d = insight.decision ?? null;
  const o = insight.outcome ?? null;

  if (o) {
    const observed = fmtSignedPct(o.observed_effect);
    const expected =
      o.expected_effect != null ? fmtSignedPct(o.expected_effect) : null;
    const detail = expected
      ? `Beobachtet ${observed} · Erwartet ${expected}`
      : `Beobachtet ${observed}`;
    return <FieldRow icon={Activity} label="Wirkung" value={detail} />;
  }

  if (!d || d.decision !== "approve") {
    return (
      <FieldRow
        icon={Clock}
        label="Wirkung"
        value="Wird nach Freigabe gemessen"
      />
    );
  }

  return (
    <div className="flex items-start gap-1.5">
      <Clock className="size-3.5 text-[var(--color-muted)] mt-0.5 shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="text-[var(--color-muted)]">Wirkung</div>
        <div className="font-medium leading-tight">
          Wird gemessen am {fmtDate(d.outcome_due_at)}
        </div>
        <MeasureNowButton decisionId={d.decision_id} onMeasured={onMeasured} />
      </div>
    </div>
  );
}

function MeasureNowButton({
  decisionId,
  onMeasured,
}: {
  decisionId: string;
  onMeasured: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function trigger() {
    setBusy(true);
    setErr(null);
    try {
      const res = await api.measureDecisionOutcome(decisionId, {
        post_period_days: 30,
      });
      if (res.status === "measured" || res.status === "already_measured") {
        onMeasured();
      } else if (res.error) {
        setErr(res.error);
      } else if (res.reason) {
        setErr(`Noch nicht messbar: ${res.reason}`);
      } else {
        setErr(`Status: ${res.status}`);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-1">
      <button
        type="button"
        onClick={trigger}
        disabled={busy}
        className="text-[11px] underline text-[var(--color-accent)] hover:opacity-80 disabled:opacity-50 inline-flex items-center gap-1"
      >
        {busy ? <Loader2 className="size-3 animate-spin" /> : null}
        Jetzt messen (Demo)
      </button>
      {err ? (
        <div className="mt-0.5 text-[11px] text-[var(--color-danger)]">
          {err}
        </div>
      ) : null}
    </div>
  );
}

function FieldRow({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Lightbulb;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-start gap-1.5">
      <Icon className="size-3.5 text-[var(--color-muted)] mt-0.5 shrink-0" />
      <div className="min-w-0">
        <div className="text-[var(--color-muted)]">{label}</div>
        <div className="font-medium leading-tight">{value}</div>
      </div>
    </div>
  );
}
