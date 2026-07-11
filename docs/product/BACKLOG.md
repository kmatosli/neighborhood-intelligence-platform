# Backlog

Priorities: **P0** blocks the next milestone · **P1** needed for MVP · **P2** valuable, not
blocking.

Items marked ✅ are done. Everything else is not started.

---

## Epic: Crime Data Foundation

| Pri | Item |
| --- | --- |
| ✅ | Chicago Socrata client with retries and typed errors |
| ✅ | Metadata schema validation before extraction |
| ✅ | Record validation split from schema validation |
| ✅ | Coordinates as warnings, not blocking failures |
| **P0** | Historical ingestion, 2006 to present — paged and restartable |
| **P0** | Raw Parquet storage in the Bronze layer, partitioned by refresh run |
| **P0** | Incremental refresh using `updated_on` and `id` |
| **P0** | `data_refresh_run` recording; failed refresh must not erase valid data |
| **P1** | Silver normalization: typing, dedup on `id`, corrections by newest `updated_on` |
| **P1** | Configurable, documented crime groupings |
| P2 | Backfill resumption from a partial run without re-fetching completed windows |

## Epic: Geography

**Blocked** on ADR-0004 approval.

| Pri | Item |
| --- | --- |
| **P0** | Draft the Bronzeville custom GeoJSON boundary with written rationale |
| **P0** | Get the Bronzeville boundary approved, versioned, and stored in `config/neighborhoods/` |
| **P0** | Ingest the official Woodlawn community-area polygon |
| **P0** | Point-in-polygon neighborhood assignment |
| **P1** | Excluded-record accounting surfaced on every spatial figure |
| P2 | Boundary versioning applied to historical figures |

## Epic: Census and Economics

| Pri | Item |
| --- | --- |
| **P1** | Census and ACS ingestion for the two neighborhoods |
| **P1** | Margins of error carried through to any published rate |
| **P1** | Per-capita rate denominators (needed before any "rate" is published) |
| P2 | Business and vacancy context for the Community Change page |

## Epic: Voting Participation

| Pri | Item |
| --- | --- |
| **P1** | Election turnout ingestion |
| **P1** | Precinct-to-neighborhood mapping resolved **per election year** (precincts move) |
| P2 | Turnout trends on the Community Change page |

## Epic: Events and Policy Context

| Pri | Item |
| --- | --- |
| **P1** | Event calendar: COVID periods, holidays, school calendar, sports, weather, neighborhood events |
| **P1** | Policy-event timeline: federal, state, county, city |
| **P1** | Before/during/after windows with alternative explanations shown |
| **P1** | Guardrails so no timing association renders as a causal claim |
| P2 | Weather ingestion at daily granularity |

## Epic: Accountability

| Pri | Item |
| --- | --- |
| **P1** | Responsibility mapping: direct authority, budget authority, coordination influence, no direct control |
| **P1** | `public_commitment` tracking with evidence links and an honest `unclear` status |
| P2 | Commitment status history over time |

## Epic: Beat Meeting Tools

| Pri | Item |
| --- | --- |
| **P1** | Beat Meeting Brief — one printable page with source and refresh date |
| **P1** | "What changed since the last meeting" summary |
| P2 | Commitments-made-here tracking per beat |

## Epic: Public Web Application

| Pri | Item |
| --- | --- |
| **P0** | Read-only API over the Gold layer; **no public refresh endpoint** |
| **P1** | Neighborhood Overview |
| **P1** | Crime Trends |
| **P1** | Map — block level, never exact addresses |
| **P1** | Who Is Responsible |
| **P1** | Data Health — ships with the first public numbers, not after |
| **P1** | Methodology at a 4th–6th grade reading level |
| **P1** | Community Change |
| P2 | Shareable summary cards that keep their citation when screenshotted |
| P2 | Readability check enforced in CI |
