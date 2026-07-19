"""Build the Woodlawn Overview from real Silver + Bronze data.

Silver (`crime_with_geography`) holds the spatial assignment; Bronze holds the incident
attributes (`primary_type`, `date`). They are joined on the source incident `id`. Bronze is
opened read-only and never modified.

Rules enforced here, not in the frontend:

* Woodlawn is filtered on `neighborhood_woodlawn`, the point-in-polygon result — never on
  the city's source `community_area` field, and never on a ward.
* Bronzeville has no approved boundary, so it is reported as unavailable with a reason. It
  is never zero and never inferred.
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
import yaml

from bw_observatory.config import Settings
from bw_observatory.geography.normalize import load_neighborhood_config
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


def load_neighborhood_records(data_dir: Path, year: int, neighborhood_id: str) -> pd.DataFrame:
    """Records for one neighborhood, joining spatial assignment to incident attributes."""
    silver = silver_path(data_dir, year)
    bronze = bronze_path(data_dir, year)

    if not silver.exists():
        raise OverviewDataUnavailable(
            f"No geography-enriched crime data for {year}. Run "
            f"scripts/enrich_crime_geography.py --year {year}."
        )
    if not bronze.exists():
        raise OverviewDataUnavailable(f"No Bronze crime data for {year}.")

    enriched = pd.read_parquet(silver)
    flag = f"neighborhood_{neighborhood_id}"
    if flag not in enriched.columns:
        raise OverviewDataUnavailable(f"Silver data has no `{flag}` column.")

    # The point-in-polygon result, not the city's reported community_area.
    in_neighborhood = enriched[enriched[flag] == True]  # noqa: E712

    attributes = pd.read_parquet(bronze, columns=["id", "primary_type", "date"])
    return in_neighborhood.merge(attributes, on="id", how="left")


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
    """Availability comes from the neighborhood config — the same source the pipeline uses."""
    entries: list[NeighborhoodAvailability] = []
    for config in load_neighborhood_config():
        available = config.is_active
        entries.append(
            NeighborhoodAvailability(
                neighborhood_id=config.neighborhood_id,
                display_name=config.display_name,
                available=available,
                # The resident-facing reason. Never "0 incidents".
                reason=None if available else "Boundary pending approval.",
            )
        )
    return entries


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
    neighborhood_id: str = "woodlawn",
) -> OverviewResponse:
    availability = {n.neighborhood_id: n for n in neighborhood_availability()}
    requested = availability.get(neighborhood_id)

    if requested is None:
        raise OverviewDataUnavailable(f"Unknown neighborhood: {neighborhood_id}")
    if not requested.available:
        # Bronzeville lands here. No counts are produced, and none are fabricated.
        raise OverviewDataUnavailable(
            f"{requested.display_name} is not available: {requested.reason}"
        )

    records = load_neighborhood_records(data_dir, year, neighborhood_id)
    if records.empty:
        raise OverviewDataUnavailable(f"No {requested.display_name} records found for {year}.")

    prior = year - 1
    comparison_available = year_is_enriched(data_dir, prior)

    prior_records = (
        load_neighborhood_records(data_dir, prior, neighborhood_id)
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
    neighborhood_config = next(
        c for c in load_neighborhood_config() if c.neighborhood_id == neighborhood_id
    )

    through = data_through(records)
    partial = is_year_to_date(year, through)

    return OverviewResponse(
        neighborhood_id=neighborhood_id,
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
        provenance=Provenance(
            source_dataset_id=CRIME_DATASET_ID,
            source_dataset_name=CRIME_DATASET_NAME,
            boundary_type=neighborhood_config.boundary_type,
            boundary_source=neighborhood_config.source,
            boundary_vintage=boundary_vintage(records),
            last_refresh=last_refresh(data_dir, year),
            data_through=through,
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


def overview_payload(data_dir: Path, year: int, neighborhood_id: str) -> dict[str, Any]:
    return build_overview(data_dir, year, neighborhood_id).model_dump()
