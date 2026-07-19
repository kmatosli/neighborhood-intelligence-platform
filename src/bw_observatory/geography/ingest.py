"""Download official boundary layers into versioned reference storage.

Layout:

    data/reference/chicago/<version>/
        community_areas.geojson
        wards_current.geojson
        ...
        manifest.parquet

`<version>` is the UTC date of the download. Boundaries change (wards were redrawn for
2023; beats and districts in 2012), so a boundary set is versioned and any figure derived
from it records which version produced it. Overwriting boundaries in place would silently
change every historical number derived from them.

Two download routes, because the portal's map-type datasets do not serve features through
the ordinary GeoJSON endpoint:

1. `/resource/<id>.geojson` — works for tabular geo datasets (community areas, wards, ZIP).
2. `/resource/<id>.json` with a `the_geom` column — the fallback for map-type datasets
   (police beats, police districts, census tracts), assembled into GeoJSON here.

A layer that yields nothing through either route is recorded as `source_unresolved` and
skipped. It is never fabricated or approximated.
"""

from __future__ import annotations

import hashlib
import io
import json
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import httpx
import pandas as pd

from bw_observatory.geography.models import (
    INTERCHANGE_CRS,
    BoundarySource,
    ValidationStatus,
)
from bw_observatory.geography.sources import BOUNDARY_SOURCES, COOK_COUNTY_FIPS
from bw_observatory.logging_config import api_logger, download_logger

MANIFEST_FILENAME = "manifest.parquet"

MANIFEST_COLUMNS = [
    "layer",
    "geography_type",
    "dataset_id",
    "dataset_name",
    "source_url",
    "role",
    "vintage_start",
    "vintage_end",
    "source_updated_at",
    "crs",
    "feature_count",
    "geometry_hash",
    "file_checksum",
    "downloaded_at",
    "version",
    "validation_status",
    "notes",
]

PAGE_LIMIT = 50_000

# Recorded when the source's own update timestamp cannot be established. Distinct from an
# empty string, which would read as "the source has no timestamp".
SOURCE_UPDATED_UNKNOWN = "UNKNOWN"


class GeographyDownloadError(RuntimeError):
    """A boundary layer could not be retrieved from its official source."""


def default_version() -> str:
    return datetime.now(UTC).date().isoformat()


def version_dir(reference_dir: Path, version: str) -> Path:
    return reference_dir / "chicago" / version


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _fetch(client: httpx.Client, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
    api_logger().info("GET %s params=%s", url, params or {})
    response = client.get(url, params=params)
    response.raise_for_status()
    return response


def _features_from_geojson(client: httpx.Client, source: BoundarySource) -> list[dict[str, Any]]:
    response = _fetch(client, source.source_url, {"$limit": PAGE_LIMIT})
    payload = response.json()
    features = payload.get("features", []) if isinstance(payload, dict) else []
    return [f for f in features if f.get("geometry")]


def _features_from_rows(client: httpx.Client, source: BoundarySource) -> list[dict[str, Any]]:
    """Fallback: build features from a tabular row set carrying a `the_geom` column."""
    url = source.source_url.replace(".geojson", ".json")
    rows = _fetch(client, url, {"$limit": PAGE_LIMIT}).json()
    if not isinstance(rows, list):
        return []

    features: list[dict[str, Any]] = []
    for row in rows:
        geometry = row.get("the_geom")
        if not geometry:
            continue
        properties = {k: v for k, v in row.items() if k != "the_geom"}
        features.append({"type": "Feature", "geometry": geometry, "properties": properties})
    return features


def fetch_layer(client: httpx.Client, source: BoundarySource) -> list[dict[str, Any]]:
    """Retrieve one layer's features, trying the GeoJSON route then the tabular route."""
    if source.key == "census_block_groups":
        return _fetch_block_groups(client, source)
    if source.key == "police_districts":
        return _derive_districts_from_beats(client, source)

    features = _features_from_geojson(client, source)
    if features:
        return features

    download_logger().info(
        "%s: GeoJSON endpoint returned no geometry; falling back to the tabular route.",
        source.key,
    )
    return _features_from_rows(client, source)


def _derive_districts_from_beats(
    client: httpx.Client, source: BoundarySource
) -> list[dict[str, Any]]:
    """Dissolve the beat layer into districts on the beats' own `district` field.

    The district boundary dataset serves no geometry. Beats nest exactly within districts by
    construction, so the union of a district's beats *is* that district — an exact
    derivation, not an approximation. The manifest records it as `role=derived`.
    """
    from bw_observatory.geography.sources import POLICE_BEATS

    beats = _features_from_geojson(client, POLICE_BEATS)
    if not beats:
        return []

    frame = gpd.GeoDataFrame.from_features(beats, crs=INTERCHANGE_CRS)
    if "district" not in frame.columns:
        download_logger().error(
            "police_districts: the beat layer has no `district` field; cannot derive."
        )
        return []

    frame["dist_num"] = frame["district"].astype(str).str.lstrip("0").str.zfill(3)
    dissolved = frame.dissolve(by="dist_num", as_index=False)[["dist_num", "geometry"]]

    payload: dict[str, Any] = json.loads(dissolved.to_json())
    features: list[dict[str, Any]] = payload["features"]
    return features


def _fetch_block_groups(client: httpx.Client, source: BoundarySource) -> list[dict[str, Any]]:
    """TIGER ships a statewide shapefile in a zip; keep only Cook County."""
    response = _fetch(client, source.source_url)

    with tempfile.TemporaryDirectory() as workspace:
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            archive.extractall(workspace)
        shapefiles = sorted(Path(workspace).glob("*.shp"))
        if not shapefiles:
            return []
        frame = gpd.read_file(shapefiles[0], engine="pyogrio")

    if "COUNTYFP" in frame.columns:
        frame = frame[frame["COUNTYFP"] == COOK_COUNTY_FIPS]

    frame = frame.to_crs(INTERCHANGE_CRS)
    payload: dict[str, Any] = json.loads(frame.to_json())
    features: list[dict[str, Any]] = payload["features"]
    return features


def _source_updated_at(client: httpx.Client, source: BoundarySource) -> str:
    """Portal metadata timestamp. TIGER files carry their vintage in the path instead.

    When the timestamp cannot be established it is recorded as `UNKNOWN`, never as an empty
    string. An empty field reads as "the source has no timestamp"; `UNKNOWN` says we failed
    to find out, which is a different claim and is the honest one.
    """
    if source.key == "census_block_groups":
        return source.vintage_start

    # A derived layer carries no dataset of its own; ask the dataset it was derived from.
    dataset_id = source.dataset_id.removeprefix("derived:")

    url = f"https://data.cityofchicago.org/api/views/{dataset_id}"
    try:
        metadata = _fetch(client, url).json()
    except (httpx.HTTPError, ValueError) as exc:
        api_logger().error(
            "%s (%s): could not read the source metadata timestamp: %s. Recording %s.",
            source.key,
            dataset_id,
            exc,
            SOURCE_UPDATED_UNKNOWN,
        )
        return SOURCE_UPDATED_UNKNOWN

    raw = metadata.get("rowsUpdatedAt")
    if isinstance(raw, int):
        return datetime.fromtimestamp(raw, tz=UTC).isoformat()

    api_logger().error(
        "%s (%s): source metadata has no usable `rowsUpdatedAt` (got %r). Recording %s.",
        source.key,
        dataset_id,
        raw,
        SOURCE_UPDATED_UNKNOWN,
    )
    return SOURCE_UPDATED_UNKNOWN


def write_layer(
    features: list[dict[str, Any]], source: BoundarySource, target_dir: Path
) -> tuple[Path, str, str]:
    """Write raw GeoJSON verbatim. Returns (path, file checksum, geometry hash)."""
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{source.key}.geojson"

    collection = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": INTERCHANGE_CRS}},
        "features": features,
    }
    payload = json.dumps(collection, sort_keys=True).encode("utf-8")
    path.write_bytes(payload)

    geometry_blob = json.dumps([f.get("geometry") for f in features], sort_keys=True).encode(
        "utf-8"
    )
    return path, _sha256(payload), _sha256(geometry_blob)


def download_boundaries(
    reference_dir: Path,
    *,
    version: str | None = None,
    client: httpx.Client | None = None,
    sources: tuple[BoundarySource, ...] = BOUNDARY_SOURCES,
    force: bool = False,
) -> pd.DataFrame:
    """Download every boundary layer into `data/reference/chicago/<version>/`."""
    resolved_version = version or default_version()
    target = version_dir(reference_dir, resolved_version)
    log = download_logger()

    owns_client = client is None
    active = client or httpx.Client(timeout=180.0, follow_redirects=True)

    previous = read_manifest(reference_dir, resolved_version)

    rows: list[dict[str, Any]] = []
    try:
        for source in sources:
            path = target / f"{source.key}.geojson"
            if path.exists() and not force:
                prior = (
                    previous[previous["layer"] == source.key] if not previous.empty else previous
                )
                if not prior.empty:
                    log.info(
                        "%s already downloaded for version %s; skipping. Use --force to "
                        "re-download.",
                        source.key,
                        resolved_version,
                    )
                    rows.append(dict(prior.iloc[0]))
                    continue
                log.warning(
                    "%s: file exists for version %s but has no manifest row; re-downloading.",
                    source.key,
                    resolved_version,
                )

            downloaded_at = datetime.now(UTC).isoformat()
            try:
                features = fetch_layer(active, source)
            except (httpx.HTTPError, ValueError, zipfile.BadZipFile) as exc:
                log.error("%s: download failed: %s", source.key, exc)
                features = []

            if not features:
                # Recorded, not faked. A layer with no features is unusable, and the
                # manifest must say so rather than leaving a silent gap.
                log.error("%s: no features retrieved; marking source_unresolved.", source.key)
                rows.append(
                    _manifest_row(
                        source,
                        resolved_version,
                        downloaded_at,
                        feature_count=0,
                        file_checksum="",
                        geometry_hash="",
                        source_updated_at=SOURCE_UPDATED_UNKNOWN,
                        status=ValidationStatus.UNRESOLVED,
                    )
                )
                continue

            _, file_checksum, geometry_hash = write_layer(features, source, target)
            log.info("%s: %d features written to %s", source.key, len(features), path)

            rows.append(
                _manifest_row(
                    source,
                    resolved_version,
                    downloaded_at,
                    feature_count=len(features),
                    file_checksum=file_checksum,
                    geometry_hash=geometry_hash,
                    source_updated_at=_source_updated_at(active, source),
                    status=ValidationStatus.VALID,
                )
            )
    finally:
        if owns_client:
            active.close()

    manifest = pd.DataFrame(rows, columns=MANIFEST_COLUMNS)
    target.mkdir(parents=True, exist_ok=True)
    manifest.to_parquet(target / MANIFEST_FILENAME, index=False)
    return manifest


def _manifest_row(
    source: BoundarySource,
    version: str,
    downloaded_at: str,
    *,
    feature_count: int,
    file_checksum: str,
    geometry_hash: str,
    source_updated_at: str,
    status: str,
) -> dict[str, Any]:
    return {
        "layer": source.key,
        "geography_type": source.geography_type,
        "dataset_id": source.dataset_id,
        "dataset_name": source.dataset_name,
        "source_url": source.source_url,
        "role": source.role,
        "vintage_start": source.vintage_start,
        "vintage_end": source.vintage_end,
        "source_updated_at": source_updated_at,
        "crs": INTERCHANGE_CRS,
        "feature_count": feature_count,
        "geometry_hash": geometry_hash,
        "file_checksum": file_checksum,
        "downloaded_at": downloaded_at,
        "version": version,
        "validation_status": status,
        "notes": source.notes,
    }


def read_manifest(reference_dir: Path, version: str) -> pd.DataFrame:
    path = version_dir(reference_dir, version) / MANIFEST_FILENAME
    if not path.exists():
        return pd.DataFrame(columns=MANIFEST_COLUMNS)
    return pd.read_parquet(path)


def latest_version(reference_dir: Path) -> str | None:
    root = reference_dir / "chicago"
    if not root.exists():
        return None
    versions = sorted(p.name for p in root.iterdir() if p.is_dir())
    return versions[-1] if versions else None
