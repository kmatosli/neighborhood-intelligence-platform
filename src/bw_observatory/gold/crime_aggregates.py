"""Gold crime aggregates: daily counts per product geography, with coverage and a build proof.

Contract: `reports/design/CRIME_SPRINT1_FOUNDATION_2026-10-27.md` §1.

    <release_root>/gold/crime/daily_counts.parquet   the one base table
    <release_root>/gold/crime/coverage.parquet       which days the release covers
    <release_root>/gold/crime/_build.json            the proof that makes Gold trustworthy

Gold is a cache with a proof attached, never a second source of truth:

* the builder **fails** unless every year's Gold total reconciles exactly to Silver's
  current-source rows, for Ward 20 and for every validated community-area portion, the
  portions sum to the ward, and the source-removed counts reconcile too;
* membership is the point-in-polygon placement (`geography_mask`), never the city's
  reported ward or community area; only geographies with a validated boundary are built, so
  Bronzeville (unknown) and Back of the Yards (pending) can never appear — not even as zero;
* at request time the API checks only cheap identities (release id, ledger digest, config
  digest, build status). Any disagreement makes the aggregates `aggregates_stale` and no
  figure is served from them (`check_gold`).

Daily, not monthly: like-for-like windows cut on a day (year-to-date through 6 September
against the prior year through 6 September), which monthly totals cannot do without
inventing the partial month. Coverage makes the absence of a row mean zero *only* on a
covered day; a day outside coverage is unknown, never zero.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from bw_observatory.geography.models import SourceStatus
from bw_observatory.presentation.geography import (
    GEOGRAPHY_COLUMNS,
    KIND_AREA_WITHIN_WARD,
    KIND_WARD,
    ProductGeography,
    geography_mask,
    load_geography_registry,
)
from bw_observatory.presentation.measurement import PROVISIONAL_WINDOW_DAYS
from bw_observatory.presentation.overview import (
    SOURCE_STATUS_COLUMN,
    broad_category_of,
    bronze_path,
    silver_path,
)
from bw_observatory.release import (
    ReleaseManifestError,
    config_digests,
    ledger_digest,
    read_release_manifest,
    verify_release_manifest,
)

GOLD_CRIME = Path("gold") / "crime"
DAILY_COUNTS_FILENAME = "daily_counts.parquet"
COVERAGE_FILENAME = "coverage.parquet"
BUILD_FILENAME = "_build.json"
SCHEMA_VERSION = 1
FIRST_YEAR = 2006

BUILD_PASS = "PASS"
BUILD_FAIL = "FAIL"

# Runtime conditions under which no Gold figure may be served.
UNAVAILABLE = "aggregates_unavailable"  # no Gold, or no release identity
STALE = "aggregates_stale"  # Gold exists but no longer describes the inputs beside it

DAILY_SCHEMA = pa.schema(
    [
        ("release_id", pa.string()),
        ("geography_id", pa.string()),
        ("geography_kind", pa.string()),
        ("date", pa.date32()),
        ("year", pa.int16()),
        ("month", pa.int8()),
        ("primary_type", pa.string()),
        ("fbi_code", pa.string()),
        ("broad_category", pa.string()),
        ("count", pa.int32()),
        ("count_source_removed", pa.int32()),
    ]
)

_GROUP = ["geography_id", "geography_kind", "date", "primary_type", "fbi_code"]


class GoldBuildError(RuntimeError):
    """The aggregates could not be proved equal to Silver; nothing was published."""


class GoldUnavailable(RuntimeError):
    """No Gold figure may be served. `condition` is UNAVAILABLE or STALE."""

    def __init__(self, condition: str, reason: str) -> None:
        super().__init__(reason)
        self.condition = condition
        self.reason = reason


@dataclass
class GoldBuild:
    release_id: str
    built_at: str
    builder_commit: str
    input_ledger_sha256: str
    config_sha256: dict[str, str]
    data_through: str | None
    years: list[int]
    geographies: list[str]
    rows: int
    reconciliation: dict[str, dict[str, Any]] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    status: str = BUILD_FAIL
    schema_version: int = SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def gold_dir(data_dir: Path) -> Path:
    return data_dir / GOLD_CRIME


def built_geographies() -> list[ProductGeography]:
    """Ward 20 plus every community-area portion with a validated boundary — nothing else."""
    return [
        g
        for g in load_geography_registry().geographies
        if g.is_available and g.kind in {KIND_WARD, KIND_AREA_WITHIN_WARD}
    ]


def _years(data_dir: Path) -> list[int]:
    silver_dir = silver_path(data_dir, FIRST_YEAR).parent
    return sorted(int(p.stem) for p in silver_dir.glob("*.parquet") if p.stem.isdigit())


def _incident_day(values: pd.Series) -> pd.Series:
    """Chicago-local calendar day of the source timestamp (already local, no zone)."""
    text = values.astype("string").str.slice(0, 10)
    return pd.to_datetime(text, format="%Y-%m-%d", errors="coerce").dt.date


def _year_rows(
    data_dir: Path, year: int, geographies: list[ProductGeography]
) -> tuple[pd.DataFrame, dict[str, dict[str, int]]]:
    """Per-day counts for one Silver partition, plus the Silver-side figures they must equal."""
    silver_file = silver_path(data_dir, year)
    present = set(pq.read_schema(silver_file).names)
    columns = ["id", *GEOGRAPHY_COLUMNS]
    if SOURCE_STATUS_COLUMN in present:
        columns.append(SOURCE_STATUS_COLUMN)
    silver = pd.read_parquet(silver_file, columns=columns)
    if SOURCE_STATUS_COLUMN not in silver.columns:
        silver[SOURCE_STATUS_COLUMN] = SourceStatus.ACTIVE
    removed = silver[SOURCE_STATUS_COLUMN].astype("string") == SourceStatus.REMOVED

    ward = next(g for g in geographies if g.kind == KIND_WARD)
    in_ward = geography_mask(silver, ward)
    ward_rows = silver[in_ward].copy()
    ward_rows["_removed"] = removed[in_ward].to_numpy()

    # Attributes only for the ward's ids: a few thousand rows, not the city's year.
    ids = pa.array(ward_rows["id"].astype("string").tolist(), type=pa.string())
    bronze = (
        ds.dataset(bronze_path(data_dir, year))
        .to_table(
            columns=["id", "date", "primary_type", "fbi_code"],
            filter=pc.field("id").isin(ids),
        )
        .to_pandas()
    )
    joined = ward_rows.merge(bronze, on="id", how="left")
    joined["date"] = _incident_day(joined["date"])
    joined["primary_type"] = joined["primary_type"].astype("string").str.strip().str.upper()
    joined["fbi_code"] = joined["fbi_code"].astype("string").str.strip().str.upper()

    frames: list[pd.DataFrame] = []
    expected: dict[str, dict[str, int]] = {}
    for geography in geographies:
        mask = geography_mask(joined, geography)
        part = joined[mask]
        silver_mask = geography_mask(silver, geography)
        expected[geography.geography_id] = {
            "silver_current": int((silver_mask & ~removed).sum()),
            "silver_removed": int((silver_mask & removed).sum()),
            # A row with no Bronze attributes or no usable date cannot sit on a day. It is
            # counted here so the reconciliation still closes, and reported, never hidden.
            "undated_current": int((part["date"].isna() & ~part["_removed"]).sum()),
            "undated_removed": int((part["date"].isna() & part["_removed"]).sum()),
        }
        dated = part[part["date"].notna()].copy()
        dated["geography_id"] = geography.geography_id
        dated["geography_kind"] = geography.kind
        dated["primary_type"] = dated["primary_type"].fillna("UNKNOWN")
        dated["fbi_code"] = dated["fbi_code"].fillna("UNKNOWN")
        dated["count"] = (~dated["_removed"]).astype("int32")
        dated["count_source_removed"] = dated["_removed"].astype("int32")
        frames.append(dated[[*_GROUP, "count", "count_source_removed"]])

    combined = pd.concat(frames, ignore_index=True)
    grouped = combined.groupby(_GROUP, as_index=False, dropna=False)[
        ["count", "count_source_removed"]
    ].sum()
    return grouped, expected


def _coverage(first_year: int, data_through: date) -> pd.DataFrame:
    days = pd.date_range(date(first_year, 1, 1), data_through, freq="D").date
    frame = pd.DataFrame({"date": days})
    stamps = pd.to_datetime(frame["date"])
    frame["year"] = stamps.dt.year.astype("int16")
    frame["month"] = stamps.dt.month.astype("int8")
    month_end = (stamps + pd.offsets.MonthEnd(0)).dt.date
    frame["month_complete"] = month_end <= data_through
    frame["provisional"] = [(data_through - d).days <= PROVISIONAL_WINDOW_DAYS for d in days]
    return frame


def _write_parquet(frame: pd.DataFrame, target: Path, schema: pa.Schema | None = None) -> None:
    temp = target.with_suffix(".parquet.tmp")
    table = pa.Table.from_pandas(frame, schema=schema, preserve_index=False)
    pq.write_table(table, temp)
    temp.replace(target)


def _write_build(target_dir: Path, build: GoldBuild) -> None:
    target = target_dir / BUILD_FILENAME
    temp = target.with_suffix(".json.tmp")
    temp.write_text(json.dumps(build.as_dict(), indent=2, sort_keys=True) + "\n", "utf-8")
    temp.replace(target)


def build_crime_gold(data_dir: Path, config_dir: Path, commit: str = "unknown") -> GoldBuild:
    """Build, prove and publish Gold for one release root. Raises GoldBuildError on any gap.

    The release must already carry `release.json`; Gold takes its identity from it. On
    failure `_build.json` records FAIL and the reasons (so the API refuses the old files too)
    and no new aggregate replaces the previous one.
    """
    try:
        release = read_release_manifest(data_dir)
    except ReleaseManifestError as exc:
        raise GoldBuildError(str(exc)) from exc

    geographies = built_geographies()
    years = _years(data_dir)
    if not years:
        raise GoldBuildError(f"No Silver crime partitions under {data_dir}.")
    target_dir = gold_dir(data_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    build = GoldBuild(
        release_id=release.release_id,
        built_at=datetime.now(UTC).isoformat(timespec="seconds"),
        builder_commit=commit,
        input_ledger_sha256=ledger_digest(data_dir),
        config_sha256=config_digests(config_dir),
        data_through=release.data_through,
        years=years,
        geographies=[g.geography_id for g in geographies],
        rows=0,
    )
    # Full verification, not just the ledger: a Silver rewrite that touches no ledger file (a
    # whole-year re-enrichment) would otherwise yield Gold that reconciles to the new Silver
    # while release.json still describes the old one, and the runtime check could never tell.
    for problem in verify_release_manifest(data_dir, config_dir):
        build.failures.append(
            f"release.json does not describe this root ({problem}) Re-cut the release "
            "identity before building Gold."
        )
    # Coverage is one continuous run of days, so every year inside it must have a partition,
    # and it must not run past the last one: a missing year would read as a complete zero.
    gaps = sorted(set(range(years[0], years[-1] + 1)) - set(years))
    if gaps:
        build.failures.append(f"Silver crime partitions are missing for {gaps}.")
    if release.data_through is not None and int(release.data_through[:4]) != years[-1]:
        build.failures.append(
            f"release.json data_through {release.data_through} is not in the last Silver "
            f"year ({years[-1]})."
        )
    # Config is code (it ships in Git), not release data: release.json records the config of
    # the cut as provenance, and Gold records the config it was built with. The runtime check
    # compares the live config with Gold's record, so a config change makes Gold stale until it
    # is rebuilt, without rewriting the identity of an immutable release.

    frames: list[pd.DataFrame] = []
    for year in years:
        grouped, expected = _year_rows(data_dir, year, geographies)
        frames.append(grouped)
        checks: dict[str, Any] = {}
        for geography in geographies:
            gid = geography.geography_id
            mine = grouped[grouped["geography_id"] == gid]
            exp = expected[gid]
            gold_current = int(mine["count"].sum()) + exp["undated_current"]
            gold_removed = int(mine["count_source_removed"].sum()) + exp["undated_removed"]
            ok = gold_current == exp["silver_current"] and gold_removed == exp["silver_removed"]
            checks[gid] = {**exp, "gold_current": gold_current, "gold_removed": gold_removed}
            checks[gid]["pass"] = ok
            if not ok:
                build.failures.append(
                    f"{year} {gid}: Gold {gold_current} current / {gold_removed} removed vs "
                    f"Silver {exp['silver_current']} / {exp['silver_removed']}."
                )
        ward_id = next(g.geography_id for g in geographies if g.kind == KIND_WARD)
        portion_sum = sum(
            expected[g.geography_id]["silver_current"]
            for g in geographies
            if g.kind == KIND_AREA_WITHIN_WARD
        )
        ward_total = expected[ward_id]["silver_current"]
        checks["portions_sum_to_ward"] = {
            "ward": ward_total,
            "portions": portion_sum,
            "pass": portion_sum == ward_total,
        }
        if portion_sum != ward_total:
            build.failures.append(
                f"{year}: the validated portions hold {portion_sum} current rows but Ward 20 "
                f"holds {ward_total}; some ward rows lie in no validated portion."
            )
        build.reconciliation[str(year)] = checks

    daily = pd.concat(frames, ignore_index=True)
    allowed = set(build.geographies)
    stray = set(daily["geography_id"]) - allowed
    if stray:  # pragma: no cover - defensive: only built geographies are ever grouped
        build.failures.append(f"Unsupported geographies in the aggregate: {sorted(stray)}.")

    if release.data_through is None:
        build.failures.append("release.json records no data_through; coverage is undefined.")

    if build.failures:
        build.status = BUILD_FAIL
        _write_build(target_dir, build)
        raise GoldBuildError("; ".join(build.failures))

    stamps = pd.to_datetime(daily["date"])
    daily["year"] = stamps.dt.year.astype("int16")
    daily["month"] = stamps.dt.month.astype("int8")
    daily["broad_category"] = daily["primary_type"].map(broad_category_of)
    daily["release_id"] = release.release_id
    daily = daily.sort_values(["geography_id", "date", "primary_type", "fbi_code"])
    through = date.fromisoformat(str(release.data_through))
    coverage = _coverage(years[0], through)

    _write_parquet(daily[DAILY_SCHEMA.names], target_dir / DAILY_COUNTS_FILENAME, DAILY_SCHEMA)
    _write_parquet(coverage, target_dir / COVERAGE_FILENAME)
    build.rows = len(daily)
    build.status = BUILD_PASS
    _write_build(target_dir, build)  # last, so a crash mid-write leaves no PASS behind
    return build


# -- runtime ---------------------------------------------------------------------------


def read_build(data_dir: Path) -> GoldBuild:
    path = gold_dir(data_dir) / BUILD_FILENAME
    if not path.exists():
        raise GoldUnavailable(UNAVAILABLE, "No Gold crime aggregates in this release.")
    try:
        return GoldBuild(**json.loads(path.read_text("utf-8")))
    except (ValueError, TypeError) as exc:
        raise GoldUnavailable(UNAVAILABLE, f"Gold build record unreadable: {exc}") from exc


def check_gold(data_dir: Path, config_dir: Path) -> GoldBuild:
    """Cheap per-request proof that Gold still describes this release. Raises GoldUnavailable.

    Compares identities only — never re-reads Silver (full checksums belong to release
    verification and deployment acceptance).
    """
    try:
        release = read_release_manifest(data_dir)
    except ReleaseManifestError as exc:
        raise GoldUnavailable(UNAVAILABLE, str(exc)) from exc
    build = read_build(data_dir)
    if build.status != BUILD_PASS:
        raise GoldUnavailable(STALE, "The last Gold build did not pass its reconciliation.")
    if build.release_id != release.release_id:
        raise GoldUnavailable(
            STALE, f"Gold was built for {build.release_id}, not {release.release_id}."
        )
    ledger = ledger_digest(data_dir)
    if ledger != build.input_ledger_sha256 or ledger != release.ledger_sha256:
        raise GoldUnavailable(
            STALE, "The release's data changed after Gold was built (ledger digest differs)."
        )
    if config_digests(config_dir) != build.config_sha256:
        raise GoldUnavailable(STALE, "Category or geography config changed after Gold was built.")
    return build


def load_daily_counts(data_dir: Path, geography_id: str) -> pd.DataFrame:
    """One geography's daily counts (current-source view in `count`)."""
    table = ds.dataset(gold_dir(data_dir) / DAILY_COUNTS_FILENAME).to_table(
        filter=pc.field("geography_id") == geography_id
    )
    frame: pd.DataFrame = table.to_pandas()
    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    return frame


def load_coverage(data_dir: Path) -> pd.DataFrame:
    frame = pd.read_parquet(gold_dir(data_dir) / COVERAGE_FILENAME)
    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    return frame


def covered(coverage: pd.DataFrame, start: date, end: date) -> bool:
    """True only when every day from start through end is inside the release's coverage."""
    if start > end:
        return False
    days = set(coverage["date"])
    current = start
    while current <= end:
        if current not in days:
            return False
        current += timedelta(days=1)
    return True
