"""Build the Overview for one product geography from real Silver + Bronze data.

Silver (`crime_with_geography`) holds the spatial assignment; Bronze holds the incident
attributes (`primary_type`, `date`). They are joined on the source incident `id`. Bronze is
opened read-only and never modified.

Rules enforced here, not in the frontend:

* Place is decided by `presentation.geography` — Ward 20 overall, or the portion of a
  community area inside Ward 20 — from the point-in-polygon columns in Silver. Never from
  the city's source `ward` / `community_area` fields.
* A geography with no validated boundary is reported as unavailable with a reason. It is
  never zero and never inferred.
* Prior-year figures are `None` unless the prior year has actually been enriched. No
  imputation, no "assume flat", no arrows.
* Crime groupings come from `config/crime_categories.yml`. They are never hardcoded here.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
import yaml

from bw_observatory.config import Settings
from bw_observatory.geography.models import SourceStatus
from bw_observatory.presentation.geography import (
    GEOGRAPHY_COLUMNS,
    ProductGeography,
    boundary_source_text,
    geography_availability,
    geography_mask,
    geography_scope_note,
    load_geography_registry,
)
from bw_observatory.presentation.models import (
    CategoryCount,
    DataQuality,
    MonthlyPoint,
    NeighborhoodAvailability,
    OverviewResponse,
    Provenance,
)

CRIME_DATASET_ID = "ijzp-q8t2"
CRIME_DATASET_NAME = "Crimes - 2001 to Present (City of Chicago)"

MONTH_LABELS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]  # fmt: skip

COMPARISON_PENDING = (
    "Prior-year comparison will appear after {prior} geography enrichment is complete."
)


class OverviewDataUnavailable(RuntimeError):
    """The data this page needs has not been produced yet. Say so; do not substitute."""


@dataclass(frozen=True)
class CrimeCategory:
    key: str
    label: str
    description: str
    primary_types: frozenset[str]


@lru_cache(maxsize=1)
def load_crime_categories(path: Path | None = None) -> tuple[CrimeCategory, ...]:
    """Load the groupings. Deterministic: same file in, same order and membership out.

    Resolved at call time rather than import time so the location can come from the
    environment (`BW_CONFIG_DIR`) without the working directory deciding it.
    """
    resolved = path or Settings().crime_categories_config
    if not resolved.exists():
        raise OverviewDataUnavailable(f"Crime category config not found: {resolved}")

    payload = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    categories = payload.get("categories", {})

    return tuple(
        CrimeCategory(
            key=key,
            label=str(entry.get("label", key)),
            description=str(entry.get("description", "")).strip(),
            # Upper-cased so matching is insensitive to how the source cases its values.
            primary_types=frozenset(str(t).upper() for t in entry.get("primary_types", [])),
        )
        for key, entry in categories.items()
    )


@dataclass(frozen=True)
class BroadCategory:
    key: str
    label: str
    description: str
    primary_types: frozenset[str]


@lru_cache(maxsize=1)
def load_broad_categories(path: Path | None = None) -> tuple[tuple[BroadCategory, ...], str]:
    """Load the broad, resident-facing partition and the fallback key for unmapped types.

    Returns the ordered categories plus the `unmapped_broad_category` key (default "other").
    Unlike the analytic `categories`, this is a partition: every primary_type maps to exactly
    one broad category, and anything not listed falls to the unmapped key. Same file in, same
    order and membership out.
    """
    resolved = path or Settings().crime_categories_config
    if not resolved.exists():
        raise OverviewDataUnavailable(f"Crime category config not found: {resolved}")

    payload = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    categories = payload.get("broad_categories", {})
    unmapped = str(payload.get("unmapped_broad_category", "other"))

    broad = tuple(
        BroadCategory(
            key=key,
            label=str(entry.get("label", key)),
            description=str(entry.get("description", "")).strip(),
            primary_types=frozenset(str(t).upper() for t in entry.get("primary_types", [])),
        )
        for key, entry in categories.items()
    )
    if unmapped not in {c.key for c in broad}:
        raise OverviewDataUnavailable(
            f"unmapped_broad_category '{unmapped}' is not one of the broad categories."
        )
    return broad, unmapped


@lru_cache(maxsize=1)
def _broad_lookup() -> tuple[dict[str, str], str]:
    """primary_type (upper) -> broad key, plus the fallback key. Built once from config."""
    broad, unmapped = load_broad_categories()
    lookup = {ptype: category.key for category in broad for ptype in category.primary_types}
    return lookup, unmapped


def broad_category_of(primary_type: str | None) -> str:
    """The broad category key for a raw primary_type. Unknown/blank types map to the
    unmapped key, so no record is ever silently dropped."""
    lookup, unmapped = _broad_lookup()
    if primary_type is None:
        return unmapped
    return lookup.get(primary_type.strip().upper(), unmapped)


SOURCE_STATUS_COLUMN = "source_status"


def bronze_path(data_dir: Path, year: int) -> Path:
    return data_dir / "bronze" / "crime" / f"{year}.parquet"


def silver_path(data_dir: Path, year: int) -> Path:
    return data_dir / "silver" / "crime" / "crime_with_geography" / f"{year}.parquet"


def year_is_enriched(data_dir: Path, year: int) -> bool:
    return silver_path(data_dir, year).exists() and bronze_path(data_dir, year).exists()


def verify_bronze_integrity(data_dir: Path, year: int) -> bool:
    """Compare the Bronze file against the checksum recorded when it was ingested."""
    manifest_path = data_dir / "bronze" / "crime" / "manifest.parquet"
    source = bronze_path(data_dir, year)
    if not manifest_path.exists() or not source.exists():
        return False

    manifest = pd.read_parquet(manifest_path)
    row = manifest[manifest["year"] == year]
    if row.empty:
        return False

    recorded = str(row.iloc[0]["checksum"])
    actual = hashlib.sha256(source.read_bytes()).hexdigest()
    return bool(recorded) and recorded == actual


def resolve_geography(geography_id: str) -> ProductGeography:
    """The requested product geography, or an honest refusal.

    Unknown ids and geographies without a validated boundary both raise, with the reason,
    so the route answers 404 rather than an empty (zero-looking) payload.
    """
    geography = load_geography_registry().get(geography_id)
    if geography is None:
        raise OverviewDataUnavailable(f"Unknown geography: {geography_id}")
    if not geography.is_available:
        raise OverviewDataUnavailable(
            f"{geography.display_name} is not available: {geography.reason}"
        )
    return geography


def load_geography_rows(
    data_dir: Path,
    year: int,
    geography: ProductGeography,
    extra_columns: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Silver rows inside one geography for a year — `id`, the spatial columns, and any
    `extra_columns` the caller publishes (e.g. `geography_status`).

    Shared by every page so the place filter is applied in exactly one way. The
    `boundary_vintage` column feeds provenance and is read when present.
    """
    silver = silver_path(data_dir, year)
    if not silver.exists():
        raise OverviewDataUnavailable(
            f"No geography-enriched crime data for {year}. Run "
            f"scripts/enrich_crime_geography.py --year {year}."
        )
    if not bronze_path(data_dir, year).exists():
        raise OverviewDataUnavailable(f"No Bronze crime data for {year}.")

    wanted = ["id", *GEOGRAPHY_COLUMNS, *extra_columns]
    # Columns a partition may or may not carry yet (older enrichments lack them); read the
    # ones it has rather than failing over to none of them.
    present = set(pq.read_schema(silver).names)
    optional = [c for c in ("boundary_vintage", SOURCE_STATUS_COLUMN) if c in present]
    enriched = pd.read_parquet(silver, columns=[*wanted, *optional])
    # The point-in-polygon result, not the city's reported ward / community_area.
    inside = enriched[geography_mask(enriched, geography)]
    return current_source_view(inside)


def current_source_view(rows: pd.DataFrame) -> pd.DataFrame:
    """Drop records a reconciliation run found the City no longer publishes.

    They stay in Bronze and Silver as provenance (`source_status = source_removed`), but the
    figures on every page describe the City's *current* published dataset, so they do not
    count. A partition that predates reconciliation has no such column and is used whole.
    """
    if SOURCE_STATUS_COLUMN not in rows.columns:
        return rows
    return rows[rows[SOURCE_STATUS_COLUMN].astype("string") != SourceStatus.REMOVED]


def load_neighborhood_records(
    data_dir: Path, year: int, geography: ProductGeography
) -> pd.DataFrame:
    """Records for one geography, joining spatial assignment to incident attributes."""
    inside = load_geography_rows(data_dir, year, geography)
    attributes = pd.read_parquet(
        bronze_path(data_dir, year), columns=["id", "primary_type", "date"]
    )
    return inside.merge(attributes, on="id", how="left")


def count_categories(records: pd.DataFrame) -> dict[str, int]:
    types = records["primary_type"].astype("string").str.upper()
    return {
        category.key: int(types.isin(category.primary_types).sum())
        for category in load_crime_categories()
    }


def monthly_trend(records: pd.DataFrame, year: int) -> list[MonthlyPoint]:
    """Twelve points, always. A month with no reported incidents is a real zero."""
    months = pd.to_datetime(records["date"], errors="coerce").dt.month
    counts = months.value_counts()

    return [
        MonthlyPoint(
            month=month,
            month_label=MONTH_LABELS[month - 1],
            incidents=int(counts.get(month, 0)),
        )
        for month in range(1, 13)
    ]


def data_through(records: pd.DataFrame) -> str:
    latest = pd.to_datetime(records["date"], errors="coerce").max()
    if pd.isna(latest):
        raise OverviewDataUnavailable("No usable incident dates in the requested year.")
    return str(latest.date())


def last_refresh(data_dir: Path, year: int) -> str:
    """When the dataset was last brought up to date with the source.

    The incremental refresh confirms every year against the source's `updated_on` stream,
    whether or not the year's file needed rewriting, so its last successful run is the
    honest answer. Before any refresh has run, the year's own download date is.
    """
    log_path = data_dir / "bronze" / "crime" / "incremental_refresh_log.parquet"
    if log_path.exists():
        log = pd.read_parquet(log_path)
        if not log.empty and {"status", "dry_run", "end_time"} <= set(log.columns):
            done = log[(log["status"] == "complete") & (~log["dry_run"].astype(bool))]
            if not done.empty:
                return str(done.iloc[-1]["end_time"])[:10]
    manifest_path = data_dir / "bronze" / "crime" / "manifest.parquet"
    if not manifest_path.exists():
        return "unknown"
    manifest = pd.read_parquet(manifest_path)
    row = manifest[manifest["year"] == year]
    if row.empty:
        return "unknown"
    completed = row.iloc[0]["download_completed"]
    return "unknown" if pd.isna(completed) else str(completed)[:10]


def boundary_vintage(records: pd.DataFrame) -> str:
    if records.empty or "boundary_vintage" not in records.columns:
        return "unknown"
    return str(records["boundary_vintage"].iloc[0])


def quality_counts(data_dir: Path, year: int) -> dict[str, int]:
    """Whole-year quality figures, from the geography quality report."""
    path = data_dir / "silver" / "geography" / "geography_quality.parquet"
    if not path.exists():
        raise OverviewDataUnavailable("No geography quality report. Run the enrichment first.")

    quality = pd.read_parquet(path)
    row = quality[quality["year"] == year]
    if row.empty:
        raise OverviewDataUnavailable(f"No geography quality row for {year}.")

    record = row.iloc[0]
    return {
        "total": int(record["total_records"]),
        "no_coords": int(record["records_without_coordinates"]),
        "outside": int(record["outside_chicago_boundaries"]),
        "invalid": int(record["invalid_coordinates"]),
        "ca_mismatch": int(record["community_area_mismatches"]),
    }


def neighborhood_availability() -> list[NeighborhoodAvailability]:
    """Every product geography and whether it can be shown, from config/geographies.yml."""
    return geography_availability()


def build_provenance(
    geography: ProductGeography, records: pd.DataFrame, data_dir: Path, year: int, through: str
) -> Provenance:
    """Where the figures come from and exactly what place they cover."""
    ward = load_geography_registry().ward
    return Provenance(
        source_dataset_id=CRIME_DATASET_ID,
        source_dataset_name=CRIME_DATASET_NAME,
        boundary_type=geography.kind,
        boundary_source=boundary_source_text(geography),
        boundary_vintage=boundary_vintage(records),
        last_refresh=last_refresh(data_dir, year),
        data_through=through,
        ward_source=ward.source,
        ward_vintage=ward.source_vintage,
        geography_scope=geography_scope_note(geography),
    )


def is_year_to_date(year: int, through: str) -> bool:
    """True when the year's data stops before 31 December — an incomplete year."""
    return through < f"{year}-12-31"


def build_headline(
    year: int,
    total: int,
    comparison_available: bool,
    name: str,
    *,
    partial: bool = False,
    through: str = "",
) -> str:
    """A truthful headline.

    With no prior year there is no basis for "rose" or "fell", so the headline says what the
    page actually shows and nothing more. Direction language is only permissible once a
    comparison exists.

    A partial year says so in the headline itself. "1,919 incidents in 2026" invites the
    reader to compare it with a full year and conclude crime collapsed; "year-to-date
    through 2 July 2026" does not.
    """
    period = f"{year} year-to-date, through {through}" if partial else str(year)

    if not comparison_available:
        return (
            f"Prior-year comparisons are not available yet. This page currently shows "
            f"{total:,} reported incidents in {name} during {period}."
        )
    return (
        f"This page shows {total:,} reported incidents in {name} during {period}, "
        f"compared with the same period in the prior year."
    )


def build_overview(
    data_dir: Path,
    year: int,
    neighborhood_id: str | None = None,
) -> OverviewResponse:
    # A pending geography (no validated boundary) raises here. No counts are produced, and
    # none are fabricated.
    requested = resolve_geography(neighborhood_id or load_geography_registry().default_id)

    records = load_neighborhood_records(data_dir, year, requested)
    if records.empty:
        raise OverviewDataUnavailable(f"No {requested.display_name} records found for {year}.")

    prior = year - 1
    comparison_available = year_is_enriched(data_dir, prior)

    prior_records = (
        load_neighborhood_records(data_dir, prior, requested)
        if comparison_available
        else pd.DataFrame()
    )
    prior_counts = count_categories(prior_records) if comparison_available else {}

    counts = count_categories(records)
    total = len(records)

    categories = [
        CategoryCount(
            key=category.key,
            label=category.label,
            description=category.description,
            count=counts[category.key],
            prior_year_count=prior_counts.get(category.key) if comparison_available else None,
        )
        for category in load_crime_categories()
    ]

    quality = quality_counts(data_dir, year)

    through = data_through(records)
    partial = is_year_to_date(year, through)

    return OverviewResponse(
        neighborhood_id=requested.geography_id,
        neighborhood_name=requested.display_name,
        year=year,
        is_year_to_date=partial,
        total_incidents=total,
        total_incidents_prior_year=len(prior_records) if comparison_available else None,
        categories=categories,
        monthly_trend=monthly_trend(records, year),
        comparison_available=comparison_available,
        comparison_note=("" if comparison_available else COMPARISON_PENDING.format(prior=prior)),
        headline=build_headline(
            year,
            total,
            comparison_available,
            requested.display_name,
            partial=partial,
            through=through,
        ),
        provenance=build_provenance(requested, records, data_dir, year, through),
        data_quality=DataQuality(
            total_bronze_records_year=quality["total"],
            records_without_coordinates=quality["no_coords"],
            records_outside_boundaries=quality["outside"],
            records_invalid_coordinates=quality["invalid"],
            community_area_mismatches=quality["ca_mismatch"],
            bronze_integrity_verified=verify_bronze_integrity(data_dir, year),
        ),
        neighborhoods=neighborhood_availability(),
    )


def overview_payload(data_dir: Path, year: int, neighborhood_id: str) -> dict[str, Any]:
    return build_overview(data_dir, year, neighborhood_id).model_dump()
