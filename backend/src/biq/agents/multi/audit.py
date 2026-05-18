"""Audit helpers for the multi-agent investigator.

Wraps biq.audit so leads and sub-workers can record themselves into
audit.agent_steps without each node having to plumb a RunContext through
its signature.

Key properties:
- Contextvar-based: run_graph() sets the active RunContext, then every
  Lead and Sub-Worker reaches for it through `audit_lead()` / `audit_sub()`.
- No-op when no context is active — keeps unit tests DB-free.
- Swallows DB errors and logs them: an audit-write failure must NEVER
  bring down a manager-facing investigation. The error surfaces in the
  app log (and in observability) but the user still gets a report.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from biq.agents.multi import budget as ma_budget
from biq.audit import RunContext, finish_step, log_step

log = logging.getLogger(__name__)

_CURRENT_CTX: ContextVar[RunContext | None] = ContextVar("multi_agent_run_ctx", default=None)

# Tracks the currently-active Lead step so Sub-Workers can attach themselves
# without the Lead having to plumb the step_id down. Set by audit_lead's body,
# read by audit_sub when no explicit parent is provided.
_CURRENT_PARENT_STEP_ID: ContextVar[str | None] = ContextVar(
    "multi_agent_parent_step_id", default=None
)


# --- Context lifecycle ---------------------------------------------------


def set_context(ctx: RunContext | None) -> Any:
    """Install `ctx` as the active multi-agent run context. Returns a Token
    that the caller passes back to `reset_context` to restore the prior value.
    """
    return _CURRENT_CTX.set(ctx)


def reset_context(token: Any) -> None:
    _CURRENT_CTX.reset(token)


def current_context() -> RunContext | None:
    return _CURRENT_CTX.get()


def current_run_id() -> str | None:
    ctx = _CURRENT_CTX.get()
    return ctx.run_id if ctx else None


# --- Pricing -------------------------------------------------------------

# Per-1M-token USD prices (input, output). Sources: anthropic.com/pricing.
# Keep this conservative — used for back-of-envelope cost attribution in
# the audit table, NOT for billing.
_MODEL_PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-4-7": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
}


def estimate_cost_usd(
    model: str | None, tokens_in: int | None, tokens_out: int | None
) -> float | None:
    if not model or tokens_in is None or tokens_out is None:
        return None
    rate = _MODEL_PRICES.get(model)
    if rate is None:
        return None
    in_rate, out_rate = rate
    return round(tokens_in * in_rate / 1_000_000 + tokens_out * out_rate / 1_000_000, 6)


def usage_from_anthropic(resp: Any) -> tuple[int | None, int | None]:
    """Extract (input_tokens, output_tokens) from an Anthropic Response, if present.

    Includes cache-read and cache-creation tokens in the input total so cost
    attribution stays honest even when prompt caching is active.
    """
    usage = getattr(resp, "usage", None)
    if usage is None:
        return None, None
    tin = (
        (getattr(usage, "input_tokens", 0) or 0)
        + (getattr(usage, "cache_read_input_tokens", 0) or 0)
        + (getattr(usage, "cache_creation_input_tokens", 0) or 0)
    )
    tout = getattr(usage, "output_tokens", 0) or 0
    return int(tin), int(tout)


# --- Context managers ----------------------------------------------------


@contextmanager
def _audit_step(
    agent_name: str,
    agent_level: str,
    action: str,
    input: dict[str, Any] | None,
    parent_step_id: str | None,
    model: str | None,
) -> Iterator[dict[str, Any]]:
    """Internal: yields a mutable dict the caller writes back into.

    The dict supports:
      out["output"] = {...}         # mirrored to audit.agent_steps.output
      out["tokens_in"] = int        # ditto
      out["tokens_out"] = int
      out["cost_usd"] = float       # auto-computed if model+tokens given
      out["step_id"] -> str | None  # populated when DB write succeeded
    """
    ctx = current_context()
    state: dict[str, Any] = {
        "step_id": None,
        "output": None,
        "tokens_in": None,
        "tokens_out": None,
        "cost_usd": None,
    }
    if ctx is None:
        # No-op path — tests + offline runs hit here. We still expose the
        # parent contextvar so nested audit_sub() calls don't crash when
        # somebody does open one without a run. Budget tracking *does*
        # still apply (it has its own contextvar), so LLM-using sub-workers
        # can be cost-capped even outside of audit.
        try:
            yield state
        finally:
            ma_budget.record_llm_usage(
                agent_name,
                state["tokens_in"],
                state["tokens_out"],
                state["cost_usd"],
            )
        return

    step_id: str | None = None
    try:
        step_id = log_step(
            ctx,
            agent_name=agent_name,
            action=action,
            input=input,
            parent_step_id=parent_step_id,
            agent_level=agent_level,
            model=model,
        )
        state["step_id"] = step_id
    except Exception as e:  # pragma: no cover — audit must never crash the agent
        log.warning("audit log_step failed for %s.%s: %s", agent_name, action, e)
        yield state
        return

    # While the block executes, sub-workers spawned underneath us should
    # see step_id as their default parent. Leads set this; sub steps don't
    # rebind (a sub-worker is always a leaf in our hierarchy).
    parent_token = None
    if agent_level == "lead":
        parent_token = _CURRENT_PARENT_STEP_ID.set(step_id)

    try:
        yield state
    finally:
        if parent_token is not None:
            _CURRENT_PARENT_STEP_ID.reset(parent_token)
        cost = state["cost_usd"]
        if cost is None:
            cost = estimate_cost_usd(model, state["tokens_in"], state["tokens_out"])
        # Always record into the budget — even if the DB write below fails.
        ma_budget.record_llm_usage(agent_name, state["tokens_in"], state["tokens_out"], cost)
        try:
            finish_step(
                step_id,
                output=state["output"],
                tokens_in=state["tokens_in"],
                tokens_out=state["tokens_out"],
                cost_usd=cost,
            )
        except Exception as e:  # pragma: no cover
            log.warning("audit finish_step failed for %s.%s: %s", agent_name, action, e)


def audit_supervisor(
    action: str,
    input: dict[str, Any] | None = None,
):
    """Context manager for a Supervisor step. Yields a mutable telemetry dict."""
    return _audit_step(
        agent_name="supervisor",
        agent_level="supervisor",
        action=action,
        input=input,
        parent_step_id=None,
        model=None,
    )


def audit_lead(
    agent_name: str,
    action: str,
    input: dict[str, Any] | None = None,
    parent_step_id: str | None = None,
    model: str | None = None,
):
    """Context manager for a Lead step."""
    return _audit_step(
        agent_name=agent_name,
        agent_level="lead",
        action=action,
        input=input,
        parent_step_id=parent_step_id,
        model=model,
    )


def audit_sub(
    agent_name: str,
    action: str,
    input: dict[str, Any] | None = None,
    parent_step_id: str | None = None,
    model: str | None = None,
):
    """Context manager for a Sub-Worker step (always nested under a Lead).

    `parent_step_id` defaults to whichever Lead is currently active (via
    the audit_lead context manager) — sub-workers don't need to plumb it.
    """
    if parent_step_id is None:
        parent_step_id = _CURRENT_PARENT_STEP_ID.get()
    return _audit_step(
        agent_name=agent_name,
        agent_level="sub",
        action=action,
        input=input,
        parent_step_id=parent_step_id,
        model=model,
    )
