# backend

Python 3.12 · FastAPI · LangGraph · SQLAlchemy · psycopg 3 · uv.

## Setup

Run from the repo root:

```bash
make db-up         # start local Postgres
make backend-sync  # uv sync
make db-schemas    # apply db/schemas/*.sql
# download Olist CSVs into data/seed/ first (see data/seed/README.md)
make db-load       # load CSVs into raw.*
```

## Layout

```
backend/
├── pyproject.toml
├── src/biq/
│   ├── __init__.py
│   ├── config.py     pydantic-settings, reads .env
│   ├── db.py         SQLAlchemy engine + session
│   ├── api/          FastAPI routes (TBD)
│   ├── agents/       LangGraph nodes (TBD)
│   ├── mcp_servers/  one module per MCP server (TBD)
│   └── eval/         evaluation harness (TBD)
└── scripts/
    ├── run_schemas.py
    ├── load_olist.py
    ├── simulate.py        (TBD — web_events / campaigns / releases / tickets)
    └── generate_kpi_views.py  (TBD — kpi-catalog.yaml → 02_kpi.sql)
```
