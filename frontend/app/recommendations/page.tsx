"use client";

import { useMemo, useState } from "react";
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
import type { Recommendation } from "@/lib/types";

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
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const { data, error, isLoading, mutate } = useSWR(
    ["recommendations-index", filter],
    () => api.listRecommendations(filter, 100, ["test"]),
  );

  // Multi-select is only meaningful for pending rows — decided ones are
  // visible but not selectable. Clear selection when filter changes.
  function toggle(rec: Recommendation) {
    if (rec.status !== "pending") return;
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(rec.rec_id)) next.delete(rec.rec_id);
      else next.add(rec.rec_id);
      return next;
    });
  }
  function changeFilter(next: StatusFilter) {
    setSelected(new Set());
    setFilter(next);
  }

  const selectableIds = useMemo(
    () => (data ?? []).filter((r) => r.status === "pending").map((r) => r.rec_id),
    [data],
  );
  const allSelected =
    selectableIds.length > 0 && selectableIds.every((id) => selected.has(id));

  function selectAll() {
    setSelected(new Set(selectableIds));
  }
  function clearSelection() {
    setSelected(new Set());
  }

  return (
    <div className="space-y-6 max-w-5xl">
      <PageHeader
        label="Handlungsempfehlungen"
        title="Empfehlungen"
        description="Alle vom Agenten erzeugten Empfehlungen — offen, freigegeben oder abgelehnt. Markieren Sie mehrere offene Empfehlungen, um sie gemeinsam zu entscheiden, oder klicken Sie eine Karte für die volle Beweisführung."
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
                  onClick={() => changeFilter(o.v)}
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

      {selected.size > 0 ? (
        <BulkActionBar
          selectedCount={selected.size}
          rec_ids={[...selected]}
          onDone={async () => {
            clearSelection();
            await mutate();
          }}
          onClear={clearSelection}
        />
      ) : null}

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
        <>
          <div className="flex items-center justify-between text-sm text-[var(--color-muted)] -mb-2">
            <span>
              {data.length} {data.length === 1 ? "Empfehlung" : "Empfehlungen"}
              {selectableIds.length > 0
                ? ` · ${selectableIds.length} offen, auswählbar`
                : ""}
            </span>
            {selectableIds.length > 0 ? (
              <button
                type="button"
                onClick={allSelected ? clearSelection : selectAll}
                className="text-[var(--color-accent)] hover:underline"
              >
                {allSelected
                  ? "Auswahl aufheben"
                  : `Alle ${selectableIds.length} offene auswählen`}
              </button>
            ) : null}
          </div>

          <ul className="space-y-3">
            {data.map((r) => (
              <RecommendationRow
                key={r.rec_id}
                rec={r}
                checked={selected.has(r.rec_id)}
                onToggle={() => toggle(r)}
              />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function RecommendationRow({
  rec,
  checked,
  onToggle,
}: {
  rec: Recommendation;
  checked: boolean;
  onToggle: () => void;
}) {
  const meta = riskMeta(rec.risk_level);
  const Icon = meta.Icon;
  const isPending = rec.status === "pending";

  return (
    <li
      className={`flex items-start gap-4 bg-[var(--color-surface)] border rounded-2xl p-5 transition-colors ${
        checked
          ? "border-[var(--color-accent)] ring-2 ring-[var(--color-accent)] ring-opacity-20"
          : "border-[var(--color-border)] hover:border-[var(--color-accent)]"
      }`}
    >
      <label
        className={`shrink-0 size-5 mt-1.5 flex items-center justify-center rounded border ${
          isPending
            ? "cursor-pointer border-[var(--color-border)] hover:border-[var(--color-accent)]"
            : "cursor-not-allowed border-[var(--color-border)] opacity-30"
        }`}
        title={isPending ? "Auswählen" : "Bereits entschieden"}
      >
        <input
          type="checkbox"
          checked={checked}
          disabled={!isPending}
          onChange={onToggle}
          className="sr-only"
        />
        {checked ? (
          <span className="size-3 rounded-sm bg-[var(--color-accent)]" />
        ) : null}
      </label>

      <span
        className={`size-10 rounded-xl flex items-center justify-center shrink-0 ${meta.ring}`}
      >
        <Icon className="size-5" />
      </span>

      <Link
        href={`/recommendations/${rec.rec_id}`}
        className="min-w-0 flex-1 group"
      >
        <div className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-wider font-medium">
          <span className="opacity-80">{meta.label}</span>
          <span className="opacity-50">·</span>
          <Pill tone={statusTone(rec.status)}>{friendlyStatus(rec.status)}</Pill>
          <span className="opacity-60">{formatRelativeTime(rec.created_at)}</span>
        </div>
        <h3 className="text-base font-semibold mt-1 leading-snug group-hover:text-[var(--color-accent)] transition-colors">
          {rec.title}
        </h3>
        <p className="text-sm text-[var(--color-muted)] mt-1.5 line-clamp-2 leading-relaxed">
          {rec.body}
        </p>
      </Link>

      <ArrowRight className="size-4 text-[var(--color-muted)] mt-1 shrink-0" />
    </li>
  );
}

function BulkActionBar({
  selectedCount,
  rec_ids,
  onDone,
  onClear,
}: {
  selectedCount: number;
  rec_ids: string[];
  onDone: () => Promise<void>;
  onClear: () => void;
}) {
  const [approver, setApprover] = useState("");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const [result, setResult] = useState<{
    decided: number;
    skipped: number;
  } | null>(null);

  async function decide(decision: "approve" | "reject") {
    if (!approver.trim()) {
      setErr(new Error("Bitte tragen Sie Ihren Namen ein."));
      return;
    }
    setBusy(true);
    setErr(null);
    setResult(null);
    try {
      const res = await api.bulkDecision({
        rec_ids,
        decision,
        approver: approver.trim(),
        comment: comment.trim() || undefined,
      });
      setResult({ decided: res.decided.length, skipped: res.skipped.length });
      await onDone();
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="sticky top-4 z-10 p-4 bg-aurora">
      <div className="flex flex-wrap items-center gap-3">
        <div className="font-medium text-sm">
          {selectedCount} {selectedCount === 1 ? "Empfehlung" : "Empfehlungen"} ausgewählt
        </div>
        <input
          type="text"
          value={approver}
          onChange={(e) => setApprover(e.target.value)}
          placeholder="Ihr Name (Freigabe-Identität)"
          disabled={busy}
          className="flex-1 min-w-[180px] max-w-xs px-3 py-1.5 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
        />
        <input
          type="text"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Bemerkung (optional, gilt für alle)"
          disabled={busy}
          className="flex-1 min-w-[200px] px-3 py-1.5 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
        />
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => decide("approve")}
            className="px-4 py-1.5 rounded-full bg-[var(--color-success)] text-white text-sm font-medium hover:opacity-90 disabled:opacity-50"
          >
            Freigeben
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => decide("reject")}
            className="px-4 py-1.5 rounded-full bg-[var(--color-danger)] text-white text-sm font-medium hover:opacity-90 disabled:opacity-50"
          >
            Ablehnen
          </button>
          <button
            type="button"
            onClick={onClear}
            disabled={busy}
            className="text-xs text-[var(--color-muted)] hover:text-[var(--color-fg)] px-2"
          >
            Aufheben
          </button>
        </div>
      </div>
      {err ? (
        <div className="mt-2">
          <ErrorMessage error={err} />
        </div>
      ) : null}
      {result ? (
        <div className="mt-2 text-xs text-[var(--color-muted)]">
          {result.decided} entschieden
          {result.skipped > 0
            ? ` · ${result.skipped} übersprungen (bereits entschieden)`
            : ""}
        </div>
      ) : null}
    </Card>
  );
}
