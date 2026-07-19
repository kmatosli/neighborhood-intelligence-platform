"""Individual Woodlawn incidents, read from the real Bronze + Silver parquet files.

Read-only. Silver supplies the spatial assignment; Bronze supplies the incident's published
fields; they are joined on the source incident `id`. Nothing is written, and no value is
derived, imputed, or invented — every field is either what the city published or what
point-in-polygon determined.

Only records whose coordinates fall inside the official Woodlawn boundary are returned:
the filter is `neighborhood_woodlawn`, never the city's reported `community_area`.

Filtering, sorting, and pagination all happen here (server-side), so the browser never has
to download a whole year to page or sort through it.
"""

from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Any

import pandas as pd

from bw_observatory.presentation.models import IncidentPage, IncidentRecord
from bw_observatory.presentation.overview import (
    OverviewDataUnavailable,
    broad_category_of,
    bronze_path,
    silver_path,
)

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200
# CSV export is bounded so a pathological request cannot stream an unbounded response. A
# Woodlawn year is a few thousand rows, well under this.
MAX_EXPORT_ROWS = 50_000

BRONZE_FIELDS = [
    "id",
    "case_number",
    "date",
    "updated_on",
    "block",
    "primary_type",
    "description",
    "location_description",
    "arrest",
    "domestic",
    "beat",
    "district",
    "ward",
    "community_area",
    "latitude",
    "longitude",
]

# Columns a reader may sort by, mapped to the frame column that backs them. `date` sorts on
# the parsed timestamp so it orders chronologically, not lexically.
SORTABLE = {
    "date": "_when",
    "block": "block",
    "primary_type": "primary_type",
    "arrest": "arrest",
    "beat": "beat",
    "district": "district",
    "ward": "ward",
}

# Columns the free-text search scans.
_SEARCH_COLUMNS = ["block", "description", "location_description", "primary_type", "case_number"]

# Column order for the CSV export — the same fields, and order, a resident sees in the table.
_EXPORT_COLUMNS = [
    "date",
    "block",
    "primary_type",
    "description",
    "location_description",
    "arrest",
    "beat",
    "district",
    "ward",
]


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) and bool(pd.isna(value)):
        return None
    text = str(value)
    return text if text else None


def _boolean(value: Any) -> bool | None:
    """Bronze stores booleans as the JSON text the API sent ("true"/"false")."""
    text = _text(value)
    if text is None:
        return None
    lowered = text.strip().lower()
    if lowered in {"true", "1"}:
        return True
    if lowered in {"false", "0"}:
        return False
    return None


def _number(value: Any) -> float | None:
    text = _text(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def load_woodlawn_incidents(data_dir: Path, year: int) -> pd.DataFrame:
    """Every Woodlawn incident for a year, newest first. Raises if the year has no data."""
    silver = silver_path(data_dir, year)
    bronze = bronze_path(data_dir, year)

    if not silver.exists():
        raise OverviewDataUnavailable(
            f"No geography-enriched crime data for {year}. Run "
            f"scripts/enrich_crime_geography.py --year {year}."
        )
    if not bronze.exists():
        raise OverviewDataUnavailable(f"No Bronze crime data for {year}.")

    enriched = pd.read_parquet(silver, columns=["id", "neighborhood_woodlawn", "geography_status"])
    woodlawn = enriched[enriched["neighborhood_woodlawn"] == True]  # noqa: E712

    attributes = pd.read_parquet(bronze, columns=BRONZE_FIELDS)
    joined = woodlawn.merge(attributes, on="id", how="left")

    joined["_when"] = pd.to_datetime(joined["date"], errors="coerce")
    # The broad, resident-facing category for each record — used by the broad_category filter.
    joined["_broad"] = joined["primary_type"].astype("string").str.upper().map(broad_category_of)
    return joined.reset_index(drop=True)


def apply_filters(
    frame: pd.DataFrame,
    *,
    primary_type: str | None = None,
    broad_category: str | None = None,
    block: str | None = None,
    description: str | None = None,
    location: str | None = None,
    ward: str | None = None,
    district: str | None = None,
    beat: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    arrest: bool | None = None,
    search: str | None = None,
) -> pd.DataFrame:
    filtered = frame

    def contains(column: str, needle: str) -> pd.DataFrame:
        values = filtered[column].astype("string").str.upper()
        return filtered[values.str.contains(needle.strip().upper(), na=False, regex=False)]

    if primary_type:
        types = filtered["primary_type"].astype("string").str.upper()
        filtered = filtered[types == primary_type.strip().upper()]

    if broad_category:
        filtered = filtered[filtered["_broad"] == broad_category.strip().lower()]

    if block:
        filtered = contains("block", block)
    if description:
        filtered = contains("description", description)
    if location:
        filtered = contains("location_description", location)
    if ward:
        filtered = filtered[filtered["ward"].astype("string").str.strip() == ward.strip()]
    if district:
        districts = filtered["district"].astype("string").str.strip().str.lstrip("0")
        filtered = filtered[districts == district.strip().lstrip("0")]
    if beat:
        beats = filtered["beat"].astype("string").str.strip().str.lstrip("0")
        filtered = filtered[beats == beat.strip().lstrip("0")]

    if date_from:
        filtered = filtered[filtered["_when"] >= pd.Timestamp(date_from)]
    if date_to:
        # Inclusive of the whole end day, which is what a reader means by "to 3 July".
        filtered = filtered[filtered["_when"] < pd.Timestamp(date_to) + pd.Timedelta(days=1)]

    if arrest is not None:
        arrests = filtered["arrest"].astype("string").str.lower()
        filtered = filtered[arrests == ("true" if arrest else "false")]

    if search:
        needle = search.strip().upper()
        mask = pd.Series(False, index=filtered.index)
        for column in _SEARCH_COLUMNS:
            mask = mask | filtered[column].astype("string").str.upper().str.contains(
                needle, na=False, regex=False
            )
        filtered = filtered[mask]

    return filtered


def sort_incidents(frame: pd.DataFrame, sort_by: str, sort_dir: str) -> pd.DataFrame:
    """Sort by a whitelisted column, `id` as a stable tie-break so paging never repeats."""
    column = SORTABLE.get(sort_by, "_when")
    ascending = sort_dir == "asc"
    return frame.sort_values(
        [column, "id"], ascending=[ascending, ascending], kind="mergesort"
    ).reset_index(drop=True)


def to_record(row: pd.Series) -> IncidentRecord:
    return IncidentRecord(
        id=str(row["id"]),
        case_number=_text(row.get("case_number")),
        date=str(row["date"]),
        updated_on=_text(row.get("updated_on")),
        block=_text(row.get("block")),
        primary_type=_text(row.get("primary_type")),
        description=_text(row.get("description")),
        location_description=_text(row.get("location_description")),
        arrest=_boolean(row.get("arrest")),
        domestic=_boolean(row.get("domestic")),
        beat=_text(row.get("beat")),
        district=_text(row.get("district")),
        ward=_text(row.get("ward")),
        community_area=_text(row.get("community_area")),
        latitude=_number(row.get("latitude")),
        longitude=_number(row.get("longitude")),
        geography_status=_text(row.get("geography_status")),
    )


def _filtered_and_sorted(
    data_dir: Path,
    year: int,
    *,
    primary_type: str | None,
    broad_category: str | None,
    block: str | None,
    description: str | None,
    location: str | None,
    ward: str | None,
    district: str | None,
    beat: str | None,
    date_from: str | None,
    date_to: str | None,
    arrest: bool | None,
    search: str | None,
    sort_by: str,
    sort_dir: str,
) -> pd.DataFrame:
    incidents = load_woodlawn_incidents(data_dir, year)
    filtered = apply_filters(
        incidents,
        primary_type=primary_type,
        broad_category=broad_category,
        block=block,
        description=description,
        location=location,
        ward=ward,
        district=district,
        beat=beat,
        date_from=date_from,
        date_to=date_to,
        arrest=arrest,
        search=search,
    )
    return sort_incidents(filtered, sort_by, sort_dir)


def build_incident_page(
    data_dir: Path,
    year: int,
    *,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    primary_type: str | None = None,
    broad_category: str | None = None,
    block: str | None = None,
    description: str | None = None,
    location: str | None = None,
    ward: str | None = None,
    district: str | None = None,
    beat: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    arrest: bool | None = None,
    search: str | None = None,
    sort_by: str = "date",
    sort_dir: str = "desc",
    neighborhood_id: str = "woodlawn",
) -> IncidentPage:
    if page < 1:
        raise ValueError("page must be 1 or greater")
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise ValueError(f"page_size must be between 1 and {MAX_PAGE_SIZE}")

    ordered = _filtered_and_sorted(
        data_dir,
        year,
        primary_type=primary_type,
        broad_category=broad_category,
        block=block,
        description=description,
        location=location,
        ward=ward,
        district=district,
        beat=beat,
        date_from=date_from,
        date_to=date_to,
        arrest=arrest,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )

    total = len(ordered)
    total_pages = math.ceil(total / page_size) if total else 0
    start = (page - 1) * page_size
    window = ordered.iloc[start : start + page_size]

    return IncidentPage(
        neighborhood_id=neighborhood_id,
        year=year,
        total_records=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        records=[to_record(row) for _, row in window.iterrows()],
    )


def build_incident_csv(
    data_dir: Path,
    year: int,
    *,
    primary_type: str | None = None,
    broad_category: str | None = None,
    block: str | None = None,
    description: str | None = None,
    location: str | None = None,
    ward: str | None = None,
    district: str | None = None,
    beat: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    arrest: bool | None = None,
    search: str | None = None,
    sort_by: str = "date",
    sort_dir: str = "desc",
) -> str:
    """The full filtered/sorted result set as CSV — masked block-level, exactly as published."""
    ordered = _filtered_and_sorted(
        data_dir,
        year,
        primary_type=primary_type,
        broad_category=broad_category,
        block=block,
        description=description,
        location=location,
        ward=ward,
        district=district,
        beat=beat,
        date_from=date_from,
        date_to=date_to,
        arrest=arrest,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
    ).head(MAX_EXPORT_ROWS)

    export = ordered.reindex(columns=_EXPORT_COLUMNS)
    buffer = io.StringIO()
    export.to_csv(buffer, index=False)
    return buffer.getvalue()
