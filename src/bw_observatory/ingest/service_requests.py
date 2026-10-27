"""Chicago 311 Service Requests (v6vf-nfxy) — Bronze ingest and Silver enrichment.

Built on the conventions the crime pipeline established, deliberately not beside them:
per-year Parquet partitions, a manifest with a SHA-256 per file, atomic temp-sibling publish,
a watermark for incremental refresh, and an `O_EXCL` lock so only one writer runs. What is new
here is 311's own governance, and all of it lives in `config/service_requests.yml` rather than
in this code: which short codes make an analytical category, which records are excluded from
service-demand figures and why, and what a closure means for each category.

Two decisions worth stating up front, because they shape everything downstream.

**Ward membership is spatial.** The dataset carries its own `ward`, but it is the ward recorded
when the request was created, against whatever map was then in force. Membership here is the
point-in-polygon result for the published coordinates against the current Ward 20 polygon, and
the source's own ward/community area/ZIP are preserved beside it so the two can be compared
rather than confused.

**Retrieval is pre-filtered by a bounding box, not by ward.** Pulling 14.7M citywide rows to
keep a few hundred thousand would be wasteful, so retrieval asks the portal for the rectangle
around Ward 20. That is a transport optimisation, never the inclusion test: every retrieved
record still has to pass point-in-polygon, and the box is deliberately larger than the ward so
no boundary record is lost before the real test runs.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from bw_observatory.clients.chicago_data import ChicagoDataClient
from bw_observatory.config import Settings
from bw_observatory.logging_config import download_logger

#: Rows per retrieval page. Matches the crime pipeline so memory behaviour is one known
#: quantity across the project rather than two.
BATCH_ROWS = 20_000

#: Source columns kept in Bronze. The computed `:@computed_region_*` columns are left out: they
#: are the portal's own spatial joins against layers of unstated vintage, and this project does
#: its own point-in-polygon against a layer it downloaded and can name.
SOURCE_COLUMNS = (
    "sr_number",
    "sr_type",
    "sr_short_code",
    "owner_department",
    "created_department",
    "status",
    "origin",
    "created_date",
    "last_modified_date",
    "closed_date",
    "street_address",
    "city",
    "state",
    "zip_code",
    "duplicate",
    "legacy_record",
    "legacy_sr_number",
    "parent_sr_number",
    "community_area",
    "ward",
    "police_district",
    "police_beat",
    "precinct",
    "latitude",
    "longitude",
)

#: Bronze column recording which retrieval clause produced the row.
RETRIEVAL_REASON_COLUMN = "retrieval_reason"

MANIFEST_FILENAME = "manifest.parquet"
REFRESH_LOG_FILENAME = "refresh_log.parquet"


class ServiceRequestConfigError(RuntimeError):
    """The 311 governance file is malformed. Raised rather than guessing a definition."""


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    description: str
    short_codes: frozenset[str]
    validated: bool
    subcategories: dict[str, frozenset[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class Exclusion:
    reason: str
    description: str
    match: dict[str, Any]


@dataclass(frozen=True)
class ServiceRequestConfig:
    dataset_id: str
    dataset_name: str
    analysis_start_year: int
    watermark_column: str
    id_column: str
    categories: dict[str, Category]
    exclusions: tuple[Exclusion, ...]
    closure_semantics: dict[str, dict[str, Any]]
    chicago_bounds: dict[str, float]
    default_point_threshold: int

    def category_for_code(self, short_code: str | None) -> str:
        """The analytical category for a short code, or `uncategorized`.

        An unknown code keeps its raw type and lands here rather than being folded into a
        neighbour, so a new City category shows up as unrecognised instead of silently
        inflating an existing figure.
        """
        if not short_code:
            return "uncategorized"
        code = short_code.strip().upper()
        for key, category in self.categories.items():
            if code in category.short_codes:
                return key
        return "uncategorized"


def _text(value: Any) -> str:
    return " ".join(str(value).split())


@lru_cache(maxsize=1)
def load_service_request_config(path: Path | None = None) -> ServiceRequestConfig:
    """The 311 governance file, validated. Same file in, same definitions out."""
    resolved = path or Settings().service_requests_config
    if not resolved.exists():
        raise ServiceRequestConfigError(f"311 config not found: {resolved}")
    payload = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}

    dataset = payload.get("dataset") or {}
    if not dataset.get("id"):
        raise ServiceRequestConfigError("`dataset.id` is required.")

    validated = {str(k) for k in payload.get("validated_categories", [])}
    categories: dict[str, Category] = {}
    seen_codes: dict[str, str] = {}
    for key, entry in (payload.get("categories") or {}).items():
        codes = frozenset(str(c).strip().upper() for c in entry.get("short_codes", []))
        if not codes:
            raise ServiceRequestConfigError(f"category `{key}` lists no short_codes.")
        # One code in two categories would make a record's category depend on iteration order.
        for code in codes:
            if code in seen_codes:
                raise ServiceRequestConfigError(
                    f"short code {code} is claimed by both `{seen_codes[code]}` and `{key}`."
                )
            seen_codes[code] = str(key)
        subcategories = {
            str(sub_key): frozenset(str(c).strip().upper() for c in sub.get("short_codes", []))
            for sub_key, sub in (entry.get("subcategories") or {}).items()
        }
        categories[str(key)] = Category(
            key=str(key),
            label=str(entry.get("label", key)),
            description=_text(entry.get("description", "")),
            short_codes=codes,
            validated=str(key) in validated,
            subcategories=subcategories,
        )
    unknown = validated - set(categories)
    if unknown:
        raise ServiceRequestConfigError(f"validated_categories names unknown categories: {unknown}")

    exclusions = tuple(
        Exclusion(
            reason=str(item["reason"]),
            description=_text(item.get("description", "")),
            match=dict(item.get("match") or {}),
        )
        for item in payload.get("exclusions", [])
    )
    quality = payload.get("coordinate_quality") or {}
    return ServiceRequestConfig(
        dataset_id=str(dataset["id"]),
        dataset_name=str(dataset.get("name", "311 Service Requests")),
        analysis_start_year=int(dataset.get("analysis_start_year", 2019)),
        watermark_column=str(dataset.get("watermark_column", "last_modified_date")),
        id_column=str(dataset.get("id_column", "sr_number")),
        categories=categories,
        exclusions=exclusions,
        closure_semantics=dict(payload.get("closure_semantics") or {}),
        chicago_bounds=dict(quality.get("chicago_bounds") or {}),
        default_point_threshold=int(quality.get("default_point_threshold", 1000)),
    )


# -- paths --------------------------------------------------------------------------------


def bronze_dir(data_dir: Path) -> Path:
    return data_dir / "bronze" / "service_requests"


def bronze_path(data_dir: Path, year: int) -> Path:
    return bronze_dir(data_dir) / f"{year}.parquet"


def silver_dir(data_dir: Path) -> Path:
    return data_dir / "silver" / "service_requests" / "requests_with_geography"


def silver_path(data_dir: Path, year: int) -> Path:
    return silver_dir(data_dir) / f"{year}.parquet"


def years_on_disk(data_dir: Path, *, layer: str = "bronze") -> list[int]:
    directory = bronze_dir(data_dir) if layer == "bronze" else silver_dir(data_dir)
    if not directory.is_dir():
        return []
    return sorted(int(p.stem) for p in directory.glob("*.parquet") if p.stem.isdigit())


def file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_parquet_atomic(frame: pd.DataFrame, path: Path) -> None:
    """Write through a temp sibling and swap, so a crash never leaves a truncated partition."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        frame.to_parquet(temporary, index=False)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


# -- retrieval ----------------------------------------------------------------------------


def ward_bounding_box(data_dir: Path, reference_version: str) -> tuple[float, float, float, float]:
    """(min_lon, min_lat, max_lon, max_lat) around the current Ward 20 polygon.

    Used only to keep retrieval from downloading the whole city. Inclusion is still decided by
    point-in-polygon, so this box is allowed to be generous.
    """
    import geopandas as gpd

    path = data_dir / "reference" / "chicago" / reference_version / "wards_current.geojson"
    wards = gpd.read_file(path)
    column = next(c for c in wards.columns if "ward" in c.lower())
    ward = wards[wards[column].astype(str).str.lstrip("0") == "20"]
    if ward.empty:
        raise ServiceRequestConfigError(f"Ward 20 not found in {path}")
    minx, miny, maxx, maxy = (float(v) for v in ward.total_bounds)
    return minx, miny, maxx, maxy


#: Why a record was retrieved. Recorded on every Bronze row, because the two populations answer
#: different questions and must stay distinguishable after the fact.
RETRIEVAL_SPATIAL = "spatial_bounding_box"
RETRIEVAL_SOURCE_WARD = "source_ward_audit_candidate"


def _period_clause(year: int, since: str | None) -> str:
    clause = (
        f"created_date >= '{year}-01-01T00:00:00' AND created_date < '{year + 1}-01-01T00:00:00'"
    )
    if since:
        clause += f" AND last_modified_date > '{since}'"
    return clause


def source_where_clause(
    box: tuple[float, float, float, float], *, year: int, since: str | None = None
) -> str:
    """The spatial retrieval clause: records whose published point falls in the bounding box."""
    minx, miny, maxx, maxy = box
    # Socrata's within_box takes (north latitude, west longitude, south latitude, east longitude).
    return f"within_box(location, {maxy}, {minx}, {miny}, {maxx}) AND {_period_clause(year, since)}"


def audit_candidate_where_clause(ward_id: str, *, year: int, since: str | None = None) -> str:
    """The supplemental retrieval clause: records the SOURCE labels with this ward.

    This exists so Bronze can preserve records the City associates with Ward 20 that the spatial
    clause cannot reach — a record with no coordinates has no point to test, and `within_box`
    silently drops it. Retrieval and membership are different questions: these rows are kept so
    the coordinate exclusion is measurable from our own Bronze instead of only from live probes.

    The source `ward` is used here, and ONLY here, as a retrieval hint. It never grants Ward 20
    analytical membership — Silver still decides that by point-in-polygon, and a record without
    trustworthy coordinates is excluded with its reason.
    """
    return f"ward = '{ward_id}' AND {_period_clause(year, since)}"


def retrieval_clauses(
    box: tuple[float, float, float, float],
    ward_id: str,
    *,
    year: int,
    since: str | None = None,
) -> list[tuple[str, str]]:
    """Every clause that defines the retrieval universe, paired with its reason.

    One function, used by both the ingest and the reconciler, because a reconciliation that
    compared a different universe than the ingest built would report its own filter as if the
    City had withdrawn records.
    """
    return [
        (RETRIEVAL_SPATIAL, source_where_clause(box, year=year, since=since)),
        (
            RETRIEVAL_SOURCE_WARD,
            audit_candidate_where_clause(ward_id, year=year, since=since),
        ),
    ]


@dataclass
class IngestResult:
    year: int
    rows_fetched: int = 0
    rows_written: int = 0
    watermark: str | None = None
    pages: int = 0


class ServiceRequestIngest:
    """Retrieves 311 records into Bronze, one year partition at a time."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: ChicagoDataClient | None = None,
        reference_version: str = "2026-07-12",
        page_size: int = BATCH_ROWS,
        ward_id: str = "20",
    ) -> None:
        self.settings = settings
        self.config = load_service_request_config()
        self.client = client or ChicagoDataClient(settings)
        self.reference_version = reference_version
        self.page_size = page_size
        self.ward_id = ward_id
        self.log = download_logger()

    def bounding_box(self) -> tuple[float, float, float, float]:
        return ward_bounding_box(self.settings.data_dir, self.reference_version)

    def _fetch_clause(self, year: int, where: str, reason: str) -> list[dict[str, Any]]:
        """Every record one clause returns, paged and ordered stably.

        Ordering by `sr_number` matters: Socrata gives no stable order without one, so paging
        an unordered query can repeat or skip rows.
        """
        select = ",".join(SOURCE_COLUMNS)
        records: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = self.client.get_records(
                self.config.dataset_id,
                limit=self.page_size,
                offset=offset,
                where=where,
                order="sr_number",
                select=select,
            )
            # A new dict per row rather than stamping the reason onto the caller's: two clauses
            # can return the same record, and mutating a shared dict would let the second pass
            # relabel the first pass's rows.
            records.extend({**row, RETRIEVAL_REASON_COLUMN: reason} for row in page)
            self.log.info(
                "311 %s (%s): fetched %d rows (total %d)", year, reason, len(page), len(records)
            )
            if len(page) < self.page_size:
                break
            offset += self.page_size
        return records

    def fetch_year(self, year: int, *, since: str | None = None) -> list[dict[str, Any]]:
        """Every record for one year in the retrieval universe: the bounding box, plus the
        records the source itself labels with this ward.

        The second clause is what makes the coordinate exclusion measurable. A record with no
        published point cannot be tested by `within_box`, so the spatial clause drops it
        silently; keeping it in Bronze means the exclusion can be counted from our own data.
        It changes no published figure — Silver refuses to place a record without trustworthy
        coordinates, whatever the source says its ward is.

        Deduplication keeps the spatial retrieval where both clauses match the same record, so
        `retrieval_reason` names the stronger evidence rather than whichever query ran last.
        """
        records: list[dict[str, Any]] = []
        for reason, where in retrieval_clauses(
            self.bounding_box(), self.ward_id, year=year, since=since
        ):
            records.extend(self._fetch_clause(year, where, reason))
        return records

    def _conform(self, records: list[dict[str, Any]]) -> pd.DataFrame:
        """Source records as a Bronze-shaped frame: every source column, all text, plus
        provenance. Nothing is coerced or dropped."""
        frame = pd.DataFrame(records)
        for column in (*SOURCE_COLUMNS, RETRIEVAL_REASON_COLUMN):
            if column not in frame.columns:
                frame[column] = pd.NA
        frame = frame[[*SOURCE_COLUMNS, RETRIEVAL_REASON_COLUMN]].astype("string")
        # Provenance every row carries, so a partition can always say where it came from.
        frame["source_dataset_id"] = self.config.dataset_id
        frame["ingested_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        return frame

    def _dedupe(self, frame: pd.DataFrame) -> pd.DataFrame:
        """One row per `sr_number`, preferring the spatial retrieval when both clauses matched.

        Order matters for the reason, not the row: the source columns are identical either way,
        but `retrieval_reason` must name the stronger evidence. A stable sort on the preference
        rank keeps the spatial row first, so `keep="first"` resolves it.
        """
        rank = (
            frame[RETRIEVAL_REASON_COLUMN]
            .map({RETRIEVAL_SPATIAL: 0, RETRIEVAL_SOURCE_WARD: 1})
            .fillna(2)
        )
        ordered = frame.assign(_rank=rank).sort_values(
            [self.config.id_column, "_rank"], kind="stable"
        )
        ordered = ordered.drop_duplicates(subset=[self.config.id_column], keep="first")
        return ordered.drop(columns="_rank").reset_index(drop=True)

    def write_bronze(self, year: int, records: list[dict[str, Any]]) -> IngestResult:
        """Publish one year's Bronze partition and its manifest row."""
        result = IngestResult(year=year, rows_fetched=len(records), pages=0)
        if not records:
            return result

        frame = self._dedupe(self._conform(records))
        target = bronze_path(self.settings.data_dir, year)
        write_parquet_atomic(frame, target)

        watermark = str(frame[self.config.watermark_column].dropna().max() or "")
        self._upsert_manifest(year, frame, target, watermark)

        result.rows_written = len(frame)
        result.watermark = watermark or None
        return result

    def _upsert_manifest(
        self, year: int, frame: pd.DataFrame, target: Path, watermark: str
    ) -> None:
        path = bronze_dir(self.settings.data_dir) / MANIFEST_FILENAME
        row = {
            "year": year,
            "rows": len(frame),
            "source_dataset_id": self.config.dataset_id,
            "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "source_watermark": watermark,
            "checksum": file_checksum(target),
            "status": "complete",
        }
        existing = pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=list(row))
        existing = existing[existing["year"] != year] if "year" in existing.columns else existing
        updated = pd.concat([existing, pd.DataFrame([row])], ignore_index=True)
        write_parquet_atomic(updated.sort_values("year").reset_index(drop=True), path)

    def watermark_for(self, year: int) -> str | None:
        """The newest `last_modified_date` already stored for a year, for incremental refresh."""
        path = bronze_path(self.settings.data_dir, year)
        if not path.exists():
            return None
        column = self.config.watermark_column
        frame = pd.read_parquet(path, columns=[column])
        newest = frame[column].dropna().max()
        return None if pd.isna(newest) else str(newest)

    def refresh_year(self, year: int) -> IngestResult:
        """Fetch only what changed since the stored watermark and upsert it by id.

        Idempotent: running twice with nothing new leaves the partition unchanged, because the
        upsert keys on `sr_number` and the watermark only advances on a successful write.
        """
        since = self.watermark_for(year)
        fetched = self.fetch_year(year, since=since)
        if not fetched:
            return IngestResult(year=year, rows_fetched=0, watermark=since)

        target = bronze_path(self.settings.data_dir, year)
        # Resolve the two retrieval clauses against each other first, then let the refreshed row
        # win over the stored one: `keep="last"` is what makes the upsert an upsert.
        incoming = self._dedupe(self._conform(fetched))

        if target.exists():
            existing = pd.read_parquet(target)
            if RETRIEVAL_REASON_COLUMN not in existing.columns:
                # A partition written before retrieval reasons existed. Its rows came from the
                # spatial clause, which was the only one there was.
                existing[RETRIEVAL_REASON_COLUMN] = RETRIEVAL_SPATIAL
            merged = pd.concat([existing, incoming], ignore_index=True)
            merged = merged.drop_duplicates(subset=[self.config.id_column], keep="last")
        else:
            merged = incoming
        merged = merged.sort_values(self.config.id_column).reset_index(drop=True)

        write_parquet_atomic(merged, target)
        watermark = str(merged[self.config.watermark_column].dropna().max() or "")
        self._upsert_manifest(year, merged, target, watermark)
        return IngestResult(
            year=year,
            rows_fetched=len(incoming),
            rows_written=len(merged),
            watermark=watermark or None,
        )
