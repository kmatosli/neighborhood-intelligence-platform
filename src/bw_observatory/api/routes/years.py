"""Which years the API can actually answer for.

The frontend must not offer a year the data cannot answer, and it must not hardcode a list
that silently goes stale as more years are enriched. This endpoint reports the years that
have geography-enriched Silver data on disk **and** whose Bronze incident attributes are
still present, right now.

Why both layers are checked: the resident-facing pages join the Silver spatial assignment to
the Bronze incident attributes (crime type, date, block) on the source `id`. A Silver year
whose Bronze file has been truncated or corrupted would load and then fail with no usable
dates. Silver is derived one-to-one from Bronze, so a healthy Bronze file has at least as
many rows as its Silver output; fewer means the attributes the pages need are gone. The check
is self-healing — restore the Bronze file and the year reappears with no code change.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from fastapi import APIRouter
from pydantic import BaseModel

from bw_observatory.config import Settings

router = APIRouter(prefix="/api/v1", tags=["years"])


class EnrichedYears(BaseModel):
    years: list[int]
    latest: int | None


def _row_count(path: Path) -> int:
    """Row count read from one column only, so a large file is not fully materialized."""
    return len(pd.read_parquet(path, columns=["id"]))


def year_is_answerable(silver_file: Path, bronze_file: Path) -> bool:
    """True when a year has both Silver geography and its Bronze attributes intact.

    Bronze must exist and carry at least as many rows as Silver. The pathological case this
    rules out is a Bronze file reduced to a stub (e.g. a single row) while its Silver output —
    enriched earlier from good data — still holds the full year: the join would then produce
    rows with no crime type and no date, and the Overview would 404 with "no usable dates".
    """
    if not bronze_file.exists() or not silver_file.exists():
        return False
    try:
        return _row_count(bronze_file) >= _row_count(silver_file)
    except (OSError, ValueError):  # unreadable/corrupt file → the year cannot be answered
        return False


@router.get("/years", response_model=EnrichedYears)
def get_years() -> EnrichedYears:
    settings = Settings()
    silver_dir = settings.data_dir / "silver" / "crime" / "crime_with_geography"
    bronze_dir = settings.data_dir / "bronze" / "crime"

    if not silver_dir.exists():
        return EnrichedYears(years=[], latest=None)

    years = sorted(
        int(p.stem)
        for p in silver_dir.glob("*.parquet")
        if p.stem.isdigit() and year_is_answerable(p, bronze_dir / f"{p.stem}.parquet")
    )
    return EnrichedYears(years=years, latest=years[-1] if years else None)
