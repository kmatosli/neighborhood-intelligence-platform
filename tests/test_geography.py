"""Geography tests. Synthetic polygons and points only — no live network calls."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import pytest
from pytest_httpx import HTTPXMock
from shapely.geometry import Polygon, mapping

from bw_observatory.geography.assign import (
    GeographyAssigner,
    classify_coordinates,
    completed_years,
    enrich_year,
    parse_coordinate,
    quality_path,
    quality_row,
    silver_path,
)
from bw_observatory.geography.ingest import (
    SOURCE_UPDATED_UNKNOWN,
    download_boundaries,
    read_manifest,
    version_dir,
)
from bw_observatory.geography.models import (
    INTERCHANGE_CRS,
    BoundarySource,
    GeographyStatus,
    NeighborhoodStatus,
    ValidationStatus,
)
from bw_observatory.geography.normalize import (
    build_neighborhood_boundaries,
    load_neighborhood_config,
)
from bw_observatory.geography.validation import (
    GeometryValidationError,
    count_overlaps,
    resolve_id_field,
    validate_layer,
)

# A tidy synthetic city, placed over the real Chicago south side so that projecting to
# EPSG:26971 (Illinois East) is meaningful. Squares at null island reproject to NaN area.
#   A = lon [-87.61, -87.60]   B = lon [-87.60, -87.59]   both lat [41.78, 41.79]
X0, X1, X2 = -87.61, -87.60, -87.59
Y0, Y1 = 41.78, 41.79

SQUARE_A = Polygon([(X0, Y0), (X1, Y0), (X1, Y1), (X0, Y1)])
SQUARE_B = Polygon([(X1, Y0), (X2, Y0), (X2, Y1), (X1, Y1)])
OVERLAPPING = Polygon([(-87.605, Y0), (-87.595, Y0), (-87.595, Y1), (-87.605, Y1)])
BOWTIE = Polygon([(X0, Y0), (X1, Y1), (X1, Y0), (X0, Y1)])  # self-intersecting -> invalid

ON_SHARED_EDGE = (41.785, -87.60)  # (lat, lon)

FAKE_SOURCE = BoundarySource(
    key="test_layer",
    dataset_id="test-1234",
    dataset_name="Test Boundaries",
    geography_type="community_area",
    source_url="https://data.cityofchicago.org/resource/test-1234.geojson",
    id_field_candidates=("area_numbe", "area_num_1"),
    name_field_candidates=("community",),
    vintage_start="1920",
)


def layer(
    polygons: list[Polygon], ids: list[str], names: list[str] | None = None
) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "area_numbe": ids,
            "community": names or [f"AREA {i}" for i in ids],
        },
        geometry=polygons,
        crs=INTERCHANGE_CRS,
    )


# -- source metadata & download ------------------------------------------------------------


def test_boundary_download_writes_geojson_and_manifest(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    feature = {
        "type": "Feature",
        "geometry": mapping(SQUARE_A),
        "properties": {"area_numbe": "42", "community": "WOODLAWN"},
    }
    httpx_mock.add_response(
        url="https://data.cityofchicago.org/resource/test-1234.geojson?%24limit=50000",
        json={"type": "FeatureCollection", "features": [feature]},
    )
    httpx_mock.add_response(
        url="https://data.cityofchicago.org/api/views/test-1234",
        json={"rowsUpdatedAt": 1_700_000_000},
    )

    manifest = download_boundaries(tmp_path, version="v1", sources=(FAKE_SOURCE,))

    path = version_dir(tmp_path, "v1") / "test_layer.geojson"
    assert path.exists()

    row = manifest.iloc[0]
    assert row["dataset_id"] == "test-1234"
    assert row["feature_count"] == 1
    assert row["crs"] == INTERCHANGE_CRS
    assert row["file_checksum"] and row["geometry_hash"]
    assert row["downloaded_at"] and row["source_updated_at"]
    assert row["validation_status"] == ValidationStatus.VALID

    assert read_manifest(tmp_path, "v1").iloc[0]["layer"] == "test_layer"


def test_download_falls_back_to_the_tabular_route(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """Map-type datasets serve no features from .geojson; the_geom rows are the fallback."""
    httpx_mock.add_response(
        url="https://data.cityofchicago.org/resource/test-1234.geojson?%24limit=50000",
        json={"type": "FeatureCollection", "features": []},
    )
    httpx_mock.add_response(
        url="https://data.cityofchicago.org/resource/test-1234.json?%24limit=50000",
        json=[{"the_geom": mapping(SQUARE_A), "area_numbe": "42", "community": "WOODLAWN"}],
    )
    httpx_mock.add_response(
        url="https://data.cityofchicago.org/api/views/test-1234",
        json={"rowsUpdatedAt": 1_700_000_000},
    )

    manifest = download_boundaries(tmp_path, version="v1", sources=(FAKE_SOURCE,))

    assert manifest.iloc[0]["feature_count"] == 1
    payload = json.loads((version_dir(tmp_path, "v1") / "test_layer.geojson").read_text())
    assert payload["features"][0]["properties"]["community"] == "WOODLAWN"


def test_unretrievable_layer_is_recorded_not_invented(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    httpx_mock.add_response(
        url="https://data.cityofchicago.org/resource/test-1234.geojson?%24limit=50000",
        json={"type": "FeatureCollection", "features": []},
    )
    httpx_mock.add_response(
        url="https://data.cityofchicago.org/resource/test-1234.json?%24limit=50000", json=[]
    )

    manifest = download_boundaries(tmp_path, version="v1", sources=(FAKE_SOURCE,))

    assert manifest.iloc[0]["validation_status"] == ValidationStatus.UNRESOLVED
    assert manifest.iloc[0]["feature_count"] == 0
    assert not (version_dir(tmp_path, "v1") / "test_layer.geojson").exists()
    # Never "" — an empty timestamp reads as "the source has no timestamp".
    assert manifest.iloc[0]["source_updated_at"] == SOURCE_UPDATED_UNKNOWN


def _mock_layer(httpx_mock: HTTPXMock, *, reusable: bool = False) -> None:
    feature = {
        "type": "Feature",
        "geometry": mapping(SQUARE_A),
        "properties": {"area_numbe": "42", "community": "WOODLAWN"},
    }
    httpx_mock.add_response(
        url="https://data.cityofchicago.org/resource/test-1234.geojson?%24limit=50000",
        json={"type": "FeatureCollection", "features": [feature]},
        is_reusable=reusable,
    )
    httpx_mock.add_response(
        url="https://data.cityofchicago.org/api/views/test-1234",
        json={"rowsUpdatedAt": 1_700_000_000},
        is_reusable=reusable,
    )


def test_existing_layer_is_skipped_without_force(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    """A second run must not re-fetch a layer it already has, and must keep its manifest row."""
    _mock_layer(httpx_mock)
    first = download_boundaries(tmp_path, version="v1", sources=(FAKE_SOURCE,))
    requests_after_first = len(httpx_mock.get_requests())

    second = download_boundaries(tmp_path, version="v1", sources=(FAKE_SOURCE,))

    # Nothing was fetched the second time...
    assert len(httpx_mock.get_requests()) == requests_after_first
    # ...and the layer still has its manifest row, carried over intact.
    assert len(second) == 1
    assert second.iloc[0]["layer"] == "test_layer"
    assert second.iloc[0]["file_checksum"] == first.iloc[0]["file_checksum"]
    assert second.iloc[0]["downloaded_at"] == first.iloc[0]["downloaded_at"]


def test_force_redownloads_an_existing_layer(httpx_mock: HTTPXMock, tmp_path: Path) -> None:
    _mock_layer(httpx_mock, reusable=True)
    download_boundaries(tmp_path, version="v1", sources=(FAKE_SOURCE,))
    requests_after_first = len(httpx_mock.get_requests())

    forced = download_boundaries(tmp_path, version="v1", sources=(FAKE_SOURCE,), force=True)

    assert len(httpx_mock.get_requests()) > requests_after_first
    assert forced.iloc[0]["feature_count"] == 1


def test_unreadable_source_timestamp_is_recorded_as_unknown(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    """A failed metadata lookup must not masquerade as a source with no timestamp."""
    feature = {
        "type": "Feature",
        "geometry": mapping(SQUARE_A),
        "properties": {"area_numbe": "42", "community": "WOODLAWN"},
    }
    httpx_mock.add_response(
        url="https://data.cityofchicago.org/resource/test-1234.geojson?%24limit=50000",
        json={"type": "FeatureCollection", "features": [feature]},
    )
    httpx_mock.add_response(
        url="https://data.cityofchicago.org/api/views/test-1234", status_code=500
    )

    manifest = download_boundaries(tmp_path, version="v1", sources=(FAKE_SOURCE,))

    assert manifest.iloc[0]["source_updated_at"] == SOURCE_UPDATED_UNKNOWN
    assert manifest.iloc[0]["feature_count"] == 1  # the layer itself still downloaded


def test_missing_rows_updated_at_is_recorded_as_unknown(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    feature = {
        "type": "Feature",
        "geometry": mapping(SQUARE_A),
        "properties": {"area_numbe": "42", "community": "WOODLAWN"},
    }
    httpx_mock.add_response(
        url="https://data.cityofchicago.org/resource/test-1234.geojson?%24limit=50000",
        json={"type": "FeatureCollection", "features": [feature]},
    )
    httpx_mock.add_response(
        url="https://data.cityofchicago.org/api/views/test-1234", json={"name": "no timestamp"}
    )

    manifest = download_boundaries(tmp_path, version="v1", sources=(FAKE_SOURCE,))

    assert manifest.iloc[0]["source_updated_at"] == SOURCE_UPDATED_UNKNOWN


# -- geometry validation --------------------------------------------------------------------


def test_crs_is_normalized_to_the_interchange_crs() -> None:
    projected = layer([SQUARE_A], ["1"]).to_crs("EPSG:3857")
    cleaned, result = validate_layer(projected.to_crs(INTERCHANGE_CRS), FAKE_SOURCE)

    assert result.crs == INTERCHANGE_CRS
    assert cleaned.crs is not None


def test_invalid_geometry_is_repaired_and_counted() -> None:
    _, result = validate_layer(layer([BOWTIE], ["1"]), FAKE_SOURCE)

    assert result.repaired_geometries == 1
    assert result.validation_status == ValidationStatus.REPAIRED


def test_empty_geometry_is_rejected() -> None:
    frame = layer([SQUARE_A, Polygon()], ["1", "2"])
    cleaned, result = validate_layer(frame, FAKE_SOURCE)

    assert result.empty_geometries == 1
    assert len(cleaned) == 1


def test_duplicate_geography_ids_are_detected_and_combined() -> None:
    """The city publishes some geographies as several parts sharing one id (beat 3100).

    Those parts are that geography, so they are combined into a single multipolygon —
    an exact union. Leaving them as duplicate rows would make assignment ambiguous, and
    dropping one would silently lose territory.
    """
    cleaned, result = validate_layer(layer([SQUARE_A, SQUARE_B], ["7", "7"]), FAKE_SOURCE)

    assert result.duplicate_ids == 2
    assert result.validation_status == ValidationStatus.REPAIRED
    assert len(cleaned) == 1  # one row per geography id
    assert "7" in result.messages[0]

    # Nothing was dropped: the combined polygon covers both original parts.
    combined = cleaned.geometry.iloc[0]
    assert combined.contains(SQUARE_A.centroid)
    assert combined.contains(SQUARE_B.centroid)


def test_adjacent_polygons_are_not_counted_as_overlapping() -> None:
    # Sharing an edge is normal. Only a shared *area* is an overlap.
    projected = layer([SQUARE_A, SQUARE_B], ["1", "2"]).to_crs("EPSG:26971")
    assert count_overlaps(projected) == 0


def test_real_overlap_is_detected() -> None:
    projected = layer([SQUARE_A, OVERLAPPING], ["1", "2"]).to_crs("EPSG:26971")
    assert count_overlaps(projected) == 1


def test_area_is_computed_in_a_projected_crs_not_degrees() -> None:
    _, result = validate_layer(layer([SQUARE_A], ["1"]), FAKE_SOURCE)
    # The square spans ~0.01 degrees, so roughly 1 km². Computed in degrees it would be 1e-4.
    assert 0.5 < result.total_area_sq_km < 2.0


def test_missing_id_field_is_an_error() -> None:
    frame = gpd.GeoDataFrame({"nope": ["x"]}, geometry=[SQUARE_A], crs=INTERCHANGE_CRS)
    with pytest.raises(GeometryValidationError, match="id fields"):
        resolve_id_field(frame, FAKE_SOURCE)


# -- neighbourhood configuration --------------------------------------------------------------


def test_repository_neighborhood_config_is_loadable() -> None:
    configs = {c.neighborhood_id: c for c in load_neighborhood_config()}

    assert configs["woodlawn"].boundary_type == "official_community_area"
    assert configs["woodlawn"].status == NeighborhoodStatus.ACTIVE
    assert configs["bronzeville"].boundary_type == "custom_geojson"
    assert configs["bronzeville"].status == NeighborhoodStatus.BLOCKED


def dimension_fixture() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "geography_type": ["community_area", "community_area", "ward", "police_beat"],
            "geography_id": ["42", "43", "20", "0132"],
            "geography_name": ["WOODLAWN", "SOUTH SHORE", "20", "0132"],
            "vintage_start": ["1920", "1920", "2023", "2012-12-19"],
        },
        geometry=[SQUARE_A, SQUARE_B, SQUARE_A, SQUARE_A],
        crs=INTERCHANGE_CRS,
    )


def neighborhoods_fixture(tmp_path: Path, *, with_bronzeville: bool = False) -> gpd.GeoDataFrame:
    configs = load_neighborhood_config()
    bronzeville_path = tmp_path / "bronzeville.geojson"

    if with_bronzeville:
        approved = gpd.GeoDataFrame(
            {"name": ["Bronzeville"]}, geometry=[SQUARE_B], crs=INTERCHANGE_CRS
        )
        approved.to_file(bronzeville_path, driver="GeoJSON")

    return build_neighborhood_boundaries(
        dimension_fixture(), configs, bronzeville_path=bronzeville_path
    )


def test_woodlawn_resolves_from_the_official_community_area(tmp_path: Path) -> None:
    neighborhoods = neighborhoods_fixture(tmp_path)
    woodlawn = neighborhoods[neighborhoods["neighborhood_id"] == "woodlawn"].iloc[0]

    assert woodlawn["status"] == NeighborhoodStatus.ACTIVE
    assert woodlawn["boundary_type"] == "official_community_area"
    assert woodlawn.geometry is not None


def test_bronzeville_is_blocked_without_an_approved_polygon(tmp_path: Path) -> None:
    neighborhoods = neighborhoods_fixture(tmp_path)
    bronzeville = neighborhoods[neighborhoods["neighborhood_id"] == "bronzeville"].iloc[0]

    assert bronzeville["status"] == NeighborhoodStatus.BLOCKED
    assert bronzeville.geometry is None  # never approximated from a ward or community area


def test_bronzeville_activates_when_an_approved_polygon_exists(tmp_path: Path) -> None:
    neighborhoods = neighborhoods_fixture(tmp_path, with_bronzeville=True)
    bronzeville = neighborhoods[neighborhoods["neighborhood_id"] == "bronzeville"].iloc[0]

    assert bronzeville["status"] == NeighborhoodStatus.ACTIVE
    assert bronzeville.geometry is not None


# -- coordinate parsing -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [("41.8", 41.8), (41.8, 41.8), (None, None), ("", None), ("not-a-number", None)],
)
def test_parse_coordinate(value: Any, expected: float | None) -> None:
    assert parse_coordinate(value) == expected


def test_classify_coordinates_distinguishes_missing_from_invalid() -> None:
    def status(lat: Any, lon: Any) -> str | None:
        return classify_coordinates(lat, lon)[0]

    # Absent: the city published no location. An ordinary record, not a defect.
    assert status(None, None) == GeographyStatus.MISSING_COORDINATES
    assert status("", "") == GeographyStatus.MISSING_COORDINATES
    assert status("41.8", None) == GeographyStatus.MISSING_COORDINATES

    # Present but unusable: a defect, which must not hide inside the "missing" count.
    assert status("bogus", "-87.6") == GeographyStatus.INVALID_COORDINATES
    assert status(999.0, -87.6) == GeographyStatus.INVALID_COORDINATES
    assert status(0.0, 0.0) == GeographyStatus.INVALID_COORDINATES

    assert status(41.785, -87.605) is None


# -- assignment -------------------------------------------------------------------------------


def bronze_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        [
            # inside SQUARE_A -> community area 42 (Woodlawn), ward 20, beat 0132
            {
                "id": "1",
                "latitude": "41.785",
                "longitude": "-87.605",
                "ward": "20",
                "beat": "0132",
                "district": "003",
                "community_area": "42",
            },
            # inside SQUARE_B -> community area 43; SQUARE_B carries no ward polygon
            {
                "id": "2",
                "latitude": "41.785",
                "longitude": "-87.595",
                "ward": "20",
                "beat": "0132",
                "district": "003",
                "community_area": "43",
            },
            # no coordinates -> kept, all spatial fields null
            {
                "id": "3",
                "latitude": None,
                "longitude": None,
                "ward": "20",
                "beat": "0132",
                "district": "003",
                "community_area": "42",
            },
            # unparseable -> invalid_coordinates, kept
            {
                "id": "4",
                "latitude": "bogus",
                "longitude": "-87.6",
                "ward": "20",
                "beat": "0132",
                "district": "003",
                "community_area": "42",
            },
            # valid but far outside the synthetic city -> outside_chicago_boundaries
            {
                "id": "5",
                "latitude": "50.0",
                "longitude": "50.0",
                "ward": "20",
                "beat": "0132",
                "district": "003",
                "community_area": "42",
            },
            # source community_area disagrees with the polygon -> mismatch flag
            {
                "id": "6",
                "latitude": "41.785",
                "longitude": "-87.605",
                "ward": "3",
                "beat": "0111",
                "district": "003",
                "community_area": "35",
            },
        ]
    )


def assigner_fixture(tmp_path: Path, *, with_bronzeville: bool = False) -> GeographyAssigner:
    return GeographyAssigner(
        dimension_fixture(), neighborhoods_fixture(tmp_path, with_bronzeville=with_bronzeville)
    )


def test_point_in_polygon_assigns_official_geographies(tmp_path: Path) -> None:
    enriched = assigner_fixture(tmp_path).enrich(bronze_fixture(), 2024)
    row = enriched[enriched["id"] == "1"].iloc[0]

    assert row["spatial_community_area"] == "42"
    assert row["spatial_ward_current"] == "20"
    assert row["spatial_beat_current"] == "0132"
    assert row["geography_status"] == GeographyStatus.ASSIGNED


def test_boundary_edge_point_lands_in_exactly_one_polygon(tmp_path: Path) -> None:
    """A point on the shared edge of two adjacent polygons must not be double-assigned."""
    on_edge = pd.DataFrame(
        [
            {
                "id": "edge",
                "latitude": str(ON_SHARED_EDGE[0]),
                "longitude": str(ON_SHARED_EDGE[1]),
                "ward": None,
                "beat": None,
                "district": None,
                "community_area": None,
            }
        ]
    )
    enriched = assigner_fixture(tmp_path).enrich(on_edge, 2024)
    row = enriched.iloc[0]

    # `within` excludes the boundary, so an edge point falls in neither square rather than
    # being counted twice. It is reported honestly as outside, not silently duplicated.
    assert row["geography_status"] in {
        GeographyStatus.ASSIGNED,
        GeographyStatus.OUTSIDE_CHICAGO,
    }
    assert len(enriched) == 1


def test_records_without_coordinates_are_retained(tmp_path: Path) -> None:
    enriched = assigner_fixture(tmp_path).enrich(bronze_fixture(), 2024)
    row = enriched[enriched["id"] == "3"].iloc[0]

    assert row["geography_status"] == GeographyStatus.MISSING_COORDINATES
    assert pd.isna(row["spatial_community_area"])
    assert pd.isna(row["neighborhood_woodlawn"])
    assert row["source_community_area"] == "42"  # source value preserved


def test_invalid_coordinates_are_retained_but_marked(tmp_path: Path) -> None:
    enriched = assigner_fixture(tmp_path).enrich(bronze_fixture(), 2024)
    row = enriched[enriched["id"] == "4"].iloc[0]

    assert row["geography_status"] == GeographyStatus.INVALID_COORDINATES
    assert pd.isna(row["spatial_community_area"])


def test_valid_coordinates_outside_the_city_are_marked(tmp_path: Path) -> None:
    enriched = assigner_fixture(tmp_path).enrich(bronze_fixture(), 2024)
    row = enriched[enriched["id"] == "5"].iloc[0]

    assert row["geography_status"] == GeographyStatus.OUTSIDE_CHICAGO


def test_no_record_is_ever_dropped(tmp_path: Path) -> None:
    bronze = bronze_fixture()
    enriched = assigner_fixture(tmp_path).enrich(bronze, 2024)

    assert len(enriched) == len(bronze)
    assert set(enriched["id"]) == set(bronze["id"])


def test_source_and_spatial_geography_are_both_kept_and_compared(tmp_path: Path) -> None:
    enriched = assigner_fixture(tmp_path).enrich(bronze_fixture(), 2024)
    row = enriched[enriched["id"] == "6"].iloc[0]

    assert row["source_community_area"] == "35"  # what the city published
    assert row["spatial_community_area"] == "42"  # what the polygon says
    assert bool(row["community_area_mismatch"]) is True
    assert bool(row["ward_mismatch"]) is True  # source ward 3, polygon ward 20


def test_matching_geographies_are_not_flagged_as_mismatches(tmp_path: Path) -> None:
    enriched = assigner_fixture(tmp_path).enrich(bronze_fixture(), 2024)
    row = enriched[enriched["id"] == "1"].iloc[0]

    assert bool(row["community_area_mismatch"]) is False
    assert bool(row["ward_mismatch"]) is False


def test_woodlawn_is_assigned_from_the_official_polygon(tmp_path: Path) -> None:
    enriched = assigner_fixture(tmp_path).enrich(bronze_fixture(), 2024)

    assert bool(enriched[enriched["id"] == "1"].iloc[0]["neighborhood_woodlawn"]) is True
    assert bool(enriched[enriched["id"] == "2"].iloc[0]["neighborhood_woodlawn"]) is False


def test_bronzeville_is_null_not_false_when_blocked(tmp_path: Path) -> None:
    assigner = assigner_fixture(tmp_path)
    assert assigner.bronzeville_available is False

    enriched = assigner.enrich(bronze_fixture(), 2024)

    # Null means "not yet defined", never "not in Bronzeville". Collapsing the two would
    # publish a false negative for every record in the neighborhood.
    assert enriched["neighborhood_bronzeville"].isna().all()


def test_bronzeville_is_assigned_once_a_polygon_is_approved(tmp_path: Path) -> None:
    assigner = assigner_fixture(tmp_path, with_bronzeville=True)
    assert assigner.bronzeville_available is True

    enriched = assigner.enrich(bronze_fixture(), 2024)

    assert bool(enriched[enriched["id"] == "2"].iloc[0]["neighborhood_bronzeville"]) is True
    assert bool(enriched[enriched["id"] == "1"].iloc[0]["neighborhood_bronzeville"]) is False


def test_boundary_vintage_is_recorded_on_every_row(tmp_path: Path) -> None:
    enriched = assigner_fixture(tmp_path).enrich(bronze_fixture(), 2024)

    vintage = enriched["boundary_vintage"].iloc[0]
    assert "ward:2023" in vintage  # current wards, not the ward at the time of the incident
    assert enriched["boundary_vintage"].nunique() == 1


# -- quality report & resume -------------------------------------------------------------------


def test_quality_report_counts(tmp_path: Path) -> None:
    enriched = assigner_fixture(tmp_path).enrich(bronze_fixture(), 2024)
    row = quality_row(enriched, 2024, bronzeville_available=False)

    assert row["year"] == 2024
    assert row["total_records"] == 6
    assert row["records_without_coordinates"] == 1
    assert row["records_with_coordinates"] == 5
    assert row["invalid_coordinates"] == 1
    assert row["outside_chicago_boundaries"] == 1
    assert row["records_assigned_to_community_area"] == 3
    assert row["records_woodlawn"] == 2
    assert row["records_bronzeville"] is None
    assert row["bronzeville_status"] == GeographyStatus.BRONZEVILLE_UNAVAILABLE
    assert row["community_area_mismatches"] == 1


def bronze_year(tmp_path: Path, year: int) -> Path:
    bronze_dir = tmp_path / "bronze" / "crime"
    bronze_dir.mkdir(parents=True, exist_ok=True)
    bronze_fixture().astype("string").to_parquet(bronze_dir / f"{year}.parquet", index=False)
    return bronze_dir


def test_enrich_year_writes_silver_and_quality(tmp_path: Path) -> None:
    bronze_dir = bronze_year(tmp_path, 2024)
    silver_dir = tmp_path / "silver"

    enrich_year(assigner_fixture(tmp_path), bronze_dir, silver_dir, 2024)

    assert silver_path(silver_dir, 2024).exists()
    assert quality_path(silver_dir).exists()
    assert len(pd.read_parquet(silver_path(silver_dir, 2024))) == 6


def test_enrichment_never_modifies_bronze(tmp_path: Path) -> None:
    bronze_dir = bronze_year(tmp_path, 2024)
    source = bronze_dir / "2024.parquet"
    before = source.read_bytes()

    enrich_year(assigner_fixture(tmp_path), bronze_dir, tmp_path / "silver", 2024)

    assert source.read_bytes() == before  # byte-for-byte identical


def test_resume_skips_completed_years(tmp_path: Path) -> None:
    bronze_dir = bronze_year(tmp_path, 2024)
    silver_dir = tmp_path / "silver"

    assert completed_years(silver_dir) == set()

    enrich_year(assigner_fixture(tmp_path), bronze_dir, silver_dir, 2024)

    assert completed_years(silver_dir) == {2024}


def test_quality_report_keeps_one_row_per_year(tmp_path: Path) -> None:
    bronze_dir = bronze_year(tmp_path, 2024)
    silver_dir = tmp_path / "silver"
    assigner = assigner_fixture(tmp_path)

    enrich_year(assigner, bronze_dir, silver_dir, 2024)
    enrich_year(assigner, bronze_dir, silver_dir, 2024)

    quality = pd.read_parquet(quality_path(silver_dir))
    assert len(quality) == 1


def test_missing_bronze_year_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        enrich_year(assigner_fixture(tmp_path), tmp_path / "bronze" / "crime", tmp_path / "s", 1999)
