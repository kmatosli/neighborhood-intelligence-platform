# Architecture

## Current phase

**The repository is in the data-foundation phase.** Raw crime ingestion and the geography
layer are built: boundaries are downloaded and versioned, and crime records are assigned to
official geographies by point-in-polygon. There is still no Silver normalization of crime
itself, no analytical (Gold) tables, no API, and no web application.

Bronzeville assignment is **blocked** pending an approved boundary.

## Target pipeline

```
Official source APIs
        │
        ▼
Source validation          ← metadata schema + record contract   [BUILT for crime]
        │
        ▼
Bronze raw layer           ← immutable, as-published             [BUILT for crime]
        │
        ▼
Silver normalized layer    ← typed, deduplicated, conformed      [NOT BUILT]
        │
        ▼
GIS enrichment             ← point-in-polygon neighborhood       [BUILT; Bronzeville blocked]
        │
        ▼
Gold analytical tables     ← aggregates the site actually reads  [NOT BUILT]
        │
        ▼
API                        ← read-only, serves Gold              [NOT BUILT]
        │
        ▼
Public web application     ← resident-facing pages               [NOT BUILT]
```

Each stage is described step by step in [DATA_FLOW.md](DATA_FLOW.md).

## What exists today

| Component | Location | Notes |
| --- | --- | --- |
| Settings | `src/bw_observatory/config.py` | Pydantic settings, `.env`-backed; dataset ID, domain, optional API token |
| Chicago client | `src/bw_observatory/clients/chicago_data.py` | `get_metadata()`, `get_crimes()`; retries on timeout/transport errors via tenacity; raises `ChicagoDataError` |
| Crime validation | `src/bw_observatory/validation/crime_schema.py` | Metadata column contract; blocking core fields; warning-level coordinates |
| **Ingestion framework** | `src/bw_observatory/ingest/base.py` | `BaseDownloader` and `BaseBronzeWriter`. Owns everything shared: schema gate, paging, resume, row-count reconciliation, manifest, refresh log, catalog registration |
| **Bronze writer** | `src/bw_observatory/ingest/bronze.py` | `ParquetBronzeWriter` — one Parquet file per partition; partition column configurable (`year` for crime) |
| **Dataset catalog** | `src/bw_observatory/ingest/catalog.py` | `data/reference/dataset_catalog.parquet` — one row per ingested dataset |
| **Crime downloader** | `src/bw_observatory/ingest/crime_history.py` | `CrimeDownloader`, the first implementation. Supplies only the year window, record contract, and schema rules |
| Logging | `src/bw_observatory/logging_config.py` | `logs/download.log`, `logs/api.log`, `logs/validation.log` |
| Historical ingestion | `scripts/download_crime_history.py` | `--year`, `--start-year`, `--end-year`, `--resume`, `--force` |
| **Geography sources** | `src/bw_observatory/geography/sources.py` | 7 official boundary layers, dataset IDs confirmed against the portal catalog |
| **Boundary ingest** | `src/bw_observatory/geography/ingest.py` | Versioned download to `data/reference/chicago/<version>/` + manifest |
| **Geometry validation** | `src/bw_observatory/geography/validation.py` | CRS, repair, duplicates, overlaps, area QA |
| **Silver geography** | `src/bw_observatory/geography/normalize.py` | `geography_dimension`, `neighborhood_boundaries` |
| **Spatial assignment** | `src/bw_observatory/geography/assign.py` | Point-in-polygon enrichment, explicit statuses, mismatch flags |
| Geography scripts | `scripts/download_geography.py`, `validate_geography.py`, `enrich_crime_geography.py` | Download, validate, enrich |
| API check | `scripts/check_crime_api.py` | Validates metadata, pulls 10 live records, blocks on core fields, warns on coordinates |
| Sample pull | `scripts/pull_crime_sample.py` | Writes a JSON sample to `data/bronze/` (JSON, not Parquet — interim) |
| CI | `.github/workflows/ci.yml` | Ruff, Ruff format, mypy, pytest |

`data/bronze/crime/` holds year-partitioned raw crime data plus `manifest.parquet` and
`refresh_log.parquet`. `data/reference/` holds `dataset_catalog.parquet` and the versioned
boundary sets under `chicago/<version>/`. `data/silver/geography/` holds
`geography_dimension.parquet`, `neighborhood_boundaries.parquet`, and
`geography_quality.parquet`; `data/silver/crime/crime_with_geography/` holds the enriched
year partitions. `config/neighborhoods/` holds `neighborhoods.yml`. Still empty: `data/gold/`.

## The ingestion framework

A second dataset should not mean a second copy of the ingestion logic. Two abstractions
separate what every source shares from what is genuinely source-specific.

**`BaseDownloader`** owns the orchestration: validate the schema *before* fetching anything,
page a partition with a stable sort key, validate every record, reconcile the row count
against the download count before marking a partition complete, write the manifest and
refresh log, and register the dataset in the catalog. A subclass supplies only
`fetch_metadata`, `fetch_page`, `validate_schema`, `validate_records`, and a schema
fingerprint.

**`BaseBronzeWriter`** owns storage: where a partition lands, how it is written verbatim,
and how partition progress is recorded. `ParquetBronzeWriter` is the implementation; its
partition column is configurable, so a monthly dataset reuses it unchanged.

**`CrimeDownloader`** is the only implementation today. No other dataset is ingested yet.

### Dataset catalog

`data/reference/dataset_catalog.parquet` answers, without opening a data file, what this
project ingests and whether it can currently be trusted. One row per dataset:
`dataset_id`, `dataset_name`, `source`, `primary_key`, `date_column`, `refresh_frequency`,
`bronze_location`, `schema_version`, `last_verified`, `status`.

`schema_version` is a fingerprint of the source's column set, so a **changed fingerprint is
itself the drift signal**. `status` describes the dataset, not a run: `active` means the
schema validated on the last attempt; `blocked` means a required column has gone missing and
nothing downstream should trust this dataset until a human looks at it.

## Geography layer

Seven official boundary layers, downloaded into **versioned** reference storage
(`data/reference/chicago/<version>/`) with a manifest recording dataset ID, CRS, feature
count, checksums, geometry hash, vintage, and download timestamp. Boundaries move, so a
boundary set is never overwritten in place.

**CRS.** EPSG:4326 for interchange; EPSG:26971 (Illinois East, metres) for area and overlap.
Area is never computed in degrees.

**Assignment** is point-in-polygon only. Woodlawn uses the official community-area polygon.
Bronzeville requires an approved custom GeoJSON and is **blocked** until one exists — no ward,
beat, ZIP, or single community area is ever substituted. Wards 3 and 20 are retained as
separate political-accountability layers, never as neighborhood definitions.

**Source-reported geography is preserved alongside spatially derived geography** and the two
are compared, so disagreement is visible rather than silently resolved. Records without
coordinates are kept with `geography_status = missing_coordinates`.

## Design principles

**Source fidelity.** The Bronze layer preserves what the city published, unmodified. All
cleaning happens downstream so any number can be traced back to a raw record.

**Validation is layered, not binary.** A dataset losing a column is a different failure
from one record lacking a value. See [VALIDATION.md](VALIDATION.md).

**Refresh failures must not destroy valid data.** Ingestion writes new partitions; it does
not overwrite good data with an empty or partial result.

**Geography is exact or absent.** Neighborhood assignment uses point-in-polygon against an
approved boundary, never a ward/beat/ZIP proxy. See [GIS_STRATEGY.md](GIS_STRATEGY.md).

**Scope is two neighborhoods.** Bronzeville and Woodlawn only. City-wide data is fetched
only where needed to compute a comparison baseline.

## Technology

Python 3.12+, `uv` for dependency management, `httpx` + `tenacity` for HTTP, `pydantic` /
`pydantic-settings` for config and models, `pandas` + `pyarrow` for tabular work and
Parquet. Storage format and query engine for the Gold layer are not yet decided; the
web-application stack is not yet decided.
