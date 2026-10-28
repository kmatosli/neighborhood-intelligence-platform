"""Crime Trends — Change: windows, decomposition, composition, history, trend, revisions, API.

Each test pins one rule the Change analysis must keep so a reader is not misled: like-for-like
periods, every type reconciled to the total, counts before percentages, overlays that never
pretend to be a partition, descriptive (never causal) language, and refusal over guesswork.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from crime_release_fixtures import CONFIG_DIR, row, write_root

from bw_observatory.gold.crime_aggregates import build_crime_gold, load_coverage, load_daily_counts
from bw_observatory.gold.revisions import build_revision_events
from bw_observatory.presentation.change import (
    WINDOW_FULL_YEAR,
    WINDOW_TRAILING,
    WINDOW_YTD,
    WindowUnavailable,
    build_change,
    composition,
    decompose,
    history,
    kendall_trend,
    load_overlays,
    min_prior_rules,
    resolve_window,
    response_strings,
    shift_years,
)


def _monthly_rows() -> list[dict[str, object]]:
    """One THEFT on the 15th of every month, Jan 2023 – Jan 2026, plus a final 14 Feb 2026."""
    rows = []
    for year in (2023, 2024, 2025):
        for month in range(1, 13):
            rows.append(row(f"m{year}{month:02d}", f"{year}-{month:02d}-15", "THEFT"))
    rows.append(row("m202601", "2026-01-15", "THEFT"))
    rows.append(row("m202602", "2026-02-14", "THEFT"))
    return rows


def _mix_rows() -> list[dict[str, object]]:
    return [
        # Jan–14 Feb 2025 (comparison for a 2026 YTD)
        *[row(f"b25{i}", "2025-01-10", "BATTERY", fbi_code="08B") for i in range(30)],
        *[row(f"n25{i}", "2025-02-01", "NARCOTICS", fbi_code="18") for i in range(3)],
        row("h25", "2025-02-02", "HOMICIDE", fbi_code="01A"),
        # Jan–14 Feb 2026
        *[row(f"b26{i}", "2026-01-10", "BATTERY", fbi_code="08B") for i in range(20)],
        *[row(f"n26{i}", "2026-02-01", "NARCOTICS", fbi_code="18") for i in range(9)],
        row("r26", "2026-02-03", "ROBBERY", fbi_code="03"),
        row("ab26", "2026-02-04", "BATTERY", fbi_code="04B"),
        row("aa26", "2026-02-05", "ASSAULT", fbi_code="04A"),
        row("cs26", "2026-02-06", "CRIMINAL SEXUAL ASSAULT", fbi_code="02"),
        row("rh26", "2026-02-07", "HOMICIDE", fbi_code="01B"),  # reckless homicide: excluded
        row("sa26", "2026-02-08", "ASSAULT", fbi_code="08A"),  # simple assault: excluded
        row("mvt26", "2026-02-09", "MOTOR VEHICLE THEFT", fbi_code="07"),
        row("e26", "2026-02-10", "THEFT", spatial_ca="68"),  # Englewood portion
        row("last", "2026-02-14", "THEFT"),
    ]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    built = write_root(tmp_path / "release", [*_monthly_rows(), *_mix_rows()])
    build_crime_gold(built, CONFIG_DIR)
    return built


# -- windows ---------------------------------------------------------------------------


def test_ytd_compares_the_same_inclusive_span(root: Path) -> None:
    window = resolve_window(WINDOW_YTD, 2026, date(2026, 2, 14), load_coverage(root))
    assert (window.start, window.end) == (date(2026, 1, 1), date(2026, 2, 14))
    assert (window.comparison_start, window.comparison_end) == (
        date(2025, 1, 1),
        date(2025, 2, 14),
    )


def test_leap_day_clamps_to_28_february() -> None:
    assert shift_years(date(2024, 2, 29), -1) == date(2023, 2, 28)
    assert shift_years(date(2024, 2, 28), -1) == date(2023, 2, 28)


def test_trailing_12_month_boundaries_are_contiguous_and_inclusive(root: Path) -> None:
    window = resolve_window(WINDOW_TRAILING, 2026, date(2026, 2, 14), load_coverage(root))
    assert (window.start, window.end) == (date(2025, 2, 15), date(2026, 2, 14))
    assert (window.comparison_start, window.comparison_end) == (
        date(2024, 2, 15),
        date(2025, 2, 14),
    )


def _days(first: date, last: date) -> pd.DataFrame:
    return pd.DataFrame({"date": pd.date_range(first, last, freq="D").date})


def test_trailing_12_months_are_exact_calendar_periods_across_leap_years() -> None:
    coverage = _days(date(2022, 1, 1), date(2025, 12, 31))
    # Ending 28 Feb after a leap year: starts 1 Mar, never on the previous 29 Feb.
    after_leap = resolve_window(WINDOW_TRAILING, 2025, date(2025, 2, 28), coverage)
    assert (after_leap.start, after_leap.end) == (date(2024, 3, 1), date(2025, 2, 28))
    assert (after_leap.comparison_start, after_leap.comparison_end) == (
        date(2023, 3, 1),
        date(2024, 2, 29),
    )
    on_leap = resolve_window(WINDOW_TRAILING, 2024, date(2024, 2, 29), coverage)
    assert (on_leap.start, on_leap.end) == (date(2023, 3, 1), date(2024, 2, 29))
    assert (on_leap.comparison_start, on_leap.comparison_end) == (
        date(2022, 3, 1),
        date(2023, 2, 28),
    )
    # Each period is exactly 12 calendar months; only the one holding 29 Feb has 366 days.
    model = after_leap.model()
    assert (model.current.days, model.comparison.days) == (365, 366)


def test_full_year_never_compares_a_partial_year(root: Path) -> None:
    window = resolve_window(WINDOW_FULL_YEAR, 2026, date(2026, 2, 14), load_coverage(root))
    assert (window.start, window.end) == (date(2025, 1, 1), date(2025, 12, 31))
    assert window.note is not None and "not complete" in window.note


def test_an_uncovered_comparison_is_refused_not_zero(root: Path) -> None:
    with pytest.raises(WindowUnavailable):
        resolve_window(WINDOW_YTD, 2023, date(2026, 2, 14), load_coverage(root))
    with pytest.raises(WindowUnavailable):
        resolve_window(WINDOW_YTD, 2027, date(2026, 2, 14), load_coverage(root))


# -- decomposition ---------------------------------------------------------------------


def _ytd(root: Path) -> tuple[pd.DataFrame, object]:
    counts = load_daily_counts(root, "ward20")
    window = resolve_window(WINDOW_YTD, 2026, date(2026, 2, 14), load_coverage(root))
    return counts, window


def test_every_type_is_listed_and_changes_reconcile_exactly(root: Path) -> None:
    counts, window = _ytd(root)
    result = decompose(counts, window)  # type: ignore[arg-type]
    present = set(
        counts[(counts["date"] >= date(2025, 1, 1)) & (counts["count"] > 0)]["primary_type"]
    )
    assert {t.primary_type for t in result.types} == present  # no top-N truncation
    assert result.reconciles
    assert result.sum_of_type_changes == result.total.absolute_change
    assert sum(t.current for t in result.types) == result.total.current
    assert sum(t.comparison for t in result.types) == result.total.comparison


def test_percent_is_withheld_below_min_prior_but_counts_remain(root: Path) -> None:
    counts, window = _ytd(root)
    result = decompose(counts, window)  # type: ignore[arg-type]
    overall_min, type_min = min_prior_rules()
    assert (result.min_prior_total, result.min_prior_type) == (overall_min, type_min)
    narcotics = next(t for t in result.types if t.primary_type == "NARCOTICS")
    assert narcotics.comparison < type_min
    assert narcotics.percent_change is None and narcotics.percent_withheld_reason
    assert (narcotics.current, narcotics.comparison, narcotics.absolute_change) == (9, 3, 6)
    battery = next(t for t in result.types if t.primary_type == "BATTERY")
    assert battery.comparison >= type_min and battery.percent_change is not None
    # no percentage anywhere without its counts
    for t in result.types:
        if t.percent_change is not None:
            assert t.comparison >= type_min


def test_net_contribution_is_signed_and_flagged_and_gross_share_is_separate(root: Path) -> None:
    counts, window = _ytd(root)
    result = decompose(counts, window)  # type: ignore[arg-type]
    assert result.net_contribution_status == "interpretation_limited"
    contributions = [t.net_contribution for t in result.types if t.net_contribution is not None]
    assert any(abs(c) > 1 for c in contributions)  # signed shares can exceed 100%
    assert sum(t.gross_movement_share or 0 for t in result.types) == pytest.approx(1, abs=1e-3)
    assert "not a contribution to the net change" in result.gross_movement_note


def test_enforcement_generated_types_are_flagged(root: Path) -> None:
    counts, window = _ytd(root)
    result = decompose(counts, window)  # type: ignore[arg-type]
    flags = {t.primary_type: t.enforcement_generated for t in result.types}
    assert flags["NARCOTICS"] is True and flags["BATTERY"] is False


# -- composition -----------------------------------------------------------------------


def test_partition_reconciles_and_overlays_are_not_additive(root: Path) -> None:
    counts = load_daily_counts(root, "ward20")
    result = composition(counts, date(2026, 2, 14))
    assert result.last_complete_year == 2025  # 2026 is partial: never a composition year
    for year in result.years:
        assert year.partition_reconciles
        assert sum(s.count for s in year.partition) == year.total
        assert all(s.denominator == year.total for s in [*year.partition, *year.overlays])
    assert all(not d.additive for d in result.overlay_definitions)


def test_overlays_can_overlap(tmp_path: Path) -> None:
    built = write_root(
        tmp_path / "r",
        [row("n1", "2025-01-02", "NARCOTICS", fbi_code="18"), row("z", "2025-12-31", "THEFT")],
    )
    build_crime_gold(built, CONFIG_DIR)
    year = composition(load_daily_counts(built, "ward20"), date(2025, 12, 31)).years[0]
    shares = {s.key: s.count for s in year.overlays}
    # The one NARCOTICS report is in two overlays at once.
    assert shares["narcotics"] == 1 and shares["enforcement_generated"] == 1
    assert sum(shares.values()) > year.total - 1  # overlays do not sum to the total


def test_selected_fbi_violent_membership_follows_the_source_code(tmp_path: Path) -> None:
    built = write_root(
        tmp_path / "r",
        [
            row("a", "2025-01-01", "HOMICIDE", fbi_code="01A"),
            row("b", "2025-01-01", "CRIMINAL SEXUAL ASSAULT", fbi_code="02"),
            row("c", "2025-01-01", "ROBBERY", fbi_code="03"),
            row("d", "2025-01-01", "ASSAULT", fbi_code="04A"),
            row("e", "2025-01-01", "BATTERY", fbi_code="04B"),
            row("x1", "2025-01-01", "HOMICIDE", fbi_code="01B"),
            row("x2", "2025-01-01", "ASSAULT", fbi_code="08A"),
            row("x3", "2025-01-01", "BATTERY", fbi_code="08B"),
            row("z", "2025-12-31", "THEFT"),
        ],
    )
    build_crime_gold(built, CONFIG_DIR)
    year = composition(load_daily_counts(built, "ward20"), date(2025, 12, 31)).years[0]
    violent = next(s for s in year.overlays if s.key == "selected_fbi_violent")
    assert violent.count == 5 and violent.denominator == 9
    definition = next(o for o in load_overlays() if o.key == "selected_fbi_violent")
    assert definition.label == "Selected FBI/NIBRS violent-offense classes"
    assert definition.fbi_codes == {"01A", "02", "03", "04A", "04B"}
    assert not ({"01B", "08A", "08B"} & definition.fbi_codes)


def test_sensitive_classes_are_never_broken_out_of_the_overlay(root: Path) -> None:
    response = build_change(root, CONFIG_DIR, "ward20", 2026, WINDOW_YTD)
    assert response.composition is not None
    for year in response.composition.years:
        for share in year.overlays:
            assert set(share.model_dump()) == {"key", "label", "count", "share", "denominator"}
    dumped = str(response.model_dump())
    for forbidden in ("0485", "0487", "0495", "0496", "0497", "0498", "iucr"):
        assert forbidden not in dumped


# -- history ---------------------------------------------------------------------------


def test_monthly_series_flags_the_partial_month_and_trailing_sums_twelve(root: Path) -> None:
    counts = load_daily_counts(root, "woodlawn").query("primary_type == 'THEFT'")
    window = resolve_window(WINDOW_YTD, 2026, date(2026, 2, 14), load_coverage(root))
    result = history(counts, load_coverage(root), window)
    last = result.monthly[-1]
    assert (last.year, last.month, last.complete) == (2026, 2, False)
    first_trailing = result.trailing_12_months[0]
    assert (first_trailing.year, first_trailing.month) == (2023, 12)
    # One THEFT a month from the monthly fixture (plus the Feb 2026 extras, which are partial).
    assert {p.total for p in result.trailing_12_months} == {12}
    assert [a.year for a in result.annual if a.complete] == [2023, 2024, 2025]
    same = result.same_span[0]
    assert same.lookback_years == 5 and [v.year for v in same.values] == [2023, 2024, 2025]


# -- trend -----------------------------------------------------------------------------


def test_kendall_increasing_decreasing_flat_and_too_short() -> None:
    years = list(range(2016, 2024))
    rising = kendall_trend(list(zip(years, range(10, 18), strict=True)), "x")
    assert rising.direction == "rising" and rising.tau == 1.0 and rising.p_value < 0.05
    falling = kendall_trend(list(zip(years, range(18, 10, -1), strict=True)), "x")
    assert falling.direction == "falling" and falling.tau == -1.0
    flat = kendall_trend([(y, 7) for y in years], "x")
    assert flat.direction == "no_variation" and flat.tau is None
    short = kendall_trend([(2020, 1), (2021, 2), (2022, 3)], "x")
    assert short.direction == "unavailable" and short.n == 3


def test_kendall_tau_b_with_ties_matches_the_hand_value() -> None:
    # y = 1,2,2,3,4: 9 concordant pairs, 0 discordant, one tie in y.
    # tau-b = 9 / sqrt(10 * 9) = 0.9487
    result = kendall_trend([(2020, 1), (2021, 2), (2022, 2), (2023, 3), (2024, 4)], "x")
    assert result.tau == pytest.approx(0.9487, abs=1e-4)


def test_kendall_without_a_direction_says_so() -> None:
    result = kendall_trend([(2018, 5), (2019, 1), (2020, 4), (2021, 2), (2022, 3)], "x")
    assert result.direction == "no_consistent_direction"


# -- revisions -------------------------------------------------------------------------


def test_revision_summary_reproduces_the_prior_release_totals(tmp_path: Path) -> None:
    base = [row(f"t{i}", "2025-01-10", "THEFT") for i in range(5)]
    prior = write_root(
        tmp_path / "p", [*base, row("z", "2026-02-14", "THEFT")], release_id="dev-prior"
    )
    current = write_root(
        tmp_path / "c",
        [
            *base[:4],
            row("t4", "2025-01-10", "THEFT", source_status="source_removed"),
            row("new", "2025-01-11", "THEFT"),
            row("moved", "2026-01-05", "ROBBERY", fbi_code="03"),
            row("z", "2026-02-14", "THEFT"),
        ],
        release_id="dev-current",
    )
    build_crime_gold(prior, CONFIG_DIR)
    build_crime_gold(current, CONFIG_DIR)
    build_revision_events(prior, current)
    response = build_change(current, CONFIG_DIR, "ward20", 2026, WINDOW_YTD)
    summary = response.revisions
    assert summary is not None
    assert (summary.prior_release_id, summary.current_release_id) == ("dev-prior", "dev-current")
    prior_counts = load_daily_counts(prior, "ward20")
    for side in (summary.current_period, summary.comparison_period):
        start, end = date.fromisoformat(side.period.start), date.fromisoformat(side.period.end)
        expected = int(
            prior_counts[(prior_counts["date"] >= start) & (prior_counts["date"] <= end)][
                "count"
            ].sum()
        )
        assert side.prior_release_total == expected
    assert summary.reasons["added"] >= 1 and summary.reasons["removed"] == 1


# -- assembly + API --------------------------------------------------------------------


def test_every_response_carries_its_identity(root: Path) -> None:
    response = build_change(root, CONFIG_DIR, "woodlawn", 2026, WINDOW_YTD)
    assert response.analysis_status == "ok"
    identity = response.identity
    assert identity is not None
    assert identity.geography_id == "woodlawn" and identity.release_id == "dev-test"
    assert "only the part of the Woodlawn community area" in identity.geography_frame
    assert identity.data_through == "2026-02-14" and identity.provisional
    assert response.window is not None and response.window.current.start == "2026-01-01"
    assert response.anchors["decomposition"] == "drivers"
    assert response.anchors["composition"] == "composition"


_CAUSAL = re.compile(
    r"\b(because|caused|causes|due to|led to|leads to|result(?:ed)? (?:of|from|in)|"
    r"driven by|attributable|thanks to|safer|more dangerous)\b",
    re.IGNORECASE,
)


def test_no_generated_text_makes_a_causal_claim(root: Path) -> None:
    for kind in (WINDOW_YTD, WINDOW_TRAILING, WINDOW_FULL_YEAR):
        response = build_change(root, CONFIG_DIR, "ward20", 2026, kind)
        offending = [s for s in response_strings(response) if _CAUSAL.search(s)]
        assert offending == [], offending


def test_window_sensitivity_reports_each_window(root: Path) -> None:
    response = build_change(root, CONFIG_DIR, "ward20", 2026, WINDOW_YTD)
    assert response.sensitivity is not None
    kinds = [w.kind for w in response.sensitivity.windows]
    assert kinds == [WINDOW_YTD, WINDOW_TRAILING, WINDOW_FULL_YEAR]
    for w in response.sensitivity.windows:
        if w.direction != "unavailable":
            assert w.current and w.comparison and w.current_total is not None
