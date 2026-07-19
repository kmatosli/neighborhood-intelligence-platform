# ADR-0003 — Validation levels

**Status.** Accepted
**Date.** 2026-07-11

## Context

The original validation treated a single set of required fields as mandatory for both the
dataset schema and every individual record. A record missing any required field failed the
run.

This blocked on real, valid data. The live check against `ijzp-q8t2` failed with:

```
BLOCKING: invalid record shapes: [{'index': 0, 'missing': ['latitude', 'longitude']}]
```

One record in ten had no coordinates. That is not corruption — Chicago publishes incidents
without coordinates routinely (ungeocoded or withheld locations), and Socrata omits null
fields from its JSON entirely. The pipeline was rejecting crimes that genuinely happened.

The naive fix — drop coordinates from the required set — would have been worse: if the city
ever stopped publishing the `latitude` column at all, the project would silently lose every
map and neighborhood figure with no error at all.

The two failures look identical to a flat required-fields check, and must not be.

## Decision

Four validation levels, with severity attached to each.

1. **Schema validation** — source columns and types. **Blocking.** Runs against the metadata
   endpoint *before* extraction. `latitude` and `longitude` remain required **columns**.
2. **Record validation** — identity and analytical fields (`id`, `case_number`, `date`,
   `iucr`, `primary_type`, `arrest`, `domestic`, `year`, `updated_on`). **Blocking.** A
   null value counts as missing.
3. **Analytic validation** — missing coordinates or partial geography. **Warning.** The
   record is kept and counted; it is excluded from exact spatial analysis, and the excluded
   count is disclosed.
4. **Quality reporting** — completeness, timeliness, duplicates, unexpected change.
   **Reported publicly.**

Fields outside the core set (`block`, `description`, `location_description`, `ward`,
`community_area`, …) are nullable in the source and are not blocking.

Levels 1–3 are implemented in `src/bw_observatory/validation/crime_schema.py`. Level 4 is
not built.

## Consequences

- The live API check passes and reports `WARNING: 1 of 10 records have no
  latitude/longitude` instead of failing.
- Records without coordinates are counted in totals and excluded from maps — the honest
  handling, provided the exclusion count is published.
- A genuine schema break still fails loudly and immediately.
- Every geography-dependent figure now owes the reader an exclusion count. This is a
  requirement on the presentation layer, not just the pipeline.
- More concepts to hold: contributors must know which level a new field belongs to. The
  table in [VALIDATION.md](../VALIDATION.md) exists to make that decision quick.

## Alternatives considered

**Keep one flat required-field list.** Rejected: it blocks on valid records, which is what
broke the check.

**Drop coordinates from the required set entirely.** Rejected: a schema break — the city
removing the column — would then pass silently, which is the more dangerous failure.

**Accept records with missing coordinates and impute a neighborhood from `beat`, `ward`, or
`community_area`.** Rejected: it would fabricate a spatial precision the data does not have,
and for Bronzeville specifically no such proxy is valid. See
[GIS_STRATEGY.md](../GIS_STRATEGY.md).

**Warn on missing core fields instead of blocking.** Rejected: a record with no `id` or no
`date` cannot be deduplicated, corrected, or counted in a time series. Publishing numbers
built on such records would be worse than failing.
