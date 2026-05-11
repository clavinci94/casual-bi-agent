"""Shared pytest fixtures.

Most tests here are *integration* tests: they require a live Postgres
(loaded with Olist + simulator output) and, for causal tests, a running
R service on port 8765.

Run with:
    make test                                   # all tests
    cd backend && uv run pytest -m "not causal" # skip R-dependent tests
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from biq.db import engine


def pytest_collection_modifyitems(config, items):
    """Auto-mark causal tests so they can be skipped without an R service."""
    for item in items:
        if "causal" in item.nodeid:
            item.add_marker(pytest.mark.causal)


def pytest_configure(config):
    config.addinivalue_line("markers", "causal: requires R service on port 8765")


@pytest.fixture(scope="session")
def db_ready() -> bool:
    """Sanity-check the DB has the expected seed data. Skip everything if not."""
    try:
        with engine.connect() as conn:
            orders = conn.execute(text("SELECT count(*) FROM raw.orders")).scalar_one()
            events = conn.execute(text("SELECT count(*) FROM raw.web_events")).scalar_one()
            releases = conn.execute(text("SELECT count(*) FROM raw.releases")).scalar_one()
    except Exception as e:
        pytest.skip(f"DB not reachable or schemas missing: {e}")

    if orders < 1000 or events < 1000 or releases < 1:
        pytest.skip(
            f"DB lacks seed data (orders={orders}, events={events}, releases={releases}). "
            f"Run: make db-seed"
        )
    return True
