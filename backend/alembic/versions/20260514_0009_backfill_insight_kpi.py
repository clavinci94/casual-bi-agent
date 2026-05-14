"""backfill kpi + period_prior on legacy Insight nodes

The early agents (graph.py) recorded recommendations without passing
kpi / period_prior / relative_change to the KG mirror. That left the
Insight properties without the metadata the outcome loop needs, so
measure_outcome_for_decision returned 'unsupported_kpi' and the daily
cron skipped almost every approval.

Going forward graph.py writes the rich properties (see commit fixing
record_node). For the legacy Insights we backfill the most likely
KPI — conversion_rate_daily — since that's the only KPI the
LangGraph orchestrator ever computed. We also synthesise a
period_prior from the run window when it's missing, so the same
baseline-comparison the agent originally used is available at
measurement time.

Idempotent: only touches Insights that don't already carry the field.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-14
"""

from __future__ import annotations

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # 1. backfill kpi="conversion_rate" wherever it's missing. The view is
    #    called conversion_rate_daily but the KG label we standardised on
    #    (and that _OUTCOME_KPI_SQL keys on) drops the time-grain suffix.
    op.execute("""
        UPDATE kg.nodes
        SET properties = jsonb_set(properties, '{kpi}', '"conversion_rate"'::jsonb, true)
        WHERE label = 'Insight'
          AND NOT (properties ? 'kpi');
    """)

    # 1b. Fix any pre-existing rows that used the old `_daily` suffix
    #     (e.g. from earlier hand-written backfills) so they line up
    #     with the _OUTCOME_KPI_SQL lookup.
    op.execute("""
        UPDATE kg.nodes
        SET properties = jsonb_set(properties, '{kpi}', '"conversion_rate"'::jsonb, true)
        WHERE label = 'Insight'
          AND (properties->>'kpi') = 'conversion_rate_daily';
    """)

    # 2. backfill a placeholder period_prior on Insights that have period_*
    #    but no period_prior_* — assume a window of equal length immediately
    #    before the anomaly window. measure_outcome_for_decision falls back
    #    to other heuristics when these are missing, but having them lets the
    #    common path succeed.
    op.execute("""
        UPDATE kg.nodes
        SET properties = properties
            || jsonb_build_object(
                'period_prior_start',
                ((properties->>'period_start')::date
                 - ((properties->>'period_end')::date - (properties->>'period_start')::date))::text,
                'period_prior_end',
                ((properties->>'period_start')::date - 1)::text
            )
        WHERE label = 'Insight'
          AND properties ? 'period_start'
          AND properties ? 'period_end'
          AND NOT (properties ? 'period_prior_start');
    """)


def downgrade() -> None:
    # Remove only the keys this migration added; we can't tell which
    # rows already had them so we strip from all legacy Insights.
    op.execute("""
        UPDATE kg.nodes
        SET properties = properties
            - 'kpi'
            - 'period_prior_start'
            - 'period_prior_end'
        WHERE label = 'Insight';
    """)
