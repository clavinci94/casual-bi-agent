"""Recommendation queue + HITL decisions."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from biq.db import engine

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


class Recommendation(BaseModel):
    rec_id: str
    run_id: str
    title: str
    body: str
    confidence: float | None
    action_type: str
    risk_level: str
    status: str
    created_at: datetime


class DecisionRequest(BaseModel):
    decision: Literal["approve", "reject", "modify"]
    approver: str = Field(min_length=1, max_length=200)
    comment: str | None = None


class DecisionResponse(BaseModel):
    rec_id: str
    decision: str
    status: str


_LIST_SQL = """
    SELECT rec_id, run_id, title, body, confidence, action_type,
           risk_level, status, created_at
    FROM audit.recommendations
    {where}
    ORDER BY created_at DESC
    LIMIT :limit
"""

_GET_SQL = """
    SELECT rec_id, run_id, title, body, confidence, action_type,
           risk_level, status, created_at
    FROM audit.recommendations
    WHERE rec_id = :id
"""


@router.get("", response_model=list[Recommendation])
def list_recommendations(
    status: Literal["pending", "approved", "rejected", "all"] = "pending",
    limit: int = Query(default=50, le=200),
) -> list[Recommendation]:
    where = "" if status == "all" else "WHERE status = :status"
    sql = text(_LIST_SQL.format(where=where))
    params: dict[str, object] = {"limit": limit}
    if status != "all":
        params["status"] = status
    with engine.connect() as conn:
        rows = conn.execute(sql, params).all()
    return [Recommendation(**dict(r._mapping)) for r in rows]


@router.get("/{rec_id}", response_model=Recommendation)
def get_recommendation(rec_id: str) -> Recommendation:
    with engine.connect() as conn:
        row = conn.execute(text(_GET_SQL), {"id": rec_id}).first()
    if not row:
        raise HTTPException(status_code=404, detail="recommendation not found")
    return Recommendation(**dict(row._mapping))


@router.post("/{rec_id}/decision", response_model=DecisionResponse)
def record_decision(rec_id: str, payload: DecisionRequest) -> DecisionResponse:
    new_status_map = {"approve": "approved", "reject": "rejected", "modify": "pending"}
    new_status = new_status_map[payload.decision]

    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM audit.recommendations WHERE rec_id = :id"),
            {"id": rec_id},
        ).first()
        if not exists:
            raise HTTPException(status_code=404, detail="recommendation not found")

        # Generate the hitl_decision id up-front so we can mirror it into the KG.
        import uuid as _uuid

        hitl_id = str(_uuid.uuid4())

        conn.execute(
            text(
                "INSERT INTO audit.hitl_decisions "
                "(decision_id, rec_id, approver, decision, comment) "
                "VALUES (:did, :rec, :approver, :dec, :comment)"
            ),
            {
                "did": hitl_id,
                "rec": rec_id,
                "approver": payload.approver,
                "dec": payload.decision,
                "comment": payload.comment,
            },
        )
        conn.execute(
            text("UPDATE audit.recommendations SET status = :s WHERE rec_id = :r"),
            {"s": new_status, "r": rec_id},
        )

    # Mirror Decision into the KG (best-effort).
    try:
        from biq.tools import kg as kg_tools

        kg_tools.record_decision_for_hitl(
            rec_id=rec_id,
            hitl_decision_id=hitl_id,
            decision=payload.decision,
            approver=payload.approver,
            comment=payload.comment,
        )
    except Exception:
        pass

    return DecisionResponse(rec_id=rec_id, decision=payload.decision, status=new_status)
