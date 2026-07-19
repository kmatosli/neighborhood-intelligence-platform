"""The dataset catalog: `data/reference/dataset_catalog.parquet`.

One row per ingested dataset. It answers, without opening any data file, what this project
ingests, where the raw records live, what schema was last seen, when the source was last
verified, and whether the dataset is currently trustworthy.

`status` is about the dataset, not a single run: `active` means the schema validated on the
last attempt; `blocked` means a required column has gone missing and nothing downstream
should trust this dataset until a human looks at it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from bw_observatory.ingest.base import DatasetSpec

CATALOG_FILENAME = "dataset_catalog.parquet"

CATALOG_COLUMNS = [
    "dataset_id",
    "dataset_name",
    "source",
    "primary_key",
    "date_column",
    "refresh_frequency",
    "bronze_location",
    "schema_version",
    "last_verified",
    "status",
]


def schema_fingerprint(column_names: set[str]) -> str:
    """A stable short hash of the source's column set.

    Changes only when the source's columns change, so a shifting `schema_version` in the
    catalog is itself the signal that the dataset was restructured.
    """
    joined = ",".join(sorted(column_names))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:12]


def catalog_path(reference_dir: Path) -> Path:
    return reference_dir / CATALOG_FILENAME


def read_catalog(reference_dir: Path) -> pd.DataFrame:
    path = catalog_path(reference_dir)
    if not path.exists():
        return pd.DataFrame(columns=CATALOG_COLUMNS)
    return pd.read_parquet(path)


def register_dataset(
    reference_dir: Path,
    spec: DatasetSpec,
    *,
    schema_version: str,
    last_verified: str,
    status: str,
) -> None:
    """Insert or replace this dataset's catalog row. One row per `dataset_id`."""
    row = {
        "dataset_id": spec.dataset_id,
        "dataset_name": spec.dataset_name,
        "source": spec.source,
        "primary_key": spec.primary_key,
        "date_column": spec.date_column,
        "refresh_frequency": spec.refresh_frequency,
        "bronze_location": spec.bronze_location,
        "schema_version": schema_version,
        "last_verified": last_verified,
        "status": status,
    }

    catalog = read_catalog(reference_dir)
    if not catalog.empty:
        catalog = catalog[catalog["dataset_id"] != spec.dataset_id]

    updated = pd.concat([catalog, pd.DataFrame([row], columns=CATALOG_COLUMNS)])
    updated = updated.sort_values("dataset_id").reset_index(drop=True)

    path = catalog_path(reference_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    updated.to_parquet(path, index=False)
