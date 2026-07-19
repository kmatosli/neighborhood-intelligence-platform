"""Overview presentation + API tests, against a synthetic Silver/Bronze fixture."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bw_observatory.api.routes import overview as overview_route
from bw_observatory.presentation.models import OverviewResponse
from bw_observatory.presentation.overview import (
    OverviewDataUnavailable,
    build_overview,
    count_categories,
    load_crime_categories,
    verify_bronze_integrity,
)


def bronze_rows() -> list[dict[str, Any]]:
    """Six Woodlawn incidents plus two that are not in Woodlawn."""
    return [
        {"id": "1", "primary_type": "BATTERY", "date": "2024-01-15T10:00:00.000"},
        {"id": "2", "primary_type": "ROBBERY", "date": "2024-01-20T10:00:00.000"},
        {"id": "3", "primary_type": "MOTOR VEHICLE THEFT", "date": "2024-03-02T10:00:00.000"},
        {"id": "4", "primary_type": "BURGLARY", "date": "2024-07-04T10:00:00.000"},
        {"id": "5", "primary_type": "THEFT", "date": "2024-12-31T10:00:00.000"},
        {"id": "6", "primary_type": "NARCOTICS", "date": "2024-07-05T10:00:00.000"},
        {"id": "7", "primary_type": "BATTERY", "date": "2024-05-05T10:00:00.000"},  # not Woodlawn
        {"id": "8", "primary_type": "THEFT", "date": "2024-05-06T10:00:00.000"},  # not Woodlawn
    ]


def silver_rows() -> list[dict[str, Any]]:
    woodlawn = [True] * 6 + [False, False]
    rows = []
    for index, flag in enumerate(woodlawn, start=1):
        rows.append(
            {
                "id": str(index),
                "source_year": 2024,
                # A source community_area that disagrees with the polygon: filtering must use
                # the spatial flag, not this.
                "source_community_area": "42" if index != 7 else "99",
                "spatial_community_area": "42" if flag else "43",
                "neighborhood_woodlawn": flag,
                "neighborhood_bronzeville": None,
                "geography_status": "assigned",
                "community_area_mismatch": False,
                "boundary_vintage": "community_area:1920;ward:2023",
                "enriched_at": "2026-07-12T00:00:00+00:00",
            }
        )
    return rows


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    bronze = tmp_path / "bronze" / "crime"
    silver = tmp_path / "silver" / "crime" / "crime_with_geography"
    geography = tmp_path / "silver" / "geography"
    for directory in (bronze, silver, geography):
        directory.mkdir(parents=True, exist_ok=True)

    frame = pd.DataFrame(bronze_rows()).astype("string")
    bronze_file = bronze / "2024.parquet"
    frame.to_parquet(bronze_file, index=False)

    import hashlib

    checksum = hashlib.sha256(bronze_file.read_bytes()).hexdigest()
    pd.DataFrame(
        [
            {
                "year": 2024,
                "rows": len(frame),
                "download_started": "2026-07-11T22:54:14+00:00",
                "download_completed": "2026-07-11T22:55:02+00:00",
                "api_version": "socrata-resource-v2.1",
                "dataset_last_updated": "2026-07-11T12:11:28+00:00",
                "checksum": checksum,
                "status": "complete",
            }
        ]
    ).to_parquet(bronze / "manifest.parquet", index=False)

    pd.DataFrame(silver_rows()).to_parquet(silver / "2024.parquet", index=False)

    pd.DataFrame(
        [
            {
                "year": 2024,
                "total_records": 8,
                "records_without_coordinates": 1,
                "invalid_coordinates": 0,
                "outside_chicago_boundaries": 2,
                "community_area_mismatches": 1,
            }
        ]
    ).to_parquet(geography / "geography_quality.parquet", index=False)

    return tmp_path


# -- grouping configuration ------------------------------------------------------------


def test_crime_groupings_are_deterministic() -> None:
    first = load_crime_categories()
    second = load_crime_categories()

    keys = [c.key for c in first]
    assert keys == [c.key for c in second]
    assert keys == ["violent_crime", "property_crime", "vehicle_related_crime", "burglary"]
    assert first[0].primary_types == second[0].primary_types


def test_groupings_come_from_config_not_code() -> None:
    violent = next(c for c in load_crime_categories() if c.key == "violent_crime")
    assert "HOMICIDE" in violent.primary_types
    assert "BATTERY" in violent.primary_types
    # A non-violent type must not leak into the violent set.
    assert "THEFT" not in violent.primary_types


def test_category_counts_use_the_config(data_dir: Path) -> None:
    response = build_overview(data_dir, 2024)
    counts = {c.key: c.count for c in response.categories}

    assert counts["violent_crime"] == 2  # BATTERY + ROBBERY
    assert counts["vehicle_related_crime"] == 1  # MOTOR VEHICLE THEFT
    assert counts["burglary"] == 1
    assert counts["property_crime"] == 3  # MVT + BURGLARY + THEFT


def test_categories_do_not_sum_to_the_total(data_dir: Path) -> None:
    """NARCOTICS belongs to no category — the categories are not a breakdown of the total."""
    response = build_overview(data_dir, 2024)
    assert response.total_incidents == 6
    assert sum(c.count for c in response.categories) != response.total_incidents


# -- Woodlawn filtering ----------------------------------------------------------------


def test_woodlawn_filtering_uses_the_spatial_flag(data_dir: Path) -> None:
    """Filtering must use point-in-polygon, not the city's reported community_area."""
    response = build_overview(data_dir, 2024)

    # Record 7 is NOT in Woodlawn spatially, though its source community_area says 99 and
    # records 1-6 are. Only the six spatially-assigned records count.
    assert response.total_incidents == 6


def test_endpoint_returns_real_woodlawn_data(data_dir: Path) -> None:
    response = build_overview(data_dir, 2024)

    assert response.neighborhood_id == "woodlawn"
    assert response.neighborhood_name == "Woodlawn"
    assert response.year == 2024
    assert response.provenance.source_dataset_id == "ijzp-q8t2"
    assert response.provenance.boundary_type == "official_community_area"
    assert response.provenance.data_through == "2024-12-31"
    assert response.provenance.last_refresh == "2026-07-11"


# -- monthly trend ---------------------------------------------------------------------


def test_annual_total_equals_the_sum_of_the_monthly_trend(data_dir: Path) -> None:
    response = build_overview(data_dir, 2024)

    assert len(response.monthly_trend) == 12
    assert sum(point.incidents for point in response.monthly_trend) == response.total_incidents


def test_months_with_no_incidents_are_real_zeros(data_dir: Path) -> None:
    response = build_overview(data_dir, 2024)
    february = response.monthly_trend[1]

    assert february.month_label == "Feb"
    assert february.incidents == 0


# -- comparison ------------------------------------------------------------------------


def test_comparison_is_null_when_the_prior_year_is_not_enriched(data_dir: Path) -> None:
    response = build_overview(data_dir, 2024)

    assert response.comparison_available is False
    assert response.total_incidents_prior_year is None
    assert all(c.prior_year_count is None for c in response.categories)
    assert "2023" in response.comparison_note


def test_headline_makes_no_directional_claim_without_a_comparison(data_dir: Path) -> None:
    headline = build_overview(data_dir, 2024).headline.lower()

    assert "not available yet" in headline
    for forbidden in ("increased", "decreased", "rose", "fell", "up from", "down from"):
        assert forbidden not in headline


# -- Bronzeville -----------------------------------------------------------------------


def test_bronzeville_is_never_fabricated(data_dir: Path) -> None:
    with pytest.raises(OverviewDataUnavailable, match="Boundary pending approval"):
        build_overview(data_dir, 2024, "bronzeville")


def test_bronzeville_is_reported_unavailable_not_zero(data_dir: Path) -> None:
    response = build_overview(data_dir, 2024)
    bronzeville = next(n for n in response.neighborhoods if n.neighborhood_id == "bronzeville")

    assert bronzeville.available is False
    assert bronzeville.reason == "Boundary pending approval."
    # There is no count field to be zero — availability is the only thing published.
    assert not hasattr(bronzeville, "count")


# -- quality + integrity ---------------------------------------------------------------


def test_bronze_integrity_is_verified(data_dir: Path) -> None:
    assert verify_bronze_integrity(data_dir, 2024) is True
    assert build_overview(data_dir, 2024).data_quality.bronze_integrity_verified is True


def test_bronze_tampering_is_detected(data_dir: Path) -> None:
    target = data_dir / "bronze" / "crime" / "2024.parquet"
    rows = bronze_rows() + [{"id": "9", "primary_type": "THEFT", "date": "2024-02-02T00:00:00.000"}]
    pd.DataFrame(rows).astype("string").to_parquet(target, index=False)

    assert verify_bronze_integrity(data_dir, 2024) is False


def test_data_quality_counts_come_from_the_quality_report(data_dir: Path) -> None:
    quality = build_overview(data_dir, 2024).data_quality

    assert quality.total_bronze_records_year == 8
    assert quality.records_without_coordinates == 1
    assert quality.records_outside_boundaries == 2
    assert quality.community_area_mismatches == 1


# -- response model --------------------------------------------------------------------


def test_response_validates_against_the_model(data_dir: Path) -> None:
    payload = build_overview(data_dir, 2024).model_dump()
    revalidated = OverviewResponse.model_validate(payload)

    assert revalidated.total_incidents == 6
    assert revalidated.monthly_trend[0].month == 1


# -- HTTP ------------------------------------------------------------------------------


def client_for(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.chdir(Path(__file__).resolve().parents[1])  # config/ lives at the repo root
    monkeypatch.setenv("DATA_DIR", str(data_dir))

    app = FastAPI()
    app.include_router(overview_route.router)
    return TestClient(app, raise_server_exceptions=False)


def test_http_endpoint_returns_woodlawn(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = client_for(data_dir, monkeypatch)

    response = client.get("/api/v1/overview/woodlawn?year=2024")

    assert response.status_code == 200
    payload = response.json()
    assert payload["neighborhood_name"] == "Woodlawn"
    assert payload["total_incidents"] == 6
    assert payload["comparison_available"] is False
    assert payload["total_incidents_prior_year"] is None


def test_http_bronzeville_returns_an_honest_404(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = client_for(data_dir, monkeypatch)

    response = client.get("/api/v1/overview/bronzeville?year=2024")

    assert response.status_code == 404
    assert "Boundary pending approval" in response.json()["detail"]


def test_http_missing_year_returns_an_honest_error(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = client_for(data_dir, monkeypatch)

    response = client.get("/api/v1/overview/woodlawn?year=2019")

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "2019" in detail
    assert "enrich_crime_geography" in detail  # tells the operator how to fix it


def test_count_categories_on_an_empty_frame() -> None:
    empty = pd.DataFrame({"primary_type": pd.Series(dtype="string")})
    counts = count_categories(empty)

    assert set(counts) == {"violent_crime", "property_crime", "vehicle_related_crime", "burglary"}
    assert all(value == 0 for value in counts.values())
