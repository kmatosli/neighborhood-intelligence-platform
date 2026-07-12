"""Normalize validated boundary layers into the Silver geography layer.

Outputs:

    data/silver/geography/geography_dimension.parquet     one row per official polygon
    data/silver/geography/neighborhood_boundaries.parquet one row per study neighborhood

Woodlawn resolves from the official community-area polygon. Bronzeville resolves **only**
from an approved custom GeoJSON at `config/neighborhoods/bronzeville.geojson`. If that file
is absent, Bronzeville is recorded as blocked and carries no geometry. It is never
approximated from a ward, a beat, a ZIP code, or a single community area
(docs/architecture/ADR/ADR-0004-neighborhood-boundary-strategy.md).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import yaml

from bw_observatory.geography.models import (
    INTERCHANGE_CRS,
    NeighborhoodConfig,
    NeighborhoodStatus,
    ValidationStatus,
)
from bw_observatory.geography.sources import BOUNDARY_SOURCES, source_by_key
from bw_observatory.geography.validation import (
    load_layer,
    resolve_name_field,
    validate_layer,
)
from bw_observatory.logging_config import validation_logger

GEOGRAPHY_DIMENSION_COLUMNS = [
    "geography_type",
    "geography_id",
    "geography_name",
    "source_dataset_id",
    "source_url",
    "vintage_start",
    "vintage_end",
    "source_updated_at",
    "geometry",
    "geometry_hash",
    "ingested_at",
    "validation_status",
]

NEIGHBORHOOD_COLUMNS = [
    "neighborhood_id",
    "display_name",
    "boundary_type",
    "source",
    "source_vintage",
    "status",
    "geometry",
    "geometry_hash",
    "notes",
]

NEIGHBORHOOD_CONFIG = Path("config/neighborhoods/neighborhoods.yml")
BRONZEVILLE_GEOJSON = Path("config/neighborhoods/bronzeville.geojson")

WOODLAWN_COMMUNITY_AREA = "WOODLAWN"


def geometry_hash(geometry: Any) -> str:
    return hashlib.sha256(geometry.wkb).hexdigest()[:16]


def load_neighborhood_config(path: Path = NEIGHBORHOOD_CONFIG) -> list[NeighborhoodConfig]:
    if not path.exists():
        raise FileNotFoundError(f"Neighborhood config not found: {path}")

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = payload.get("neighborhoods", [])
    return [
        NeighborhoodConfig(
            neighborhood_id=entry["neighborhood_id"],
            display_name=entry["display_name"],
            boundary_type=entry["boundary_type"],
            source=entry["source"],
            source_vintage=str(entry.get("source_vintage", "")),
            status=entry["status"],
            notes=entry.get("notes", ""),
        )
        for entry in entries
    ]


def build_geography_dimension(version_path: Path, manifest: pd.DataFrame) -> gpd.GeoDataFrame:
    """One row per official polygon, across every usable layer."""
    ingested_at = datetime.now(UTC).isoformat()
    frames: list[gpd.GeoDataFrame] = []

    for source in BOUNDARY_SOURCES:
        path = version_path / f"{source.key}.geojson"
        if not path.exists():
            validation_logger().warning(
                "%s: no downloaded file; excluded from the geography dimension.", source.key
            )
            continue

        raw = load_layer(path)
        cleaned, result = validate_layer(raw, source)
        name_field = resolve_name_field(cleaned, source)

        row = manifest[manifest["layer"] == source.key]
        source_updated_at = str(row.iloc[0]["source_updated_at"]) if not row.empty else ""

        dimension = gpd.GeoDataFrame(
            {
                "geography_type": source.geography_type,
                "geography_id": cleaned[result.resolved_id_field].astype("string"),
                "geography_name": (
                    cleaned[name_field].astype("string")
                    if name_field
                    else cleaned[result.resolved_id_field].astype("string")
                ),
                "source_dataset_id": source.dataset_id,
                "source_url": source.source_url,
                "vintage_start": source.vintage_start,
                "vintage_end": source.vintage_end,
                "source_updated_at": source_updated_at,
                "geometry_hash": [geometry_hash(g) for g in cleaned.geometry],
                "ingested_at": ingested_at,
                "validation_status": result.validation_status,
            },
            geometry=cleaned.geometry,
            crs=INTERCHANGE_CRS,
        )
        frames.append(dimension)

    if not frames:
        return gpd.GeoDataFrame(
            columns=GEOGRAPHY_DIMENSION_COLUMNS, geometry=[], crs=INTERCHANGE_CRS
        )

    combined = pd.concat(frames, ignore_index=True)
    return gpd.GeoDataFrame(combined, geometry="geometry", crs=INTERCHANGE_CRS)


def woodlawn_polygon(dimension: gpd.GeoDataFrame) -> gpd.GeoSeries | None:
    """The official Woodlawn community-area polygon, or None if the layer is unusable."""
    areas = dimension[dimension["geography_type"] == "community_area"]
    match = areas[areas["geography_name"].str.upper() == WOODLAWN_COMMUNITY_AREA]
    if match.empty:
        return None
    return match.geometry


def bronzeville_polygon(path: Path = BRONZEVILLE_GEOJSON) -> gpd.GeoSeries | None:
    """The approved custom Bronzeville polygon, or None when no approved file exists.

    None means blocked. It never means "fall back to something convenient".
    """
    if not path.exists():
        return None
    frame = gpd.read_file(path)
    if frame.empty:
        return None
    if frame.crs is None:
        frame = frame.set_crs(INTERCHANGE_CRS)
    return frame.to_crs(INTERCHANGE_CRS).geometry


def build_neighborhood_boundaries(
    dimension: gpd.GeoDataFrame,
    configs: list[NeighborhoodConfig],
    *,
    bronzeville_path: Path = BRONZEVILLE_GEOJSON,
) -> gpd.GeoDataFrame:
    rows: list[dict[str, Any]] = []
    geometries: list[Any] = []

    for config in configs:
        geometry = None
        status = config.status

        if config.neighborhood_id == "woodlawn":
            series = woodlawn_polygon(dimension)
            if series is None or series.empty:
                status = NeighborhoodStatus.BLOCKED
                validation_logger().error("Woodlawn polygon not found in the community-area layer.")
            else:
                geometry = series.union_all()

        elif config.neighborhood_id == "bronzeville":
            series = bronzeville_polygon(bronzeville_path)
            if series is None or series.empty:
                status = NeighborhoodStatus.BLOCKED
                validation_logger().warning(
                    "Bronzeville has no approved boundary at %s. Assignment is blocked; "
                    "no substitute geography will be used.",
                    bronzeville_path,
                )
            else:
                geometry = series.union_all()
                status = NeighborhoodStatus.ACTIVE

        rows.append(
            {
                "neighborhood_id": config.neighborhood_id,
                "display_name": config.display_name,
                "boundary_type": config.boundary_type,
                "source": config.source,
                "source_vintage": config.source_vintage,
                "status": status,
                "geometry_hash": geometry_hash(geometry) if geometry is not None else "",
                "notes": config.notes,
            }
        )
        geometries.append(geometry)

    frame = gpd.GeoDataFrame(rows, geometry=geometries, crs=INTERCHANGE_CRS)
    return frame[NEIGHBORHOOD_COLUMNS]


def write_silver_geography(
    silver_dir: Path,
    dimension: gpd.GeoDataFrame,
    neighborhoods: gpd.GeoDataFrame,
) -> tuple[Path, Path]:
    target = silver_dir / "geography"
    target.mkdir(parents=True, exist_ok=True)

    dimension_path = target / "geography_dimension.parquet"
    neighborhood_path = target / "neighborhood_boundaries.parquet"

    # Geometry is stored as WKT so the table stays a plain Parquet file readable without a
    # geospatial stack; the CRS is fixed and recorded (EPSG:4326).
    _to_wkt(dimension, GEOGRAPHY_DIMENSION_COLUMNS).to_parquet(dimension_path, index=False)
    _to_wkt(neighborhoods, NEIGHBORHOOD_COLUMNS).to_parquet(neighborhood_path, index=False)

    return dimension_path, neighborhood_path


def _to_wkt(frame: gpd.GeoDataFrame, columns: list[str]) -> pd.DataFrame:
    plain = pd.DataFrame(frame.drop(columns="geometry"))
    plain["geometry"] = [None if g is None else g.wkt for g in frame.geometry]
    return plain[columns]


def read_silver_geography(silver_dir: Path) -> gpd.GeoDataFrame:
    from shapely import from_wkt

    path = silver_dir / "geography" / "geography_dimension.parquet"
    frame = pd.read_parquet(path)
    return gpd.GeoDataFrame(
        frame.drop(columns="geometry"),
        geometry=from_wkt(frame["geometry"]),
        crs=INTERCHANGE_CRS,
    )


def read_neighborhoods(silver_dir: Path) -> gpd.GeoDataFrame:
    from shapely import from_wkt

    path = silver_dir / "geography" / "neighborhood_boundaries.parquet"
    frame = pd.read_parquet(path)
    geometry = [None if pd.isna(w) else from_wkt(w) for w in frame["geometry"]]
    return gpd.GeoDataFrame(frame.drop(columns="geometry"), geometry=geometry, crs=INTERCHANGE_CRS)


def layer_validation_report(version_path: Path) -> pd.DataFrame:
    """Validate every downloaded layer and return the QA table."""
    rows: list[dict[str, Any]] = []
    for source in BOUNDARY_SOURCES:
        path = version_path / f"{source.key}.geojson"
        if not path.exists():
            rows.append(
                {
                    "layer": source.key,
                    "feature_count": 0,
                    "crs": "",
                    "geometry_types": "",
                    "repaired_geometries": 0,
                    "empty_geometries": 0,
                    "duplicate_ids": 0,
                    "unexpected_overlaps": 0,
                    "total_area_sq_km": 0.0,
                    "resolved_id_field": "",
                    "validation_status": ValidationStatus.UNRESOLVED,
                    "messages": "layer was not downloaded",
                }
            )
            continue

        frame = load_layer(path)
        _, result = validate_layer(frame, source_by_key(source.key))
        rows.append(result.as_row())

    return pd.DataFrame(rows)
