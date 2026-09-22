"""How much of a ward each community area (or other polygon) accounts for, and vice versa.

Method (documented so the numbers in config/geographies.yml and docs/methodology/GEOGRAPHY.md
can be reproduced exactly):

* Both layers are reprojected to `MEASUREMENT_CRS` — EPSG:3435, NAD83 / Illinois East
  (US survey feet), the State Plane zone that contains Chicago — and areas are planar areas
  in that projection. Geodesic error at this scale is far below the rounding shown.
* Intersections are polygon-on-polygon (`shapely.intersection`); nothing is buffered,
  simplified, or snapped. Polygons are the validated reference layers as downloaded.
* `share_of_ward_pct` is the intersection area over the ward polygon's area. Summed over
  every intersecting polygon of a partitioning layer (community areas partition the city) it
  is 100% by construction — which is the coverage proof, not an assumption.
* `share_of_polygon_in_ward_pct` is the intersection area over the polygon's own area.

Nothing here decides what is shown to residents. It measures; the product owner decides.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry.base import BaseGeometry

MEASUREMENT_CRS = "EPSG:3435"
SQ_FT_PER_SQ_MI = 43_560 * 640

COVERAGE_COLUMNS = [
    "polygon_id",
    "polygon_name",
    "intersection_sq_mi",
    "share_of_ward_pct",
    "share_of_polygon_in_ward_pct",
]


@dataclass(frozen=True)
class WardCoverage:
    ward_id: str
    ward_sq_mi: float
    #: One row per polygon that intersects the ward, largest share of the ward first.
    rows: pd.DataFrame
    #: Sum of `share_of_ward_pct` — 100 (to rounding) when the layer partitions the ward.
    total_share_pct: float


def ward_polygon(wards: gpd.GeoDataFrame, ward_id: str, id_field: str = "ward") -> BaseGeometry:
    match = wards[wards[id_field].astype(str).str.lstrip("0") == ward_id.lstrip("0")]
    if match.empty:
        raise KeyError(f"Ward {ward_id} not found in the ward layer.")
    geometry: BaseGeometry = match.to_crs(MEASUREMENT_CRS).geometry.union_all()
    return geometry


def measure_ward_coverage(
    wards: gpd.GeoDataFrame,
    layer: gpd.GeoDataFrame,
    *,
    ward_id: str,
    id_field: str,
    name_field: str,
    ward_id_field: str = "ward",
) -> WardCoverage:
    """Intersect every polygon of `layer` with one ward and report both shares."""
    ward = ward_polygon(wards, ward_id, ward_id_field)
    ward_area = ward.area

    projected = layer.to_crs(MEASUREMENT_CRS)
    rows: list[dict[str, object]] = []
    for _, feature in projected.iterrows():
        geometry = feature.geometry
        if geometry is None or geometry.is_empty or not geometry.intersects(ward):
            continue
        intersection = geometry.intersection(ward).area
        if intersection <= 0:
            continue
        rows.append(
            {
                "polygon_id": str(feature[id_field]),
                "polygon_name": str(feature[name_field]),
                "intersection_sq_mi": intersection / SQ_FT_PER_SQ_MI,
                "share_of_ward_pct": intersection / ward_area * 100,
                "share_of_polygon_in_ward_pct": intersection / geometry.area * 100,
            }
        )

    frame = pd.DataFrame(rows, columns=COVERAGE_COLUMNS)
    frame = frame.sort_values("share_of_ward_pct", ascending=False).reset_index(drop=True)
    return WardCoverage(
        ward_id=ward_id,
        ward_sq_mi=ward_area / SQ_FT_PER_SQ_MI,
        rows=frame,
        total_share_pct=float(frame["share_of_ward_pct"].sum()) if len(frame) else 0.0,
    )


def community_area_coverage(version_dir: Path, ward_id: str = "20") -> WardCoverage:
    """Ward coverage by official community area, from a downloaded reference version."""
    wards = gpd.read_file(version_dir / "wards_current.geojson")
    areas = gpd.read_file(version_dir / "community_areas.geojson")
    return measure_ward_coverage(
        wards, areas, ward_id=ward_id, id_field="area_numbe", name_field="community"
    )


def symmetric_difference_sq_mi(a: BaseGeometry, b: BaseGeometry) -> float:
    """How different two polygons are, in square miles, in the measurement CRS."""
    return float(a.symmetric_difference(b).area / SQ_FT_PER_SQ_MI)
