"""Neighborhood Pulse endpoint. Read-only over Silver + Bronze.

Returns the same-period comparison, broad-category breakdown, beat concentration, category
drivers, arrest summary, data-derived headline/narrative, and issue cards for one
neighborhood and year. Missing data returns an honest 404 with the reason — never zeros or
sample figures.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from bw_observatory.config import Settings
from bw_observatory.presentation.models import PulseResponse
from bw_observatory.presentation.overview import OverviewDataUnavailable
from bw_observatory.presentation.pulse import build_pulse

router = APIRouter(prefix="/api/v1/pulse", tags=["pulse"])


@router.get("/{neighborhood_id}", response_model=PulseResponse)
def get_pulse(
    neighborhood_id: str,
    year: int = Query(default=2026, ge=2006, le=2100),
) -> PulseResponse:
    settings = Settings()
    try:
        return build_pulse(settings.data_dir, year, neighborhood_id.lower())
    except OverviewDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
