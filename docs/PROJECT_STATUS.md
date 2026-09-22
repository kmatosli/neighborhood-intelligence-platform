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

## V2 work packages

The sections above describe the data-foundation phase and are retained as history. Since then
the API (`bw_observatory.api`) and the web app (`apps/web`) were built and deployed as a
development preview (Render backend + Vercel frontend), with Bronze and Silver 2006–2026 on the
production disk. Version 2 proceeds in numbered work packages.

- **V2-001 — Global navigation, year context, and mobile foundation.** Completed
  2026-09-12 (local; not yet committed or deployed).
  - One canonical year authority: the URL's `?year`, validated at the root route and retained
    across navigation (`apps/web/src/lib/useYear.ts`, `apps/web/src/routes/__root.tsx`). The
    year list comes from `/api/v1/years`; no year is hardcoded. Invalid or missing years fall
    back to the latest enriched year.
  - Shared `YearControl` in the shell (`apps/web/src/components/YearControl.tsx`), shown only
    on routes that consume year, with explicit loading / unavailable / empty states.
  - Mobile-first shell and question-oriented navigation (`apps/web/src/components/WireShell.tsx`):
    stacked nav on phones, wrapping tab bar from `sm`, 44px tap targets, visible focus, no
    horizontal overflow verified at 320/375/430px and at 640px (≈200% zoom).
  - Shared coming-soon / not-connected presentation (`apps/web/src/components/Pending.tsx`) and
    page-question header (`apps/web/src/components/QuestionHeader.tsx`) replace per-page copies;
    wording and caveats preserved.
  - Not in this package (flagged for later packages): public Lovable metadata/branding in
    `apps/web/src/routes/__root.tsx`, product naming, the methodology/trust layer, Ward 20
    scope and neighborhood breakdowns.

- **V2-002 — Ward 20 geography foundation.** Completed 2026-09-12 (local; not committed or
  deployed). See ADR-0005 and `docs/methodology/GEOGRAPHY.md`.
  - Product scope is now exclusively **Ward 20**: `ward20` is the default geography; the
    portions of Woodlawn, Washington Park, Englewood, Fuller Park and New City inside the
    ward are selectable; Back of the Yards is listed as pending a validated boundary.
  - One geography authority per side: `config/geographies.yml` +
    `src/bw_observatory/presentation/geography.py` (filter on `spatial_ward_current` /
    `spatial_community_area`); `apps/web/src/lib/useGeography.ts` (URL `?geo=`, alongside
    `?year=`). New `GET /api/v1/geographies`. Unknown/pending ids are 404 with the reason.
  - Bronzeville removed from public identity, copy and application geography; pipeline
    history, ADR-0004 and Silver columns retained. Lovable metadata removed; working public
    identity "Ward 20 Neighborhood Intelligence"; SVG favicon.
  - Tests: 172 passing (`tests/test_geographies_api.py` added). Browser matrix 41/41.
  - Pending: final product name; `pyproject.toml` name/description unchanged on purpose.

- **V2-002A — Ward 20 geography gaps closed.** Completed 2026-09-13 (local; not committed
  or deployed).
  - Ingested the City's *Boundaries - Neighborhoods* shapefile (`9wp7-iasj`, Office of
    Tourism) as a **secondary** reference layer with manifest/checksums. Finding: it has no
    Back of the Yards feature; the two polygons carrying that name as a secondary label are
    geometrically identical to community areas 61 and 37. **Back of the Yards stays pending**
    with that reason recorded (`config/geographies.yml` → `evaluated_source`).
  - Explicit geography types (`ward`, `community_area_portion`, `neighborhood_portion`) in
    the registry, API provenance and catalog (`boundary_system`, `boundary_source`).
  - Reusable, documented intersection measurement (`geography/ward_coverage.py`,
    `scripts/measure_ward_coverage.py`, EPSG:3435): all nine intersecting community areas
    measured; the four non-selectable ones disclosed with sq mi and both shares — no UI change.
  - Coverage/double-counting invariants tested (ward total independent of drilldowns;
    drilldowns clipped; overlaps cannot alter the ward; pending never zero). 183 tests pass.
  - Deleted the unlinked Lovable-era `apps/web/public/favicon.ico` (approved).
  - **Revised product decision (2026-09-13, same day):** all nine intersecting community areas
    are drilldowns, small portions included, because the drilldowns serve geographic equity
    analysis and hiding small portions could conceal disproportionate patterns. Selector
    labels "X (part in Ward 20)", headings and every generated sentence say "the Ward 20 part
    of X"; the scope note states the portion's measured size (no suppression rule). Ward total
    still computed from the ward polygon alone. "Current Ward 20 footprint" methodology kept
    and documented; intended equity questions documented (not built). 184 tests pass;
    browser matrix 26/26.

- **V2-003 — Equity & accountability data readiness audit.** Completed 2026-09-14 (documentation
  only; no analytics built). Deliverable: `docs/data/WARD20_EQUITY_DATA_READINESS.md`, with
  the reproducible source table `docs/data/source_readiness_2026-09-14.json`
  (`scripts/audit_source_readiness.py`, `src/bw_observatory/audit/source_readiness.py`).
  - In the repo: crime only (Bronze/Silver 2006–2026, local copy through 2026-07-02; no
    incremental refresh) plus boundary layers. **Nothing** for 311, Census attributes,
    TIF/investment, parcels, streets.
  - Key findings: the 311 dataset (`v6vf-nfxy`, 2018-12 onward) is 99.9 % geocoded but its
    `ward` field is the ward at creation time (≈77 % of pre-2023 "ward 20" rows are in today's
    polygon) — Ward 20 filtering must be point-in-polygon; completion semantics vary by
    category; Census API now requires a key (`CENSUS_API_KEY`); 2020 block groups straddle the
    ward (13 of 92 fully inside) so blocks are the denominator path; 76 % of Ward 20 area lies
    in active TIF districts; no authoritative menu-money dataset exists.
  - **Selected next package: V2-004 — 311 service requests (denominator-free request →
    response → completion measures for Ward 20 and the nine portions).** Not started.
  - Environment note (2026-09-14): Windows Application Control began blocking
    `pyogrio/_io.pyd`; `geopandas.read_file` fails, so 2 pipeline tests in
    `tests/test_geography.py` and the geography download/measure scripts fail on this machine
    until the policy is fixed. Not a repo defect; 182/184 tests otherwise pass.

- **V2-004 — Crime refresh reliability and currentness.** Completed 2026-09-14 (local; not
  committed or pushed). Re-scoped from the requested "311 refresh" once the repo showed the
  app holds **no** 311 data (V2-003 stands); the dataset that had stopped in July was crime
  (Bronze 2026 max `date` 2026-07-03, last pulled 2026-07-11).
  - Why it stopped: the only loader was the whole-year downloader; nothing re-ran it. There
    was no watermark and no incremental path.
  - Built: `src/bw_observatory/ingest/crime_refresh.py` + `scripts/refresh_crime.py`
    (`--dry-run`, `--since`). Watermark on the source's `updated_on` (verified: stamped on
    insert and on every later edit, never null, one batch/day ≈15:45 UTC, seven-day lag);
    upsert by `id` into the year partition of the record's `date` (cross-year moves handled);
    manifest checksum rewritten so `bronze_integrity_verified` stays truthful; PIP enrichment
    of only new/changed rows with the existing `GeographyAssigner`; quality row recomputed;
    per-year local-vs-source row reconciliation (exposes deletions, which a watermark cannot
    see); rich `incremental_refresh_log.parquet`; atomic file swaps; watermark advances only
    on success. Also repairs a Silver partition that drifted from Bronze (found on 2024: 18
    Bronze ids without Silver rows, 1 orphan Silver row, from the 2026-07-26 Bronze restore
    that was never re-enriched).
  - Fallback watermark with no prior refresh = the **minimum** over year partitions of each
    partition's max `updated_on` (a disk-wide max would have skipped 2026-07-10 → 07-25 in
    every year but 2024).
  - `ChicagoDataClient.count_crimes()` added for reconciliation. 15 new tests
    (`tests/test_crime_refresh.py`).
  - Manual command: `uv run python scripts/refresh_crime.py`. Recommended cadence: daily,
    after ~16:00 UTC. Not scheduled anywhere yet (see "Automation" below).
  - Known limits: source deletions show as negative drift and need a `--force` year re-pull;
    the OneDrive-synced working tree can stall a file swap for minutes (seen on 2017).
  - Next data package remains **V2-005 — 311 service requests**, exactly as V2-003 selected.
    Not started.
  - Checkpoint commit `9eeb19f` (local, 2026-09-15; not pushed).

- **V2-004A — Crime production freshness, automation, and source reconciliation.**
  Completed locally 2026-09-15 (not committed, not pushed, nothing deployed or scheduled).
  Operating model: `docs/methodology/CRIME_DATA_OPERATING_MODEL.md`.
  - Invariants (`ingest/partitions.py::partition_problems`) proved after every publish:
    unique ids on both layers, identical id sets, manifest rows + checksum match the file.
    Bronze and Silver for a year are staged together and swapped back to back; failed
    staging is discarded; the 2024 Silver drift class is detected and repaired every run.
  - Bounded memory: all partition I/O streams in 20 000-row batches; files repacked into
    20 000-row groups (`ops.repack_crime`, one-time). Refresh ≈ 390 MB peak, reconcile
    ≈ 320 MB — the API alone peaks ≈ 500 MB under load, so both do **not** fit a 512 MB
    Starter instance together (owner decision, see the operating model).
  - Source-truth model: Silver `source_status` / `source_last_seen` / `source_removed_at`;
    `ops.reconcile_crime` lists source ids per year and marks removals (never deletes);
    `presentation.overview.current_source_view` excludes `source_removed` rows from every
    figure. First reconciliation (2026-09-15): 210 removed rows across 2017–2026 (5 inside
    Ward 20), 0 missing locally, 0 reappeared; older years reconciled with 0 removals.
  - Concurrency: `ingest/refresh_lock.py` (O_EXCL lock file, dead-pid/6 h stale takeover);
    CLIs exit 3 when a run is active.
  - Health: `/api/v1/freshness` (`ingest/freshness.py`): current / stale (48 h or > 11
    days behind) / refresh_failed / never_refreshed, with the full run bookkeeping.
  - Scheduling: `ops/scheduler.py` inside the API process (a Render disk is reachable only
    by its own service — cron/one-off jobs cannot see it), subprocess-based, off unless
    `BW_REFRESH_SCHEDULE` is set; monthly reconciliation on `BW_RECONCILE_DAY`.
  - `last_refresh` provenance now = last successful refresh run (log), not the year file's
    write time. `pyarrow.*` added to the mypy untyped-import override.
  - Tests: 30 new in `tests/test_crime_operations.py` (suite 229 → see report).

- **Release checkpoint 2026-09-21 (local commits; nothing pushed, deployed, or scheduled).**
  Recovery found nothing changed since 2026-09-15: local data through 2026-09-06, watermark
  2026-09-13; production still V1 (`main` @ `502c351`) with data through 2026-07-02, at
  `https://neighborhood-intelligence-platform.onrender.com` behind
  `bronzeville-woodlawn-observatory.vercel.app` (Vercel is CLI-deployed, no Git link). Full
  suite 230 passed, ruff and mypy clean. The V2 work was committed as four selective commits
  on `feature/research-platform`: V2-001–003 foundation, V2-004A freshness, deployment
  tooling, documentation. Release safety added with the deployment commit:
  `scripts/build_data_release.py --output/--overwrite` (never clobbers the previous
  release's archive; writes a `.sha256` sidecar) and `bw_observatory.ops.verify_data_root`
  (bounded-memory proof of a staged data root before activation). Production publication
  is now a versioned release root beside the live July one (`/var/data/bw-release-YYYYMMDD`;
  production was found on 2026-09-21 to be already versioned at `bw-release-20260726`) with
  `BW_DATA_DIR=/var/data/current` as an atomically renamed symlink and a same-mechanism
  rollback — `docs/render-data-deployment.md`. Open owner decisions: push/merge; instance
  size before `BW_REFRESH_SCHEDULE` (Starter + scheduler = catch-up crash loop, see the
  operating model); the Render SSH/transfer path; the one-time `BW_DATA_DIR` change.

## Next feature

~~**Incremental refresh using `updated_on` and `id`**~~ — done in V2-004 (2026-09-14);
`scripts/refresh_crime.py`.

Then, in order:

1. Daily automated refresh — **V2-004A built it** (in-process scheduler, off until
   `BW_REFRESH_SCHEDULE` is set); what remains is the instance-size decision and setting
   the env var. Earlier note (V2-004): the manual command is
   idempotent and restartable, so scheduling is a wrapper, not new logic. Still required
   for production: (a) a place to run it with write access to the Render disk (`/var/data`)
   — a Render cron job on the same disk, or run on the API service via `render` shell —
   since the API itself is read-only by design; (b) `CHICAGO_DATA_APP_TOKEN` for headroom
   (the run works anonymously today); (c) an alert on `status = failed` or non-zero drift
   in `incremental_refresh_log.parquet`; (d) a decision on whether the API should cache
   nothing across a refresh (today it reads Parquet per request, so a refresh is visible
   immediately — keep it that way).
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
