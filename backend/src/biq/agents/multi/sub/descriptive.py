"""Deterministic descriptive sub-worker.

Reads conversion_rate_daily from kpi.* for the analyst's horizon vs baseline
windows and emits one Finding per device whose conversion rate moved by
more than `threshold_rel` between the two windows.

Pure delta arithmetic — no LLM. The Analyst-Lead aggregates these Findings
together with the CausalSubResult into a single AnalysisResult.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from biq.agents.multi.audit import audit_sub
from biq.agents.multi.state import EvidenceRef, Finding
from biq.tools import kpi as kpi_tools

# A relative move >10% in conversion is the same heuristic the existing
# heuristic detector uses; keeping them aligned avoids surprises.
DEFAULT_THRESHOLD_REL = 0.10


@dataclass
class DescriptiveSubResult:
    findings: list[Finding] = field(default_factory=list)
    notes: str | None = None
    skipped: bool = False  # True when DB was unreachable or window empty


def _parse(d: str) -> date:
    return date.fromisoformat(d)


def derive_baseline(post_start: str, post_end: str) -> tuple[str, str]:
    """Default baseline = same length window immediately before post_start."""
    ps, pe = _parse(post_start), _parse(post_end)
    span = (pe - ps).days + 1  # inclusive day count
    pre_end = ps - timedelta(days=1)
    pre_start = pre_end - timedelta(days=span - 1)
    return pre_start.isoformat(), pre_end.isoformat()


def _severity(rel: float) -> str:
    abs_rel = abs(rel)
    if abs_rel >= 0.25:
        return "high"
    if abs_rel >= 0.15:
        return "medium"
    return "low"


def run(
    horizon: tuple[str, str],
    baseline: tuple[str, str] | None = None,
    target_device: str = "*",
    threshold_rel: float = DEFAULT_THRESHOLD_REL,
) -> DescriptiveSubResult:
    """Compare conversion rates between baseline and horizon, per device."""
    post_start, post_end = horizon
    pre_start, pre_end = baseline or derive_baseline(post_start, post_end)

    with audit_sub(
        agent_name="descriptive",
        action="kpi_delta",
        input={
            "horizon": [post_start, post_end],
            "baseline": [pre_start, pre_end],
            "target_device": target_device,
            "threshold_rel": threshold_rel,
        },
    ) as tel:
        result = _run_inner(post_start, post_end, pre_start, pre_end, target_device, threshold_rel)
        tel["output"] = {
            "skipped": result.skipped,
            "findings_count": len(result.findings),
            "notes": result.notes,
        }
        return result


def _run_inner(
    post_start: str,
    post_end: str,
    pre_start: str,
    pre_end: str,
    target_device: str,
    threshold_rel: float,
) -> DescriptiveSubResult:
    try:
        pre = kpi_tools.kpi_query("conversion_rate_daily", pre_start, pre_end, group_by=["device"])
        post = kpi_tools.kpi_query(
            "conversion_rate_daily", post_start, post_end, group_by=["device"]
        )
    except Exception as e:
        return DescriptiveSubResult(
            skipped=True,
            notes=f"KPI query failed: {type(e).__name__}: {e}",
        )

    if "error" in pre or "error" in post:
        return DescriptiveSubResult(
            skipped=True,
            notes=f"KPI query rejected: pre={pre.get('error')} post={post.get('error')}",
        )

    pre_by = {r["device"]: r for r in pre.get("rows", [])}
    post_by = {r["device"]: r for r in post.get("rows", [])}

    if not pre_by or not post_by:
        return DescriptiveSubResult(
            skipped=True,
            notes=f"no data: pre_devices={list(pre_by)}, post_devices={list(post_by)}",
        )

    devices = [target_device] if target_device != "*" else sorted(set(pre_by) | set(post_by))

    findings: list[Finding] = []
    for device in devices:
        pre_row = pre_by.get(device)
        post_row = post_by.get(device)
        if not pre_row or not post_row:
            continue

        pre_sess = max(pre_row.get("sessions", 0), 1)
        post_sess = max(post_row.get("sessions", 0), 1)
        pre_cr = pre_row.get("conversions", 0) / pre_sess
        post_cr = post_row.get("conversions", 0) / post_sess
        if pre_cr == 0:
            continue

        rel = (post_cr - pre_cr) / pre_cr
        if abs(rel) < threshold_rel:
            continue

        direction = "eingebrochen" if rel < 0 else "gestiegen"
        findings.append(
            Finding(
                title=f"Conversion {direction} auf {device}: {rel:+.1%}",
                body_de=(
                    f"Conversion-Rate auf {device} ging von {pre_cr:.2%} "
                    f"({pre_start} bis {pre_end}) auf {post_cr:.2%} "
                    f"({post_start} bis {post_end}) — Veränderung {rel:+.1%}."
                ),
                evidence=[
                    EvidenceRef(
                        kind="kpi_query",
                        ref=f"kpi.conversion_rate_daily/{device}/{pre_start}..{pre_end}",
                    ),
                    EvidenceRef(
                        kind="kpi_query",
                        ref=f"kpi.conversion_rate_daily/{device}/{post_start}..{post_end}",
                    ),
                ],
                confidence=min(0.5 + abs(rel), 0.95),
                severity=_severity(rel),
            )
        )

    return DescriptiveSubResult(
        findings=findings,
        notes=f"checked {len(devices)} device(s), threshold ±{threshold_rel:.0%}",
    )
