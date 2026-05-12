"""LLM-driven anomaly investigator.

Uses Claude tool-use to plan and execute a multi-step investigation.
Shares the audit pattern with the heuristic detector in `agents/anomaly.py`
but lets the LLM decide which tool to call when.

Process — plan-then-execute:
- Extended thinking is enabled on every turn (default 4000 tokens). The
  system prompt mandates a short plan before any tool call; that plan is
  surfaced via the thinking blocks and persisted to the audit log.
- A token budget halts the loop cleanly (with an audit entry) before it
  can run away — defaults are tuned for Sonnet 4.6.

Prompt caching:
- System prompt is cached (ephemeral)
- Last tool definition is cached, so the whole tools array is cached up to it
- These two breakpoints amortise across iterations within a run AND across
  separate runs within the 5-minute cache window.

Costs (Sonnet 4.6 @ Jan-2026 list prices, after the standard cache discount):
- ~CHF 0.10-0.20 per typical investigation
- Defaults below cap a single run at roughly CHF 1 worst-case
- Override with --model claude-haiku-4-5-20251001 for cheaper local testing.
"""

from __future__ import annotations

import json
from contextlib import nullcontext
from typing import Any

from anthropic import Anthropic

from biq.audit import (
    finish_step,
    log_recommendation,
    log_step,
    log_tool_call,
    run_context,
)
from biq.config import settings
from biq.observability import init_langfuse
from biq.tools import causal as causal_tools
from biq.tools import context as ctx_tools
from biq.tools import kg as kg_tools
from biq.tools import kpi as kpi_tools

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOOL_RESULT_CHARS = 6000

# Extended thinking: at least 1024, less than MAX_TOKENS. 4000 is enough for
# a 3-5 bullet plan + reflection between tool calls.
DEFAULT_THINKING_BUDGET = 4000
MAX_TOKENS = 8192  # thinking + visible output combined

# Hard caps on a single investigation. Cumulative across all iterations.
# Sized so that the worst case (max_iterations x full tool results) still
# fits without surprise blow-up. Override via investigate(...) kwargs.
DEFAULT_MAX_INPUT_TOKENS = 200_000
DEFAULT_MAX_OUTPUT_TOKENS = 20_000

SYSTEM_PROMPT = """You are an autonomous Business Intelligence investigator.

GOAL
When the user gives you a business question or anomaly, investigate it
using the available tools, then write a clear management-grade finding.

PROCESS — plan, then execute
Before calling any tool, draft a 3-5 bullet plan in your reasoning:
  - which KPI / dimension to probe first
  - what would distinguish a correlation from a causal effect
  - which device or segment is the likely target for causal_impact_conversion
  - one fallback if the first hypothesis doesn't hold
Then execute the plan with tool calls. Revise the plan as evidence arrives
— don't rigidly stick to a plan that the data contradicts.

RULES
- Read KPIs only via the kpi_query tool. The kpi.* views are the governed
  semantic layer; never invent or estimate numbers yourself.
- When you detect a drop or spike, cross-reference releases_in_window
  and campaigns_in_window for the same period to find candidate treatments.
- If the affected segment looks small (low daily sessions), call power_test
  with the baseline rate, the expected post-treatment rate, and the per-group
  sample size BEFORE causal_impact_conversion. If power < 0.8, say so and
  treat any null result as ambiguous, not as evidence of no effect.
- For an evidence-backed causal claim, call causal_impact_conversion with
  a clear pre/post period and synthetic-control devices. Only then upgrade
  language from "correlates with" to "caused by ~X% (95% CI [...])".
- When the causal estimate is significant, call evalue with the relative
  effect (and lower CI bound) to quantify how robust the claim is to
  unmeasured confounders. Mention the E-value in record_finding so the
  reviewer sees the sensitivity, not just the point estimate.
- Cite the data in your reasoning: period, magnitude, segment, sample size,
  p-value, and E-value when available.
- Call record_finding once per distinct, evidence-backed conclusion.
  Set risk_level=high only when both magnitude and sample size warrant it.
- Be concise. Managers read the title and first sentence."""

TOOLS: list[dict[str, Any]] = [
    {
        "name": "kpi_query",
        "description": (
            "Read aggregated KPI data from a governed view. Returns up to 200 rows. "
            "Use group_by to slice by extra dimensions (e.g. ['device','channel'])."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "view": {
                    "type": "string",
                    "enum": sorted(kpi_tools.ALLOWED_VIEWS),
                    "description": "Name of the kpi.* view to query.",
                },
                "start": {"type": "string", "description": "ISO date (inclusive)."},
                "end": {"type": "string", "description": "ISO date (exclusive)."},
                "group_by": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Extra dimensions to aggregate by.",
                },
            },
            "required": ["view", "start", "end"],
        },
    },
    {
        "name": "releases_in_window",
        "description": (
            "List software releases active during the window. "
            "Candidate treatments for causal investigation of KPI moves."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start": {"type": "string"},
                "end": {"type": "string"},
            },
            "required": ["start", "end"],
        },
    },
    {
        "name": "campaigns_in_window",
        "description": "List marketing campaigns active during the window.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start": {"type": "string"},
                "end": {"type": "string"},
            },
            "required": ["start", "end"],
        },
    },
    {
        "name": "kg_lookup_past_decisions",
        "description": (
            "Look up past insights, decisions, and outcomes for a component. "
            "Call this FIRST when investigating a recurring issue — past "
            "decisions and their measured outcomes inform what to recommend now."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "component": {
                    "type": "string",
                    "description": "e.g. 'mobile_checkout' or 'device=mobile'",
                },
                "days_back": {"type": "integer", "default": 180, "minimum": 1, "maximum": 730},
            },
            "required": ["component"],
        },
    },
    {
        "name": "causal_impact_conversion",
        "description": (
            "Estimate the causal effect of a treatment on a device's conversion rate "
            "using CausalImpact (Bayesian structural time series) with optional "
            "synthetic controls from other devices. Use after you have located a "
            "candidate treatment via releases_in_window or campaigns_in_window. "
            "Returns relative effect with 95% CI and p-value."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target_device": {"type": "string", "enum": ["mobile", "desktop", "tablet"]},
                "pre_start": {
                    "type": "string",
                    "description": "ISO date, pre-period start (inclusive).",
                },
                "pre_end": {
                    "type": "string",
                    "description": "ISO date, pre-period end (inclusive).",
                },
                "post_start": {
                    "type": "string",
                    "description": "ISO date, post-period start (inclusive).",
                },
                "post_end": {
                    "type": "string",
                    "description": "ISO date, post-period end (inclusive).",
                },
                "controls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Other devices to use as synthetic controls.",
                },
            },
            "required": ["target_device", "pre_start", "pre_end", "post_start", "post_end"],
        },
    },
    {
        "name": "evalue",
        "description": (
            "Sensitivity analysis (VanderWeele 2017): minimum strength an "
            "unmeasured confounder would need to fully explain the observed "
            "effect away. Call AFTER causal_impact_conversion when the effect "
            "is significant — higher e_value = more robust causal claim. "
            "Quote it in the finding alongside the p-value."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "rel_effect": {
                    "type": "number",
                    "description": "Fractional change, e.g. -0.384 for -38.4%.",
                },
                "rel_effect_lower": {
                    "type": "number",
                    "description": "Optional signed lower 95% CI bound for a CI-edge E-value.",
                },
            },
            "required": ["rel_effect"],
        },
    },
    {
        "name": "power_test",
        "description": (
            "Two-proportion power analysis. Pass exactly three of "
            "{p1, p2, n, power}; the missing one is solved. Use BEFORE "
            "causal_impact_conversion when sample is small: power < 0.8 "
            "means an insignificant result is ambiguous, not negative."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "p1": {"type": "number", "description": "Baseline proportion (0..1)."},
                "p2": {"type": "number", "description": "Alternative proportion (0..1)."},
                "n": {"type": "integer", "description": "Sample size per group."},
                "power": {"type": "number", "description": "Desired power (0..1)."},
                "sig_level": {
                    "type": "number",
                    "default": 0.05,
                    "description": "Two-sided alpha, default 0.05.",
                },
            },
        },
    },
    {
        "name": "record_finding",
        "description": (
            "Persist a finding as a recommendation in the audit log. "
            "Call once per distinct, evidence-backed conclusion."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "body": {
                    "type": "string",
                    "description": "Management-grade explanation, 2-5 sentences.",
                },
                "confidence": {"type": "number", "description": "0..1"},
                "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
            },
            "required": ["title", "body", "confidence", "risk_level"],
        },
    },
]


def _dispatch(name: str, params: dict[str, Any], run_id: str) -> dict[str, Any]:
    if name == "kpi_query":
        return kpi_tools.kpi_query(**params)
    if name == "releases_in_window":
        return ctx_tools.releases_in_window(**params)
    if name == "campaigns_in_window":
        return ctx_tools.campaigns_in_window(**params)
    if name == "causal_impact_conversion":
        return causal_tools.causal_impact_conversion(**params)
    if name == "evalue":
        return causal_tools.evalue(**params)
    if name == "power_test":
        return causal_tools.power_test(**params)
    if name == "kg_lookup_past_decisions":
        return kg_tools.lookup_past_decisions(**params)
    if name == "record_finding":
        rec_id = log_recommendation(
            run_id=run_id,
            title=params["title"],
            body=params["body"],
            confidence=float(params["confidence"]),
            action_type="read_only",
            risk_level=params["risk_level"],
        )
        return {"recommendation_id": rec_id, "status": "recorded"}
    return {"error": f"unknown tool: {name}"}


def _cached_tools() -> list[dict[str, Any]]:
    """Mark last tool with cache_control so the whole tools array is cached."""
    out: list[dict[str, Any]] = []
    for i, t in enumerate(TOOLS):
        if i == len(TOOLS) - 1:
            out.append({**t, "cache_control": {"type": "ephemeral"}})
        else:
            out.append(t)
    return out


def _cached_system() -> list[dict[str, Any]]:
    return [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }
    ]


def investigate(
    question: str,
    model: str = DEFAULT_MODEL,
    max_iterations: int = 10,
    max_input_tokens: int = DEFAULT_MAX_INPUT_TOKENS,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    thinking_budget: int = DEFAULT_THINKING_BUDGET,
) -> dict[str, Any]:
    """Run the investigator loop. Returns final answer + audit metadata.

    Halts cleanly when any of these caps trip:
      - max_iterations: tool-use loop budget
      - max_input_tokens: cumulative input tokens (incl. cache hits)
      - max_output_tokens: cumulative output tokens (visible + thinking)
    """
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set. Add it to .env to run the LLM investigator.")

    client = Anthropic(api_key=settings.anthropic_api_key)
    tools = _cached_tools()
    system = _cached_system()
    lf = init_langfuse()

    with run_context(trigger="cli", prompt=question) as ctx:
        # Parent agent-trace in Langfuse — per-turn generation spans nest
        # under it. nullcontext() makes this a no-op when LF env vars
        # aren't set, so the wrapping costs nothing in dev/CI.
        agent_cm = (
            lf.start_as_current_observation(
                name="investigator",
                as_type="agent",
                input={"question": question, "model": model},
                metadata={"audit_run_id": ctx.run_id},
            )
            if lf is not None
            else nullcontext()
        )

        with agent_cm:
            return _run_loop(
                client=client,
                ctx=ctx,
                question=question,
                model=model,
                tools=tools,
                system=system,
                max_iterations=max_iterations,
                max_input_tokens=max_input_tokens,
                max_output_tokens=max_output_tokens,
                thinking_budget=thinking_budget,
                lf=lf,
            )


def _run_loop(
    *,
    client: Anthropic,
    ctx: Any,
    question: str,
    model: str,
    tools: list[dict[str, Any]],
    system: list[dict[str, Any]],
    max_iterations: int,
    max_input_tokens: int,
    max_output_tokens: int,
    thinking_budget: int,
    lf: Any,
) -> dict[str, Any]:
    """Inner loop. Extracted so the Langfuse `with agent_cm` block stays flat."""
    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    recommendation_ids: list[str] = []
    total_in = total_out = total_cache_read = total_cache_write = 0
    plan_text: str | None = None
    last_response = None

    for iteration in range(max_iterations):
        step_id = log_step(
            ctx,
            agent_name="investigator",
            action=f"llm_call_{iteration + 1}",
            input={"messages_so_far": len(messages)},
        )

        gen_cm = (
            lf.start_as_current_observation(
                name=f"turn_{iteration + 1}",
                as_type="generation",
                model=model,
                input={"messages_so_far": len(messages)},
                model_parameters={
                    "max_tokens": MAX_TOKENS,
                    "thinking_budget": thinking_budget,
                },
            )
            if lf is not None
            else nullcontext()
        )

        with gen_cm as gen_span:
            response = client.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                system=system,
                tools=tools,
                messages=messages,
                thinking={"type": "enabled", "budget_tokens": thinking_budget},
            )
            if gen_span is not None:
                gen_span.update(
                    usage_details={
                        "input": response.usage.input_tokens,
                        "output": response.usage.output_tokens,
                        "cache_read_input_tokens": getattr(
                            response.usage, "cache_read_input_tokens", 0
                        )
                        or 0,
                        "cache_creation_input_tokens": getattr(
                            response.usage, "cache_creation_input_tokens", 0
                        )
                        or 0,
                    },
                    output={"stop_reason": response.stop_reason},
                )

        last_response = response
        usage = response.usage
        total_in += usage.input_tokens
        total_out += usage.output_tokens
        total_cache_read += getattr(usage, "cache_read_input_tokens", 0) or 0
        total_cache_write += getattr(usage, "cache_creation_input_tokens", 0) or 0

        finish_step(
            step_id,
            output={
                "stop_reason": response.stop_reason,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0),
                "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0),
            },
        )

        # Plan extraction on the first turn — system prompt instructs the
        # model to draft 3-5 bullets in its thinking before any tool call.
        if iteration == 0:
            plan_text = (
                "\n".join(
                    getattr(b, "thinking", "") for b in response.content if b.type == "thinking"
                ).strip()
                or None
            )
            if plan_text:
                plan_step = log_step(
                    ctx,
                    agent_name="investigator",
                    action="plan",
                    input={"question": question},
                )
                finish_step(plan_step, output={"plan": plan_text[:4000]})

        assistant_content = [block.model_dump() for block in response.content]
        messages.append({"role": "assistant", "content": assistant_content})

        if response.stop_reason == "end_turn":
            final_text = "\n".join(block.text for block in response.content if block.type == "text")
            return _result(
                ctx.run_id,
                final_answer=final_text,
                recommendation_ids=recommendation_ids,
                iterations=iteration + 1,
                plan=plan_text,
                tokens=(total_in, total_out, total_cache_read, total_cache_write),
            )

        if response.stop_reason == "tool_use":
            tool_results: list[dict[str, Any]] = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_input = dict(block.input)
                tool_step_id = log_step(
                    ctx,
                    agent_name="investigator",
                    action=f"tool::{block.name}",
                    input={"tool": block.name, "input": tool_input},
                )

                error: str | None = None
                try:
                    result = _dispatch(block.name, tool_input, ctx.run_id)
                except Exception as e:
                    result = {"error": str(e)}
                    error = str(e)

                if (
                    block.name == "record_finding"
                    and isinstance(result, dict)
                    and "recommendation_id" in result
                ):
                    recommendation_ids.append(result["recommendation_id"])

                log_tool_call(
                    tool_step_id,
                    block.name,
                    params=tool_input,
                    result_summary=(
                        {"keys": list(result.keys())} if isinstance(result, dict) else None
                    ),
                    rows=int(result.get("row_count", 0)) if isinstance(result, dict) else 0,
                    error=error,
                )
                finish_step(tool_step_id, output={"summary": str(result)[:500]})

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str)[:MAX_TOOL_RESULT_CHARS],
                    }
                )

            messages.append({"role": "user", "content": tool_results})

            # Budget check after a full round-trip (LLM call + tools).
            if total_in + total_cache_read >= max_input_tokens:
                budget_step = log_step(
                    ctx,
                    agent_name="investigator",
                    action="budget_exceeded",
                    input={"axis": "input", "limit": max_input_tokens},
                )
                finish_step(
                    budget_step,
                    output={"consumed": total_in + total_cache_read},
                )
                return _result(
                    ctx.run_id,
                    error=f"input token budget exceeded ({max_input_tokens})",
                    recommendation_ids=recommendation_ids,
                    iterations=iteration + 1,
                    plan=plan_text,
                    tokens=(total_in, total_out, total_cache_read, total_cache_write),
                )
            if total_out >= max_output_tokens:
                budget_step = log_step(
                    ctx,
                    agent_name="investigator",
                    action="budget_exceeded",
                    input={"axis": "output", "limit": max_output_tokens},
                )
                finish_step(budget_step, output={"consumed": total_out})
                return _result(
                    ctx.run_id,
                    error=f"output token budget exceeded ({max_output_tokens})",
                    recommendation_ids=recommendation_ids,
                    iterations=iteration + 1,
                    plan=plan_text,
                    tokens=(total_in, total_out, total_cache_read, total_cache_write),
                )

            continue

        # Other stop reason — bail out cleanly.
        break

    return _result(
        ctx.run_id,
        error=f"loop ended without end_turn (iterations={max_iterations})",
        stop_reason=last_response.stop_reason if last_response else None,
        recommendation_ids=recommendation_ids,
        iterations=max_iterations,
        plan=plan_text,
        tokens=(total_in, total_out, total_cache_read, total_cache_write),
    )


def _result(
    run_id: str,
    *,
    final_answer: str | None = None,
    error: str | None = None,
    stop_reason: str | None = None,
    recommendation_ids: list[str],
    iterations: int,
    plan: str | None,
    tokens: tuple[int, int, int, int],
) -> dict[str, Any]:
    """Uniform return envelope for both success and budget-stop paths."""
    out: dict[str, Any] = {
        "run_id": run_id,
        "recommendation_ids": recommendation_ids,
        "iterations": iterations,
        "tokens": {
            "input": tokens[0],
            "output": tokens[1],
            "cache_read": tokens[2],
            "cache_write": tokens[3],
        },
    }
    if plan is not None:
        out["plan"] = plan
    if final_answer is not None:
        out["final_answer"] = final_answer
    if error is not None:
        out["error"] = error
    if stop_reason is not None:
        out["stop_reason"] = stop_reason
    return out
