"""LLM-driven anomaly investigator.

Uses Claude tool-use to plan and execute a multi-step investigation.
Shares the audit pattern with the heuristic detector in `agents/anomaly.py`
but lets the LLM decide which tool to call when.

Prompt caching:
- System prompt is cached (ephemeral)
- Last tool definition is cached, so the whole tools array is cached up to it
- These two breakpoints amortise across iterations within a run AND across
  separate runs within the 5-minute cache window.

Costs:
- Sonnet 4.6 is the default. Override with --model claude-haiku-4-5-20251001
  for cheaper local testing.
"""

from __future__ import annotations

import json
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
from biq.tools import causal as causal_tools
from biq.tools import context as ctx_tools
from biq.tools import kg as kg_tools
from biq.tools import kpi as kpi_tools

DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOOL_RESULT_CHARS = 6000

SYSTEM_PROMPT = """You are an autonomous Business Intelligence investigator.

GOAL
When the user gives you a business question or anomaly, investigate it
using the available tools, then write a clear management-grade finding.

RULES
- Read KPIs only via the kpi_query tool. The kpi.* views are the governed
  semantic layer; never invent or estimate numbers yourself.
- When you detect a drop or spike, cross-reference releases_in_window
  and campaigns_in_window for the same period to find candidate treatments.
- For an evidence-backed causal claim, call causal_impact_conversion with
  a clear pre/post period and synthetic-control devices. Only then upgrade
  language from "correlates with" to "caused by ~X% (95% CI [...])".
- Cite the data in your reasoning: period, magnitude, segment, sample size,
  p-value when available.
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
) -> dict[str, Any]:
    """Run the investigator loop. Returns final answer + audit metadata."""
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set. Add it to .env to run the LLM investigator.")

    client = Anthropic(api_key=settings.anthropic_api_key)
    tools = _cached_tools()
    system = _cached_system()

    with run_context(trigger="cli", prompt=question) as ctx:
        messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
        recommendation_ids: list[str] = []
        total_in = total_out = total_cache_read = total_cache_write = 0
        last_response = None

        for iteration in range(max_iterations):
            step_id = log_step(
                ctx,
                agent_name="investigator",
                action=f"llm_call_{iteration + 1}",
                input={"messages_so_far": len(messages)},
            )

            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=system,
                tools=tools,
                messages=messages,
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

            assistant_content = [block.model_dump() for block in response.content]
            messages.append({"role": "assistant", "content": assistant_content})

            if response.stop_reason == "end_turn":
                final_text = "\n".join(
                    block.text for block in response.content if block.type == "text"
                )
                return {
                    "run_id": ctx.run_id,
                    "final_answer": final_text,
                    "recommendation_ids": recommendation_ids,
                    "iterations": iteration + 1,
                    "tokens": {
                        "input": total_in,
                        "output": total_out,
                        "cache_read": total_cache_read,
                        "cache_write": total_cache_write,
                    },
                }

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
                continue

            # Other stop reason → bail
            break

        return {
            "run_id": ctx.run_id,
            "error": f"loop ended without end_turn (iterations={max_iterations})",
            "stop_reason": last_response.stop_reason if last_response else None,
            "recommendation_ids": recommendation_ids,
            "tokens": {
                "input": total_in,
                "output": total_out,
                "cache_read": total_cache_read,
                "cache_write": total_cache_write,
            },
        }
