"""KPI read access — same governed semantic layer as the agents use."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from biq.tools import kpi as kpi_tools

router = APIRouter(prefix="/kpis", tags=["kpis"])


@router.get("")
def list_kpis() -> dict[str, list[str]]:
    """Allowlisted kpi.* view names."""
    return {"views": sorted(kpi_tools.ALLOWED_VIEWS)}


@router.get("/{view}")
def query_kpi(
    view: str,
    start: Annotated[str, Query(description="ISO date, inclusive.")],
    end: Annotated[str, Query(description="ISO date, exclusive.")],
    group_by: Annotated[list[str] | None, Query()] = None,
) -> dict:
    result = kpi_tools.kpi_query(view, start, end, group_by=group_by)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
