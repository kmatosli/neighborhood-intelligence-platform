"""Geometry validation and QA for boundary layers.

Repair policy (documented, per docs/methodology/DATA_GOVERNANCE.md): an invalid polygon is
repaired **only** by `shapely.make_valid`, which resolves self-intersections and ring
problems without moving the boundary. Every repaired feature is counted and reported. No
other geometric surgery — no simplification, no buffering, no snapping — is performed, and
a geometry that cannot be made valid is rejected rather than approximated.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely import make_valid

from bw_observatory.geography.models import (
    INTERCHANGE_CRS,
    PROJECTED_CRS,
    BoundarySource,
    LayerValidation,
    ValidationStatus,
)
from bw_observatory.logging_config import validation_logger

POLYGON_TYPES = {"Polygon", "MultiPolygon"}


class GeometryValidationError(RuntimeError):
    """A boundary layer is not usable for spatial assignment."""


def resolve_id_field(frame: gpd.GeoDataFrame, source: BoundarySource) -> str:
    """Pick the identifying column from the ones the layer actually has."""
    lowered = {column.lower(): column for column in frame.columns}
    for candidate in source.id_field_candidates:
        if candidate.lower() in lowered:
            return str(lowered[candidate.lower()])
    raise GeometryValidationError(
        f"{source.key}: none of the expected id fields {source.id_field_candidates} are "
        f"present. Columns: {sorted(frame.columns)}"
    )


def resolve_name_field(frame: gpd.GeoDataFrame, source: BoundarySource) -> str | None:
    lowered = {column.lower(): column for column in frame.columns}
    for candidate in source.name_field_candidates:
        if candidate.lower() in lowered:
            return str(lowered[candidate.lower()])
    return None


def load_layer(path: Path) -> gpd.GeoDataFrame:
    frame = gpd.read_file(path)
    if frame.crs is None:
        # GeoJSON is defined as EPSG:4326; a missing CRS tag is assumed, not invented.
        validation_logger().warning("%s: no CRS declared; assuming %s.", path.name, INTERCHANGE_CRS)
        frame = frame.set_crs(INTERCHANGE_CRS)
    return frame.to_crs(INTERCHANGE_CRS)


def validate_layer(
    frame: gpd.GeoDataFrame,
    source: BoundarySource,
    *,
    expect_no_overlaps: bool = True,
) -> tuple[gpd.GeoDataFrame, LayerValidation]:
    """Validate and (where necessary) repair a boundary layer.

    Returns the cleaned frame and its QA result. Raises only when the layer cannot be used
    at all: no geometry column, or no resolvable identifier.
    """
    log = validation_logger()
    result = LayerValidation(key=source.key)

    if "geometry" not in frame.columns:
        raise GeometryValidationError(f"{source.key}: no geometry column.")
    if frame.crs is None:
        raise GeometryValidationError(f"{source.key}: no CRS.")

    result.crs = str(frame.crs)
    result.feature_count = len(frame)
    result.resolved_id_field = resolve_id_field(frame, source)

    # Reject empty geometries rather than carrying rows that can never match a point.
    empty = frame.geometry.is_empty | frame.geometry.isna()
    result.empty_geometries = int(empty.sum())
    if result.empty_geometries:
        log.warning("%s: dropping %d empty geometries.", source.key, result.empty_geometries)
        frame = frame[~empty].copy()

    invalid = ~frame.geometry.is_valid
    result.repaired_geometries = int(invalid.sum())
    if result.repaired_geometries:
        log.warning(
            "%s: repairing %d invalid geometries with make_valid.",
            source.key,
            result.repaired_geometries,
        )
        frame.loc[invalid, "geometry"] = frame.loc[invalid, "geometry"].apply(make_valid)
        result.validation_status = ValidationStatus.REPAIRED

    still_invalid = ~frame.geometry.is_valid
    if still_invalid.any():
        count = int(still_invalid.sum())
        result.messages.append(f"{count} geometries could not be made valid; dropped.")
        log.error("%s: %d geometries could not be made valid; dropping them.", source.key, count)
        frame = frame[~still_invalid].copy()

    types = set(frame.geometry.geom_type.unique())
    result.geometry_types = sorted(types)
    if not types <= POLYGON_TYPES:
        unexpected = sorted(types - POLYGON_TYPES)
        result.messages.append(f"non-polygon geometry types present: {unexpected}")
        log.error("%s: unexpected geometry types %s", source.key, unexpected)
        result.validation_status = ValidationStatus.FAILED

    ids = frame[result.resolved_id_field].astype("string")
    duplicates = ids.duplicated(keep=False)
    result.duplicate_ids = int(duplicates.sum())
    if result.duplicate_ids:
        # A duplicate id makes assignment ambiguous — a point inside it would get two
        # answers. The city genuinely publishes some geographies as several polygon parts
        # sharing one id (police beat 3100, district 31). Those parts *are* that geography,
        # so each id's parts are combined into one multipolygon: an exact union of what was
        # published. Nothing is dropped, no boundary is moved, and the count is reported.
        affected = sorted(set(ids[duplicates].dropna()))
        result.messages.append(
            f"{result.duplicate_ids} rows shared {len(affected)} duplicate geography id(s) "
            f"{affected}; each id's parts combined into one multipolygon"
        )
        log.warning(
            "%s: %d rows share duplicate geography ids %s; combining each id's parts.",
            source.key,
            result.duplicate_ids,
            affected,
        )
        frame = frame.dissolve(by=result.resolved_id_field, as_index=False)
        result.validation_status = ValidationStatus.REPAIRED

    projected = frame.to_crs(PROJECTED_CRS)
    result.total_area_sq_km = float(projected.geometry.area.sum()) / 1_000_000

    if expect_no_overlaps:
        result.unexpected_overlaps = count_overlaps(projected)
        if result.unexpected_overlaps:
            result.messages.append(
                f"{result.unexpected_overlaps} overlapping polygon pairs in a layer that "
                "should partition space"
            )
            log.warning("%s: %d overlapping polygon pairs.", source.key, result.unexpected_overlaps)

    frame = frame.reset_index(drop=True)
    return frame, result


def count_overlaps(projected: gpd.GeoDataFrame) -> int:
    """Count polygon pairs whose interiors overlap by a non-trivial area.

    Adjacent polygons legitimately share edges, so touching is not an overlap. A shared
    *area* is. The tolerance (1 m²) keeps floating-point slivers from being reported as
    real overlaps.
    """
    pairs = projected.sindex.query(projected.geometry, predicate="overlaps")
    seen: set[tuple[int, int]] = set()
    overlaps = 0

    for left, right in zip(pairs[0], pairs[1], strict=True):
        if left == right:
            continue
        key = (min(int(left), int(right)), max(int(left), int(right)))
        if key in seen:
            continue
        seen.add(key)

        shared = projected.geometry.iloc[key[0]].intersection(projected.geometry.iloc[key[1]])
        if shared.area > 1.0:
            overlaps += 1

    return overlaps
