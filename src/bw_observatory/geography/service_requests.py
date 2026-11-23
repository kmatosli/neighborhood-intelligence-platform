"""Silver enrichment for 311 service requests: spatial placement plus analytical governance.

Reuses the crime pipeline's *method* and its *reference layers* — the same downloaded ward and
community-area GeoJSON, the same point-in-polygon-within predicate — without reusing
`GeographyAssigner.enrich`, whose output columns are shaped for crime records. What 311 adds is
governance the crime data does not need: an analytical-inclusion decision, a coordinate-quality
verdict, and a duplicate/parent linkage model.

Nothing is dropped and nothing is overwritten. A record that cannot be placed, or that is
excluded from service-demand figures, keeps every source value and gains a flag and a reason, so
each exclusion is countable, explainable and reversible.

The one judgement that would be easy to get wrong: the source's own `ward` is the ward recorded
when the request was created, against whatever map was in force then. It is preserved as
`source_ward` and compared, never used to decide membership.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd

from bw_observatory.geography.models import SourceStatus
from bw_observatory.ingest.service_requests import ServiceRequestConfig

#: Lon/lat. The reference layers are published in this CRS and the source's coordinates are too.
INTERCHANGE_CRS = "EPSG:4326"

#: Coordinate verdicts. Only `ok` may enter spatial analysis.
COORD_OK = "ok"
COORD_MISSING = "missing"
COORD_ZERO = "zero"
COORD_OUT_OF_RANGE = "outside_chicago"
COORD_DEFAULT_POINT = "repeated_default_point"

#: Statuses normalised to a small, stable set. The source's single "Closed" row (against
#: 14.2M "Completed") is treated as closed rather than given a category of its own.
STATUS_OPEN = "open"
STATUS_COMPLETED = "completed"
STATUS_CANCELED = "canceled"
STATUS_OTHER = "other"


@dataclass(frozen=True)
class ReferenceLayers:
    """The boundary layers Silver is measured against, and the version they came from."""

    wards: gpd.GeoDataFrame
    community_areas: gpd.GeoDataFrame
    version: str

    @property
    def vintage(self) -> str:
        return f"community_area:1920;ward:2023;reference:{self.version}"


def load_reference_layers(data_dir: Path, version: str = "2026-07-12") -> ReferenceLayers:
    """The same ward and community-area layers the crime pipeline placed its points against."""
    base = data_dir / "reference" / "chicago" / version
    wards = gpd.read_file(base / "wards_current.geojson").to_crs(INTERCHANGE_CRS)
    areas = gpd.read_file(base / "community_areas.geojson").to_crs(INTERCHANGE_CRS)

    # The ward layer carries BOTH `ward` and `ward_id`; picking by a substring match would
    # rename two columns to the same name and leave a DataFrame where a Series is expected.
    ward_column = "ward" if "ward" in wards.columns else "ward_id"
    area_column = "area_numbe" if "area_numbe" in areas.columns else "area_num_1"

    placed_wards = gpd.GeoDataFrame(
        {"ward_id": wards[ward_column].astype(str).str.strip().str.lstrip("0")},
        geometry=wards.geometry,
        crs=wards.crs,
    )
    placed_areas = gpd.GeoDataFrame(
        {"area_number": areas[area_column].astype(str).str.strip().str.lstrip("0")},
        geometry=areas.geometry,
        crs=areas.crs,
    )
    return ReferenceLayers(wards=placed_wards, community_areas=placed_areas, version=version)


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _column(frame: pd.DataFrame, name: str) -> pd.Series:
    """A column, or an all-missing column of the right length when the source omits it.

    Keeps every downstream operation total: a partition from an older retrieval that lacks a
    field yields nulls rather than a type error or a silently absent column.
    """
    if name in frame.columns:
        return frame[name]
    return pd.Series(pd.NA, index=frame.index, dtype="string")


def _dates(frame: pd.DataFrame, name: str) -> pd.Series:
    return pd.to_datetime(_column(frame, name), errors="coerce")


def classify_coordinates(
    frame: pd.DataFrame, config: ServiceRequestConfig
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """(verdict, latitude, longitude) for each row.

    A record only reaches spatial analysis with a verdict of `ok`. The `repeated_default_point`
    verdict exists because 311 geocodes some request types to a single fixed location — the
    information-only calls put over two million records on one coordinate — and placing those
    in a ward would invent a concentration that is an artifact of the geocoder.
    """
    latitude = _numeric(_column(frame, "latitude"))
    longitude = _numeric(_column(frame, "longitude"))
    bounds = config.chicago_bounds

    verdict = pd.Series(COORD_OK, index=frame.index, dtype="object")
    verdict[latitude.isna() | longitude.isna()] = COORD_MISSING
    verdict[(latitude == 0) | (longitude == 0)] = COORD_ZERO

    if bounds:
        out_of_range = (
            (latitude < bounds.get("min_latitude", -90))
            | (latitude > bounds.get("max_latitude", 90))
            | (longitude < bounds.get("min_longitude", -180))
            | (longitude > bounds.get("max_longitude", 180))
        )
        verdict[out_of_range & latitude.notna() & longitude.notna()] = COORD_OUT_OF_RANGE

    # A coordinate shared by an implausible number of records is a geocoding default. Rounding
    # first, because the source writes the same default point with varying float precision.
    candidates = verdict == COORD_OK
    if candidates.any():
        key = (
            latitude[candidates].round(6).astype("string")
            + ","
            + longitude[candidates].round(6).astype("string")
        )
        counts = key.value_counts()
        defaults = set(counts[counts >= config.default_point_threshold].index)
        if defaults:
            verdict.loc[candidates & key.isin(defaults).reindex(frame.index, fill_value=False)] = (
                COORD_DEFAULT_POINT
            )
    return verdict, latitude, longitude


def _place(
    latitude: pd.Series, longitude: pd.Series, usable: pd.Series, layers: ReferenceLayers
) -> tuple[pd.Series, pd.Series]:
    """Point-in-polygon ward and community area for the usable rows; NA for the rest."""
    ward = pd.Series(pd.NA, index=latitude.index, dtype="string")
    area = pd.Series(pd.NA, index=latitude.index, dtype="string")
    if not usable.any():
        return ward, area

    points = gpd.GeoDataFrame(
        {"_row": latitude.index[usable]},
        geometry=gpd.points_from_xy(longitude[usable], latitude[usable]),
        crs=INTERCHANGE_CRS,
    ).set_index("_row")

    for layer, column, target in (
        (layers.wards, "ward_id", ward),
        (layers.community_areas, "area_number", area),
    ):
        joined = points.sjoin(layer, how="left", predicate="within")
        # A point in two polygons of a layer that should partition space takes the first match
        # and is rare; the ward and community-area layers are partitions by construction.
        joined = joined[~joined.index.duplicated(keep="first")]
        target.loc[joined.index] = joined[column].astype("string")
    return ward, area


def _status(series: pd.Series) -> pd.Series:
    normalized = series.astype("string").str.strip().str.lower()
    mapped = pd.Series(STATUS_OTHER, index=series.index, dtype="object")
    mapped[normalized == "open"] = STATUS_OPEN
    mapped[normalized.isin(["completed", "closed"])] = STATUS_COMPLETED
    mapped[normalized == "canceled"] = STATUS_CANCELED
    return mapped


def _truthy(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.lower().isin(["true", "1", "t", "yes"])


def enrich_service_requests(
    bronze: pd.DataFrame,
    year: int,
    config: ServiceRequestConfig,
    layers: ReferenceLayers,
    ward_id: str = "20",
    ingested_at: str | None = None,
) -> pd.DataFrame:
    """Silver rows for one Bronze partition: placement, classification and governance."""
    frame = bronze.reset_index(drop=True)
    out = pd.DataFrame(index=frame.index)

    out["sr_number"] = frame["sr_number"].astype("string")
    out["parent_sr_number"] = _column(frame, "parent_sr_number")
    out["source_year"] = year

    # Classification keys on the short code, which is stable; the raw type is kept because its
    # wording is what a resident recognises even when it drifts.
    codes = _column(frame, "sr_short_code").astype("string")
    out["sr_short_code"] = codes
    out["sr_type_raw"] = _column(frame, "sr_type")
    out["analytical_category"] = codes.map(config.category_for_code).astype("string")
    subcategory = pd.Series(pd.NA, index=frame.index, dtype="string")
    for category in config.categories.values():
        for sub_key, sub_codes in category.subcategories.items():
            subcategory[codes.str.upper().isin(sub_codes)] = sub_key
    out["analytical_subcategory"] = subcategory

    created = _dates(frame, "created_date")
    out["created_at"] = created
    out["last_modified_at"] = _dates(frame, "last_modified_date")
    closed = _dates(frame, "closed_date")
    out["closed_at"] = closed
    out["created_month"] = created.dt.month
    out["created_day_of_week"] = created.dt.dayofweek
    out["created_hour"] = created.dt.hour

    out["status_raw"] = _column(frame, "status")
    status = _status(_column(frame, "status"))
    out["status_normalized"] = status.astype("string")
    out["is_open"] = status == STATUS_OPEN
    out["is_closed"] = status.isin([STATUS_COMPLETED, STATUS_CANCELED])

    # Linkage. The audit found the duplicate flag and the parent link agree, so either
    # identifies a child; both are published rather than one being inferred from the other.
    out["is_explicit_duplicate"] = _truthy(_column(frame, "duplicate"))
    out["has_parent"] = _column(frame, "parent_sr_number").notna()
    out["is_primary_request"] = ~out["is_explicit_duplicate"]

    verdict, latitude, longitude = classify_coordinates(frame, config)
    out["coordinate_quality"] = pd.Series(verdict, dtype="string")
    out["latitude"] = latitude
    out["longitude"] = longitude
    usable = verdict == COORD_OK

    spatial_ward, spatial_area = _place(latitude, longitude, usable, layers)
    out["spatial_ward_current"] = spatial_ward
    out["spatial_community_area"] = spatial_area
    # False, not NA: a record with nothing to place is definitively not inside the ward. An NA in
    # a column used as a filter mask is only ever safe by accident — the audit-candidate rows are
    # what exposed it, because they are the first rows that reach Silver with no placement.
    out["in_ward20"] = (spatial_ward == ward_id).fillna(False).astype(bool)

    # Source-reported geography is preserved and compared, never overwritten.
    out["source_ward"] = _column(frame, "ward")
    out["source_community_area"] = _column(frame, "community_area")
    out["source_zip"] = _column(frame, "zip_code")
    out["source_police_district"] = _column(frame, "police_district")
    out["source_police_beat"] = _column(frame, "police_beat")
    source_ward = out["source_ward"].astype("string").str.strip().str.lstrip("0")
    source_area = out["source_community_area"].astype("string").str.strip().str.lstrip("0")
    out["ward_mismatch"] = (
        spatial_ward.notna() & source_ward.notna() & (spatial_ward != source_ward)
    )
    out["community_area_mismatch"] = (
        spatial_area.notna() & source_area.notna() & (spatial_area != source_area)
    )

    # Analytical inclusion. Excluded rows stay, carrying the reason.
    reason = pd.Series(pd.NA, index=frame.index, dtype="string")
    for exclusion in config.exclusions:
        matched = pd.Series(True, index=frame.index)
        for column, expected in exclusion.match.items():
            if column not in frame.columns:
                matched = pd.Series(False, index=frame.index)
                break
            values = frame[column].astype("string").str.strip().str.lower()
            matched &= values == str(expected).strip().lower()
        reason[matched & reason.isna()] = exclusion.reason
    # A record with no trustworthy coordinates cannot enter a geographic figure.
    reason[reason.isna() & ~usable] = (
        "coordinate_"
        + pd.Series(verdict, index=frame.index, dtype="string")[reason.isna() & ~usable]
    )
    out["exclusion_reason"] = reason
    out["analytical_inclusion"] = reason.isna()

    out["boundary_vintage"] = layers.vintage
    out["source_dataset_id"] = _column(frame, "source_dataset_id").fillna(config.dataset_id)
    # Which retrieval clause produced the row. An audit candidate — retrieved because the SOURCE
    # labels it Ward 20, not because its point falls inside — is kept so the coordinate exclusion
    # is countable from our own data. It is still placed by point-in-polygon or not at all.
    out["retrieval_reason"] = _column(frame, "retrieval_reason")

    # Source-truth provenance, the same model the crime layers use. A refresh sees inserts and
    # edits because both restamp `last_modified_date`; it cannot see a record the City withdraws,
    # which has no timestamp to fetch. Reconciliation finds those and marks them here. Until a
    # year has been reconciled every row is ACTIVE, dated to when it was ingested — never
    # back-dated to imply an observation that did not happen.
    out["source_status"] = pd.Series(SourceStatus.ACTIVE, index=frame.index, dtype="string")
    out["source_last_seen"] = pd.Series(ingested_at or "", index=frame.index, dtype="string")
    out["source_removed_at"] = pd.Series(pd.NA, index=frame.index, dtype="string")
    return out


def duration_frame(
    silver: pd.DataFrame, category: str, config: ServiceRequestConfig
) -> pd.DataFrame:
    """Rows eligible for a recorded-closure duration, per the audited closure semantics.

    Returns an empty frame for a category whose closure semantics have not been audited, which
    is the point: a duration is published only where its meaning has been established. What the
    interval measures is the gap between two source timestamps, not the work in between.
    """
    rules = config.closure_semantics.get(category)
    if not rules:
        return silver.iloc[0:0]

    eligible = [str(s).strip().lower() for s in rules.get("duration_eligible_statuses", [])]
    rows = silver[
        silver["analytical_inclusion"]
        & (silver["analytical_category"] == category)
        & silver["status_raw"].astype("string").str.strip().str.lower().isin(eligible)
        & silver["closed_at"].notna()
        & silver["created_at"].notna()
    ]
    if rules.get("duration_excludes_duplicates", True):
        rows = rows[~rows["is_explicit_duplicate"]]
    # A closure recorded before creation is a source contradiction, not a negative duration.
    return rows[rows["closed_at"] >= rows["created_at"]]
