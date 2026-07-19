# Roadmap

Phases, not dates. Each phase is only "done" when its quality gates pass and
[PROJECT_STATUS.md](../PROJECT_STATUS.md) reflects it.

## Phase 1 — Source connection and validation · **In progress**

Establish a trustworthy connection to the City of Chicago crime dataset before anything is
built on top of it.

- [x] Chicago Socrata client with retries and typed errors
- [x] Metadata schema validation (blocking)
- [x] Record validation split from schema validation
- [x] Coordinates handled as warnings, not failures
- [x] Live API check passing; Ruff, mypy, and 14 tests green
- [ ] Historical ingestion from 2006 to present (restartable, paged)
- [ ] Incremental refresh using `updated_on` and `id`
- [ ] Raw Parquet storage in Bronze
- [ ] Refresh-run recording and failure semantics

## Phase 2 — Geography · **Blocked**

Blocked on the Bronzeville boundary being approved
([ADR-0004](../architecture/ADR/ADR-0004-neighborhood-boundary-strategy.md)). No
neighborhood figure may be published before this lands.

- [ ] Woodlawn official community-area polygon ingested
- [ ] Bronzeville custom GeoJSON drafted, reviewed, approved, versioned
- [ ] Point-in-polygon assignment
- [ ] Excluded-record (no-coordinate) accounting on every spatial figure

## Phase 3 — Analytical layer

- [ ] Silver normalization: typing, dedup on `id`, corrections by newest `updated_on`
- [ ] Configurable, documented crime groupings
- [ ] Gold aggregates: trends by neighborhood, period, and group
- [ ] Data-quality metrics computed per refresh

## Phase 4 — Context

- [ ] Census and ACS ingestion
- [ ] Election turnout ingestion
- [ ] Event and policy calendar
- [ ] Accountability mapping and public-commitment tracking

## Phase 5 — Public application

- [ ] Read-only API over Gold
- [ ] MVP pages (see [PRD.md](PRD.md))
- [ ] Printable Beat Meeting Brief
- [ ] Plain-language methodology at a fourth-to-sixth-grade reading level
- [ ] Data Health page

## Sequencing rules

- Nothing is published from a layer that has not passed its validation gates.
- Geography blocks the map, neighborhood trends, and most of the MVP. Do not route around
  it with a ward, beat, ZIP, or single community area.
- The Data Health page ships **with** the first public numbers, not after them.
