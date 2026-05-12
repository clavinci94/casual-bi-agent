DB_URL ?= postgresql+psycopg://causalbi:causalbi@localhost:5433/causalbi
PSQL_URL := $(subst postgresql+psycopg,postgresql,$(DB_URL))
DATA_DIR ?= $(PWD)/data/seed

.PHONY: help db-up db-down db-wait db-schemas db-load db-simulate db-seed db-reset detect-anomalies investigate graph-investigate mcp-serve mcp-inspect mcp-smoke r-up r-down r-logs causal-smoke hitl api-serve backend-sync format lint test evals frontend-install frontend-dev frontend-build

help:
	@echo "Targets:"
	@echo "  db-up         Start local Postgres+pgvector (port 5433)"
	@echo "  db-down       Stop Postgres"
	@echo "  db-schemas    Apply all SQL files in db/schemas/"
	@echo "  db-load       Load Olist CSVs into raw.* (download into data/seed/ first)"
	@echo "  db-simulate   Generate synthetic web_events / campaigns / releases / tickets"
	@echo "  db-seed       db-schemas + db-load + db-simulate (full pipeline)"
	@echo "  db-reset      Wipe volume, restart, reapply schemas"
	@echo "  detect-anomalies  Run the heuristic anomaly detector"
	@echo "  investigate Q=\"...\"  Run the LLM-driven investigator (requires ANTHROPIC_API_KEY)"
	@echo "  mcp-serve     Run the causal-bi MCP server (stdio)"
	@echo "  mcp-inspect   Open the MCP Inspector GUI against the server"
	@echo "  mcp-smoke     Programmatic smoke test of the MCP server"
	@echo "  r-up          Build + start the R CausalImpact service (port 8765)"
	@echo "  r-down        Stop the R service"
	@echo "  r-logs        Tail R service logs"
	@echo "  causal-smoke  Run CausalImpact on the mobile_v2 ground truth"
	@echo "  graph-investigate  Run the LangGraph multi-agent investigator"
	@echo "  hitl          Launch the Streamlit HITL approval UI"
	@echo "  api-serve     Launch the FastAPI HTTP API on http://localhost:8000"
	@echo "  backend-sync  uv sync inside backend/"
	@echo "  format        ruff format + autofix"
	@echo "  lint          ruff check + mypy"
	@echo "  test          pytest"
	@echo "  evals         LLM-as-judge quality eval (costs ~CHF 0.05/run, needs ANTHROPIC_API_KEY)"
	@echo "  frontend-install  npm install in frontend/"
	@echo "  frontend-dev      Next.js dev server on http://localhost:3000 (needs api-serve running)"
	@echo "  frontend-build    Next.js production build"

db-up:
	docker compose up -d db
	@$(MAKE) db-wait
	@echo ""
	@echo "Postgres ready on port 5433."
	@echo "DATABASE_URL=$(DB_URL)"

db-wait:
	@echo -n "Waiting for Postgres "
	@until docker compose exec -T db pg_isready -U causalbi -d causalbi > /dev/null 2>&1; do \
		echo -n "."; sleep 1; \
	done; echo " ok"

db-down:
	docker compose down

db-schemas:
	@cd backend && DATABASE_URL="$(DB_URL)" uv run python scripts/run_schemas.py

db-load:
	@cd backend && DATABASE_URL="$(DB_URL)" uv run python scripts/load_olist.py --data-dir $(DATA_DIR) $(LOAD_ARGS)

db-simulate:
	@cd backend && DATABASE_URL="$(DB_URL)" uv run python scripts/simulate.py --all $(SIM_ARGS)

db-seed: db-schemas db-load db-simulate

detect-anomalies:
	@cd backend && DATABASE_URL="$(DB_URL)" uv run python scripts/detect_anomalies.py $(DETECT_ARGS)

investigate:
	@if [ -z "$(Q)" ]; then echo 'Usage: make investigate Q="your question here"'; exit 1; fi
	@cd backend && DATABASE_URL="$(DB_URL)" uv run python scripts/investigate.py "$(Q)" $(INVESTIGATE_ARGS)

mcp-serve:
	@cd backend && DATABASE_URL="$(DB_URL)" uv run python -m biq.mcp_servers.bi

mcp-inspect:
	@cd backend && DATABASE_URL="$(DB_URL)" uv run mcp dev src/biq/mcp_servers/bi.py

mcp-smoke:
	@cd backend && DATABASE_URL="$(DB_URL)" uv run python scripts/mcp_smoke.py

r-up:
	docker compose up -d --build r-causal

r-down:
	docker compose stop r-causal

r-logs:
	docker compose logs -f r-causal

causal-smoke:
	@cd backend && DATABASE_URL="$(DB_URL)" R_BASE_URL="http://localhost:8765" uv run python scripts/causal_smoke.py

graph-investigate:
	@cd backend && DATABASE_URL="$(DB_URL)" R_BASE_URL="http://localhost:8765" uv run python scripts/graph_investigate.py $(GRAPH_ARGS)

hitl:
	@cd backend && DATABASE_URL="$(DB_URL)" uv run streamlit run src/biq/ui/hitl.py

api-serve:
	@cd backend && DATABASE_URL="$(DB_URL)" R_BASE_URL="http://localhost:8765" \
		uv run uvicorn biq.api.app:app --reload --port 8000

db-reset:
	docker compose down -v
	$(MAKE) db-up
	$(MAKE) db-schemas

backend-sync:
	cd backend && uv sync

format:
	cd backend && uv run ruff format src scripts && uv run ruff check --fix src scripts

lint:
	cd backend && uv run ruff check src scripts && uv run mypy src

test:
	cd backend && uv run pytest

evals:
	@cd backend && DATABASE_URL="$(DB_URL)" R_BASE_URL="http://localhost:8765" \
		uv run pytest -m eval -v -s tests/evals/

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build
