# Data Governance

The rules that govern how data is handled, derived, and published. They exist because this
project makes public claims about two real neighborhoods, and a resident who cannot check a
number has to take it on faith. Nothing here is optional.

Enforcement status is marked per principle: **In force** where the code or repository
already enforces it, **Binding on future work** where it constrains what gets built.

---

## Source integrity

### Never modify source data

What the City of Chicago published is what we store. No cleaning, renaming, casting, or
correcting happens on the way in. Every transformation happens downstream, where it can be
inspected and replayed.

*In force* — the Bronze layer is defined as immutable
([ADR-0002](../architecture/ADR/ADR-0002-bronze-silver-gold-data-layers.md)).

### Preserve raw Chicago records

Raw records are retained as fetched, partitioned by ingestion run, so any published number
can be walked back to the official record behind it. Normalized fields sit *alongside*
source fields, never on top of them.

*Binding on future work* — the Bronze layer is specified but not built.

---

## Reproducibility

### Every metric reproducible

Any published statistic can be regenerated from raw data plus committed code and
configuration. If a number cannot be reproduced from what is in the repository, it does not
get published.

### Every visualization traceable

Each chart or map states the dataset, the query, the boundary version, and the exclusion
counts behind it. A reader must be able to get from a chart to the records that produced it.

### Every statistic timestamped

Every figure carries its source dataset and refresh date wherever it appears — including
inside downloads, fact sheets, and shareable summaries, which travel away from the site and
lose their surrounding context.

### Every algorithm documented

Grouping rules, deduplication logic, trend calculations, and any classification are
documented in plain language and published on the Methodology page. Crime groupings live in
configuration, not hardcoded in analysis code — a grouping choice changes what a trend looks
like, which makes it a methodological claim rather than an implementation detail.

### Every derived dataset documented

Each Silver and Gold table records what it was derived from, by what logic, and when.

---

## Auditability

### Every refresh logged

Each ingestion attempt is recorded: when it ran, what it fetched, what it wrote, what it
rejected, how many records lacked coordinates, and whether it succeeded. Failures are logged
as loudly as successes. A failed refresh must never erase valid data.

*Binding on future work* — specified as `data_refresh_run`
([DATA_MODEL.md](../architecture/DATA_MODEL.md)); not built.

### Every correction logged

Chicago revises records after publication, so historical figures legitimately change.
Corrections are resolved by keeping the newest `updated_on` for a given `id` — and the fact
that a figure changed is recorded, not silently absorbed. The site must be able to explain
why last month's number is different today.

---

## Honesty about gaps

### Never fabricate missing data

No imputation, no interpolation, no filling a hole with a plausible value. A missing value is
reported as missing and counted. Records with no coordinates are kept, counted in totals,
excluded from spatial analysis, and their exclusion count is disclosed on every
geography-dependent figure.

Where the data cannot answer a question, the published answer is that it cannot — not an
estimate dressed as a fact.

*In force* — missing coordinates are detected and warned on
([ADR-0003](../architecture/ADR/ADR-0003-validation-levels.md)); the disclosure requirement
binds the unbuilt presentation layer.

### Never infer neighborhood assignment without GIS validation

A record is assigned to Bronzeville or Woodlawn **only** by point-in-polygon against an
approved boundary. Ward, beat, police district, ZIP code, and any single community area are
prohibited as substitutes. A record without coordinates stays unassigned.

This is the rule most likely to be violated under deadline, because every crime record
already carries a `ward`, a `beat`, and a `community_area` — a working neighborhood filter is
always a few minutes away. It would be wrong, and it would misstate to residents what is
happening in their own neighborhood.

*Binding on future work* — see
[ADR-0004](../architecture/ADR/ADR-0004-neighborhood-boundary-strategy.md) and
[GIS_STRATEGY.md](../architecture/GIS_STRATEGY.md).

---

## Public transparency first

When transparency and convenience conflict, transparency wins.

Quality information is **published, not just logged** — a resident deciding whether to trust
a number is entitled to the same information the maintainers have. The Data Health page ships
with the first public numbers, not after them. Limitations are stated without being asked.
Methodology is written to be read by residents, not defended to auditors.

The test: **a resident who disagrees with a number should be able to find out exactly how it
was produced and argue with it.** If they cannot, the number is not ready to publish.

---

## Related

- [VALIDATION.md](../architecture/VALIDATION.md) — the four validation levels
- [DATA_QUALITY.md](DATA_QUALITY.md) — the health signals tracked per refresh
- [SECURITY.md](../architecture/SECURITY.md) — secrets and the analytical limits on what may be built
- [KNOWN_LIMITATIONS.md](../decisions/KNOWN_LIMITATIONS.md) — what this project cannot tell you
