"""Neighborhood Pulse tests against a synthetic Silver/Bronze fixture.

The current year (2026) is deliberately partial (data through 15 March) so the same-period
comparison logic is exercised: it must compare 1 Jan - 15 Mar 2026 against 1 Jan - 15 Mar
2025, never against the whole of 2025.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bw_observatory.api.routes import pulse as pulse_route
from bw_observatory.presentation.overview import broad_category_of
from bw_observatory.presentation.pulse import build_pulse, same_period_cutoff

# -- fixture data ----------------------------------------------------------------------

# 2026 Woodlawn incidents, all within 1 Jan - 15 March (a partial year). Two trailing rows
# are NOT in Woodlawn, to prove the spatial flag — not the source community_area — is used.
_CURRENT = [
    ("c1", "2026-01-10", "BATTERY", "true", "0321", "001XX W 63RD ST", True),
    ("c2", "2026-01-20", "THEFT", "false", "0321", "001XX W 63RD ST", True),
    ("c3", "2026-02-05", "THEFT", "false", "0321", "002XX E 61ST ST", True),
    ("c4", "2026-02-15", "CRIMINAL DAMAGE", "false", "0313", "003XX E 60TH ST", True),
    ("c5", "2026-03-01", "MOTOR VEHICLE THEFT", "true", "0321", "001XX W 63RD ST", True),
    ("c6", "2026-03-10", "NARCOTICS", "true", "0313", "004XX E 63RD ST", True),
    ("c7", "2026-03-15", "ROBBERY", "false", "0321", "001XX W 63RD ST", True),
    # An unmapped primary type must land in "Other", never be dropped.
    ("c8", "2026-03-15", "SPACE PIRACY", "false", "0321", "005XX E 62ND ST", True),
    ("c9", "2026-02-01", "THEFT", "false", "0100", "999XX W 1ST ST", False),
    ("c10", "2026-02-02", "BATTERY", "false", "0100", "999XX W 1ST ST", False),
]

# 2025 Woodlawn incidents. p4/p5 fall AFTER 15 March and must be excluded from the
# same-period comparison, even though they are in the same calendar year.
_PRIOR = [
    ("p1", "2025-01-15", "THEFT", "false", "0321", "001XX W 63RD ST", True),
    ("p2", "2025-02-10", "BATTERY", "true", "0313", "003XX E 60TH ST", True),
    ("p3", "2025-03-14", "THEFT", "false", "0321", "002XX E 61ST ST", True),
    ("p4", "2025-06-01", "THEFT", "false", "0321", "001XX W 63RD ST", True),
    ("p5", "2025-12-01", "ROBBERY", "false", "0321", "001XX W 63RD ST", True),
    ("p6", "2025-02-02", "BATTERY", "false", "0100", "999XX W 1ST ST", False),
]

_BRONZE_COLS = ["id", "date", "primary_type", "arrest", "beat", "block"]


def _bronze_frame(rows: list[tuple[Any, ...]]) -> pd.DataFrame:
    records = [
        {
            "id": r[0],
            "date": f"{r[1]}T12:00:00.000",
            "primary_type": r[2],
            "arrest": r[3],
            "beat": r[4],
            "block": r[5],
        }
        for r in rows
    ]
    return pd.DataFrame(records).astype("string")


def _silver_frame(rows: list[tuple[Any, ...]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id": r[0],
                "neighborhood_woodlawn": r[6],
                "neighborhood_bronzeville": None,
                "boundary_vintage": "community_area:1920;ward:2023",
            }
            for r in rows
        ]
    )


def _write_year(root: Path, year: int, rows: list[tuple[Any, ...]]) -> None:
    bronze = root / "bronze" / "crime"
    silver = root / "silver" / "crime" / "crime_with_geography"
    geo = root / "silver" / "geography"
    for directory in (bronze, silver, geo):
        directory.mkdir(parents=True, exist_ok=True)

    bronze_file = bronze / f"{year}.parquet"
    _bronze_frame(rows).to_parquet(bronze_file, index=False)
    _silver_frame(rows).to_parquet(silver / f"{year}.parquet", index=False)

    checksum = hashlib.sha256(bronze_file.read_bytes()).hexdigest()
    manifest_path = bronze / "manifest.parquet"
    manifest_row = {
        "year": year,
        "rows": len(rows),
        "download_completed": f"{year}-04-01T00:00:00+00:00",
        "checksum": checksum,
        "status": "complete",
    }
    if manifest_path.exists():
        existing = pd.read_parquet(manifest_path)
        combined = pd.concat([existing, pd.DataFrame([manifest_row])], ignore_index=True)
    else:
        combined = pd.DataFrame([manifest_row])
    combined.to_parquet(manifest_path, index=False)

    quality_path = geo / "geography_quality.parquet"
    quality_row = {
        "year": year,
        "total_records": len(rows),
        "records_without_coordinates": 0,
        "invalid_coordinates": 0,
        "outside_chicago_boundaries": 0,
        "community_area_mismatches": 0,
    }
    if quality_path.exists():
        existing_q = pd.read_parquet(quality_path)
        combined_q = pd.concat([existing_q, pd.DataFrame([quality_row])], ignore_index=True)
    else:
        combined_q = pd.DataFrame([quality_row])
    combined_q.to_parquet(quality_path, index=False)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    _write_year(tmp_path, 2025, _PRIOR)
    _write_year(tmp_path, 2026, _CURRENT)
    return tmp_path


# -- same-period comparison ------------------------------------------------------------


def test_partial_year_uses_the_same_period_last_year(data_dir: Path) -> None:
    pulse = build_pulse(data_dir, 2026)

    assert pulse.is_year_to_date is True
    assert pulse.data_through == "2026-03-15"
    # Current period: all 8 Woodlawn 2026 records (1 Jan - 15 Mar).
    assert pulse.current_period.end == "2026-03-15"
    assert pulse.incidents.current == 8
    # Prior period: only p1, p2, p3 (1 Jan - 15 Mar 2025). p4/p5 are excluded.
    assert pulse.prior_period is not None
    assert pulse.prior_period.end == "2025-03-15"
    assert pulse.incidents.prior == 3
    assert pulse.incidents.absolute_change == 5
    assert pulse.incidents.percent_change == pytest.approx(166.7, abs=0.05)


def test_same_period_cutoff_clamps_leap_day() -> None:
    from datetime import date

    assert same_period_cutoff(date(2024, 2, 29), 2023) == date(2023, 2, 28)
    assert same_period_cutoff(date(2026, 7, 9), 2025) == date(2025, 7, 9)


def test_full_year_compares_against_the_full_prior_year(tmp_path: Path) -> None:
    full = [
        ("f1", "2024-01-10", "THEFT", "false", "0321", "001XX W 63RD ST", True),
        ("f2", "2024-12-31", "BATTERY", "false", "0321", "001XX W 63RD ST", True),
    ]
    prior_full = [("g1", "2023-05-01", "THEFT", "false", "0321", "001XX W 63RD ST", True)]
    _write_year(tmp_path, 2023, prior_full)
    _write_year(tmp_path, 2024, full)

    pulse = build_pulse(tmp_path, 2024)
    assert pulse.is_year_to_date is False
    assert pulse.prior_period is not None
    assert pulse.prior_period.end == "2023-12-31"
    assert pulse.incidents.current == 2
    assert pulse.incidents.prior == 1


# -- broad category partition ----------------------------------------------------------


def test_broad_categories_partition_the_total(data_dir: Path) -> None:
    pulse = build_pulse(data_dir, 2026)
    assert sum(c.current for c in pulse.broad_categories) == pulse.incidents.current

    by_key = {c.key: c.current for c in pulse.broad_categories}
    assert by_key["property_crime"] == 4  # 2x THEFT + CRIMINAL DAMAGE + MVT
    assert by_key["violent_crime"] == 2  # BATTERY + ROBBERY
    assert by_key["narcotics"] == 1
    assert by_key["other"] == 1  # SPACE PIRACY, an unmapped type
    assert by_key["weapons"] == 0
    assert by_key["public_order"] == 0


def test_unmapped_primary_type_maps_to_other() -> None:
    assert broad_category_of("SPACE PIRACY") == "other"
    assert broad_category_of(None) == "other"
    assert broad_category_of("battery") == "violent_crime"


def test_largest_increase_and_decline(data_dir: Path) -> None:
    pulse = build_pulse(data_dir, 2026)
    assert pulse.largest_increase is not None
    assert pulse.largest_increase.key == "property_crime"
    assert pulse.largest_increase.absolute_change == 2  # 4 now vs 2 in same period
    # No broad category declined in the fixture.
    assert pulse.largest_decline is None


def test_category_drivers_include_the_raw_cpd_type(data_dir: Path) -> None:
    pulse = build_pulse(data_dir, 2026)
    space = next(d for d in pulse.category_drivers if d.primary_type == "SPACE PIRACY")
    assert space.broad_category == "other"
    assert space.current == 1
    theft = next(d for d in pulse.category_drivers if d.primary_type == "THEFT")
    assert theft.current == 2
    assert theft.prior == 2  # p1 + p3 within the same period
    assert theft.absolute_change == 0


# -- beat concentration ----------------------------------------------------------------


def test_beat_ranking_and_display(data_dir: Path) -> None:
    pulse = build_pulse(data_dir, 2026)
    top = pulse.beats[0]
    assert top.beat == "0321"
    assert top.beat_display == "321"  # leading zero stripped for residents
    assert top.current == 6
    assert top.share == pytest.approx(0.75, abs=0.001)


# -- arrests ---------------------------------------------------------------------------


def test_arrest_summary_is_a_report_field_not_a_clearance_rate(data_dir: Path) -> None:
    pulse = build_pulse(data_dir, 2026)
    # Arrests recorded on c1, c5, c6 = 3 of 8.
    assert pulse.arrests.count == 3
    assert pulse.arrests.total == 8
    assert pulse.arrests.percent == pytest.approx(0.375, abs=0.001)
    assert "clearance" in pulse.narrative.lower()


# -- charts ----------------------------------------------------------------------------


def test_monthly_comparison_marks_the_partial_month_and_excludes_future(data_dir: Path) -> None:
    pulse = build_pulse(data_dir, 2026)
    march = next(m for m in pulse.monthly_comparison if m.month == 3)
    assert march.current == 4  # c5, c6, c7, c8
    assert march.prior == 1  # p3 only (p4/p5 are later)
    assert march.is_partial_month is True
    assert march.in_comparison_window is True

    april = next(m for m in pulse.monthly_comparison if m.month == 4)
    assert april.current is None
    assert april.in_comparison_window is False


def test_monthly_categories_sum_to_month_total(data_dir: Path) -> None:
    pulse = build_pulse(data_dir, 2026)
    for point in pulse.monthly_categories:
        assert sum(point.counts.values()) == point.total


# -- narrative + headline (composed only from the numbers) -----------------------------


def test_narrative_is_grammatical_and_data_derived(data_dir: Path) -> None:
    narrative = build_pulse(data_dir, 2026).narrative
    assert "Through March 15, 2026" in narrative  # resident-friendly date, not ISO
    assert "8 reported incidents" not in narrative or "1,919" not in narrative
    assert "5 more than during the same period in 2025" in narrative
    assert "an increase of 166.7%" in narrative
    # Never an awkward fused phrase.
    assert "up the same period" not in narrative
    assert "No cause is inferred from correlation." in narrative


def test_headline_states_direction_and_top_category(data_dir: Path) -> None:
    headline = build_pulse(data_dir, 2026).headline
    assert "up" in headline
    assert "166.7%" in headline
    assert "year-to-date" in headline
    assert "Property crime rose most" in headline


# -- comparison unavailable ------------------------------------------------------------


def test_no_prior_year_is_honest(tmp_path: Path) -> None:
    _write_year(tmp_path, 2006, _CURRENT)  # 2005 is not enriched
    pulse = build_pulse(tmp_path, 2006)
    assert pulse.comparison_available is False
    assert pulse.incidents.prior is None
    assert pulse.largest_increase is None
    assert "isn't available yet" in pulse.narrative
    assert "2005" in pulse.comparison_note


# -- HTTP ------------------------------------------------------------------------------


def test_http_pulse_endpoint(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    app = FastAPI()
    app.include_router(pulse_route.router)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/v1/pulse/woodlawn?year=2026")
    assert response.status_code == 200
    payload = response.json()
    assert payload["incidents"]["current"] == 8
    assert payload["neighborhood_name"] == "Woodlawn"


def test_http_bronzeville_is_an_honest_404(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    app = FastAPI()
    app.include_router(pulse_route.router)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/v1/pulse/bronzeville?year=2026")
    assert response.status_code == 404
    assert "Boundary pending approval" in response.json()["detail"]
