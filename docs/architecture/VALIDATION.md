# Validation

Validation has four levels. The distinction that matters most: **a dataset losing a column
is not the same failure as a record lacking a value.** Conflating the two either blocks
valid data or lets broken data through.

## Level 1 — Schema validation

**Checks.** The source dataset still publishes every column the project depends on, with
the expected types.
**Runs.** Before any data is requested, against the metadata endpoint.
**Severity.** **Blocking.** The run aborts. Prior good data is left untouched.

If the city restructures a dataset, we fail loudly rather than ingest a changed shape.

Implemented: `missing_required_fields()` in `src/bw_observatory/validation/crime_schema.py`.

## Level 2 — Record validation

**Checks.** Each record carries the fields required to identify and analyze it.
**Runs.** On every record, after extraction.
**Severity.** **Blocking.** A record missing a core field means the pipeline cannot count
or identify an incident, which makes every downstream number suspect.

For crime, core fields are: `id`, `case_number`, `date`, `iucr`, `primary_type`, `arrest`,
`domestic`, `year`, `updated_on`.

A field present but null counts as missing.

Implemented: `missing_core_fields()`.

## Level 3 — Analytic validation

**Checks.** Fields needed for *some* analyses but not for the record's validity — chiefly
coordinates and partial geography.
**Runs.** On every record.
**Severity.** **Warning.** The record is kept. The count of affected records is reported.

A crime with no coordinates is a real crime and must still be counted in totals. It simply
cannot be mapped or assigned to a neighborhood by point-in-polygon. Any figure that depends
on geography must disclose how many records were excluded.

Implemented: `missing_coordinates()`.

## Level 4 — Quality reporting

**Checks.** Completeness, timeliness, duplicate rates, row-count collapse, schema drift,
and unexpected changes between refreshes.
**Runs.** Per refresh, across runs.
**Severity.** **Reported publicly** on the Data Health page. Some conditions (row-count
collapse, latest date moving backward) also block publication of a refresh.

Detailed in [DATA_QUALITY.md](../methodology/DATA_QUALITY.md). Not built.

---

## The crime dataset, concretely

| Condition | Level | Severity |
| --- | --- | --- |
| Dataset stops publishing the `latitude` column | 1 | **Blocking** |
| Dataset stops publishing the `longitude` column | 1 | **Blocking** |
| Record missing `id` | 2 | **Blocking** |
| Record missing `date` | 2 | **Blocking** |
| Record missing `primary_type` | 2 | **Blocking** |
| Record missing `latitude` | 3 | **Warning** |
| Record missing `longitude` | 3 | **Warning** |
| Refresh returns zero rows | 4 | **Blocking** |
| Duplicate `id` values within a refresh | 4 | Reported |

The two coordinate rows are the crux: the **column** disappearing is a schema break; a
**record** lacking a coordinate is normal in Chicago's published data and happens on a
meaningful share of incidents.

## Rationale

Recorded in [ADR-0003](ADR/ADR-0003-validation-levels.md).
