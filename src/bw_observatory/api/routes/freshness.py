"""Is the crime data current? Read-only, computed from the refresh bookkeeping.

Lets the product owner (or a monitor) distinguish `current`, `stale`, `refresh_failed` and
`never_refreshed` without opening a Parquet file. Nothing here triggers a refresh.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from bw_observatory.config import Settings
from bw_observatory.ingest.freshness import crime_freshness

router = APIRouter(prefix="/api/v1", tags=["freshness"])


class CrimeFreshness(BaseModel):
    status: str
    reasons: list[str]
    refresh_running: bool
    last_successful_refresh: str | None
    hours_since_success: float | None
    last_run_status: str | None
    last_run_started: str | None
    last_run_error: str | None
    source_watermark: str | None
    data_through: str | None
    days_behind: int | None
    stale_after_hours: int
    source_lag_days: int
    rows_fetched: int | None
    rows_inserted: int | None
    rows_updated: int | None
    rows_unchanged: int | None
    rows_missing_geography: int | None
    duration_seconds: float | None
    reconciliation_drift: dict[str, int]
    last_reconciliation: dict[str, Any] | None


@router.get("/freshness", response_model=CrimeFreshness)
def freshness() -> CrimeFreshness:
    return CrimeFreshness(**crime_freshness(Settings().data_dir).as_dict())
