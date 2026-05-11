DB_URL ?= postgresql+psycopg://causalbi:causalbi@localhost:5433/causalbi
PSQL_URL := $(subst postgresql+psycopg,postgresql,$(DB_URL))
DATA_DIR ?= $(PWD)/data/seed

.PHONY: help db-up db-down db-wait db-schemas db-load db-simulate db-seed db-reset detect-anomalies backend-sync format lint test

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
	@echo "  backend-sync  uv sync inside backend/"
	@echo "  format        ruff format + autofix"
	@echo "  lint          ruff check + mypy"
	@echo "  test          pytest"

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
	@cd backend && DATABASE_URL="$(DB_URL)" uv run python scripts/load_olist.py --data-dir $(DATA_DIR)

db-simulate:
	@cd backend && DATABASE_URL="$(DB_URL)" uv run python scripts/simulate.py --all $(SIM_ARGS)

db-seed: db-schemas db-load db-simulate

detect-anomalies:
	@cd backend && DATABASE_URL="$(DB_URL)" uv run python scripts/detect_anomalies.py $(DETECT_ARGS)

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
