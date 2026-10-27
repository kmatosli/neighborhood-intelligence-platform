"""Synthetic release roots for the Gold, revision and Change tests.

A row is a dict with `id`, `date` (YYYY-MM-DD) and `primary_type`; everything else defaults
to an active, dated Woodlawn (community area 42) incident inside Ward 20. `spatial_ward` /
`spatial_ca` are the point-in-polygon placement; `source_ward` is what the City published,
which must never decide membership.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd

from bw_observatory.config import Settings
from bw_observatory.release import (
    STATUS_DEVELOPMENT,
    build_release_manifest,
    write_release_manifest,
)

CONFIG_DIR = Settings().config_dir

_DEFAULTS: dict[str, Any] = {
    "fbi_code": "06",
    "arrest": "false",
    "domestic": "false",
    "spatial_ward": "20",
    "spatial_ca": "42",
    "source_ward": "20",
    "source_status": "active_in_source",
    "bronze": True,  # False: a Silver row with no Bronze attributes
}


def row(id_: str, day: str, primary_type: str, **overrides: Any) -> dict[str, Any]:
    return {"id": id_, "date": day, "primary_type": primary_type, **_DEFAULTS, **overrides}


def write_root(
    root: Path,
    rows: list[dict[str, Any]],
    *,
    release_id: str = "dev-test",
    status: str = STATUS_DEVELOPMENT,
    with_manifest: bool = True,
) -> Path:
    bronze_dir = root / "bronze" / "crime"
    silver_dir = root / "silver" / "crime" / "crime_with_geography"
    bronze_dir.mkdir(parents=True, exist_ok=True)
    silver_dir.mkdir(parents=True, exist_ok=True)

    frame = pd.DataFrame(rows)
    frame["_year"] = frame["date"].str.slice(0, 4).astype(int)
    manifest = []
    for year, part in frame.groupby("_year"):
        with_attributes = part[part["bronze"]]
        bronze = pd.DataFrame(
            {
                "id": with_attributes["id"],
                "date": with_attributes["date"] + "T12:00:00.000",
                "primary_type": with_attributes["primary_type"],
                "fbi_code": with_attributes["fbi_code"],
                "arrest": with_attributes["arrest"],
                "domestic": with_attributes["domestic"],
                "ward": with_attributes["source_ward"],
                "community_area": with_attributes["spatial_ca"],
                "beat": "0312",
                "block": "001XX E 63RD ST",
            }
        ).astype("string")
        bronze_file = bronze_dir / f"{year}.parquet"
        bronze.to_parquet(bronze_file, index=False)
        pd.DataFrame(
            {
                "id": part["id"],
                "spatial_ward_current": part["spatial_ward"],
                "spatial_community_area": part["spatial_ca"],
                "source_status": part["source_status"],
            }
        ).astype("string").to_parquet(silver_dir / f"{year}.parquet", index=False)
        manifest.append(
            {
                "year": int(str(year)),
                "rows": len(bronze),
                "checksum": hashlib.sha256(bronze_file.read_bytes()).hexdigest(),
                "status": "complete",
            }
        )
    pd.DataFrame(manifest).to_parquet(bronze_dir / "manifest.parquet", index=False)
    if with_manifest:
        write_release_manifest(
            root, build_release_manifest(root, CONFIG_DIR, release_id, status, commit="test")
        )
    return root
