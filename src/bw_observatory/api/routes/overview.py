"""Overview endpoint. Read-only over the Silver layer."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from bw_observatory.config import Settings
from bw_observatory.presentation.models import OverviewResponse
from bw_observatory.presentation.overview import OverviewDataUnavailable, build_overview

router = APIRouter(prefix="/api/v1/overview", tags=["overview"])


@router.get("/{geography_id}", response_model=OverviewResponse)
def get_overview(
    geography_id: str,
    year: int = Query(default=2024, ge=2006, le=2100),
) -> OverviewResponse:
    """Overview for one geography (Ward 20 overall or an area within it) and year.

    Missing data returns an honest 404 with the reason. It never returns zeros, sample
    figures, or a partially-invented payload.
    """
    settings = Settings()
    try:
        return build_overview(settings.data_dir, year, geography_id.lower())
    except OverviewDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
