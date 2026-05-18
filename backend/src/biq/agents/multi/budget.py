"""Per-run token + cost budget for the multi-agent investigator.

The supervisor checks `budget_exceeded()` before every routing decision
and short-circuits to the reporter when either limit is hit. The audit
layer records consumed tokens/cost into the active budget after every
LLM step.

Defaults come from biq.config.settings:
- biq_max_tokens_per_run    (default 100_000)
- biq_max_cost_usd_per_run  (default 2.0)

Each run gets its own budget object — set by run_graph() at start, cleared
when the graph returns. Outside of a run the helpers are no-ops so the
deterministic sub-workers don't have to care.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from biq.config import settings

__all__ = [
    "RunBudget",
    "budget_exceeded",
    "budget_for_settings",
    "current_budget",
    "record_llm_usage",
    "reset_budget",
    "set_budget",
]


@dataclass
class RunBudget:
    """Hard caps + counters for a single multi-agent run.

    `exceeded_reason` is set on the first overrun and never cleared — the
    supervisor uses its presence (not a re-check) as the short-circuit
    signal, which keeps the reason stable for the final report.
    """

    max_tokens: int
    max_cost_usd: float
    used_tokens: int = 0
    used_cost_usd: float = 0.0
    exceeded_reason: str | None = field(default=None)

    def record(
        self,
        agent_name: str,
        tokens_in: int | None,
        tokens_out: int | None,
        cost_usd: float | None,
    ) -> None:
        added_tokens = (tokens_in or 0) + (tokens_out or 0)
        self.used_tokens += added_tokens
        if cost_usd is not None:
            self.used_cost_usd += float(cost_usd)

        if self.exceeded_reason is None:
            if self.used_tokens > self.max_tokens:
                self.exceeded_reason = (
                    f"token budget exceeded after {agent_name}: "
                    f"{self.used_tokens} > {self.max_tokens}"
                )
            elif self.used_cost_usd > self.max_cost_usd:
                self.exceeded_reason = (
                    f"cost budget exceeded after {agent_name}: "
                    f"${self.used_cost_usd:.4f} > ${self.max_cost_usd:.2f}"
                )


def budget_for_settings() -> RunBudget:
    """Construct a RunBudget seeded from the current biq.config.settings."""
    return RunBudget(
        max_tokens=int(settings.biq_max_tokens_per_run),
        max_cost_usd=float(settings.biq_max_cost_usd_per_run),
    )


_CURRENT_BUDGET: ContextVar[RunBudget | None] = ContextVar("multi_agent_run_budget", default=None)


def set_budget(budget: RunBudget | None) -> Any:
    return _CURRENT_BUDGET.set(budget)


def reset_budget(token: Any) -> None:
    _CURRENT_BUDGET.reset(token)


def current_budget() -> RunBudget | None:
    return _CURRENT_BUDGET.get()


def record_llm_usage(
    agent_name: str,
    tokens_in: int | None,
    tokens_out: int | None,
    cost_usd: float | None,
) -> None:
    """No-op when no budget is active (offline runs, unit tests)."""
    budget = _CURRENT_BUDGET.get()
    if budget is None:
        return
    budget.record(agent_name, tokens_in, tokens_out, cost_usd)


def budget_exceeded() -> str | None:
    """Returns the human-readable reason if the active budget is over, else None."""
    budget = _CURRENT_BUDGET.get()
    if budget is None:
        return None
    return budget.exceeded_reason
