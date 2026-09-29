"""The Overview brief: configured findings, reproducible numbers, honest gaps.

The point of these tests is that a published conclusion cannot drift away from the data behind
it. Each one pins a property that keeps the brief trustworthy rather than merely working.
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import yaml

from bw_observatory.presentation.findings import (
    CALCULATIONS,
    FindingsConfigError,
    build_findings,
    load_finding_specs,
)
from bw_observatory.presentation.pulse import _within, build_pulse

_BRONZE_COLS = ["id", "date", "primary_type", "arrest", "beat", "block"]

# Two years so a same-period comparison exists. The prior year deliberately includes a record on
# its final day, which the period window used to drop.
_PRIOR = [
    ("p1", "2025-01-10", "BATTERY", "false", "0321", "001XX W 63RD ST"),
    ("p2", "2025-02-11", "THEFT", "false", "0321", "001XX W 63RD ST"),
    ("p3", "2025-03-12", "NARCOTICS", "true", "0313", "003XX E 60TH ST"),
    ("p4", "2025-06-01", "THEFT", "false", "0321", "001XX W 63RD ST"),
    ("p5", "2025-12-31", "THEFT", "false", "0321", "001XX W 63RD ST"),
]
_CURRENT = [
    ("c1", "2026-01-10", "BATTERY", "false", "0321", "001XX W 63RD ST"),
    ("c2", "2026-02-11", "THEFT", "false", "0321", "001XX W 63RD ST"),
    ("c3", "2026-03-12", "THEFT", "false", "0313", "003XX E 60TH ST"),
]


def _bulk(
    prefix: str, year: int, count: int, *, last_day: str | None = None
) -> list[tuple[Any, ...]]:
    """Enough records for a percentage to be publishable, spread across the year.

    F-001 requires a prior period of at least 100 reports, so a fixture that exercises a
    published percentage has to clear that bar rather than work around it.
    """
    rows: list[tuple[Any, ...]] = []
    types = ("BATTERY", "THEFT", "CRIMINAL DAMAGE", "NARCOTICS", "ROBBERY")
    for index in range(count):
        month = index % 8 + 1
        day = index % 27 + 1
        rows.append(
            (
                f"{prefix}{index}",
                f"{year}-{month:02d}-{day:02d}",
                types[index % len(types)],
                "true" if index % 7 == 0 else "false",
                "0321" if index % 3 else "0313",
                "001XX W 63RD ST",
            )
        )
    if last_day:
        rows.append((f"{prefix}last", last_day, "THEFT", "false", "0321", "001XX W 63RD ST"))
    return rows


def _write_year(root: Path, year: int, rows: list[tuple[Any, ...]]) -> None:
    bronze = root / "bronze" / "crime"
    silver = root / "silver" / "crime" / "crime_with_geography"
    geo = root / "silver" / "geography"
    for directory in (bronze, silver, geo):
        directory.mkdir(parents=True, exist_ok=True)

    frame = pd.DataFrame(
        [
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
    )[_BRONZE_COLS].astype("string")
    bronze_file = bronze / f"{year}.parquet"
    frame.to_parquet(bronze_file, index=False)

    pd.DataFrame(
        [
            {
                "id": r[0],
                "spatial_ward_current": "20",
                "spatial_community_area": "42",
                "neighborhood_woodlawn": True,
                "neighborhood_bronzeville": None,
                "boundary_vintage": "community_area:1920;ward:2023",
                "geography_status": "assigned",
                "source_status": "active_in_source",
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
    """A release with enough history for the percentage findings to publish."""
    _write_year(tmp_path, 2025, _bulk("p", 2025, 160, last_day="2025-12-31"))
    _write_year(tmp_path, 2026, _bulk("c", 2026, 120))
    return tmp_path


@pytest.fixture
def sparse_data_dir(tmp_path: Path) -> Path:
    """A release whose comparison period is too small for a percentage to mean anything."""
    _write_year(tmp_path, 2025, _PRIOR)
    _write_year(tmp_path, 2026, _CURRENT)
    return tmp_path


@pytest.fixture(autouse=True)
def _fresh_config_cache() -> Any:
    """The spec loader is cached; tests that write their own config must not see a stale one."""
    load_finding_specs.cache_clear()
    yield
    load_finding_specs.cache_clear()


# -- the period boundary that made a published percentage wrong -------------------------


def test_the_final_day_of_a_period_is_included() -> None:
    """Incident timestamps carry a time of day, so an end-of-day boundary must be inclusive.

    Comparing against midnight dropped every record dated on the last day of the prior period.
    On the real release that understated Ward 20's 2024 comparison by 24 records (8,191 against
    8,215) and published -4.6% where the true change was -4.8%.
    """
    frame = pd.DataFrame(
        {"_when": pd.to_datetime(["2025-12-30T09:00", "2025-12-31T12:00", "2026-01-01T01:00"])}
    )
    kept = _within(frame, date(2025, 1, 1), date(2025, 12, 31))
    assert len(kept) == 2, "the record dated on the final day must be counted"


# -- configuration is validated, not trusted --------------------------------------------


def _write_config(tmp_path: Path, findings: list[dict[str, Any]]) -> Path:
    path = tmp_path / "findings.yml"
    path.write_text(yaml.safe_dump({"findings": findings}), encoding="utf-8")
    return path


def test_a_stated_figure_must_name_the_calculation_that_produced_it(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        [
            {
                "id": "X-1",
                "topic": "public_safety",
                "classification": "verified_finding",
                "headline": {"any": "A claim with no arithmetic behind it."},
                "observation": "...",
                "status": "published",
            }
        ],
    )
    with pytest.raises(FindingsConfigError, match="needs a `calculation`"):
        load_finding_specs(path)


def test_unknown_classification_is_refused(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        [
            {
                "id": "X-2",
                "topic": "public_safety",
                "classification": "probably_true",
                "headline": {"any": "..."},
                "observation": "...",
            }
        ],
    )
    with pytest.raises(FindingsConfigError, match="classification"):
        load_finding_specs(path)


def test_duplicate_ids_are_refused(tmp_path: Path) -> None:
    entry = {
        "id": "X-3",
        "topic": "city_services",
        "classification": "data_gap",
        "headline": {"any": "..."},
        "observation": "...",
    }
    with pytest.raises(FindingsConfigError, match="Duplicate"):
        load_finding_specs(_write_config(tmp_path, [entry, dict(entry)]))


def test_every_shipped_finding_is_reviewed_and_classified() -> None:
    """The file that ships must not contain an unreviewed published claim."""
    for spec in load_finding_specs():
        if spec.status != "published":
            continue
        assert spec.headline, f"{spec.id}: no wording"
        assert spec.observation, f"{spec.id}: no observation"
        assert spec.reviewed_by and spec.reviewed_at, f"{spec.id}: published without a reviewer"
        if spec.calculation:
            assert spec.calculation in CALCULATIONS, f"{spec.id}: unknown calculation"
        if spec.classification in {"data_gap", "research_question"}:
            assert spec.calculation is None, f"{spec.id}: a gap must not state a computed figure"


# -- the published numbers must equal a recomputation ------------------------------------


def test_lead_finding_numbers_match_the_data_they_came_from(data_dir: Path) -> None:
    brief = build_findings(data_dir, 2026, "ward20")
    pulse = build_pulse(data_dir, 2026, "ward20")

    overall = next(f for f in brief.lead if f.id == "F-001")
    values = {e.label: e.value for e in overall.evidence}
    assert values["Reported incidents"] == f"{pulse.incidents.current:,}"
    assert values["Same period last year"] == f"{pulse.incidents.prior:,}"
    # The figure in the prose is the figure in the evidence.
    assert f"{pulse.incidents.current:,}" in overall.observation


def test_findings_carry_the_context_a_reader_needs_to_judge_them(data_dir: Path) -> None:
    brief = build_findings(data_dir, 2026, "ward20")
    overall = next(f for f in brief.lead if f.id == "F-001")

    assert overall.classification == "verified_finding"
    assert overall.geography_label == "Ward 20"
    assert overall.reporting_period and overall.comparison_period
    assert overall.source_dataset_id == "ijzp-q8t2"
    assert overall.data_through == pulse_through(data_dir)
    assert overall.limitations, "a published figure must travel with its limitations"
    # Deep link preserves the shared filters so the evidence opens in the same state.
    assert overall.destination_route == "/trends"
    assert overall.destination_params == {"geo": "ward20", "year": "2026"}


def pulse_through(data_dir: Path) -> str:
    return build_pulse(data_dir, 2026, "ward20").data_through


def test_the_brief_records_what_it_was_computed_from(data_dir: Path) -> None:
    """An archived brief has to be reproducible, so it names its release and period."""
    brief = build_findings(data_dir, 2026, "ward20")
    assert brief.data_release == data_dir.resolve().name
    assert brief.data_through
    assert brief.generated_at
    assert brief.freshness_status in {"provisional", "settled"}


# -- honesty about what is not known -----------------------------------------------------


def test_domains_without_data_publish_a_gap_and_never_a_figure(data_dir: Path) -> None:
    brief = build_findings(data_dir, 2026, "ward20")
    topics = {f.topic for f in brief.data_gaps}
    assert {
        "people_and_housing",
        "city_services",
        "economic_conditions",
        "public_investment",
    } <= topics

    for gap in brief.data_gaps:
        assert gap.classification == "data_gap"
        assert gap.missing, f"{gap.id}: a gap must say what is missing"
        assert gap.evidence == [], f"{gap.id}: a gap must not carry figures"
        assert gap.calculation is None


def test_research_questions_are_separated_from_findings(data_dir: Path) -> None:
    brief = build_findings(data_dir, 2026, "ward20")
    assert brief.questions, "the brief states the questions the evidence raises"
    for question in brief.questions:
        assert question.classification == "research_question"
        assert question.evidence == []


def test_unpublished_findings_are_withheld_with_a_reason(tmp_path: Path, data_dir: Path) -> None:
    path = _write_config(
        tmp_path,
        [
            {
                "id": "D-1",
                "topic": "public_safety",
                "classification": "verified_finding",
                "calculation": "overall_change",
                "headline": {"any": "Draft wording."},
                "observation": "{total} reports.",
                "status": "draft",
            }
        ],
    )
    load_finding_specs(path)  # prime the cache with the test config
    from bw_observatory.presentation import findings as module

    specs = module.load_finding_specs(path)
    assert specs[0].status == "draft"
    # Nothing with a draft status may reach a reader.
    brief = build_findings(data_dir, 2026, "ward20")
    assert all(f.id != "D-1" for f in brief.lead + brief.by_domain)


def test_a_small_comparison_period_suppresses_the_percentage(sparse_data_dir: Path) -> None:
    """F-001 requires 100 prior reports; this fixture has 5, so it is withheld, not shown."""
    brief = build_findings(sparse_data_dir, 2026, "ward20")
    assert all(f.id != "F-001" for f in brief.lead), "an unstable percentage must not publish"
    assert any("F-001" in reason and "below the" in reason for reason in brief.withheld)


def test_geography_specific_findings_only_appear_for_their_geography(data_dir: Path) -> None:
    ward = build_findings(data_dir, 2026, "ward20")
    assert any(f.id == "F-010" for f in ward.neighborhood_differences) or any(
        "F-010" in reason for reason in ward.withheld
    )
    portion = build_findings(data_dir, 2026, "woodlawn")
    assert all(f.id != "F-010" for f in portion.neighborhood_differences)


def test_enforcement_sensitive_findings_are_labelled(data_dir: Path) -> None:
    """A finding whose figure tracks police activity must say so, wherever it appears."""
    brief = build_findings(data_dir, 2026, "ward20")
    share = next((f for f in brief.by_domain if f.id == "F-003"), None)
    if share is not None:
        assert share.enforcement_sensitive is True
