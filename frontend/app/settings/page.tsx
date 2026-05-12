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

export default function SettingsPage() {
  const [statusFilter, setStatusFilter] = useState<
    AnthropicApiKey["status"] | "all"
  >("all");

  const swrKey = ["anthropic-keys", statusFilter];
  const { data, error, isLoading } = useSWR(
    swrKey,
    () =>
      api.listAnthropicKeys(
        statusFilter === "all" ? {} : { status: statusFilter },
      ),
    { revalidateOnFocus: false },
  );

  const isDisabled =
    error instanceof ApiError && error.status === 503;

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-[var(--color-muted)] mt-1">
          Anthropic API keys visible to this organisation. Fetched live via
          the Admin API (<span className="mono">/v1/organizations/api_keys</span>).
          The admin key never leaves the backend.
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
                  setStatusFilter(
                    e.target.value as AnthropicApiKey["status"] | "all",
                  )
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
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--color-border)]">
                  {data.data.map((k) => (
                    <tr key={k.id} className="hover:bg-[var(--color-bg)]">
                      <td className="px-4 py-2 align-top">
                        <div className="font-medium">{k.name}</div>
                        <div className="text-xs text-[var(--color-muted)] mono">
                          {k.id}
                        </div>
                      </td>
                      <td className="px-4 py-2 align-top mono text-xs">
                        {k.partial_key_hint}
                      </td>
                      <td className="px-4 py-2 align-top">
                        <Pill tone={STATUS_TONES[k.status]}>{k.status}</Pill>
                      </td>
                      <td className="px-4 py-2 align-top text-xs text-[var(--color-muted)] mono">
                        {k.workspace_id ?? "(default)"}
                      </td>
                      <td className="px-4 py-2 align-top text-xs text-[var(--color-muted)]">
                        {fmtDate(k.created_at)}
                      </td>
                      <td className="px-4 py-2 align-top text-xs text-[var(--color-muted)]">
                        {fmtDate(k.expires_at)}
                      </td>
                    </tr>
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
