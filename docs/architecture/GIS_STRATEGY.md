# GIS Strategy

## Scope

This project reports on **Bronzeville and Woodlawn only**. No other neighborhood is
published. City-wide data is used only to compute comparison baselines.

## The core problem

**Woodlawn** corresponds to an official City of Chicago community area (Community Area 42)
and may use that official polygon directly.

**Bronzeville does not.** Bronzeville is a historically and culturally defined
neighborhood that does not map to one official community area. It is commonly associated
with parts of Douglas and Grand Boulevard, and — depending on who is asked — Oakland,
Fuller Park, or Washington Park in whole or in part. There is no single official polygon
that is simply "Bronzeville."

## Rules

**Bronzeville requires an approved custom GeoJSON definition.** The boundary must be
written down, reviewed, approved, versioned, and stored in `config/neighborhoods/`. Its
provenance and approval date are published alongside any Bronzeville figure.

**Do not substitute a proxy.** Ward, police beat, police district, ZIP code, and any single
community area are all **prohibited** as stand-ins for the Bronzeville boundary. Each is
either drawn for a different purpose, redrawn over time (wards, beats), or simply wrong
(one community area). A convenient proxy would silently misstate what residents are being
told about their own neighborhood.

**Assignment is point-in-polygon.** A record is assigned to a neighborhood by testing its
coordinates against the approved polygon. Nothing else counts as an exact assignment.

**Records without coordinates stay in the raw data.** They are preserved in Bronze and
Silver, counted in totals where totals are appropriate, and **excluded from exact spatial
analysis**. They may only be resolved into a neighborhood if another reliable method is
established and documented; until then they remain unassigned. Every geography-dependent
figure discloses how many records were excluded for this reason.

## Boundary versioning

Changing the Bronzeville polygon changes every historical number derived from it. The
boundary is therefore versioned, and published figures record which version produced them.
A boundary change is a documented event, not a silent edit.

## Boundary vintage — current boundaries are not historical boundaries

Boundaries move. Wards were redrawn for 2023; police beats and districts were redrawn
effective 2012-12-19; census tracts are 2010 vintage. The project currently assigns **every**
incident, back to 2006, against **current** boundaries.

**Assigning a 2006 incident to a 2023 ward tells you which ward that location is in today —
not which ward it was in at the time.** That is not historical-boundary assignment, and it
must never be presented as such. A ward-level trend spanning a redistricting is comparing
two different areas.

Community areas are the stable exception, which is one more reason Woodlawn's official
polygon is trustworthy for long time series and ward figures are not.

Every enriched record therefore carries a `boundary_vintage` field recording which vintage
produced its assignment, and every boundary set is versioned under
`data/reference/chicago/<version>/`.

## Coordinate systems

- **EPSG:4326** — public interchange. Every stored GeoJSON and every Silver geometry.
- **EPSG:26971** (NAD83 / Illinois East, metres) — all area, distance, and overlap work.

Area is never computed in latitude/longitude degrees. A degree is not a unit of length, so a
"square degree" is not an area.

## Status

| Item | Status |
| --- | --- |
| Official boundary layers downloaded and versioned | **Built** — 7 layers |
| Geometry validation (CRS, repair, duplicates, overlaps, area QA) | **Built** |
| Silver `geography_dimension` / `neighborhood_boundaries` | **Built** |
| Woodlawn official community-area polygon ingested | **Built** — active |
| Point-in-polygon assignment | **Built** — 2024 enriched |
| Bronzeville custom GeoJSON drafted | **Not drafted** |
| Bronzeville boundary approved | **Not approved — assignment blocked** |
| `config/neighborhoods/neighborhoods.yml` | **Built** |
| `config/neighborhoods/bronzeville.geojson` | **Absent by design** — documented expected path |

While Bronzeville is blocked, `neighborhood_bronzeville` is **null** on every record. Null
means "not yet defined", never "not in Bronzeville" — collapsing the two would publish a
false negative for every resident of the neighborhood.

Geography work is **blocked** on the Bronzeville boundary being defined and approved. See
[ADR-0004](ADR/ADR-0004-neighborhood-boundary-strategy.md).
