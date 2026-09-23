"""Properties of the dataset that could explain part of a pattern.

Read-only. Nothing here describes the neighborhood; everything here describes the records, so
a reader can tell "the area changed" from "the measurement changed". Each figure is computed
from Silver columns the pipeline already writes — no new source, no new field.

Three facts drive this module, all measured on the September 2026 release:

* Published coordinates are masked to the block (Ward 20 2025: 3,438 distinct points for
  7,817 incidents), so a beat boundary cannot be resolved from them. CPD's published `beat`
  and the point-in-polygon beat therefore disagree for ~11% of records. That is a property of
  the masking, not an error, and it is disclosed rather than silently resolved.
* The disagreement scales with polygon size — ward ~3%, community area ~9%, beat ~11% —
  because a larger polygon absorbs more of the masking error.
* The City revises published records after the fact, so a recent period is incomplete and a
  decline in it may shrink as records arrive.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq

from bw_observatory.presentation.geography import (
    GEOGRAPHY_COLUMNS,
    ProductGeography,
    geography_mask,
)
from bw_observatory.presentation.models import MeasurementNotes
from bw_observatory.presentation.overview import (
    SOURCE_STATUS_COLUMN,
    bronze_path,
    silver_path,
)

#: Flag columns Silver carries for the reported-vs-spatial comparison.
_MISMATCH_COLUMNS = ("beat_mismatch", "ward_mismatch", "community_area_mismatch")

#: A period whose end is within this many days of the newest record is still filling in. The
#: source withholds roughly the last seven days and keeps editing records after publication,
#: so a window this recent is labelled provisional rather than compared like a settled one.
PROVISIONAL_WINDOW_DAYS = 60


def _flag_total(frame: pd.DataFrame, column: str) -> int:
    if column not in frame.columns:
        return 0
    return int(frame[column].fillna(False).astype(bool).sum())


def measurement_notes(
    data_dir: Path,
    year: int,
    geography: ProductGeography,
    *,
    through_iso: str,
    newest_iso: str | None = None,
) -> MeasurementNotes:
    """What the records themselves could be doing to this geography/year's figures.

    `through_iso` is the period end being published; `newest_iso` is the newest incident date
    anywhere in the release (resolved from disk when not supplied). The gap between them decides
    whether the period is still provisional: a period ending near the edge of the data is still
    filling in, while one ending long before it has settled.
    """
    if newest_iso is None:
        newest_iso = newest_incident_date(data_dir) or through_iso

    # Read Silver directly rather than through `load_geography_rows`: that helper already drops
    # withdrawn records, and this module has to count them before they disappear.
    silver = silver_path(data_dir, year)
    if not silver.exists():
        raise FileNotFoundError(silver)
    present = set(pq.read_schema(silver).names)
    optional = [
        c for c in (*_MISMATCH_COLUMNS, "geography_status", SOURCE_STATUS_COLUMN) if c in present
    ]
    enriched = pd.read_parquet(silver, columns=["id", *GEOGRAPHY_COLUMNS, *optional])
    inside = enriched[geography_mask(enriched, geography)]

    removed = 0
    if SOURCE_STATUS_COLUMN in inside.columns:
        status = inside[SOURCE_STATUS_COLUMN].astype("string")
        removed = int((status == "source_removed").sum())
        inside = inside[status != "source_removed"]

    unplaced = 0
    if "geography_status" in inside.columns:
        placed = inside["geography_status"].astype("string") == "assigned"
        unplaced = int((~placed).sum())

    beat_mismatch = _flag_total(inside, "beat_mismatch")
    ward_mismatch = _flag_total(inside, "ward_mismatch")
    area_mismatch = _flag_total(inside, "community_area_mismatch")

    provisional = _is_provisional(through_iso, newest_iso)

    total = len(inside)
    notes: list[str] = []
    if beat_mismatch and total:
        notes.append(
            f"CPD's published beat and the mapped beat disagree for {beat_mismatch:,} of "
            f"{total:,} records ({beat_mismatch / total:.0%}). Published coordinates are masked "
            "to the block, so they cannot resolve a beat boundary. Beat figures here use the "
            "beat CPD published on the record."
        )
    if ward_mismatch or area_mismatch:
        notes.append(
            f"The ward CPD published differs from the mapped ward for {ward_mismatch:,} records, "
            f"and the community area for {area_mismatch:,}. Selection here uses the mapped "
            "location, never the published field."
        )
    if unplaced:
        notes.append(
            f"{unplaced:,} records in this area could not be placed in a boundary and are "
            "excluded from geographic figures."
        )
    if removed:
        notes.append(
            f"{removed:,} records were withdrawn by the City after publication. They are kept "
            "as provenance and excluded from every figure above."
        )
    if provisional:
        notes.append(
            "This reporting period is recent enough that records are still arriving. Counts "
            "will rise and an apparent decline may shrink."
        )

    return MeasurementNotes(
        unplaced_records=unplaced,
        beat_definition_disagreements=beat_mismatch,
        ward_definition_disagreements=ward_mismatch,
        community_area_definition_disagreements=area_mismatch,
        source_removed_records=removed,
        provisional_period=provisional,
        notes=notes,
    )


def newest_incident_date(data_dir: Path) -> str | None:
    """The newest incident date in the release, from the newest Bronze year file.

    Reads one column's statistics rather than the file, so this costs a footer read.
    """
    bronze_dir = data_dir / "bronze" / "crime"
    if not bronze_dir.is_dir():
        return None
    years = sorted(int(f.stem) for f in bronze_dir.glob("*.parquet") if f.stem.isdigit())
    if not years:
        return None
    try:
        table = pq.read_table(bronze_dir / f"{years[-1]}.parquet", columns=["date"])
        newest = pc.max(table["date"]).as_py()
    except Exception:  # noqa: BLE001 - an unreadable file must not break disclosure
        return None
    return str(newest)[:10] if newest else None


def _is_provisional(through_iso: str, newest_iso: str) -> bool:
    try:
        through = date.fromisoformat(through_iso[:10])
        newest = date.fromisoformat(newest_iso[:10])
    except ValueError:
        return False
    return (newest - through).days <= PROVISIONAL_WINDOW_DAYS


def whole_beat_counts(
    data_dir: Path,
    year: int,
    *,
    start: date,
    end: date,
) -> dict[str, int]:
    """Citywide count per published beat for one period — the whole beat, not clipped.

    A CPD beat meeting covers the whole beat, so a resident comparing what they are told with
    what they read here needs the unclipped number. Reads only `id`/`date`/`beat` from Bronze
    plus `source_status` from Silver, so a large year is never fully materialized.
    """
    bronze = bronze_path(data_dir, year)
    silver = silver_path(data_dir, year)
    if not bronze.exists():
        return {}

    frame = pd.read_parquet(bronze, columns=["id", "date", "beat"])
    # `source_status` only exists on partitions a reconciliation run has touched; a partition
    # without it has nothing withdrawn to exclude.
    if silver.exists() and SOURCE_STATUS_COLUMN in set(pq.read_schema(silver).names):
        status = pd.read_parquet(silver, columns=["id", SOURCE_STATUS_COLUMN])
        frame = frame.merge(status, on="id", how="left")
        keep = frame[SOURCE_STATUS_COLUMN].astype("string") != "source_removed"
        frame = frame[keep.fillna(True)]

    when = pd.to_datetime(frame["date"], errors="coerce")
    window = (when >= pd.Timestamp(start)) & (when < pd.Timestamp(end) + pd.Timedelta(days=1))
    beats = frame.loc[window, "beat"].astype("string").str.strip()
    return {str(k): int(v) for k, v in beats.value_counts().items() if k}
