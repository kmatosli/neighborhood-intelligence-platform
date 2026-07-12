# Data Flow

The nine steps between an official API and a published number. Status is marked per step.
Only steps 1–4 exist today.

## 1. Metadata validation — before extraction · BUILT

Fetch the dataset's metadata endpoint and confirm every column the project depends on is
still published. This runs *before* any data request, so a dataset that has been
restructured fails immediately instead of silently ingesting a changed shape.

A missing column is **blocking**. For crime, that includes `latitude` and `longitude`:
individual records may lack coordinates, but the dataset must still offer the columns.

Implemented by `missing_required_fields()` against the metadata endpoint.

## 2. API request · BUILT

Query the resource endpoint with an explicit `$limit`, `$order`, and optional `$where`.
Requests carry an app token when one is configured, retry with exponential backoff on
timeouts and transport errors, and raise `ChicagoDataError` on anything unrecoverable.

Planned additions: paging for backfill, and `$where` windows driven by `updated_on`.

## 3. Raw preservation — Bronze · PARTIAL

Write the response exactly as received, before any cleaning. The raw payload is the
evidence trail; every downstream number must be traceable back to it.

Today `scripts/pull_crime_sample.py` writes a JSON sample to `data/bronze/`. Partitioned
Parquet with ingestion-run metadata is planned and not built.

## 4. Record validation · BUILT

Each record is checked against the core-field contract. Missing identity or analytical
fields (`id`, `date`, `primary_type`, and peers) are **blocking** — the run fails rather
than publishing records that cannot be identified or counted.

Implemented by `missing_core_fields()`.

## 5. Optional geography handling · BUILT (detection only)

Coordinates are checked separately from core fields. A record with no `latitude` or
`longitude` is **valid** and produces a **warning**, not a failure. The count of such
records is reported.

These records stay in the raw and normalized layers. They are excluded from exact spatial
analysis, and any map or neighborhood-level figure must disclose how many records were
excluded for this reason.

Implemented by `missing_coordinates()`. Downstream exclusion logic is not built.

## 6. Normalization — Silver · NOT BUILT

Cast types (dates to timestamps, `arrest`/`domestic` to booleans, coordinates to floats),
deduplicate on `id`, apply corrections by keeping the record with the newest `updated_on`,
and conform crime groupings using a documented, configurable mapping.

Source field names and values are preserved alongside normalized ones.

## 7. Spatial assignment · BUILT (Bronzeville blocked)

Point-in-polygon against the official layers: community area, ward, police beat, police
district, census tract, and census block group. Woodlawn resolves from the official
community-area polygon.

**Bronzeville remains blocked**: it needs an approved custom GeoJSON, and until one exists
`neighborhood_bronzeville` is null on every record. No ward, beat, ZIP, or single community
area is used as a substitute.

Every record's outcome is an explicit status — `assigned`, `missing_coordinates`,
`invalid_coordinates`, `outside_chicago_boundaries`, `ambiguous_overlap`, or
`bronzeville_boundary_unavailable` — never a single generic null. Source-reported ward, beat,
district, and community area are preserved alongside the derived values and compared, with
mismatch flags.

Boundaries are **current**, so a historical incident is assigned to the geography it falls in
*today*. Each row records its `boundary_vintage`. Implemented by
`src/bw_observatory/geography/assign.py`.

## 8. Aggregation — Gold · NOT BUILT

Build the small set of tables the site actually reads: counts by neighborhood, period, and
crime group; trend directions; comparison baselines. Each aggregate carries its source
dataset, refresh timestamp, and the count of records excluded for missing geography.

## 9. Publication · NOT BUILT

A read-only API serves Gold tables to the public web application. No unrestricted refresh
endpoint is exposed. Every published statistic renders with its source and refresh date.

## Failure behavior

A failure at steps 1, 2, 4, or 6 aborts the run and leaves the last good data in place. A
refresh that returns zero rows, or whose latest date moves backward, is treated as a
failure — not as a legitimate empty result. See
[DATA_QUALITY.md](../methodology/DATA_QUALITY.md).
