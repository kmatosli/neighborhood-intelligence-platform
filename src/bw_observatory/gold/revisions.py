"""Incident-level revision events between two retained releases (CA-11).

    <current_root>/gold/crime/revisions/<prior_id>__<current_id>/events.parquet
    <current_root>/gold/crime/revisions/<prior_id>__<current_id>/_proof.json

One row per incident id whose state differs between the releases, for every id placed in
Ward 20 in either of them. An id appears **once** however many of its attributes changed,
and its reason flags may be several at once — so reasons are never summed into a total.

The source publishes no report date (`date` is when the incident occurred; `updated_on` is
the last edit), so a revision is observed only by comparing what two releases published.

Every summary derives from this table. The builder proves, for every analytical cell
(geography × year × month × primary type, current-source view),

    current_count − prior_count = entries_to_cell − exits_from_cell

where an entry is an event whose new state is in the cell and whose old state is not, and an
exit the reverse. If any cell fails, nothing is published.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from bw_observatory.geography.models import SourceStatus
from bw_observatory.gold.crime_aggregates import (
    BUILD_FAIL,
    BUILD_PASS,
    built_geographies,
    gold_dir,
)
from bw_observatory.presentation.geography import (
    COMMUNITY_AREA_COLUMN,
    KIND_WARD,
    WARD_COLUMN,
    ProductGeography,
    geography_mask,
)
from bw_observatory.presentation.overview import SOURCE_STATUS_COLUMN, bronze_path, silver_path
from bw_observatory.release import ReleaseManifestError, read_release_manifest

REVISIONS_DIR = "revisions"
EVENTS_FILENAME = "events.parquet"
PROOF_FILENAME = "_proof.json"

# Compared attributes, in the order they are published (old_/new_ pairs).
_ATTRIBUTES = [
    "date",
    "year",
    "month",
    "primary_type",
    "fbi_code",
    "arrest",
    "domestic",
    "ward",
    "community_area",
    "source_status",
]
REASONS = [
    "added",
    "removed",
    "restored",
    "reclassified",
    "date_changed",
    "geography_changed",
    "arrest_changed",
    "domestic_changed",
]


class RevisionBuildError(RuntimeError):
    """The revision events could not be proved consistent; nothing was published."""


@dataclass
class RevisionProof:
    prior_release_id: str
    current_release_id: str
    built_at: str
    events: int
    ids_compared: int
    cells_checked: int
    failures: list[str] = field(default_factory=list)
    status: str = BUILD_FAIL

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def revision_dir(current_root: Path, prior_id: str, current_id: str) -> Path:
    return gold_dir(current_root) / REVISIONS_DIR / f"{prior_id}__{current_id}"


def _years(root: Path) -> list[int]:
    folder = silver_path(root, 2006).parent
    return sorted(int(p.stem) for p in folder.glob("*.parquet") if p.stem.isdigit())


def _ward(geographies: list[ProductGeography]) -> ProductGeography:
    return next(g for g in geographies if g.kind == KIND_WARD)


def _ward_ids(root: Path, ward: ProductGeography) -> set[str]:
    ids: set[str] = set()
    for year in _years(root):
        silver = pd.read_parquet(
            silver_path(root, year), columns=["id", WARD_COLUMN, COMMUNITY_AREA_COLUMN]
        )
        ids.update(silver.loc[geography_mask(silver, ward), "id"].astype("string"))
    return ids


def _flag(values: pd.Series) -> pd.Series:
    return values.astype("string").str.lower().isin(["true", "1"]).astype("boolean")


def _states(root: Path, ids: set[str]) -> pd.DataFrame:
    """The published state of each id in `ids` (absent ids are simply missing)."""
    wanted = pa.array(sorted(ids), type=pa.string())
    frames: list[pd.DataFrame] = []
    for year in _years(root):
        silver_file = silver_path(root, year)
        names = set(pq.read_schema(silver_file).names)
        columns = ["id", WARD_COLUMN, COMMUNITY_AREA_COLUMN]
        if SOURCE_STATUS_COLUMN in names:
            columns.append(SOURCE_STATUS_COLUMN)
        silver = (
            ds.dataset(silver_file)
            .to_table(columns=columns, filter=pc.field("id").isin(wanted))
            .to_pandas()
        )
        if silver.empty:
            continue
        if SOURCE_STATUS_COLUMN not in silver.columns:
            silver[SOURCE_STATUS_COLUMN] = SourceStatus.ACTIVE
        bronze = (
            ds.dataset(bronze_path(root, year))
            .to_table(
                columns=["id", "date", "primary_type", "fbi_code", "arrest", "domestic"],
                filter=pc.field("id").isin(wanted),
            )
            .to_pandas()
        )
        frames.append(silver.merge(bronze, on="id", how="left"))
    if not frames:
        return pd.DataFrame(columns=["id", *_ATTRIBUTES])
    states = pd.concat(frames, ignore_index=True)
    day = pd.to_datetime(states["date"].astype("string").str.slice(0, 10), errors="coerce")
    out = pd.DataFrame({"id": states["id"].astype("string")})
    out["date"] = day.dt.date
    out["year"] = day.dt.year.astype("Int16")
    out["month"] = day.dt.month.astype("Int8")
    # Same fallbacks as the Gold aggregate, so a cell key is never a missing value.
    out["primary_type"] = (
        states["primary_type"].astype("string").str.strip().str.upper().fillna("UNKNOWN")
    )
    out["fbi_code"] = states["fbi_code"].astype("string").str.strip().str.upper().fillna("UNKNOWN")
    out["arrest"] = _flag(states["arrest"])
    out["domestic"] = _flag(states["domestic"])
    out["ward"] = states[WARD_COLUMN].astype("string").str.strip().str.lstrip("0")
    out["community_area"] = (
        states[COMMUNITY_AREA_COLUMN].astype("string").str.strip().str.lstrip("0")
    )
    out["source_status"] = states[SOURCE_STATUS_COLUMN].astype("string")
    if out["id"].duplicated().any():
        raise RevisionBuildError(f"{root}: an incident id appears in two partitions.")
    return out


_MISSING = "\0missing"


def _differs(old: pd.Series, new: pd.Series) -> pd.Series:
    """Element-wise inequality where two missing values count as equal."""
    return (old.astype("string").fillna(_MISSING) != new.astype("string").fillna(_MISSING)).astype(
        bool
    )


def build_events(prior: pd.DataFrame, current: pd.DataFrame) -> pd.DataFrame:
    """Pure function: one row per id whose published state differs. Exposed for tests."""
    merged = (
        prior.add_prefix("old_")
        .rename(columns={"old_id": "id"})
        .merge(current.add_prefix("new_").rename(columns={"new_id": "id"}), on="id", how="outer")
    )
    # Every published state carries a source_status, so its absence means the id is absent.
    merged["exists_prior"] = merged["old_source_status"].notna()
    merged["exists_current"] = merged["new_source_status"].notna()

    removed_old = merged["old_source_status"] == SourceStatus.REMOVED
    removed_new = merged["new_source_status"] == SourceStatus.REMOVED
    both = merged["exists_prior"] & merged["exists_current"]

    merged["added"] = ~merged["exists_prior"] & merged["exists_current"]
    merged["removed"] = merged["exists_prior"] & (
        ~merged["exists_current"] | (removed_new.fillna(False) & ~removed_old.fillna(False))
    )
    merged["restored"] = both & removed_old.fillna(False) & ~removed_new.fillna(False)
    merged["reclassified"] = both & (
        _differs(merged["old_primary_type"], merged["new_primary_type"])
        | _differs(merged["old_fbi_code"], merged["new_fbi_code"])
    )
    merged["date_changed"] = both & _differs(merged["old_date"], merged["new_date"])
    merged["geography_changed"] = both & (
        _differs(merged["old_ward"], merged["new_ward"])
        | _differs(merged["old_community_area"], merged["new_community_area"])
    )
    merged["arrest_changed"] = both & _differs(merged["old_arrest"], merged["new_arrest"])
    merged["domestic_changed"] = both & _differs(merged["old_domestic"], merged["new_domestic"])

    changed = merged[REASONS].any(axis=1)
    columns = ["id", "exists_prior", "exists_current"]
    for attribute in _ATTRIBUTES:
        columns += [f"old_{attribute}", f"new_{attribute}"]
    return merged.loc[changed, [*columns, *REASONS]].reset_index(drop=True)


def _in_geography(frame: pd.DataFrame, prefix: str, geography: ProductGeography) -> pd.Series:
    view = pd.DataFrame(
        {
            WARD_COLUMN: frame[f"{prefix}ward"],
            COMMUNITY_AREA_COLUMN: frame[f"{prefix}community_area"],
        }
    )
    counted = frame[f"{prefix}date"].notna() & (
        frame[f"{prefix}source_status"].astype("string") != SourceStatus.REMOVED
    ).fillna(False)
    return geography_mask(view, geography).fillna(False) & counted


def _cells(states: pd.DataFrame, geography: ProductGeography) -> pd.Series:
    inside = states[_in_geography(states, "", geography)]
    return inside.groupby(["year", "month", "primary_type"], dropna=False).size()


def check_cell_invariant(
    prior: pd.DataFrame,
    current: pd.DataFrame,
    events: pd.DataFrame,
    geographies: list[ProductGeography],
) -> tuple[int, list[str]]:
    """current − prior = entries − exits for every (geography, year, month, type) cell."""
    failures: list[str] = []
    checked = 0
    for geography in geographies:
        before = _cells(prior, geography)
        after = _cells(current, geography)
        old_in = _in_geography(events, "old_", geography)
        new_in = _in_geography(events, "new_", geography)
        keys = ["year", "month", "primary_type"]
        old_key = events[[f"old_{k}" for k in keys]].set_axis(keys, axis=1)
        new_key = events[[f"new_{k}" for k in keys]].set_axis(keys, axis=1)
        same_cell = (old_key.astype("string") == new_key.astype("string")).fillna(False).all(axis=1)
        entries = new_key[new_in & ~(old_in & same_cell)].groupby(keys, dropna=False).size()
        exits = old_key[old_in & ~(new_in & same_cell)].groupby(keys, dropna=False).size()
        index = before.index.union(after.index).union(entries.index).union(exits.index)
        for cell in index:
            checked += 1
            delta = int(after.get(cell, 0)) - int(before.get(cell, 0))
            flow = int(entries.get(cell, 0)) - int(exits.get(cell, 0))
            if delta != flow:
                failures.append(
                    f"{geography.geography_id} {cell}: Δ {delta} ≠ entries−exits {flow}"
                )
    return checked, failures


def build_revision_events(prior_root: Path, current_root: Path) -> RevisionProof:
    """Compare two release roots and publish the events into the current root's Gold."""
    try:
        prior_release = read_release_manifest(prior_root)
        current_release = read_release_manifest(current_root)
    except ReleaseManifestError as exc:
        raise RevisionBuildError(str(exc)) from exc
    if prior_release.release_id == current_release.release_id:
        raise RevisionBuildError("Both roots carry the same release id; nothing to compare.")

    geographies = built_geographies()
    ward = _ward(geographies)
    ids = _ward_ids(prior_root, ward) | _ward_ids(current_root, ward)
    prior = _states(prior_root, ids)
    current = _states(current_root, ids)
    events = build_events(prior, current)
    events.insert(1, "prior_release_id", prior_release.release_id)
    events.insert(2, "current_release_id", current_release.release_id)

    proof = RevisionProof(
        prior_release_id=prior_release.release_id,
        current_release_id=current_release.release_id,
        built_at=datetime.now(UTC).isoformat(timespec="seconds"),
        events=len(events),
        ids_compared=len(ids),
        cells_checked=0,
    )
    proof.cells_checked, proof.failures = check_cell_invariant(prior, current, events, geographies)

    target = revision_dir(current_root, prior_release.release_id, current_release.release_id)
    target.mkdir(parents=True, exist_ok=True)
    if not proof.failures:
        temp = target / (EVENTS_FILENAME + ".tmp")
        events.to_parquet(temp, index=False)
        temp.replace(target / EVENTS_FILENAME)
        proof.status = BUILD_PASS
    (target / PROOF_FILENAME).write_text(
        json.dumps(proof.as_dict(), indent=2, sort_keys=True) + "\n", "utf-8"
    )
    if proof.failures:
        raise RevisionBuildError("; ".join(proof.failures[:20]))
    return proof


def latest_revision(
    current_root: Path, current_id: str
) -> tuple[RevisionProof, pd.DataFrame] | None:
    """The newest PASSing comparison into this release, or None when none was built."""
    folder = gold_dir(current_root) / REVISIONS_DIR
    if not folder.is_dir():
        return None
    candidates: list[tuple[str, Path]] = []
    for path in folder.iterdir():
        proof_file = path / PROOF_FILENAME
        if not path.is_dir() or not proof_file.exists():
            continue
        proof = json.loads(proof_file.read_text("utf-8"))
        if proof.get("status") == BUILD_PASS and proof.get("current_release_id") == current_id:
            candidates.append((str(proof["prior_release_id"]), path))
    if not candidates:
        return None
    _, path = max(candidates)
    proof = RevisionProof(**json.loads((path / PROOF_FILENAME).read_text("utf-8")))
    events = pd.read_parquet(path / EVENTS_FILENAME)
    for prefix in ("old_", "new_"):
        events[f"{prefix}date"] = pd.to_datetime(events[f"{prefix}date"]).dt.date
    return proof, events


def in_window(
    events: pd.DataFrame, prefix: str, geography: ProductGeography, start: Any, end: Any
) -> pd.Series:
    """Event rows whose `prefix` state is counted in the geography between start and end."""
    day = events[f"{prefix}date"]
    within = (day.notna() & (day >= start) & (day <= end)).fillna(False).astype(bool)
    inside: pd.Series = _in_geography(events, prefix, geography) & within
    return inside
