/**
 * Thin client for the FastAPI backend.
 *
 * Reads the API base URL from NEXT_PUBLIC_API_URL (defaults to 127.0.0.1:8000)
 * and the API key from localStorage (set by the auth gate). Every /api/*
 * route is gated server-side when BIQ_API_KEY is configured.
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

const API_KEY_STORAGE = "biq.api_key";

export function getApiKey(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(API_KEY_STORAGE);
}

export function setApiKey(key: string): void {
  window.localStorage.setItem(API_KEY_STORAGE, key);
}

export function clearApiKey(): void {
  window.localStorage.removeItem(API_KEY_STORAGE);
}

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
  const key = getApiKey();
  if (key) headers.set("X-API-Key", key);

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
  ) =>
    request<Recommendation[]>(
      `/api/recommendations?status=${status}&limit=${limit}`,
    ),
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
  listRuns: (limit = 50) => request<AgentRun[]>(`/api/runs?limit=${limit}`),
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
  listInsights: (limit = 50) =>
    request<Insight[]>(`/api/kg/insights?limit=${limit}`),
};
