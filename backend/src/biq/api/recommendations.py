"""Recommendation queue + HITL decisions."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

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
    SELECT r.rec_id, r.run_id, r.title, r.body, r.confidence, r.action_type,
           r.risk_level, r.status, r.created_at
    FROM audit.recommendations r
    LEFT JOIN audit.agent_runs ar ON ar.run_id = r.run_id
    {where}
    ORDER BY r.created_at DESC
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
    limit: Annotated[int, Query(le=200)] = 50,
    exclude_triggers: Annotated[
        list[str] | None,
        Query(
            description=(
                "Exclude recommendations whose parent run has any of these "
                "triggers (e.g. 'test') — keeps pytest fixtures off the HITL queue."
            ),
        ),
    ] = None,
) -> list[Recommendation]:
    conditions: list[str] = []
    params: dict[str, object] = {"limit": limit}
    if status != "all":
        conditions.append("r.status = :status")
        params["status"] = status
    if exclude_triggers:
        conditions.append("(ar.trigger IS NULL OR ar.trigger <> ALL(:excluded))")
        params["excluded"] = list(exclude_triggers)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    sql = text(_LIST_SQL.format(where=where))
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


# --- Bulk decision -----------------------------------------------------


class BulkDecisionRequest(BaseModel):
    """Approve or reject several pending recommendations in one call.
    Same approver + comment apply to every rec_id."""

    rec_ids: list[str] = Field(min_length=1, max_length=100)
    decision: Literal["approve", "reject"]
    approver: str = Field(min_length=1, max_length=200)
    comment: str | None = None


class BulkDecisionResponse(BaseModel):
    decided: list[DecisionResponse]
    skipped: list[dict[str, str]]  # [{"rec_id": "...", "reason": "not_pending"|"not_found"}]


@router.post("/bulk-decision", response_model=BulkDecisionResponse)
def bulk_decision(payload: BulkDecisionRequest) -> BulkDecisionResponse:
    """Apply the same approve/reject decision to multiple recommendations.

    Only `pending` recommendations are touched — already-decided ones are
    listed in the `skipped` array with a reason, so the UI can warn the
    operator that a row in their selection was already handled by someone
    else. Atomic per-rec but not as a whole batch: if one row fails for
    a non-existence reason, the rest still get decided.
    """
    new_status = "approved" if payload.decision == "approve" else "rejected"
    decided: list[DecisionResponse] = []
    skipped: list[dict[str, str]] = []

    import uuid as _uuid

    for rec_id in payload.rec_ids:
        with engine.begin() as conn:
            row = conn.execute(
                text("SELECT status FROM audit.recommendations WHERE rec_id = :id"),
                {"id": rec_id},
            ).first()
            if not row:
                skipped.append({"rec_id": rec_id, "reason": "not_found"})
                continue
            if row[0] != "pending":
                skipped.append({"rec_id": rec_id, "reason": "not_pending"})
                continue

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

        # KG mirror — best effort, outside the txn so a KG outage can't
        # block the audit write.
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

        decided.append(
            DecisionResponse(rec_id=rec_id, decision=payload.decision, status=new_status)
        )

    return BulkDecisionResponse(decided=decided, skipped=skipped)
