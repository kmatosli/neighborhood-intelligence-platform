# Changelog

All notable changes to this project are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The project has not been
released; everything to date is pre-release groundwork.

## [Unreleased]

### Added

- Project documentation structure: architecture, ADRs, product, methodology, and decision
  records under [docs/](docs/README.md).
- Package installation via a `hatchling` build backend so `bw_observatory` is installed
  into the environment rather than only being on the test `sys.path`.
- Record-level validation split into blocking core-field checks (`missing_core_fields`)
  and non-blocking coordinate checks (`missing_coordinates`).
- Tests covering metadata column loss, absent coordinates, null coordinates, and missing
  core fields.

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
