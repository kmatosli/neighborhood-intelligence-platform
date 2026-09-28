"""City Services endpoints — Chicago 311 service requests. Read-only over Silver.

Every response carries the metadata a reader needs to interpret it: the geography and how it was
decided, the period and its comparison window, what was excluded and why, the duplicate rule,
the closure interpretation, whether the period is still filling in, and whether any denominator
was used. A figure without that context is not publishable, so the API does not offer one.

Only categories whose closure semantics have been audited are served; asking for another returns
an honest 404 naming the reason rather than an unaudited number.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from bw_observatory.config import Settings
from bw_observatory.ingest.service_requests import load_service_request_config
from bw_observatory.presentation.city_services import (
    CityServicesUnavailable,
    available_years,
    build_category_report,
)
from bw_observatory.presentation.overview import OverviewDataUnavailable

router = APIRouter(prefix="/api/v1/city-services", tags=["city-services"])


class ServiceYears(BaseModel):
    years: list[int]
    latest: int | None
    #: Analysis starts here because the consolidated 311 system launched in December 2018 and
    #: earlier rows are migrated legacy records on a different taxonomy.
    analysis_start_year: int


class ServiceCategory(BaseModel):
    key: str
    label: str
    description: str
    short_codes: list[str]
    #: Only a validated category may be published: its closure semantics have been audited.
    validated: bool


class ServiceCategories(BaseModel):
    categories: list[ServiceCategory]
    dataset_id: str
    dataset_name: str


class Counts(BaseModel):
    raw: int = Field(ge=0, description="Every submission, including duplicates.")
    primary: int = Field(ge=0, description="Submissions not flagged as duplicates of another.")
    duplicates: int = Field(ge=0)
    duplicate_share: float | None = None


class CategoryReportResponse(BaseModel):
    geography_id: str
    geography_label: str
    #: Percent of the community area's area inside Ward 20, when a portion is selected.
    geography_area_share_pct: float | None
    category: str
    category_label: str
    year: int
    data_through: str
    #: True when records are still arriving for the period, so counts will rise.
    provisional: bool

    counts: Counts
    prior_counts: Counts | None
    prior_period_end: str | None

    subcategories: dict[str, int]
    monthly: list[dict[str, int]]
    status: dict[str, int]
    open_ages: dict[str, float | int | None]
    #: Absent when the category's closure semantics do not support a duration.
    completion: dict[str, object] | None
    portions: list[dict[str, object]]
    repeat_addresses: list[dict[str, object]]

    excluded_from_analysis: dict[str, int]
    source_ward_disagreement: int
    denominator: str | None
    methodology: list[str]


@router.get("/years", response_model=ServiceYears)
def get_years() -> ServiceYears:
    settings = Settings()
    config = load_service_request_config()
    years = available_years(settings.data_dir)
    return ServiceYears(
        years=years,
        latest=years[-1] if years else None,
        analysis_start_year=config.analysis_start_year,
    )


@router.get("/categories", response_model=ServiceCategories)
def get_categories() -> ServiceCategories:
    config = load_service_request_config()
    return ServiceCategories(
        dataset_id=config.dataset_id,
        dataset_name=config.dataset_name,
        categories=[
            ServiceCategory(
                key=category.key,
                label=category.label,
                description=category.description,
                short_codes=sorted(category.short_codes),
                validated=category.validated,
            )
            for category in config.categories.values()
        ],
    )


@router.get("/{category}/{geography_id}", response_model=CategoryReportResponse)
def get_category_report(
    category: str,
    geography_id: str,
    year: int = Query(default=2026, ge=2019, le=2100),
) -> CategoryReportResponse:
    settings = Settings()
    try:
        report = build_category_report(
            settings.data_dir, year, geography_id.lower(), category.lower()
        )
    except (CityServicesUnavailable, OverviewDataUnavailable) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return CategoryReportResponse(
        geography_id=report.geography_id,
        geography_label=report.geography_label,
        geography_area_share_pct=report.geography_area_share_pct,
        category=report.category,
        category_label=report.category_label,
        year=report.year,
        data_through=report.data_through,
        provisional=report.provisional,
        counts=Counts(
            raw=report.counts.raw,
            primary=report.counts.primary,
            duplicates=report.counts.duplicates,
            duplicate_share=report.counts.duplicate_share,
        ),
        prior_counts=(
            None
            if report.prior_counts is None
            else Counts(
                raw=report.prior_counts.raw,
                primary=report.prior_counts.primary,
                duplicates=report.prior_counts.duplicates,
                duplicate_share=report.prior_counts.duplicate_share,
            )
        ),
        prior_period_end=report.prior_period_end,
        subcategories=report.subcategories,
        monthly=report.monthly,
        status=report.status,
        open_ages=report.open_ages,
        completion=report.completion,
        portions=report.portions,
        repeat_addresses=report.repeat_addresses,
        excluded_from_analysis=report.excluded_from_analysis,
        source_ward_disagreement=report.source_ward_disagreement,
        denominator=report.denominator,
        methodology=report.methodology,
    )
