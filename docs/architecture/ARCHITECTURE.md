# Architecture

## Current phase

**The repository is in the data-foundation phase.** A verified Chicago Socrata client and
a validation layer exist. There is no storage layer, no geography, no analytical tables,
no API, and no web application. Everything downstream of "source validation" below is
planned, not built.

Do not read the pipeline diagram as a description of running code.

## Target pipeline

```
Official source APIs
        │
        ▼
Source validation          ← metadata schema + record contract   [BUILT for crime]
        │
        ▼
Bronze raw layer           ← immutable, as-published             [NOT BUILT]
        │
        ▼
Silver normalized layer    ← typed, deduplicated, conformed      [NOT BUILT]
        │
        ▼
GIS enrichment             ← point-in-polygon neighborhood       [NOT BUILT]
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
| API check | `scripts/check_crime_api.py` | Validates metadata, pulls 10 live records, blocks on core fields, warns on coordinates |
| Sample pull | `scripts/pull_crime_sample.py` | Writes a JSON sample to `data/bronze/` (JSON, not Parquet — interim) |
| CI | `.github/workflows/ci.yml` | Ruff, Ruff format, mypy, pytest |

Directory scaffolding exists but is empty: `data/bronze/`, `data/silver/`, `data/gold/`,
`data/reference/`, and `config/neighborhoods/`.

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
