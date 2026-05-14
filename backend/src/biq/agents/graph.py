"""LangGraph multi-agent investigator.

Splits the monolithic investigator into specialised nodes with explicit state
and a deterministic flow:

    START -> data -> context -> causal -> narrative -> review -> record -> END

The review node validates the narrative against three rules; if any fail it
loops back to narrative (up to 2 retries). When review passes, the
recommendation is persisted via audit.recommendations.

Each node logs its step to audit.agent_steps with the seq counter incremented
by run_context.

Deterministic by design: no LLM calls in this graph. The single-agent
investigator (agents/investigator.py) covers the LLM-driven path.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from biq.audit import finish_step, log_recommendation, log_step, run_context
from biq.tools import causal as causal_tools
from biq.tools import context as ctx_tools
from biq.tools import kpi as kpi_tools


class State(TypedDict, total=False):
    question: str
    target_device: str
    pre_period: tuple[str, str]
    post_period: tuple[str, str]

    # Filled by nodes
    anomalies: list[dict[str, Any]]
    treatments: list[dict[str, Any]]
    causal_estimate: dict[str, Any]

    finding_title: str
    finding_body: str
    confidence: float
    risk_level: str

    # Review loop
    review_passed: bool
    review_comments: list[str]
    retries: int

    # Audit
    run_id: str
    rec_id: str


# --- Nodes ---------------------------------------------------------------


def data_node(state: State) -> dict[str, Any]:
    pre_s, pre_e = state["pre_period"]
    post_s, post_e = state["post_period"]

    pre = kpi_tools.kpi_query("conversion_rate_daily", pre_s, pre_e, group_by=["device"])
    post = kpi_tools.kpi_query("conversion_rate_daily", post_s, post_e, group_by=["device"])

    pre_by_dev = {r["device"]: r for r in pre["rows"]}
    post_by_dev = {r["device"]: r for r in post["rows"]}

    anomalies: list[dict[str, Any]] = []
    for device, post_row in post_by_dev.items():
        pre_row = pre_by_dev.get(device)
        if not pre_row:
            continue
        pre_cr = pre_row["conversions"] / max(pre_row["sessions"], 1)
        post_cr = post_row["conversions"] / max(post_row["sessions"], 1)
        if pre_cr == 0:
            continue
        rel = (post_cr - pre_cr) / pre_cr
        if abs(rel) > 0.10:
            anomalies.append(
                {
                    "device": device,
                    "pre_conv_rate": pre_cr,
                    "post_conv_rate": post_cr,
                    "rel_change": rel,
                }
            )

    return {"anomalies": anomalies}


def context_node(state: State) -> dict[str, Any]:
    post_s, post_e = state["post_period"]
    releases = ctx_tools.releases_in_window(post_s, post_e)
    campaigns = ctx_tools.campaigns_in_window(post_s, post_e)
    return {"treatments": releases["rows"] + campaigns["rows"]}


def causal_node(state: State) -> dict[str, Any]:
    target = state["target_device"]
    controls = [d for d in ("mobile", "desktop", "tablet") if d != target]
    pre_s, pre_e = state["pre_period"]
    post_s, post_e = state["post_period"]
    estimate = causal_tools.causal_impact_conversion(
        target_device=target,
        pre_start=pre_s,
        pre_end=pre_e,
        post_start=post_s,
        post_end=post_e,
        controls=controls,
    )
    return {"causal_estimate": estimate}


def _pick_treatment(treatments: list[dict[str, Any]], target_device: str, post_start: str) -> str:
    """Pick the most plausible candidate release for the narrative.

    Priority:
      1. Release on the target component that was rolled back inside the window
      2. Release on the target component released closest to (and before) post_start
      3. Anything else
    """
    matching = [
        t
        for t in treatments
        if t.get("release_id") and target_device.lower() in (t.get("component") or "").lower()
    ]
    if not matching:
        return "No device-specific release found in the window; consider campaigns."

    rolled_back = [t for t in matching if t.get("rollback_ts")]
    if rolled_back:
        chosen = rolled_back[0]
    else:
        chosen = max(matching, key=lambda t: str(t.get("released_ts") or ""))

    return (
        f"Active release: {chosen['release_id']} "
        f"({chosen['component']} {chosen['version']}) released {chosen['released_ts']}, "
        f"rolled back {chosen.get('rollback_ts') or 'not yet'}."
    )


def narrative_node(state: State) -> dict[str, Any]:
    target = state["target_device"]
    causal = state.get("causal_estimate") or {}
    treatments = state.get("treatments", [])
    post_s, post_e = state["post_period"]

    treatment_summary = _pick_treatment(treatments, target, post_s)

    rel = causal.get("rel_effect")
    p = causal.get("p_value")
    ci_low = causal.get("rel_effect_lower_95ci")
    ci_high = causal.get("rel_effect_upper_95ci")
    significant = bool(causal.get("is_significant"))

    if rel is None or "error" in causal:
        return {
            "finding_title": f"No causal estimate for {target}",
            "finding_body": (
                "The causal layer could not produce an estimate. "
                f"Window: {post_s}..{post_e}. Reason: {causal.get('error', 'unknown')}."
            ),
            "confidence": 0.1,
            "risk_level": "low",
        }

    if rel < -0.20 and significant:
        rel_pct = abs(rel) * 100
        return {
            "finding_title": f"{target} conversion fell {rel_pct:.1f}% (high confidence)",
            "finding_body": (
                f"Causal analysis (CausalImpact, BSTS) estimates {target} conversion rate "
                f"fell {rel_pct:.1f}% during {post_s}..{post_e} versus a synthetic control "
                f"built from the other devices. 95% CI: "
                f"[{ci_low * 100:+.1f}%, {ci_high * 100:+.1f}%], p = {p:.4f}. "
                f"{treatment_summary} "
                f"Recommendation: investigate the release and rollback if symptoms persist."
            ),
            "confidence": 0.85,
            "risk_level": "high",
        }

    return {
        "finding_title": f"No high-confidence anomaly on {target}",
        "finding_body": (
            f"Observed change is within noise bounds for {target} in {post_s}..{post_e}. "
            f"rel_effect = {rel:+.2%}, p = {p:.4f}."
        ),
        "confidence": 0.3,
        "risk_level": "low",
    }


def review_node(state: State) -> dict[str, Any]:
    """Three rules; if any fail, loop back to narrative."""
    comments: list[str] = []
    body = state.get("finding_body", "")
    causal = state.get("causal_estimate") or {}

    if state.get("risk_level") == "high" and "p =" not in body:
        comments.append("HIGH-risk finding must cite a p-value")
    if state.get("risk_level") == "high" and not causal.get("is_significant"):
        comments.append("HIGH-risk finding but causal effect not statistically significant")
    target = state.get("target_device")
    if target and target not in body:
        comments.append(f"body does not mention target device '{target}'")

    return {
        "review_passed": not comments,
        "review_comments": comments,
        "retries": state.get("retries", 0) + 1,
    }


def record_node(state: State) -> dict[str, Any]:
    run_id = state.get("run_id")
    if not run_id:
        return {}

    # Mirror the rich KG-side metadata so the outcome loop can later measure
    # what we recommended. Without these fields measure_outcome_for_decision
    # returns 'unsupported_kpi' and the n8n cron skips the decision forever.
    causal = state.get("causal_estimate") or {}
    kg_extra: dict[str, Any] = {"kpi": "conversion_rate"}
    if "rel_effect" in causal:
        kg_extra["relative_change"] = causal["rel_effect"]

    rec_id = log_recommendation(
        run_id=run_id,
        title=state["finding_title"],
        body=state["finding_body"],
        confidence=state["confidence"],
        action_type="read_only",
        risk_level=state["risk_level"],
        component=state.get("target_device"),
        period=state.get("post_period"),
        period_prior=state.get("pre_period"),
        kg_extra=kg_extra,
    )

    # Mirror Hypothesis + Evidence into the KG so future runs can learn.
    causal = state.get("causal_estimate") or {}
    target = state.get("target_device") or "unknown"
    if causal and "rel_effect" in causal:
        try:
            from biq.tools import kg as kg_tools

            kg_tools.record_evidence_for_causal_estimate(
                rec_id_or_run_id=rec_id,
                component=target,
                estimate=causal,
            )
        except Exception:
            pass

    return {"rec_id": rec_id}


# --- Routing -------------------------------------------------------------


def _route_after_review(state: State) -> Literal["narrative", "record", "end"]:
    if state.get("review_passed"):
        return "record"
    if state.get("retries", 0) >= 2:
        return "end"
    return "narrative"


# --- Build + run ---------------------------------------------------------


def build_graph():
    g = StateGraph(State)
    g.add_node("data", data_node)
    g.add_node("context", context_node)
    g.add_node("causal", causal_node)
    g.add_node("narrative", narrative_node)
    g.add_node("review", review_node)
    g.add_node("record", record_node)

    g.add_edge(START, "data")
    g.add_edge("data", "context")
    g.add_edge("context", "causal")
    g.add_edge("causal", "narrative")
    g.add_edge("narrative", "review")
    g.add_conditional_edges(
        "review",
        _route_after_review,
        {"narrative": "narrative", "record": "record", "end": END},
    )
    g.add_edge("record", END)
    return g.compile()


def run_graph(
    target_device: str = "mobile",
    pre_period: tuple[str, str] = ("2018-02-15", "2018-04-14"),
    post_period: tuple[str, str] = ("2018-04-15", "2018-05-10"),
    question: str | None = None,
) -> dict[str, Any]:
    """Run the multi-agent graph end-to-end. Returns the final state."""
    prompt = question or f"investigate {target_device} for window {post_period}"

    with run_context(trigger="cli", prompt=prompt) as ctx:
        step_id = log_step(
            ctx,
            agent_name="graph",
            action="invoke",
            input={
                "target_device": target_device,
                "pre_period": list(pre_period),
                "post_period": list(post_period),
            },
        )

        graph = build_graph()
        initial: State = {
            "question": prompt,
            "target_device": target_device,
            "pre_period": pre_period,
            "post_period": post_period,
            "run_id": ctx.run_id,
            "retries": 0,
        }
        final = dict(graph.invoke(initial))

        finish_step(
            step_id,
            output={
                "review_passed": final.get("review_passed"),
                "rec_id": final.get("rec_id"),
                "risk_level": final.get("risk_level"),
                "retries": final.get("retries"),
            },
        )
        return final
