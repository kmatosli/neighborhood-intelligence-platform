"""Types and constants for the geography layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Public interchange CRS. Every stored GeoJSON is in this.
INTERCHANGE_CRS = "EPSG:4326"

# Projected CRS for area, distance, and overlap work: NAD83 / Illinois East, in metres.
# Area is NEVER computed in degrees — a degree is not a unit of length, and areas computed
# in lat/lon are meaningless (see docs/architecture/GIS_STRATEGY.md).
PROJECTED_CRS = "EPSG:26971"


class GeographyStatus:
    """Per-record outcome of spatial assignment. Deliberately not one generic null."""

    ASSIGNED = "assigned"
    MISSING_COORDINATES = "missing_coordinates"
    INVALID_COORDINATES = "invalid_coordinates"
    OUTSIDE_CHICAGO = "outside_chicago_boundaries"
    AMBIGUOUS_OVERLAP = "ambiguous_overlap"
    BRONZEVILLE_UNAVAILABLE = "bronzeville_boundary_unavailable"


class ValidationStatus:
    VALID = "valid"
    REPAIRED = "repaired"
    FAILED = "failed"
    UNRESOLVED = "source_unresolved"


class NeighborhoodStatus:
    ACTIVE = "active"
    BLOCKED = "blocked_pending_approval"


@dataclass(frozen=True)
class BoundarySource:
    """One official boundary layer.

    `id_field_candidates` rather than a single field name: the portal's map-type datasets
    do not expose their schema through the metadata endpoint, so the identifying column is
    resolved against the columns actually downloaded, and the resolved name is recorded in
    the manifest. Guessing a field name and silently producing nulls would be worse.
    """

    key: str
    dataset_id: str
    dataset_name: str
    geography_type: str
    source_url: str
    id_field_candidates: tuple[str, ...]
    name_field_candidates: tuple[str, ...] = ()
    vintage_start: str = ""
    vintage_end: str = ""
    role: str = "primary"
    notes: str = ""


@dataclass
class LayerValidation:
    """QA result for one downloaded layer."""

    key: str
    feature_count: int = 0
    crs: str = ""
    geometry_types: list[str] = field(default_factory=list)
    repaired_geometries: int = 0
    empty_geometries: int = 0
    duplicate_ids: int = 0
    unexpected_overlaps: int = 0
    total_area_sq_km: float = 0.0
    resolved_id_field: str = ""
    validation_status: str = ValidationStatus.VALID
    messages: list[str] = field(default_factory=list)

    def as_row(self) -> dict[str, Any]:
        return {
            "layer": self.key,
            "feature_count": self.feature_count,
            "crs": self.crs,
            "geometry_types": ",".join(sorted(set(self.geometry_types))),
            "repaired_geometries": self.repaired_geometries,
            "empty_geometries": self.empty_geometries,
            "duplicate_ids": self.duplicate_ids,
            "unexpected_overlaps": self.unexpected_overlaps,
            "total_area_sq_km": round(self.total_area_sq_km, 3),
            "resolved_id_field": self.resolved_id_field,
            "validation_status": self.validation_status,
            "messages": "; ".join(self.messages),
        }


@dataclass(frozen=True)
class NeighborhoodConfig:
    neighborhood_id: str
    display_name: str
    boundary_type: str
    source: str
    source_vintage: str
    status: str
    notes: str = ""

    @property
    def is_active(self) -> bool:
        return self.status == NeighborhoodStatus.ACTIVE
