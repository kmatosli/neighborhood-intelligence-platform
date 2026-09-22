# Ward 20 Neighborhood Intelligence

A civic-data platform for **Chicago's Ward 20** and the neighborhoods within it
(the portions of Woodlawn, Washington Park, Englewood, Fuller Park and New City that
lie inside the ward). Working public name pending a final product name.

> The repository is still named `bronzeville-woodlawn-observatory` and the Python
> package `bw_observatory` for historical reasons. Bronzeville is no longer a product
> geography — see `docs/methodology/GEOGRAPHY.md` and ADR-0005.

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

## Historical ingestion

Downloads raw crime records into the Bronze layer, one calendar year per Parquet file. Paged, retried, and restartable.

```powershell
uv run python scripts/download_crime_history.py --year 2024
uv run python scripts/download_crime_history.py --start-year 2006 --end-year 2012
uv run python scripts/download_crime_history.py --resume
uv run python scripts/download_crime_history.py --year 2024 --force
```

Output lands in `data/bronze/crime/` (`<year>.parquet`, `manifest.parquet`, `refresh_log.parquet`) with logs in `logs/`. Records are stored exactly as published — no filtering, no cleaning, no neighborhood assignment. Geography fields are preserved for later GIS work.

## Keeping crime data current

The historical loader re-downloads whole years and is **not** the freshness path. Crime
data stays current through a daily incremental refresh (source `updated_on` watermark,
upsert by `id`, only new/changed rows re-enriched), a monthly reconciliation that marks
records the City has since removed (`source_status`, never deleted), and a read-only health
endpoint. The full model — schedule, safety properties, failure behaviour, production
scheduling and its open memory decision — is in
[docs/methodology/CRIME_DATA_OPERATING_MODEL.md](docs/methodology/CRIME_DATA_OPERATING_MODEL.md).

```powershell
uv run python scripts/refresh_crime.py --dry-run     # what would change; writes nothing
uv run python scripts/refresh_crime.py               # daily incremental refresh
uv run python scripts/reconcile_crime.py             # monthly: mark source-removed rows
curl http://127.0.0.1:8000/api/v1/freshness          # current | stale | refresh_failed
```

Safe to run repeatedly; a second concurrent run exits with "already running". Logs:
`data/bronze/crime/incremental_refresh_log.parquet` and `reconciliation_log.parquet`.

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
- A neighborhood figure is always the portion inside Ward 20, never a whole community area.
- Do not infer causation, nationality, or immigration status from crime records.
