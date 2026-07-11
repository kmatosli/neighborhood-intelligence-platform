"""Historical Chicago crime ingestion — the first implementation of the framework.

Raw ingestion only. No neighborhood filtering, no analytics, no derived columns. The
geography fields (`ward`, `beat`, `district`, `community_area`, `latitude`, `longitude`)
are preserved exactly as published so that GIS assignment can happen later, against an
approved boundary. Wards are political and voting geography and are never a neighborhood
substitute (docs/architecture/GIS_STRATEGY.md).

Everything generic — paging, resume, manifest, refresh log, catalog registration — lives in
`base.py`. What stays here is what is actually specific to the Chicago crime dataset: the
year window, the record contract, and the schema rules.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bw_observatory.clients.chicago_data import ChicagoDataClient
from bw_observatory.config import Settings
from bw_observatory.ingest.base import (
    BaseDownloader,
    DatasetSpec,
    RecordValidationError,
    RunResult,
    SchemaValidationError,
)
from bw_observatory.ingest.bronze import ParquetBronzeWriter
from bw_observatory.ingest.catalog import schema_fingerprint
from bw_observatory.logging_config import api_logger, download_logger, validation_logger
from bw_observatory.validation.crime_schema import (
    REQUIRED_CRIME_FIELDS,
    metadata_field_names,
    missing_coordinates,
    missing_core_fields,
    missing_required_fields,
)

FIRST_YEAR = 2006
PAGE_SIZE = 50_000
API_VERSION = "socrata-resource-v2.1"

# Paging must be ordered by a stable key. Ordering by `date` would let records shift
# between pages as the portal reorders ties, which silently duplicates and drops rows.
PAGE_ORDER = "id ASC"

CRIME_DATASET = DatasetSpec(
    dataset_id="ijzp-q8t2",
    dataset_name="Chicago Crimes — 2001 to Present",
    source="City of Chicago Data Portal (Socrata)",
    primary_key="id",
    date_column="date",
    refresh_frequency="daily",
    bronze_location="data/bronze/crime",
)

# Columns the portal publishes that the project does not require, but expects to see.
OPTIONAL_CRIME_COLUMNS = {"x_coordinate", "y_coordinate", "location", "fbi_code"}


class CrimeDownloader(BaseDownloader):
    def __init__(
        self,
        settings: Settings,
        client: ChicagoDataClient | None = None,
        page_size: int = PAGE_SIZE,
    ) -> None:
        self.settings = settings
        self.client = client or ChicagoDataClient(settings)
        self.bronze_dir = settings.data_dir / "bronze" / "crime"

        super().__init__(
            CRIME_DATASET,
            ParquetBronzeWriter(self.bronze_dir, partition_column="year"),
            page_size=page_size,
            reference_dir=settings.data_dir / "reference",
        )

        self.log = download_logger()
        self.api_log = api_logger()
        self.validation_log = validation_logger()

    # -- source -----------------------------------------------------------------------

    @property
    def api_version(self) -> str:
        return API_VERSION

    def fetch_metadata(self) -> dict[str, Any]:
        return self.client.get_metadata()

    def fetch_page(self, partition: str, offset: int, limit: int) -> list[dict[str, Any]]:
        return self.client.get_crimes(
            limit=limit,
            where=year_where_clause(int(partition)),
            order=PAGE_ORDER,
            offset=offset,
        )

    def schema_version(self, metadata: dict[str, Any]) -> str:
        return schema_fingerprint(metadata_field_names(metadata))

    def source_last_updated(self, metadata: dict[str, Any]) -> str:
        return dataset_last_updated(metadata)

    # -- validation ---------------------------------------------------------------------

    def validate_schema(self, metadata: dict[str, Any]) -> int:
        """Gate the whole run on the source schema. Returns a count of warnings.

        A required column disappearing is blocking — we stop rather than ingest a dataset
        whose shape has changed underneath us. Any other metadata change is a warning.
        """
        missing = missing_required_fields(metadata)
        if missing:
            self.validation_log.error(
                "BLOCKING: source is missing required columns: %s", sorted(missing)
            )
            raise SchemaValidationError(
                f"Source dataset is missing required columns: {sorted(missing)}"
            )

        warnings = 0
        published = metadata_field_names(metadata)
        new_columns = published - (REQUIRED_CRIME_FIELDS | OPTIONAL_CRIME_COLUMNS)
        if new_columns:
            warnings += 1
            self.validation_log.warning(
                "Source publishes new columns not yet known to this project: %s. "
                "Continuing; they are preserved in Bronze.",
                sorted(new_columns),
            )

        self.validation_log.info("Schema validation passed (%d columns).", len(published))
        return warnings

    def validate_records(self, records: list[dict[str, Any]], partition: str) -> int:
        """Block on missing core fields; warn on missing coordinates. Nothing is dropped."""
        invalid = [
            {"id": record.get("id"), "missing": sorted(missing_core_fields(record))}
            for record in records
            if missing_core_fields(record)
        ]
        if invalid:
            self.validation_log.error(
                "BLOCKING: %d record(s) in %s are missing core fields: %s",
                len(invalid),
                partition,
                invalid[:5],
            )
            raise RecordValidationError(
                f"{len(invalid)} record(s) in {partition} are missing core fields: {invalid[:5]}"
            )

        no_coords = sum(1 for record in records if missing_coordinates(record))
        if no_coords:
            self.validation_log.warning(
                "%d of %d records in %s have no coordinates. They are kept in Bronze and "
                "excluded from later spatial analysis.",
                no_coords,
                len(records),
                partition,
            )
        return no_coords

    # -- logging ------------------------------------------------------------------------

    def log_download(self, message: str, *args: Any) -> None:
        self.log.info(message, *args)

    def log_api(self, message: str, *args: Any) -> None:
        self.api_log.info(message, *args)

    # -- year helpers -------------------------------------------------------------------

    def run_years(
        self, years: list[int], *, resume: bool = False, force: bool = False
    ) -> RunResult:
        """Year-typed convenience wrapper over the generic `run()`."""
        return self.run([str(year) for year in years], resume=resume, force=force)


def year_where_clause(year: int) -> str:
    """A half-open window, so a record on the year boundary lands in exactly one file."""
    return f"date >= '{year}-01-01T00:00:00.000' AND date < '{year + 1}-01-01T00:00:00.000'"


def dataset_last_updated(metadata: dict[str, Any]) -> str:
    raw = metadata.get("rowsUpdatedAt")
    if isinstance(raw, int):
        return datetime.fromtimestamp(raw, tz=UTC).isoformat()
    return "" if raw is None else str(raw)


def resolve_years(
    *,
    year: int | None = None,
    start_year: int | None = None,
    end_year: int | None = None,
    resume: bool = False,
    bronze_dir: Path | None = None,
    current_year: int | None = None,
) -> list[int]:
    """Work out which calendar years a run should cover."""
    latest = current_year if current_year is not None else datetime.now(UTC).year

    if year is not None:
        if year < FIRST_YEAR or year > latest:
            raise ValueError(f"year must be between {FIRST_YEAR} and {latest}")
        return [year]

    first = start_year if start_year is not None else FIRST_YEAR
    last = end_year if end_year is not None else latest

    if first < FIRST_YEAR:
        raise ValueError(f"start-year must not precede {FIRST_YEAR}")
    if last > latest:
        raise ValueError(f"end-year must not exceed {latest}")
    if first > last:
        raise ValueError("start-year must not be after end-year")

    candidates = list(range(first, last + 1))

    if resume and bronze_dir is not None:
        done = {int(p) for p in ParquetBronzeWriter(bronze_dir).completed_partitions()}
        return [year for year in candidates if year not in done]

    return candidates
