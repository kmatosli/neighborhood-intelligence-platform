# Data Quality

The signals tracked per refresh and published on the Data Health page. **None are
implemented** — this is the specification for Level 4 validation
([VALIDATION.md](../architecture/VALIDATION.md)).

The governing rule: **a refresh failure must never erase valid data.** Silence is not
success, and an empty result is not an empty neighborhood.

## Signals

### Freshness

Time since the last successful refresh, and the latest incident date present in the data.
Both are published. Expect roughly a seven-day lag from the source itself — a stale *source*
and a stale *pipeline* are different failures and are reported separately.

### Completeness

Records fetched vs. written vs. rejected, per refresh. Field-level completeness for core and
optional fields. Any drop in completeness against recent history is flagged.

### Duplicates

Duplicate `id` values within a refresh, and unresolved duplicates after deduplication. A
rising duplicate rate usually means paging or incremental-window logic is broken.

### Schema drift

Columns added, removed, or retyped in the source, detected against the metadata endpoint
**before** extraction. A removed column the project depends on — including `latitude` or
`longitude` — is **blocking**.

### Row-count collapse

A refresh returning far fewer rows than recent comparable refreshes, or **zero** rows. This
is treated as a **failure, not a legitimate empty result**. The last good data is retained
and the refresh is marked failed. Without this rule an API outage would publish "crime went
to zero."

### Latest date moving backward

If the newest incident date in a refresh is earlier than the previous refresh's, something
is wrong upstream or in the query window. **Blocking.**

### Missing coordinates

Count and share of records with no `latitude`/`longitude`. A **warning**, always reported,
never blocking. Published alongside every geography-dependent figure as an exclusion count.
A sudden jump in this share is itself a quality signal.

### Rejected records

Count and reasons for records rejected by record validation (missing core fields). Any
rejection is investigated — under the current contract, a rejected record means the source
did something unexpected.

### Last successful refresh

Timestamp and outcome of the most recent successful run, plus the outcome of the most recent
run of any kind. If the two differ, the site is showing data older than its last attempt and
must say so.

## Publication

These are **published, not just logged**. A resident deciding whether to trust a number is
entitled to the same quality information the maintainers have.

The Data Health page ships **with** the first public numbers, not after them.
