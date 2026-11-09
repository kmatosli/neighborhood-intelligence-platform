"""Crime Trends endpoints. Read-only over the release's Gold aggregates.

`/change` answers what moved and in what context: every crime type's change with an exact
reconciliation to the total, long-run composition (partition plus non-additive overlays),
historical context, Kendall tau-b direction, comparison-window sensitivity and, when a
retained earlier release has been compared, the revisions between them.

An unknown or unavailable geography is a 404 with the reason. Gold that is missing or no
longer describes the release answers `analysis_status: aggregates_unavailable /
aggregates_stale` with no figures at all — never a recomputation against mismatched inputs.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from bw_observatory.config import Settings
from bw_observatory.presentation.change import WINDOW_YTD, build_change
from bw_observatory.presentation.models import ChangeResponse
from bw_observatory.presentation.overview import OverviewDataUnavailable

router = APIRouter(prefix="/api/v1/trends", tags=["trends"])


@router.get("/{geography_id}/change", response_model=ChangeResponse)
def get_change(
    geography_id: str,
    year: int | None = Query(default=None, ge=2006, le=2100),
    window: Literal["ytd", "t12m", "full_year"] = Query(default=WINDOW_YTD),
) -> ChangeResponse:
    settings = Settings()
    try:
        return build_change(
            settings.data_dir, settings.config_dir, geography_id.lower(), year, window
        )
    except OverviewDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
