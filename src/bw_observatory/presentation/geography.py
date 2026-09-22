"""The one place product geography lives.

The application is a Ward 20 platform. A resident can look at Ward 20 as a whole or at the
portion of a neighborhood that lies inside Ward 20. This module is the single authority for
which geographies exist, which are answerable, and how a Silver record is decided to be in
one of them. Nothing else in the API filters by place on its own.

Placement is always the point-in-polygon result recorded in Silver (`spatial_ward_current`,
`spatial_community_area`) — never the city's own reported `ward` / `community_area` fields,
and never a police beat or district standing in for a neighborhood.

The registry is read from `config/geographies.yml`, which also carries the provenance
(source dataset, vintage) that every response repeats back to the reader.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from bw_observatory.config import Settings
from bw_observatory.presentation.models import NeighborhoodAvailability

# Silver columns the geography filter reads. Both are point-in-polygon results.
WARD_COLUMN = "spatial_ward_current"
COMMUNITY_AREA_COLUMN = "spatial_community_area"
GEOGRAPHY_COLUMNS = [WARD_COLUMN, COMMUNITY_AREA_COLUMN]

# Geography types name the boundary SYSTEM a geography comes from. Selectable geographies are
# not peers from one system, and every statistic's provenance says which produced it.
KIND_WARD = "ward"
KIND_AREA_WITHIN_WARD = "community_area_portion"
KIND_NEIGHBORHOOD_PORTION = "neighborhood_portion"
KINDS = frozenset({KIND_WARD, KIND_AREA_WITHIN_WARD, KIND_NEIGHBORHOOD_PORTION})

STATUS_ACTIVE = "active"


class GeographyConfigError(RuntimeError):
    """config/geographies.yml is missing or malformed. Fail loudly; never guess a boundary."""


@dataclass(frozen=True)
class WardDefinition:
    ward_id: str
    geography_id: str
    display_name: str
    source: str
    source_dataset_id: str
    source_vintage: str
    reference_version: str
    notes: str


@dataclass(frozen=True)
class ProductGeography:
    geography_id: str
    display_name: str
    kind: str
    #: Official community-area number for areas within the ward; None for the ward itself and
    #: for pending neighborhoods.
    community_area: str | None
    community_area_name: str | None
    status: str
    #: Why the geography cannot be shown, when it cannot. Never "0 incidents".
    reason: str | None
    #: For a pending neighborhood, the official geography that contains it.
    represented_by: str | None
    notes: str
    share_of_ward_area_pct: float | None = None
    share_of_area_in_ward_pct: float | None = None
    intersection_sq_mi: float | None = None

    @property
    def is_available(self) -> bool:
        return self.status == STATUS_ACTIVE

    @property
    def is_ward(self) -> bool:
        return self.kind == KIND_WARD

    @property
    def boundary_system(self) -> str:
        """Where the boundary comes from, for provenance."""
        if self.kind == KIND_WARD:
            return "City of Chicago ward map"
        if self.kind == KIND_AREA_WITHIN_WARD:
            return "City of Chicago community area, clipped to the ward"
        return "documented neighborhood boundary, clipped to the ward"


@dataclass(frozen=True)
class OtherCommunityArea:
    community_area: str
    community_area_name: str
    share_of_ward_area_pct: float | None
    intersection_sq_mi: float | None = None
    share_of_area_in_ward_pct: float | None = None


@dataclass(frozen=True)
class GeographyRegistry:
    ward: WardDefinition
    geographies: tuple[ProductGeography, ...]
    other_community_areas: tuple[OtherCommunityArea, ...]

    @property
    def default_id(self) -> str:
        return self.ward.geography_id

    def get(self, geography_id: str) -> ProductGeography | None:
        wanted = geography_id.strip().lower()
        return next((g for g in self.geographies if g.geography_id == wanted), None)


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


@lru_cache(maxsize=1)
def load_geography_registry(path: Path | None = None) -> GeographyRegistry:
    """Load the registry once. Same file in, same order and membership out.

    Resolved at call time so `BW_CONFIG_DIR` can move the file without the working directory
    deciding. The ward is always the first, default geography; areas follow in file order.
    """
    resolved = path or Settings().geographies_config
    if not resolved.exists():
        raise GeographyConfigError(f"Geography config not found: {resolved}")

    payload = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    ward_entry = payload.get("ward")
    if not ward_entry:
        raise GeographyConfigError("config/geographies.yml has no `ward` block.")

    ward = WardDefinition(
        ward_id=str(ward_entry["ward_id"]),
        geography_id=str(ward_entry.get("geography_id", f"ward{ward_entry['ward_id']}")),
        display_name=str(ward_entry.get("display_name", f"Ward {ward_entry['ward_id']}")),
        source=str(ward_entry.get("source", "")),
        source_dataset_id=str(ward_entry.get("source_dataset_id", "")),
        source_vintage=str(ward_entry.get("source_vintage", "")),
        reference_version=str(ward_entry.get("reference_version", "")),
        notes=str(ward_entry.get("notes", "")).strip(),
    )

    geographies: list[ProductGeography] = [
        ProductGeography(
            geography_id=ward.geography_id,
            # "Ward 20", not "Ward 20 overall": the name is used inside sentences. The
            # selector adds "overall" itself.
            display_name=ward.display_name,
            kind=KIND_WARD,
            community_area=None,
            community_area_name=None,
            status=STATUS_ACTIVE,
            reason=None,
            represented_by=None,
            notes=ward.notes,
        )
    ]
    for entry in payload.get("areas", []):
        kind = str(entry.get("kind", KIND_AREA_WITHIN_WARD))
        status = str(entry.get("status", STATUS_ACTIVE))
        community_area = entry.get("community_area")
        if kind not in KINDS:
            raise GeographyConfigError(f"{entry.get('geography_id')}: unknown kind `{kind}`.")
        if kind == KIND_AREA_WITHIN_WARD and status == STATUS_ACTIVE and community_area is None:
            raise GeographyConfigError(
                f"{entry.get('geography_id')}: an active area needs a `community_area`."
            )
        geographies.append(
            ProductGeography(
                geography_id=str(entry["geography_id"]).lower(),
                display_name=str(entry["display_name"]),
                kind=kind,
                community_area=None if community_area is None else str(community_area),
                community_area_name=(
                    None
                    if entry.get("community_area_name") is None
                    else str(entry["community_area_name"])
                ),
                status=status,
                reason=None if entry.get("reason") is None else str(entry["reason"]).strip(),
                represented_by=(
                    None if entry.get("represented_by") is None else str(entry["represented_by"])
                ),
                notes=str(entry.get("notes", "")).strip(),
                share_of_ward_area_pct=_optional_float(entry.get("share_of_ward_area_pct")),
                share_of_area_in_ward_pct=_optional_float(entry.get("share_of_area_in_ward_pct")),
                intersection_sq_mi=_optional_float(entry.get("intersection_sq_mi")),
            )
        )

    others = tuple(
        OtherCommunityArea(
            community_area=str(o["community_area"]),
            community_area_name=str(o.get("community_area_name", "")),
            share_of_ward_area_pct=_optional_float(o.get("share_of_ward_area_pct")),
            intersection_sq_mi=_optional_float(o.get("intersection_sq_mi")),
            share_of_area_in_ward_pct=_optional_float(o.get("share_of_area_in_ward_pct")),
        )
        for o in payload.get("other_community_areas_in_ward", [])
    )

    ids = [g.geography_id for g in geographies]
    if len(ids) != len(set(ids)):
        raise GeographyConfigError("Duplicate geography_id in config/geographies.yml.")

    return GeographyRegistry(
        ward=ward, geographies=tuple(geographies), other_community_areas=others
    )


def geography_availability() -> list[NeighborhoodAvailability]:
    """Every product geography with whether it can be shown and, if not, why."""
    registry = load_geography_registry()
    return [
        NeighborhoodAvailability(
            neighborhood_id=g.geography_id,
            display_name=g.display_name,
            available=g.is_available,
            reason=None if g.is_available else g.reason,
            kind=g.kind,
            community_area=g.community_area,
            represented_by=g.represented_by,
            boundary_system=g.boundary_system,
            boundary_source=boundary_source_text(g) if g.is_available else None,
            intersection_sq_mi=g.intersection_sq_mi,
            share_of_ward_area_pct=g.share_of_ward_area_pct,
            share_of_area_in_ward_pct=g.share_of_area_in_ward_pct,
        )
        for g in registry.geographies
    ]


def _normalized(column: pd.Series) -> pd.Series:
    """Ward/community-area ids as plain digit strings, so "020" and "20" compare equal."""
    return column.astype("string").str.strip().str.lstrip("0").fillna("")


def geography_mask(enriched: pd.DataFrame, geography: ProductGeography) -> pd.Series:
    """True for each Silver row that lies inside the geography.

    Ward 20 overall: the point-in-polygon ward is 20. An area within the ward: the ward is 20
    AND the point-in-polygon community area is the area's number. A row with no spatial
    assignment (no coordinates, outside Chicago) is never inside anything.
    """
    for column in GEOGRAPHY_COLUMNS:
        if column not in enriched.columns:
            raise GeographyConfigError(f"Silver data has no `{column}` column.")

    # The ward test stands alone: Ward 20 overall is decided by the ward polygon and nothing
    # else, so no drilldown — however defined, overlapping or not — can change the ward total.
    ward = load_geography_registry().ward
    in_ward = _normalized(enriched[WARD_COLUMN]) == ward.ward_id.lstrip("0")
    if geography.is_ward:
        return in_ward
    if geography.kind == KIND_NEIGHBORHOOD_PORTION:
        # No neighborhood boundary has been validated for filtering. Silver carries no
        # neighborhood assignment, so this must fail loudly rather than return "nothing".
        raise GeographyConfigError(
            f"{geography.geography_id}: neighborhood_portion filtering is not implemented; "
            "no validated neighborhood boundary exists."
        )
    if geography.community_area is None:
        # A pending area has no boundary; it must not silently become "nothing".
        raise GeographyConfigError(f"{geography.geography_id} has no boundary to filter by.")
    in_area = _normalized(enriched[COMMUNITY_AREA_COLUMN]) == geography.community_area.lstrip("0")
    return in_ward & in_area


def geography_scope_note(geography: ProductGeography) -> str:
    """One resident-facing sentence saying exactly what the figures cover."""
    ward = load_geography_registry().ward
    if geography.is_ward:
        return (
            f"Figures cover all of {ward.display_name} as drawn in the {ward.source_vintage} "
            f"ward map — the current {ward.display_name} footprint — applied to every year "
            f"shown."
        )
    note = (
        f"Figures cover only the part of the {geography.display_name} community area that "
        f"lies inside the current {ward.display_name} footprint — not the whole of "
        f"{geography.display_name}."
    )
    # The measured size of the portion is a fact about the denominator, stated plainly so a
    # reader can judge small counts for themselves. It is not a significance rule.
    if (
        geography.intersection_sq_mi is not None
        and geography.share_of_area_in_ward_pct is not None
        and geography.share_of_ward_area_pct is not None
    ):
        # One decimal, so a small portion reads "0.3% of Ward 20", never "0%".
        note += (
            f" That part is about {geography.intersection_sq_mi:.2f} square miles: "
            f"{geography.share_of_area_in_ward_pct:.1f}% of {geography.display_name} and "
            f"{geography.share_of_ward_area_pct:.1f}% of {ward.display_name}."
        )
    return note


def spoken_geography_name(geography: ProductGeography) -> str:
    """The place as it should be named inside a sentence: the ward by its name, a community
    area portion always as "the Ward 20 part of X" — never bare "X", which would read as the
    whole community area."""
    if geography.kind == KIND_AREA_WITHIN_WARD:
        return f"the {load_geography_registry().ward.display_name} part of {geography.display_name}"
    return geography.display_name


def boundary_source_text(geography: ProductGeography) -> str:
    ward = load_geography_registry().ward
    if geography.is_ward:
        return ward.source
    return (
        f"{ward.source}, intersected with City of Chicago — Boundaries - Community Areas "
        f"(igwz-8jzy), community area {geography.community_area}"
    )
