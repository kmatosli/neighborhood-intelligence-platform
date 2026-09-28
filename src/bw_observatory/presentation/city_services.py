"""City Services analytics over the 311 Silver layer. Read-only.

What this measures, stated once because everything below depends on it: **reported service
requests**. Not the number of physical problems, and not the City's performance. Request volume
moves with the underlying condition, but also with population, road network, awareness of 311,
access to it, reporting habits, duplicate submissions, organised reporting drives, weather and
administrative practice. Those are different things and this module never collapses them.

Consequences that show up in the code:

* Every count is available as **raw** (what residents submitted) and **primary** (excluding
  requests the City flagged as duplicates of another). Neither is "the" number.
* A completion-time statistic is produced only for a category whose closure semantics have been
  audited in `config/service_requests.yml`, and only from statuses that audit allows.
* Distributions are reported as median and quartiles, because closure times are strongly skewed
  and a mean would be moved by a handful of very old requests.
* Areas are never ranked as better or worse served. Without an exposure measure — street
  mileage for potholes — a count difference is not a service-quality difference.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from bw_observatory.geography.models import SourceStatus
from bw_observatory.geography.service_requests import duration_frame
from bw_observatory.ingest.service_requests import (
    ServiceRequestConfig,
    load_service_request_config,
    silver_path,
    years_on_disk,
)
from bw_observatory.presentation.geography import ProductGeography, load_geography_registry
from bw_observatory.presentation.overview import OverviewDataUnavailable, resolve_geography

#: A period ending within this many days of the newest record is still filling in.
PROVISIONAL_WINDOW_DAYS = 60


class CityServicesUnavailable(OverviewDataUnavailable):
    """No 311 data for the requested geography/year, with the reason."""


@dataclass(frozen=True)
class RequestCounts:
    """Raw and primary counts for one slice. Published together, always."""

    raw: int
    primary: int
    duplicates: int

    @property
    def duplicate_share(self) -> float | None:
        return round(self.duplicates / self.raw, 4) if self.raw else None


def load_silver(data_dir: Path, year: int) -> pd.DataFrame:
    """One year of enriched 311 rows, or an honest refusal."""
    path = silver_path(data_dir, year)
    if not path.exists():
        raise CityServicesUnavailable(
            f"No 311 service-request data for {year}. Run the 311 ingest for that year."
        )
    return pd.read_parquet(path)


def newest_request_date(data_dir: Path) -> date | None:
    """The newest `created_at` anywhere in the release, for judging whether a period is settled."""
    years = years_on_disk(data_dir, layer="silver")
    if not years:
        return None
    frame = pd.read_parquet(silver_path(data_dir, years[-1]), columns=["created_at"])
    newest = frame["created_at"].max()
    return None if pd.isna(newest) else newest.date()


def available_years(data_dir: Path) -> list[int]:
    """Years the 311 Silver layer can answer for, computed from disk rather than assumed."""
    config = load_service_request_config()
    return [y for y in years_on_disk(data_dir, layer="silver") if y >= config.analysis_start_year]


def in_geography(frame: pd.DataFrame, geography: ProductGeography) -> pd.Series:
    """Rows inside a product geography, by point-in-polygon placement only.

    Ward 20 overall is `spatial_ward_current == "20"`. An area within the ward additionally
    requires the mapped community area. The source's own ward is never consulted here.
    """
    inside = frame["spatial_ward_current"].astype("string") == "20"
    if geography.community_area is not None:
        inside &= frame["spatial_community_area"].astype("string") == str(
            geography.community_area
        ).lstrip("0")
    return inside


def current_source_view(rows: pd.DataFrame) -> pd.DataFrame:
    """Drop requests a reconciliation run found the City no longer publishes.

    They stay in Bronze and Silver as provenance (`source_status = source_removed`), but every
    published figure describes the City's *current* dataset, so they do not count. A partition
    written before reconciliation existed has no such column and is used whole.
    """
    if "source_status" not in rows.columns:
        return rows
    return rows[rows["source_status"].astype("string") != SourceStatus.REMOVED]


def analytical_rows(
    frame: pd.DataFrame, geography: ProductGeography, category: str | None = None
) -> pd.DataFrame:
    """The rows a published figure may use: still published, placed, inside, and included."""
    frame = current_source_view(frame)
    rows = frame[frame["analytical_inclusion"] & in_geography(frame, geography)]
    if category:
        rows = rows[rows["analytical_category"].astype("string") == category]
    return rows


def counts_for(rows: pd.DataFrame) -> RequestCounts:
    duplicates = int(rows["is_explicit_duplicate"].sum())
    return RequestCounts(raw=len(rows), primary=len(rows) - duplicates, duplicates=duplicates)


def _same_period_cutoff(through: date, prior_year: int) -> date:
    """The same month and day in the prior year, so a partial year is never set against a
    completed one. 29 February falls back to the 28th."""
    try:
        return date(prior_year, through.month, through.day)
    except ValueError:
        return date(prior_year, through.month, through.day - 1)


def _within(rows: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    """Rows created from `start` through the WHOLE of `end`.

    Inclusive of the end day: `created_at` carries a time, so comparing against midnight would
    drop the final day — the same defect that was found and fixed in the crime comparison.
    """
    created = rows["created_at"]
    return rows[
        (created >= pd.Timestamp(start)) & (created < pd.Timestamp(end) + pd.Timedelta(days=1))
    ]


def monthly_counts(rows: pd.DataFrame, through: date) -> list[dict[str, int]]:
    """Raw and primary counts per calendar month. Sums to the period total by construction.

    Months the period does not reach are omitted rather than reported as zero. A zero and "has
    not happened yet" look identical in a bar chart, and the second one is not a fact about the
    neighborhood.
    """
    out: list[dict[str, int]] = []
    for month in range(1, through.month + 1):
        slice_ = rows[rows["created_at"].dt.month == month]
        if slice_.empty:
            out.append({"month": month, "raw": 0, "primary": 0})
            continue
        counts = counts_for(slice_)
        out.append({"month": month, "raw": counts.raw, "primary": counts.primary})
    return out


def status_breakdown(rows: pd.DataFrame) -> dict[str, int]:
    """Counts by normalised status. Sums to the raw total."""
    values = rows["status_normalized"].astype("string").fillna("other")
    return {str(k): int(v) for k, v in values.value_counts().items()}


def open_request_ages(rows: pd.DataFrame, as_of: date) -> dict[str, float | int | None]:
    """How long the currently open requests have been open, in days."""
    open_rows = rows[rows["is_open"] & rows["created_at"].notna()]
    if open_rows.empty:
        return {"count": 0, "median_days": None, "p75_days": None, "oldest_days": None}
    age = (pd.Timestamp(as_of) - open_rows["created_at"]).dt.total_seconds() / 86400
    return {
        "count": int(len(open_rows)),
        "median_days": round(float(age.median()), 1),
        "p75_days": round(float(age.quantile(0.75)), 1),
        "oldest_days": round(float(age.max()), 1),
    }


def completion_times(
    rows: pd.DataFrame, category: str, config: ServiceRequestConfig
) -> dict[str, object] | None:
    """Completion-time distribution, or None when the category's semantics do not support one.

    Returning None is a real answer: a duration is published only where an audit established
    what a closure means. The numbers are days from creation to closure for the statuses the
    audit allows, excluding duplicates, because a duplicate closes when its parent is resolved
    and would measure the linkage rather than the work.
    """
    eligible = duration_frame(rows, category, config)
    if eligible.empty:
        return None
    days = (eligible["closed_at"] - eligible["created_at"]).dt.total_seconds() / 86400
    rules = config.closure_semantics.get(category, {})
    return {
        "eligible_requests": int(len(eligible)),
        "median_days": round(float(days.median()), 1),
        "p25_days": round(float(days.quantile(0.25)), 1),
        "p75_days": round(float(days.quantile(0.75)), 1),
        "p90_days": round(float(days.quantile(0.90)), 1),
        "statuses_counted": list(rules.get("duration_eligible_statuses", [])),
        "excludes_duplicates": bool(rules.get("duration_excludes_duplicates", True)),
        # The limitation that matters most, carried with the number rather than filed elsewhere.
        "interpretation": (
            "Days from when the request was created to when the City closed it. The source "
            "carries no resolution code, so a closure does not establish that the condition "
            "was repaired — only that the request was closed."
        ),
    }


def _as_int(value: object) -> int:
    """Sort key for a heterogeneous row mapping, without asserting the value's type."""
    return value if isinstance(value, int) else 0


def portion_distribution(
    frame: pd.DataFrame, category: str | None = None
) -> list[dict[str, object]]:
    """Counts across the community-area portions inside Ward 20.

    Deliberately not a ranking. Each row carries the portion's share of the ward's land, so a
    reader can see that a larger portion producing more requests is not, by itself, news.
    """
    registry = load_geography_registry()
    ward = resolve_geography(registry.default_id)
    rows = analytical_rows(frame, ward, category)
    total = len(rows)
    out: list[dict[str, object]] = []
    for geography in registry.geographies:
        if not geography.is_available or geography.community_area is None:
            continue
        area = str(geography.community_area).lstrip("0")
        slice_ = rows[rows["spatial_community_area"].astype("string") == area]
        if slice_.empty:
            continue
        counts = counts_for(slice_)
        out.append(
            {
                "geography_id": geography.geography_id,
                "label": geography.display_name,
                "raw": counts.raw,
                "primary": counts.primary,
                "share_of_ward_requests": round(counts.raw / total, 4) if total else None,
                "share_of_ward_area_pct": geography.share_of_ward_area_pct,
            }
        )
    out.sort(key=lambda row: _as_int(row.get("raw")), reverse=True)
    return out


def repeat_locations(rows: pd.DataFrame, minimum: int = 3) -> list[dict[str, object]]:
    """Addresses generating repeated requests.

    Repeated requests are evidence of repeated reporting, which is not the same as repeated
    service failure: a second request may be a duplicate, a new condition, or a resident
    following up. Records are grouped only on the address the City published — never on
    geographic proximity, which would merge conditions the source treats as distinct.
    """
    if "street_address" not in rows.columns:
        return []
    addresses = rows["street_address"].astype("string").str.strip().str.upper()
    counts = addresses.value_counts()
    frequent = counts[counts >= minimum]
    return [
        {"address": str(address), "requests": int(count)}
        for address, count in list(frequent.items())[:25]
    ]


@dataclass(frozen=True)
class CategoryReport:
    """Everything a City Services view needs for one category, geography and year."""

    geography_id: str
    geography_label: str
    geography_area_share_pct: float | None
    category: str
    category_label: str
    year: int
    data_through: str
    provisional: bool
    counts: RequestCounts
    prior_counts: RequestCounts | None
    prior_period_end: str | None
    subcategories: dict[str, int]
    monthly: list[dict[str, int]]
    status: dict[str, int]
    open_ages: dict[str, float | int | None]
    completion: dict[str, object] | None
    portions: list[dict[str, object]]
    repeat_addresses: list[dict[str, object]]
    excluded_from_analysis: dict[str, int]
    source_ward_disagreement: int
    denominator: str | None
    methodology: list[str]


def build_category_report(
    data_dir: Path, year: int, geography_id: str, category: str
) -> CategoryReport:
    """A complete, self-describing report for one service category."""
    config = load_service_request_config()
    if category not in config.categories:
        raise CityServicesUnavailable(f"Unknown service category: {category}")
    definition = config.categories[category]
    if not definition.validated:
        raise CityServicesUnavailable(
            f"{definition.label} has not had its closure semantics audited, so no figures are "
            "published for it yet."
        )

    geography = resolve_geography(geography_id)
    frame = load_silver(data_dir, year)
    rows = analytical_rows(frame, geography, category)
    if rows.empty:
        raise CityServicesUnavailable(
            f"No {definition.label.lower()} requests for {geography.display_name} in {year}."
        )

    newest = frame["created_at"].max()
    through = newest.date() if pd.notna(newest) else date(year, 12, 31)
    through = min(through, date(year, 12, 31))
    current = _within(rows, date(year, 1, 1), through)

    # A partial year is compared with the same window of the prior year, never a whole one.
    prior_counts = None
    prior_end = None
    prior_year = year - 1
    if silver_path(data_dir, prior_year).exists():
        prior_frame = load_silver(data_dir, prior_year)
        prior_rows = analytical_rows(prior_frame, geography, category)
        cutoff = _same_period_cutoff(through, prior_year)
        prior_counts = counts_for(_within(prior_rows, date(prior_year, 1, 1), cutoff))
        prior_end = cutoff.isoformat()

    excluded = frame.loc[~frame["analytical_inclusion"], "exclusion_reason"]
    # Provisional is judged against the newest data in the RELEASE, not within this year's own
    # file: a completed year's last record is by definition its own period end, so comparing the
    # two would mark every year provisional.
    newest_release = newest_request_date(data_dir)
    provisional = bool(
        newest_release is not None and (newest_release - through).days <= PROVISIONAL_WINDOW_DAYS
    )

    return CategoryReport(
        geography_id=geography.geography_id,
        geography_label=geography.display_name,
        geography_area_share_pct=geography.share_of_area_in_ward_pct,
        category=category,
        category_label=definition.label,
        year=year,
        data_through=through.isoformat(),
        provisional=provisional,
        counts=counts_for(current),
        prior_counts=prior_counts,
        prior_period_end=prior_end,
        subcategories={
            str(k): int(v)
            for k, v in current["analytical_subcategory"].astype("string").value_counts().items()
        },
        monthly=monthly_counts(current, through),
        status=status_breakdown(current),
        open_ages=open_request_ages(current, datetime.now(UTC).date()),
        completion=completion_times(current, category, config),
        portions=portion_distribution(frame, category) if geography.community_area is None else [],
        repeat_addresses=repeat_locations(current),
        excluded_from_analysis={str(k): int(v) for k, v in excluded.value_counts().items()},
        source_ward_disagreement=int(frame["ward_mismatch"].sum()),
        # Potholes would need street mileage to become a rate. The City's street centre-line
        # layer has no working API export, so no denominator is ingested and none is invented.
        denominator=None,
        methodology=[
            "Counts are service requests reported to 311, not a count of physical conditions "
            "and not a measure of how well the City performs.",
            "Ward membership is decided by placing the published coordinates in the current "
            "Ward 20 boundary, never by the ward recorded on the request.",
            f"{definition.description}",
            "Raw counts include every submission; primary counts exclude requests the City "
            "flagged as duplicates of another request.",
            "No population or street-mileage denominator is available, so these are request "
            "counts and not rates. Areas are not ranked by them.",
        ],
    )
