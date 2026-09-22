# Crime data operating model

_V2-004A, 2026-09-15. How the Ward 20 crime data stays current without anyone remembering
to run a command._

```
City of Chicago crime source (ijzp-q8t2)
        │  one batch/day ≈ 15:45 UTC; the most recent ~7 days are withheld
        ▼
DAILY incremental refresh            python -m bw_observatory.ops.refresh_crime
        │  updated_on ≥ watermark → upsert by id → Bronze
        ▼
Bronze  (verbatim source rows, one file per year, manifest + checksum)
        │  only new/changed rows are point-in-polygon enriched (current Ward 20 map)
        ▼
Silver  (spatial assignment + source_status provenance)
        │  invariants proved after every publish; row-count reconciliation vs source
        ▼
MONTHLY reconciliation               python -m bw_observatory.ops.reconcile_crime
        │  source id set vs local → source_removed marked, never deleted
        ▼
API     (reads Parquet per request; current view excludes source_removed rows)
        │  /api/v1/freshness: current | stale | refresh_failed
        ▼
UI      "Data through <date>" · "Last refreshed <date>"  (from provenance, not text)
```

## Daily: incremental source refresh

`bw_observatory.ops.refresh_crime` (also `scripts/refresh_crime.py`) fetches every record
whose source `updated_on` is at or after the last watermark, upserts it by `id` into the
Bronze year of its `date`, rewrites the manifest checksum, enriches only the new or
changed rows, and appends one row to `data/bronze/crime/incremental_refresh_log.parquet`.

Why `updated_on`: the portal stamps it on insert **and** on every later edit, it is never
null, and edits to existing incidents (arrest status, reclassification, relocated
coordinates) are ~20 % of a year's rows. A `date`-only pull would miss them.

Why 16:30 UTC: the source's daily batch lands around 15:45 UTC and is published on the
portal within the hour; half past four collects it the same day. Set
`BW_REFRESH_SCHEDULE=16:30` on the API service to turn the scheduler on.

Cost of a normal day: ~700 rows fetched, 15–60 s, ~400 MB peak in the refresh process.

## Monthly: current-source reconciliation

Incremental refresh cannot see a record the City *removes* — a removed row has no new
timestamp. The refresh reports the symptom (per-year `drift` = source rows − local rows);
`bw_observatory.ops.reconcile_crime` finds the rows. It lists the source's ids for a year
(id-only requests, ~1 % of the row payload, never a re-download), compares them with the
local partition, and rewrites Silver's provenance columns:

| Column | Meaning |
|---|---|
| `source_status` | `active_in_source` — returned by the source at `source_last_seen`; `source_removed` — a reconciliation found the id no longer returned. Nothing about *why*. |
| `source_last_seen` | Last instant the source returned the row (download, refresh, or reconciliation). |
| `source_removed_at` | First reconciliation that observed the removal; cleared if the id reappears. |

A year that has never been reconciled carries `active_in_source` on every row, dated to
its download. Bronze is never modified by reconciliation and no row is ever deleted.

Default scope: the two newest years plus any year the last refresh reported non-zero drift
for. Removals concentrate in recent months (first run, 2026-09-15: 149 in 2026, 42 in 2025,
≤ 7 per year further back), so monthly on the newest years, driven by the daily drift
signal for older ones, is proportionate. Scheduled on `BW_RECONCILE_DAY` (default 1) after
that day's refresh. Log: `data/bronze/crime/reconciliation_log.parquet`.

## Continuously: the API serves last-known-good data

- Every year file is rewritten to a temp sibling and swapped in atomically; Bronze and
  Silver for a year are swapped back to back, the manifest and quality rows follow at once.
- After every publish the partition invariants are proved: unique ids on both layers, the
  same id set on both, manifest row count and checksum matching the file. A run that cannot
  prove them fails, the watermark does not advance, and the next run repeats the work.
- The current analytical view (`presentation.overview.current_source_view`) excludes
  `source_removed` rows from every figure on every page.
- One writer at a time: `data/bronze/crime/refresh.lock`. A second refresh, or a
  reconciliation during a refresh, exits with code 3 ("already running"). A lock whose
  owner process is gone, or that is older than six hours, is taken over.
- Memory: Bronze and Silver are streamed in 20 000-row batches (`ingest/partitions.py`);
  no year is ever held whole. Files are written in 20 000-row groups so this stays true.

## UI: provenance, not text

`data_through` is the newest incident `date` in the requested year's records;
`last_refresh` is the end time of the last successful refresh run (before any refresh has
run, the year's download date). Both are computed per request from the data and the logs
(`presentation/overview.py`), never hardcoded.

## Health: `/api/v1/freshness`

| Status | Meaning |
|---|---|
| `current` | last refresh succeeded within 48 h and the newest incident is ≤ 11 days old |
| `stale` | no successful refresh for 48 h, **or** newest incident older than 7 (source lag) + 4 (grace) days |
| `refresh_failed` | the most recent run failed and nothing has succeeded since; the API keeps serving the previous data |
| `never_refreshed` | no refresh and no download recorded |

The payload also carries the watermark, data-through date, rows fetched / inserted /
updated / unchanged, missing-geography count, duration, per-year reconciliation drift, the
last reconciliation summary, and whether a run is in progress. Read-only; nothing here
triggers work.

## Failure: retain the previous data, surface the failure

A failed run leaves every live file as it was (staging is discarded), does not advance the
watermark, records the failure with its error in the log, and exits non-zero (1 blocked by
source or data, 2 usage, 3 lock held). The scheduler logs the exit code to the service log
and `/api/v1/freshness` reports `refresh_failed` until a run succeeds.

## Manual commands

Emergency / on-demand refresh (the normal freshness path):

```powershell
uv run python scripts/refresh_crime.py --dry-run   # report what would change, write nothing
uv run python scripts/refresh_crime.py             # apply
uv run python scripts/reconcile_crime.py --dry-run # compare ids, mark nothing
uv run python scripts/reconcile_crime.py           # mark source-removed rows
curl http://127.0.0.1:8000/api/v1/freshness        # health
```

Deliberate full-year recovery — **not** the freshness path. Use only to rebuild a year
whose file is lost or corrupt, then re-enrich it; the incremental refresh picks up from
there:

```powershell
uv run python scripts/download_crime_history.py --year 2026 --force
uv run python scripts/enrich_crime_geography.py --year 2026 --force
```

One-time after restoring or transferring legacy files (single-row-group Parquet):

```powershell
uv run python -m bw_observatory.ops.repack_crime
```

## Production scheduling

On Render a persistent disk is reachable **only** by the service it is attached to, at
runtime (render.com/docs/disks): not by a cron job, not by a one-off job, not by another
service. The API owns the disk, so the scheduler runs **inside the API process**
(`bw_observatory.ops.scheduler`, started from the FastAPI lifespan) and launches the same
CLI a person would run as a subprocess. It is off until `BW_REFRESH_SCHEDULE` is set.

| Env var | Default | Meaning |
|---|---|---|
| `BW_REFRESH_SCHEDULE` | unset (off) | `HH:MM` UTC daily refresh time; recommended `16:30` |
| `BW_RECONCILE_DAY` | `1` | day of month on which reconciliation follows the refresh |
| `BW_REFRESH_TIMEOUT_SECONDS` | `10800` | a run longer than this is killed and logged as failed |
| `CHICAGO_DATA_APP_TOKEN` | unset | Socrata app token; anonymous works today, a token buys rate-limit headroom |

If the process starts and the last successful refresh is more than 24 h old, one catch-up
run happens two minutes after start, so a deploy at the wrong time does not cost a day.

**Memory.** Measured 2026-09-15 (Windows, daily-sized delta): the API process idles at
~130 MB and peaks at ~500 MB under a burst of requests; a daily refresh peaks at ~390 MB;
reconciliation at ~320 MB. The production service is a Standard instance (1 CPU / 2 GB,
verified by the owner 2026-09-21), so the worst measured coincidence — API burst + refresh +
reconciliation ≈ 1.2 GB — fits with headroom; on the 512 MB Starter it would not have, and
the catch-up-after-restart rule above would have turned one memory kill into a restart
loop. Nothing is scheduled until `BW_REFRESH_SCHEDULE` is set deliberately, and the first
run after enabling it should be watched in the service log (`Scheduler:` lines and the
refresh CLI's own log) and confirmed by `/api/v1/freshness`.
