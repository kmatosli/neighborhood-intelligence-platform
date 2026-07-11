# Project Status

**Phase.** Data foundation. The project has a verified, validated connection to the Chicago
crime dataset. It has **no stored data, no geography, no analysis, and no public site.**

Last updated: 2026-07-11.

## Completed

- Repository initialized; GitHub remote connected
- Python packaging configured — `src/` layout with a hatchling build backend, so
  `bw_observatory` is installed into the environment
  ([ADR-0001](architecture/ADR/ADR-0001-repository-and-python-layout.md))
- `uv` lock file committed
- Environment configuration via pydantic settings and `.env`
- Chicago Socrata client with retries and typed errors
  (`src/bw_observatory/clients/chicago_data.py`)
- **Chicago crime API metadata endpoint verified** against the live portal
- **Chicago crime API data endpoint verified** against the live portal
- **Schema validation separated from record-level validation**
  ([ADR-0003](architecture/ADR/ADR-0003-validation-levels.md))
- **Missing coordinates handled as warnings**, not blocking failures — a crime without
  coordinates is a real crime
- Sample crime pull script (JSON sample to `data/bronze/`)
- CI running Ruff, Ruff format, mypy (`strict`), and pytest
- **14 tests passing; Ruff passing; mypy passing**

## Next feature

**Historical crime ingestion from 2006 to present** — paged, restartable, writing raw Parquet
to the Bronze layer with a recorded refresh run. This is the current critical path; nearly
everything else depends on it.

Then, in order:

1. Incremental refresh using `updated_on` and `id`
2. Raw Parquet storage in the Bronze layer
3. Bronzeville boundary definition (**blocked** — needs approval,
   [ADR-0004](architecture/ADR/ADR-0004-neighborhood-boundary-strategy.md))
4. Woodlawn boundary ingestion
5. Point-in-polygon neighborhood assignment
6. Census and ACS ingestion
7. Election turnout ingestion
8. Event and policy calendar
9. Public web application

Full list in [../TODO.md](../TODO.md); prioritized breakdown in
[product/BACKLOG.md](product/BACKLOG.md).

## Blockers

- **Bronzeville boundary is not approved.** Blocks all geography work, and therefore the map,
  neighborhood trends, and most of the MVP. It must not be worked around with a ward, beat,
  ZIP, or single community area.

Open issues: [decisions/ISSUE_LOG.md](decisions/ISSUE_LOG.md).

## What cannot be claimed yet

No number from this repository should be cited as a finding about Bronzeville or Woodlawn.
No record has been assigned to a neighborhood, and no historical data has been ingested. See
[decisions/KNOWN_LIMITATIONS.md](decisions/KNOWN_LIMITATIONS.md).
