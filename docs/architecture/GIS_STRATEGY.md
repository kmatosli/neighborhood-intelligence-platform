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

## Status

| Item | Status |
| --- | --- |
| Woodlawn official community-area polygon ingested | **Not built** |
| Bronzeville custom GeoJSON drafted | **Not built** |
| Bronzeville boundary approved | **Not approved** |
| Point-in-polygon assignment | **Not built** |
| `config/neighborhoods/` directory | Exists, empty |

Geography work is **blocked** on the Bronzeville boundary being defined and approved. See
[ADR-0004](ADR/ADR-0004-neighborhood-boundary-strategy.md).
