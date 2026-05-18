"""Shared state + result schemas for the hierarchical multi-agent investigator.

Framed as AI-in-the-loop (AI²L), not autonomous: the manager is the decision
maker, the agents prepare structured proposals. ReportResult is what the
manager actually sees; everything else is supporting evidence the manager
can drill into.

State layout:
- GlobalState (TypedDict) holds the run-wide shared dict that LangGraph
  threads through nodes.
- Each Lead writes exactly one finalized Pydantic result object (e.g.
  AnalysisResult) into its slot. Subgraph scratch lives outside this file.
- The Supervisor reads `completed`, `plan`, and the result slots to decide
  routing; it never touches a slot another Lead owns.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high"]
RiskLevel = Literal["low", "medium", "high"]


class EvidenceRef(BaseModel):
    """Pointer back to the source row(s) that justify a Finding.

    Kept abstract on purpose: a kpi-query result, an audit step, a
    causal-estimate row, or a knowledge-graph node all reference back
    the same way — `kind` + `ref` (table.row_id / step_id / kg_id).
    """

    kind: Literal["kpi_query", "audit_step", "causal_estimate", "kg_node", "external"]
    ref: str
    note: str | None = None


class CausalEstimate(BaseModel):
    method: str
    treatment: str
    outcome: str
    estimate: float
    ci_lower: float | None = None
    ci_upper: float | None = None
    p_value: float | None = None
    notes: str | None = None


class Finding(BaseModel):
    """One discrete observation. Manager-facing copy goes in `body_de`."""

    title: str
    body_de: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    severity: Severity = "medium"


class DataMiningResult(BaseModel):
    patterns: list[Finding] = Field(default_factory=list)
    segments: list[dict[str, Any]] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    notes: str | None = None


class AnalysisResult(BaseModel):
    findings: list[Finding] = Field(default_factory=list)
    causal_estimates: list[CausalEstimate] = Field(default_factory=list)
    method_notes: str | None = None


class ModelBenchmark(BaseModel):
    name: str
    metric: str
    score: float
    baseline_score: float | None = None


class MLResult(BaseModel):
    models: list[dict[str, Any]] = Field(default_factory=list)
    benchmarks: list[ModelBenchmark] = Field(default_factory=list)
    chosen_model: str | None = None
    notes: str | None = None


class StrategyOption(BaseModel):
    title: str
    body_de: str
    expected_impact_de: str
    risks_de: list[str] = Field(default_factory=list)
    effort: Literal["low", "medium", "high"] = "medium"


class StrategyResult(BaseModel):
    options: list[StrategyOption] = Field(default_factory=list)
    risk_level: RiskLevel = "medium"
    notes: str | None = None


class ReportResult(BaseModel):
    """The single artefact the manager actually reads.

    Plain German, story-card-style — kept short on purpose. Anything
    deeper lives in the other Result objects and is one click away in
    the UI.
    """

    headline_de: str
    summary_de: str
    top_options: list[StrategyOption] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    risk_level: RiskLevel = "medium"


class AgentStep(TypedDict, total=False):
    """In-memory mirror of an audit.agent_steps row.

    Persisted via biq.audit.log_step; kept on the state so a single
    invocation can return its own trace without re-querying.
    """

    step_id: str
    parent_step_id: str | None
    agent_name: str
    agent_level: Literal["supervisor", "lead", "sub"]
    action: str
    input: dict[str, Any]
    output: dict[str, Any]


LeadName = Literal["data_mining", "analyst", "ml", "strategy", "reporter"]


class GlobalState(TypedDict, total=False):
    """LangGraph-threaded state. All fields optional so nodes can patch in."""

    # Input
    question: str
    horizon: tuple[str, str]  # (post_start, post_end) — what we're investigating
    baseline: tuple[str, str]  # (pre_start, pre_end) — comparison window; derived if missing
    target_kpi: str
    target_device: str  # 'mobile' | 'desktop' | 'tablet' | '*' for all

    # Lead results — each Lead writes exactly one of these
    data_mining: DataMiningResult
    analysis: AnalysisResult
    ml: MLResult
    strategy: StrategyResult
    report: ReportResult

    # Supervisor control
    plan: list[LeadName]
    completed: list[LeadName]
    open_questions: list[str]
    iteration: int

    # Audit
    run_id: str
    agent_steps: list[AgentStep]
