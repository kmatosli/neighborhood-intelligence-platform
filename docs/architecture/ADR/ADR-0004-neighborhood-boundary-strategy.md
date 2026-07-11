# ADR-0004 — Neighborhood boundary strategy

**Status.** Proposed — the Bronzeville boundary is **not yet approved**
**Date.** 2026-07-11

## Context

The project reports on Bronzeville and Woodlawn. Only one of them has an official polygon.

**Woodlawn** corresponds to an official City of Chicago community area and can use that
boundary directly.

**Bronzeville does not exist as one official community area.** It is a historically and
culturally defined neighborhood, commonly associated with parts of Douglas and Grand
Boulevard, and — depending on who is asked — Oakland, Fuller Park, or Washington Park, in
whole or in part. Reasonable residents disagree about its edges.

This is not a technicality. The boundary determines every number the project will publish
about Bronzeville. Choosing it silently would mean deciding, without saying so, whose
neighborhood is being described.

Meanwhile the crime data offers several tempting shortcuts — `ward`, `beat`, `district`,
`community_area` — each of which is already in every record and would take minutes to use.

## Decision

- **Woodlawn** uses the official community-area polygon, ingested from the city.
- **Bronzeville** requires a **custom GeoJSON boundary that is explicitly approved** before
  any Bronzeville figure is published. It is stored in `config/neighborhoods/`, with its
  definition rationale, approver, and approval date recorded.
- **Ward, beat, police district, ZIP code, and any single community area are prohibited as
  substitutes** for the Bronzeville boundary.
- Neighborhood assignment is **point-in-polygon** on record coordinates. No other method
  counts as an exact assignment.
- Records without coordinates remain in the raw and normalized layers, are **excluded from
  exact spatial analysis**, and their excluded count is disclosed on any geography-dependent
  figure.
- The boundary is **versioned**. Published figures record the boundary version that produced
  them.

This ADR stays **Proposed** until the Bronzeville GeoJSON is approved. All geography work is
blocked until then.

## Consequences

- Geography — and therefore the map, neighborhood trends, and most of the MVP — is blocked
  on a decision that is social, not technical. This is the correct place for the project to
  be slow.
- The approved boundary becomes a published, contestable artifact. Residents can see exactly
  what "Bronzeville" means here and argue with it.
- Changing the boundary later changes every historical Bronzeville number. Versioning makes
  that visible instead of silent.
- Some crimes will be unassignable (no coordinates) and permanently absent from
  neighborhood-level counts. Totals and map counts will therefore differ, and that gap must
  be explained wherever both appear.

## Alternatives considered

**Use a single community area (e.g. Douglas or Grand Boulevard) as "Bronzeville."** Fast,
official, and wrong. It would exclude residents who live in Bronzeville and include people
who do not say they do. Prohibited by project rules.

**Use ward boundaries.** Rejected: wards are political districts redrawn every ten years,
so historical trends would silently shift under a redistricting.

**Use police beats or districts.** Rejected: drawn for police deployment, redrawn over time,
and would make "crime in Bronzeville" a circular artifact of how policing is organized.

**Use ZIP codes.** Rejected: postal delivery geography with no relationship to neighborhood
identity.

**Publish Bronzeville figures under multiple candidate boundaries and let the reader
choose.** Genuinely appealing for honesty, and not fully rejected — but deferred. It
multiplies every number by the number of definitions and would make the MVP unreadable.
Revisit once a primary approved boundary exists.
