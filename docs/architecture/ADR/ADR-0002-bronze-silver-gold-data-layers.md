# ADR-0002 — Bronze / Silver / Gold data layers

**Status.** Accepted (layering); the layers themselves are **not built**
**Date.** 2026-07-11

## Context

This project publishes claims about crime and civic conditions in two real neighborhoods.
Residents, journalists, and officials must be able to trace any published number back to
the official record it came from. That requires keeping the city's data as published,
separately from anything the project derives from it.

The data also changes underneath us: Chicago corrects crime records after publication (the
`updated_on` field exists precisely for this), and the most recent ~7 days are incomplete.
A pipeline that cleans in place cannot reconstruct what a number looked like last month, or
show why it changed.

## Decision

Adopt three storage layers, plus a reference layer.

- **Bronze — raw, immutable.** Exactly what the API returned, unmodified, partitioned by
  ingestion run. No type casting, no deduplication, no renaming. This is the evidence trail.
- **Silver — normalized.** Typed, deduplicated on `id`, corrections resolved by newest
  `updated_on`, crime groupings applied from a documented and configurable mapping, source
  fields preserved alongside derived ones.
- **Gold — analytical.** The small set of aggregates the public site actually reads. Each
  carries its source dataset, refresh timestamp, and the count of records excluded for
  missing geography.
- **Reference** (`data/reference/`) — boundaries and lookup tables.

Directories exist (`data/bronze/`, `data/silver/`, `data/gold/`, `data/reference/`) and are
gitignored except for `.gitkeep`. Parquet is the intended format for Bronze and Silver.

## Consequences

- Any published figure can be traced to a raw record. Provenance is structural, not a
  convention someone has to remember.
- Reprocessing does not require re-fetching: a mapping change or a boundary change can be
  replayed from Bronze.
- Corrections and late-arriving data are handled explicitly rather than silently
  overwriting history.
- Storage costs more, and the same incident exists in three forms. Accepted — the dataset is
  small enough that this does not matter.
- A refresh failure cannot destroy good data, because ingestion writes new partitions rather
  than overwriting.

## Alternatives considered

**Single cleaned table, refreshed in place.** Simplest and cheapest. Rejected: it destroys
the audit trail, makes corrections indistinguishable from errors, and would force a full
re-fetch of 2006-to-present whenever a mapping or boundary changed.

**Bronze and Gold only, skipping Silver.** Rejected: the normalization work (typing,
dedup, correction resolution, grouping) is real and would end up duplicated inside every
Gold aggregate, where it would inevitably drift.

**A database as the system of record instead of files.** Not rejected on the merits —
deferred. The query engine for Gold is not yet chosen, and the raw-preservation argument
holds regardless of what sits on top.
