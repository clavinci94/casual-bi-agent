"""Causal sub-worker — wraps biq.tools.causal.causal_impact_conversion.

Returns a CausalSubResult that the Analyst-Lead merges into AnalysisResult.
Skipped (with notes) when the R service or DB is unreachable, so the
Analyst still produces a partial result instead of crashing the run.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from biq.agents.multi.audit import audit_sub
from biq.agents.multi.state import CausalEstimate
from biq.agents.multi.sub.descriptive import derive_baseline
from biq.tools import causal as causal_tools


@dataclass
class CausalSubResult:
    estimates: list[CausalEstimate] = field(default_factory=list)
    notes: str | None = None
    skipped: bool = False


# Sensible defaults: every device we have data for is a potential control,
# minus the target. The R service tolerates missing series.
_ALL_DEVICES = ("mobile", "desktop", "tablet")


def run(
    horizon: tuple[str, str],
    target_device: str,
    baseline: tuple[str, str] | None = None,
    controls: list[str] | None = None,
) -> CausalSubResult:
    pre = baseline or derive_baseline(*horizon)
    effective_controls = (
        controls if controls is not None else [d for d in _ALL_DEVICES if d != target_device]
    )
    with audit_sub(
        agent_name="causal",
        action="causal_impact",
        input={
            "horizon": list(horizon),
            "baseline": list(pre),
            "target_device": target_device,
            "controls": effective_controls,
        },
    ) as tel:
        result = _run_inner(horizon, pre, target_device, effective_controls)
        tel["output"] = {
            "skipped": result.skipped,
            "estimates_count": len(result.estimates),
            "notes": result.notes,
        }
        return result


def _run_inner(
    horizon: tuple[str, str],
    pre: tuple[str, str],
    target_device: str,
    controls: list[str],
) -> CausalSubResult:
    if target_device == "*":
        return CausalSubResult(
            skipped=True,
            notes="causal estimation requires a specific target_device",
        )

    try:
        raw = causal_tools.causal_impact_conversion(
            target_device=target_device,
            pre_start=pre[0],
            pre_end=pre[1],
            post_start=horizon[0],
            post_end=horizon[1],
            controls=controls,
        )
    except Exception as e:
        return CausalSubResult(
            skipped=True,
            notes=f"R service call failed: {type(e).__name__}: {e}",
        )

    if "error" in raw:
        return CausalSubResult(skipped=True, notes=f"R service: {raw['error']}")

    rel = raw.get("rel_effect")
    if rel is None:
        return CausalSubResult(skipped=True, notes="R service returned no rel_effect")

    method = "CausalImpact (BSTS)"
    if raw.get("controls_used"):
        method += f" with controls={raw['controls_used']}"

    estimate = CausalEstimate(
        method=method,
        treatment=f"horizon {horizon[0]}..{horizon[1]}",
        outcome=f"conversion_rate ({target_device})",
        estimate=float(rel),
        ci_lower=raw.get("rel_effect_lower_95ci"),
        ci_upper=raw.get("rel_effect_upper_95ci"),
        p_value=raw.get("p_value"),
        notes=(
            f"avg_actual={raw.get('avg_actual')}, "
            f"avg_predicted={raw.get('avg_predicted')}, "
            f"n_obs={raw.get('n_observations')}"
        ),
    )
    return CausalSubResult(estimates=[estimate], notes=method)
