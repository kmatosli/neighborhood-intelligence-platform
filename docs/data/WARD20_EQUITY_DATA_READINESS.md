# Ward 20 equity & accountability — data readiness audit (V2-003)

**Audit date.** 2026-09-14. **Scope.** What can be defensibly measured *now* toward the
product question — *are burden, government response, and public investment distributed
equitably across Ward 20?* — what already exists in the repository, what is missing, and
which implementation package should come first. Nothing analytical was built.

**Analytical model (binding, unchanged).**
`NEED / CONDITION → REQUEST / REPORT → GOVERNMENT RESPONSE → COMPLETION / OUTCOME →
PUBLIC INVESTMENT`. Stages stay distinct. A 311 request proves a request was made, not that
a need exists. A crime record is a reported incident, not a conviction. Spending is not
benefit. Absence of records is not zero. Descriptive administrative data supports no causal
claim. No equity score, ranking, grade or composite index.

**Geographic foundation (binding, V2-002A).** Ward 20 overall = the current (2023) Ward 20
footprint, computed independently; nine community-area portions (community area ∩ current
Ward 20); Back of the Yards `neighborhood_portion / pending_boundary`. Small portions stay;
no suppression rule is defined here.

Reproduce the source table with `uv run python scripts/audit_source_readiness.py`; the
2026-09-14 run is saved as `docs/data/source_readiness_2026-09-14.json`.

Status vocabulary used throughout: **ALREADY BUILT · PARTIALLY BUILT · DATA PRESENT BUT
NOT PRODUCTIZED · SOURCE IDENTIFIED BUT NOT INGESTED · NOT YET INVESTIGATED.**

---

## 1. What is already in the repository

| Asset | Status | Detail |
|---|---|---|
| Crime incidents, Bronze | **ALREADY BUILT** | `ijzp-q8t2`, 21 year files 2006–2026, 6,088,844 rows (manifest), checksummed; 2026 through **2026-07-02** locally (portal is at 2026-09-06 — local copy is ~2 months stale; refresh is a manual per-year re-download, `scripts/download_crime_history.py`; incremental refresh on `updated_on` is **not** implemented although the field is present) |
| Crime, Silver `crime_with_geography` | **ALREADY BUILT** | point-in-polygon per record: `spatial_ward_current` (2023 map), `spatial_community_area`, beat, district, 2010 tract, 2020 block group; quality report per year |
| Crime API + UI | **ALREADY BUILT** (Overview/Pulse, incidents table + CSV) / **PARTIALLY BUILT** (`/overview` categories endpoint exists, not used by the UI) | geography × year context, all nine portions verified |
| Reference geography | **ALREADY BUILT** | community areas (1920), wards (2023), beats/districts (2012), tracts (2010), block groups (2020), ZIP, tourism neighborhoods (secondary) — `data/reference/chicago/2026-07-12/` with manifest |
| Dataset catalog | **ALREADY BUILT** | `data/reference/dataset_catalog.parquet` — one row (crime) |
| 311 / service requests | **SOURCE IDENTIFIED BUT NOT INGESTED** | nothing in the repo (confirmed by grep and the 2026-07-21 loader audit) |
| Census / ACS attributes | **SOURCE IDENTIFIED BUT NOT INGESTED** | only polygons exist; no population or household counts anywhere in the repo |
| TIF / investment | **SOURCE IDENTIFIED BUT NOT INGESTED** | `TIF Projection 2025 Yearend Report.pdf` (owner's Downloads, copied to `C:\tmp\ward20` for this audit; **not in the repo**); machine-readable equivalents found on the portal (§5) |
| Menu money, capital program, contracts | **NOT YET INVESTIGATED** beyond portal search | no authoritative dataset surfaced (§5) |
| Gold layer | empty | — |

---

## 2. Signal family 1 — public safety (reported crime)

**Source.** City of Chicago *Crimes – 2001 to Present* (`ijzp-q8t2`), Bronze 2006–2026.

| Item | Finding |
|---|---|
| Coverage by year | complete 2006–2025 (manifest `complete`, row counts reconcile); 2026 partial through 2026-07-02 locally |
| Fields present | `id, case_number, date, block (masked to 100-block), iucr, primary_type, description, location_description, arrest, domestic, beat, district, ward, community_area, fbi_code, x/y, year, updated_on, latitude, longitude` |
| Coordinates | missing on 0.1–2.6 % of records per year (`geography_quality.parquet`); 2025: 1,546 of 237,516 |
| Geography | Ward 20 and all nine portions **verified** (V2-002A): 2025 = 7,813 ward; 2,960 / 1,842 / 747 / 429 / 1,009 / 299 / 227 / 270 / 30 by portion |
| `arrest` | a boolean **as of the record's last update** (`updated_on`, 2025 file last touched 2026-07-10). It is not a clearance, charge or conviction; no arrest date exists, so **arrest timing cannot be measured**. "Arrest share" = share of reported incidents carrying an arrest flag at refresh time — defensible only with that wording, and it drifts as older records are updated |
| Clearance / completion | **not in this dataset**; CPD clearance data would be a separate source (not investigated) |
| `domestic` | present (2025: 45,221 true) — governs privacy handling, never a public breakdown at block level |
| Repeat location / hotspot | technically possible at the masked 100-block and beat level (`block` never null); the Pulse already surfaces beat concentration and a repeat-block issue card. Privacy rules (no exact address, no DV/child/sexual-offense location detail) are enforceable because only the block is stored |
| Built but not surfaced | `/api/v1/overview/{geo}` (config-driven crime groupings + monthly trend), incidents CSV export, `category_drivers`, `monthly_categories`, arrest summary with prior-period comparison |
| Longitudinal issues | 2023 ward map applied to all years (disclosed); beats/districts are 2012 lines; IUCR/primary-type coding is stable but `description` wording varies; recent weeks incomplete (YTD flagged); the city revises records after publication |

**Readiness:** crime burden by portion — **READY**. Arrest share by portion — **POSSIBLE WITH
CAVEATS** (flag semantics above; small-N in small portions). Arrest timing, clearance —
**NOT CURRENTLY DEFENSIBLE** (no data).

---

## 3. Signal family 2 — 311 municipal service requests

**Authoritative source.** *311 Service Requests* (`v6vf-nfxy`), City of Chicago Data Portal,
metadata and aggregate queries retrieved 2026-09-14. Legacy per-type datasets (e.g. Pot Holes
`7as2-ds3y`, 2009-01-12 → 2018-12-18, 560,478 rows; street lights `3aav-uy2v`/`zuxi-7xem`;
graffiti `hec5-y4x5`; rodents `97t6-zrhs`; vacant buildings `7nii-7srd`; etc.) cover the
previous CSR system with a **different schema and category taxonomy**.

| Item | Finding (portal, 2026-09-14) |
|---|---|
| Rows / span | 14,638,674; `created_date` 2018-07-01 → 2026-09-13; new system launched **2018-12-18**; `legacy_record` flags 31,443 carried-over rows |
| Ward 20 (by `ward` field) | 144,808; by year 2019 21,140 · 2020 23,720 · 2021 18,305 · 2022 15,661 · 2023 15,985 · 2024 17,867 · 2025 16,683 · 2026 YTD 14,523 |
| Categories | `sr_type` (110 distinct), `sr_short_code`, `owner_department`, `created_department` |
| Dates | `created_date`, `last_modified_date`, `closed_date` (present on 100 % of Completed) |
| Status | Completed 14,179,812 · Open 246,200 · Canceled 212,661 · Closed 1 |
| Department | `owner_department` (Ward 20: Streets & Sanitation 75,400; CDOT 31,177; Buildings 11,390; Water 11,275; Animal Care 8,432; …) |
| Location | `latitude/longitude`, x/y, `street_address`, `zip_code`; **missing coordinates 14,830 of 14.6 M (0.1 %)**; Ward 20: 26 |
| Ward / CA fields | `ward`, `community_area`, police beat/district, precinct |
| Duplicates / reopen | `duplicate` checkbox (750,357 true, 5.1 %) and `parent_sr_number` (750,001) link duplicates to a parent; **no reopen indicator** |
| Origin | `origin` (Phone 8.3 M, Internet 4.0 M, Mobile 1.2 M, Mass Entry 547 k, **Alderman's Office 459 k**, Generated In House 27 k) — matters for "reporting propensity" |
| Information-only calls | `311 INFORMATION ONLY CALL` (Ward 20: 4,645) is geocoded to the 311 Center address — must be excluded from any geography |
| Category churn | e.g. `Tree Trim Request (NO LONGER BEING ACCEPTED)` still receives records (300,218; last 2026-09-11); taxonomy changed wholesale at the 2018 system switch |

**Geography — critical finding.** The `ward` field is the ward **at creation time**, not
today's map. Point-in-polygon on 3,000-record samples of `ward='20'`: 2019 **78.0 %** inside
the current Ward 20 polygon, 2022 76.8 %, 2023 99.5 %, 2025 97.7 %. Conversely, 2019
Washington Park requests inside today's Ward 20 carried ward 20 (1,625), 3 (183) or 4 (45).
The `community_area` field agrees with the polygon on 99.5 %. **Ward 20 and portion filters
for 311 must be point-in-polygon on coordinates against the current footprint** — the same
method as crime — and that is feasible for 99.9 % of records.

**Metric readiness (once ingested and enriched as above):**

| Metric | Class | Why |
|---|---|---|
| Request count by portion | **READY** | coordinates + PIP; exclude info-only calls; decide duplicate handling explicitly |
| Request rate | **POSSIBLE WITH CAVEATS** | needs a category-appropriate denominator (§4); no denominator is ingested today |
| Open count / aging open requests | **READY** | `status='Open'` + `created_date`; Ward 20 open by creation year today: 2019 261 · 2020 151 · 2021 92 · 2022 130 · 2023 310 · 2024 318 · 2025 428 · 2026 2,405 |
| Closed / completed count | **READY** | `status`, `closed_date` |
| Completion rate | **POSSIBLE WITH CAVEATS** | denominator must exclude Canceled and duplicates, and window by creation cohort (recent cohorts are right-censored) |
| Median completion time | **POSSIBLE WITH CAVEATS** | probe: Ward 20 pothole complaints 2025, completed, non-duplicate, n=478: median 3.3 days, p90 112 days, 0 % same-day; `closed_date` semantics differ by department (auto-close, "completed = inspected", mass closures) — must be described per category, never pooled across categories |
| Service-category mix | **READY** | `sr_type` / `owner_department`; taxonomy is post-2018 only |
| Repeat requests (same location) | **POSSIBLE WITH CAVEATS** | by `street_address`/block; privacy: publish at block level only |
| Duplicate requests | **READY** | `duplicate` + `parent_sr_number` |
| Reopened requests | **NOT CURRENTLY DEFENSIBLE** | no field |
| Pre-2019 history | **NOT CURRENTLY DEFENSIBLE** as one series | legacy datasets use different schemas/taxonomies; joining requires explicit crosswalks (not to be done silently) |

---

## 4. Signal family 3 — need, context and denominators

| Candidate | Source | Status | Geography fit for portions |
|---|---|---|---|
| Population, households, housing units, tenure, age | Census 2020 Decennial (PL/DHC, **block** level) and ACS 5-year (**block group** level) via `api.census.gov` | **SOURCE IDENTIFIED BUT NOT INGESTED** — the API now returns *Missing Key* without a key (free credential the owner must supply; `CENSUS_API_KEY` placeholder already in `.env.example`) | Repo holds 2020 block groups: **92 intersect Ward 20, only 13 fully inside** → block-group values need apportionment. 2020 **blocks** (TIGER `tabblock20`, not yet downloaded) nest far better; block-level 2020 population/housing is the defensible denominator path |
| Income, poverty, unemployment | ACS 5-year block group / tract | as above | tract vintage on disk is **2010** (65 tracts touch Ward 20, 5 fully inside); ACS 2020+ uses 2020 tracts — a new tract layer is needed |
| City ACS by community area | `t68z-cikk` (77 rows) / `kn9c-c2s2` (2008-12) | available, no key | **whole community areas only — cannot serve portions** (usable for context, not denominators) |
| Parcels / residential parcels | Cook County Assessor *Parcel Universe* `pabr-t5kh` (1,863,665 rows, `lat/lon`, `class`, 2020 block-group and tract GEOIDs) | **SOURCE IDENTIFIED BUT NOT INGESTED**; no key | coordinates → PIP; residential via `class` |
| Vacant lots (city-owned) | *City-Owned Land Inventory* `aksk-kvfp` (20,770, coordinates, `ward`, `community_area_number`) | identified | PIP; city-owned only — not all vacant land |
| Vacant buildings | *Vacant and Abandoned Buildings – Violations* `kc9i-wq85` (5,012; through 2025-08); 311 vacant-building complaints | identified | PIP; complaint/violation-based, i.e. **REQUEST/RESPONSE-stage data, not a condition census** |
| Building conditions | *Building Violations* `22u3-xenr` (2.0 M, coordinates); *Building Permits* `ydr8-5enu` (847 k) | identified | PIP; both are administrative activity, not conditions |
| Street miles | *Street Center Lines* `6imu-meau` (56,338) | identified — **map view only, no API export** (GeoJSON export returns an empty collection); would need the Data Portal download UI or CDOT | polygon/line clipping |
| Sidewalks, streetlight inventory, tree inventory | none found on the portal (only 311 request datasets and old performance metrics) | **NOT FOUND** | — |

**Denominator recommendations (per category; none adopted here):**

| Service / burden | Plausible denominator(s) | Class |
|---|---|---|
| Potholes, street resurfacing | street centerline miles inside the portion | AVAILABLE WITH NEW INGESTION (manual download) |
| Street/alley lights | street miles (proxy); no light inventory | PROXY ONLY |
| Tree trims / debris / emergencies | no inventory; street miles or land area as proxy | PROXY ONLY |
| Building complaints/violations | housing units (2020 blocks) or parcels/buildings (Assessor) | AVAILABLE WITH NEW INGESTION |
| Vacant-lot complaints | city-owned vacant parcels (`aksk-kvfp`) + Assessor vacant classes | AVAILABLE WITH NEW INGESTION |
| Garbage carts, rodents, sanitation, general resident services | households / population (2020 blocks) | AVAILABLE WITH NEW INGESTION (needs Census key) |
| Reported crime | population (2020 blocks) as one lens; land area and street miles for others; none is "the" denominator | AVAILABLE WITH NEW INGESTION |
| Public investment | no single denominator; compare against observable need measures above | NO DEFENSIBLE DENOMINATOR IDENTIFIED (by design) |

**Available now:** land area of every portion (from V2-002A) — a weak, but honest, first
exposure measure. Nothing else.

---

## 5. Signal family 4 — public investment and resources

| Source | Status | What it gives | Ward 20 attribution |
|---|---|---|---|
| *TIF Projection 2025 Year-end Report* (PDF, 189 pp, projections as of 2025-12-31) | in owner's Downloads; **not in repo** | per district: FY2024 available fund balance, 2025-34 revenue projections, current obligations and proposed projects by department and line item, ward split by % | header ward shares (8 districts include the 20th) |
| *TIF Projections 2025-2034* `fpsv-qjg3` (2,246 rows) | identified | the same report as data: district, category, line item, yearly amounts | **no geography**; district → ward % only |
| *Boundaries – TIF Districts* `eejr-xtfb` (100) | identified | polygons, `wards`, `comm_area`, approval/expiration | polygon ∩ Ward 20 (computed 2026-09-14, EPSG:3435): Washington Park T-178 99.0 % of district in ward (29.3 % of ward area); 47th/Halsted T-121 65.9 % (18.6 %); West Woodlawn T-171 90.0 % (9.3 %); Woodlawn T-65 86.7 % (8.7 %); Englewood Neighborhood T-106 18.3 % (5.6 %); 47th/Ashland T-117 23.0 % (2.3 %); 47th/State T-136 10.2 % (1.0 %); 67th & Wentworth 2.0 %; 71st & Stony Island 3.7 %; 47th & King Drive 0.5 %. **76.0 % of Ward 20's area lies in an active TIF district.** The PDF's ward percentages match the polygon result and omit districts under ~5 % |
| *TIF Annual Report – Projects* `72uz-ikdv` (5,782) | identified | per district/report year/project: payments, public/private funds, status | **no geography** — district → ward |
| *TIF Funded RDA and IGA Projects* `mex4-ppfc` (761; coordinates, `ward`, `community_area`) | identified | address-level developer/IGA projects, approved amounts, affordable units | **PIP-able** → portion-level |
| *SBIF projects* `etqr-sz5x` (2,260; coordinates) | identified | small-business grants by address | PIP-able |
| *TIF Investment Committee decisions* `nm3d-wkdd` (1,698, 2019-24; coordinates) | identified | decisions | PIP-able |
| Aldermanic menu money | **no authoritative dataset found** on the portal; published as ward PDFs by OBM | NOT FOUND | — |
| Capital Improvement Program, contracts/payments, development projects, SSAs (`cmr6-dn8c`, 58) | portal search found no CIP dataset; contracts are not geographically attributable; SSAs are boundaries only | NOT YET INVESTIGATED beyond search | — |

**Cautions that govern any future use:** TIF district ≠ Ward 20 (only Washington Park and
West Woodlawn are essentially ward-internal); a district's projection is a fund, not a place;
project location ≠ beneficiary geography; contractor address ≠ project location; spending ≠
outcome; obligations ≠ money spent. Address-level datasets (RDA/IGA, SBIF) are the only ones
that can be clipped to portions; fund-level figures can only be described *per district that
overlaps the ward*, with the overlap share stated.

---

## 6. Equity-analytics readiness matrix

| Question | Data required | Data present? | Geography ready? | Denominator ready? | Methodology ready? | Confidence | Next action |
|---|---|---|---|---|---|---|---|
| Crime burden by portion | crime Silver | yes | yes | area only | yes (counts, same-period) | high | none — surfaced already |
| Arrest share/rate by portion | crime `arrest` | yes | yes | n/a (share) | caveated wording required | medium | write the "arrest flag ≠ clearance" note; small-N warning |
| 311 request distribution | 311 + PIP | **no** | method proven on samples | area only | exclusion rules needed (info-only, duplicates) | high once ingested | ingest + enrich (V2-004) |
| 311 request rate | 311 + denominators | no | yes | **no** | per-category denominators | low–medium | Census key + blocks; street miles |
| Completion rate | 311 status/closed | no | yes | cohort logic | per-category semantics | medium | V2-004 with category notes |
| Completion time | 311 dates | no | yes | n/a | per-category, right-censoring | medium | V2-004 |
| Unresolved-request burden | 311 open + aging | no | yes | area / households | yes | medium–high | V2-004 |
| Service-category differences | 311 types/departments | no | yes | n/a | post-2018 taxonomy only | high | V2-004 |
| Request activity vs observable need | 311 + condition data | no | partly | **no** — condition data absent | not ready | low | later; needs denominators first |
| Public investment by portion | RDA/IGA + SBIF (address) ; TIF funds (district) | no | address-level yes; fund-level no | none | attribution rules drafted (§5) | low–medium | later package |
| Investment relative to need | above + denominators | no | partly | no | not ready | low | later |
| Combined burden/response | all of the above | no | — | — | **not ready; no composite allowed** | — | not planned |

---

## 7. Data quality and longitudinal issues

- **Ward geography:** crime and 311 both need PIP on the current footprint; the 311 `ward`
  field is historical (§3). Any "by ward" figure taken from a source's own ward field is a
  different, shifting geography.
- **311 system switch 2018-12-18:** category taxonomy, status semantics and identifiers
  changed; legacy datasets are per-type with their own schemas. A single 2009–2026 series
  requires explicit, documented crosswalks — never silent normalization.
- **Completion semantics differ by department/category** (auto-closure, "completed" meaning
  inspected, mass entries); completion time is only comparable within a category.
- **Right-censoring:** open requests and recent cohorts bias completion metrics; use cohorts
  with a maturity window.
- **Crime:** records revised after publication; `arrest` drifts with `updated_on`; local Bronze
  is 2 months behind the portal; YTD periods flagged.
- **Census vintages:** 2010 tracts on disk vs 2020 ACS geography; block groups straddle the
  ward line; blocks needed.
- **TIF:** projections are not spending; annual-report payments are the closest to spending;
  district boundaries and expirations change (47th/Halsted, 47th/Ashland, 47th & King expire
  2026-12-31; Englewood Mall expired 2025-12-31).

## 8. Small-geography risk (Kenwood, Grand Boulevard, Hyde Park — and any category slice)

2025 reported incidents: Kenwood **30**, Hyde Park 227, Grand Boulevard 270; 311 volumes per
category per small portion will be in the tens or single digits. Recommended safeguards for
later packages (none implemented here): always display raw N and the portion's measured
size; an interpretation warning below a stated N (threshold to be decided with evidence, not
invented); multi-year pooling and rolling 12-month periods; category aggregation to the
`owner_department` level; never a percentage without its N; never a rate whose denominator
is itself an estimate with a large margin of error without saying so.

---

## 9. Summary lists

**READY now:** crime burden (counts, same-period change, beat concentration, category mix)
for Ward 20 and all nine portions; incidents export; portion land areas.

**POSSIBLE WITH CAVEATS (after V2-004 ingestion):** 311 request counts, category mix, open
and aging counts, duplicate counts, per-category completion rate and completion time,
repeat-location counts at block level; crime arrest share.

**NOT CURRENTLY DEFENSIBLE:** any *rate* per population/household/parcel/street-mile
(no denominators ingested; Census key required); 311 reopens; pre-2019 311 continuity;
arrest timing and clearance; TIF spending "in Ward 20" at portion level; menu money; any
composite or ranking.

**Missing datasets required (in order of leverage):** (1) 311 `v6vf-nfxy` with PIP
enrichment; (2) Census 2020 blocks (TIGER `tabblock20` IL) + Decennial PL/DHC population and
housing (needs `CENSUS_API_KEY`); (3) ACS 5-year block groups (same key) with 2020 tract
layer; (4) street centerlines (manual export); (5) Assessor parcel universe (Ward 20 subset);
(6) TIF boundaries + RDA/IGA + SBIF + annual-report projects; (7) menu-money — no source.

**New authoritative sources identified (all retrieved 2026-09-14):** `v6vf-nfxy`,
`7as2-ds3y` and sibling legacy 311 sets, `fpsv-qjg3`, `72uz-ikdv`, `mex4-ppfc`,
`etqr-sz5x`, `eejr-xtfb`, `nm3d-wkdd`, `t68z-cikk`, `kn9c-c2s2`, `aksk-kvfp`, `kc9i-wq85`,
`22u3-xenr`, `ydr8-5enu`, `6imu-meau`, `cmr6-dn8c` (Chicago); `pabr-t5kh` (Cook County);
`api.census.gov` 2020 `dec/pl` and `acs/acs5` (key required).

---

## 10. Recommendation — V2-004: 311 service requests, Ward 20 foundation

**Recommended next package:** ingest and geography-enrich the *311 Service Requests* dataset
(`v6vf-nfxy`, 2018-12-18 onward) into the existing Bronze/Silver pattern, clipped by
point-in-polygon to the current Ward 20 footprint and the nine portions, and publish the
**request → response → completion** measures that need no denominator: counts by category
and department, open and aging requests, and per-category completion rate and completion
time with cohort windows and explicit exclusion rules (information-only calls, duplicates,
canceled). No rates, no need claims.

**Why first, against the seven criteria:**
1. *Resident/accountability value* — it is the only source that carries the RESPONSE and
   COMPLETION stages, which the model needs and which crime data cannot supply; open and
   overdue requests are directly actionable at a beat meeting or ward office.
2. *Data quality* — one authoritative, daily-updated source; 99.9 % geocoded; explicit
   duplicate linkage; closed dates on 100 % of completions.
3. *Geographic readiness* — the PIP method is proven on samples and the enrichment pipeline
   already exists for crime; the historical-`ward` trap is documented and avoided.
4. *Denominator readiness* — the recommended measures are denominator-free (counts, shares
   of requests, completion rate among requests, elapsed time), so the package does not have
   to wait for Census access; it also creates the demand-side table that later denominators
   attach to.
5. *Methodological defensibility* — the NEED ≠ REQUEST rule is preserved because nothing in
   the package claims need; completion metrics are scoped per category with censoring rules.
6. *Effort* — reuses `BaseDownloader`/`BaseBronzeWriter`, `assign.py`, the geography
   registry, and the geography × year UI context; the new work is one downloader, one
   enrichment column set, one presentation module.
7. *Decision-useful* — "which requests in the Ward 20 part of Englewood have been open more
   than 90 days, and how long do potholes take to close here versus the rest of the ward" is
   a question a resident can act on; another crime chart is not.

Not chosen first: **Census/context** (blocked on a credential and delivers no answer alone);
**crime analytics** (already served; the remaining gaps need external data); **public
investment** (highest attribution risk, weakest geography, and meaningless without the
burden/response side).

**Question the package lets Ward 20 residents answer:** *Where are municipal service
requests originating across Ward 20, what is still open, and — for a given kind of request —
how long does the City take to complete it in one part of the ward compared with another?*
