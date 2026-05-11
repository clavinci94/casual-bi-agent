"""Human-in-the-loop approval UI for agent recommendations.

Lists pending audit.recommendations with their full investigation trail
(agent steps, tool calls, sources) and lets a reviewer approve or reject.
The decision lands in audit.hitl_decisions. Closes the trust loop:

    agent run -> recommendation -> human review -> outcome

Run:
    make hitl
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import text

from biq.db import engine

st.set_page_config(page_title="Causal BI · HITL", layout="wide")


# ---- Data access ---------------------------------------------------------

@st.cache_data(ttl=10)
def _load_recommendations(status: str | None) -> pd.DataFrame:
    sql = """
        SELECT r.rec_id, r.title, r.body, r.confidence, r.action_type,
               r.risk_level, r.status, r.created_at, r.run_id,
               run.trigger, run.prompt, run.started_at AS run_started_at
        FROM audit.recommendations r
        LEFT JOIN audit.agent_runs run ON run.run_id = r.run_id
        {where}
        ORDER BY r.created_at DESC
        LIMIT 200
    """
    where = "WHERE r.status = :status" if status else ""
    with engine.connect() as conn:
        return pd.read_sql(text(sql.format(where=where)), conn, params={"status": status} if status else {})


def _load_run_steps(run_id: str) -> pd.DataFrame:
    sql = text(
        "SELECT seq, agent_name, action, latency_ms, input::text AS input, output::text AS output "
        "FROM audit.agent_steps WHERE run_id = :rid ORDER BY seq"
    )
    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params={"rid": run_id})


def _load_tool_calls(run_id: str) -> pd.DataFrame:
    sql = text(
        "SELECT s.seq, s.agent_name, tc.tool_name, tc.rows_returned, tc.latency_ms, "
        "       tc.params::text AS params, tc.error "
        "FROM audit.tool_calls tc "
        "JOIN audit.agent_steps s ON s.step_id = tc.step_id "
        "WHERE s.run_id = :rid ORDER BY s.seq, tc.called_at"
    )
    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params={"rid": run_id})


def _record_decision(rec_id: str, decision: str, approver: str, comment: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO audit.hitl_decisions (rec_id, approver, decision, comment) "
                "VALUES (:rec, :approver, :dec, :comment)"
            ),
            {"rec": rec_id, "approver": approver, "dec": decision, "comment": comment},
        )
        new_status = {"approve": "approved", "reject": "rejected", "modify": "pending"}[decision]
        conn.execute(
            text("UPDATE audit.recommendations SET status = :s WHERE rec_id = :r"),
            {"s": new_status, "r": rec_id},
        )


# ---- UI -----------------------------------------------------------------

st.title("Causal BI · Human-in-the-Loop")
st.caption(
    "Review and approve agent recommendations before they influence downstream "
    "actions. Every decision is logged to `audit.hitl_decisions`."
)

with st.sidebar:
    st.subheader("Filters")
    status_filter = st.selectbox(
        "Status",
        options=["pending", "approved", "rejected", "all"],
        index=0,
    )
    approver = st.text_input("Reviewer name", value="claudio")

status = None if status_filter == "all" else status_filter
df = _load_recommendations(status)

if df.empty:
    st.info(f"No recommendations with status='{status_filter}'.")
    st.stop()

st.metric("Recommendations", len(df))

# ---- Per-recommendation card --------------------------------------------

for _, rec in df.iterrows():
    risk_colour = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(rec["risk_level"], "⚪")
    with st.expander(f"{risk_colour} {rec['title']}", expanded=(rec["status"] == "pending")):
        cols = st.columns([3, 1, 1, 1])
        cols[0].markdown(f"**Created:** {rec['created_at']}")
        cols[1].metric("Risk", rec["risk_level"])
        cols[2].metric("Confidence", f"{rec['confidence']:.0%}" if rec["confidence"] else "—")
        cols[3].metric("Status", rec["status"])

        st.markdown(rec["body"])

        with st.expander("Investigation trace", expanded=False):
            st.markdown(f"**Run prompt:** _{rec['prompt']}_  ·  trigger: `{rec['trigger']}`")
            steps_df = _load_run_steps(rec["run_id"])
            calls_df = _load_tool_calls(rec["run_id"])
            tab1, tab2 = st.tabs(["Agent steps", "Tool calls"])
            with tab1:
                if steps_df.empty:
                    st.write("(no steps)")
                else:
                    st.dataframe(steps_df, hide_index=True, use_container_width=True)
            with tab2:
                if calls_df.empty:
                    st.write("(no tool calls)")
                else:
                    st.dataframe(calls_df, hide_index=True, use_container_width=True)

        if rec["status"] == "pending":
            with st.form(key=f"form_{rec['rec_id']}"):
                comment = st.text_input("Comment (optional)", key=f"cmt_{rec['rec_id']}")
                col_a, col_r = st.columns(2)
                approve_clicked = col_a.form_submit_button("✓ Approve", use_container_width=True)
                reject_clicked = col_r.form_submit_button("✗ Reject", use_container_width=True)

                if approve_clicked or reject_clicked:
                    if not approver.strip():
                        st.error("Reviewer name is required.")
                    else:
                        decision = "approve" if approve_clicked else "reject"
                        _record_decision(rec["rec_id"], decision, approver, comment)
                        st.success(f"Recorded {decision} from {approver}.")
                        _load_recommendations.clear()
                        st.rerun()
        else:
            st.info(f"This recommendation has status `{rec['status']}`. Re-open is not implemented.")
