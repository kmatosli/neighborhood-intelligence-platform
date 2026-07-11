# Project Status

**Phase.** Data foundation. The project can ingest historical Chicago crime data into the
Bronze layer. It has **no geography, no analysis, and no public site.**

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
- **Historical crime ingestion (Feature 0002)** — `scripts/download_crime_history.py` pages
  through one calendar year at a time, retries on transport errors, resumes after
  interruption, and writes raw Parquet to `data/bronze/crime/`:
  - Year-partitioned files (`2024.parquet`, …), `manifest.parquet`, `refresh_log.parquet`
  - Schema validated against the metadata endpoint **before** any download
  - Records never silently discarded; row counts reconciled before a year is marked complete
  - Every source field preserved verbatim, including `ward`, `beat`, `district`,
    `community_area`, `latitude`, and `longitude` for later GIS assignment
  - Verified live: **2024 ingested — 259,191 records, 6 pages, ~49s, 0 duplicates**
- Retry defect fixed in the Chicago client — timeouts and transport errors were wrapped in
  `ChicagoDataError` *inside* the retried call, so tenacity never saw them and no retry had
  ever fired
- Logging to `logs/download.log`, `logs/api.log`, `logs/validation.log`
- **Reusable ingestion framework (Feature 0002A)** — `BaseDownloader` and
  `BaseBronzeWriter` hold everything a second dataset would otherwise duplicate (schema
  gate, paging, resume, row reconciliation, manifest, refresh log). `CrimeDownloader` is the
  only implementation; no other dataset is ingested yet
- **Dataset catalog** — `data/reference/dataset_catalog.parquet`, one row per dataset, with
  a `schema_version` fingerprint and an `active`/`blocked` trust status
- CI running Ruff, Ruff format, mypy (`strict`), and pytest
- **42 tests passing; Ruff passing; mypy passing**

## Next feature

**Incremental refresh using `updated_on` and `id`** — so that corrections the city publishes
after the fact are picked up, rather than the Bronze layer freezing at whatever the backfill
happened to see.

Then, in order:

1. Daily automated refresh
2. Bronzeville boundary definition (**blocked** — needs approval,
   [ADR-0004](architecture/ADR/ADR-0004-neighborhood-boundary-strategy.md))
3. Woodlawn boundary ingestion
4. Point-in-polygon neighborhood assignment
5. Silver normalization (typing, dedup, corrections, crime groupings)
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
Raw citywide records can now be ingested, but **no record has been assigned to a
neighborhood** — there are no boundaries yet, and ingestion deliberately does no geographic
filtering. Ward 3 and Ward 20 are political and voting geography; they are **not** stand-ins
for Bronzeville or Woodlawn. See
[decisions/KNOWN_LIMITATIONS.md](decisions/KNOWN_LIMITATIONS.md).
