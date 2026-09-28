# City Services — Chicago 311 Service Requests

How NIP ingests, places, classifies and interprets Chicago's consolidated 311 data, and what the
resulting figures do and do not establish. Audited against the live source on **2026-09-27**.

Governance lives in `config/service_requests.yml`; this document explains it. Code:
`ingest/service_requests.py` (Bronze), `geography/service_requests.py` (Silver),
`presentation/city_services.py` (analysis), `api/routes/city_services.py`.

---

## 1. What these numbers measure

**Reported service requests.** Not the number of physical problems, and not how well the City
performs. Three different things, kept apart everywhere in the product:

| | What it is | Do we have it? |
|---|---|---|
| Reported requests | what residents and staff submitted to 311 | **yes** |
| Physical conditions | how many potholes actually exist | **no** — no condition survey exists |
| Service performance | whether the City responded well | **no** — closure is not repair, and there is no target to measure against |

Request volume moves with the underlying condition, but also with population, road network,
awareness of 311, access to it, reporting habits, duplicate submissions, organised reporting
drives, weather and administrative practice. A higher count is therefore **not** evidence of
worse service, and the product never says or implies that it is.

## 2. Source

| | |
|---|---|
| Dataset | 311 Service Requests, `v6vf-nfxy` |
| URL | https://data.cityofchicago.org/Service-Requests/311-Service-Requests/v6vf-nfxy |
| Rows | 14,729,538 |
| `created_date` span | 2018-07-01 → 2026-09-27 |
| Columns | 45 · 110 distinct `sr_type` |
| Retrieval | Socrata JSON API, 20,000 rows per page, ordered by `sr_number` |

Field names differ from what their descriptions suggest: the identifier is `sr_number`, the
category is `sr_type` with a stable `sr_short_code`, and the update timestamp is
`last_modified_date`. **There is no subtype field and no resolution/disposition code** — the
second absence is the single most consequential fact in this document (§7).

The portal's own `:@computed_region_*` spatial joins are deliberately not ingested: their layer
vintages are unstated, and this project places points against a boundary layer it downloaded and
can name.

## 3. Temporal scope: 2019 onward

The consolidated system launched **2018-12-18**. Analysis starts at **2019** because:

- 2018 holds 36,568 rows against ~1.8M in a full year — a partial half-year, not a comparable one.
- 31,443 rows are flagged `legacy_record`, migrated from the previous system on a different
  schema and taxonomy. They are ingested and retained, then excluded from analysis so that one
  series never spans two systems.

Annual volume since: 2019 1.76M · 2020 2.04M · 2021 1.83M · 2022 1.78M · 2023 1.78M · 2024 1.91M ·
2025 1.96M · 2026 YTD 1.62M.

## 4. Geography — spatial, never the source's ward

```
source record → valid coordinates? → point-in-polygon against the current Ward 20 polygon
              → Ward 20 analytical membership
```

The dataset carries its own `ward`, but that is the ward recorded when the request was created,
against whatever map was then in force. It is preserved as `source_ward` and **compared**, never
obeyed. Same for community area, ZIP, police district and beat.

Measured on the ingested Ward 20 data, source-reported and mapped ward disagree for **442
records in 2024, 389 in 2025 and 307 in 2026** — and community area for more (635 / 560 / 406).
Both disagreement counts are published on every report.

Derived fields: `spatial_ward_current`, `spatial_community_area`, `in_ward20`, plus
`ward_mismatch` and `community_area_mismatch`. Placement uses the same downloaded ward (2023) and
community-area (1920) layers the crime pipeline uses, and records their vintage on every row.

**Retrieval is pre-filtered by a bounding box around Ward 20** so that keeping a few hundred
thousand records does not require downloading 14.7M. That is a transport optimisation, not the
inclusion test: every retrieved record still has to pass point-in-polygon, and the box is
deliberately larger than the ward.

## 5. Coordinate quality

A record enters spatial analysis only with a verdict of `ok`. Otherwise it is retained, flagged,
and given a reason:

| Verdict | Meaning |
|---|---|
| `ok` | usable |
| `missing` | no latitude/longitude |
| `zero` | a zero coordinate, i.e. a null written as a number |
| `outside_chicago` | outside 41.60–42.10 N, −87.95 to −87.50 W |
| `repeated_default_point` | shares a coordinate with ≥1,000 other records, so it is a geocoding default rather than a location |

The last verdict exists because of a measured behaviour: `311 INFORMATION ONLY CALL` records are
geocoded to a single fixed point, and **one coordinate (41.871831, −87.679846) carries 2,029,501
records**. Placing those in a ward would invent an enormous false concentration.

**Known limitation.** Because retrieval filters on `within_box(location, …)`, records with no
coordinates are never retrieved, so coordinate-exclusion counts cannot be measured from the
current Bronze — every ingested row scores `ok`. Citywide, potholes missing coordinates are 2,006
of 507,569 (0.4%). A production ingest should make a second pass for null-coordinate records by
source ward and store them flagged as unplaceable; until then this gap is stated rather than
implied to be zero.

## 6. Information-only calls

`311 INFORMATION ONLY CALL` (`311IOC`) is **5,173,430 of 14,729,538 rows — 35% of the dataset**,
and the largest single `sr_type` by a wide margin. It records someone asking a question, not a
request for service at a place.

Treatment: **retained in Bronze with its original type**, flagged in Silver with
`analytical_inclusion = false` and `exclusion_reason = information_only_call`, and excluded from
every service-demand and geographic figure. Within the ingested Ward 20 box this removes 2,104
records in 2024, 2,040 in 2025 and 1,551 in 2026, each reported on the relevant response.

## 7. Closure semantics — audited per category

**No completion-time statistic is published for a category until its closure semantics have been
audited.** `config/service_requests.yml` holds the audit; a category absent from it returns no
duration, which is a real answer rather than a gap.

**Potholes (507,569 records citywide), audited 2026-09-27:**

| Status | Records | `closed_date` present |
|---|---|---|
| Completed | 492,763 | yes |
| Open | 13,993 | no |
| Canceled | 813 | **yes** |

`closed_date` is present on exactly 493,576 records = Completed + Canceled, and absent on every
Open row. Closure is recorded consistently — but a **cancellation also carries a closed date**, so
counting cancellations as completions would make the City look faster than it was. Duration is
computed from **Completed only**.

Duplicates are also excluded from duration: a duplicate closes when its parent is resolved, so
its interval measures the linkage rather than the work, and 31% of pothole records are duplicates
— easily enough to move a median.

**What "Completed" does not establish.** The source carries no resolution or disposition code, so
a filled pothole, a request the crew could not locate, a condition already repaired, and a
referral elsewhere are **indistinguishable**. Completion time measures when the City closed the
request. It is not evidence that a pothole was filled, and every duration figure carries that
sentence.

A closure timestamped before creation is treated as a source contradiction and excluded, not as a
negative duration.

## 8. Duplicates and linkage

Audited on potholes: **all 157,958 records flagged `duplicate` carry a `parent_sr_number`**, and
only 153 non-duplicates do — so the flag and the parent link agree, and either identifies a child
request.

Two counts are always published together, and neither is presented as "the" number:

- **Raw** — every submission, i.e. what residents actually sent.
- **Primary** — submissions not flagged as duplicates of another request.

For Ward 20 potholes in 2025 that is **807 raw / 550 primary** (32% duplicates).

Records are **never** collapsed by geographic proximity. Two requests at the same corner may be
two real conditions, and the source does not say otherwise. Repeated requests at one address are
reported as repeated *reporting* — which may be a duplicate, a new condition, or a resident
following up — and never as repeated service failure.

## 9. Bronze

Per-year Parquet at `bronze/service_requests/<year>.parquet`, following the crime pipeline's
conventions: 25 preserved source columns plus `source_dataset_id` and `ingested_at`, deterministic
column order, all values as strings so no source value is coerced or lost, deduplicated on
`sr_number`, written through a temp sibling and swapped atomically. A manifest
(`bronze/service_requests/manifest.parquet`) records rows, retrieval time, source watermark,
SHA-256 checksum and status per year.

## 10. Silver

`silver/service_requests/requests_with_geography/<year>.parquet`. Identifiers, classification
(`analytical_category`, `analytical_subcategory`, raw type and short code), parsed dates plus
month/day-of-week/hour, normalised status with `is_open`/`is_closed`, spatial placement and the
preserved source geography with mismatch flags, linkage (`is_explicit_duplicate`, `has_parent`,
`is_primary_request`), coordinate quality, and the governance pair
`analytical_inclusion` / `exclusion_reason`, plus boundary vintage and dataset provenance, and the
source-truth trio `source_status` / `source_last_seen` / `source_removed_at` (see §12).

Classification keys on `sr_short_code`, never on wording: one live type is still labelled
"Tree Trim Request (NO LONGER BEING ACCEPTED)" and continues to receive records. An unrecognised
code becomes `uncategorized` and keeps its raw type, so a new City category surfaces as
unrecognised instead of silently inflating an existing figure.

## 11. Refresh

Incremental, on the source's `last_modified_date` watermark: read the newest stored value, request
only rows modified after it, upsert by `sr_number`, rewrite the manifest checksum, and publish
atomically. Idempotent — a second run with nothing new leaves the partition byte-identical — and
the watermark advances only on a successful write. Verified by test.

**No scheduler is enabled**, in production or locally. The implementation is scheduler-ready;
activation requires separate authorisation.

## 12. Reconciliation

The watermark sees inserts and edits but cannot see a source *withdrawal*: a record the City has
removed has no timestamp left to fetch, so an incremental query can never return it. Reconciliation
(`src/bw_observatory/ingest/service_request_reconcile.py`) compares the local id set for a year
against the source's and records what it finds. It uses the same source-truth model as the crime
pipeline, deliberately — one model, two datasets:

- **Nothing is deleted.** A withdrawn request stays in Bronze verbatim and in Silver with its
  geography. Silver's `source_status` becomes `source_removed`, `source_removed_at` holds the
  *first* time that was observed (a later run does not restamp it), and `source_last_seen` keeps
  the last instant the source actually returned the row rather than being overwritten with a lie.
- **Published figures use the current official view.** `current_source_view` excludes
  `source_removed` rows from every count, share, duration and monthly series. A partition written
  before reconciliation existed has no such column and is used whole.
- **A request that reappears returns to `active_in_source`**, and its removal stamp is cleared.
- **The comparison window matches the ingest filter exactly** — the same Ward 20 bounding box and
  the same half-open year range. Widening it would report every record elsewhere in Chicago as
  missing locally; narrowing it would report records we correctly hold as withdrawn.
- **Ids present upstream but absent locally are a refresh gap, not a withdrawal**, and are logged
  separately (`missing_locally`, with a sample) rather than silently.
- **One writer at a time.** The run takes the Bronze directory's refresh lock, so it can never
  interleave with an upsert of the same partition, and Silver is rewritten batch by batch through
  a temp sibling that is swapped only on success.

Every run appends to `bronze/service_requests/reconciliation_log.parquet`: run id, year, local and
source row counts, confirmed active, newly removed, still removed, reappeared, missing locally,
duration, dry-run flag, status and error. `--dry-run` compares and reports without writing.

Default scope is the two newest years, where edits and withdrawals concentrate; a year costs a
handful of id-only requests (ids are a fraction of the row payload), which is cheap enough to run
monthly. Withdrawal counts are **not yet measured against the live source** — no reconciliation run
has been performed, so this document states no figure for how many records the City withdraws.

One case this does not resolve, and does not pretend to: a record whose `created_date` the City
edits across a year boundary leaves the window of the year it was filed under. It is counted as
removed from that year and missing from the other — both correct — but the log shows two entries
rather than one move. `missing_ids_sample` is what makes that visible.

## 12a. Commands

```powershell
uv run python scripts/ingest_service_requests.py --year 2024 --backfill     # fetch a year whole
uv run python scripts/ingest_service_requests.py                            # refresh newest years
uv run python scripts/ingest_service_requests.py --enrich-only --year 2025   # rebuild Silver only
uv run python scripts/reconcile_service_requests.py --dry-run                # compare, write nothing
uv run python scripts/reconcile_service_requests.py --year 2025 --year 2026  # mark withdrawals
```

Both are thin wrappers over `bw_observatory.ops.*`, so a scheduler would run identical code. No
311 scheduler exists in production or locally; activation requires separate authorisation.

## 13. Pothole classification

Two codes, counted separately as well as together because they concern different assets and would
need different exposure measures to compare fairly:

- `PHF` — Pothole in Street Complaint (426,745 citywide)
- `PHB` — Alley Pothole Complaint (80,830 citywide)

Ward 20, mapped spatially, analytically included: **1,010 (2024) · 807 (2025) · 828 (2026 YTD)**.
2025 splits 709 street / 98 alley.

## 14. Statistical treatment

- **Comparable periods.** A partial year is compared with the same month and day of the prior
  year, never with a completed year. Date windows are inclusive of the final day, because
  `created_at` carries a time of day.
- **Distributions, not means.** Completion times are strongly skewed — Ward 20 potholes in 2025:
  median 5.0 days, p25 0.0, p75 46.0, p90 132.2 — so median and quartiles are published and a
  bare mean is not.
- **No denominator is invented.** Potholes would need street mileage or roadway-network exposure
  to become a rate. The City's street centre-line layer has no working API export, so none is
  ingested and figures are labelled **request counts, not service-condition rates**.
- **No rankings.** Areas are not ordered as better or worse served. Portion rows carry each
  area's share of the ward's land so a reader can see that a larger area producing more requests
  is not, by itself, news.
- **Reconciliation.** Monthly and status subtotals sum to the published total; raw = primary +
  duplicates. Asserted by test.

## 15. Known data-quality issues

1. Coordinate-less records are absent from Bronze because of the bounding-box pre-filter (§5).
2. `sr_type` wording drifts; `sr_short_code` is the stable key.
3. One live type is labelled "NO LONGER BEING ACCEPTED" yet still receives records.
4. Legacy (pre-2019) rows use a different schema and taxonomy and are excluded from analysis.
5. Status carries a single `Closed` row against 14.2M `Completed`; it is normalised to closed.
6. No resolution code exists, so closure is not repair (§7).
7. `uncategorized` is the largest bucket in Ward 20 (8,163 records in 2025) because only eight
   categories are defined so far — visible by design, not hidden.
8. Only **potholes** has audited closure semantics; every other category is ingested and
   queryable but publishes no completion statistic.

## 16. Interpretation guardrails

Required wherever a City Services figure appears:

- These are **reported requests**, not a count of conditions and not a measure of City performance.
- Ward membership is decided by placing the published coordinates in the current Ward 20
  boundary, never by the ward recorded on the request.
- Raw and primary counts mean different things; both are shown.
- A closure means the request was closed, not that the condition was repaired.
- Without a street-mileage denominator these are counts, not rates, and areas are not ranked.
- A period near the edge of the data is provisional and its counts will rise.
