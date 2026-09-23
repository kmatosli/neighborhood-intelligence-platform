"""Tier 0/0b disclosures: whole-beat context, enforcement-generated types, measurement notes,
and non-silent published-field filtering.

Each test pins a behaviour that exists so a reader is not misled, so a regression here is a
public-information defect, not a cosmetic one.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from bw_observatory.presentation.incidents import build_incident_page
from bw_observatory.presentation.measurement import measurement_notes, whole_beat_counts
from bw_observatory.presentation.overview import is_enforcement_generated, resolve_geography
from bw_observatory.presentation.pulse import build_pulse

# id, date, primary_type, arrest, beat, block, in_ward20, beat_mismatch, source_status
# Beat 0321 straddles: r1-r3 are inside Ward 20, r7 is in the same beat but outside it, so the
# whole beat is larger than the part inside the geography — the case a beat meeting exposes.
_ROWS: list[tuple[Any, ...]] = [
    (
        "r1",
        "2026-01-10",
        "BATTERY",
        "false",
        "0321",
        "001XX W 63RD ST",
        True,
        False,
        "active_in_source",
    ),
    (
        "r2",
        "2026-01-20",
        "NARCOTICS",
        "true",
        "0321",
        "001XX W 63RD ST",
        True,
        True,
        "active_in_source",
    ),
    (
        "r3",
        "2026-02-05",
        "PROSTITUTION",
        "true",
        "0321",
        "002XX E 61ST ST",
        True,
        False,
        "active_in_source",
    ),
    (
        "r4",
        "2026-02-10",
        "THEFT",
        "false",
        "0313",
        "003XX E 60TH ST",
        True,
        True,
        "active_in_source",
    ),
    (
        "r5",
        "2026-02-20",
        "THEFT",
        "false",
        "0313",
        "003XX E 60TH ST",
        True,
        False,
        "source_removed",
    ),
    (
        "r6",
        "2026-03-01",
        "ROBBERY",
        "false",
        "0313",
        "004XX E 63RD ST",
        True,
        False,
        "active_in_source",
    ),
    (
        "r7",
        "2026-02-25",
        "THEFT",
        "false",
        "0321",
        "999XX W 1ST ST",
        False,
        False,
        "active_in_source",
    ),
]

_BRONZE_COLS = [
    "id",
    "case_number",
    "date",
    "updated_on",
    "primary_type",
    "description",
    "location_description",
    "arrest",
    "domestic",
    "beat",
    "district",
    "ward",
    "community_area",
    "block",
    "latitude",
    "longitude",
]


def _write(root: Path, year: int, rows: list[tuple[Any, ...]]) -> None:
    bronze = root / "bronze" / "crime"
    silver = root / "silver" / "crime" / "crime_with_geography"
    geo = root / "silver" / "geography"
    for directory in (bronze, silver, geo):
        directory.mkdir(parents=True, exist_ok=True)

    frame = pd.DataFrame(
        [
            {
                "id": r[0],
                "case_number": f"JX{r[0]}",
                "date": f"{r[1]}T12:00:00.000",
                "updated_on": "2026-09-01T00:00:00.000",
                "primary_type": r[2],
                "description": "TEST DESCRIPTION",
                "location_description": "STREET",
                "arrest": r[3],
                "domestic": "false",
                "beat": r[4],
                "district": "003",
                # r4's published ward disagrees with its mapped ward: the frame-mixing case.
                "ward": "20" if r[0] != "r4" else "5",
                "community_area": "42",
                "block": r[5],
                "latitude": "41.78",
                "longitude": "-87.60",
            }
            for r in rows
        ]
    )[_BRONZE_COLS].astype("string")
    bronze_file = bronze / f"{year}.parquet"
    frame.to_parquet(bronze_file, index=False)

    pd.DataFrame(
        [
            {
                "id": r[0],
                "spatial_ward_current": "20" if r[6] else "5",
                "spatial_community_area": "42",
                "neighborhood_woodlawn": True,
                "neighborhood_bronzeville": None,
                "boundary_vintage": "community_area:1920;ward:2023",
                "geography_status": "assigned",
                "beat_mismatch": r[7],
                "ward_mismatch": r[0] == "r4",
                "community_area_mismatch": False,
                "source_status": r[8],
            }
            for r in rows
        ]
    ).to_parquet(silver / f"{year}.parquet", index=False)

    pd.DataFrame(
        [
            {
                "year": year,
                "rows": len(frame),
                "download_started": "2026-09-01T00:00:00+00:00",
                "download_completed": "2026-09-01T00:01:00+00:00",
                "api_version": "socrata-resource-v2.1",
                "dataset_last_updated": "2026-09-01T00:00:00+00:00",
                "checksum": hashlib.sha256(bronze_file.read_bytes()).hexdigest(),
                "status": "complete",
            }
        ]
    ).to_parquet(bronze / "manifest.parquet", index=False)

    pd.DataFrame(
        [
            {
                "year": year,
                "total_records": len(frame),
                "records_without_coordinates": 0,
                "invalid_coordinates": 0,
                "outside_chicago_boundaries": 0,
                "community_area_mismatches": 0,
            }
        ]
    ).to_parquet(geo / "geography_quality.parquet", index=False)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    _write(tmp_path, 2026, _ROWS)
    return tmp_path


# -- whole beat vs the part inside the geography ----------------------------------------


def test_whole_beat_counts_are_not_clipped_to_the_geography(data_dir: Path) -> None:
    from datetime import date

    totals = whole_beat_counts(data_dir, 2026, start=date(2026, 1, 1), end=date(2026, 3, 1))
    # Beat 0321 has four records citywide (r1, r2, r3, r7) — r7 is outside Ward 20.
    assert totals["0321"] == 4
    # r5 was withdrawn by the City and must not be counted.
    assert totals["0313"] == 2


def test_beat_rows_publish_the_whole_beat_and_flag_that_it_extends_beyond(
    data_dir: Path,
) -> None:
    pulse = build_pulse(data_dir, 2026, "ward20")
    by_beat = {b.beat: b for b in pulse.beats}

    straddling = by_beat["0321"]
    assert straddling.current == 3  # inside Ward 20
    assert straddling.whole_beat_current == 4  # the beat a CPD beat meeting covers
    assert straddling.extends_beyond_geography is True
    assert straddling.share_of_beat_inside == pytest.approx(0.75)

    # A beat wholly inside the geography must not be labelled as extending beyond it.
    contained = by_beat["0313"]
    assert contained.current == contained.whole_beat_current
    assert contained.extends_beyond_geography is False


# -- enforcement-generated categories ---------------------------------------------------


def test_enforcement_generated_types_come_from_config() -> None:
    assert is_enforcement_generated("PROSTITUTION") is True
    assert is_enforcement_generated("narcotics") is True  # case-insensitive
    assert is_enforcement_generated("BATTERY") is False
    assert is_enforcement_generated(None) is False


def test_category_drivers_label_enforcement_generated_offences(data_dir: Path) -> None:
    pulse = build_pulse(data_dir, 2026, "ward20")
    flags = {d.primary_type: d.enforcement_generated for d in pulse.category_drivers}
    assert flags["NARCOTICS"] is True
    assert flags["PROSTITUTION"] is True
    # A victim-reported offence must never carry the label.
    assert flags["ROBBERY"] is False


# -- measurement notes ------------------------------------------------------------------


def test_measurement_notes_count_definition_disagreements_and_withdrawals(
    data_dir: Path,
) -> None:
    notes = measurement_notes(data_dir, 2026, resolve_geography("ward20"), through_iso="2026-03-01")
    # r2 and r4 carry beat_mismatch and are inside Ward 20; r5 is withdrawn and excluded.
    assert notes.beat_definition_disagreements == 2
    assert notes.ward_definition_disagreements == 1
    assert notes.source_removed_records == 1
    assert notes.unplaced_records == 0
    # The period ends at the edge of the data, so it is still filling in.
    assert notes.provisional_period is True
    assert any("masked" in note for note in notes.notes)
    assert any("withdrawn" in note for note in notes.notes)


def test_a_settled_period_is_not_labelled_provisional(data_dir: Path) -> None:
    notes = measurement_notes(
        data_dir,
        2026,
        resolve_geography("ward20"),
        through_iso="2025-01-01",
        newest_iso="2026-03-01",
    )
    assert notes.provisional_period is False


def test_pulse_publishes_measurement_notes(data_dir: Path) -> None:
    pulse = build_pulse(data_dir, 2026, "ward20")
    assert pulse.measurement is not None
    assert pulse.measurement.beat_definition_disagreements == 2


# -- published-field filtering is never silent ------------------------------------------


def test_published_field_filter_reports_the_rows_it_excluded(data_dir: Path) -> None:
    unfiltered = build_incident_page(data_dir, 2026, neighborhood_id="ward20")
    assert unfiltered.published_field_filters == []
    assert unfiltered.excluded_by_published_field_filters == 0

    # r4 is inside Ward 20 by point-in-polygon but CPD published ward 5 on it, so filtering on
    # the published field hides a record that IS in the geography. That must be reported.
    filtered = build_incident_page(data_dir, 2026, neighborhood_id="ward20", ward="20")
    assert filtered.published_field_filters == ["ward"]
    assert filtered.excluded_by_published_field_filters == 1
    assert filtered.total_records == unfiltered.total_records - 1
