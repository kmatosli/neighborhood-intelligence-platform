# Geography — Ward 20 product scope

**Status.** In force since V2-002 (2026-09-12); gaps closed and all nine intersecting
community areas exposed in V2-002A (2026-09-13).
Supersedes the Bronzeville/Woodlawn product scope described in older documents; those
documents are retained as history and are not rewritten.

## The rule

The analytical universe of this application is **Ward 20, Chicago**.

```
Chicago
  -> Ward 20                                   (the default, "Ward 20 overall")
      -> neighborhood/area WITHIN Ward 20      (Woodlawn, Washington Park, …)
          -> smaller geography where appropriate (police beat, census tract — later)
```

A statistic shown for a neighborhood is for the **portion of that neighborhood inside
Ward 20** unless explicitly labelled otherwise. Every drilldown means

```
NAMED COMMUNITY AREA  ∩  CURRENT WARD 20 BOUNDARY
```

and **never** the entire Chicago community area. The application says so everywhere the
name appears: the selector reads "Woodlawn (part in Ward 20)", the page heading reads "the
Ward 20 part of Woodlawn", every generated sentence uses that phrase, and every response
carries a `provenance.geography_scope` sentence stating the coverage and the measured size of
the portion.

**"Current Ward 20 footprint."** Ward 20 means the ward as drawn in the 2023 ward map. All
observations, 2006–2026, are examined within the geography that constitutes Ward 20 *today*.
See "Historical ward boundary" below.

## Sources and vintages

| Layer | Source | Dataset | Vintage | Local copy |
|---|---|---|---|---|
| Ward 20 boundary | City of Chicago, *Boundaries - Wards (2023-)* | `p293-wvbd` | 2023 ward map (feature `edit_date` 2022-06-01; source updated 2022-06-15) | `data/reference/chicago/2026-07-12/wards_current.geojson`, downloaded 2026-07-12, validated |
| Community areas | City of Chicago, *Boundaries - Community Areas* | `igwz-8jzy` | 1920 (stable, 77 areas) | `data/reference/chicago/2026-07-12/community_areas.geojson` |
| Police beats | City of Chicago, *PoliceBeatDec2012* | `n9it-hstw` | effective 2012-12-19 | `…/police_beats.geojson` |
| Police districts | derived by dissolving beats | `derived:n9it-hstw` | 2012-12-19 | `…/police_districts.geojson` |
| Census tracts | City of Chicago, *Census Tracts (2010)* | `4hp8-2i8z` | 2010 | `…/census_tracts.geojson` |
| Census block groups | US Census TIGER/Line 2020 | `tiger-2020-bg-17` | 2020 | `…/census_block_groups.geojson` |
| ZIP codes | City of Chicago | `unjd-c2ca` | current | secondary reference only — never an analytical geography |
| Neighborhoods (tourism) | City of Chicago, *Boundaries - Neighborhoods* (Office of Tourism, `Neighborhoods_2012b`) | shapefile `9wp7-iasj` (map view `bbvz-uum9` serves no geometry) | file 2012b; portal updated 2010-12-22 | `…/neighborhoods.geojson`, retrieved 2026-09-13 (V2-002A); **secondary reference only** — the City states these boundaries are approximate and names not official |

The **2023 ward map is applied to every year of incidents, 2006–2026**, including years
before the remap. This keeps one fixed boundary across the series so years are comparable.
It also means figures for older years describe today's Ward 20 lines, not the ward lines in
force at the time. The application says so ("as drawn in the 2023 ward map, applied to every
year shown"). Ward maps in force before 2023 have not been ingested.

## How a record is placed

Every incident is placed **by point-in-polygon** during Silver enrichment
(`src/bw_observatory/geography/assign.py`), which writes, per record:

- `spatial_ward_current` — the 2023 ward containing the incident's published coordinates;
- `spatial_community_area` — the community area containing them;
- `spatial_beat_current`, `spatial_district_current`, `census_tract`, `census_block_group`.

The product filter (`src/bw_observatory/presentation/geography.py`) reads only the two
spatial columns:

- **Ward 20 overall**: `spatial_ward_current == "20"`
- **Area within Ward 20**: `spatial_ward_current == "20" AND spatial_community_area == <id>`

The city's own reported `ward` and `community_area` fields are never used for placement (they
disagree with the polygons on roughly 4% and 1% of records respectively; the disagreement is
counted in `geography_quality.parquet`). A record without usable coordinates is inside
nothing and is disclosed as such in every response's `data_quality` block.

## Geography types

Selectable geographies are **not peers from one boundary system**. Every geography carries a
`kind`, and every statistic's `provenance.boundary_type` repeats it, so later analytics can
always say which boundary definition produced a number:

| `kind` | Boundary system | In use |
|---|---|---|
| `ward` | the ward polygon itself (2023 ward map) | Ward 20 overall (default) |
| `community_area_portion` | an official community area (`igwz-8jzy`) clipped to the ward | Woodlawn, Washington Park, Englewood, Fuller Park, New City |
| `neighborhood_portion` | a neighborhood polygon from a documented neighborhood layer, clipped to the ward | none active — Back of the Yards is registered with this kind and status `pending_boundary` |

No `neighborhood_portion` filtering is implemented: Silver carries no neighborhood
assignment. If such a geography were ever marked active without that work, the filter
raises rather than returning an empty result (tested).

## Every community area intersecting Ward 20

Measured 2026-09-13 with `scripts/measure_ward_coverage.py --version 2026-07-12`
(method: `src/bw_observatory/geography/ward_coverage.py`). **CRS:** EPSG:3435, NAD83 /
Illinois East, US survey feet; planar polygon-on-polygon intersection of the validated
reference layers, nothing buffered, simplified or snapped. Ward 20 = **5.214 sq mi**. The
nine shares of the ward sum to **100.0000 %** — community areas partition the city, so this
is the coverage proof, not an assumption.

| CA | Community area | Intersection (sq mi) | % of Ward 20 | % of the area inside Ward 20 | Treatment |
|---|---|---|---|---|---|
| 61 | New City | 1.264 | 24.24 | 26.17 | selectable drilldown |
| 40 | Washington Park | 1.203 | 23.08 | 79.18 | selectable drilldown |
| 42 | Woodlawn | 1.040 | 19.94 | 50.14 | selectable drilldown |
| 68 | Englewood | 0.705 | 13.53 | 22.95 | selectable drilldown |
| 37 | Fuller Park | 0.488 | 9.35 | 68.25 | selectable drilldown |
| 69 | Greater Grand Crossing | 0.324 | 6.21 | 9.13 | selectable drilldown (small portion) |
| 41 | Hyde Park | 0.090 | 1.73 | 5.56 | selectable drilldown (small portion) |
| 38 | Grand Boulevard | 0.086 | 1.64 | 4.92 | selectable drilldown (small portion) |
| 39 | Kenwood | 0.014 | 0.27 | 1.37 | selectable drilldown (small portion) |

**Product decision (2026-09-13): every official community area that intersects Ward 20 is a
drilldown, including the small portions.** The drilldowns exist for geographic equity and
accountability analysis, not only navigation, and hiding a small portion could conceal a
disproportionate pattern. Small portions carry small denominators: the measured size travels
with every response (`intersection_sq_mi`, `share_of_ward_area_pct`,
`share_of_area_in_ward_pct` in the catalog; the scope sentence on the page) so future
analytical components can warn when counts or denominators are too small for strong
conclusions. **No suppression or significance rule is defined**; that is deliberately left to
a later methodology package. On 2025 data the nine portions hold 2,960 / 1,842 / 747 / 429 /
1,009 / 299 / 227 / 270 / 30 reports; the ward holds 7,813, computed from the ward polygon
alone.

## Back of the Yards — evaluated, left pending

**Source evaluated (V2-002A, 2026-09-13):** City of Chicago *Boundaries - Neighborhoods*,
"as developed by the Office of Tourism" — shapefile blob `9wp7-iasj` (`Neighborhoods_2012b`,
native CRS EPSG:3435; the map view `bbvz-uum9` serves no geometry). Retrieved 2026-09-13
into `data/reference/chicago/2026-07-12/neighborhoods.geojson` (reprojected to EPSG:4326),
manifest row recorded with checksums; portal `rowsUpdatedAt` 2010-12-22. Validation: 98
features, 0 repaired, 0 empty, 0 duplicate ids, 0 unexpected overlaps.

**Finding:**

1. The City's own description: *"These boundaries are approximate and names are not
   official."* The layer is a tourism product, not a boundary of record.
2. **No feature is primarily named Back of the Yards.** The string appears only as the
   secondary label (`SEC_NEIGH`) of two features whose primary names are **New City** and
   **Fuller Park**.
3. Those two polygons are **geometrically identical** to community areas **61 (New City)**
   and **37 (Fuller Park)**: symmetric difference 0.0000 sq mi in each case. Their
   intersections with Ward 20 are therefore exactly the New City and Fuller Park rows above
   (1.264 and 0.488 sq mi).
4. So the City publishes no Back of the Yards boundary distinct from New City. Activating
   "Back of the Yards" from this source would substitute the whole New City community area
   (and, by the same label, Fuller Park) — precisely what the product rules forbid.

**Treatment:** Back of the Yards stays `pending_boundary` (`kind: neighborhood_portion`,
`represented_by: new-city`), shown disabled with this reason; New City is named as the
official geography that contains it. Nothing was inferred or drawn. The full evaluation is
recorded under `evaluated_source` in `config/geographies.yml`. Activating it would need a
boundary that is both authoritative and distinct from New City — none is known.

The tourism layer is also **not** a substitute for the five community-area drilldowns: its
"Woodlawn" polygon differs from community area 42 (71.6 % vs 50.1 % of it inside the ward)
and its "Englewood" polygon from 68 (11.3 % vs 22.9 %). Changing the five drilldowns to any
neighborhood definition is a methodology decision requiring explicit approval.

## Intended use: geographic equity analysis (documented, not built)

The drilldowns are the geographic frame for future equity and accountability questions such
as:

1. Where are service requests originating?
2. Are requests disproportionately concentrated in certain Ward 20 areas?
3. Are some areas potentially under-reporting problems?
4. Given submitted requests, are completion rates different geographically?
5. Are response / completion times different?
6. How does service-request activity compare with observable need?
7. How does public-safety burden vary geographically?
8. How does municipal response compare with population, households, parcels, street miles,
   housing conditions, vacant lots, and other appropriate denominators?
9. Are City resources distributed consistently with demonstrated need?

Rules any such analysis must follow, recorded now so they bind later packages:

- **Request volume is never service need.** Low request volume may mean fewer problems,
  lower population, lower reporting propensity, access / language / digital barriers,
  distrust or disengagement, different housing or infrastructure conditions, or another
  unobserved factor. High request volume does not by itself mean an area is receiving better
  or worse service.
- Equity analysis must distinguish **NEED → REQUEST → RESPONSE → COMPLETION** and use
  appropriate denominators before making any equity claim.
- Small portions (Kenwood, Grand Boulevard, Hyde Park) stay in the frame; their small
  denominators are a reason to warn, not to hide them.
- None of this is implemented in V2-002/002A. No 311, service, demographic, housing or
  resource dataset is connected.

## Coverage and double counting — the invariants

The drilldowns are **not required to partition Ward 20**, and may in future overlap (a
neighborhood polygon and a community area are different systems). The rules that make that
safe, each enforced by `tests/test_geographies_api.py`:

1. Ward 20 overall is decided by `spatial_ward_current == "20"` **alone**; the area list is
   never consulted. Adding, removing, overlapping or pending drilldowns cannot change it.
2. No Ward 20 record is excluded for belonging to no drilldown (Greater Grand Crossing,
   Kenwood, or a missing community area all still count toward the ward).
3. Every community-area drilldown is `in_ward AND in_area` — a strict subset of the ward.
4. A `neighborhood_portion`, if ever activated, must use the same `in_ward AND …` shape; today
   it raises.
5. Overlapping drilldowns double-count only themselves, never the ward: the ward total is
   asserted unchanged with two fully overlapping areas configured.
6. An unknown or pending geography is a 404 with its reason, never an empty (zero-looking)
   payload.

Police beats: 21 beats intersect Ward 20 across districts 2, 3, 7 and 9; five lie entirely or
almost entirely inside it (0311, 0232, 0313, 0933, 0312). Beats are reported as beats — a beat
is never treated as a neighborhood, and a district is never treated as the ward.

## Bronzeville

Bronzeville is **not a product geography**. It was removed from the application in V2-002:
it is not in `config/geographies.yml`, the API answers `404 Unknown geography` for it, and no
public copy mentions it. The enrichment pipeline still writes a `neighborhood_bronzeville`
column (always null) because the Silver files on disk carry it; rewriting 21 years of Silver
to drop a column was judged not worth the risk. ADR-0004 and `config/neighborhoods/
neighborhoods.yml` are retained as pipeline history and are not read by the product filter.

## Where geography is defined

- `config/geographies.yml` — the registry: ward, areas, status, provenance, disclosed shares.
- `src/bw_observatory/presentation/geography.py` — the single filter authority.
- `GET /api/v1/geographies` — the catalog the frontend selector is built from.
- `apps/web/src/lib/useGeography.ts` — the one frontend authority (URL `?geo`, default Ward 20).
- `tests/test_geographies_api.py` — the rules above as tests.

## Historical ward boundary — "current Ward 20 footprint"

**Methodology (kept, 2026-09-13):** all observations 2006–2026 are analyzed through the
**current Ward 20 footprint** — the ward as drawn in the 2023 map. Historical events are
being examined within the geography that constitutes Ward 20 today, not within the ward lines
in force when they occurred. This keeps one fixed territory across the whole series so years
are comparable, and it is what "Ward 20" means everywhere in the product. It is disclosed on
every page and in every response (`provenance.ward_vintage`, `geography_scope`).

The alternative — each period's own ward map (2015 and 2003 remaps at least) — would break
comparability across remap years and has **not** been adopted. Historical ward maps are not
ingested. Revisiting this is a separate work package.

## What is not yet available

- No pre-2023 ward maps (see above).
- No authoritative, distinct Back of the Yards boundary (the tourism layer is now on disk as
  a secondary reference and is not one).
- No Census demographics joined to any geography.
- No sub-area geography in the UI beyond police beats in the Overview.
