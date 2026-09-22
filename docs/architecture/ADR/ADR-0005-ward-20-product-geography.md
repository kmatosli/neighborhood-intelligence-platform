# ADR-0005 — Ward 20 is the product geography

**Status.** Accepted (product decision by the owner, 2026-09-12; work package V2-002)
**Date.** 2026-09-12
**Supersedes.** The Bronzeville/Woodlawn product scope in ADR-0004, `CLAUDE.md` §1 and §10
(as written before V2-002), `docs/product/PRD.md`, and the V1 README. ADR-0004 stays on file
as the history of the Bronzeville boundary question; it no longer describes the product.

## Decision

1. The application is exclusively a **Ward 20, Chicago** neighborhood intelligence platform.
   Ward 20 overall is the default and primary geography.
2. Residents can also select the **portion within Ward 20** of Woodlawn, Washington Park,
   Englewood, Fuller Park and New City (official community areas clipped to the ward).
   Back of the Yards is listed but unavailable until a documented neighborhood boundary is
   validated; it is represented today through New City.
3. **Bronzeville is not a product geography.** It is removed from public identity, copy, and
   application geography logic. Source data and pipeline history that mention it are not
   rewritten.
4. Geography is a canonical, URL-borne context (`?geo=`) alongside year (`?year=`), with one
   authority on each side: `config/geographies.yml` + `presentation/geography.py` on the API,
   `useGeography()` in the web app.
5. The public working identity is **"Ward 20 Neighborhood Intelligence"** until a final
   product name is chosen. Lovable-generated metadata and branding are removed. The
   repository folder and Python package keep their historical names to avoid deployment
   and Git risk.

## Why

- Ward 20 is the geography that maps to an accountable office; the platform's questions
  ("who is responsible, what can residents ask") are answerable at the ward.
- The existing Silver layer already places every record in a 2023 ward and a community area
  by point-in-polygon, so the change needs no re-enrichment and no new data.
- A whole-community-area figure labelled as a Ward 20 neighborhood would be wrong for every
  area that straddles the ward line (Woodlawn is only half inside). Clipping to the ward
  keeps every published number inside the analytical universe.

## Consequences

- The `woodlawn` geography id now means *Woodlawn within Ward 20* (2,960 reported incidents
  in 2025), not the whole community area (3,847). Older smoke-test figures in `CLAUDE.md`
  are superseded.
- `/api/v1/{overview,pulse,incidents}/{geography_id}` accept `ward20` and the area ids;
  unknown ids (including `bronzeville`) are `404 Unknown geography`; pending ids are `404`
  with the reason.
- The 2023 ward map is applied to all years; this is disclosed on every page. Pre-2023 ward
  maps are a possible future enhancement, not a substitute.
- See `docs/methodology/GEOGRAPHY.md` for sources, vintages and the area table.
