"""Prove a data root is complete and internally consistent before the API is pointed at it.

    python -m bw_observatory.ops.verify_data_root                       # Settings.data_dir
    python -m bw_observatory.ops.verify_data_root --data-dir /var/data/releases/2026-09-21

Run on a staged release root *before* the release switch, and again on the live root after
it. Read-only. Every check streams (id columns and Parquet footers only), so it runs in the
same bounded memory as the refresh. Exit codes: 0 sound, 1 problems found, 2 usage.

Checks, per year 2006..newest: Bronze and Silver files present, unique ids on both layers,
identical id sets, manifest row count and checksum match the Bronze file (the same
invariants the refresh proves after every publish). Across years: no id in two year files.
Plus the geography quality file, and the freshness summary the API would report from this
root (data-through date, watermark, last run), so the root can be compared with what
production is expected to serve.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bw_observatory.config import Settings
from bw_observatory.geography.assign import quality_path
from bw_observatory.ingest.freshness import crime_freshness
from bw_observatory.ingest.partitions import duplicate_ids_across_partitions, partition_problems

FIRST_YEAR = 2006


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Data root to verify (default: the configured BW_DATA_DIR).",
    )
    return parser


def years_on_disk(bronze_dir: Path) -> list[int]:
    return sorted(int(p.stem) for p in bronze_dir.glob("*.parquet") if p.stem.isdigit())


def verify(data_dir: Path, first_year: int = FIRST_YEAR) -> list[str]:
    """Every problem found under `data_dir`; empty means the root is sound."""
    bronze_dir = data_dir / "bronze" / "crime"
    silver_dir = data_dir / "silver"
    problems: list[str] = []

    if not bronze_dir.is_dir():
        return [f"{bronze_dir}: Bronze crime directory missing"]
    years = years_on_disk(bronze_dir)
    if not years:
        return [f"{bronze_dir}: no year files"]
    # Every year from the first to the newest must exist: a gap would silently shorten
    # `/api/v1/years`, which is computed live from this directory.
    expected = list(range(first_year, years[-1] + 1))
    for year in expected:
        problems.extend(partition_problems(bronze_dir, silver_dir, year))

    duplicates = duplicate_ids_across_partitions(bronze_dir, years)
    if duplicates:
        sample = ", ".join(f"{k}:{v}" for k, v in list(duplicates.items())[:5])
        problems.append(f"{len(duplicates)} id(s) present in more than one year file ({sample})")

    if not quality_path(silver_dir).exists():
        problems.append(f"{quality_path(silver_dir)}: geography quality file missing")
    return problems


def main() -> int:
    args = build_parser().parse_args()
    data_dir: Path = args.data_dir if args.data_dir is not None else Settings().data_dir
    print(f"Data root        : {data_dir}")
    problems = verify(data_dir, first_year=FIRST_YEAR)
    freshness = crime_freshness(data_dir).as_dict()
    summary = {
        key: freshness.get(key)
        for key in (
            "status",
            "data_through",
            "source_watermark",
            "last_successful_refresh",
            "last_run_status",
            "refresh_running",
        )
    }
    print(f"Freshness        : {json.dumps(summary, default=str)}")
    if problems:
        for problem in problems:
            print(f"PROBLEM          : {problem}")
        print(f"RESULT: FAIL — {len(problems)} problem(s)")
        return 1
    print("RESULT: PASS — every year is complete and consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
