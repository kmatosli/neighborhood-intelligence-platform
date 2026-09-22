"""Partition-level I/O shared by the crime refresh and reconciliation.

Two concerns live here so that neither pipeline step has to re-derive them:

* **Bounded memory.** A Bronze year holds up to ~450k rows of ~22 text columns — ~380 MB as
  one Arrow table, ~360 MB as a pandas frame of Python strings, and an upsert that reads the
  whole thing and concatenates doubles that. The API runs on a 512 MB instance, and the
  scheduled refresh runs beside it. So nothing here materializes a partition: every rewrite
  streams the existing file through a `ParquetWriter` in `BATCH_ROWS` batches (single
  threaded — the parallel reader pulls several row groups in at once), dropping the rows
  being replaced and appending the new ones at the end. Files are written in small row
  groups so the next run streams them just as cheaply. Only the rows being compared or
  enriched ever become a pandas frame.

* **Integrity invariants.** After a partition is published, `partition_problems` proves the
  state the API will read from: unique ids on both layers, the same id set on both, and a
  manifest row whose checksum matches the bytes on disk. A refresh that cannot prove this
  fails rather than advancing its watermark.

Row order after a rewrite is: surviving rows in their previous order, then appended rows
in ascending id. Bronze and Silver are rewritten with the same drop set and the same
appended ids, so they stay row-aligned; nothing depends on that alignment (the API joins on
`id`), it just keeps the files easy to inspect side by side.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from bw_observatory.geography.assign import silver_path
from bw_observatory.geography.models import GeographyStatus
from bw_observatory.ingest.bronze import MANIFEST_FILENAME, file_checksum

ID_COLUMN = "id"
BATCH_ROWS = 20_000


# -- staging and publishing --------------------------------------------------------------


def temp_sibling(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")


def write_table_atomic(table: pa.Table, path: Path) -> None:
    """Write to a sibling temp file, then swap. The old file is intact until the swap."""
    temporary = temp_sibling(path)
    try:
        pq.write_table(table, temporary, row_group_size=BATCH_ROWS)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_parquet_atomic(frame: pd.DataFrame, path: Path) -> None:
    write_table_atomic(pa.Table.from_pandas(frame, preserve_index=False), path)


def publish(staged: dict[Path, Path]) -> None:
    """Swap every staged temp file into place, cleaning up on the way."""
    try:
        for target, temporary in staged.items():
            os.replace(temporary, target)
    finally:
        discard(staged)


def discard(staged: dict[Path, Path]) -> None:
    """Remove staged temp files that will not be published (a later stage failed)."""
    for temporary in staged.values():
        if temporary.exists():
            temporary.unlink()


# -- reading without materializing ---------------------------------------------------------


def iter_batches(path: Path, columns: list[str] | None = None) -> Iterator[pa.RecordBatch]:
    parquet = pq.ParquetFile(path)
    yield from parquet.iter_batches(batch_size=BATCH_ROWS, columns=columns, use_threads=False)


def row_count(path: Path) -> int:
    """Row count from the Parquet footer — no data is read."""
    return int(pq.read_metadata(path).num_rows)


def file_columns(path: Path) -> list[str]:
    return list(pq.read_schema(path).names)


def column_max(path: Path, column: str) -> str | None:
    """Newest value of a text column (used for the `updated_on` watermark)."""
    newest: str | None = None
    for batch in iter_batches(path, [column]):
        value = pc.max(batch.column(column)).as_py()
        if value is not None and (newest is None or str(value) > newest):
            newest = str(value)
    return newest


def partition_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    for batch in iter_batches(path, [ID_COLUMN]):
        ids.update(str(v) for v in batch.column(ID_COLUMN).to_pylist())
    return ids


def _id_mask(batch: pa.RecordBatch | pa.Table, ids: set[str]) -> pa.Array:
    column = batch.column(ID_COLUMN)
    if not ids:
        return pa.array([False] * batch.num_rows, type=pa.bool_())
    return pc.is_in(column, value_set=pa.array(sorted(ids), type=column.type))


def ids_present(path: Path, ids: set[str]) -> set[str]:
    """Which of `ids` this partition holds. One Arrow filter per batch, no Python loop."""
    if not ids:
        return set()
    present: set[str] = set()
    for batch in iter_batches(path, [ID_COLUMN]):
        present.update(
            str(v) for v in batch.column(ID_COLUMN).filter(_id_mask(batch, ids)).to_pylist()
        )
    return present


def rows_for_ids(path: Path, ids: set[str]) -> pd.DataFrame:
    """The rows for `ids`, as a string-typed pandas frame indexed by id. Only those rows
    are ever materialized."""
    schema = pq.read_schema(path)
    pieces = [batch.filter(_id_mask(batch, ids)) for batch in iter_batches(path)]
    table = pa.Table.from_batches(pieces, schema=schema) if pieces else schema.empty_table()
    frame: pd.DataFrame = table.to_pandas()
    return frame.astype("string").set_index(ID_COLUMN)


# -- schemas ----------------------------------------------------------------------------


def bronze_schema(columns: list[str]) -> pa.Schema:
    """All-text schema with the pandas metadata `records_to_frame(...).to_parquet(...)`
    writes, so every reader still gets `string`-typed columns back."""
    empty = pd.DataFrame({column: pd.Series(dtype="string") for column in columns})
    return pa.Schema.from_pandas(empty, preserve_index=False)


def frame_schema(frame: pd.DataFrame) -> pa.Schema:
    """The schema (with pandas metadata) a frame with these dtypes writes."""
    return pa.Schema.from_pandas(frame.head(0), preserve_index=False)


def conform(table: pa.Table, schema: pa.Schema, defaults: dict[str, Any] | None = None) -> pa.Table:
    """Give `table` exactly the schema's columns, in order, with its types.

    A column the table lacks is filled with its default (or null). Types are cast safely,
    so a legacy `large_string` column becomes `string` without loss.
    """
    filled = defaults or {}
    for field in schema:
        if field.name not in table.column_names:
            value = filled.get(field.name)
            table = table.append_column(
                field.name,
                pa.nulls(len(table), field.type)
                if value is None
                else pa.array([value] * len(table), type=field.type),
            )
    return table.select(schema.names).cast(schema)


def frame_to_table(frame: pd.DataFrame, schema: pa.Schema) -> pa.Table:
    table = pa.Table.from_pandas(frame.reindex(columns=schema.names), preserve_index=False)
    return conform(table, schema)


# -- streaming rewrite ------------------------------------------------------------------


def stream_rewrite(
    source: Path | None,
    target: Path,
    *,
    schema: pa.Schema,
    drop: set[str],
    append: pa.Table | None,
    defaults: dict[str, Any] | None = None,
    adapt: Callable[[pa.Table], pa.Table] | None = None,
) -> list[str]:
    """Write `source` minus the rows whose id is in `drop`, then `append`, to `target`.

    Batches pass through `adapt` (if given) after being conformed to the schema, which is
    how reconciliation rewrites the provenance columns without loading the year. Returns
    every id in the order written, which is what the caller needs to keep Bronze and Silver
    aligned and to prove the result.
    """
    written: list[str] = []
    with pq.ParquetWriter(target, schema) as writer:
        if source is not None and source.exists():
            for batch in iter_batches(source):
                table = conform(pa.Table.from_batches([batch]), schema, defaults)
                if drop:
                    table = table.filter(pc.invert(_id_mask(table, drop)))
                if adapt is not None:
                    table = conform(adapt(table), schema)
                if len(table):
                    writer.write_table(table, row_group_size=BATCH_ROWS)
                    written.extend(str(v) for v in table.column(ID_COLUMN).to_pylist())
        if append is not None and len(append):
            table = conform(append, schema)
            writer.write_table(table, row_group_size=BATCH_ROWS)
            written.extend(str(v) for v in table.column(ID_COLUMN).to_pylist())
    return written


def sorted_by_id(table: pa.Table) -> pa.Table:
    """Ascending numeric id — the historical loader's page order."""
    return table.take(pc.sort_indices(pc.cast(table.column(ID_COLUMN), pa.int64())))


# -- quality report without materializing ----------------------------------------------


def _count_equal(table: pa.Table, column: str, value: Any) -> int:
    if column not in table.column_names:
        return 0
    equal = pc.fill_null(pc.equal(table.column(column), value), False)
    return int(pc.sum(pc.cast(equal, pa.int64())).as_py() or 0)


def _count_true(table: pa.Table, column: str) -> int:
    if column not in table.column_names:
        return 0
    flags = pc.fill_null(table.column(column), False)
    return int(pc.sum(pc.cast(flags, pa.int64())).as_py() or 0)


def _count_present(table: pa.Table, column: str) -> int:
    if column not in table.column_names:
        return 0
    return int(len(table) - table.column(column).null_count)


def quality_row_from_file(path: Path, year: int, bronzeville_available: bool) -> dict[str, Any]:
    """The same figures as `assign.quality_row`, accumulated batch by batch."""
    totals: dict[str, int] = {}
    first_vintage = ""
    first_enriched = ""

    def add(key: str, value: int) -> None:
        totals[key] = totals.get(key, 0) + value

    for batch in iter_batches(path):
        table = pa.Table.from_batches([batch])
        if not first_vintage and len(table):
            first_vintage = str(table.column("boundary_vintage")[0].as_py() or "")
            first_enriched = str(table.column("enriched_at")[0].as_py() or "")
        add("total_records", len(table))
        missing = _count_equal(table, "geography_status", GeographyStatus.MISSING_COORDINATES)
        add("records_without_coordinates", missing)
        add("records_with_coordinates", len(table) - missing)
        add("records_assigned_to_community_area", _count_present(table, "spatial_community_area"))
        add("records_assigned_to_ward", _count_present(table, "spatial_ward_current"))
        add("records_assigned_to_beat", _count_present(table, "spatial_beat_current"))
        add("records_assigned_to_district", _count_present(table, "spatial_district_current"))
        add("records_assigned_to_census_tract", _count_present(table, "census_tract"))
        add("records_woodlawn", _count_true(table, "neighborhood_woodlawn"))
        add("records_bronzeville", _count_true(table, "neighborhood_bronzeville"))
        add("ward_mismatches", _count_true(table, "ward_mismatch"))
        add("beat_mismatches", _count_true(table, "beat_mismatch"))
        add("district_mismatches", _count_true(table, "district_mismatch"))
        add("community_area_mismatches", _count_true(table, "community_area_mismatch"))
        add(
            "invalid_coordinates",
            _count_equal(table, "geography_status", GeographyStatus.INVALID_COORDINATES),
        )
        add(
            "outside_chicago_boundaries",
            _count_equal(table, "geography_status", GeographyStatus.OUTSIDE_CHICAGO),
        )
        add(
            "ambiguous_overlaps",
            _count_equal(table, "geography_status", GeographyStatus.AMBIGUOUS_OVERLAP),
        )

    def total(key: str) -> int:
        return totals.get(key, 0)

    return {
        "year": year,
        "total_records": total("total_records"),
        "records_with_coordinates": total("records_with_coordinates"),
        "records_without_coordinates": total("records_without_coordinates"),
        "records_assigned_to_community_area": total("records_assigned_to_community_area"),
        "records_assigned_to_ward": total("records_assigned_to_ward"),
        "records_assigned_to_beat": total("records_assigned_to_beat"),
        "records_assigned_to_district": total("records_assigned_to_district"),
        "records_assigned_to_census_tract": total("records_assigned_to_census_tract"),
        "records_woodlawn": total("records_woodlawn"),
        "records_bronzeville": total("records_bronzeville") if bronzeville_available else None,
        "bronzeville_status": (
            "assigned" if bronzeville_available else GeographyStatus.BRONZEVILLE_UNAVAILABLE
        ),
        "ward_mismatches": total("ward_mismatches"),
        "beat_mismatches": total("beat_mismatches"),
        "district_mismatches": total("district_mismatches"),
        "community_area_mismatches": total("community_area_mismatches"),
        "invalid_coordinates": total("invalid_coordinates"),
        "outside_chicago_boundaries": total("outside_chicago_boundaries"),
        "ambiguous_overlaps": total("ambiguous_overlaps"),
        "boundary_vintage": first_vintage,
        "enriched_at": first_enriched,
    }


# -- invariants -------------------------------------------------------------------------


def partition_problems(bronze_dir: Path, silver_dir: Path, year: int) -> list[str]:
    """Every way a published year could be inconsistent. Empty means the year is sound.

    Reads only the `id` columns and the Parquet footers, plus one checksum of the Bronze
    file, so it is cheap enough to run after every partition write.
    """
    problems: list[str] = []
    bronze_file = bronze_dir / f"{year}.parquet"
    silver_file = silver_path(silver_dir, year)

    if not bronze_file.exists():
        return [f"{year}: Bronze file missing"]
    if not silver_file.exists():
        return [f"{year}: Silver file missing"]

    bronze_list: list[str] = []
    for batch in iter_batches(bronze_file, [ID_COLUMN]):
        bronze_list.extend(str(v) for v in batch.column(ID_COLUMN).to_pylist())
    silver_list: list[str] = []
    for batch in iter_batches(silver_file, [ID_COLUMN]):
        silver_list.extend(str(v) for v in batch.column(ID_COLUMN).to_pylist())
    bronze_set, silver_set = set(bronze_list), set(silver_list)

    if len(bronze_set) != len(bronze_list):
        problems.append(f"{year}: {len(bronze_list) - len(bronze_set)} duplicate Bronze id(s)")
    if len(silver_set) != len(silver_list):
        problems.append(f"{year}: {len(silver_list) - len(silver_set)} duplicate Silver id(s)")
    if bronze_set - silver_set:
        problems.append(f"{year}: {len(bronze_set - silver_set)} Bronze id(s) with no Silver row")
    if silver_set - bronze_set:
        problems.append(f"{year}: {len(silver_set - bronze_set)} orphan Silver row(s)")

    manifest_file = bronze_dir / MANIFEST_FILENAME
    if not manifest_file.exists():
        problems.append(f"{year}: manifest missing")
        return problems
    manifest = pd.read_parquet(manifest_file)
    row = manifest[manifest["year"] == year]
    if row.empty:
        problems.append(f"{year}: no manifest row")
        return problems
    if int(row.iloc[0]["rows"]) != len(bronze_list):
        problems.append(
            f"{year}: manifest says {int(row.iloc[0]['rows'])} rows, file has {len(bronze_list)}"
        )
    if str(row.iloc[0]["checksum"]) != file_checksum(bronze_file):
        problems.append(f"{year}: manifest checksum does not match the Bronze file")
    return problems


def duplicate_ids_across_partitions(bronze_dir: Path, years: list[int]) -> dict[str, list[int]]:
    """Ids that appear in more than one year file. Expected to be empty."""
    seen: dict[str, list[int]] = {}
    for year in years:
        for record_id in partition_ids(bronze_dir / f"{year}.parquet"):
            seen.setdefault(record_id, []).append(year)
    return {record_id: years for record_id, years in seen.items() if len(years) > 1}
