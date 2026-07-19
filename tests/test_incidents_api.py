"""Incidents endpoint tests, against a synthetic Bronze/Silver fixture."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bw_observatory.api.routes import incidents as incidents_route
from bw_observatory.presentation.incidents import (
    MAX_PAGE_SIZE,
    build_incident_csv,
    build_incident_page,
)
from bw_observatory.presentation.overview import OverviewDataUnavailable


def bronze_rows() -> list[dict[str, Any]]:
    """Five Woodlawn incidents (ids 1-5) and two that are not in Woodlawn (6-7)."""
    return [
        {
            "id": "1",
            "case_number": "JA0001",
            "date": "2026-01-05T08:00:00.000",
            "updated_on": "2026-01-12T00:00:00.000",
            "block": "063XX S BLACKSTONE AVE",
            "primary_type": "BATTERY",
            "description": "SIMPLE",
            "location_description": "STREET",
            "arrest": "false",
            "domestic": "false",
            "beat": "0313",
            "district": "003",
            "ward": "20",
            "community_area": "42",
            "latitude": "41.78",
            "longitude": "-87.59",
        },
        {
            "id": "2",
            "case_number": "JA0002",
            "date": "2026-03-10T12:00:00.000",
            "updated_on": "2026-03-17T00:00:00.000",
            "block": "064XX S KIMBARK AVE",
            "primary_type": "THEFT",
            "description": "OVER $500",
            "location_description": "STREET",
            "arrest": "true",
            "domestic": "false",
            "beat": "0314",
            "district": "003",
            "ward": "20",
            "community_area": "42",
            "latitude": "41.78",
            "longitude": "-87.59",
        },
        {
            "id": "3",
            "case_number": "JA0003",
            "date": "2026-05-20T22:10:00.000",
            "updated_on": "2026-05-27T00:00:00.000",
            "block": "061XX S UNIVERSITY AVE",
            "primary_type": "BURGLARY",
            "description": "FORCIBLE ENTRY",
            "location_description": "RESIDENCE",
            "arrest": "false",
            "domestic": "false",
            "beat": "0312",
            "district": "003",
            "ward": "5",
            "community_area": "42",
            "latitude": "41.78",
            "longitude": "-87.60",
        },
        {
            "id": "4",
            "case_number": "JA0004",
            "date": "2026-07-02T22:10:00.000",
            "updated_on": "2026-07-09T00:00:00.000",
            "block": "063XX S WOODLAWN AVE",
            "primary_type": "MOTOR VEHICLE THEFT",
            "description": "AUTOMOBILE",
            "location_description": "STREET",
            "arrest": "false",
            "domestic": "false",
            "beat": "0313",
            "district": "003",
            "ward": "20",
            "community_area": "42",
            "latitude": "41.78",
            "longitude": "-87.60",
        },
        {
            "id": "5",
            "case_number": "JA0005",
            "date": "2026-07-02T09:00:00.000",
            "updated_on": "2026-07-09T00:00:00.000",
            "block": "065XX S ELLIS AVE",
            "primary_type": "THEFT",
            "description": "RETAIL",
            "location_description": "STORE",
            "arrest": "true",
            "domestic": "false",
            "beat": "0321",
            "district": "003",
            "ward": "20",
            "community_area": "42",
            "latitude": "41.77",
            "longitude": "-87.60",
        },
        {
            "id": "6",
            "case_number": "JA0006",
            "date": "2026-06-01T10:00:00.000",
            "updated_on": "2026-06-08T00:00:00.000",
            "block": "001XX N STATE ST",
            "primary_type": "THEFT",
            "description": "RETAIL",
            "location_description": "STORE",
            "arrest": "false",
            "domestic": "false",
            "beat": "0111",
            "district": "001",
            "ward": "42",
            "community_area": "32",
            "latitude": "41.88",
            "longitude": "-87.62",
        },
        {
            "id": "7",
            "case_number": "JA0007",
            "date": "2026-06-02T10:00:00.000",
            "updated_on": "2026-06-09T00:00:00.000",
            "block": "002XX N STATE ST",
            "primary_type": "BATTERY",
            "description": "SIMPLE",
            "location_description": "STREET",
            "arrest": "false",
            "domestic": "false",
            "beat": "0112",
            "district": "001",
            "ward": "42",
            "community_area": "32",
            "latitude": "41.88",
            "longitude": "-87.62",
        },
    ]


def silver_rows() -> list[dict[str, Any]]:
    return [
        {
            "id": str(index),
            # ids 1-5 are in Woodlawn; 6-7 are not.
            "neighborhood_woodlawn": index <= 5,
            "neighborhood_bronzeville": None,
            "geography_status": "assigned",
        }
        for index in range(1, 8)
    ]


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    bronze = tmp_path / "bronze" / "crime"
    silver = tmp_path / "silver" / "crime" / "crime_with_geography"
    bronze.mkdir(parents=True, exist_ok=True)
    silver.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(bronze_rows()).astype("string").to_parquet(bronze / "2026.parquet", index=False)
    pd.DataFrame(silver_rows()).to_parquet(silver / "2026.parquet", index=False)
    return tmp_path


def client_for(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    app = FastAPI()
    app.include_router(incidents_route.router)
    return TestClient(app, raise_server_exceptions=False)


# -- Woodlawn-only filter ----------------------------------------------------------------


def test_only_woodlawn_records_are_returned(data_dir: Path) -> None:
    page = build_incident_page(data_dir, 2026, page_size=50)

    assert page.total_records == 5  # not 7 — ids 6 and 7 are outside Woodlawn
    assert {r.id for r in page.records} == {"1", "2", "3", "4", "5"}


def test_filter_uses_the_spatial_flag_not_the_reported_community_area(data_dir: Path) -> None:
    page = build_incident_page(data_dir, 2026, page_size=50)
    # Every returned record was assigned by point-in-polygon, and each carries its status.
    assert all(r.geography_status == "assigned" for r in page.records)


# -- ordering ----------------------------------------------------------------------------


def test_records_are_newest_first(data_dir: Path) -> None:
    page = build_incident_page(data_dir, 2026, page_size=50)
    dates = [r.date for r in page.records]

    assert dates == sorted(dates, reverse=True)
    assert page.records[0].date.startswith("2026-07-02T22:10")  # the newest incident
    assert page.records[0].id == "4"


def test_same_timestamp_is_broken_by_id_so_paging_is_stable(data_dir: Path) -> None:
    first = build_incident_page(data_dir, 2026, page=1, page_size=1).records[0]
    second = build_incident_page(data_dir, 2026, page=2, page_size=1).records[0]

    assert first.id != second.id  # no repeat across page boundaries


# -- pagination --------------------------------------------------------------------------


def test_pagination_splits_the_result_set(data_dir: Path) -> None:
    first = build_incident_page(data_dir, 2026, page=1, page_size=2)
    second = build_incident_page(data_dir, 2026, page=2, page_size=2)
    third = build_incident_page(data_dir, 2026, page=3, page_size=2)

    assert first.total_records == 5
    assert first.total_pages == 3
    assert len(first.records) == 2
    assert len(second.records) == 2
    assert len(third.records) == 1  # the remainder

    ids = [r.id for r in first.records + second.records + third.records]
    assert len(set(ids)) == 5  # no duplicates across pages


def test_page_beyond_the_end_is_empty_not_an_error(data_dir: Path) -> None:
    page = build_incident_page(data_dir, 2026, page=99, page_size=25)

    assert page.records == []
    assert page.total_records == 5


def test_invalid_page_size_is_rejected(data_dir: Path) -> None:
    with pytest.raises(ValueError, match="page_size"):
        build_incident_page(data_dir, 2026, page_size=MAX_PAGE_SIZE + 1)

    with pytest.raises(ValueError, match="page_size"):
        build_incident_page(data_dir, 2026, page_size=0)


def test_invalid_page_is_rejected(data_dir: Path) -> None:
    with pytest.raises(ValueError, match="page"):
        build_incident_page(data_dir, 2026, page=0)


# -- filters -----------------------------------------------------------------------------


def test_primary_type_filter(data_dir: Path) -> None:
    page = build_incident_page(data_dir, 2026, primary_type="theft")  # case-insensitive

    assert page.total_records == 2
    assert {r.id for r in page.records} == {"2", "5"}


def test_block_filter_is_a_substring_search(data_dir: Path) -> None:
    page = build_incident_page(data_dir, 2026, block="blackstone")

    assert page.total_records == 1
    assert page.records[0].id == "1"


def test_date_range_filter_includes_the_whole_end_day(data_dir: Path) -> None:
    page = build_incident_page(data_dir, 2026, date_from="2026-07-02", date_to="2026-07-02")

    # Both 2 July incidents, including the one at 22:10.
    assert page.total_records == 2
    assert {r.id for r in page.records} == {"4", "5"}


def test_arrest_filter(data_dir: Path) -> None:
    with_arrest = build_incident_page(data_dir, 2026, arrest=True)
    without_arrest = build_incident_page(data_dir, 2026, arrest=False)

    assert {r.id for r in with_arrest.records} == {"2", "5"}
    assert {r.id for r in without_arrest.records} == {"1", "3", "4"}
    assert all(r.arrest is True for r in with_arrest.records)


# -- new filters: broad category, search, ward/district, sorting, CSV --------------------


def test_broad_category_filter(data_dir: Path) -> None:
    # THEFT, BURGLARY, MOTOR VEHICLE THEFT are all Property; BATTERY is Violent.
    page = build_incident_page(data_dir, 2026, broad_category="property_crime", page_size=50)
    assert {r.id for r in page.records} == {"2", "3", "4", "5"}

    violent = build_incident_page(data_dir, 2026, broad_category="violent_crime", page_size=50)
    assert {r.id for r in violent.records} == {"1"}


def test_free_text_search_scans_multiple_columns(data_dir: Path) -> None:
    # "RESIDENCE" appears only in record 3's location description.
    page = build_incident_page(data_dir, 2026, search="residence", page_size=50)
    assert {r.id for r in page.records} == {"3"}

    # "KIMBARK" appears only in record 2's block.
    block_hit = build_incident_page(data_dir, 2026, search="kimbark", page_size=50)
    assert {r.id for r in block_hit.records} == {"2"}


def test_ward_and_district_filters(data_dir: Path) -> None:
    ward5 = build_incident_page(data_dir, 2026, ward="5", page_size=50)
    assert {r.id for r in ward5.records} == {"3"}

    # District "003" matches with or without the leading zero.
    district3 = build_incident_page(data_dir, 2026, district="3", page_size=50)
    assert {r.id for r in district3.records} == {"1", "2", "3", "4", "5"}


def test_sorting_by_block_ascending(data_dir: Path) -> None:
    page = build_incident_page(data_dir, 2026, sort_by="block", sort_dir="asc", page_size=50)
    blocks = [r.block for r in page.records]
    assert blocks == sorted(blocks)


def test_sorting_by_primary_type(data_dir: Path) -> None:
    page = build_incident_page(data_dir, 2026, sort_by="primary_type", sort_dir="asc", page_size=50)
    types = [r.primary_type for r in page.records]
    assert types == sorted(types)


def test_csv_export_has_header_and_all_filtered_rows(data_dir: Path) -> None:
    csv = build_incident_csv(data_dir, 2026)
    lines = [line for line in csv.splitlines() if line.strip()]
    # Header + 5 Woodlawn rows (6 and 7 are outside Woodlawn and excluded).
    assert lines[0].split(",")[:3] == ["date", "block", "primary_type"]
    assert len(lines) == 1 + 5


def test_csv_export_respects_filters(data_dir: Path) -> None:
    csv = build_incident_csv(data_dir, 2026, broad_category="violent_crime")
    lines = [line for line in csv.splitlines() if line.strip()]
    assert len(lines) == 1 + 1  # header + record 1 only


def test_http_csv_export(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = client_for(data_dir, monkeypatch)
    response = client.get("/api/v1/incidents/woodlawn/export.csv?year=2026&arrest=true")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers.get("content-disposition", "")
    lines = [line for line in response.text.splitlines() if line.strip()]
    assert len(lines) == 1 + 2  # header + the two arrests (records 2, 5)


def test_http_invalid_sort_is_rejected(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = client_for(data_dir, monkeypatch)
    response = client.get("/api/v1/incidents/woodlawn?year=2026&sort_by=latitude")
    assert response.status_code == 422


# -- missing data ------------------------------------------------------------------------


def test_year_without_silver_data_is_an_honest_error(data_dir: Path) -> None:
    with pytest.raises(OverviewDataUnavailable, match="2025"):
        build_incident_page(data_dir, 2025)


# -- HTTP --------------------------------------------------------------------------------


def test_http_returns_a_page(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = client_for(data_dir, monkeypatch)

    response = client.get("/api/v1/incidents/woodlawn?year=2026&page=1&page_size=2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_records"] == 5
    assert payload["total_pages"] == 3
    assert len(payload["records"]) == 2
    assert payload["records"][0]["primary_type"] == "MOTOR VEHICLE THEFT"


def test_http_rejects_an_oversized_page(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = client_for(data_dir, monkeypatch)

    response = client.get("/api/v1/incidents/woodlawn?year=2026&page_size=500")

    assert response.status_code == 422  # FastAPI bounds the query parameter


def test_http_bronzeville_is_blocked_not_empty(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = client_for(data_dir, monkeypatch)

    response = client.get("/api/v1/incidents/bronzeville?year=2026")

    # An empty list would read as "no incidents in Bronzeville". It must not.
    assert response.status_code == 404
    assert "Boundary pending approval" in response.json()["detail"]


def test_http_missing_year_is_an_honest_404(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = client_for(data_dir, monkeypatch)

    response = client.get("/api/v1/incidents/woodlawn?year=2025")

    assert response.status_code == 404
    assert "2025" in response.json()["detail"]
