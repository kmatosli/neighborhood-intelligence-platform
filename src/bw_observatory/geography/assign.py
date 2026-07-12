"""Point-in-polygon enrichment of Bronze crime records into Silver.

Reads `data/bronze/crime/<year>.parquet` **read-only** and writes
`data/silver/crime/crime_with_geography/<year>.parquet`. Bronze is never modified.

Every Bronze record survives. A record with no coordinates is not a defective record — it
is a real crime whose location was not published — so it is kept, its spatial fields are
null, and it carries `geography_status = missing_coordinates`. Statuses are explicit and
distinct, because "assigned to nothing" has several very different causes and collapsing
them into one null would hide all of them.

Source-reported geography (`ward`, `beat`, `district`, `community_area` as published) is
preserved *alongside* the spatially derived values, never overwritten by them, and the two
are compared so disagreement is visible rather than silently resolved.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from bw_observatory.geography.models import INTERCHANGE_CRS, GeographyStatus, NeighborhoodStatus
from bw_observatory.logging_config import download_logger, validation_logger

SILVER_SUBDIR = Path("crime") / "crime_with_geography"
QUALITY_FILENAME = "geography_quality.parquet"

OUTPUT_COLUMNS = [
    "id",
    "source_year",
    "source_ward",
    "source_beat",
    "source_district",
    "source_community_area",
    "spatial_ward_current",
    "spatial_beat_current",
    "spatial_district_current",
    "spatial_community_area",
    "census_tract",
    "census_block_group",
    "neighborhood_woodlawn",
    "neighborhood_bronzeville",
    "geography_status",
    "ward_mismatch",
    "beat_mismatch",
    "district_mismatch",
    "community_area_mismatch",
    "boundary_vintage",
    "enriched_at",
]

QUALITY_COLUMNS = [
    "year",
    "total_records",
    "records_with_coordinates",
    "records_without_coordinates",
    "records_assigned_to_community_area",
    "records_assigned_to_ward",
    "records_assigned_to_beat",
    "records_assigned_to_district",
    "records_assigned_to_census_tract",
    "records_woodlawn",
    "records_bronzeville",
    "bronzeville_status",
    "ward_mismatches",
    "beat_mismatches",
    "district_mismatches",
    "community_area_mismatches",
    "invalid_coordinates",
    "outside_chicago_boundaries",
    "ambiguous_overlaps",
    "boundary_vintage",
    "enriched_at",
]

# Chicago's bounding box, generously padded. Used only to separate "this coordinate is
# nonsense" from "this coordinate is real but outside the city".
WORLD_LAT = (-90.0, 90.0)
WORLD_LON = (-180.0, 180.0)


def is_absent(value: Any) -> bool:
    """The source published nothing here — distinct from publishing something unusable."""
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    if value is pd.NA:
        return True
    return isinstance(value, str) and not value.strip()


def parse_coordinate(value: Any) -> float | None:
    """Parse a coordinate safely. Anything unparseable is None, never a guess."""
    if is_absent(value):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(parsed):
        return None
    return parsed


def classify_coordinates(
    raw_latitude: Any, raw_longitude: Any
) -> tuple[str | None, float | None, float | None]:
    """Classify a raw coordinate pair.

    Returns (status, latitude, longitude). A status of None means the pair is usable.

    `missing` and `invalid` are deliberately different outcomes. A record the city
    published with no coordinates is an ordinary record whose location was withheld; a
    record carrying an unparseable or impossible coordinate is a data defect. Reporting
    both as "missing" would hide every defect inside a number we expect to be large.
    """
    latitude_absent = is_absent(raw_latitude)
    longitude_absent = is_absent(raw_longitude)
    if latitude_absent and longitude_absent:
        return GeographyStatus.MISSING_COORDINATES, None, None

    latitude = parse_coordinate(raw_latitude)
    longitude = parse_coordinate(raw_longitude)

    # One half present, the other absent: the pair is unusable and the record is incomplete
    # rather than defective.
    if latitude_absent or longitude_absent:
        return GeographyStatus.MISSING_COORDINATES, None, None

    # Present but unparseable — a defect, not an absence.
    if latitude is None or longitude is None:
        return GeographyStatus.INVALID_COORDINATES, None, None

    if not (WORLD_LAT[0] <= latitude <= WORLD_LAT[1]):
        return GeographyStatus.INVALID_COORDINATES, None, None
    if not (WORLD_LON[0] <= longitude <= WORLD_LON[1]):
        return GeographyStatus.INVALID_COORDINATES, None, None
    # Chicago's crime feed occasionally carries a null island point. It is not a location.
    if latitude == 0.0 and longitude == 0.0:
        return GeographyStatus.INVALID_COORDINATES, None, None

    return None, latitude, longitude


def boundary_vintage(dimension: gpd.GeoDataFrame) -> str:
    """A compact record of which boundary vintage produced an assignment.

    Stored on every enriched row, because these are *current* boundaries: a 2006 incident
    assigned to a 2023 ward is being told which ward it is in today, not which ward it was
    in at the time.
    """
    pairs = (
        dimension[["geography_type", "vintage_start"]]
        .drop_duplicates()
        .sort_values("geography_type")
    )
    return ";".join(f"{row.geography_type}:{row.vintage_start}" for row in pairs.itertuples())


class GeographyAssigner:
    """Assigns points to official geographies and to the study neighborhoods."""

    def __init__(self, dimension: gpd.GeoDataFrame, neighborhoods: gpd.GeoDataFrame) -> None:
        self.dimension = dimension
        self.neighborhoods = neighborhoods
        self.vintage = boundary_vintage(dimension)

        self._layers = {
            geography_type: gpd.GeoDataFrame(
                group[["geography_id"]].reset_index(drop=True),
                geometry=group.geometry.reset_index(drop=True),
                crs=INTERCHANGE_CRS,
            )
            for geography_type, group in dimension.groupby("geography_type")
        }

    # -- neighborhoods ---------------------------------------------------------------

    def _neighborhood(self, neighborhood_id: str) -> tuple[Any, str]:
        match = self.neighborhoods[self.neighborhoods["neighborhood_id"] == neighborhood_id]
        if match.empty:
            return None, NeighborhoodStatus.BLOCKED
        row = match.iloc[0]
        return row.geometry, str(row["status"])

    @property
    def bronzeville_available(self) -> bool:
        geometry, status = self._neighborhood("bronzeville")
        return geometry is not None and status == NeighborhoodStatus.ACTIVE

    # -- assignment ------------------------------------------------------------------

    def _join(self, points: gpd.GeoDataFrame, geography_type: str) -> tuple[pd.Series, pd.Series]:
        """Point-in-polygon join. Returns (assigned id per point, ambiguity flag)."""
        layer = self._layers.get(geography_type)
        if layer is None or layer.empty:
            empty = pd.Series([pd.NA] * len(points), index=points.index, dtype="string")
            return empty, pd.Series(False, index=points.index)

        joined = points.sjoin(layer, how="left", predicate="within")

        # A point landing in two polygons of a layer that should partition space is
        # ambiguous. It is reported, not silently resolved by taking the first match.
        ambiguous = joined.index.duplicated(keep=False)
        ambiguous_flags = pd.Series(False, index=points.index)
        if ambiguous.any():
            ambiguous_flags.loc[joined.index[ambiguous].unique()] = True

        assigned = joined[~joined.index.duplicated(keep="first")]["geography_id"]
        return assigned.reindex(points.index).astype("string"), ambiguous_flags

    def enrich(self, bronze: pd.DataFrame, year: int) -> pd.DataFrame:
        """Enrich one year of Bronze records. Never drops a record."""
        enriched_at = datetime.now(UTC).isoformat()
        total = len(bronze)

        frame = pd.DataFrame(index=bronze.index)
        frame["id"] = bronze.get("id", pd.Series(dtype="string")).astype("string")
        frame["source_year"] = year
        for column, target in (
            ("ward", "source_ward"),
            ("beat", "source_beat"),
            ("district", "source_district"),
            ("community_area", "source_community_area"),
        ):
            values = (
                bronze[column] if column in bronze.columns else pd.Series(pd.NA, index=bronze.index)
            )
            frame[target] = values.astype("string")

        raw_latitudes = list(bronze.get("latitude", pd.Series(pd.NA, index=bronze.index)))
        raw_longitudes = list(bronze.get("longitude", pd.Series(pd.NA, index=bronze.index)))

        classified = [
            classify_coordinates(lat, lon)
            for lat, lon in zip(raw_latitudes, raw_longitudes, strict=True)
        ]
        statuses = pd.Series(
            [status for status, _, _ in classified], index=bronze.index, dtype="object"
        )
        latitudes = [lat for _, lat, _ in classified]
        longitudes = [lon for _, _, lon in classified]
        usable = statuses.isna()

        for column in (
            "spatial_ward_current",
            "spatial_beat_current",
            "spatial_district_current",
            "spatial_community_area",
            "census_tract",
            "census_block_group",
        ):
            frame[column] = pd.Series(pd.NA, index=bronze.index, dtype="string")

        frame["neighborhood_woodlawn"] = pd.Series(pd.NA, index=bronze.index, dtype="boolean")
        frame["neighborhood_bronzeville"] = pd.Series(pd.NA, index=bronze.index, dtype="boolean")

        ambiguous_any = pd.Series(False, index=bronze.index)

        if usable.any():
            usable_index = bronze.index[usable]
            geometry = [Point(longitudes[i], latitudes[i]) for i in range(total) if usable.iloc[i]]
            points = gpd.GeoDataFrame(
                {"_row": usable_index}, geometry=geometry, index=usable_index, crs=INTERCHANGE_CRS
            )

            layer_targets = {
                "community_area": "spatial_community_area",
                "ward": "spatial_ward_current",
                "police_beat": "spatial_beat_current",
                "police_district": "spatial_district_current",
                "census_tract": "census_tract",
                "census_block_group": "census_block_group",
            }
            for geography_type, target in layer_targets.items():
                assigned, ambiguous = self._join(points, geography_type)
                frame.loc[usable_index, target] = assigned
                ambiguous_any.loc[usable_index] |= ambiguous.fillna(False)

            woodlawn_geometry, woodlawn_status = self._neighborhood("woodlawn")
            if woodlawn_geometry is not None and woodlawn_status == NeighborhoodStatus.ACTIVE:
                frame.loc[usable_index, "neighborhood_woodlawn"] = points.geometry.within(
                    woodlawn_geometry
                ).values

            if self.bronzeville_available:
                bronzeville_geometry, _ = self._neighborhood("bronzeville")
                frame.loc[usable_index, "neighborhood_bronzeville"] = points.geometry.within(
                    bronzeville_geometry
                ).values
            else:
                # Blocked, not false. A null here means "we do not know", and that is the
                # only honest value until an approved polygon exists.
                validation_logger().warning(
                    "Bronzeville boundary unavailable; neighborhood_bronzeville left null "
                    "for every record in %d. No substitute geography was used.",
                    year,
                )

            # Valid coordinates that land in no community area are outside Chicago.
            outside = usable & frame["spatial_community_area"].isna()
            statuses[outside] = GeographyStatus.OUTSIDE_CHICAGO
            statuses[usable & ambiguous_any] = GeographyStatus.AMBIGUOUS_OVERLAP
            statuses[statuses.isna()] = GeographyStatus.ASSIGNED

        frame["geography_status"] = statuses.astype("string")

        for source_column, spatial_column, flag in (
            ("source_ward", "spatial_ward_current", "ward_mismatch"),
            ("source_beat", "spatial_beat_current", "beat_mismatch"),
            ("source_district", "spatial_district_current", "district_mismatch"),
            ("source_community_area", "spatial_community_area", "community_area_mismatch"),
        ):
            frame[flag] = _mismatch(frame[source_column], frame[spatial_column])

        frame["boundary_vintage"] = self.vintage
        frame["enriched_at"] = enriched_at

        return frame[OUTPUT_COLUMNS].reset_index(drop=True)


def _mismatch(source: pd.Series, spatial: pd.Series) -> pd.Series:
    """True only when both values exist and disagree. Unknown is not a mismatch."""
    both = source.notna() & spatial.notna()
    normalized_source = source.str.strip().str.lstrip("0")
    normalized_spatial = spatial.str.strip().str.lstrip("0")
    return (both & (normalized_source != normalized_spatial)).astype("boolean")


def quality_row(enriched: pd.DataFrame, year: int, bronzeville_available: bool) -> dict[str, Any]:
    status = enriched["geography_status"]
    return {
        "year": year,
        "total_records": len(enriched),
        "records_with_coordinates": int(
            (~status.isin([GeographyStatus.MISSING_COORDINATES])).sum()
        ),
        "records_without_coordinates": int((status == GeographyStatus.MISSING_COORDINATES).sum()),
        "records_assigned_to_community_area": int(enriched["spatial_community_area"].notna().sum()),
        "records_assigned_to_ward": int(enriched["spatial_ward_current"].notna().sum()),
        "records_assigned_to_beat": int(enriched["spatial_beat_current"].notna().sum()),
        "records_assigned_to_district": int(enriched["spatial_district_current"].notna().sum()),
        "records_assigned_to_census_tract": int(enriched["census_tract"].notna().sum()),
        "records_woodlawn": int((enriched["neighborhood_woodlawn"] == True).sum()),  # noqa: E712
        "records_bronzeville": (
            int((enriched["neighborhood_bronzeville"] == True).sum())  # noqa: E712
            if bronzeville_available
            else None
        ),
        "bronzeville_status": (
            "assigned" if bronzeville_available else GeographyStatus.BRONZEVILLE_UNAVAILABLE
        ),
        "ward_mismatches": int((enriched["ward_mismatch"] == True).sum()),  # noqa: E712
        "beat_mismatches": int((enriched["beat_mismatch"] == True).sum()),  # noqa: E712
        "district_mismatches": int((enriched["district_mismatch"] == True).sum()),  # noqa: E712
        "community_area_mismatches": int(
            (enriched["community_area_mismatch"] == True).sum()  # noqa: E712
        ),
        "invalid_coordinates": int((status == GeographyStatus.INVALID_COORDINATES).sum()),
        "outside_chicago_boundaries": int((status == GeographyStatus.OUTSIDE_CHICAGO).sum()),
        "ambiguous_overlaps": int((status == GeographyStatus.AMBIGUOUS_OVERLAP).sum()),
        "boundary_vintage": enriched["boundary_vintage"].iloc[0] if len(enriched) else "",
        "enriched_at": enriched["enriched_at"].iloc[0] if len(enriched) else "",
    }


def silver_path(silver_dir: Path, year: int) -> Path:
    return silver_dir / SILVER_SUBDIR / f"{year}.parquet"


def quality_path(silver_dir: Path) -> Path:
    return silver_dir / "geography" / QUALITY_FILENAME


def completed_years(silver_dir: Path) -> set[int]:
    path = quality_path(silver_dir)
    if not path.exists():
        return set()
    quality = pd.read_parquet(path)
    if quality.empty:
        return set()
    return {int(year) for year in quality["year"] if silver_path(silver_dir, int(year)).exists()}


def upsert_quality_row(silver_dir: Path, row: dict[str, Any]) -> None:
    path = quality_path(silver_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=QUALITY_COLUMNS)
    if not existing.empty:
        existing = existing[existing["year"] != row["year"]]

    updated = pd.concat([existing, pd.DataFrame([row], columns=QUALITY_COLUMNS)])
    updated.sort_values("year").reset_index(drop=True).to_parquet(path, index=False)


def enrich_year(
    assigner: GeographyAssigner,
    bronze_dir: Path,
    silver_dir: Path,
    year: int,
) -> dict[str, Any]:
    """Enrich one year. Reads Bronze read-only; writes one Silver partition."""
    log = download_logger()
    source = bronze_dir / f"{year}.parquet"
    if not source.exists():
        raise FileNotFoundError(f"No Bronze crime data for {year}: {source}")

    bronze = pd.read_parquet(source)
    log.info("Enriching %d: %d Bronze records", year, len(bronze))

    enriched = assigner.enrich(bronze, year)

    if len(enriched) != len(bronze):
        raise RuntimeError(
            f"{year}: enrichment produced {len(enriched)} rows from {len(bronze)} Bronze "
            "records. No Bronze record may be dropped."
        )

    target = silver_path(silver_dir, year)
    target.parent.mkdir(parents=True, exist_ok=True)
    enriched.to_parquet(target, index=False)

    row = quality_row(enriched, year, assigner.bronzeville_available)
    upsert_quality_row(silver_dir, row)

    log.info("Enriched %d: %d rows written to %s", year, len(enriched), target)
    return row
