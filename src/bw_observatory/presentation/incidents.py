"""Individual incidents for one product geography, read from the real Bronze + Silver files.

Read-only. Silver supplies the spatial assignment; Bronze supplies the incident's published
fields; they are joined on the source incident `id`. Nothing is written, and no value is
derived, imputed, or invented — every field is either what the city published or what
point-in-polygon determined.

Only records whose coordinates fall inside the requested geography (Ward 20, or the part of
an area inside Ward 20) are returned. The place filter lives in `presentation.geography`,
never in the city's reported `ward` / `community_area` fields.

The `ward`, `district` and `beat` query filters are different: they match the fields CPD
publishes on each record, which is what a reader comparing this table with a CPD document
needs. Those published fields disagree with the mapped location for a minority of records
(about 3% for ward, 11% for beat on Ward 20 2025) because published coordinates are masked to
the block. Applying one can therefore hide records that ARE inside the geography, so the number
of rows dropped that way is counted and published on the response rather than left silent.

Filtering, sorting, and pagination all happen here (server-side), so the browser never has
to download a whole year to page or sort through it.
"""

from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from bw_observatory.presentation.geography import ProductGeography, load_geography_registry
from bw_observatory.presentation.models import IncidentPage, IncidentRecord
from bw_observatory.presentation.overview import (
    broad_category_of,
    bronze_path,
    load_geography_rows,
    resolve_geography,
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

# Filters that match CPD's published fields rather than the mapped location. Mixing frames is
# legitimate (a reader may want the beat CPD printed on the record) but must never be silent.
PUBLISHED_FIELD_FILTERS = ("ward", "district", "beat")

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


def load_geography_incidents(
    data_dir: Path, year: int, geography: ProductGeography
) -> pd.DataFrame:
    """Every incident inside one geography for a year. Raises if the year has no data."""
    # The spatial counterparts of the published ward/district/beat let a published-field filter
    # report how many records it hid that the mapped location would have kept. A partition from
    # an older enrichment may not carry them, so only the columns present are requested and the
    # comparison simply reports nothing rather than failing the request.
    # Only inspect the schema when the file is there: a missing year is `load_geography_rows`'s
    # error to raise, with its own message, and must stay a 404 rather than becoming a 500 here.
    silver = silver_path(data_dir, year)
    optional_spatial: tuple[str, ...] = ()
    if silver.exists():
        present = set(pq.read_schema(silver).names)
        optional_spatial = tuple(
            column
            for column in ("spatial_district_current", "spatial_beat_current")
            if column in present
        )
    inside = load_geography_rows(
        data_dir, year, geography, extra_columns=("geography_status", *optional_spatial)
    )

    attributes = pd.read_parquet(bronze_path(data_dir, year), columns=BRONZE_FIELDS)
    joined = inside.merge(attributes, on="id", how="left")

    joined["_when"] = pd.to_datetime(joined["date"], errors="coerce")
    # The broad, resident-facing category for each record — used by the broad_category filter.
    joined["_broad"] = joined["primary_type"].astype("string").str.upper().map(broad_category_of)
    return joined.reset_index(drop=True)


#: Published field -> the Silver column holding the mapped equivalent. `ward` compares against
#: the ward the geography filter already uses, so a ward filter inside a ward selection reports
#: exactly the frame disagreement.
_PUBLISHED_TO_SPATIAL = {
    "ward": "spatial_ward_current",
    "district": "spatial_district_current",
    "beat": "spatial_beat_current",
}


def _digits(values: pd.Series) -> pd.Series:
    """Ids as plain digit strings so "0312", "312" and " 312 " compare equal."""
    return values.astype("string").str.strip().str.lstrip("0").fillna("")


def _frame_disagreement_excluded(
    before: pd.DataFrame,
    after: pd.DataFrame,
    *,
    ward: str | None,
    district: str | None,
    beat: str | None,
) -> int:
    """Records dropped by a published-field filter that the mapped location would have kept.

    This is the number worth showing a reader: it is the part of the drop caused by the two
    geographic frames disagreeing, not the part caused by the filter selecting one place.
    """
    requested = {"ward": ward, "district": district, "beat": beat}
    if not any(requested.values()) or before.empty:
        return 0

    removed = before.loc[before.index.difference(after.index)]
    if removed.empty:
        return 0

    # A removed record counts only if EVERY requested filter would have matched spatially.
    keeps = pd.Series(True, index=removed.index)
    for field, value in requested.items():
        if not value:
            continue
        column = _PUBLISHED_TO_SPATIAL[field]
        if column not in removed.columns:
            return 0
        keeps &= _digits(removed[column]) == value.strip().lstrip("0")
    return int(keeps.sum())


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
    # Published-field filters. These match what CPD printed on the record, while the records
    # were selected by point-in-polygon. Removing records that do not match is the filter doing
    # its job; what has to be surfaced is narrower — records the MAPPED location would have kept
    # and the published field hid. Anything else would report "all other beats" as an exclusion.
    before_published = filtered
    if ward:
        filtered = filtered[filtered["ward"].astype("string").str.strip() == ward.strip()]
    if district:
        districts = filtered["district"].astype("string").str.strip().str.lstrip("0")
        filtered = filtered[districts == district.strip().lstrip("0")]
    if beat:
        beats = filtered["beat"].astype("string").str.strip().str.lstrip("0")
        filtered = filtered[beats == beat.strip().lstrip("0")]
    filtered.attrs["published_field_excluded"] = _frame_disagreement_excluded(
        before_published, filtered, ward=ward, district=district, beat=beat
    )

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
    geography: ProductGeography,
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
    incidents = load_geography_incidents(data_dir, year, geography)
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
    neighborhood_id: str | None = None,
) -> IncidentPage:
    if page < 1:
        raise ValueError("page must be 1 or greater")
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise ValueError(f"page_size must be between 1 and {MAX_PAGE_SIZE}")

    geography = resolve_geography(neighborhood_id or load_geography_registry().default_id)
    ordered = _filtered_and_sorted(
        data_dir,
        year,
        geography,
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

    applied = [
        name for name, value in (("ward", ward), ("district", district), ("beat", beat)) if value
    ]
    return IncidentPage(
        neighborhood_id=geography.geography_id,
        year=year,
        total_records=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        records=[to_record(row) for _, row in window.iterrows()],
        published_field_filters=applied,
        excluded_by_published_field_filters=int(ordered.attrs.get("published_field_excluded", 0)),
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
    neighborhood_id: str | None = None,
) -> str:
    """The full filtered/sorted result set as CSV — masked block-level, exactly as published."""
    geography = resolve_geography(neighborhood_id or load_geography_registry().default_id)
    ordered = _filtered_and_sorted(
        data_dir,
        year,
        geography,
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
