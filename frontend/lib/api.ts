/**
 * Thin client for the FastAPI backend.
 *
 * Reads the API base URL from NEXT_PUBLIC_API_URL (defaults to 127.0.0.1:8000).
 *
 * Auth: when Auth0 SSO is configured (BIQ_AUTH_MODE=bearer_jwt on the
 * backend, AUTH0_* env on the frontend), this module fetches an access
 * token from /auth/access-token (a route the Auth0 SDK middleware exposes)
 * and attaches it as `Authorization: Bearer <jwt>` to every backend call.
 * The token is cached client-side until the SDK refreshes it.
 *
 * Falls back to no-auth when the access-token endpoint returns 401/204,
 * so local dev with BIQ_AUTH_MODE=disabled still works without anyone
 * being logged in.
 */

import type {
  AgentRun,
  AnthropicApiKey,
  AnthropicApiKeyList,
  BriefingResponse,
  CommerceCalendarResponse,
  CorrelationResponse,
  DecisionResponse,
  HealthStatus,
  Insight,
  KpiList,
  KpiQueryResult,
  MarketResponse,
  NewsResponse,
  Recommendation,
  RunDetail,
  ShopifyStatusResponse,
  TrendsResponse,
  WebSearchResponse,
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

// In-memory cache for the Auth0 access token. Cleared after a 401 so a
// stale token can be refreshed by re-fetching from /auth/access-token.
let _cachedAccessToken: string | null = null;

async function fetchAccessToken(): Promise<string | null> {
  if (_cachedAccessToken) return _cachedAccessToken;
  try {
    // The Auth0 v4 middleware exposes /auth/access-token which returns
    // { token: "..." } for the signed-in user, or 401 when there's no
    // session. We never throw on auth errors here — the caller might
    // be running against a backend with auth disabled.
    const res = await fetch("/auth/access-token", { cache: "no-store" });
    if (!res.ok) return null;
    const data = (await res.json()) as { token?: string };
    _cachedAccessToken = data.token ?? null;
    return _cachedAccessToken;
  } catch {
    return null;
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

  // Only attach the Bearer token when running in the browser — server
  // components reach the backend through their own auth path. /healthz
  // and similar public endpoints don't need a token either.
  if (typeof window !== "undefined" && !headers.has("Authorization")) {
    const token = await fetchAccessToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }

  const url = path.startsWith("http") ? path : `${BASE_URL}${path}`;
  const res = await fetch(url, { ...init, headers, cache: "no-store" });

  // On 401: invalidate the cached token and let the next call re-fetch it.
  if (res.status === 401) {
    _cachedAccessToken = null;
  }

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
  bulkDecision: (payload: {
    rec_ids: string[];
    decision: "approve" | "reject";
    approver: string;
    comment?: string;
  }) =>
    request<{
      decided: DecisionResponse[];
      skipped: { rec_id: string; reason: "not_found" | "not_pending" | string }[];
    }>("/api/recommendations/bulk-decision", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
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

  // external intelligence (Markt-Radar)
  externalNews: (params: {
    q?: string;
    max?: number;
    lang?: "de" | "en";
    region?: "default" | "dach";
  } = {}) => {
    const qs = new URLSearchParams();
    if (params.q) qs.set("q", params.q);
    qs.set("max_results", String(params.max ?? 10));
    qs.set("language", params.lang ?? "de");
    if (params.region) qs.set("region", params.region);
    return request<NewsResponse>(`/api/external/news?${qs}`);
  },

  shopifyTopCategories: (params: { limit?: number; window_days?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.limit) qs.set("limit", String(params.limit));
    if (params.window_days) qs.set("window_days", String(params.window_days));
    const suffix = qs.toString() ? `?${qs}` : "";
    return request<{
      window_days: number;
      categories: { product_type: string; revenue: number; units_sold: number; n_orders: number }[];
      horizon: { start: string | null; end: string | null };
    }>(`/api/shopify/top-categories${suffix}`);
  },
  externalSearch: (params: { q: string; max?: number; days?: number; topic?: "general" | "news" }) => {
    const qs = new URLSearchParams({ q: params.q });
    qs.set("max_results", String(params.max ?? 5));
    if (params.days) qs.set("days", String(params.days));
    if (params.topic) qs.set("topic", params.topic);
    return request<WebSearchResponse>(`/api/external/search?${qs}`);
  },
  externalTrends: (params: {
    keywords: string[];
    geo?: string;
    timeframe?: string;
  }) => {
    const qs = new URLSearchParams();
    params.keywords.forEach((k) => qs.append("keywords", k));
    if (params.geo) qs.set("geo", params.geo);
    if (params.timeframe) qs.set("timeframe", params.timeframe);
    return request<TrendsResponse>(`/api/external/trends?${qs}`);
  },
  externalMarket: (params: {
    symbols?: string[];
    period?: "5d" | "1mo" | "3mo" | "6mo" | "1y";
  } = {}) => {
    const qs = new URLSearchParams();
    (params.symbols ?? []).forEach((s) => qs.append("symbols", s));
    if (params.period) qs.set("period", params.period);
    return request<MarketResponse>(`/api/external/market?${qs}`);
  },

  externalShopifyStatus: () =>
    request<ShopifyStatusResponse>("/api/external/shopify-status"),

  externalCommerceCalendar: (
    params: { country?: "CH" | "DE" | "AT"; limit?: number; window_days?: number } = {},
  ) => {
    const qs = new URLSearchParams();
    if (params.country) qs.set("country", params.country);
    if (params.limit) qs.set("limit", String(params.limit));
    if (params.window_days) qs.set("window_days", String(params.window_days));
    const suffix = qs.toString() ? `?${qs}` : "";
    return request<CommerceCalendarResponse>(`/api/external/commerce-calendar${suffix}`);
  },

  externalCorrelateWithShop: (params: {
    internal: string;
    external_kind: "market" | "trends";
    external_key: string;
    days?: number;
  }) => {
    const qs = new URLSearchParams({
      internal: params.internal,
      external_kind: params.external_kind,
      external_key: params.external_key,
    });
    if (params.days) qs.set("days", String(params.days));
    return request<CorrelationResponse>(
      `/api/external/correlate-with-shop?${qs}`,
    );
  },

  // Tagesbriefing
  briefingToday: () => request<BriefingResponse>("/api/briefing/today"),
  briefingRefresh: () =>
    request<BriefingResponse>("/api/briefing/refresh", { method: "POST" }),

  // Manager-visible system settings (audit.system_config)
  getSystemSettings: () =>
    request<{
      briefing_daily_active: boolean;
      data_source: "sim" | "live";
      briefing_model: "haiku" | "sonnet" | "opus";
    }>("/api/settings"),
  updateSystemSettings: (patch: {
    briefing_daily_active?: boolean;
    data_source?: "sim" | "live";
    briefing_model?: "haiku" | "sonnet" | "opus";
  }) =>
    request<{
      briefing_daily_active: boolean;
      data_source: "sim" | "live";
      briefing_model: "haiku" | "sonnet" | "opus";
    }>("/api/settings", {
      method: "PUT",
      body: JSON.stringify(patch),
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
  measureDecisionOutcome: (
    decisionId: string,
    payload: { post_period_days?: number; notes?: string } = {},
  ) =>
    request<{
      status: string;
      outcome_id?: string;
      observed_effect?: number | null;
      expected_effect?: number | null;
      observed_rate?: number | null;
      baseline_rate?: number | null;
      period_start?: string;
      period_end?: string;
      anchored_to_data?: boolean;
      error?: string;
      reason?: string;
    }>(`/api/kg/decisions/${decisionId}/measure-outcome`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
