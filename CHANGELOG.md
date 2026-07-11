# Changelog

All notable changes to this project are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The project has not been
released; everything to date is pre-release groundwork.

## [Unreleased]

### Added

- Historical crime ingestion (`scripts/download_crime_history.py`): paged, retried,
  restartable, writing year-partitioned raw Parquet to `data/bronze/crime/` with
  `manifest.parquet` and `refresh_log.parquet`.
- Reusable ingestion framework: `BaseDownloader` and `BaseBronzeWriter`, with
  `CrimeDownloader` as the first and only implementation.
- Dataset catalog at `data/reference/dataset_catalog.parquet` — one row per ingested
  dataset, with a `schema_version` fingerprint and an `active`/`blocked` trust status.
- Ingestion logging to `logs/download.log`, `logs/api.log`, and `logs/validation.log`.
- Project documentation structure: architecture, ADRs, product, methodology, and decision
  records under [docs/](docs/README.md).
- Package installation via a `hatchling` build backend so `bw_observatory` is installed
  into the environment rather than only being on the test `sys.path`.
- Record-level validation split into blocking core-field checks (`missing_core_fields`)
  and non-blocking coordinate checks (`missing_coordinates`).
- Tests covering metadata column loss, absent coordinates, null coordinates, and missing
  core fields.

### Fixed

- Chicago client retries never fired. `httpx.TimeoutException` and `TransportError` are
  subclasses of `httpx.HTTPError`, which was caught *inside* the `@retry`-decorated call and
  re-raised as `ChicagoDataError` — so tenacity never saw a retryable exception. The retry
  now sits on the raw request, with error wrapping outside it.

### Changed

- `scripts/check_crime_api.py` now exits 0 when missing coordinates are the only defect,
  printing a warning with the count of affected records.
- Dataset schema validation and per-record validation are now separate concerns; the
  dataset losing a `latitude`/`longitude` column remains blocking.

### Removed

- `validate_record_shape()`, which incorrectly treated coordinates as required on every
  record. Replaced by `missing_core_fields()` and `missing_coordinates()`.
- Unused `pathlib.Path` import in `scripts/pull_crime_sample.py`.

### Not yet built

Historical backfill, incremental refresh, Parquet storage, neighborhood boundaries,
point-in-polygon assignment, census/ACS, elections, event calendar, and the public web
application. See [TODO.md](TODO.md).
