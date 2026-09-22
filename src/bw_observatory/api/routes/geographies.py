"""Which places the API can answer for, and where their boundaries come from.

The frontend's geography selector is built from this — never from a hardcoded list — so a
newly validated area appears with no frontend change, and a pending one is shown disabled
with its reason rather than silently dropped or silently substituted.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from bw_observatory.presentation.geography import geography_availability, load_geography_registry
from bw_observatory.presentation.models import NeighborhoodAvailability

router = APIRouter(prefix="/api/v1", tags=["geographies"])


class WardInfo(BaseModel):
    ward_id: str
    geography_id: str
    display_name: str
    source: str
    source_dataset_id: str
    source_vintage: str
    notes: str


class OtherAreaInWard(BaseModel):
    community_area: str
    community_area_name: str
    share_of_ward_area_pct: float | None
    intersection_sq_mi: float | None = None
    share_of_area_in_ward_pct: float | None = None


class GeographyCatalog(BaseModel):
    ward: WardInfo
    #: The default selection — Ward 20 overall.
    default_geography_id: str
    geographies: list[NeighborhoodAvailability]
    #: Community areas the ward also touches that are not offered as selections, so the ward
    #: total is never mistaken for the sum of the selectable areas.
    other_community_areas_in_ward: list[OtherAreaInWard]


@router.get("/geographies", response_model=GeographyCatalog)
def get_geographies() -> GeographyCatalog:
    registry = load_geography_registry()
    ward = registry.ward
    return GeographyCatalog(
        ward=WardInfo(
            ward_id=ward.ward_id,
            geography_id=ward.geography_id,
            display_name=ward.display_name,
            source=ward.source,
            source_dataset_id=ward.source_dataset_id,
            source_vintage=ward.source_vintage,
            notes=ward.notes,
        ),
        default_geography_id=registry.default_id,
        geographies=geography_availability(),
        other_community_areas_in_ward=[
            OtherAreaInWard(
                community_area=o.community_area,
                community_area_name=o.community_area_name,
                share_of_ward_area_pct=o.share_of_ward_area_pct,
                intersection_sq_mi=o.intersection_sq_mi,
                share_of_area_in_ward_pct=o.share_of_area_in_ward_pct,
            )
            for o in registry.other_community_areas
        ],
    )
