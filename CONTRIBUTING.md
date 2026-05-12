# Contributing

Thanks for your interest. The codebase is small, the rules are short.

## Before you start

1. Read [`AGENTS.md`](AGENTS.md). It's the operational guide; everything below
   assumes you know that document.
2. Skim [`docs/clean-architecture.md`](docs/clean-architecture.md) for the
   layering rules. PRs that violate them get bounced fast.

## Setup

```bash
git clone https://github.com/clavinci94/causal-bi-agent.git
cd causal-bi-agent
cp .env.example .env
make db-up && make backend-sync
make db-schemas        # runs alembic upgrade head
make db-load           # if you have Olist CSVs in data/seed/
# or
cd backend && uv run python scripts/seed_minimal.py
```

## Running the tests

```bash
make test                                # all
cd backend && uv run pytest -m "not causal"   # skip R-service-dependent
```

CI requires **≥75 % coverage**; current main is 89 %. New code that drops it
below 75 % gets blocked.

## Code style

- `ruff check` and `ruff format` are gospel. CI fails on either.
- Python ≥3.12. Use modern type hints (`list[str]`, `X | None`).
- No new top-level dirs without an entry in `AGENTS.md`.

## Architecture rules

- **Domain (`biq/tools/`, `biq/seeders/`)** must not import from
  `biq/agents/` or `biq/api/`. If you need agent orchestration in a tool,
  the abstraction is wrong — extract it.
- **Application (`biq/agents/`)** is the only place that touches
  `biq/audit.py`. Tools never write audit; the agent that called them does.
- **Interface (`biq/api/`, `biq/mcp_servers/`, `biq/ui/`)** does no business
  logic — translate between the outside world and the application layer.
- New schema changes go through Alembic:
  ```bash
  cd backend && uv run alembic revision -m "what changed"
  ```
  Edit the new file in `backend/alembic/versions/`; do NOT touch existing
  revisions.

## Commits + PRs

- Conventional Commits: `feat:`, `fix:`, `chore:`, `docs:`, `test:`.
- One logical change per commit, even if it spans many files.
- PR title mirrors the headline commit. PR body explains the **why**.
- Keep PRs under ~400 LOC where possible. Large refactors get split.

## Tests

- Unit tests for pure logic (e.g. `tests/test_graph.py` for graph nodes).
- Integration tests that need the DB use the `db_ready` fixture (skips on
  missing data).
- R-service-dependent tests get marked `@pytest.mark.causal`; CI skips them
  because the R service isn't spun up there.

## Releases

`main` is always deployable. Render auto-deploys on push to `main` once the
blueprint is connected (see `infra/deploy.md`).

## Security

See [`SECURITY.md`](SECURITY.md).
