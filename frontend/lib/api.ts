/**
 * Thin client for the FastAPI backend.
 *
 * Reads the API base URL from NEXT_PUBLIC_API_URL (defaults to 127.0.0.1:8000).
 *
 * Auth: the dashboard is intended to be deployed behind a reverse proxy /
 * SSO that handles user authentication. The FastAPI backend's X-API-Key
 * (BIQ_API_KEY) protects machine-to-machine integrations (n8n, scripts);
 * it is intentionally NOT shipped to the browser. For development the
 * backend runs open (BIQ_API_KEY unset) so the dashboard reaches it
 * without credentials.
 */

import type {
  AgentRun,
  AnthropicApiKey,
  AnthropicApiKeyList,
  DecisionResponse,
  HealthStatus,
  Insight,
  KpiList,
  KpiQueryResult,
  Recommendation,
  RunDetail,
} from "./types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown, message?: string) {
    super(message ?? `API error ${status}`);
    this.status = status;
    this.body = body;
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }

  const url = path.startsWith("http") ? path : `${BASE_URL}${path}`;
  const res = await fetch(url, { ...init, headers, cache: "no-store" });

  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      body = await res.text();
    }
    throw new ApiError(res.status, body);
  }

  // Allow void responses (e.g. healthchecks that return empty).
  const contentType = res.headers.get("Content-Type") ?? "";
  if (!contentType.includes("application/json")) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  // health (public — never gated, no key needed)
  health: () => request<HealthStatus>("/healthz"),
  readiness: () => request<HealthStatus>("/readyz"),

  // kpis
  listKpis: () => request<KpiList>("/api/kpis"),
  queryKpi: (
    view: string,
    params: { start: string; end: string; group_by?: string[] },
  ) => {
    const qs = new URLSearchParams({ start: params.start, end: params.end });
    (params.group_by ?? []).forEach((g) => qs.append("group_by", g));
    return request<KpiQueryResult>(`/api/kpis/${view}?${qs}`);
  },

  // recommendations
  listRecommendations: (
    status: "pending" | "approved" | "rejected" | "all" = "pending",
    limit = 50,
    excludeTriggers: string[] = [],
  ) => {
    const qs = new URLSearchParams({ status, limit: String(limit) });
    for (const t of excludeTriggers) qs.append("exclude_triggers", t);
    return request<Recommendation[]>(`/api/recommendations?${qs}`);
  },
  getRecommendation: (rec_id: string) =>
    request<Recommendation>(`/api/recommendations/${rec_id}`),
  decideRecommendation: (
    rec_id: string,
    payload: {
      decision: "approve" | "reject" | "modify";
      approver: string;
      comment?: string;
    },
  ) =>
    request<DecisionResponse>(`/api/recommendations/${rec_id}/decision`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // runs
  listRuns: (limit = 50, excludeTriggers: string[] = []) => {
    const qs = new URLSearchParams({ limit: String(limit) });
    for (const t of excludeTriggers) qs.append("exclude_triggers", t);
    return request<AgentRun[]>(`/api/runs?${qs}`);
  },
  getRun: (run_id: string) => request<RunDetail>(`/api/runs/${run_id}`),

  // admin (Anthropic Admin API, gated server-side on ANTHROPIC_ADMIN_API_KEY)
  listAnthropicKeys: (
    params: {
      status?: "active" | "inactive" | "archived" | "expired";
      limit?: number;
      after_id?: string;
    } = {},
  ) => {
    const qs = new URLSearchParams();
    if (params.status) qs.set("status", params.status);
    if (params.limit) qs.set("limit", String(params.limit));
    if (params.after_id) qs.set("after_id", params.after_id);
    const suffix = qs.toString() ? `?${qs}` : "";
    return request<AnthropicApiKeyList>(`/api/admin/anthropic-keys${suffix}`);
  },
  getAnthropicKey: (id: string) =>
    request<AnthropicApiKey>(`/api/admin/anthropic-keys/${id}`),
  updateAnthropicKey: (
    id: string,
    payload: {
      name?: string;
      status?: "active" | "inactive" | "archived";
    },
  ) =>
    request<AnthropicApiKey>(`/api/admin/anthropic-keys/${id}`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // investigations
  startLlmInvestigation: (payload: {
    question: string;
    model?: string;
    max_iterations?: number;
    max_input_tokens?: number;
    max_output_tokens?: number;
  }) =>
    request<{ run_id: string; status: string; poll_url: string }>(
      "/api/investigations/llm",
      { method: "POST", body: JSON.stringify(payload) },
    ),

  // kg
  listInsights: (limit = 50, excludeTriggers: string[] = []) => {
    const qs = new URLSearchParams({ limit: String(limit) });
    for (const t of excludeTriggers) qs.append("exclude_triggers", t);
    return request<Insight[]>(`/api/kg/insights?${qs}`);
  },
};
