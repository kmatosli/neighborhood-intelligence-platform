"""Individual incidents. Read-only over Bronze + Silver."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from bw_observatory.config import Settings
from bw_observatory.presentation.incidents import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    SORTABLE,
    build_incident_csv,
    build_incident_page,
)
from bw_observatory.presentation.models import IncidentPage
from bw_observatory.presentation.overview import OverviewDataUnavailable

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])

BRONZEVILLE_BLOCKED = "Bronzeville is not available: Boundary pending approval."
_SORT_DIRS = {"asc", "desc"}


def _guard_neighborhood(neighborhood_id: str) -> str:
    requested = neighborhood_id.lower()
    if requested == "bronzeville":
        raise HTTPException(status_code=404, detail=BRONZEVILLE_BLOCKED)
    if requested != "woodlawn":
        raise HTTPException(status_code=404, detail=f"Unknown neighborhood: {neighborhood_id}")
    return requested


def _validate_sort(sort_by: str, sort_dir: str) -> None:
    if sort_by not in SORTABLE:
        raise HTTPException(status_code=422, detail=f"Cannot sort by '{sort_by}'.")
    if sort_dir not in _SORT_DIRS:
        raise HTTPException(status_code=422, detail="sort_dir must be 'asc' or 'desc'.")


@router.get("/{neighborhood_id}", response_model=IncidentPage)
def get_incidents(
    neighborhood_id: str,
    year: int = Query(default=2026, ge=2006, le=2100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    primary_type: str | None = Query(default=None),
    broad_category: str | None = Query(default=None),
    block: str | None = Query(default=None),
    description: str | None = Query(default=None),
    location: str | None = Query(default=None),
    ward: str | None = Query(default=None),
    district: str | None = Query(default=None),
    beat: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    arrest: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    sort_by: str = Query(default="date"),
    sort_dir: str = Query(default="desc"),
) -> IncidentPage:
    """Reported incidents spatially assigned to a neighborhood, newest first by default.

    Woodlawn only for now. Bronzeville has no approved boundary, so it returns 404 with the
    reason rather than an empty list — an empty list would read as "no incidents".
    """
    requested = _guard_neighborhood(neighborhood_id)
    _validate_sort(sort_by, sort_dir)

    settings = Settings()
    try:
        return build_incident_page(
            settings.data_dir,
            year,
            page=page,
            page_size=page_size,
            primary_type=primary_type,
            broad_category=broad_category,
            block=block,
            description=description,
            location=location,
            ward=ward,
            district=district,
            beat=beat,
            date_from=date_from,
            date_to=date_to,
            arrest=arrest,
            search=search,
            sort_by=sort_by,
            sort_dir=sort_dir,
            neighborhood_id=requested,
        )
    except OverviewDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{neighborhood_id}/export.csv", response_class=PlainTextResponse)
def export_incidents(
    neighborhood_id: str,
    year: int = Query(default=2026, ge=2006, le=2100),
    primary_type: str | None = Query(default=None),
    broad_category: str | None = Query(default=None),
    block: str | None = Query(default=None),
    description: str | None = Query(default=None),
    location: str | None = Query(default=None),
    ward: str | None = Query(default=None),
    district: str | None = Query(default=None),
    beat: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    arrest: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    sort_by: str = Query(default="date"),
    sort_dir: str = Query(default="desc"),
) -> PlainTextResponse:
    """The current filtered result set as CSV — masked block-level, exactly as published."""
    requested = _guard_neighborhood(neighborhood_id)
    _validate_sort(sort_by, sort_dir)

    settings = Settings()
    try:
        csv = build_incident_csv(
            settings.data_dir,
            year,
            primary_type=primary_type,
            broad_category=broad_category,
            block=block,
            description=description,
            location=location,
            ward=ward,
            district=district,
            beat=beat,
            date_from=date_from,
            date_to=date_to,
            arrest=arrest,
            search=search,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
    except OverviewDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    filename = f"{requested}-incidents-{year}.csv"
    return PlainTextResponse(
        content=csv,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
