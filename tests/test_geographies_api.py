"""Product geography: Ward 20, the areas within it, and how geography interacts with year.

The fixture places incidents so that every geographic rule has a row that would break it:

* in Ward 20 and in Woodlawn (counts for both);
* in Ward 20 but in New City (counts for the ward, not for Woodlawn);
* in the Woodlawn community area but outside Ward 20 (counts for neither — the product's
  Woodlawn is the part inside the ward);
* with a source `ward` that says 20 while the polygon says otherwise (source is ignored).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bw_observatory.api.routes import geographies as geographies_route
from bw_observatory.api.routes import incidents as incidents_route
from bw_observatory.api.routes import pulse as pulse_route
from bw_observatory.presentation.geography import (
    GeographyConfigError,
    geography_mask,
    load_geography_registry,
)
from bw_observatory.presentation.incidents import build_incident_page
from bw_observatory.presentation.overview import OverviewDataUnavailable, build_overview
from bw_observatory.presentation.pulse import build_pulse

# id, date, primary_type, spatial ward, spatial community area, source ward
_ROWS_2025 = [
    ("a1", "2025-01-10", "BATTERY", "20", "42", "20"),  # Woodlawn, in ward
    ("a2", "2025-02-10", "THEFT", "20", "42", "5"),  # Woodlawn, in ward (source ward wrong)
    ("a3", "2025-03-10", "THEFT", "20", "61", "20"),  # New City, in ward
    ("a4", "2025-04-10", "ROBBERY", "20", "68", "20"),  # Englewood, in ward
    ("a5", "2025-05-10", "BATTERY", "5", "42", "20"),  # Woodlawn, OUTSIDE ward (source says 20)
    ("a6", "2025-06-10", "THEFT", "3", "38", "3"),  # Grand Boulevard, outside ward
    ("a7", "2025-07-10", "THEFT", None, None, "20"),  # no coordinates: nowhere
]
_ROWS_2024 = [
    ("b1", "2024-01-10", "BATTERY", "20", "42", "20"),
    ("b2", "2024-02-10", "THEFT", "20", "61", "20"),
    ("b3", "2024-03-10", "THEFT", "5", "42", "20"),
]


def _write_year(root: Path, year: int, rows: list[tuple[Any, ...]]) -> None:
    bronze = root / "bronze" / "crime"
    silver = root / "silver" / "crime" / "crime_with_geography"
    geo = root / "silver" / "geography"
    for directory in (bronze, silver, geo):
        directory.mkdir(parents=True, exist_ok=True)

    bronze_file = bronze / f"{year}.parquet"
    pd.DataFrame(
        [
            {
                "id": r[0],
                "case_number": f"JJ{r[0]}",
                "date": f"{r[1]}T12:00:00.000",
                "updated_on": f"{r[1]}T12:00:00.000",
                "block": "001XX W 63RD ST",
                "primary_type": r[2],
                "description": "SIMPLE",
                "location_description": "STREET",
                "arrest": "false",
                "domestic": "false",
                "beat": "0321",
                "district": "003",
                "ward": r[5],
                "community_area": r[4],
                "latitude": "41.78",
                "longitude": "-87.61",
            }
            for r in rows
        ]
    ).astype("string").to_parquet(bronze_file, index=False)

    pd.DataFrame(
        [
            {
                "id": r[0],
                "source_ward": r[5],
                "spatial_ward_current": r[3],
                "spatial_community_area": r[4],
                "geography_status": "assigned" if r[3] else "no_coordinates",
                "boundary_vintage": "community_area:1920;ward:2023",
            }
            for r in rows
        ]
    ).to_parquet(silver / f"{year}.parquet", index=False)

    checksum = hashlib.sha256(bronze_file.read_bytes()).hexdigest()
    manifest_row = pd.DataFrame(
        [
            {
                "year": year,
                "rows": len(rows),
                "download_completed": f"{year}-12-31T00:00:00+00:00",
                "checksum": checksum,
                "status": "complete",
            }
        ]
    )
    manifest_path = bronze / "manifest.parquet"
    if manifest_path.exists():
        manifest_row = pd.concat([pd.read_parquet(manifest_path), manifest_row])
    manifest_row.to_parquet(manifest_path, index=False)

    quality_row = pd.DataFrame(
        [
            {
                "year": year,
                "total_records": len(rows),
                "records_without_coordinates": sum(1 for r in rows if r[3] is None),
                "invalid_coordinates": 0,
                "outside_chicago_boundaries": 0,
                "community_area_mismatches": 0,
            }
        ]
    )
    quality_path = geo / "geography_quality.parquet"
    if quality_path.exists():
        quality_row = pd.concat([pd.read_parquet(quality_path), quality_row])
    quality_row.to_parquet(quality_path, index=False)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    _write_year(tmp_path, 2024, _ROWS_2024)
    _write_year(tmp_path, 2025, _ROWS_2025)
    return tmp_path


def _client(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    app = FastAPI()
    app.include_router(geographies_route.router)
    app.include_router(pulse_route.router)
    app.include_router(incidents_route.router)
    return TestClient(app, raise_server_exceptions=False)


# -- registry ----------------------------------------------------------------------------


def test_registry_is_ward_20_first_and_default() -> None:
    registry = load_geography_registry()

    assert registry.ward.ward_id == "20"
    assert registry.ward.source_dataset_id == "p293-wvbd"
    assert registry.ward.source_vintage == "2023"
    assert registry.default_id == "ward20"
    assert registry.geographies[0].geography_id == "ward20"
    assert registry.geographies[0].is_ward


# Every official community area that intersects Ward 20, by product decision (2026-09-13):
# small portions are kept because hiding them could conceal a disproportionate pattern.
ALL_INTERSECTING_AREAS = {
    "woodlawn": "42",
    "washington-park": "40",
    "englewood": "68",
    "fuller-park": "37",
    "new-city": "61",
    "greater-grand-crossing": "69",
    "hyde-park": "41",
    "grand-boulevard": "38",
    "kenwood": "39",
}


def test_registry_offers_every_intersecting_community_area_with_honest_status() -> None:
    by_id = {g.geography_id: g for g in load_geography_registry().geographies}

    for geography_id, community_area in ALL_INTERSECTING_AREAS.items():
        assert by_id[geography_id].is_available, geography_id
        assert by_id[geography_id].community_area == community_area
        assert by_id[geography_id].kind == "community_area_portion"
        # The measured size of the portion is published for every area, small ones included.
        assert by_id[geography_id].intersection_sq_mi is not None
        assert by_id[geography_id].share_of_area_in_ward_pct is not None

    pending = by_id["back-of-the-yards"]
    assert not pending.is_available
    assert pending.kind == "neighborhood_portion"
    assert pending.represented_by == "new-city"
    assert pending.community_area is None


def test_bronzeville_is_absent_from_the_registry() -> None:
    assert load_geography_registry().get("bronzeville") is None


def test_lookup_is_case_insensitive() -> None:
    registry = load_geography_registry()
    assert registry.get("Ward20") is registry.get("ward20")
    assert registry.get(" Woodlawn ") is registry.get("woodlawn")


# -- mask semantics ------------------------------------------------------------------------


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id": ["1", "2", "3", "4", "5"],
            "spatial_ward_current": ["20", "020", "5", "20", None],
            "spatial_community_area": ["42", "42", "42", "61", "42"],
        }
    )


def test_ward_mask_is_the_point_in_polygon_ward() -> None:
    registry = load_geography_registry()
    mask = geography_mask(_frame(), registry.get("ward20"))  # type: ignore[arg-type]
    assert mask.tolist() == [True, True, False, True, False]


def test_area_mask_is_the_portion_inside_the_ward() -> None:
    registry = load_geography_registry()
    mask = geography_mask(_frame(), registry.get("woodlawn"))  # type: ignore[arg-type]
    # Row 3 is Woodlawn but Ward 5; row 4 is Ward 20 but New City; row 5 has no assignment.
    assert mask.tolist() == [True, True, False, False, False]


def test_mask_refuses_a_pending_neighborhood() -> None:
    registry = load_geography_registry()
    # A pending neighborhood_portion raises for two reasons at once — no validated boundary
    # and no neighborhood filtering — never an empty mask.
    with pytest.raises(GeographyConfigError, match="no validated neighborhood boundary"):
        geography_mask(_frame(), registry.get("back-of-the-yards"))  # type: ignore[arg-type]


def test_mask_refuses_silver_without_spatial_columns() -> None:
    registry = load_geography_registry()
    with pytest.raises(GeographyConfigError, match="spatial_ward_current"):
        geography_mask(pd.DataFrame({"id": ["1"]}), registry.get("ward20"))  # type: ignore[arg-type]


# -- geography x year -----------------------------------------------------------------------


def test_ward_total_is_not_the_sum_of_selectable_areas(data_dir: Path) -> None:
    ward = build_overview(data_dir, 2025)
    woodlawn = build_overview(data_dir, 2025, "woodlawn")
    new_city = build_overview(data_dir, 2025, "new-city")
    englewood = build_overview(data_dir, 2025, "englewood")

    assert ward.total_incidents == 4  # a1-a4; a5 is Woodlawn outside the ward, a6/a7 nowhere
    assert woodlawn.total_incidents == 2
    assert new_city.total_incidents == 1
    assert englewood.total_incidents == 1


def test_same_geography_different_years_keep_the_same_boundary(data_dir: Path) -> None:
    """The 2023 ward map is applied to every year, so the prior-year comparison is like for
    like: 2024's b3 (Woodlawn, Ward 5) is excluded exactly as 2025's a5 is."""
    pulse = build_pulse(data_dir, 2025, "woodlawn")

    assert pulse.incidents.current == 2
    assert pulse.incidents.prior == 1  # b1 only; b3 is outside the ward
    assert pulse.provenance.ward_vintage == "2023"
    assert "inside the current Ward 20 footprint" in pulse.provenance.geography_scope


def test_pending_geography_is_unavailable_for_every_year(data_dir: Path) -> None:
    for year in (2024, 2025):
        with pytest.raises(OverviewDataUnavailable, match="not an official community area"):
            build_pulse(data_dir, year, "back-of-the-yards")


def test_area_with_no_records_in_a_year_is_an_honest_error_not_zero(data_dir: Path) -> None:
    # Fuller Park (37) has no rows in the fixture. That is "no records", not "0 incidents".
    with pytest.raises(OverviewDataUnavailable, match="No Fuller Park records"):
        build_overview(data_dir, 2025, "fuller-park")


def test_incidents_follow_the_same_geography_rule(data_dir: Path) -> None:
    ward = build_incident_page(data_dir, 2025, page_size=50)
    woodlawn = build_incident_page(data_dir, 2025, page_size=50, neighborhood_id="woodlawn")

    assert {r.id for r in ward.records} == {"a1", "a2", "a3", "a4"}
    assert {r.id for r in woodlawn.records} == {"a1", "a2"}


# -- HTTP ---------------------------------------------------------------------------------


def test_http_geographies_catalog(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    response = _client(data_dir, monkeypatch).get("/api/v1/geographies")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ward"]["ward_id"] == "20"
    assert payload["default_geography_id"] == "ward20"
    ids = [g["neighborhood_id"] for g in payload["geographies"]]
    assert ids[0] == "ward20"
    assert "bronzeville" not in ids
    pending = next(g for g in payload["geographies"] if g["neighborhood_id"] == "back-of-the-yards")
    assert pending["available"] is False
    assert pending["represented_by"] == "new-city"
    # Every intersecting community area is selectable; nothing is withheld from the catalog.
    assert payload["other_community_areas_in_ward"] == []
    assert {g["community_area"] for g in payload["geographies"] if g["available"]} == {
        None,  # the ward itself
        *ALL_INTERSECTING_AREAS.values(),
    }


def test_http_pulse_default_and_area(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(data_dir, monkeypatch)

    ward = client.get("/api/v1/pulse/ward20?year=2025").json()
    area = client.get("/api/v1/pulse/new-city?year=2025").json()

    assert ward["neighborhood_name"] == "Ward 20"
    assert ward["incidents"]["current"] == 4
    assert area["neighborhood_name"] == "New City"
    assert area["incidents"]["current"] == 1
    assert area["provenance"]["geography_scope"].startswith("Figures cover only the part")


def test_http_incidents_export_names_the_geography(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = _client(data_dir, monkeypatch).get(
        "/api/v1/incidents/englewood/export.csv?year=2025"
    )

    assert response.status_code == 200
    assert 'filename="englewood-incidents-2025.csv"' in response.headers["content-disposition"]
    assert response.text.count("\n") == 2  # header + a4


# -- coverage invariants (V2-002A) ----------------------------------------------------------
#
# The resident-facing drilldowns need not partition the ward. The ward total must therefore
# be computed from the ward polygon alone, every drilldown must be clipped to the ward, and
# no configuration of drilldowns — overlapping, missing, or pending — may change the ward
# total or turn an unsupported geography into a zero.


def _ward_frame() -> pd.DataFrame:
    """Rows chosen so every invariant has a row that would break it."""
    return pd.DataFrame(
        {
            "id": ["w1", "w2", "w3", "w4", "w5", "w6", "w7", "w8"],
            #                  in-ward: w1..w6 ;  outside: w7 (Ward 5), w8 (no assignment)
            "spatial_ward_current": ["20", "20", "20", "20", "20", "20", "5", None],
            #  Woodlawn, New City, Greater Grand Crossing, Kenwood sliver, CA missing though
            #  ward assigned, Englewood ; Woodlawn (Ward 5) ; nothing
            "spatial_community_area": ["42", "61", "69", "39", None, "68", "42", None],
        }
    )


def _write_registry(tmp_path: Path, areas_yaml: str) -> Path:
    """A registry file with the real ward block and a caller-supplied `areas` list."""
    path = tmp_path / "geographies.yml"
    path.write_text(
        "ward:\n"
        '  ward_id: "20"\n'
        "  geography_id: ward20\n"
        '  display_name: "Ward 20"\n'
        '  source: "test"\n'
        '  source_vintage: "2023"\n'
        "areas:\n" + areas_yaml,
        encoding="utf-8",
    )
    return path


def test_ward_total_covers_every_in_ward_record_regardless_of_drilldowns() -> None:
    registry = load_geography_registry()
    frame = _ward_frame()

    ward_mask = geography_mask(frame, registry.get("ward20"))  # type: ignore[arg-type]
    # w5 has a ward but no community area, so it belongs to no drilldown. It is still
    # Ward 20 and still counted; the ward mask never looks at the area column.
    assert frame.loc[ward_mask, "id"].tolist() == ["w1", "w2", "w3", "w4", "w5", "w6"]


def test_every_drilldown_is_a_strict_subset_of_the_ward() -> None:
    registry = load_geography_registry()
    frame = _ward_frame()
    ward_mask = geography_mask(frame, registry.get("ward20"))  # type: ignore[arg-type]

    union = pd.Series(False, index=frame.index)
    for geography in registry.geographies:
        if not geography.is_available or geography.is_ward:
            continue
        mask = geography_mask(frame, geography)
        assert not (mask & ~ward_mask).any(), f"{geography.geography_id} leaks outside the ward"
        union |= mask
    # Drilldowns do not have to be exhaustive: w5 is in the ward but in no drilldown.
    assert set(frame.loc[ward_mask & ~union, "id"]) == {"w5"}
    # The small portions are real drilldowns: w3 (Greater Grand Crossing) and w4 (Kenwood).
    ggc = geography_mask(frame, registry.get("greater-grand-crossing"))  # type: ignore[arg-type]
    kenwood = geography_mask(frame, registry.get("kenwood"))  # type: ignore[arg-type]
    assert frame.loc[ggc, "id"].tolist() == ["w3"]
    assert frame.loc[kenwood, "id"].tolist() == ["w4"]
    # w7 is Woodlawn but Ward 5: no drilldown may claim it.
    assert not union.loc[frame["id"] == "w7"].any()


def test_overlapping_drilldowns_cannot_change_the_ward_total(tmp_path: Path) -> None:
    """Two areas both pointing at community area 61 overlap completely. The ward total is
    computed from the ward column alone, so it is identical with or without them."""
    load_geography_registry.cache_clear()
    try:
        overlapping = _write_registry(
            tmp_path,
            "  - {geography_id: new-city, display_name: New City, kind: community_area_portion,"
            ' community_area: "61", status: active}\n'
            "  - {geography_id: yards-overlap, display_name: Overlap, kind: community_area_portion,"
            ' community_area: "61", status: active}\n',
        )
        registry = load_geography_registry(overlapping)
        frame = _ward_frame()
        ward = registry.get("ward20")
        ward_total = int(geography_mask(frame, ward).sum())  # type: ignore[arg-type]
        a = geography_mask(frame, registry.get("new-city"))  # type: ignore[arg-type]
        b = geography_mask(frame, registry.get("yards-overlap"))  # type: ignore[arg-type]

        assert ward_total == 6
        assert a.tolist() == b.tolist()  # fully overlapping drilldowns
        assert int(a.sum()) + int(b.sum()) == 2  # naive summing WOULD double count...
        assert int(geography_mask(frame, ward).sum()) == 6  # type: ignore[arg-type]
    finally:
        load_geography_registry.cache_clear()


def test_ward_total_is_independent_of_the_area_list(tmp_path: Path) -> None:
    load_geography_registry.cache_clear()
    try:
        empty = _write_registry(tmp_path, "  []\n")
        registry = load_geography_registry(empty)
        frame = _ward_frame()
        ward = registry.get("ward20")
        assert int(geography_mask(frame, ward).sum()) == 6  # type: ignore[arg-type]
        assert len(registry.geographies) == 1
    finally:
        load_geography_registry.cache_clear()


def test_active_neighborhood_portion_fails_loudly_not_silently(tmp_path: Path) -> None:
    """Silver carries no neighborhood assignment. If a neighborhood_portion were ever marked
    active without the filtering being built, it must raise, never return an empty mask."""
    load_geography_registry.cache_clear()
    try:
        path = _write_registry(
            tmp_path,
            "  - {geography_id: some-neighborhood, display_name: Some, kind: neighborhood_portion,"
            " status: active}\n",
        )
        registry = load_geography_registry(path)
        geography = registry.get("some-neighborhood")
        with pytest.raises(GeographyConfigError, match="neighborhood_portion filtering"):
            geography_mask(_ward_frame(), geography)  # type: ignore[arg-type]
    finally:
        load_geography_registry.cache_clear()


def test_unknown_kind_is_rejected_at_load(tmp_path: Path) -> None:
    load_geography_registry.cache_clear()
    try:
        path = _write_registry(
            tmp_path,
            "  - {geography_id: x, display_name: X, kind: tract_portion, status: active}\n",
        )
        with pytest.raises(GeographyConfigError, match="unknown kind"):
            load_geography_registry(path)
    finally:
        load_geography_registry.cache_clear()


def test_provenance_names_the_boundary_system(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _client(data_dir, monkeypatch).get("/api/v1/geographies").json()
    by_id = {g["neighborhood_id"]: g for g in payload["geographies"]}

    assert by_id["ward20"]["kind"] == "ward"
    assert by_id["ward20"]["boundary_system"] == "City of Chicago ward map"
    assert by_id["woodlawn"]["kind"] == "community_area_portion"
    assert "community area 42" in by_id["woodlawn"]["boundary_source"]
    assert by_id["back-of-the-yards"]["kind"] == "neighborhood_portion"
    assert by_id["back-of-the-yards"]["boundary_source"] is None  # nothing answerable
    assert "distinct from New City" in by_id["back-of-the-yards"]["reason"]
    # The small portions remain measured, and the measurements travel with the catalog.
    assert by_id["greater-grand-crossing"]["intersection_sq_mi"] == pytest.approx(0.324)
    assert by_id["greater-grand-crossing"]["share_of_area_in_ward_pct"] == pytest.approx(9.13)
    assert by_id["kenwood"]["share_of_ward_area_pct"] == pytest.approx(0.27)


def test_small_portion_scope_note_states_its_size_not_a_verdict(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A small area's note says how small it is (a fact) and nothing about significance."""
    _write_year(data_dir, 2023, [("k1", "2023-01-10", "THEFT", "20", "39", "20")])
    response = _client(data_dir, monkeypatch).get("/api/v1/pulse/kenwood?year=2023")

    assert response.status_code == 200
    scope = response.json()["provenance"]["geography_scope"]
    assert "only the part of the Kenwood community area" in scope
    assert "current Ward 20 footprint" in scope
    assert "0.01 square miles" in scope and "1.4% of Kenwood" in scope
    assert "0.3% of Ward 20" in scope  # never rounded to "0%"
    assert "the Ward 20 part of Kenwood" in response.json()["headline"]
    assert response.json()["provenance"]["boundary_type"] == "community_area_portion"
