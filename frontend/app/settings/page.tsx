"use client";

import { useState } from "react";
import useSWR from "swr";
import { api, ApiError } from "@/lib/api";
import type { AnthropicApiKey } from "@/lib/types";
import {
  Card,
  Empty,
  ErrorMessage,
  Loading,
  Pill,
  SectionTitle,
} from "@/components/ui";
import { PageHeader } from "@/components/page-header";

const STATUS_TONES: Record<
  AnthropicApiKey["status"],
  "success" | "warning" | "neutral" | "danger"
> = {
  active: "success",
  inactive: "warning",
  archived: "neutral",
  expired: "danger",
};

function fmtDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

type StatusFilter = AnthropicApiKey["status"] | "all";

export default function SettingsPage() {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");

  const swrKey = ["anthropic-keys", statusFilter] as const;
  const { data, error, isLoading, mutate } = useSWR(
    swrKey,
    () =>
      api.listAnthropicKeys(
        statusFilter === "all" ? {} : { status: statusFilter },
      ),
    { revalidateOnFocus: false },
  );

  const isDisabled = error instanceof ApiError && error.status === 503;

  return (
    <div className="space-y-6 max-w-6xl">
      <PageHeader
        label="Konfiguration"
        title="Einstellungen"
        description="Hier steuern Sie Kosten-relevante Funktionen und sehen, welche Anthropic-Keys für diese Organisation aktiv sind. Änderungen werden im Audit-Log mit Zeitstempel festgehalten."
      />

      <DailyBriefingToggle />
      <BriefingModelSelector />
      <DataSourceToggle />

      {!isDisabled ? (
        <>
          <SectionTitle
            title="API keys"
            hint={data ? `${data.data.length} shown` : undefined}
            action={
              <select
                value={statusFilter}
                onChange={(e) =>
                  setStatusFilter(e.target.value as StatusFilter)
                }
                className="px-2 py-1 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] text-sm mono"
              >
                <option value="all">all statuses</option>
                <option value="active">active</option>
                <option value="inactive">inactive</option>
                <option value="archived">archived</option>
                <option value="expired">expired</option>
              </select>
            }
          />

          <Card>
            {error ? (
              <div className="p-4">
                <ErrorMessage error={error} />
              </div>
            ) : isLoading ? (
              <div className="p-4">
                <Loading />
              </div>
            ) : !data || data.data.length === 0 ? (
              <Empty>No keys returned for this filter.</Empty>
            ) : (
              <table className="w-full text-sm">
                <thead className="text-xs uppercase tracking-wider text-[var(--color-muted)] border-b border-[var(--color-border)]">
                  <tr>
                    <th className="text-left px-4 py-2">Name</th>
                    <th className="text-left px-4 py-2">Hint</th>
                    <th className="text-left px-4 py-2">Status</th>
                    <th className="text-left px-4 py-2">Workspace</th>
                    <th className="text-left px-4 py-2">Created</th>
                    <th className="text-left px-4 py-2">Expires</th>
                    <th className="text-right px-4 py-2">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--color-border)]">
                  {data.data.map((k) => (
                    <KeyRow
                      key={k.id}
                      apiKey={k}
                      onChanged={() => mutate()}
                    />
                  ))}
                </tbody>
              </table>
            )}
          </Card>

          {data?.has_more ? (
            <p className="text-xs text-[var(--color-muted)]">
              More keys exist. Pagination is not wired in the UI yet — bump
              <span className="mono"> limit</span> in the API call to see more.
            </p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

// --- KeyRow with inline rename + status actions -------------------------

function KeyRow({
  apiKey,
  onChanged,
}: {
  apiKey: AnthropicApiKey;
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(apiKey.name);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);

  const isArchived = apiKey.status === "archived";
  const isExpired = apiKey.status === "expired";
  const canEdit = !isArchived && !isExpired;

  async function save(payload: {
    name?: string;
    status?: "active" | "inactive" | "archived";
  }) {
    setBusy(true);
    setErr(null);
    try {
      await api.updateAnthropicKey(apiKey.id, payload);
      onChanged();
      setEditing(false);
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  }

  async function revoke() {
    const ok = window.confirm(
      `Archive (revoke) "${apiKey.name}"? The key will stop working immediately. There is no un-archive — create a fresh key in the Console if you need a working one.`,
    );
    if (!ok) return;
    await save({ status: "archived" });
  }

  return (
    <tr className="hover:bg-[var(--color-bg)] align-top">
      <td className="px-4 py-2">
        {editing ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const trimmed = name.trim();
              if (trimmed.length === 0 || trimmed === apiKey.name) {
                setEditing(false);
                setName(apiKey.name);
                return;
              }
              save({ name: trimmed });
            }}
            className="flex items-center gap-1"
          >
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={busy}
              className="px-2 py-1 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-sm w-44"
            />
            <button
              type="submit"
              disabled={busy}
              className="text-xs px-2 py-1 rounded-md bg-[var(--color-accent)] text-[var(--color-accent-fg)] disabled:opacity-50"
            >
              save
            </button>
            <button
              type="button"
              onClick={() => {
                setEditing(false);
                setName(apiKey.name);
                setErr(null);
              }}
              disabled={busy}
              className="text-xs px-2 py-1 rounded-md text-[var(--color-muted)] hover:bg-[var(--color-bg)]"
            >
              cancel
            </button>
          </form>
        ) : (
          <>
            <div className="font-medium">{apiKey.name}</div>
            <div className="text-xs text-[var(--color-muted)] mono">
              {apiKey.id}
            </div>
          </>
        )}
        {err ? (
          <div className="mt-1">
            <ErrorMessage error={err} />
          </div>
        ) : null}
      </td>
      <td className="px-4 py-2 mono text-xs">{apiKey.partial_key_hint}</td>
      <td className="px-4 py-2">
        <Pill tone={STATUS_TONES[apiKey.status]}>{apiKey.status}</Pill>
      </td>
      <td className="px-4 py-2 text-xs text-[var(--color-muted)] mono">
        {apiKey.workspace_id ?? "(default)"}
      </td>
      <td className="px-4 py-2 text-xs text-[var(--color-muted)]">
        {fmtDate(apiKey.created_at)}
      </td>
      <td className="px-4 py-2 text-xs text-[var(--color-muted)]">
        {fmtDate(apiKey.expires_at)}
      </td>
      <td className="px-4 py-2 text-right">
        {editing ? null : (
          <div className="flex justify-end gap-1">
            {canEdit ? (
              <button
                type="button"
                onClick={() => setEditing(true)}
                disabled={busy}
                className="text-xs px-2 py-1 rounded-md border border-[var(--color-border)] hover:bg-[var(--color-bg)] disabled:opacity-50"
              >
                Rename
              </button>
            ) : null}
            {apiKey.status === "active" ? (
              <button
                type="button"
                onClick={() => save({ status: "inactive" })}
                disabled={busy}
                className="text-xs px-2 py-1 rounded-md border border-[var(--color-border)] hover:bg-[var(--color-bg)] disabled:opacity-50"
              >
                Deactivate
              </button>
            ) : null}
            {apiKey.status === "inactive" ? (
              <button
                type="button"
                onClick={() => save({ status: "active" })}
                disabled={busy}
                className="text-xs px-2 py-1 rounded-md border border-[var(--color-border)] hover:bg-[var(--color-bg)] disabled:opacity-50"
              >
                Activate
              </button>
            ) : null}
            {!isArchived && !isExpired ? (
              <button
                type="button"
                onClick={revoke}
                disabled={busy}
                className="text-xs px-2 py-1 rounded-md text-white bg-[var(--color-danger)] hover:opacity-90 disabled:opacity-50"
              >
                Revoke
              </button>
            ) : null}
          </div>
        )}
      </td>
    </tr>
  );
}


// ---------------------------------------------------------------------------
// Daily briefing toggle — pause the cost-incurring Sonnet synthesis
// ---------------------------------------------------------------------------

function DailyBriefingToggle() {
  const { data, mutate, isLoading } = useSWR(
    ["system-settings"],
    () => api.getSystemSettings(),
    { revalidateOnFocus: false },
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);

  async function set(active: boolean) {
    setBusy(true);
    setErr(null);
    try {
      const next = await api.updateSystemSettings({
        briefing_daily_active: active,
      });
      mutate(next, { revalidate: false });
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  }

  const active = data?.briefing_daily_active ?? true;

  return (
    <Card className="p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="label-micro">Kostenschalter</div>
          <h2 className="text-lg font-semibold mt-1">Tägliches Briefing</h2>
          <p className="text-sm text-[var(--color-muted)] mt-2 leading-relaxed max-w-2xl">
            Der Tagesbriefing-Agent läuft an jedem Werktag um 07:00 Europe/Zurich
            und kostet etwa <strong>CHF 0.10–0.15</strong> pro Briefing
            (~CHF 2.50/Monat). In ruhigen Phasen können Sie den Cron hier
            pausieren — der n8n-Workflow feuert weiterhin, aber das Backend
            antwortet sofort mit einem Stub und ruft Anthropic nicht auf.
          </p>
          {err ? (
            <div className="mt-3">
              <ErrorMessage error={err} />
            </div>
          ) : null}
        </div>
        <div className="shrink-0">
          {isLoading ? (
            <div className="w-32 h-10 rounded-full bg-[var(--color-surface-sunken)] animate-pulse" />
          ) : (
            <ToggleSwitch
              active={active}
              busy={busy}
              onChange={(v) => set(v)}
            />
          )}
        </div>
      </div>

      {data && !active ? (
        <div className="mt-4 rounded-lg bg-[color-mix(in_oklch,var(--color-warning)_12%,var(--color-surface))] px-3.5 py-2.5 text-xs leading-relaxed">
          <strong>Aktuell pausiert.</strong> Der Markt-Radar zeigt einen
          Hinweis statt eines Briefings. Kein Verbrauch auf Anthropic-Credits.
        </div>
      ) : null}
    </Card>
  );
}

function ToggleSwitch({
  active,
  busy,
  onChange,
}: {
  active: boolean;
  busy: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={active}
      aria-label="Tägliches Briefing aktivieren oder pausieren"
      onClick={() => onChange(!active)}
      disabled={busy}
      className={`relative inline-flex items-center w-32 h-10 rounded-full text-xs font-medium transition-colors disabled:opacity-50 ${
        active
          ? "bg-[var(--color-accent)] text-[var(--color-accent-fg)]"
          : "bg-[var(--color-surface-sunken)] text-[var(--color-muted)]"
      }`}
    >
      <span
        className={`absolute top-1 size-8 rounded-full bg-[var(--color-surface)] shadow-sm transition-transform ${
          active ? "translate-x-[5.25rem]" : "translate-x-1"
        }`}
        aria-hidden
      />
      <span className={`relative z-10 ${active ? "ml-4" : "ml-12"}`}>
        {busy ? "…" : active ? "Aktiv" : "Pausiert"}
      </span>
    </button>
  );
}


// ---------------------------------------------------------------------------
// Briefing model selector — Haiku (cheap) ↔ Sonnet (default) ↔ Opus (premium)
// ---------------------------------------------------------------------------

type BriefingModelTier = "haiku" | "sonnet" | "opus";

const BRIEFING_MODELS: {
  value: BriefingModelTier;
  label: string;
  cost: string;
  note: string;
}[] = [
  {
    value: "haiku",
    label: "Haiku",
    cost: "~CHF 0.01 / Briefing",
    note: "Günstig, kürzere Zusammenfassungen — ideal für ruhige Phasen.",
  },
  {
    value: "sonnet",
    label: "Sonnet",
    cost: "~CHF 0.10–0.15 / Briefing",
    note: "Qualität-Kosten-Balance — der Standard.",
  },
  {
    value: "opus",
    label: "Opus",
    cost: "~CHF 0.25–0.40 / Briefing",
    note: "Tiefere Synthese und mehr Nuancen — für entscheidende Tage.",
  },
];

function BriefingModelSelector() {
  const { data, mutate, isLoading } = useSWR(
    ["system-settings"],
    () => api.getSystemSettings(),
    { revalidateOnFocus: false },
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);

  async function set(next: BriefingModelTier) {
    setBusy(true);
    setErr(null);
    try {
      const updated = await api.updateSystemSettings({ briefing_model: next });
      mutate(updated, { revalidate: false });
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  }

  const value: BriefingModelTier = data?.briefing_model ?? "sonnet";
  const current = BRIEFING_MODELS.find((m) => m.value === value);

  return (
    <Card className="p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="label-micro">Modell-Stufe</div>
          <h2 className="text-lg font-semibold mt-1">Briefing-Modell</h2>
          <p className="text-sm text-[var(--color-muted)] mt-2 leading-relaxed max-w-2xl">
            Wechseln Sie das Anthropic-Modell, das den Tagesbriefing-Agent
            antreibt. Haiku ist rund <strong>10× günstiger</strong> als Sonnet
            bei etwas kürzeren Synthesen, Opus liefert die tiefste Analyse für
            entscheidende Tage. Änderungen greifen beim nächsten Briefing.
          </p>
          {err ? (
            <div className="mt-3">
              <ErrorMessage error={err} />
            </div>
          ) : null}
        </div>
        <div className="shrink-0">
          {isLoading ? (
            <div className="w-60 h-10 rounded-full bg-[var(--color-surface-sunken)] animate-pulse" />
          ) : (
            <div
              role="group"
              aria-label="Briefing-Modell wählen"
              className="inline-flex rounded-full border border-[var(--color-border)] bg-[var(--color-bg)] p-1"
            >
              {BRIEFING_MODELS.map((m) => {
                const active = m.value === value;
                return (
                  <button
                    key={m.value}
                    type="button"
                    aria-pressed={active}
                    disabled={busy}
                    onClick={() => !active && set(m.value)}
                    className={`px-4 py-1.5 rounded-full text-xs font-medium transition-colors disabled:opacity-50 ${
                      active
                        ? "bg-[var(--color-accent)] text-[var(--color-accent-fg)]"
                        : "text-[var(--color-muted)] hover:text-[var(--color-fg)]"
                    }`}
                  >
                    {busy && active ? "…" : m.label}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {data && current ? (
        <div className="mt-4 rounded-lg bg-[var(--color-surface-sunken)] px-3.5 py-2.5 text-xs leading-relaxed flex items-center justify-between gap-3">
          <span>{current.note}</span>
          <Pill tone="neutral">{current.cost}</Pill>
        </div>
      ) : null}
    </Card>
  );
}


// ---------------------------------------------------------------------------
// Sim ↔ Live data-source toggle — flip the dashboard between the simulated
// demo store and the real Shopify dev-store sync
// ---------------------------------------------------------------------------

function DataSourceToggle() {
  const { data, mutate, isLoading } = useSWR(
    ["system-settings"],
    () => api.getSystemSettings(),
    { revalidateOnFocus: false },
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);

  async function set(next: "sim" | "live") {
    setBusy(true);
    setErr(null);
    try {
      const updated = await api.updateSystemSettings({ data_source: next });
      mutate(updated, { revalidate: false });
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  }

  const value: "sim" | "live" = data?.data_source ?? "sim";

  return (
    <Card className="p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="label-micro">Datenquelle</div>
          <h2 className="text-lg font-semibold mt-1">Dashboard-Daten</h2>
          <p className="text-sm text-[var(--color-muted)] mt-2 leading-relaxed max-w-2xl">
            <strong>Sim</strong>: simulierter Demo-Shop mit 5'000 Bestellungen
            inkl. einer eingepflanzten Mobile-Anomalie — ideal für
            wiederholbare Demos.{" "}
            <strong>Live</strong>: echter Shopify-Dev-Store (
            <span className="mono">causal-bi-demo.myshopify.com</span>) mit
            den per ETL synchronisierten Bestellungen. Beide Datensätze
            koexistieren in der DB — der Wechsel ist nicht-destruktiv.
          </p>
          {err ? (
            <div className="mt-3">
              <ErrorMessage error={err} />
            </div>
          ) : null}
        </div>
        <div className="shrink-0">
          {isLoading ? (
            <div className="w-40 h-10 rounded-full bg-[var(--color-surface-sunken)] animate-pulse" />
          ) : (
            <Segmented
              value={value}
              busy={busy}
              options={[
                { value: "sim", label: "Demo" },
                { value: "live", label: "Live" },
              ]}
              onChange={(v) => set(v)}
            />
          )}
        </div>
      </div>
    </Card>
  );
}

function Segmented({
  value,
  options,
  busy,
  onChange,
}: {
  value: "sim" | "live";
  options: { value: "sim" | "live"; label: string }[];
  busy: boolean;
  onChange: (next: "sim" | "live") => void;
}) {
  return (
    <div
      role="group"
      aria-label="Datenquelle wählen"
      className="inline-flex rounded-full border border-[var(--color-border)] bg-[var(--color-bg)] p-1"
    >
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={active}
            disabled={busy}
            onClick={() => !active && onChange(o.value)}
            className={`px-4 py-1.5 rounded-full text-xs font-medium transition-colors disabled:opacity-50 ${
              active
                ? "bg-[var(--color-accent)] text-[var(--color-accent-fg)]"
                : "text-[var(--color-muted)] hover:text-[var(--color-fg)]"
            }`}
          >
            {busy && active ? "…" : o.label}
          </button>
        );
      })}
    </div>
  );
}
