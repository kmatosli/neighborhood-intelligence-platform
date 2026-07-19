"""Official boundary sources.

Every dataset ID below was confirmed against the City of Chicago Data Portal catalog, not
recalled from memory. Confirmed 2026-07-11.

    community_areas    igwz-8jzy  Boundaries - Community Areas            updated 2025-04-22
    wards_current      p293-wvbd  Boundaries - Wards (2023-)              updated 2022-06-15
    police_beats       aerh-rz74  Boundaries - Police Beats (current)     updated 2013-02-13
    police_districts   fthy-xz3r  Boundaries - Police Districts (current) updated 2013-02-13
    census_tracts      5jrd-6zik  Boundaries - Census Tracts - 2010       updated 2013-05-23
    zip_codes          unjd-c2ca  Boundaries - ZIP Codes                  updated 2025-04-28
    census_block_groups           US Census TIGER/Line 2020, Illinois (state file, 17)

VINTAGE WARNING. These are *current* boundaries. Wards were redrawn for 2023; police beats
and districts were redrawn effective 2012-12-19; census tracts are 2010 vintage. Assigning a
2006 incident to a 2023 ward tells you which ward that location is in **today**, not which
ward it was in at the time. That is not historical-boundary assignment and must never be
presented as such. Community-area boundaries are the stable exception.
"""

from __future__ import annotations

from bw_observatory.geography.models import BoundarySource

CHICAGO_DOMAIN = "data.cityofchicago.org"


def _portal_url(dataset_id: str) -> str:
    return f"https://{CHICAGO_DOMAIN}/resource/{dataset_id}.geojson"


COMMUNITY_AREAS = BoundarySource(
    key="community_areas",
    dataset_id="igwz-8jzy",
    dataset_name="Boundaries - Community Areas",
    geography_type="community_area",
    source_url=_portal_url("igwz-8jzy"),
    id_field_candidates=("area_numbe", "area_num_1"),
    name_field_candidates=("community",),
    vintage_start="1920",
    role="primary",
    notes="Official 77 community areas. Stable. Woodlawn is CA 42.",
)

WARDS_CURRENT = BoundarySource(
    key="wards_current",
    dataset_id="p293-wvbd",
    dataset_name="Boundaries - Wards (2023-)",
    geography_type="ward",
    source_url=_portal_url("p293-wvbd"),
    id_field_candidates=("ward", "ward_id"),
    name_field_candidates=("ward",),
    vintage_start="2023",
    role="political",
    notes=(
        "Political and voting geography ONLY. Wards 3 and 20 are accountability layers and "
        "are never a substitute for the Bronzeville or Woodlawn boundary."
    ),
)

# The map-type boundary datasets (aerh-rz74 beats, fthy-xz3r districts, 5jrd-6zik tracts)
# serve no features: their /resource endpoint returns rows with no geometry, and the
# geospatial export returns an empty body. The tabular datasets below are the official
# equivalents on the same portal, and they do carry geometry. Confirmed 2026-07-11.
POLICE_BEATS = BoundarySource(
    key="police_beats",
    dataset_id="n9it-hstw",
    dataset_name="PoliceBeatDec2012 (police beat boundaries, effective 2012-12-19)",
    geography_type="police_beat",
    source_url=_portal_url("n9it-hstw"),
    id_field_candidates=("beat_num", "beat"),
    name_field_candidates=("beat_num",),
    vintage_start="2012-12-19",
    role="primary",
    notes="Tabular equivalent of the map-type layer aerh-rz74, which serves no geometry.",
)

POLICE_DISTRICTS = BoundarySource(
    key="police_districts",
    dataset_id="derived:n9it-hstw",
    dataset_name="Police Districts (dissolved from police beats)",
    geography_type="police_district",
    source_url=_portal_url("n9it-hstw"),
    id_field_candidates=("dist_num", "district"),
    name_field_candidates=("dist_num",),
    vintage_start="2012-12-19",
    role="derived",
    notes=(
        "DERIVED, not downloaded. The district boundary dataset serves no geometry, so "
        "districts are dissolved from the beat layer on the beats' own `district` field. "
        "Beats nest exactly within districts by construction (beat 1713 is in district 17), "
        "so this is an exact union, not an approximation. Provenance is recorded as derived."
    ),
)

CENSUS_TRACTS = BoundarySource(
    key="census_tracts",
    dataset_id="4hp8-2i8z",
    dataset_name="Census_Tracts (2010 vintage)",
    geography_type="census_tract",
    source_url=_portal_url("4hp8-2i8z"),
    id_field_candidates=("census_t_1", "census_tra"),
    name_field_candidates=("census_tra",),
    vintage_start="2010",
    role="primary",
    notes="Tabular equivalent of the map-type layer 5jrd-6zik, which serves no geometry.",
)

ZIP_CODES = BoundarySource(
    key="zip_codes",
    dataset_id="unjd-c2ca",
    dataset_name="Boundaries - ZIP Codes",
    geography_type="zip_code",
    source_url=_portal_url("unjd-c2ca"),
    id_field_candidates=("zip",),
    name_field_candidates=("zip",),
    vintage_start="current",
    role="secondary",
    notes="SECONDARY REFERENCE ONLY. A ZIP code is postal delivery geography, never a "
    "neighborhood definition.",
)

CENSUS_BLOCK_GROUPS = BoundarySource(
    key="census_block_groups",
    dataset_id="tiger-2020-bg-17",
    dataset_name="US Census TIGER/Line 2020 — Block Groups, Illinois",
    geography_type="census_block_group",
    source_url="https://www2.census.gov/geo/tiger/TIGER2020/BG/tl_2020_17_bg.zip",
    id_field_candidates=("GEOID", "geoid"),
    name_field_candidates=("NAMELSAD", "namelsad"),
    vintage_start="2020",
    role="primary",
    notes=(
        "Not published on the Chicago portal; taken from the authoritative Census source. "
        "2020 vintage, which does NOT match the 2010 vintage of the tract layer above."
    ),
)

BOUNDARY_SOURCES: tuple[BoundarySource, ...] = (
    COMMUNITY_AREAS,
    WARDS_CURRENT,
    POLICE_BEATS,
    POLICE_DISTRICTS,
    CENSUS_TRACTS,
    CENSUS_BLOCK_GROUPS,
    ZIP_CODES,
)

# Cook County, Illinois — used to clip the statewide TIGER block-group file.
ILLINOIS_STATE_FIPS = "17"
COOK_COUNTY_FIPS = "031"


def source_by_key(key: str) -> BoundarySource:
    for source in BOUNDARY_SOURCES:
        if source.key == key:
            return source
    raise KeyError(f"Unknown boundary source: {key}")
