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
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-[var(--color-muted)] mt-1">
          Anthropic API keys visible to this organisation. Fetched live via
          the Admin API (
          <span className="mono">/v1/organizations/api_keys</span>). The admin
          key never leaves the backend.
        </p>
      </div>

      {isDisabled ? (
        <Card className="p-6 border-dashed">
          <div className="flex flex-col items-start gap-2">
            <Pill tone="warning">disabled</Pill>
            <p className="text-sm">
              <span className="mono">ANTHROPIC_ADMIN_API_KEY</span> is not set
              on the backend. Issue an admin key in the Claude Console
              (Organization Settings → Admin Keys) and add it to{" "}
              <span className="mono">.env</span>, then restart{" "}
              <span className="mono">make api-serve</span>.
            </p>
          </div>
        </Card>
      ) : null}

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
