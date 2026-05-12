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

export type Insight = {
  node_id: string;
  title: string;
  component?: string | null;
  created_at?: string;
  [k: string]: unknown;
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
