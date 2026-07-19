"""Neighborhood Pulse: what changed, where, who is responsible, and what residents can do.

Read-only over Silver (spatial assignment) joined to Bronze (incident attributes) on `id`.
Every number is computed from the live data; every sentence returned to the reader is
composed only from those numbers. No cause is inferred, and no prior value is imputed.

The governing rule is the *same-period* comparison: a partial year is compared with January 1
through the same month and day of the previous year, never with a completed year.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from bw_observatory.geography.normalize import load_neighborhood_config
from bw_observatory.presentation.models import (
    ArrestSummary,
    BeatConcentration,
    BroadCategoryChange,
    ChangeMetric,
    DataQuality,
    IssueCard,
    MonthlyCategoryPoint,
    MonthlyComparisonPoint,
    PeriodBounds,
    PrimaryTypeChange,
    Provenance,
    PulseResponse,
)
from bw_observatory.presentation.overview import (
    CRIME_DATASET_ID,
    CRIME_DATASET_NAME,
    MONTH_LABELS,
    OverviewDataUnavailable,
    boundary_vintage,
    broad_category_of,
    bronze_path,
    data_through,
    is_year_to_date,
    last_refresh,
    load_broad_categories,
    neighborhood_availability,
    quality_counts,
    silver_path,
    verify_bronze_integrity,
    year_is_enriched,
)

# Columns the Pulse needs from Bronze. Kept narrow so a large year is not fully materialized.
_BRONZE_FIELDS = ["id", "date", "primary_type", "arrest", "beat", "block"]

# Only a beat with at least this many current-period incidents is eligible to be called out
# as a concentration or an "issue". Below it, one or two reports are noise, not a pattern.
_MIN_BEAT_FOR_CALLOUT = 15

# A masked block is only surfaced as a repeat-location issue at or above this many reports.
_MIN_REPEAT_BLOCK = 6


# -- record loading --------------------------------------------------------------------


def load_records(data_dir: Path, year: int, neighborhood_id: str) -> pd.DataFrame:
    """Dated incident records for one neighborhood/year, with the fields the Pulse needs."""
    silver = silver_path(data_dir, year)
    bronze = bronze_path(data_dir, year)
    if not silver.exists():
        raise OverviewDataUnavailable(
            f"No geography-enriched crime data for {year}. Run "
            f"scripts/enrich_crime_geography.py --year {year}."
        )
    if not bronze.exists():
        raise OverviewDataUnavailable(f"No Bronze crime data for {year}.")

    flag = f"neighborhood_{neighborhood_id}"
    # boundary_vintage feeds provenance; keep the read narrow but tolerate its absence.
    try:
        enriched = pd.read_parquet(silver, columns=["id", flag, "boundary_vintage"])
    except (ValueError, KeyError):
        enriched = pd.read_parquet(silver, columns=["id", flag])
    in_neighborhood = enriched[enriched[flag] == True]  # noqa: E712

    attributes = pd.read_parquet(bronze, columns=_BRONZE_FIELDS)
    joined = in_neighborhood.merge(attributes, on="id", how="left")

    joined["_when"] = pd.to_datetime(joined["date"], errors="coerce")
    joined["_ptype"] = joined["primary_type"].astype("string").str.upper()
    joined["_broad"] = joined["_ptype"].map(broad_category_of)
    joined["_arrest"] = joined["arrest"].astype("string").str.lower().isin(["true", "1"])
    joined["_beat"] = joined["beat"].astype("string").str.strip()
    joined["_block"] = joined["block"].astype("string").str.strip()
    # Records with no usable date cannot be placed in a comparison period.
    return joined[joined["_when"].notna()].reset_index(drop=True)


# -- period arithmetic -----------------------------------------------------------------


def same_period_cutoff(through: date, prior_year: int) -> date:
    """The same month/day as `through`, in `prior_year`. 29 Feb clamps to 28 Feb."""
    try:
        return date(prior_year, through.month, through.day)
    except ValueError:  # 29 Feb in a non-leap prior year
        return date(prior_year, through.month, 28)


def _within(records: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    when = records["_when"]
    return records[(when >= pd.Timestamp(start)) & (when <= pd.Timestamp(end))]


def _pct_change(current: int, prior: int | None) -> float | None:
    """Percentage change, rounded to one decimal. None when there is no non-zero base."""
    if prior is None or prior == 0:
        return None
    return round((current - prior) / prior * 100, 1)


def _change_metric(current: int, prior: int | None) -> ChangeMetric:
    return ChangeMetric(
        current=current,
        prior=prior,
        absolute_change=None if prior is None else current - prior,
        percent_change=_pct_change(current, prior),
    )


# -- breakdowns ------------------------------------------------------------------------


def _broad_counts(records: pd.DataFrame) -> dict[str, int]:
    broad, _ = load_broad_categories()
    counts = records["_broad"].value_counts()
    return {category.key: int(counts.get(category.key, 0)) for category in broad}


def broad_category_changes(
    current: pd.DataFrame, prior: pd.DataFrame | None
) -> list[BroadCategoryChange]:
    broad, _ = load_broad_categories()
    cur = _broad_counts(current)
    pri = _broad_counts(prior) if prior is not None else None
    changes = []
    for category in broad:
        c = cur[category.key]
        p = pri[category.key] if pri is not None else None
        changes.append(
            BroadCategoryChange(
                key=category.key,
                label=category.label,
                current=c,
                prior=p,
                absolute_change=None if p is None else c - p,
                percent_change=_pct_change(c, p),
            )
        )
    return changes


def category_drivers(current: pd.DataFrame, prior: pd.DataFrame | None) -> list[PrimaryTypeChange]:
    """Detailed CPD primary types, current vs prior, sorted by largest absolute increase."""
    cur = current["_ptype"].value_counts()
    pri = prior["_ptype"].value_counts() if prior is not None else pd.Series(dtype="int64")
    types = sorted(set(cur.index) | set(pri.index))

    rows = []
    for ptype in types:
        if not isinstance(ptype, str) or not ptype:
            continue
        c = int(cur.get(ptype, 0))
        p = int(pri.get(ptype, 0)) if prior is not None else None
        broad_key = broad_category_of(ptype)
        broad, _ = load_broad_categories()
        label = next((b.label for b in broad if b.key == broad_key), broad_key)
        rows.append(
            PrimaryTypeChange(
                primary_type=ptype,
                broad_category=broad_key,
                broad_label=label,
                current=c,
                prior=p,
                absolute_change=None if p is None else c - p,
                percent_change=_pct_change(c, p),
            )
        )
    rows.sort(
        key=lambda r: (r.absolute_change if r.absolute_change is not None else 0, r.current),
        reverse=True,
    )
    return rows


def _beat_display(beat: str) -> str:
    """Resident-facing beat: strip a single set of leading zeros but keep the raw for the API."""
    stripped = beat.lstrip("0")
    return stripped or beat


def beat_concentration(
    current: pd.DataFrame, prior: pd.DataFrame | None
) -> list[BeatConcentration]:
    total_current = len(current)
    cur = current[current["_beat"].notna() & (current["_beat"] != "")]["_beat"].value_counts()
    pri = (
        prior[prior["_beat"].notna() & (prior["_beat"] != "")]["_beat"].value_counts()
        if prior is not None
        else pd.Series(dtype="int64")
    )
    beats = sorted(set(cur.index) | set(pri.index))

    rows = []
    for beat in beats:
        if not isinstance(beat, str) or not beat:
            continue
        c = int(cur.get(beat, 0))
        p = int(pri.get(beat, 0)) if prior is not None else None
        rows.append(
            BeatConcentration(
                beat=beat,
                beat_display=_beat_display(beat),
                current=c,
                prior=p,
                share=round(c / total_current, 4) if total_current else 0.0,
                absolute_change=None if p is None else c - p,
                percent_change=_pct_change(c, p),
            )
        )
    rows.sort(key=lambda r: r.current, reverse=True)
    return rows


# -- charts ----------------------------------------------------------------------------


def monthly_comparison(
    current: pd.DataFrame,
    prior: pd.DataFrame | None,
    through: date,
    partial: bool,
) -> list[MonthlyComparisonPoint]:
    cur_by_month = current["_when"].dt.month.value_counts()
    pri_by_month = (
        prior["_when"].dt.month.value_counts() if prior is not None else pd.Series(dtype="int64")
    )
    last_month = through.month
    points = []
    for month in range(1, 13):
        in_window = month <= last_month
        points.append(
            MonthlyComparisonPoint(
                month=month,
                month_label=MONTH_LABELS[month - 1],
                current=int(cur_by_month.get(month, 0)) if in_window else None,
                prior=(
                    int(pri_by_month.get(month, 0)) if (prior is not None and in_window) else None
                ),
                is_partial_month=partial and month == last_month,
                in_comparison_window=in_window,
            )
        )
    return points


def monthly_categories(
    current: pd.DataFrame, through: date, partial: bool
) -> list[MonthlyCategoryPoint]:
    broad, _ = load_broad_categories()
    keys = [c.key for c in broad]
    last_month = through.month
    points = []
    for month in range(1, last_month + 1):
        subset = current[current["_when"].dt.month == month]
        counts = subset["_broad"].value_counts()
        by_key = {key: int(counts.get(key, 0)) for key in keys}
        points.append(
            MonthlyCategoryPoint(
                month=month,
                month_label=MONTH_LABELS[month - 1],
                counts=by_key,
                total=int(sum(by_key.values())),
                is_partial_month=partial and month == last_month,
            )
        )
    return points


# -- prose (composed only from the numbers above) --------------------------------------


def resident_date(iso: str) -> str:
    """'2026-07-09' -> 'July 9, 2026'. Never shows an ISO date in narrative text."""
    parsed = date.fromisoformat(iso[:10])
    return f"{calendar.month_name[parsed.month]} {parsed.day}, {parsed.year}"


@dataclass(frozen=True)
class _Comparison:
    available: bool
    current: int
    prior: int | None
    abs_change: int | None
    pct_change: float | None
    period_label: str  # resident-facing, e.g. "the same period in 2025"


def _direction(abs_change: int) -> tuple[str, str, str]:
    """(verb, comparative, article) for a change: up/more/an increase, etc."""
    if abs_change > 0:
        return "up", "more", "an increase"
    if abs_change < 0:
        return "down", "fewer", "a decrease"
    return "unchanged", "the same as", "no change"


def build_headline(
    name: str,
    comparison: _Comparison,
    largest_increase: BroadCategoryChange | None,
    top_beat: BeatConcentration | None,
    partial: bool,
) -> str:
    ytd = " year-to-date" if partial else ""
    if not comparison.available or comparison.abs_change is None:
        return (
            f"A same-period comparison isn't available yet, so no trend is shown. "
            f"{name} recorded {comparison.current:,} reported incidents{ytd}."
        )

    verb, _, _ = _direction(comparison.abs_change)
    pct = comparison.pct_change
    magnitude = f" {abs(pct)}%" if pct is not None else ""
    if comparison.abs_change == 0:
        lead = f"Reported incidents in {name} are unchanged{ytd} from {comparison.period_label}"
    else:
        lead = f"Reported incidents in {name} are {verb}{magnitude}{ytd}"

    if (
        largest_increase
        and largest_increase.absolute_change
        and largest_increase.absolute_change > 0
    ):
        conj = "and" if comparison.abs_change > 0 else "but"
        where = f" in Beat {top_beat.beat_display}" if top_beat else ""
        return f"{lead}, {conj} {largest_increase.label} rose most{where}."
    return f"{lead}."


def build_narrative(
    name: str,
    year: int,
    through_iso: str,
    partial: bool,
    comparison: _Comparison,
    largest_increase: BroadCategoryChange | None,
    largest_decline: BroadCategoryChange | None,
    top_beat: BeatConcentration | None,
    arrests: ArrestSummary,
) -> str:
    through_words = resident_date(through_iso)
    sentences: list[str] = []

    if comparison.available and comparison.abs_change is not None:
        _, comparative, article = _direction(comparison.abs_change)
        lead_period = f"Through {through_words}, " if partial else ""
        subject = f"{name} recorded {comparison.current:,} reported incidents in {year}"
        if comparison.abs_change == 0:
            sentences.append(
                f"{lead_period}{subject} — the same number as during {comparison.period_label}."
            )
        else:
            pct = comparison.pct_change
            magnitude = f", {article} of {abs(pct)}%" if pct is not None else ""
            sentences.append(
                f"{lead_period}{subject} — {abs(comparison.abs_change):,} {comparative} "
                f"than during {comparison.period_label}{magnitude}."
            )
    else:
        lead_period = f"Through {through_words}, " if partial else ""
        sentences.append(
            f"{lead_period}{name} recorded {comparison.current:,} reported incidents in {year}. "
            f"A same-period comparison with the previous year isn't available yet, so no "
            f"change is shown."
        )

    if (
        largest_increase
        and largest_increase.absolute_change
        and largest_increase.absolute_change > 0
    ):
        sentences.append(
            f"{largest_increase.label} rose the most, up {largest_increase.absolute_change:,} "
            f"to {largest_increase.current:,} reports."
        )
    if largest_decline and largest_decline.absolute_change and largest_decline.absolute_change < 0:
        sentences.append(
            f"{largest_decline.label} fell the most, down {abs(largest_decline.absolute_change):,} "
            f"to {largest_decline.current:,} reports."
        )
    if top_beat and top_beat.absolute_change and top_beat.absolute_change > 0:
        sentences.append(
            f"The largest local increase was in Beat {top_beat.beat_display}, up "
            f"{top_beat.absolute_change:,} to {top_beat.current:,} reports."
        )

    if arrests.total:
        sentences.append(
            f"An arrest was recorded on {arrests.percent * 100:.0f}% of these reports "
            f"({arrests.count:,} of {arrests.total:,}). An arrest is a fact recorded on a "
            f"report — it is not a clearance rate and does not establish prosecution or guilt."
        )

    if partial:
        sentences.append(
            f"{year} is a partial year: these figures cover January 1 through {through_words} "
            f"and will keep rising as the year continues. The most recent weeks are usually "
            f"incomplete because the city publishes reports with a lag."
        )

    sentences.append(
        "Every sentence above is composed from the counts and comparisons on this page. "
        "No cause is inferred from correlation."
    )
    return " ".join(sentences)


# -- issues residents should watch -----------------------------------------------------

_CPD_ALDER_CAN = (
    "Convene residents, raise the pattern with district leadership, request an explanation, "
    "advocate for resources, and escalate related lighting, vacancy, or public-space issues."
)
_CPD_ALDER_CANNOT = (
    "Direct individual investigations, order arrests, prosecute cases, determine guilt, or "
    "command day-to-day CPD deployment."
)


def _district_of(beat: str | None) -> str | None:
    if not beat:
        return None
    stripped = beat.lstrip("0") or beat
    # A CPD beat's leading digits are its district (e.g. 0321 -> district 3).
    return (beat[:2].lstrip("0") or beat[:2]) if len(beat) >= 3 else stripped


def _crime_authority(beat: str | None) -> str:
    district = _district_of(beat)
    if beat and district:
        return f"Chicago Police Department — {district} District, Beat {_beat_display(beat)}"
    return "Chicago Police Department — police district and beat"


def build_issues(
    name: str,
    comparison: _Comparison,
    period_label: str,
    largest_increase: BroadCategoryChange | None,
    top_beat: BeatConcentration | None,
    repeat_block: tuple[str, int] | None,
    arrests: ArrestSummary,
    partial: bool,
    through_iso: str,
) -> list[IssueCard]:
    issues: list[IssueCard] = []

    if (
        largest_increase
        and largest_increase.absolute_change
        and largest_increase.absolute_change > 0
    ):
        issues.append(
            IssueCard(
                id="category-largest-increase",
                kind="category_increase",
                title=f"{largest_increase.label} is rising",
                finding=(
                    f"{largest_increase.label} reports rose the most of any broad category "
                    f"in {name}, up {largest_increase.absolute_change:,} to "
                    f"{largest_increase.current:,}."
                ),
                supporting_stat=(
                    f"{largest_increase.current:,} vs {largest_increase.prior:,} "
                    f"({'+' if largest_increase.absolute_change >= 0 else ''}"
                    f"{largest_increase.absolute_change:,})"
                    if largest_increase.prior is not None
                    else f"{largest_increase.current:,} reports"
                ),
                comparison_period=period_label,
                beat=None,
                primary_authority=_crime_authority(None),
                supporting_authority=(
                    "Relevant city departments where an environmental condition is involved."
                ),
                alderperson_role=f"Can: {_CPD_ALDER_CAN} Cannot: {_CPD_ALDER_CANNOT}",
                resident_action=(
                    "Raise this category at your beat meeting and ask what is driving it."
                ),
                suggested_question=(
                    f"What does the district attribute the rise in "
                    f"{largest_increase.label.lower()} to, and what response is planned?"
                ),
                evidence="Broad-category comparison on this page (same period, prior year).",
            )
        )

    if (
        top_beat
        and top_beat.absolute_change
        and top_beat.absolute_change > 0
        and top_beat.current >= _MIN_BEAT_FOR_CALLOUT
    ):
        issues.append(
            IssueCard(
                id="beat-largest-increase",
                kind="beat_increase",
                title=f"Beat {top_beat.beat_display} saw the largest increase",
                finding=(
                    f"Reported incidents in Beat {top_beat.beat_display} rose more than in any "
                    f"other {name} beat, up {top_beat.absolute_change:,} to {top_beat.current:,}."
                ),
                supporting_stat=(
                    f"{top_beat.current:,} vs {top_beat.prior:,} (+{top_beat.absolute_change:,}), "
                    f"{top_beat.share * 100:.0f}% of the neighborhood total"
                    if top_beat.prior is not None
                    else f"{top_beat.current:,} reports ({top_beat.share * 100:.0f}% of the total)"
                ),
                comparison_period=period_label,
                beat=top_beat.beat,
                primary_authority=_crime_authority(top_beat.beat),
                supporting_authority=None,
                alderperson_role=f"Can: {_CPD_ALDER_CAN} Cannot: {_CPD_ALDER_CANNOT}",
                resident_action=(
                    f"Attend the Beat {top_beat.beat_display} CAPS meeting and ask about it."
                ),
                suggested_question=(
                    f"What is the district's plan for the increase concentrated in Beat "
                    f"{top_beat.beat_display}? Incident counts alone do not measure "
                    f"police performance."
                ),
                evidence="Per-beat concentration on this page (same period, prior year).",
            )
        )

    if repeat_block and repeat_block[1] >= _MIN_REPEAT_BLOCK:
        block, count = repeat_block
        issues.append(
            IssueCard(
                id="repeat-block",
                kind="repeat_block",
                title="Repeated reports on one masked block",
                finding=(
                    f"The crime dataset shows {count:,} reports on {block} this period. It "
                    f"does not establish whether they involve one property, several "
                    f"properties, transit or public space, or a shared underlying condition."
                ),
                supporting_stat=f"{count:,} reports on {block}",
                comparison_period=period_label,
                beat=None,
                primary_authority=_crime_authority(None),
                supporting_authority=(
                    "City departments responsible for any related property, lighting, or "
                    "public-space condition."
                ),
                alderperson_role=f"Can: {_CPD_ALDER_CAN} Cannot: {_CPD_ALDER_CANNOT}",
                resident_action="Ask that this block be reviewed, without assuming a single cause.",
                suggested_question=(
                    "Can CPD and the relevant city departments explain whether these "
                    "reports are concentrated at one location and whether any environmental "
                    "or property condition requires action?"
                ),
                evidence="Masked block-level counts in the incident table on this page.",
            )
        )

    if partial:
        issues.append(
            IssueCard(
                id="partial-month",
                kind="partial_month",
                title="The most recent weeks are incomplete",
                finding=(
                    f"Data runs through {resident_date(through_iso)}. The latest weeks "
                    f"usually undercount because the city publishes reports on a lag, so a "
                    f"late dip may not be real."
                ),
                supporting_stat=f"Data through {resident_date(through_iso)}",
                comparison_period=period_label,
                beat=None,
                primary_authority="City of Chicago — data publication (Socrata / CPD).",
                supporting_authority=None,
                alderperson_role="Informational — no action implied.",
                resident_action="Treat the most recent weeks as provisional.",
                suggested_question="",
                evidence="Data-through date from the ingestion manifest.",
            )
        )

    return issues[:5]


# -- top-level builder -----------------------------------------------------------------


def build_pulse(data_dir: Path, year: int, neighborhood_id: str = "woodlawn") -> PulseResponse:
    availability = {n.neighborhood_id: n for n in neighborhood_availability()}
    requested = availability.get(neighborhood_id)
    if requested is None:
        raise OverviewDataUnavailable(f"Unknown neighborhood: {neighborhood_id}")
    if not requested.available:
        raise OverviewDataUnavailable(
            f"{requested.display_name} is not available: {requested.reason}"
        )

    current = load_records(data_dir, year, neighborhood_id)
    if current.empty:
        raise OverviewDataUnavailable(f"No {requested.display_name} records found for {year}.")

    through_iso = data_through(current)
    through = date.fromisoformat(through_iso[:10])
    partial = is_year_to_date(year, through_iso)

    prior_year = year - 1
    comparison_available = year_is_enriched(data_dir, prior_year)
    prior: pd.DataFrame | None = None
    prior_bounds = None
    prior_cutoff = None
    if comparison_available:
        prior_all = load_records(data_dir, prior_year, neighborhood_id)
        prior_cutoff = same_period_cutoff(through, prior_year)
        prior = _within(prior_all, date(prior_year, 1, 1), prior_cutoff)
        prior_bounds = PeriodBounds(
            start=f"{prior_year}-01-01",
            end=prior_cutoff.isoformat(),
            incidents=len(prior),
        )

    current_bounds = PeriodBounds(
        start=f"{year}-01-01", end=through_iso[:10], incidents=len(current)
    )
    period_label = f"the same period in {prior_year}" if partial else str(prior_year)

    # Metric cards.
    incidents_metric = _change_metric(len(current), len(prior) if prior is not None else None)
    broad_changes = broad_category_changes(current, prior)

    increases = [
        c for c in broad_changes if c.absolute_change is not None and c.absolute_change > 0
    ]
    declines = [c for c in broad_changes if c.absolute_change is not None and c.absolute_change < 0]
    largest_increase = max(increases, key=lambda c: c.absolute_change or 0) if increases else None
    largest_decline = min(declines, key=lambda c: c.absolute_change or 0) if declines else None

    beats = beat_concentration(current, prior)
    beat_increases = [
        b
        for b in beats
        if b.absolute_change is not None
        and b.absolute_change > 0
        and b.current >= _MIN_BEAT_FOR_CALLOUT
    ]
    beat_largest_increase = (
        max(beat_increases, key=lambda b: b.absolute_change or 0) if beat_increases else None
    )

    arrest_count = int(current["_arrest"].sum())
    prior_arrest_count = int(prior["_arrest"].sum()) if prior is not None else None
    prior_percent: float | None = None
    if prior is not None and prior_arrest_count is not None and len(prior):
        prior_percent = round(prior_arrest_count / len(prior), 4)
    arrests = ArrestSummary(
        count=arrest_count,
        total=len(current),
        percent=round(arrest_count / len(current), 4) if len(current) else 0.0,
        prior_count=prior_arrest_count,
        prior_percent=prior_percent,
    )

    comparison = _Comparison(
        available=comparison_available,
        current=len(current),
        prior=len(prior) if prior is not None else None,
        abs_change=incidents_metric.absolute_change,
        pct_change=incidents_metric.percent_change,
        period_label=period_label,
    )

    # Repeat masked block (current period only).
    block_counts = current[current["_block"].notna() & (current["_block"] != "")][
        "_block"
    ].value_counts()
    repeat_block = (
        (str(block_counts.index[0]), int(block_counts.iloc[0])) if len(block_counts) else None
    )

    headline = build_headline(
        requested.display_name, comparison, largest_increase, beat_largest_increase, partial
    )
    narrative = build_narrative(
        requested.display_name,
        year,
        through_iso,
        partial,
        comparison,
        largest_increase,
        largest_decline,
        beat_largest_increase,
        arrests,
    )
    issues = build_issues(
        requested.display_name,
        comparison,
        period_label,
        largest_increase,
        beat_largest_increase,
        repeat_block,
        arrests,
        partial,
        through_iso,
    )

    quality = quality_counts(data_dir, year)
    neighborhood_config = next(
        c for c in load_neighborhood_config() if c.neighborhood_id == neighborhood_id
    )
    comparison_note = (
        ""
        if comparison_available
        else f"A same-period comparison will appear once {prior_year} is enriched."
    )

    return PulseResponse(
        neighborhood_id=neighborhood_id,
        neighborhood_name=requested.display_name,
        year=year,
        is_year_to_date=partial,
        data_through=through_iso[:10],
        current_period=current_bounds,
        prior_period=prior_bounds,
        comparison_available=comparison_available,
        comparison_note=comparison_note,
        headline=headline,
        narrative=narrative,
        incidents=incidents_metric,
        largest_increase=largest_increase,
        largest_decline=largest_decline,
        beat_largest_increase=beat_largest_increase,
        arrests=arrests,
        monthly_comparison=monthly_comparison(current, prior, through, partial),
        monthly_categories=monthly_categories(current, through, partial),
        broad_categories=broad_changes,
        category_drivers=category_drivers(current, prior),
        beats=beats,
        issues=issues,
        provenance=Provenance(
            source_dataset_id=CRIME_DATASET_ID,
            source_dataset_name=CRIME_DATASET_NAME,
            boundary_type=neighborhood_config.boundary_type,
            boundary_source=neighborhood_config.source,
            boundary_vintage=boundary_vintage(current),
            last_refresh=last_refresh(data_dir, year),
            data_through=through_iso,
        ),
        data_quality=DataQuality(
            total_bronze_records_year=quality["total"],
            records_without_coordinates=quality["no_coords"],
            records_outside_boundaries=quality["outside"],
            records_invalid_coordinates=quality["invalid"],
            community_area_mismatches=quality["ca_mismatch"],
            bronze_integrity_verified=verify_bronze_integrity(data_dir, year),
        ),
        neighborhoods=list(availability.values()),
    )
