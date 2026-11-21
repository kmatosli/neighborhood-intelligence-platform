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
    expected_crime_years,
    read_release_manifest,
    verify_release_manifest,
    write_release_manifest,
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
    assert set(manifest.silver_sha256) == {str(y) for y in range(2006, 2027)}
    assert manifest.source_dataset_id == "ijzp-q8t2"
    assert set(manifest.config_sha256) == {"crime_categories.yml", "geographies.yml"}
    assert verify_release_manifest(root, CONFIG_DIR) == []


def test_release_ids_must_say_what_they_are(root: Path) -> None:
    with pytest.raises(ReleaseManifestError):
        build_release_manifest(root, CONFIG_DIR, "data", STATUS_RELEASE)
    with pytest.raises(ReleaseManifestError):
        build_release_manifest(root, CONFIG_DIR, "bw-release-20261028", "development")
    assert build_release_manifest(root, CONFIG_DIR, "bw-release-20261028", STATUS_RELEASE)


def _misplaced(tmp_path: Path) -> Path:
    """A sound 2026-07-26 release (with PASSing Gold) sitting in a 2026-09-21 directory."""
    staged = write_root(
        tmp_path / "staging", _rows(), release_id="bw-release-20260726", status=STATUS_RELEASE
    )
    build_crime_gold(staged, CONFIG_DIR)
    return staged.rename(tmp_path / "bw-release-20260921")


def test_a_public_release_directory_matching_its_release_id_passes(tmp_path: Path) -> None:
    root = write_root(
        tmp_path / "bw-release-20260921",
        _rows(),
        release_id="bw-release-20260921",
        status=STATUS_RELEASE,
    )
    assert read_release_manifest(root).release_id == "bw-release-20260921"
    assert verify_release_manifest(root, CONFIG_DIR) == []
    build_crime_gold(root, CONFIG_DIR)
    assert check_gold(root, CONFIG_DIR).release_id == "bw-release-20260921"


def test_a_public_release_directory_contradicting_its_release_id_fails(tmp_path: Path) -> None:
    root = _misplaced(tmp_path)
    contradiction = "'bw-release-20260921' contradicts its release.json release_id"
    with pytest.raises(ReleaseManifestError, match=contradiction):
        read_release_manifest(root)
    assert any(contradiction in p for p in verify_release_manifest(root, CONFIG_DIR))
    with pytest.raises(GoldUnavailable) as refused:
        check_gold(root, CONFIG_DIR)  # Gold itself PASSed; the root it sits in is the lie
    assert refused.value.condition == UNAVAILABLE and contradiction in refused.value.reason
    with pytest.raises(GoldBuildError, match=contradiction):
        build_crime_gold(root, CONFIG_DIR)
    # Nor can a contradictory manifest be written there; nothing is renamed or rewritten.
    with pytest.raises(ReleaseManifestError, match=contradiction):
        build_release_manifest(root, CONFIG_DIR, "bw-release-20260726", STATUS_RELEASE)
    assert root.name == "bw-release-20260921"
    assert json.loads((root / "release.json").read_text("utf-8"))["release_id"] == (
        "bw-release-20260726"
    )


@pytest.mark.parametrize(
    ("directory", "release_id", "status"),
    [
        ("release", "dev-test", "development"),  # a test root
        ("candidate-2026-11", "bw-release-20261115", STATUS_RELEASE),  # a staging root
        ("tmp8x2k_scratch", "bw-release-20260921", STATUS_RELEASE),  # a scratch extraction
    ],
)
def test_a_root_not_named_like_a_public_release_is_not_rejected_for_its_name(
    tmp_path: Path, directory: str, release_id: str, status: str
) -> None:
    root = write_root(tmp_path / directory, _rows(), release_id=release_id, status=status)
    assert read_release_manifest(root).release_id == release_id
    assert verify_release_manifest(root, CONFIG_DIR) == []


SERVING_REFUSAL = "a production process serves only status 'release' releases"


def test_a_development_release_is_served_outside_production(root: Path) -> None:
    build_crime_gold(root, CONFIG_DIR)
    assert read_release_manifest(root).status == "development"
    assert check_gold(root, CONFIG_DIR).release_id == "dev-test"


@pytest.mark.parametrize("variable", ["BW_PRODUCTION", "RENDER"])
def test_a_production_process_refuses_a_development_release(
    root: Path, monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    build_crime_gold(root, CONFIG_DIR)
    monkeypatch.setenv(variable, "true")
    with pytest.raises(GoldUnavailable) as refused:
        check_gold(root, CONFIG_DIR)
    assert refused.value.condition == UNAVAILABLE and SERVING_REFUSAL in refused.value.reason
    # A serving rule, not a validity rule: the manifest still reads and verifies, tooling can
    # still build Gold for it, and nothing was promoted or rewritten.
    assert read_release_manifest(root).status == "development"
    assert verify_release_manifest(root, CONFIG_DIR) == []
    assert build_crime_gold(root, CONFIG_DIR).status == "PASS"


def test_an_explicit_non_production_setting_overrides_the_platform_default(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_crime_gold(root, CONFIG_DIR)
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("BW_PRODUCTION", "false")
    assert check_gold(root, CONFIG_DIR).release_id == "dev-test"


def test_a_production_process_serves_a_public_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = write_root(
        tmp_path / "bw-release-20260921",
        _rows(),
        release_id="bw-release-20260921",
        status=STATUS_RELEASE,
    )
    build_crime_gold(root, CONFIG_DIR)
    monkeypatch.setenv("RENDER", "true")
    assert check_gold(root, CONFIG_DIR).release_id == "bw-release-20260921"


def test_a_production_process_still_refuses_a_misplaced_public_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _misplaced(tmp_path)
    monkeypatch.setenv("RENDER", "true")
    with pytest.raises(GoldUnavailable) as refused:
        check_gold(root, CONFIG_DIR)
    assert "contradicts its release.json release_id" in refused.value.reason


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


def test_silver_changed_without_a_ledger_write_fails_the_build(root: Path) -> None:
    # A whole-year re-enrichment rewrites Silver and touches no ledger file, so only the full
    # checksums in release.json can tell; Gold must not reconcile to Silver release.json lacks.
    silver = root / "silver" / "crime" / "crime_with_geography" / "2025.parquet"
    frame = pd.read_parquet(silver)
    frame.loc[frame["id"] == "a1", "spatial_ward_current"] = "5"
    frame.to_parquet(silver, index=False)
    with pytest.raises(GoldBuildError, match="Silver 2025 checksum"):
        build_crime_gold(root, CONFIG_DIR)
    with pytest.raises(GoldUnavailable) as refused:
        check_gold(root, CONFIG_DIR)
    assert refused.value.condition == STALE


def _remove_partition(root: Path, layer: str, year: int) -> None:
    """Drop one year's partition and re-cut release.json so only the year rule can object."""
    subdir = "bronze/crime" if layer == "bronze" else "silver/crime/crime_with_geography"
    (root / subdir / f"{year}.parquet").unlink()
    write_release_manifest(
        root, build_release_manifest(root, CONFIG_DIR, "dev-test", "development", commit="test")
    )


def test_expected_years_run_from_2006_to_the_data_through_year() -> None:
    assert expected_crime_years("2026-09-06") == range(2006, 2027)
    assert expected_crime_years("2027-01-15") == range(2006, 2028)  # no source edit for 2027


def test_a_contiguous_2006_to_data_through_release_builds(root: Path) -> None:
    build = build_crime_gold(root, CONFIG_DIR)
    assert build.years == list(range(2006, 2027)) and not build.failures


def test_a_2027_release_requires_2027(tmp_path: Path) -> None:
    rows = [row("a", "2026-03-01", "THEFT"), row("b", "2027-01-15", "THEFT")]
    assert build_crime_gold(write_root(tmp_path / "ok", rows), CONFIG_DIR).years == list(
        range(2006, 2028)
    )
    short = write_root(tmp_path / "short", rows)
    _remove_partition(short, "silver", 2027)
    with pytest.raises(GoldBuildError, match="Silver is missing years: 2027"):
        build_crime_gold(short, CONFIG_DIR)


@pytest.mark.parametrize(
    ("layer", "year"),
    [("silver", 2006), ("bronze", 2006), ("silver", 2015), ("bronze", 2015), ("silver", 2026)],
)
def test_a_missing_first_middle_or_last_year_fails_the_build_rather_than_reading_as_zero(
    root: Path, layer: str, year: int
) -> None:
    _remove_partition(root, layer, year)
    with pytest.raises(GoldBuildError, match=rf"{layer.capitalize()} is missing years: {year}"):
        build_crime_gold(root, CONFIG_DIR)
    assert not (gold_dir(root) / "coverage.parquet").exists()


def test_a_year_after_data_through_fails_the_build(root: Path) -> None:
    # data_through is 2026-02-14; a 2027 partition would be counted beyond what the release
    # says it covers.
    silver = root / "silver" / "crime" / "crime_with_geography"
    (silver / "2027.parquet").write_bytes((silver / "2025.parquet").read_bytes())
    write_release_manifest(
        root, build_release_manifest(root, CONFIG_DIR, "dev-test", "development", commit="test")
    )
    with pytest.raises(GoldBuildError, match="Silver has years outside 2006-2026: 2027"):
        build_crime_gold(root, CONFIG_DIR)


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
    assert coverage["date"].min() == date(2006, 1, 1)
    assert coverage["date"].max() == date(2026, 2, 14)  # nothing after data-through
    assert covered(coverage, date(2026, 2, 1), date(2026, 2, 14))
    assert not covered(coverage, date(2026, 2, 1), date(2026, 2, 15))  # future ≠ zero
    assert not covered(coverage, date(2005, 12, 31), date(2006, 1, 2))  # before history
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


# -- revision reason semantics -----------------------------------------------------------


def test_revision_reasons_follow_the_current_source_view(tmp_path: Path) -> None:
    from bw_observatory.gold.revisions import _in_geography, _states, _ward, _ward_ids

    withdrawn = {"source_status": "source_removed"}
    prior_root = write_root(
        tmp_path / "p",
        [
            row("s1", "2025-01-05", "THEFT"),  # unchanged: no row
            row("a1", "2025-01-06", "THEFT"),  # active → source_removed
            row("a2", "2025-01-07", "THEFT"),  # active → absent
            row("r1", "2025-01-08", "THEFT", **withdrawn),  # source_removed → active
            row("g1", "2025-01-09", "THEFT", **withdrawn),  # source_removed → absent
            row("mt", "2025-01-12", "THEFT"),  # type + date + geography all change
        ],
        release_id="dev-prior",
    )
    current_root = write_root(
        tmp_path / "c",
        [
            row("s1", "2025-01-05", "THEFT"),
            row("a1", "2025-01-06", "THEFT", **withdrawn),
            row("r1", "2025-01-08", "THEFT"),
            row("mt", "2025-03-03", "BURGLARY", fbi_code="05", spatial_ca="68"),
            row("n1", "2025-01-10", "THEFT"),  # absent → active
        ],
        release_id="dev-current",
    )
    proof = build_revision_events(prior_root, current_root)
    assert proof.status == "PASS"  # the cell invariant held, or nothing was published
    found = latest_revision(current_root, "dev-current")
    assert found is not None
    events = found[1]

    # One changed incident, one row - including the record that stopped being published
    # after it had already left the analytical view.
    assert sorted(events["id"]) == ["a1", "a2", "g1", "mt", "n1", "r1"]
    assert events["id"].is_unique
    flags = events.set_index("id")[REASONS]
    reasons = {i: sorted(r for r in REASONS if flags.loc[i, r]) for i in flags.index}
    assert reasons == {
        "a1": ["removed"],
        "a2": ["removed"],
        "r1": ["restored"],
        "g1": [],  # not a second removal
        "n1": ["added"],
        "mt": ["date_changed", "geography_changed", "reclassified"],
    }
    g1 = events.set_index("id").loc["g1"]
    assert g1["exists_prior"] and not g1["exists_current"]
    assert g1["old_source_status"] == "source_removed"
    # Reason flags are not additive: mt carries three and g1 none, so their sum is no count.
    assert int(flags.to_numpy().sum()) == 7 and len(events) == 6

    # Flow comes from cell membership, never from reasons: g1 enters and leaves nothing.
    geographies = built_geographies()
    ward = _ward(geographies)
    g1_row = events[events["id"] == "g1"]
    assert not _in_geography(g1_row, "old_", ward).any()
    assert not _in_geography(g1_row, "new_", ward).any()
    ids = _ward_ids(prior_root, ward) | _ward_ids(current_root, ward)
    prior, current = _states(prior_root, ids), _states(current_root, ids)
    assert check_cell_invariant(prior, current, events, geographies)[1] == []


# -- revision ordering -------------------------------------------------------------------


def _comparisons(pair: tuple[Path, Path], specs: list[tuple[str, str | None, str, str]]) -> Path:
    """Real events from one build, filed as several comparisons into `dev-current`.

    Each spec is (prior id, prior cut_at or None for a legacy proof, status, current id).
    The original comparison is removed so only the specs compete.
    """
    import shutil

    from bw_observatory.gold.revisions import EVENTS_FILENAME, PROOF_FILENAME, REVISIONS_DIR

    prior, current = pair
    build_revision_events(prior, current)
    folder = gold_dir(current) / REVISIONS_DIR
    source = folder / "dev-prior__dev-current"
    for prior_id, cut_at, status, current_id in specs:
        target = folder / f"{prior_id}__{current_id}"
        target.mkdir()
        shutil.copyfile(source / EVENTS_FILENAME, target / EVENTS_FILENAME)
        proof = json.loads((source / PROOF_FILENAME).read_text("utf-8"))
        proof.update(prior_release_id=prior_id, status=status, current_release_id=current_id)
        if cut_at is None:
            del proof["prior_cut_at"]
        else:
            proof["prior_cut_at"] = cut_at
        (target / PROOF_FILENAME).write_text(json.dumps(proof), "utf-8")
    shutil.rmtree(source)
    return current


def _chosen(current: Path) -> str | None:
    found = latest_revision(current, "dev-current")
    return None if found is None else found[0].prior_release_id


def test_a_revision_proof_records_both_release_cuts(pair: tuple[Path, Path]) -> None:
    prior, current = pair
    proof = build_revision_events(prior, current)
    assert proof.prior_cut_at == read_release_manifest(prior).cut_at
    assert proof.current_cut_at == read_release_manifest(current).cut_at


def test_the_latest_revision_is_the_most_recently_cut_prior_release(
    pair: tuple[Path, Path],
) -> None:
    current = _comparisons(
        pair,
        [
            ("bw-release-20260726", "2026-07-26T00:00:00+00:00", "PASS", "dev-current"),
            ("bw-release-20260921", "2026-09-21T00:00:00+00:00", "PASS", "dev-current"),
        ],
    )
    assert _chosen(current) == "bw-release-20260921"


@pytest.mark.parametrize(
    ("dev_cut", "expected"),
    [
        # `dev-zzz` sorts after every `bw-release-*` id but was cut earlier: it loses.
        ("2026-01-01T00:00:00+00:00", "bw-release-20260921"),
        # And a development release cut later wins on chronology, not on its name.
        ("2026-10-01T00:00:00+00:00", "dev-zzz"),
    ],
)
def test_string_order_never_decides_which_revision_is_latest(
    pair: tuple[Path, Path], dev_cut: str, expected: str
) -> None:
    current = _comparisons(
        pair,
        [
            ("bw-release-20260921", "2026-09-21T00:00:00+00:00", "PASS", "dev-current"),
            ("dev-zzz", dev_cut, "PASS", "dev-current"),
        ],
    )
    assert _chosen(current) == expected


def test_legacy_proofs_use_a_public_id_date_and_never_guess_a_development_one(
    pair: tuple[Path, Path], tmp_path: Path
) -> None:
    # A legacy public proof (no prior_cut_at) is dated by its id, and beats a newer-format
    # proof cut earlier. A legacy dev proof has no chronology and is not eligible at all.
    current = _comparisons(
        pair,
        [
            ("bw-release-20260921", None, "PASS", "dev-current"),
            ("bw-release-20260726", "2026-08-01T00:00:00+00:00", "PASS", "dev-current"),
            ("dev-zzz", None, "PASS", "dev-current"),
        ],
    )
    assert _chosen(current) == "bw-release-20260921"
    assert _chosen(current) == "bw-release-20260921"  # deterministic

    prior2 = write_root(tmp_path / "p2", _prior_rows(), release_id="dev-prior")
    current2 = write_root(tmp_path / "c2", _current_rows(), release_id="dev-current")
    only_dev = _comparisons((prior2, current2), [("dev-zzz", None, "PASS", "dev-current")])
    assert _chosen(only_dev) is None  # excluded, not chosen by string order


def test_only_passing_comparisons_into_this_release_are_eligible(pair: tuple[Path, Path]) -> None:
    current = _comparisons(
        pair,
        [
            ("bw-release-20260726", "2026-07-26T00:00:00+00:00", "PASS", "dev-current"),
            ("bw-release-20260921", "2026-09-21T00:00:00+00:00", "FAIL", "dev-current"),
            ("bw-release-20261001", "2026-10-01T00:00:00+00:00", "PASS", "dev-elsewhere"),
        ],
    )
    assert _chosen(current) == "bw-release-20260726"


def test_the_chosen_comparison_carries_the_same_events(pair: tuple[Path, Path]) -> None:
    prior, current = pair
    build_revision_events(prior, current)
    found = latest_revision(current, "dev-current")
    assert found is not None
    built = found[1]
    chosen = _comparisons(
        pair,
        [
            ("bw-release-20260726", "2026-07-26T00:00:00+00:00", "PASS", "dev-current"),
            ("bw-release-20260921", "2026-09-21T00:00:00+00:00", "PASS", "dev-current"),
        ],
    )
    selected = latest_revision(chosen, "dev-current")
    assert selected is not None
    pd.testing.assert_frame_equal(selected[1], built)
