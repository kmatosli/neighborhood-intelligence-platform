"""One-time repack of the crime year files into small row groups.

    python -m bw_observatory.ops.repack_crime            # every year
    python -m bw_observatory.ops.repack_crime --year 2026

Files written by the historical loader hold a whole year in one Parquet row group, and a
row group is the unit a reader must materialize — so the first streaming pass over such a
file still peaks at the size of the year. Rewriting each year in `BATCH_ROWS` row groups
makes every later refresh and reconciliation run in bounded memory. Content is unchanged:
the same rows, in the same order, with the same types; only the manifest checksum moves,
and it is updated so `bronze_integrity_verified` stays true. Exit codes: 0 done, 1 a year
failed its invariants, 3 another run holds the lock.
"""

from __future__ import annotations

import argparse

import pyarrow.parquet as pq

from bw_observatory.config import Settings
from bw_observatory.geography.assign import silver_path
from bw_observatory.ingest.base import STATUS_COMPLETE, iso, now
from bw_observatory.ingest.bronze import ParquetBronzeWriter, file_checksum
from bw_observatory.ingest.partitions import (
    discard,
    partition_problems,
    publish,
    stream_rewrite,
    temp_sibling,
)
from bw_observatory.ingest.refresh_lock import AlreadyRunning, RefreshLock
from bw_observatory.logging_config import configure_logging


def repack_year(settings: Settings, year: int) -> list[str]:
    """Rewrite one year's Bronze and Silver files in small row groups. Returns problems."""
    bronze_dir = settings.data_dir / "bronze" / "crime"
    silver_dir = settings.data_dir / "silver"
    writer = ParquetBronzeWriter(bronze_dir)
    bronze_file = bronze_dir / f"{year}.parquet"
    silver_file = silver_path(silver_dir, year)

    manifest = writer.read_manifest()
    row = manifest[manifest["year"] == year]
    if row.empty:
        return [f"{year}: no manifest row; not repacked"]

    staged = {}
    try:
        for path in (bronze_file, silver_file):
            if not path.exists():
                continue
            staged[path] = temp_sibling(path)
            stream_rewrite(path, staged[path], schema=pq.read_schema(path), drop=set(), append=None)
    except BaseException:
        discard(staged)
        raise
    publish(staged)

    entry = row.iloc[0].to_dict()
    writer.upsert_manifest_entry(
        {
            "partition": str(year),
            "rows": int(entry["rows"]),
            "download_started": entry["download_started"],
            "download_completed": iso(now()),
            "api_version": entry["api_version"],
            "dataset_last_updated": entry["dataset_last_updated"],
            "checksum": file_checksum(bronze_file),
            "status": STATUS_COMPLETE,
        }
    )
    return partition_problems(bronze_dir, silver_dir, year)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, action="append", help="A year (repeatable).")
    args = parser.parse_args()

    settings = Settings()
    configure_logging(settings.log_dir, level=settings.log_level)
    bronze_dir = settings.data_dir / "bronze" / "crime"
    years = args.year or sorted(
        int(p.stem) for p in bronze_dir.glob("*.parquet") if p.stem.isdigit()
    )

    try:
        with RefreshLock(bronze_dir):
            failed = 0
            for year in years:
                problems = repack_year(settings, year)
                groups = pq.ParquetFile(bronze_dir / f"{year}.parquet").metadata.num_row_groups
                if problems:
                    failed += 1
                    print(f"  {year}: FAILED — {'; '.join(problems)}")
                else:
                    print(f"  {year}: ok ({groups} row groups)")
    except AlreadyRunning as exc:
        print(f"SKIPPED: a refresh or reconciliation is already running — {exc}")
        return 3
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
