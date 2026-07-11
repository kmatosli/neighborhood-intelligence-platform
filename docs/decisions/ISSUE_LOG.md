# Issue Log

Known open issues. Resolved issues move to [CHANGELOG.md](../../CHANGELOG.md).

---

## OneDrive interferes with uv hardlinks

**Status.** Open · **Severity.** Low (workaround available) · **Area.** Environment

The repository sits inside a OneDrive-synced folder on the primary development machine.
`uv sync` fails while installing build dependencies:

```
failed to hardlink file from ...\uv\cache\builds-v0\... to ...\uv\cache\archive-v0\...
The cloud operation cannot be performed on a file with incompatible hardlinks. (os error 396)
```

**Workaround.** Run with copy link mode: set `UV_LINK_MODE=copy`, or pass
`--link-mode=copy`. Once the project has been built and cached, a plain `uv sync` succeeds;
the failure recurs on a fresh clone or after the uv cache is cleared.

**Not fixed in the repository** because it is machine-specific — pinning `link-mode = "copy"`
in `pyproject.toml` would slow down every contributor for one environment's quirk. Better
resolved in user-level uv config, or by moving the clone outside OneDrive.

---

## Local folder name differs from the GitHub repository name

**Status.** Open · **Severity.** Cosmetic · **Area.** Environment

The working directory name does not match the GitHub repository name. Harmless to tooling,
but it makes paths in shared logs and screenshots confusing, and can mislead anyone trying to
match a local path to the remote. Left alone rather than risking a rename of a synced folder.

---

## Some crime records lack coordinates

**Status.** Open by design — **handled, not a defect** · **Severity.** Informational

A share of records in `ijzp-q8t2` have no `latitude`/`longitude` (1 of 10 in a live sample).
These are valid crimes. They are counted in totals, excluded from maps and point-in-polygon
assignment, and produce a warning rather than a failure.

The **open work** is downstream: the exclusion count must be surfaced on every
geography-dependent figure. Detection is built; disclosure is not.

See [VALIDATION.md](../architecture/VALIDATION.md) and
[ADR-0003](../architecture/ADR/ADR-0003-validation-levels.md).

---

## Bronzeville boundary is not yet approved

**Status.** Open · **Severity.** **Blocking** · **Area.** Geography

Bronzeville is not one official community area and has no approved custom GeoJSON boundary.
`config/neighborhoods/` is empty.

**This blocks all geography work** — the map, neighborhood trends, and most of the MVP. It
must not be routed around with a ward, beat, ZIP, or single community area.

See [ADR-0004](../architecture/ADR/ADR-0004-neighborhood-boundary-strategy.md).

---

## No historical backfill exists yet

**Status.** Open · **Severity.** **Blocking** · **Area.** Ingestion

There is no ingestion of crime data from 2006 to present. `scripts/pull_crime_sample.py`
pulls a small JSON sample to `data/bronze/`; that is a smoke test, not a backfill. The Bronze,
Silver, and Gold directories are empty.

---

## No incremental refresh exists yet

**Status.** Open · **Severity.** **Blocking** · **Area.** Ingestion

There is no refresh using `updated_on` and `id`, so record corrections published by the city
are not picked up, and there is no `data_refresh_run` record of what was ingested when.
