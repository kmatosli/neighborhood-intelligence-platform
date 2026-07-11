# Bronzeville–Woodlawn Observatory

A civic-data project focused only on Bronzeville and Woodlawn in Chicago.

## Current phase

Phase 1 establishes a reliable connection to the City of Chicago Socrata API and validates the crime dataset before any application UI is built.

No data has been ingested and no neighborhood figures exist yet. See [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md).

## Documentation

- [docs/README.md](docs/README.md) — documentation index
- [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) — what is built and what is next
- [TODO.md](TODO.md) — working checklist
- [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) — system design, and the [ADRs](docs/architecture/ADR/) behind it
- [docs/product/PRD.md](docs/product/PRD.md) — what is being built, for whom, and the long-term vision
- [docs/methodology/DATA_GOVERNANCE.md](docs/methodology/DATA_GOVERNANCE.md) — the rules every published number must satisfy
- [CONTRIBUTING.md](CONTRIBUTING.md) — setup, quality gates, and data rules

## Data source

- Crimes — 2001 to Present
- Dataset ID: `ijzp-q8t2`
- Analysis start date: January 1, 2006

## Setup

```powershell
uv sync
Copy-Item .env.example .env
uv run python scripts/check_crime_api.py
uv run python scripts/pull_crime_sample.py
uv run pytest
```

## Quality checks

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

## Data rules

- Never commit downloaded crime data.
- Never commit API tokens.
- Preserve official source fields.
- Treat Bronzeville as a custom GIS boundary, not a single community area.
- Do not infer causation, nationality, or immigration status from crime records.
