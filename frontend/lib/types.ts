// Types mirror the Pydantic models in backend/src/biq/api/*.py.
// Keep in sync — there's no automatic codegen yet.

export type Recommendation = {
  rec_id: string;
  run_id: string;
  title: string;
  body: string;
  confidence: number | null;
  action_type: string;
  risk_level: "low" | "medium" | "high";
  status: "pending" | "approved" | "rejected" | string;
  created_at: string;
};

export type DecisionResponse = {
  rec_id: string;
  decision: string;
  status: string;
};

export type AgentRun = {
  run_id: string;
  user_id: string | null;
  trigger: string;
  prompt: string | null;
  status: string;
  started_at: string;
  finished_at: string | null;
  cost_usd: number | null;
};

export type AgentStep = {
  step_id: string;
  seq: number;
  agent_name: string;
  action: string;
  input: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  latency_ms: number | null;
};

export type ToolCall = {
  call_id: string;
  tool_name: string;
  params: Record<string, unknown>;
  rows_returned: number;
  error: string | null;
};

export type RunDetail = {
  run: AgentRun;
  steps: AgentStep[];
  tool_calls: ToolCall[];
};

export type KpiList = { views: string[] };

export type KpiQueryResult = {
  rows: Record<string, unknown>[];
  row_count: number;
  note?: string;
  error?: string;
};

/**
 * Mirrors biq.tools.kg.list_recent_insights() — kg.nodes properties are
 * stored in a jsonb column, so `title`, `component`, `severity`, etc. live
 * inside `properties`, not at the top level. The `decision` and `outcome`
 * fields are optional joined sub-objects so the UI can show
 * "Wirkung wird am X gemessen" or the actual measured result.
 */
export type Insight = {
  insight_id: string;
  external_ref: string | null;
  created_at: string;
  properties: {
    title?: string;
    component?: string | null;
    severity?: "low" | "medium" | "high" | null;
    kpi?: string;
    run_id?: string;
    period_start?: string;
    period_end?: string;
    period_prior_start?: string;
    period_prior_end?: string;
    relative_change?: number;
    [k: string]: unknown;
  };
  decision?: {
    decision_id: string;
    decision: "approve" | "reject" | "modify" | string;
    approver: string | null;
    decided_at: string | null;
    outcome_due_at: string | null;
  } | null;
  outcome?: {
    outcome_id: string;
    metric: string | null;
    expected_effect: number | null;
    observed_effect: number | null;
    period_start: string | null;
    period_end: string | null;
    measured_at: string | null;
    notes: string | null;
  } | null;
};

export type HealthStatus = {
  status: string;
  db?: string;
  r_service?: string;
  version?: string;
};

// Mirrors the response of /v1/organizations/api_keys on Anthropic's Admin API.
export type AnthropicApiKey = {
  id: string;
  type: "api_key";
  name: string;
  status: "active" | "inactive" | "archived" | "expired";
  partial_key_hint: string;
  created_at: string;
  expires_at: string | null;
  workspace_id: string | null;
  created_by: { id: string; type: string };
};

export type AnthropicApiKeyList = {
  data: AnthropicApiKey[];
  first_id: string | null;
  last_id: string | null;
  has_more: boolean;
};

// --- External-intel responses (mirrors biq.tools.external) ---

export type NewsItem = {
  title: string | null;
  source: string | null;
  published_at: string | null;
  url: string | null;
  summary: string | null;
};

export type NewsResponse = {
  query: string;
  provider: "newsapi" | "rss";
  results: NewsItem[];
  cache?: "hit" | "miss";
  error?: string;
};

export type WebSearchResult = {
  title: string | null;
  url: string | null;
  content: string | null;
  score: number | null;
  published_date: string | null;
};

export type WebSearchResponse = {
  query: string;
  answer: string | null;
  results: WebSearchResult[];
  cache?: "hit" | "miss";
  error?: string;
};

export type MarketItem = {
  symbol: string;
  name: string;
  last: number;
  change_pct: number | null;
  history: { date: string; close: number }[];
};

export type MarketResponse = {
  period: string;
  items: MarketItem[];
  cache?: "hit" | "miss";
  error?: string;
};

export type TrendsResponse = {
  keywords: string[];
  geo: string;
  timeframe: string;
  timeline: Array<{ date: string; [k: string]: number | string }>;
  related_topics: string[];
  cache?: "hit" | "miss";
  error?: string;
};
