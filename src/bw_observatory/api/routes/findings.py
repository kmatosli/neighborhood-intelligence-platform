"""Overview findings endpoint — the Neighborhood Intelligence Brief. Read-only.

Returns the published conclusions for one geography and year: the lead findings, the remaining
findings by domain, neighborhood differences, the questions the evidence raises, and the domains
with no ingested data. Every figure is computed from the same Bronze + Silver data the Trends
page reads, so the brief and its evidence cannot disagree.

Only findings marked `published` in `config/findings.yml` are served. Anything withheld —
unpublished, suppressed by a small-sample rule, or lacking a comparison period — is listed in
`withheld` with the reason, so a suppressed finding is visible as a decision rather than an
absence. Missing data returns an honest 404 with the reason.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from bw_observatory.config import Settings
from bw_observatory.presentation.findings import FindingsConfigError, build_findings
from bw_observatory.presentation.models import FindingsResponse
from bw_observatory.presentation.overview import OverviewDataUnavailable

router = APIRouter(prefix="/api/v1/findings", tags=["findings"])


@router.get("", response_model=FindingsResponse)
def get_findings(
    geo: str = Query(default="ward20", description="Product geography id, e.g. ward20, woodlawn."),
    year: int = Query(default=2026, ge=2006, le=2100),
) -> FindingsResponse:
    settings = Settings()
    try:
        return build_findings(settings.data_dir, year, geo.lower())
    except OverviewDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FindingsConfigError as exc:
        # A malformed findings file is an operator error, not a client error: answer 500 with
        # the reason rather than serving a partial brief that looks complete.
        raise HTTPException(status_code=500, detail=str(exc)) from exc
