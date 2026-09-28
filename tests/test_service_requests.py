"""311 service requests: ingestion, spatial governance, classification and pothole analytics.

Each test pins a property that keeps a published City Services figure honest. The fixtures build
their own tiny release and their own boundary layers, so nothing here can read the production
data or depend on the live portal.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import pytest
import yaml
from shapely.geometry import Polygon

from bw_observatory.config import Settings
from bw_observatory.geography.service_requests import (
    COORD_DEFAULT_POINT,
    COORD_MISSING,
    COORD_OK,
    COORD_OUT_OF_RANGE,
    ReferenceLayers,
    classify_coordinates,
    duration_frame,
    enrich_service_requests,
)
from bw_observatory.ingest.service_request_reconcile import (
    RECONCILIATION_LOG_COLUMNS,
    ServiceRequestReconciler,
)
from bw_observatory.ingest.service_requests import (
    SOURCE_COLUMNS,
    ServiceRequestConfigError,
    ServiceRequestIngest,
    bronze_path,
    load_service_request_config,
    silver_path,
    write_parquet_atomic,
)
from bw_observatory.presentation.city_services import (
    CityServicesUnavailable,
    _within,
    build_category_report,
    counts_for,
)
from bw_observatory.presentation.findings import (
    CalcContext,
    calc_pothole_duplicate_share,
    calc_pothole_request_change,
)
from bw_observatory.presentation.overview import resolve_geography

# A square standing in for Ward 20, and a neighbour. Small and explicit, so a boundary test
# states its own expectation instead of depending on the real city geometry.
WARD20 = Polygon([(-87.65, 41.78), (-87.60, 41.78), (-87.60, 41.81), (-87.65, 41.81)])
WARD5 = Polygon([(-87.60, 41.78), (-87.55, 41.78), (-87.55, 41.81), (-87.60, 41.81)])
AREA42 = Polygon([(-87.65, 41.78), (-87.625, 41.78), (-87.625, 41.81), (-87.65, 41.81)])
AREA40 = Polygon([(-87.625, 41.78), (-87.60, 41.78), (-87.60, 41.81), (-87.625, 41.81)])


@pytest.fixture
def layers() -> ReferenceLayers:
    wards = gpd.GeoDataFrame({"ward_id": ["20", "5"]}, geometry=[WARD20, WARD5], crs="EPSG:4326")
    areas = gpd.GeoDataFrame(
        {"area_number": ["42", "40"]}, geometry=[AREA42, AREA40], crs="EPSG:4326"
    )
    return ReferenceLayers(wards=wards, community_areas=areas, version="test")


@pytest.fixture(autouse=True)
def _fresh_config_cache() -> Any:
    load_service_request_config.cache_clear()
    yield
    load_service_request_config.cache_clear()


def _row(**overrides: Any) -> dict[str, Any]:
    """A source-shaped record. Defaults land inside the stand-in Ward 20, community area 42."""
    base: dict[str, Any] = {column: None for column in SOURCE_COLUMNS}
    base.update(
        {
            "sr_number": "SR1",
            "sr_type": "Pothole in Street Complaint",
            "sr_short_code": "PHF",
            "status": "Completed",
            "created_date": "2025-03-04T09:00:00.000",
            "last_modified_date": "2025-03-09T09:00:00.000",
            "closed_date": "2025-03-09T09:00:00.000",
            "street_address": "100 W 63RD ST",
            "duplicate": "false",
            "legacy_record": "false",
            "ward": "20",
            "community_area": "42",
            "latitude": "41.79",
            "longitude": "-87.64",
        }
    )
    base.update(overrides)
    return base


def _bronze(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    for column in SOURCE_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    return frame[list(SOURCE_COLUMNS)].astype("string")


# -- classification -----------------------------------------------------------------------


def test_categories_come_from_short_codes_not_wording() -> None:
    config = load_service_request_config()
    assert config.category_for_code("PHF") == "potholes"
    assert config.category_for_code("phb") == "potholes"  # case-insensitive
    assert config.category_for_code("SGA") == "rodents"
    # A code the City introduces later must surface as unrecognised, never folded into a
    # neighbouring category where it would silently inflate a published figure.
    assert config.category_for_code("NEWCODE") == "uncategorized"
    assert config.category_for_code(None) == "uncategorized"


def test_only_audited_categories_are_publishable() -> None:
    config = load_service_request_config()
    assert config.categories["potholes"].validated is True
    assert config.categories["graffiti"].validated is False
    # A closure rule exists only for the audited category.
    assert "potholes" in config.closure_semantics
    assert "graffiti" not in config.closure_semantics


def test_a_short_code_claimed_by_two_categories_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "service_requests.yml"
    path.write_text(
        yaml.safe_dump(
            {
                "dataset": {"id": "v6vf-nfxy"},
                "categories": {
                    "a": {"label": "A", "short_codes": ["XX"]},
                    "b": {"label": "B", "short_codes": ["XX"]},
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ServiceRequestConfigError, match="claimed by both"):
        load_service_request_config(path)


def test_unknown_categories_stay_visible_in_silver(layers: ReferenceLayers) -> None:
    config = load_service_request_config()
    bronze = _bronze([_row(sr_number="A", sr_short_code="ZZZZ", sr_type="Something New")])
    silver = enrich_service_requests(bronze, 2025, config, layers)
    assert silver.loc[0, "analytical_category"] == "uncategorized"
    # The raw type survives, so the record is investigable rather than merely uncounted.
    assert silver.loc[0, "sr_type_raw"] == "Something New"
    assert bool(silver.loc[0, "analytical_inclusion"]) is True


# -- geography ----------------------------------------------------------------------------


def test_ward_membership_comes_from_coordinates_not_the_source_ward(
    layers: ReferenceLayers,
) -> None:
    """The decisive governance rule: the source's ward is recorded at creation time against
    whatever map was then in force, so it is preserved and compared, never obeyed."""
    config = load_service_request_config()
    bronze = _bronze(
        [
            # Coordinates inside the stand-in Ward 20, but the City recorded ward 5.
            _row(sr_number="A", ward="5", latitude="41.79", longitude="-87.64"),
            # Coordinates in ward 5, but the City recorded ward 20.
            _row(sr_number="B", ward="20", latitude="41.79", longitude="-87.57"),
        ]
    )
    silver = enrich_service_requests(bronze, 2025, config, layers).set_index("sr_number")

    assert silver.loc["A", "spatial_ward_current"] == "20"
    assert bool(silver.loc["A", "in_ward20"]) is True
    assert silver.loc["A", "source_ward"] == "5"
    assert bool(silver.loc["A", "ward_mismatch"]) is True

    assert silver.loc["B", "spatial_ward_current"] == "5"
    assert bool(silver.loc["B", "in_ward20"]) is False
    assert silver.loc["B", "source_ward"] == "20"
    assert bool(silver.loc["B", "ward_mismatch"]) is True


def test_community_area_portions_are_placed_spatially(layers: ReferenceLayers) -> None:
    config = load_service_request_config()
    bronze = _bronze(
        [
            _row(sr_number="A", longitude="-87.64", community_area="40"),  # geometrically 42
            _row(sr_number="B", longitude="-87.61", community_area="42"),  # geometrically 40
        ]
    )
    silver = enrich_service_requests(bronze, 2025, config, layers).set_index("sr_number")
    assert silver.loc["A", "spatial_community_area"] == "42"
    assert silver.loc["B", "spatial_community_area"] == "40"
    assert bool(silver.loc["A", "community_area_mismatch"]) is True


def test_records_without_trustworthy_coordinates_are_excluded_with_a_reason(
    layers: ReferenceLayers,
) -> None:
    config = load_service_request_config()
    bronze = _bronze(
        [
            _row(sr_number="OK"),
            _row(sr_number="NOCOORD", latitude=None, longitude=None),
            _row(sr_number="FARAWAY", latitude="45.0", longitude="-80.0"),
        ]
    )
    silver = enrich_service_requests(bronze, 2025, config, layers).set_index("sr_number")

    assert silver.loc["OK", "coordinate_quality"] == COORD_OK
    assert bool(silver.loc["OK", "analytical_inclusion"]) is True

    for sr, verdict in (("NOCOORD", COORD_MISSING), ("FARAWAY", COORD_OUT_OF_RANGE)):
        assert silver.loc[sr, "coordinate_quality"] == verdict
        assert bool(silver.loc[sr, "analytical_inclusion"]) is False
        # Excluded, but with a stated reason and no silent placement.
        assert silver.loc[sr, "exclusion_reason"] == f"coordinate_{verdict}"
        assert pd.isna(silver.loc[sr, "spatial_ward_current"])


def test_a_repeated_default_coordinate_is_not_treated_as_a_location() -> None:
    """311 geocodes some request types to one fixed point — over two million records share a
    single coordinate — and placing those in a ward would invent a concentration."""
    config = load_service_request_config()
    rows = [
        _row(sr_number=f"D{i}", latitude="41.871831", longitude="-87.679846") for i in range(1200)
    ]
    rows.append(_row(sr_number="REAL", latitude="41.79", longitude="-87.64"))
    verdict, _, _ = classify_coordinates(_bronze(rows), config)
    assert (verdict == COORD_DEFAULT_POINT).sum() == 1200
    assert verdict.iloc[-1] == COORD_OK


# -- information only calls ---------------------------------------------------------------


def test_information_only_calls_are_kept_in_bronze_and_excluded_in_silver(
    layers: ReferenceLayers,
) -> None:
    """35% of the source is a record of someone asking a question, geocoded to one point. It is
    retained as provenance and excluded from every service-demand figure."""
    config = load_service_request_config()
    bronze = _bronze(
        [
            _row(sr_number="POTHOLE"),
            _row(
                sr_number="INFO",
                sr_type="311 INFORMATION ONLY CALL",
                sr_short_code="311IOC",
            ),
        ]
    )
    # Bronze keeps it, with its original type.
    assert len(bronze) == 2
    assert "311 INFORMATION ONLY CALL" in set(bronze["sr_type"])

    silver = enrich_service_requests(bronze, 2025, config, layers).set_index("sr_number")
    assert bool(silver.loc["INFO", "analytical_inclusion"]) is False
    assert silver.loc["INFO", "exclusion_reason"] == "information_only_call"
    assert silver.loc["INFO", "sr_type_raw"] == "311 INFORMATION ONLY CALL"
    assert bool(silver.loc["POTHOLE", "analytical_inclusion"]) is True


def test_legacy_records_are_excluded_from_the_modern_series(layers: ReferenceLayers) -> None:
    config = load_service_request_config()
    bronze = _bronze([_row(sr_number="OLD", legacy_record="true")])
    silver = enrich_service_requests(bronze, 2025, config, layers)
    assert silver.loc[0, "exclusion_reason"] == "legacy_record"
    assert bool(silver.loc[0, "analytical_inclusion"]) is False


# -- duplicates and linkage ---------------------------------------------------------------


def test_raw_and_primary_counts_are_both_available_and_never_conflated(
    layers: ReferenceLayers,
) -> None:
    config = load_service_request_config()
    bronze = _bronze(
        [
            _row(sr_number="P1"),
            _row(sr_number="P2"),
            _row(sr_number="C1", duplicate="true", parent_sr_number="P1"),
        ]
    )
    silver = enrich_service_requests(bronze, 2025, config, layers)
    counts = counts_for(silver)
    assert counts.raw == 3, "raw counts every submission a resident made"
    assert counts.primary == 2, "primary excludes requests flagged as duplicates"
    assert counts.duplicates == 1
    assert counts.raw != counts.primary

    child = silver.set_index("sr_number").loc["C1"]
    assert bool(child["is_explicit_duplicate"]) is True
    assert bool(child["is_primary_request"]) is False
    # The link itself is preserved, so a child can be traced to its parent.
    assert child["parent_sr_number"] == "P1"
    assert bool(child["has_parent"]) is True


# -- closure semantics --------------------------------------------------------------------


def test_duration_uses_only_the_statuses_the_audit_allows(layers: ReferenceLayers) -> None:
    """A Canceled request carries a closed_date too. Counting it as a completion would make the
    City look faster than it was, so the audit restricts duration to Completed."""
    config = load_service_request_config()
    bronze = _bronze(
        [
            _row(sr_number="DONE", status="Completed"),
            _row(sr_number="CANCELLED", status="Canceled"),
            _row(sr_number="OPEN", status="Open", closed_date=None),
        ]
    )
    silver = enrich_service_requests(bronze, 2025, config, layers)
    eligible = set(duration_frame(silver, "potholes", config)["sr_number"])
    assert eligible == {"DONE"}


def test_duplicates_are_excluded_from_duration(layers: ReferenceLayers) -> None:
    """A duplicate closes when its parent resolves, so its interval measures the linkage."""
    config = load_service_request_config()
    bronze = _bronze(
        [
            _row(sr_number="PRIMARY"),
            _row(sr_number="CHILD", duplicate="true", parent_sr_number="PRIMARY"),
        ]
    )
    silver = enrich_service_requests(bronze, 2025, config, layers)
    assert set(duration_frame(silver, "potholes", config)["sr_number"]) == {"PRIMARY"}


def test_a_closure_before_creation_is_not_a_negative_duration(layers: ReferenceLayers) -> None:
    config = load_service_request_config()
    bronze = _bronze(
        [
            _row(
                sr_number="BACKWARDS",
                created_date="2025-03-10T09:00:00.000",
                closed_date="2025-03-04T09:00:00.000",
            )
        ]
    )
    silver = enrich_service_requests(bronze, 2025, config, layers)
    assert duration_frame(silver, "potholes", config).empty


def test_no_duration_for_a_category_without_audited_semantics(layers: ReferenceLayers) -> None:
    config = load_service_request_config()
    bronze = _bronze([_row(sr_number="G", sr_short_code="GRAF", sr_type="Graffiti Removal")])
    silver = enrich_service_requests(bronze, 2025, config, layers)
    assert duration_frame(silver, "graffiti", config).empty


# -- date windows -------------------------------------------------------------------------


def test_the_final_day_of_a_window_is_included() -> None:
    """`created_at` carries a time of day, so an end-of-day boundary must be inclusive — the
    same defect that was found and fixed in the crime comparison."""
    rows = pd.DataFrame(
        {"created_at": pd.to_datetime(["2025-12-30T09:00", "2025-12-31T18:00", "2026-01-01T01:00"])}
    )
    assert len(_within(rows, date(2025, 1, 1), date(2025, 12, 31))) == 2


# -- reconciliation of published figures --------------------------------------------------


def _release(
    root: Path, layers: ReferenceLayers, rows_by_year: dict[int, list[dict[str, Any]]]
) -> Path:
    config = load_service_request_config()
    for year, rows in rows_by_year.items():
        bronze = _bronze(rows)
        write_parquet_atomic(bronze, bronze_path(root, year))
        write_parquet_atomic(
            enrich_service_requests(bronze, year, config, layers), silver_path(root, year)
        )
    return root


def test_monthly_and_status_subtotals_reconcile_to_the_total(
    tmp_path: Path, layers: ReferenceLayers
) -> None:
    rows = [
        _row(sr_number=f"A{i}", created_date=f"2025-0{(i % 9) + 1}-05T09:00:00.000")
        for i in range(30)
    ]
    rows.append(_row(sr_number="OPEN1", status="Open", closed_date=None))
    root = _release(tmp_path, layers, {2025: rows})

    report = build_category_report(root, 2025, "ward20", "potholes")
    assert sum(month["raw"] for month in report.monthly) == report.counts.raw
    assert sum(report.status.values()) == report.counts.raw
    assert report.counts.primary + report.counts.duplicates == report.counts.raw


def test_months_the_period_has_not_reached_are_absent_not_zero(
    tmp_path: Path, layers: ReferenceLayers
) -> None:
    """A partial year must not publish zeros for months that have not happened. A zero bar and an
    unreached month look the same on a chart, and only one of them is a fact."""
    rows = [
        _row(sr_number=f"A{i}", created_date=f"2026-0{(i % 4) + 1}-05T09:00:00.000")
        for i in range(12)
    ]
    root = _release(tmp_path, layers, {2026: rows})

    report = build_category_report(root, 2026, "ward20", "potholes")
    assert [month["month"] for month in report.monthly] == [1, 2, 3, 4]
    assert sum(month["raw"] for month in report.monthly) == report.counts.raw


def test_the_report_states_its_exclusions_geography_and_limits(
    tmp_path: Path, layers: ReferenceLayers
) -> None:
    rows = [
        _row(sr_number="A"),
        _row(sr_number="INFO", sr_type="311 INFORMATION ONLY CALL", sr_short_code="311IOC"),
    ]
    root = _release(tmp_path, layers, {2025: rows})
    report = build_category_report(root, 2025, "ward20", "potholes")

    assert report.excluded_from_analysis["information_only_call"] == 1
    assert report.denominator is None, "no street-mileage denominator is ingested"
    joined = " ".join(report.methodology).lower()
    assert "not a measure of how well the city performs" in joined
    assert "never by the ward recorded on the request" in joined
    assert "not rates" in joined


def test_an_unaudited_category_is_refused_rather_than_estimated(
    tmp_path: Path, layers: ReferenceLayers
) -> None:
    root = _release(tmp_path, layers, {2025: [_row(sr_number="A")]})
    with pytest.raises(CityServicesUnavailable, match="closure semantics"):
        build_category_report(root, 2025, "ward20", "graffiti")


def test_a_partial_year_is_compared_with_the_same_window_not_a_whole_year(
    tmp_path: Path, layers: ReferenceLayers
) -> None:
    prior = [
        _row(sr_number=f"P{i}", created_date=f"2024-0{(i % 9) + 1}-05T09:00:00.000")
        for i in range(20)
    ]
    current = [_row(sr_number="C1", created_date="2025-02-10T09:00:00.000")]
    root = _release(tmp_path, layers, {2024: prior, 2025: current})

    report = build_category_report(root, 2025, "ward20", "potholes")
    # The current period ends 2025-02-10, so the comparison window ends 2024-02-10 and must not
    # include the whole of 2024.
    assert report.prior_period_end == "2024-02-10"
    assert report.prior_counts is not None
    assert report.prior_counts.raw < len(prior)


def test_calculations_read_the_injected_release_not_the_live_one(
    tmp_path: Path, layers: ReferenceLayers
) -> None:
    """A calculation that reached for global settings would read production data and pass for
    the wrong reason — which is exactly what happened once in the findings work."""
    root = _release(tmp_path, layers, {2025: [_row(sr_number="ONLY")]})
    report = build_category_report(root, 2025, "ward20", "potholes")
    assert report.counts.raw == 1, "the fixture holds one record; production holds many"


# -- ingestion ----------------------------------------------------------------------------


class _FakeClient:
    """Stands in for the portal: serves fixed pages and records how it was called."""

    def __init__(self, pages: list[list[dict[str, Any]]]) -> None:
        self.pages = pages
        self.calls: list[dict[str, Any]] = []

    def get_records(self, dataset_id: str, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append({"dataset_id": dataset_id, **kwargs})
        index = kwargs.get("offset", 0) // kwargs.get("limit", 1)
        return self.pages[index] if index < len(self.pages) else []


def _ingest(tmp_path: Path, client: _FakeClient, monkeypatch: pytest.MonkeyPatch) -> Any:
    from bw_observatory.config import Settings

    settings = Settings(_env_file=None, data_dir=tmp_path, log_dir=tmp_path / "logs")
    ingest = ServiceRequestIngest(settings, client=client, page_size=2)  # type: ignore[arg-type]
    monkeypatch.setattr(ingest, "bounding_box", lambda: (-87.65, 41.78, -87.60, 41.81))
    return ingest


def test_pagination_retrieves_every_page_with_a_stable_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _FakeClient([[_row(sr_number="A"), _row(sr_number="B")], [_row(sr_number="C")]])
    ingest = _ingest(tmp_path, client, monkeypatch)
    records = ingest.fetch_year(2025)

    assert [r["sr_number"] for r in records] == ["A", "B", "C"]
    # Socrata gives no stable order without one, so paging unordered can repeat or skip rows.
    assert all(call["order"] == "sr_number" for call in client.calls)


def test_bronze_write_is_deduplicated_and_carries_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _FakeClient([[]])
    ingest = _ingest(tmp_path, client, monkeypatch)
    result = ingest.write_bronze(
        2025,
        [_row(sr_number="A"), _row(sr_number="A", status="Open"), _row(sr_number="B")],
    )
    assert result.rows_written == 2, "a record id appears once per partition"

    stored = pd.read_parquet(bronze_path(tmp_path, 2025))
    assert set(stored["sr_number"]) == {"A", "B"}
    assert set(stored["source_dataset_id"]) == {"v6vf-nfxy"}
    assert stored["ingested_at"].notna().all()
    assert result.watermark == "2025-03-09T09:00:00.000"


def test_refresh_is_idempotent_and_captures_later_updates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ingest = _ingest(tmp_path, _FakeClient([[]]), monkeypatch)
    ingest.write_bronze(2025, [_row(sr_number="A", status="Open", closed_date=None)])
    first = pd.read_parquet(bronze_path(tmp_path, 2025))

    # Nothing new: the partition is unchanged.
    ingest.client = _FakeClient([[]])  # type: ignore[assignment]
    ingest.refresh_year(2025)
    assert (
        pd.read_parquet(bronze_path(tmp_path, 2025))["status"].tolist() == first["status"].tolist()
    )

    # The same record, later modified and now closed: upserted by id, not duplicated.
    ingest.client = _FakeClient(  # type: ignore[assignment]
        [[_row(sr_number="A", status="Completed", last_modified_date="2025-04-01T09:00:00.000")]]
    )
    ingest.refresh_year(2025)
    updated = pd.read_parquet(bronze_path(tmp_path, 2025))
    assert len(updated) == 1, "an updated record replaces its earlier version"
    assert updated.loc[0, "status"] == "Completed"


def test_the_watermark_only_reflects_what_was_stored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ingest = _ingest(tmp_path, _FakeClient([[]]), monkeypatch)
    assert ingest.watermark_for(2025) is None, "no partition, no watermark"
    ingest.write_bronze(2025, [_row(sr_number="A", last_modified_date="2025-05-05T00:00:00.000")])
    assert ingest.watermark_for(2025) == "2025-05-05T00:00:00.000"


# -- findings calculations ---------------------------------------------------------------
#
# The two pothole findings are DRAFT in config and so are never served. These tests pin what
# their calculations return, which is the precondition for a reviewer being able to check them.


def _calc_context(root: Path, year: int) -> CalcContext:
    """A context for a city-services calculation. `pulse` is unused by them on purpose: a 311
    figure must not be derived from the crime pulse."""
    return CalcContext(data_dir=root, year=year, pulse=None, geography=resolve_geography("ward20"))


def test_pothole_change_calculation_compares_the_same_window(
    tmp_path: Path, layers: ReferenceLayers
) -> None:
    rows_2025 = [
        _row(sr_number=f"P{i}", created_date=f"2025-0{(i % 5) + 1}-10T09:00:00.000")
        for i in range(120)
    ]
    # A record after the 2026 period end, which must not enter the comparison.
    rows_2025.append(_row(sr_number="LATE", created_date="2025-11-30T09:00:00.000"))
    rows_2026 = [
        _row(sr_number=f"C{i}", created_date=f"2026-0{(i % 5) + 1}-10T09:00:00.000")
        for i in range(100)
    ]
    root = _release(tmp_path, layers, {2025: rows_2025, 2026: rows_2026})

    computed = calc_pothole_request_change(_calc_context(root, 2026))
    assert computed.withhold is None
    assert computed.values["count"] == "100"
    # 120, not 121: the November record falls outside the window the 2026 period reaches.
    assert computed.values["prior"] == "120"
    assert computed.direction == "down"


def test_pothole_duplicate_share_withholds_when_there_are_too_few_requests(
    tmp_path: Path, layers: ReferenceLayers
) -> None:
    rows = [
        _row(sr_number=f"P{i}", created_date=f"2026-0{(i % 5) + 1}-10T09:00:00.000")
        for i in range(20)
    ]
    root = _release(tmp_path, layers, {2026: rows})

    computed = calc_pothole_duplicate_share(_calc_context(root, 2026))
    assert computed.withhold == "too few requests for a share to be meaningful"
    assert computed.values == {}


def test_pothole_duplicate_share_reports_the_citys_own_flag(
    tmp_path: Path, layers: ReferenceLayers
) -> None:
    rows = [
        _row(sr_number=f"P{i}", created_date=f"2026-0{(i % 5) + 1}-10T09:00:00.000")
        for i in range(150)
    ]
    for row in rows[:30]:
        row["duplicate"] = True
    root = _release(tmp_path, layers, {2026: rows})

    computed = calc_pothole_duplicate_share(_calc_context(root, 2026))
    assert computed.withhold is None
    assert computed.values["raw"] == "150"
    assert computed.values["duplicates"] == "30"
    assert computed.values["primary"] == "120"
    assert computed.values["share"] == "20%"


def test_pothole_calculations_withhold_rather_than_report_zero_without_data(
    tmp_path: Path, layers: ReferenceLayers
) -> None:
    """311 coverage starts later than crime coverage. A year without service-request data must
    withhold, never publish a zero that reads as "nobody reported a pothole"."""
    rows = [
        _row(sr_number=f"P{i}", created_date=f"2026-0{(i % 5) + 1}-10T09:00:00.000")
        for i in range(150)
    ]
    root = _release(tmp_path, layers, {2026: rows})

    for calculation in (calc_pothole_request_change, calc_pothole_duplicate_share):
        computed = calculation(_calc_context(root, 2019))
        assert computed.withhold is not None, calculation.__name__
        assert computed.values == {}


# -- reconciliation ----------------------------------------------------------------------
#
# A refresh sees inserts and edits. It can never see a withdrawal, because a withdrawn record
# has no timestamp left to fetch. These tests pin what reconciliation does about that, and — the
# part that matters most — that it never deletes anything.


def _reconciler(root: Path, ids: list[str], monkeypatch: pytest.MonkeyPatch) -> Any:
    """A reconciler whose source returns exactly `ids`, with no network and no bbox lookup."""
    settings = Settings(_env_file=None, data_dir=root, log_dir=root / "logs")
    reconciler = ServiceRequestReconciler(settings, client=_FakeClient([[]]))  # type: ignore[arg-type]
    monkeypatch.setattr(reconciler, "source_ids", lambda year: set(ids))
    return reconciler


def test_reconciliation_marks_withdrawn_requests_without_deleting_them(
    tmp_path: Path, layers: ReferenceLayers, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [
        _row(sr_number=f"P{i}", created_date=f"2026-0{(i % 5) + 1}-10T09:00:00.000")
        for i in range(10)
    ]
    root = _release(tmp_path, layers, {2026: rows})
    kept = [f"P{i}" for i in range(8)]

    reconciler = _reconciler(root, kept, monkeypatch)
    result = reconciler.run([2026])

    assert result.status == "complete"
    outcome = result.years[0]
    assert outcome.newly_removed == 2
    assert outcome.confirmed_active == 8
    assert outcome.missing_locally == 0

    silver = pd.read_parquet(silver_path(root, 2026)).set_index("sr_number")
    # Nothing is deleted: the withdrawn rows are still here, carrying the reason.
    assert len(silver) == 10
    assert set(silver.loc[silver["source_status"] == "source_removed"].index) == {"P8", "P9"}
    assert silver.loc["P8", "source_removed_at"]
    assert pd.isna(silver.loc["P0", "source_removed_at"])

    # And they are excluded from every published figure.
    report = build_category_report(root, 2026, "ward20", "potholes")
    assert report.counts.raw == 8


def test_reconciliation_keeps_the_first_observation_of_a_withdrawal(
    tmp_path: Path, layers: ReferenceLayers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second run must not restamp `source_removed_at`. When it first happened is the
    provenance; when we last looked is not."""
    rows = [
        _row(sr_number=f"P{i}", created_date=f"2026-0{(i % 5) + 1}-10T09:00:00.000")
        for i in range(6)
    ]
    root = _release(tmp_path, layers, {2026: rows})
    kept = [f"P{i}" for i in range(5)]

    first = _reconciler(root, kept, monkeypatch).run([2026])
    silver = pd.read_parquet(silver_path(root, 2026)).set_index("sr_number")
    first_seen = silver.loc["P5", "source_removed_at"]
    assert first.years[0].newly_removed == 1

    second = _reconciler(root, kept, monkeypatch).run([2026])
    silver = pd.read_parquet(silver_path(root, 2026)).set_index("sr_number")

    assert second.years[0].newly_removed == 0
    assert second.years[0].still_removed == 1
    assert silver.loc["P5", "source_removed_at"] == first_seen


def test_reconciliation_restores_a_request_that_reappears(
    tmp_path: Path, layers: ReferenceLayers, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [
        _row(sr_number=f"P{i}", created_date=f"2026-0{(i % 5) + 1}-10T09:00:00.000")
        for i in range(6)
    ]
    root = _release(tmp_path, layers, {2026: rows})
    everything = [f"P{i}" for i in range(6)]

    _reconciler(root, everything[:5], monkeypatch).run([2026])
    result = _reconciler(root, everything, monkeypatch).run([2026])

    assert result.years[0].reappeared == 1
    silver = pd.read_parquet(silver_path(root, 2026)).set_index("sr_number")
    assert (silver["source_status"] == "active_in_source").all()
    assert silver["source_removed_at"].isna().all()


def test_reconciliation_reports_ids_the_source_has_but_we_do_not(
    tmp_path: Path, layers: ReferenceLayers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ids present upstream and absent locally mean the refresh has a gap. That is a different
    problem from a withdrawal and is reported separately rather than silently."""
    rows = [_row(sr_number="P1", created_date="2026-02-10T09:00:00.000")]
    root = _release(tmp_path, layers, {2026: rows})

    result = _reconciler(root, ["P1", "P2", "P3"], monkeypatch).run([2026])

    outcome = result.years[0]
    assert outcome.missing_locally == 2
    assert outcome.missing_ids_sample == ["P2", "P3"]
    assert outcome.newly_removed == 0


def test_a_dry_run_reports_without_writing(
    tmp_path: Path, layers: ReferenceLayers, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [
        _row(sr_number=f"P{i}", created_date=f"2026-0{(i % 5) + 1}-10T09:00:00.000")
        for i in range(6)
    ]
    root = _release(tmp_path, layers, {2026: rows})
    before = silver_path(root, 2026).read_bytes()

    result = _reconciler(root, [f"P{i}" for i in range(4)], monkeypatch).run([2026], dry_run=True)

    assert result.years[0].newly_removed == 2
    assert silver_path(root, 2026).read_bytes() == before, "a dry run must not write"
    log = _reconciler(root, [], monkeypatch).read_log()
    assert bool(log.iloc[-1]["dry_run"]) is True


def test_reconciliation_logs_every_run_for_audit(
    tmp_path: Path, layers: ReferenceLayers, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [_row(sr_number="P1", created_date="2026-02-10T09:00:00.000")]
    root = _release(tmp_path, layers, {2026: rows})
    reconciler = _reconciler(root, ["P1"], monkeypatch)
    reconciler.run([2026])

    log = reconciler.read_log()
    assert list(log.columns) == RECONCILIATION_LOG_COLUMNS
    assert len(log) == 1
    assert log.iloc[0]["status"] == "complete"
    assert int(log.iloc[0]["confirmed_active"]) == 1


def test_a_missing_partition_is_an_error_not_a_silent_skip(
    tmp_path: Path, layers: ReferenceLayers, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _release(tmp_path, layers, {2026: [_row(sr_number="P1")]})

    with pytest.raises(FileNotFoundError):
        _reconciler(root, ["P1"], monkeypatch).run([2019])
