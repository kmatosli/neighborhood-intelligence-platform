"""Describe a Socrata dataset well enough to judge whether it can serve Ward 20 analysis.

Read-only and metadata-scale: one metadata call, one `count(*)`, and — where the dataset has
date-like columns — one min/max aggregate. No rows are downloaded. Used by
`scripts/audit_source_readiness.py` to produce the tables in
docs/data/WARD20_EQUITY_DATA_READINESS.md so the audit can be re-run as sources change.

What "geography ready" means here: a dataset can be clipped to the current Ward 20 footprint
(and to the community-area portions inside it) only if each record carries coordinates. A
`ward` column alone is not enough — the 311 audit showed that field is the ward *at creation
time*, not today's map — and a `community_area` column supports the community-area portion
only when combined with a Ward 20 test, which needs coordinates.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

COORDINATE_FIELDS = {
    "latitude",
    "longitude",
    "location",
    "the_geom",
    "x_coordinate",
    "y_coordinate",
    "lat",
    "lon",
}
WARD_FIELDS = {"ward", "wards"}
COMMUNITY_AREA_FIELDS = {"community_area", "community_areas", "community"}
DATE_TYPES = {"calendar_date", "floating_timestamp", "date"}


@dataclass
class DatasetReadiness:
    domain: str
    dataset_id: str
    name: str = ""
    dataset_type: str = ""
    description: str = ""
    rows_updated_at: str = ""
    row_count: int | None = None
    columns: list[dict[str, str]] = field(default_factory=list)
    has_coordinates: bool = False
    has_ward_field: bool = False
    has_community_area_field: bool = False
    has_geometry: bool = False
    date_columns: list[str] = field(default_factory=list)
    date_range: dict[str, str] = field(default_factory=dict)
    error: str = ""
    retrieved_at: str = ""

    @property
    def ward20_clip_capability(self) -> str:
        """How the dataset could be clipped to the current Ward 20 footprint."""
        if self.has_coordinates:
            return "point-in-polygon on coordinates (current footprint + community-area portions)"
        if self.has_geometry:
            return "polygon intersection with the ward polygon (area-share attribution only)"
        if self.has_ward_field:
            return "ward field only — vintage unknown; not defensible for portions"
        if self.has_community_area_field:
            return "community-area field only — cannot be clipped to the ward"
        return "no geographic field — administrative attribution only"

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["ward20_clip_capability"] = self.ward20_clip_capability
        return payload


def _fetch_json(client: httpx.Client, url: str, params: dict[str, Any] | None = None) -> Any:
    response = client.get(url, params=params)
    response.raise_for_status()
    return response.json()


def describe_dataset(
    dataset_id: str,
    *,
    domain: str = "data.cityofchicago.org",
    client: httpx.Client | None = None,
) -> DatasetReadiness:
    """Metadata, row count and date range for one dataset. Never downloads rows."""
    owns = client is None
    active = client or httpx.Client(timeout=120.0, follow_redirects=True)
    result = DatasetReadiness(
        domain=domain, dataset_id=dataset_id, retrieved_at=datetime.now(UTC).isoformat()
    )
    try:
        meta = _fetch_json(active, f"https://{domain}/api/views/{dataset_id}")
        result.name = str(meta.get("name", ""))
        result.dataset_type = str(meta.get("displayType") or meta.get("viewType") or "")
        result.description = str(meta.get("description") or "")[:600]
        raw_updated = meta.get("rowsUpdatedAt")
        if isinstance(raw_updated, int):
            result.rows_updated_at = datetime.fromtimestamp(raw_updated, tz=UTC).isoformat()

        columns = meta.get("columns") or []
        result.columns = [
            {"field": str(c.get("fieldName", "")), "type": str(c.get("dataTypeName", ""))}
            for c in columns
            if not str(c.get("fieldName", "")).startswith(":@")
        ]
        names = {c["field"].lower() for c in result.columns}
        types = {c["field"].lower(): c["type"] for c in result.columns}
        result.has_coordinates = bool(names & COORDINATE_FIELDS)
        result.has_ward_field = bool(names & WARD_FIELDS)
        result.has_community_area_field = bool(names & COMMUNITY_AREA_FIELDS)
        result.has_geometry = any(
            t in {"multipolygon", "polygon", "point", "line"} for t in types.values()
        )
        result.date_columns = [c["field"] for c in result.columns if c["type"] in DATE_TYPES]

        # Tabular datasets answer aggregate queries; map/blob views do not.
        if result.dataset_type in {"table", "dataset", ""} or meta.get("viewType") == "tabular":
            resource = f"https://{domain}/resource/{dataset_id}.json"
            count = _fetch_json(active, resource, {"$select": "count(*)"})
            if count:
                result.row_count = int(count[0].get("count", 0))
            if result.date_columns:
                first = result.date_columns[0]
                span = _fetch_json(
                    active, resource, {"$select": f"min({first}) as lo, max({first}) as hi"}
                )
                if span:
                    result.date_range = {
                        "column": first,
                        "min": str(span[0].get("lo", "")),
                        "max": str(span[0].get("hi", "")),
                    }
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        result.error = f"{type(exc).__name__}: {exc}"[:300]
    finally:
        if owns:
            active.close()
    return result
