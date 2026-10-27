"""Release identity, Gold crime aggregates and incident-level revision events.

The aggregates are a cache with a proof: every test here pins one way the proof must hold,
or one way a broken input must be refused rather than served.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from crime_release_fixtures import CONFIG_DIR, row, write_root

from bw_observatory.gold.crime_aggregates import (
    BUILD_FAIL,
    STALE,
    UNAVAILABLE,
    GoldBuildError,
    GoldUnavailable,
    build_crime_gold,
    built_geographies,
    check_gold,
    covered,
    gold_dir,
    load_coverage,
    load_daily_counts,
)
from bw_observatory.gold.revisions import (
    REASONS,
    build_events,
    build_revision_events,
    check_cell_invariant,
    latest_revision,
)
from bw_observatory.release import (
    STATUS_RELEASE,
    ReleaseManifestError,
    build_release_manifest,
    read_release_manifest,
    verify_release_manifest,
)


def _rows() -> list[dict[str, object]]:
    return [
        row("a1", "2025-01-05", "THEFT"),
        row("a2", "2025-01-05", "THEFT"),
        row("a3", "2025-02-10", "BATTERY", fbi_code="08B"),
        # Englewood portion of the ward
        row("e1", "2025-03-01", "ROBBERY", fbi_code="03", spatial_ca="68"),
        # withdrawn by the source: kept, counted separately, never in `count`
        row("r1", "2025-03-02", "THEFT", source_status="source_removed"),
        # published as Ward 20 but mapped outside it: not a Ward 20 record
        row("x1", "2025-03-03", "THEFT", spatial_ward="5", spatial_ca="68", source_ward="20"),
        # published as Ward 5 but mapped inside it: a Ward 20 record
        row("x2", "2025-03-04", "NARCOTICS", fbi_code="18", source_ward="5"),
        row("b1", "2026-01-02", "THEFT"),
        row("b2", "2026-02-14", "ASSAULT", fbi_code="04A"),
    ]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return write_root(tmp_path / "release", _rows())


def test_release_manifest_is_self_describing(root: Path) -> None:
    manifest = read_release_manifest(root)
    assert manifest.release_id == "dev-test" and manifest.status == "development"
    assert manifest.data_through == "2026-02-14"
    assert set(manifest.silver_sha256) == {"2025", "2026"}
    assert manifest.source_dataset_id == "ijzp-q8t2"
    assert set(manifest.config_sha256) == {"crime_categories.yml", "geographies.yml"}
    assert verify_release_manifest(root, CONFIG_DIR) == []


def test_release_ids_must_say_what_they_are(root: Path) -> None:
    with pytest.raises(ReleaseManifestError):
        build_release_manifest(root, CONFIG_DIR, "data", STATUS_RELEASE)
    with pytest.raises(ReleaseManifestError):
        build_release_manifest(root, CONFIG_DIR, "bw-release-20261028", "development")
    assert build_release_manifest(root, CONFIG_DIR, "bw-release-20261028", STATUS_RELEASE)


def test_release_verification_catches_a_changed_silver_partition(root: Path) -> None:
    silver = root / "silver" / "crime" / "crime_with_geography" / "2025.parquet"
    frame = pd.read_parquet(silver)
    frame.loc[0, "source_status"] = "source_removed"
    frame.to_parquet(silver, index=False)
    assert any("Silver 2025" in p for p in verify_release_manifest(root, CONFIG_DIR))


def test_gold_reconciles_to_silver_for_every_year_and_geography(root: Path) -> None:
    build = build_crime_gold(root, CONFIG_DIR)
    assert build.status == "PASS" and build.release_id == "dev-test"
    ward = load_daily_counts(root, "ward20")
    totals = ward.groupby("year")["count"].sum().to_dict()
    # 2025: a1 a2 a3 e1 x2 (x1 is outside, r1 withdrawn); 2026: b1 b2
    assert totals == {2025: 5, 2026: 2}
    assert int(ward["count_source_removed"].sum()) == 1
    assert int(load_daily_counts(root, "englewood")["count"].sum()) == 1
    assert int(load_daily_counts(root, "woodlawn")["count"].sum()) == 6
    for year, checks in build.reconciliation.items():
        assert all(c["pass"] for c in checks.values()), year
        assert checks["portions_sum_to_ward"]["pass"]


def test_membership_is_spatial_never_the_published_ward(root: Path) -> None:
    build_crime_gold(root, CONFIG_DIR)
    ward = load_daily_counts(root, "ward20")
    published_types = ward.groupby("primary_type")["count"].sum().to_dict()
    assert published_types.get("NARCOTICS") == 1  # x2: published ward 5, mapped ward 20
    days = set(ward["date"])
    assert date(2025, 3, 3) not in days  # x1: published ward 20, mapped ward 5


def test_no_unsupported_geography_is_fabricated(root: Path) -> None:
    build = build_crime_gold(root, CONFIG_DIR)
    built = set(build.geographies)
    assert "ward20" in built and "woodlawn" in built
    assert "bronzeville" not in built and "back-of-the-yards" not in built
    daily = pd.read_parquet(gold_dir(root) / "daily_counts.parquet")
    assert set(daily["geography_id"]) <= built
    assert not (daily["count"] == 0).all()  # no zero rows invented for absent geographies


def test_a_ward_row_outside_every_validated_portion_fails_the_build(tmp_path: Path) -> None:
    root = write_root(tmp_path / "r", [*_rows(), row("q1", "2025-04-01", "THEFT", spatial_ca="99")])
    with pytest.raises(GoldBuildError, match="portions"):
        build_crime_gold(root, CONFIG_DIR)
    record = json.loads((gold_dir(root) / "_build.json").read_text("utf-8"))
    assert record["status"] == BUILD_FAIL
    assert not (gold_dir(root) / "daily_counts.parquet").exists()
    with pytest.raises(GoldUnavailable) as refused:
        check_gold(root, CONFIG_DIR)
    assert refused.value.condition == STALE


def test_an_undated_silver_row_still_reconciles_and_is_not_placed_on_a_day(
    tmp_path: Path,
) -> None:
    root = write_root(tmp_path / "r", [*_rows(), row("u1", "2025-05-01", "THEFT", bronze=False)])
    build = build_crime_gold(root, CONFIG_DIR)
    assert build.reconciliation["2025"]["ward20"]["undated_current"] == 1
    assert int(load_daily_counts(root, "ward20").query("year == 2025")["count"].sum()) == 5


def test_coverage_distinguishes_missing_future_and_partial_from_zero(root: Path) -> None:
    build_crime_gold(root, CONFIG_DIR)
    coverage = load_coverage(root)
    assert coverage["date"].min() == date(2025, 1, 1)
    assert coverage["date"].max() == date(2026, 2, 14)  # nothing after data-through
    assert covered(coverage, date(2026, 2, 1), date(2026, 2, 14))
    assert not covered(coverage, date(2026, 2, 1), date(2026, 2, 15))  # future ≠ zero
    assert not covered(coverage, date(2024, 12, 31), date(2025, 1, 2))  # before history
    february = coverage[(coverage["year"] == 2026) & (coverage["month"] == 2)]
    january = coverage[(coverage["year"] == 2026) & (coverage["month"] == 1)]
    assert not february["month_complete"].any() and january["month_complete"].all()
    assert coverage.loc[coverage["date"] == date(2026, 2, 14), "provisional"].item()


def test_runtime_check_accepts_a_sound_build_and_refuses_changed_inputs(root: Path) -> None:
    build_crime_gold(root, CONFIG_DIR)
    assert check_gold(root, CONFIG_DIR).status == "PASS"

    log = root / "bronze" / "crime" / "reconciliation_log.parquet"
    pd.DataFrame([{"run_id": "late", "year": 2025}]).to_parquet(log, index=False)
    with pytest.raises(GoldUnavailable) as refused:
        check_gold(root, CONFIG_DIR)
    assert refused.value.condition == STALE and "ledger" in refused.value.reason


def test_runtime_check_refuses_a_root_without_identity_or_gold(tmp_path: Path) -> None:
    bare = write_root(tmp_path / "bare", _rows(), with_manifest=False)
    with pytest.raises(GoldUnavailable) as no_identity:
        check_gold(bare, CONFIG_DIR)
    assert no_identity.value.condition == UNAVAILABLE
    named = write_root(tmp_path / "named", _rows())
    with pytest.raises(GoldUnavailable) as no_gold:
        check_gold(named, CONFIG_DIR)
    assert no_gold.value.condition == UNAVAILABLE


def test_gold_built_for_another_release_is_stale(root: Path, tmp_path: Path) -> None:
    build_crime_gold(root, CONFIG_DIR)
    record_path = gold_dir(root) / "_build.json"
    record = json.loads(record_path.read_text("utf-8"))
    record["release_id"] = "dev-other"
    record_path.write_text(json.dumps(record), "utf-8")
    with pytest.raises(GoldUnavailable) as refused:
        check_gold(root, CONFIG_DIR)
    assert refused.value.condition == STALE


# -- revision events ---------------------------------------------------------------------


def _prior_rows() -> list[dict[str, object]]:
    return [
        row("s1", "2025-01-05", "THEFT"),  # unchanged
        row("m1", "2025-01-06", "THEFT"),  # reclassified AND re-dated: one event, two reasons
        row("w1", "2025-01-07", "THEFT"),  # withdrawn by the source in the current release
        row("o1", "2025-01-08", "THEFT"),  # moves out of the ward
        row("k1", "2025-01-09", "ROBBERY", fbi_code="03"),  # arrest flag flips
    ]


def _current_rows() -> list[dict[str, object]]:
    return [
        row("s1", "2025-01-05", "THEFT"),
        row("m1", "2025-02-11", "BURGLARY", fbi_code="05"),
        row("w1", "2025-01-07", "THEFT", source_status="source_removed"),
        row("o1", "2025-01-08", "THEFT", spatial_ward="5", spatial_ca="68"),
        row("k1", "2025-01-09", "ROBBERY", fbi_code="03", arrest="true"),
        row("n1", "2025-01-10", "THEFT"),  # new
    ]


@pytest.fixture
def pair(tmp_path: Path) -> tuple[Path, Path]:
    prior = write_root(tmp_path / "prior", _prior_rows(), release_id="dev-prior")
    current = write_root(tmp_path / "current", _current_rows(), release_id="dev-current")
    return prior, current


def test_revision_events_record_each_changed_incident_once(pair: tuple[Path, Path]) -> None:
    prior, current = pair
    proof = build_revision_events(prior, current)
    assert proof.status == "PASS" and proof.cells_checked > 0
    found = latest_revision(current, "dev-current")
    assert found is not None
    _, events = found
    assert sorted(events["id"]) == ["k1", "m1", "n1", "o1", "w1"]  # s1 unchanged → absent
    assert events["id"].is_unique
    m1 = events.set_index("id").loc["m1"]
    assert m1["reclassified"] and m1["date_changed"] and not m1["added"]
    assert m1["old_primary_type"] == "THEFT" and m1["new_primary_type"] == "BURGLARY"
    flags = events.set_index("id")[REASONS]
    assert flags.loc["n1", "added"] and flags.loc["w1", "removed"]
    assert flags.loc["o1", "geography_changed"] and flags.loc["k1", "arrest_changed"]
    assert set(events["prior_release_id"]) == {"dev-prior"}
    assert set(events["current_release_id"]) == {"dev-current"}
    # Summing reason flags over-counts: m1 alone carries two.
    assert int(flags.to_numpy().sum()) > len(events)


def test_cell_invariant_holds_and_catches_a_missing_event(pair: tuple[Path, Path]) -> None:
    from bw_observatory.gold.revisions import _states, _ward, _ward_ids

    prior_root, current_root = pair
    geographies = built_geographies()
    ward = _ward(geographies)
    ids = _ward_ids(prior_root, ward) | _ward_ids(current_root, ward)
    prior, current = _states(prior_root, ids), _states(current_root, ids)
    events = build_events(prior, current)
    _, failures = check_cell_invariant(prior, current, events, geographies)
    assert failures == []
    _, broken = check_cell_invariant(prior, current, events[events["id"] != "m1"], geographies)
    assert broken  # dropping one event breaks current − prior = entries − exits


def test_revision_build_refuses_two_roots_with_one_identity(tmp_path: Path) -> None:
    from bw_observatory.gold.revisions import RevisionBuildError

    prior = write_root(tmp_path / "p", _prior_rows(), release_id="dev-same")
    current = write_root(tmp_path / "c", _current_rows(), release_id="dev-same")
    with pytest.raises(RevisionBuildError):
        build_revision_events(prior, current)
