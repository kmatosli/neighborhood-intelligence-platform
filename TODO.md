# TODO

Working checklist for the Bronzeville–Woodlawn Observatory. Status here is the source of
truth for "what actually runs today." See [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md)
for the narrative version and [docs/product/BACKLOG.md](docs/product/BACKLOG.md) for the
prioritized epic breakdown.

## Completed

- [x] Repository initialized
- [x] GitHub remote connected
- [x] Python packaging configured (`src/` layout, hatchling build backend)
- [x] uv lock file committed
- [x] Chicago Crime API metadata endpoint verified
- [x] Chicago Crime API data endpoint verified
- [x] Schema validation separated from record-level validation
- [x] Missing coordinates handled as warnings, not blocking failures
- [x] **Historical crime ingestion from 2006 to present** — paged, retried, restartable
      (`scripts/download_crime_history.py`)
- [x] **Raw Parquet storage in the Bronze layer** — one file per calendar year, plus
      `manifest.parquet` and `refresh_log.parquet`
- [x] Retry defect fixed — timeouts were being wrapped before tenacity could see them, so
      retries had never actually fired
- [x] **Reusable ingestion framework** — `BaseDownloader` / `BaseBronzeWriter`, with
      `CrimeDownloader` as the first implementation
- [x] **Dataset catalog** — `data/reference/dataset_catalog.parquet`
- [x] 42 tests passing
- [x] Ruff passing
- [x] mypy passing

## Next

Ordered roughly by dependency. Nothing below has been started.

- [ ] Incremental refresh using `updated_on` and `id`
- [ ] Daily automated refresh
- [ ] Bronzeville boundary definition (custom GeoJSON, requires approval)
- [ ] Woodlawn boundary ingestion (official community-area polygon)
- [ ] Point-in-polygon neighborhood assignment
- [ ] Census and ACS ingestion
- [ ] Election turnout ingestion
- [ ] Event and policy calendar
- [ ] Public web application

## Notes

- The first four "Next" items are the current critical path. Geography is blocked on the
  Bronzeville boundary being approved — see
  [ADR-0004](docs/architecture/ADR/ADR-0004-neighborhood-boundary-strategy.md).
- Known blockers and environment quirks live in
  [docs/decisions/ISSUE_LOG.md](docs/decisions/ISSUE_LOG.md).
