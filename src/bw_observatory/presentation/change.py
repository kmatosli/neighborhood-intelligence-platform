"""Crime Trends — Change: what moved, which types account for it, and in what context.

Crime Analytics Sprint 1. Every figure is computed from the release's Gold daily counts
(`gold.crime_aggregates`), which are proved equal to Silver when they are built; nothing here
reads Bronze or Silver at request time, and nothing is served if Gold no longer describes the
release beside it (`aggregates_stale`).

Rules this module enforces, each with a test:

* **Like for like.** Every comparison names both periods with inclusive start and end dates,
  both periods have the same calendar span, and both lie wholly inside the release's
  coverage. A partial year is never compared with a full one; an uncovered day is never a
  zero.
* **Every type, reconciled.** The decomposition lists every primary type present in either
  period — no top-N — and Σ type change equals the overall change exactly.
* **Counts first.** A percentage is withheld (null, with the reason) below the published
  `min_prior` rule of the findings config; the counts are always present.
* **Overlays are not a partition.** The broad categories sum to the total; overlays
  (enforcement-generated, narcotics, motor-vehicle theft, the selected FBI/NIBRS violent
  classes) are published with their own denominator and are never additive.
* **Descriptive, not causal.** Trend direction is Kendall's tau-b on complete annual totals,
  reported with tau, p and n. Statistical significance is not practical importance and says
  nothing about causes; no sentence here attributes a change to anything.

Deferred (CA-12, separate methodological review): SPC control limits and change-point
detection.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from statistics import median
from typing import Any

import pandas as pd
import yaml
from scipy.stats import kendalltau

from bw_observatory.config import Settings
from bw_observatory.gold.crime_aggregates import (
    GoldUnavailable,
    check_gold,
    covered,
    load_coverage,
    load_daily_counts,
)
from bw_observatory.gold.revisions import in_window, latest_revision
from bw_observatory.ingest.freshness import crime_freshness
from bw_observatory.presentation.findings import load_finding_specs
from bw_observatory.presentation.geography import ProductGeography, geography_scope_note
from bw_observatory.presentation.measurement import PROVISIONAL_WINDOW_DAYS
from bw_observatory.presentation.models import (
    AnnualPoint,
    ChangeComposition,
    ChangeDecomposition,
    ChangeHistory,
    ChangeIdentity,
    ChangePeriod,
    ChangeResponse,
    ChangeTotal,
    ChangeWindow,
    ComparisonSensitivity,
    CompositionShare,
    CompositionYear,
    MonthPoint,
    OverlayDefinition,
    RevisionSide,
    RevisionSummary,
    SameSpanHistory,
    SpanContext,
    TrailingPoint,
    TrendResult,
    TypeChange,
    WindowSensitivity,
)
from bw_observatory.presentation.overview import (
    CRIME_DATASET_NAME,
    is_enforcement_generated,
    load_broad_categories,
    load_enforcement_generated_types,
    resolve_geography,
)
from bw_observatory.release import read_release_manifest

WINDOW_YTD = "ytd"
WINDOW_TRAILING = "t12m"
WINDOW_FULL_YEAR = "full_year"
WINDOWS = (WINDOW_YTD, WINDOW_TRAILING, WINDOW_FULL_YEAR)

TREND_ALPHA = 0.05
TREND_MIN_YEARS = 5
SPANS = ((3, "3 years"), (5, "5 years"), (10, "10 years"))
SAME_SPAN_LOOKBACKS = (5, 10)

# Anchors on the Trends page. `composition`, `drivers` and `geography` are the targets the
# Overview's findings already deep-link to (config/findings.yml `destination.anchor`).
ANCHORS = {
    "section": "change",
    "decomposition": "drivers",
    "composition": "composition",
    "history": "history",
    "trend": "trend",
    "sensitivity": "windows",
    "revisions": "revisions",
    "methods": "methods",
    "geography": "geography",
}

LIMITATIONS = [
    "These are incidents reported to the Chicago Police Department, not convictions, and not "
    "every crime is reported.",
    "Every year is placed with the current (2023) Ward 20 map, so a change over time is not a "
    "change of boundary.",
    "Enforcement-generated offences are recorded mostly when police act; their counts can move "
    "with enforcement activity rather than with the behaviour.",
    "Overlay figures overlap each other and the broad categories; they are not parts of a "
    "whole and do not add up to the total.",
    "A percentage is withheld when its comparison count is below the published minimum; the "
    "counts are always shown.",
    "The City revises published records after the fact, and recent periods are provisional. "
    "The source has no separate report-date field: a revision is seen only by comparing "
    "retained releases.",
    "The trend test describes the direction of annual totals. It is not a forecast, and a "
    "statistically detectable direction is not necessarily a large or important one.",
]

METHOD_FLAGS = [
    "source: gold daily counts proved equal to Silver at build",
    "placement: point-in-polygon (spatial_ward_current, spatial_community_area)",
    "view: current source (source_removed records excluded)",
    "trend: scipy.stats.kendalltau (tau-b) on complete annual totals",
    "deferred: SPC control limits and change-point detection (CA-12 review)",
]


# -- dates ----------------------------------------------------------------------------


def shift_years(day: date, years: int) -> date:
    """The same month/day `years` later (negative = earlier). 29 Feb clamps to 28 Feb."""
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)


def _period(start: date, end: date) -> ChangePeriod:
    return ChangePeriod(start=start.isoformat(), end=end.isoformat(), days=(end - start).days + 1)


@dataclass(frozen=True)
class Window:
    kind: str
    label: str
    start: date
    end: date
    comparison_start: date
    comparison_end: date
    note: str | None = None

    def model(self) -> ChangeWindow:
        return ChangeWindow(
            kind=self.kind,
            label=self.label,
            current=_period(self.start, self.end),
            comparison=_period(self.comparison_start, self.comparison_end),
            note=self.note,
        )


class WindowUnavailable(ValueError):
    """The requested comparison cannot be made like for like from this release."""


def resolve_window(kind: str, year: int, through: date, coverage: pd.DataFrame) -> Window:
    """The two periods to compare, or WindowUnavailable — never a partial-vs-full comparison."""
    if kind not in WINDOWS:
        raise WindowUnavailable(f"Unknown comparison window {kind!r}.")
    if year > through.year:
        raise WindowUnavailable(f"The release has no data for {year}; it ends {through}.")

    if kind == WINDOW_YTD:
        end = min(date(year, 12, 31), through)
        start = date(year, 1, 1)
        comparison = (date(year - 1, 1, 1), shift_years(end, -1))
        label = (
            "Year to date against the same span last year"
            if end < date(year, 12, 31)
            else "Full year against the previous full year"
        )
        window = Window(kind, label, start, end, *comparison)
    elif kind == WINDOW_TRAILING:
        end = through if year == through.year else date(year, 12, 31)
        # Equal exposure (owner decision, 2026-10-28): the trailing 365 days against the 365
        # before, adjacent with no gap or overlap. Calendar 12-month periods were rejected as a
        # comparison because one holding 29 Feb has a day more than the other. The API key
        # stays `t12m` for compatibility; the historical series keeps 12 complete months.
        start = end - timedelta(days=364)
        comparison_end = end - timedelta(days=365)
        comparison_start = end - timedelta(days=729)
        window = Window(
            kind,
            "Trailing 365 days vs previous 365 days",
            start,
            end,
            comparison_start,
            comparison_end,
        )
    else:
        latest = year if date(year, 12, 31) <= through else year - 1
        note = None
        if latest != year:
            note = (
                f"{year} is not complete in this release, so the latest complete year "
                f"({latest}) is compared with the year before."
            )
        window = Window(
            kind,
            "Latest complete year against the year before",
            date(latest, 1, 1),
            date(latest, 12, 31),
            date(latest - 1, 1, 1),
            date(latest - 1, 12, 31),
            note,
        )

    if not covered(coverage, window.start, window.end):
        raise WindowUnavailable(
            f"{window.start}–{window.end} is not wholly covered by this release."
        )
    if not covered(coverage, window.comparison_start, window.comparison_end):
        raise WindowUnavailable(
            f"The comparison period {window.comparison_start}–{window.comparison_end} is not "
            "wholly covered by this release."
        )
    return window


def _between(counts: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    return counts[(counts["date"] >= start) & (counts["date"] <= end)]


def _total(counts: pd.DataFrame, start: date, end: date) -> int:
    return int(_between(counts, start, end)["count"].sum())


# -- suppression -----------------------------------------------------------------------


def min_prior_rules() -> tuple[int, int]:
    """(overall, per type) minimum comparison counts, from the published findings config.

    One rule, not a second one: F-001 (`overall_change`) and F-002 (`largest_contributor`)
    already define when a percentage is too unstable to publish.
    """
    specs = {spec.calculation: spec.min_prior for spec in load_finding_specs()}
    overall = specs.get("overall_change")
    per_type = specs.get("largest_contributor")
    if overall is None or per_type is None:
        raise RuntimeError("findings config no longer defines min_prior for the Change rules")
    return overall, per_type


def _percent(current: int, comparison: int, minimum: int) -> tuple[float | None, str | None]:
    if comparison == 0:
        return None, "no reports in the comparison period"
    if comparison < minimum:
        return None, f"comparison count {comparison} is below the minimum of {minimum}"
    return round((current - comparison) / comparison * 100, 1), None


# -- decomposition ---------------------------------------------------------------------


def decompose(counts: pd.DataFrame, window: Window) -> ChangeDecomposition:
    overall_min, type_min = min_prior_rules()
    broad, _ = load_broad_categories()
    labels = {category.key: category.label for category in broad}

    current = _between(counts, window.start, window.end).groupby("primary_type")["count"].sum()
    comparison = (
        _between(counts, window.comparison_start, window.comparison_end)
        .groupby("primary_type")["count"]
        .sum()
    )
    broad_of = counts.drop_duplicates("primary_type").set_index("primary_type")["broad_category"]
    types = sorted(set(current.index[current > 0]) | set(comparison.index[comparison > 0]))

    total_current = int(current.sum())
    total_comparison = int(comparison.sum())
    total_change = total_current - total_comparison
    deltas = {t: int(current.get(t, 0)) - int(comparison.get(t, 0)) for t in types}
    gross = sum(abs(d) for d in deltas.values())

    rows: list[TypeChange] = []
    for ptype in types:
        now, then = int(current.get(ptype, 0)), int(comparison.get(ptype, 0))
        pct, reason = _percent(now, then, type_min)
        key = str(broad_of.get(ptype, "other"))
        rows.append(
            TypeChange(
                primary_type=ptype,
                broad_category=key,
                broad_label=labels.get(key, key),
                enforcement_generated=is_enforcement_generated(ptype),
                current=now,
                comparison=then,
                absolute_change=deltas[ptype],
                percent_change=pct,
                percent_withheld_reason=reason,
                net_contribution=(
                    None if total_change == 0 else round(deltas[ptype] / total_change, 4)
                ),
                gross_movement_share=None if gross == 0 else round(abs(deltas[ptype]) / gross, 4),
            )
        )
    rows.sort(key=lambda r: (-abs(r.absolute_change), r.primary_type))
    pct, reason = _percent(total_current, total_comparison, overall_min)
    sum_of_changes = sum(deltas.values())
    return ChangeDecomposition(
        total=ChangeTotal(
            current=total_current,
            comparison=total_comparison,
            absolute_change=total_change,
            percent_change=pct,
            percent_withheld_reason=reason,
        ),
        types=rows,
        sum_of_type_changes=sum_of_changes,
        reconciles=sum_of_changes == total_change,
        min_prior_total=overall_min,
        min_prior_type=type_min,
        net_contribution_status="unavailable" if total_change == 0 else "interpretation_limited",
        net_contribution_note=(
            "Each type's change divided by the overall change. Types moving in opposite "
            "directions make these signed shares exceed 100% or fall below zero, and a small "
            "overall change makes them unstable; no threshold for a meaningful overall change "
            "has been established, so they are reported for reference only."
        ),
        gross_movement_note=(
            "Share of gross category movement: each type's absolute change divided by the sum "
            "of all types' absolute changes. It shows where movement happened in either "
            "direction; it is not a contribution to the net change."
        ),
    )


# -- composition -----------------------------------------------------------------------


@dataclass(frozen=True)
class Overlay:
    key: str
    label: str
    description: str
    primary_types: frozenset[str]
    fbi_codes: frozenset[str]
    caveats: tuple[str, ...]

    def membership(self) -> str:
        if self.fbi_codes:
            return "Source fbi_code in " + ", ".join(sorted(self.fbi_codes))
        return "Source primary_type in " + ", ".join(sorted(self.primary_types))

    def mask(self, counts: pd.DataFrame) -> pd.Series:
        if self.fbi_codes:
            return counts["fbi_code"].isin(self.fbi_codes)
        return counts["primary_type"].isin(self.primary_types)


def load_overlays(path: Path | None = None) -> tuple[Overlay, ...]:
    resolved = path or Settings().crime_categories_config
    payload = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    overlays: list[Overlay] = []
    for key, entry in (payload.get("overlays") or {}).items():
        if entry.get("status", "approved") != "approved":
            continue
        if entry.get("primary_types_from") == "enforcement_generated_primary_types":
            types = load_enforcement_generated_types()
        else:
            types = frozenset(str(t).strip().upper() for t in entry.get("primary_types", []))
        codes = frozenset(str(c).strip().upper() for c in entry.get("fbi_codes", []))
        if bool(types) == bool(codes):
            raise RuntimeError(f"overlay {key}: define exactly one of primary_types / fbi_codes")
        overlays.append(
            Overlay(
                key=key,
                label=str(entry.get("label", key)),
                description=" ".join(str(entry.get("description", "")).split()),
                primary_types=types if not codes else frozenset(),
                fbi_codes=codes,
                caveats=tuple(" ".join(str(c).split()) for c in entry.get("caveats", [])),
            )
        )
    return tuple(overlays)


def _share(count: int, denominator: int) -> float | None:
    return None if denominator == 0 else round(count / denominator, 4)


def composition(counts: pd.DataFrame, through: date) -> ChangeComposition:
    broad, _ = load_broad_categories()
    overlays = load_overlays()
    last_complete = through.year if through >= date(through.year, 12, 31) else through.year - 1
    first = int(counts["year"].min()) if not counts.empty else last_complete
    years: list[CompositionYear] = []
    for year in range(first, last_complete + 1):
        part = counts[counts["year"] == year]
        total = int(part["count"].sum())
        by_broad = part.groupby("broad_category")["count"].sum()
        partition = [
            CompositionShare(
                key=c.key,
                label=c.label,
                count=int(by_broad.get(c.key, 0)),
                share=_share(int(by_broad.get(c.key, 0)), total),
                denominator=total,
            )
            for c in broad
        ]
        layered = [
            CompositionShare(
                key=o.key,
                label=o.label,
                count=int(part.loc[o.mask(part), "count"].sum()),
                share=_share(int(part.loc[o.mask(part), "count"].sum()), total),
                denominator=total,
            )
            for o in overlays
        ]
        years.append(
            CompositionYear(
                year=year,
                total=total,
                partition=partition,
                overlays=layered,
                partition_reconciles=sum(s.count for s in partition) == total,
            )
        )
    return ChangeComposition(
        first_year=first,
        last_complete_year=last_complete,
        years=years,
        overlay_definitions=[
            OverlayDefinition(
                key=o.key,
                label=o.label,
                description=o.description,
                membership=o.membership(),
                caveats=list(o.caveats),
            )
            for o in overlays
        ],
        note=(
            "The broad categories are a partition: each report is in exactly one and they sum "
            "to the total. Overlays are separate lenses on the same reports; one report can be "
            "in several, so overlay shares are never added together or drawn as parts of 100%."
        ),
    )


# -- history ---------------------------------------------------------------------------


def _last_covered(coverage: pd.DataFrame, year: int) -> date | None:
    days = coverage.loc[coverage["year"] == year, "date"]
    return None if days.empty else max(days)


def history(counts: pd.DataFrame, coverage: pd.DataFrame, window: Window) -> ChangeHistory:
    years = sorted(int(y) for y in coverage["year"].unique())
    annual: list[AnnualPoint] = []
    for year in years:
        last = _last_covered(coverage, year)
        assert last is not None
        annual.append(
            AnnualPoint(
                year=year,
                total=int(counts.loc[counts["year"] == year, "count"].sum()),
                complete=last == date(year, 12, 31),
                through=last.isoformat(),
            )
        )

    months = coverage.groupby(["year", "month"])["month_complete"].all().reset_index()
    by_month = counts.groupby(["year", "month"])["count"].sum()
    monthly = [
        MonthPoint(
            year=int(y),
            month=int(m),
            total=int(by_month.get((y, m), 0)),
            complete=bool(done),
        )
        for y, m, done in zip(
            months["year"].tolist(),
            months["month"].tolist(),
            months["month_complete"].tolist(),
            strict=True,
        )
    ]
    complete_months = [m for m in monthly if m.complete]
    trailing = [
        TrailingPoint(
            year=complete_months[i].year,
            month=complete_months[i].month,
            total=sum(m.total for m in complete_months[i - 11 : i + 1]),
        )
        for i in range(11, len(complete_months))
    ]

    complete = [a for a in annual if a.complete]
    spans: list[SpanContext] = []
    for size, label in (*SPANS, (len(complete), "Full history")):
        chosen = complete[-size:] if size else []
        if len(chosen) < size or not chosen:
            continue
        totals = [a.total for a in chosen]
        spans.append(
            SpanContext(
                label=label,
                first_year=chosen[0].year,
                last_year=chosen[-1].year,
                years=len(chosen),
                minimum=min(totals),
                median=float(median(totals)),
                maximum=max(totals),
                first_total=totals[0],
                last_total=totals[-1],
            )
        )

    current_total = _total(counts, window.start, window.end)
    # Day without a leading zero, portably (strftime's %-d is not available on Windows).
    span_label = f"{window.start.day} {window.start:%b} – {window.end.day} {window.end:%b}"
    same_span: list[SameSpanHistory] = []
    for lookback in SAME_SPAN_LOOKBACKS:
        values: list[AnnualPoint] = []
        for back in range(1, lookback + 1):
            start, end = shift_years(window.start, -back), shift_years(window.end, -back)
            if not covered(coverage, start, end):
                continue
            values.append(
                AnnualPoint(
                    year=end.year,
                    total=_total(counts, start, end),
                    complete=True,
                    through=end.isoformat(),
                )
            )
        totals = [v.total for v in values]
        same_span.append(
            SameSpanHistory(
                lookback_years=lookback,
                span_label=span_label,
                values=sorted(values, key=lambda v: v.year),
                minimum=min(totals) if totals else None,
                median=float(median(totals)) if totals else None,
                maximum=max(totals) if totals else None,
                current=current_total,
            )
        )
    return ChangeHistory(
        annual=annual,
        monthly=monthly,
        trailing_12_months=trailing,
        spans=spans,
        same_span=same_span,
    )


# -- trend -----------------------------------------------------------------------------


def kendall_trend(points: list[tuple[int, int]], span_label: str) -> TrendResult:
    """Kendall's tau-b of annual totals against year. Descriptive; never a causal claim."""
    method = "Kendall tau-b (scipy.stats.kendalltau) of complete annual totals against year"
    n = len(points)
    first = points[0][0] if points else None
    last = points[-1][0] if points else None
    if n < TREND_MIN_YEARS:
        return TrendResult(
            span_label=span_label,
            first_year=first,
            last_year=last,
            n=n,
            alpha=TREND_ALPHA,
            direction="unavailable",
            label=f"Too few complete years ({n}; at least {TREND_MIN_YEARS} are needed).",
            method=method,
        )
    totals = [total for _, total in points]
    if len(set(totals)) == 1:
        return TrendResult(
            span_label=span_label,
            first_year=first,
            last_year=last,
            n=n,
            alpha=TREND_ALPHA,
            direction="no_variation",
            label="The annual totals are identical in every year.",
            method=method,
        )
    result = kendalltau([year for year, _ in points], totals, variant="b")
    tau, p_value = float(result.statistic), float(result.pvalue)
    if math.isnan(tau) or math.isnan(p_value):
        direction, label = "unavailable", "The test could not be computed for these totals."
    elif p_value < TREND_ALPHA and tau > 0:
        direction = "rising"
        label = f"Annual totals rose across {first}–{last} (tau-b {tau:.2f}, p {p_value:.3f})."
    elif p_value < TREND_ALPHA and tau < 0:
        direction = "falling"
        label = f"Annual totals fell across {first}–{last} (tau-b {tau:.2f}, p {p_value:.3f})."
    else:
        direction = "no_consistent_direction"
        label = (
            f"No consistent direction across {first}–{last} at the {TREND_ALPHA:.0%} level "
            f"(tau-b {tau:.2f}, p {p_value:.3f})."
        )
    return TrendResult(
        span_label=span_label,
        first_year=first,
        last_year=last,
        n=n,
        tau=round(tau, 4),
        p_value=round(p_value, 4),
        alpha=TREND_ALPHA,
        direction=direction,
        label=label,
        method=method,
    )


def trends(history_: ChangeHistory) -> list[TrendResult]:
    complete = [(a.year, a.total) for a in history_.annual if a.complete]
    return [
        kendall_trend(complete[-10:], "10 years"),
        kendall_trend(complete, "Full history"),
    ]


# -- sensitivity -----------------------------------------------------------------------


def sensitivity(
    counts: pd.DataFrame, coverage: pd.DataFrame, year: int, through: date
) -> ComparisonSensitivity:
    overall_min, _ = min_prior_rules()
    rows: list[WindowSensitivity] = []
    for kind in WINDOWS:
        try:
            window = resolve_window(kind, year, through, coverage)
        except WindowUnavailable as exc:
            rows.append(
                WindowSensitivity(
                    kind=kind, label=kind, direction="unavailable", unavailable_reason=str(exc)
                )
            )
            continue
        now = _total(counts, window.start, window.end)
        then = _total(counts, window.comparison_start, window.comparison_end)
        pct, _ = _percent(now, then, overall_min)
        change = now - then
        rows.append(
            WindowSensitivity(
                kind=kind,
                label=window.label,
                current=_period(window.start, window.end),
                comparison=_period(window.comparison_start, window.comparison_end),
                current_total=now,
                comparison_total=then,
                absolute_change=change,
                percent_change=pct,
                direction="up" if change > 0 else "down" if change < 0 else "flat",
            )
        )
    directions = {r.direction for r in rows if r.direction != "unavailable"}
    return ComparisonSensitivity(
        windows=rows,
        directions_agree=None if not directions else len(directions) == 1,
        note=(
            "The same data compared over three different windows. When they disagree, the "
            "direction depends on the period chosen, and no single window settles it."
        ),
    )


# -- revisions -------------------------------------------------------------------------


def revision_summary(
    data_dir: Path,
    release_id: str,
    geography: ProductGeography,
    counts: pd.DataFrame,
    window: Window,
) -> RevisionSummary | None:
    found = latest_revision(data_dir, release_id)
    if found is None:
        return None
    proof, events = found

    def side(start: date, end: date) -> RevisionSide:
        entries = int(in_window(events, "new_", geography, start, end).sum())
        exits = int(in_window(events, "old_", geography, start, end).sum())
        # An event inside the period on both sides is neither an entry nor an exit of it.
        both = int(
            (
                in_window(events, "new_", geography, start, end)
                & in_window(events, "old_", geography, start, end)
            ).sum()
        )
        now = _total(counts, start, end)
        return RevisionSide(
            period=_period(start, end),
            current_release_total=now,
            prior_release_total=now - (entries - both) + (exits - both),
            entries=entries - both,
            exits=exits - both,
        )

    touching = (
        in_window(events, "new_", geography, window.start, window.end)
        | in_window(events, "old_", geography, window.start, window.end)
        | in_window(events, "new_", geography, window.comparison_start, window.comparison_end)
        | in_window(events, "old_", geography, window.comparison_start, window.comparison_end)
    )
    relevant = events[touching]
    reasons = [
        c
        for c in events.columns
        if c
        in {
            "added",
            "removed",
            "restored",
            "reclassified",
            "date_changed",
            "geography_changed",
            "arrest_changed",
            "domestic_changed",
        }
    ]
    return RevisionSummary(
        prior_release_id=proof.prior_release_id,
        current_release_id=proof.current_release_id,
        current_period=side(window.start, window.end),
        comparison_period=side(window.comparison_start, window.comparison_end),
        incidents_revised=int(len(relevant)),
        reasons={r: int(relevant[r].sum()) for r in reasons},
        note=(
            "Each revised incident is counted once. One incident can carry several reasons "
            "(for example reclassified and re-dated), so the reason counts are not additive. "
            "A period's total in the earlier release equals its total now, minus the incidents "
            "that entered it, plus those that left it."
        ),
    )


# -- assembly --------------------------------------------------------------------------


def _unavailable(status: str, reason: str) -> ChangeResponse:
    return ChangeResponse(analysis_status=status, unavailable_reason=reason, anchors=ANCHORS)


def build_change(
    data_dir: Path, config_dir: Path, geography_id: str, year: int | None, window_kind: str
) -> ChangeResponse:
    """The Change analysis for one geography. Raises OverviewDataUnavailable for an unknown
    or unavailable geography (the route answers 404 — never an empty, zero-looking payload)."""
    geography = resolve_geography(geography_id)
    try:
        check_gold(data_dir, config_dir)
    except GoldUnavailable as exc:
        return _unavailable(exc.condition, exc.reason)

    release = read_release_manifest(data_dir)
    through = date.fromisoformat(str(release.data_through))
    coverage = load_coverage(data_dir)
    counts = load_daily_counts(data_dir, geography.geography_id)
    chosen_year = year if year is not None else through.year
    try:
        window = resolve_window(window_kind, chosen_year, through, coverage)
    except WindowUnavailable as exc:
        return _unavailable("window_unavailable", str(exc))

    provisional = bool(coverage.loc[coverage["date"] == window.end, "provisional"].any())
    identity = ChangeIdentity(
        geography_id=geography.geography_id,
        geography_label=geography.display_name,
        geography_frame=geography_scope_note(geography),
        source=CRIME_DATASET_NAME,
        release_id=release.release_id,
        release_status=release.status,
        data_through=through.isoformat(),
        provisional=provisional,
        provisional_rule=(
            f"A period is provisional when it ends within {PROVISIONAL_WINDOW_DAYS} days of the "
            "newest published incident: the City is still adding and revising records for "
            "recent dates."
        ),
        freshness_status=crime_freshness(data_dir).status,
    )
    history_ = history(counts, coverage, window)
    revisions = revision_summary(data_dir, release.release_id, geography, counts, window)
    return ChangeResponse(
        analysis_status="ok",
        identity=identity,
        window=window.model(),
        decomposition=decompose(counts, window),
        composition=composition(counts, through),
        history=history_,
        trend=trends(history_),
        sensitivity=sensitivity(counts, coverage, chosen_year, through),
        revisions=revisions,
        revisions_note=(
            None
            if revisions is not None
            else "No retained earlier release has been compared with this one yet."
        ),
        limitations=LIMITATIONS,
        method_flags=METHOD_FLAGS,
        anchors=ANCHORS,
    )


def response_strings(response: ChangeResponse) -> list[str]:
    """Every generated string in a response — for the no-causal-language test."""
    found: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, str):
            found.append(value)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(response.model_dump())
    return found
