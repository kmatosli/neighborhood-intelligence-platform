# NIP V2 — Integrated Crime Intelligence & External Operations Architecture

**Date:** 2026-09-22 · **Status:** design for approval — nothing implemented  

> **Implementation status, updated 2026-09-23.** This document is the audit and specification
> record as written on 2026-09-22, when nothing had been built. Since then **Tier 0 + Tier 0b
> shipped as commit `a8be4a5`** (recorded as V2-006 in `docs/PROJECT_STATUS.md`): beat
> whole-beat context and clipping disclosure, removal of the crime-type and beat display
> truncation, the freshness banner, non-silent published-field filtering, the
> measurement-intelligence notes, provisional-period labelling, the enforcement-generated
> category flag, and the "counts are not a safety ranking" caution.
>
> Everything else in this document remains **proposed**. Catalogue features CA-02 through CA-19
> are **pending owner review** and none is approved. Findings infrastructure
> (`config/findings.yml`, `presentation/findings.py`, `/api/v1/findings`) is **approved for
> implementation but not yet built**, so paths referring to it are forward references. Figures
> quoted throughout were verified against the September release on 2026-09-22 and are not
> re-verified here.
**Companion:** `V2_ANALYTICAL_REDESIGN_2026-09-22.md` (same folder) holds the beat-definition
resolution, capability inventory, defect register, Overview wireframe, finding model, and
editorial process. This report **integrates and extends** it rather than repeating it.

All figures verified against the active September release (`/var/data/bw-release-20260921`,
Render `e00665c`, `data_through 2026-09-06`) during this session. **UNVERIFIED** and
**ILLUSTRATIVE** are marked explicitly.

**Note on inputs:** the *External Operations Intelligence Integration specification* referenced
in the assignment was **not attached and is not present** in the repository or the owner's local scratch area. I have
worked from the twelve domain names given in the prompt (A–L). If the full spec exists, its
detail may change the mapping in Deliverable 4. The *TIF Projection 2025 Year-end Report* **is**
available at `TIF_Projection_2025_Yearend_Report.pdf`, held in the owner's local working copy
outside the repository, with a text extraction alongside it — this resolves an earlier UNVERIFIED item, though its contents are not yet
analysed.

---

# DELIVERABLE 1 — Prostitution Reporting Investigation

## Q: Why are reported PROSTITUTION incidents so rare in Ward 20?

### 1. Verified counts (reproduced against the active dataset)

The previous audit's figures are confirmed: **Ward 20 = 1 record in 2025, 0 in 2026 YTD.**

### 2. Historical trend — a near-total collapse, not an absence

Full series, current Ward 20 footprint (2023 ward map applied to all years — a disclosed
limitation: "Ward 20 in 2006" means *the area that is Ward 20 today*):

| Year | Citywide | Ward 20 | | Year | Citywide | Ward 20 |
|---|---|---|---|---|---|---|
| 2006 | 7,034 | **372** | | 2016 | 800 | 1 |
| 2007 | 6,087 | 337 | | 2017 | 735 | 1 |
| 2008 | 5,141 | 292 | | 2018 | 718 | 0 |
| 2009 | 3,940 | 240 | | 2019 | 681 | 0 |
| 2010 | 2,484 | 105 | | 2020 | 278 | 0 |
| 2011 | 2,424 | 121 | | 2021 | 95 | 0 |
| 2012 | 2,204 | 118 | | 2022 | 283 | 0 |
| 2013 | 1,652 | 57 | | 2023 | 209 | 0 |
| 2014 | 1,625 | 8 | | 2024 | 308 | 0 |
| 2015 | 1,322 | 27 | | 2025 | 189 | **1** |
| | | | | 2026 YTD | 97 | 0 |

Citywide **−97.3%** 2006→2025. Ward 20 collapsed **earlier and more completely**: 372 → 105 by
2010, → 8 by 2014, → ~0 from 2016. There is no single change-point; it is a sustained
multi-year decline with a steep step in 2013–2014 (Ward 20) and 2015–2016 (citywide).

### 3. Geographic comparisons — filtering is not the cause

| | 2006 | 2025 |
|---|---|---|
| Ward 20 footprint | 372 | 1 (New City portion, beat 0933) |
| Top Ward 20 portions | New City 167 · Woodlawn 121 · Washington Park 68 | — |
| Top Ward 20 beats | 0312 (113) · 0931 (66) · 0933 (45) | — |
| **Whole** Woodlawn CA | 124 (121 in ward) | **0** |
| **Whole** Washington Park CA | 124 (68 in ward) | **0** |
| **Whole** Englewood CA | 190 (4 in ward) | 5 (0 in ward) |
| Citywide concentration | CA 25 Austin 829 · CA 27 E. Garfield Pk 531 · CA 8 Near North 429 | CA 56 Garfield Ridge 70 · CA 25 Austin 46 |

**Ward-clipping and portion geography are ruled out**: the *whole* Woodlawn and Washington Park
community areas also record **zero** in 2025. The residual citywide activity sits in other
community areas entirely. Nothing is being hidden by NIP's geography.

### 4. Classification findings — no reclassification artifact

IUCR codes are stable across the whole period and still in use:

| IUCR | Description | 2006 | 2015 | 2025 |
|---|---|---|---|---|
| 1506 | SOLICIT ON PUBLIC WAY | 5,000 | 911 | 141 |
| 1513 | SOLICIT(ING) FOR BUSINESS | 1,713 | 159 | 13 |
| 1505 | CALL OPERATION | 105 | 133 | 1 |
| 1512 | SOLICIT(ING) FOR A PROSTITUTE | 83 | 90 | 4 |
| 1549 | OTHER PROSTITUTION OFFENSE | — | 7 | 26 |
| 1531 | JUVENILE PIMPING | — | — | 2 |

Only description *wording* changed ("SOLICIT FOR BUSINESS" → "SOLICITING FOR BUSINESS"); codes
did not. Candidate absorbing categories cannot account for the volume:

| Category, citywide | 2006 | 2015 | 2025 |
|---|---|---|---|
| HUMAN TRAFFICKING | 1 | 14 | 18 |
| SEX OFFENSE | 1,577 | 1,063 | 1,391 |
| PUBLIC INDECENCY | 4 | 14 | 10 |
| OBSCENITY | 17 | 49 | 55 |
| any description containing "SOLICIT" | 9,919 | 1,563 | 287 |

Human trafficking grew from 1 to 18 — real, but three orders of magnitude too small to absorb
~6,800 lost records. "SOLICIT" descriptions fell in step with prostitution itself. **No evidence
of reclassification.** I did not reclassify any other offence as prostitution, and each row
above measures only what its own code measures.

### 5. The decisive finding — this variable measures enforcement, not prevalence

**PROSTITUTION is ~99% arrest-flagged; all crime citywide is 16.1%.**

| Year | PROSTITUTION arrest-flagged |
|---|---|
| 2006 | 99.3% |
| 2015 | 99.8% |
| 2025 | 91.5% |

A prostitution record essentially exists *only* when police made an arrest. It is a
**proactive/discretionary** category: the count is a measure of police activity, not of
underlying behaviour.

**Internal control — all discretionary offences collapsed together, victim-reported ones did
not** (citywide, 2006 → 2025):

| Offence | 2006 | 2025 | Change | Type |
|---|---|---|---|---|
| Gambling | 1,368 | 13 | **−99.0%** | discretionary |
| Prostitution | 7,034 | 189 | **−97.3%** | discretionary |
| Narcotics | 55,813 | 7,419 | **−86.7%** | discretionary |
| Liquor law | 1,135 | 200 | **−82.4%** | discretionary |
| **All arrests** | 135,431 | 38,346 | **−71.7%** | — |
| **Battery** | 80,667 | 42,656 | **−47.1%** | victim-reported |

Same pattern in the Ward 20 footprint: narcotics 2,261 → 141, gambling 77 → 1, prostitution
372 → 1, while battery fell 4,020 → 1,742 (−57%). The discretionary categories fell roughly
twice as far as the victim-reported one. This is the strongest available evidence that the
prostitution series tracks enforcement posture.

### 6. Documented external changes (documented ≠ established cause)

Publicly documented, from authoritative/secondary sources:

- CPD prostitution-related arrests **declined every year since 2004**, the year after the
  Mayor's Office ISA Work Group on Prostitution was established ([CAASE, *Policing & Enforcement of Prostitution Laws in Chicago*, 2020](https://www.caase.org/wp-content/uploads/2020/05/Report-PEOPL-Jan20-v1.3-WithAppx.pdf)).
- The **Chicago Prostitution and Trafficking Intervention Court** provides a diversion route for
  people arrested for selling sex ([CAASE](https://www.caase.org/city-doubles-down-on-failed-efforts-to-end-prostitution/)).
- Roughly **90% of CPD prostitution arrests are for selling rather than buying** ([WTTW summary of the CAASE report](https://news.wttw.com/2020/01/27/report-chicago-police-prioritize-arrests-of-sex-sellers-over-buyers-traffickers)).
- A broader documented CPD pullback on discretionary drug-possession and prostitution
  enforcement ([Vice](https://www.vice.com/en/article/what-happened-after-chicago-police-cut-down-on-busting-drug-possession-and-prostitution/)).

**These are documented changes in enforcement and diversion practice. They are consistent with
the observed series. They are not established as its cause** — no analysis here attributes the
Ward 20 pattern to any specific policy, and the record contains no policy field to test against.

### 7. Data-quality checks performed

| Check | Result |
|---|---|
| Category mapping | PROSTITUTION → `public_order` (`config/crime_categories.yml:116`); never dropped |
| API exposure | `category_drivers` returns all types untruncated; UI truncates to 12 (`index.tsx:466`) |
| Missing descriptions | none material in this category |
| Duplicate handling | release verifier: per-year ids unique, Bronze/Silver id sets identical, all 21 manifest checksums match |
| Geographic assignment | whole-CA cross-check gives 0 — clipping not implicated |
| Source completeness | `source_removed` rows excluded from all counts above |
| Recent-data lag | 2026 is YTD to 2026-09-06 and incomplete by design; the 7-day source lag applies |
| Historical compatibility | IUCR codes stable 2006–2026; ward map is 2023 applied to all years (disclosed) |

### 8. What the data cannot establish

- **Nothing about underlying prevalence** of commercial sex or exploitation in Ward 20. A count
  of arrests cannot measure an activity that is only recorded when police choose to act on it.
- Whether exploitation moved indoors or online — the dataset has no such field.
- Whether any specific policy caused the decline.
- Trafficking prevalence: HUMAN TRAFFICKING counts (18 citywide in 2025) are far too small and
  too enforcement-dependent to support any neighbourhood-level statement.
- Victim counts or characteristics — not present, and not to be inferred.

### 9. Recommended NIP treatment

1. **Do not publish a Ward 20 prostitution trend as a neighbourhood condition.** Publish it, if
   at all, as a **DATA GAP / enforcement-measure** card explaining what the variable is.
2. Add an **"enforcement-generated"** flag to the category metadata (prostitution, narcotics,
   gambling, liquor, weapons-possession) so every view can warn that the series responds to
   police activity. This is reusable across the platform and is the durable fix.
3. Visualisation: a **discretionary-vs-victim-reported panel** — indexed series (2006 = 100)
   for the two groups side by side, with the arrest-share line beneath. This communicates the
   finding honestly in one picture.
4. Never characterise residents, blocks, or portions using this category. No map of prostitution
   records at block level.
5. Suppression: with 0–1 records per year, any Ward 20 breakdown is below threshold — show the
   count and stop.

**This investigation is recommended as the Deliverable 10 case study** (see below): the
evidence supports a meaningful, defensible conclusion — one that corrects a naive reading
rather than forcing a finding.

---

# DELIVERABLE 2 — Crime Analytics Innovation Matrix

Feasibility classes: **1** in production · **2** in data, unexposed · **3** additional public
source · **4** restricted agency access · **5** not feasible/not appropriate.

| # | Capability | Analytical question | Data | Class | Method | Geography | Privacy | NIP integration | Recommend |
|---|---|---|---|---|---|---|---|---|---|
| 3A | **Repeat location** | Do incidents recur at the same place? | `block`, category, date | **2** | counts per masked block per period; repeat rate by category | masked block (floor) | never below block; suppress <5; no DV/sexual detail | Trends ▸ Concentration; beat profile | **Build** (Tier 3) |
| 3B | **Near-repeat** | Do burglaries cluster nearby soon after one? | coords, date | **2, degraded** | Knox-style space-time contingency vs permutation baseline | **blocked coords limit this** — 3,438 distinct points for 7,817 incidents; block-to-block adjacency only | as 3A | Burglary investigation | **Exploratory only**, with the spatial-precision caveat stated; not a headline |
| 3C | **Displacement / diffusion** | Did a decline coincide with a rise next door? | crime + beat/block adjacency | **2** | adjacent-unit change vs non-adjacent control; check type and timing shifts too | beat, block group | — | SARA Assessment | **Build** in Tier 6, never as proof of displacement |
| 3D | **Temporal sequence / co-movement** | Do categories move together? | monthly series by category | **1** | cross-correlation on deseasonalised series; report as association | ward, portion | — | Trends ▸ Time | **Build, labelled exploratory**; aggregate-only, no individual inference |
| 3E | **Harm-weighted analysis** | Does severity add information beyond counts? | category + a **published** weight set | **3** | apply an external, citable weight set (e.g. a published crime-harm index using sentencing-based weights); always shown beside counts | ward, portion | — | Trends ▸ Composition, as a secondary view | **Only with a published, cited weight set.** Never invent weights; never replace counts; never a single unexplained score |
| 3F | **Reporting-lag analysis** | Do recent counts rise as records arrive? | `date` vs `updated_on`; **retained releases** | **1** | compare the same period across releases; build a lag curve | any | — | a "provisional" badge on recent periods | **Build early** — cheap and directly improves honesty |
| 3G | **Hotspot persistence** | Recent / persistent / emerging / shifting? | crime + block/beat | **2** | elevated in k of N comparable periods; classify, report k and N | masked block, beat | as 3A | Trends ▸ Concentration | **Build** (Tier 4) |
| 3H | **Statistical trend** | Is this a trend or noise? | monthly series | **1** | Kendall tau-b stability test; rolling 12m; 5-yr band; Poisson interval; change-point as candidate flagging only | any | — | every trend statement | **Build** (Tier 4) |

**3F is the quick win.** Evidence it matters already exists: the Ward 20 2025 total moved
**7,813 → 7,817** between the July and September releases, and both releases are retained on the
production disk (`bw-release-20260726`, `bw-release-20260921`), so a genuine release-to-release
lag study is possible today with no new data. Recommended communication: label any period
within ~60 days of `data_through` as **provisional**, and state that a recent decline may shrink
as records arrive.

**Explicitly excluded:** individual or neighbourhood criminal-risk scores; any predictive
targeting; any model using demographic or socioeconomic characteristics as risk inputs. These
are out of scope on principle, not for lack of data.

**Analysis-type discipline.** Every view must be labelled as one of: **descriptive** (counts,
shares, trends — most of NIP), **exploratory association** (3B, 3D, cross-domain overlaps),
**predictive** (none proposed), **causal evaluation** (only SARA Assessment with a comparison
area). Conflating these is the most likely way this platform could mislead.

---

# DELIVERABLE 3 — Crime Trends Information Architecture

The nine-question workflow maps to **five connected views** plus one shared control bar — the
smallest set that supports the investigation without disconnected charts.

```
                ┌──────── PERSISTENT CONTROL BAR ─────────┐
                │ geography · category · period · compare  │   (URL-encoded, preserved
                │ setting · domestic · arrest              │    across every view)
                └──────────────────────────────────────────┘
 WHAT CHANGED? ─────────────────────────► V1  COMPOSITION & CHANGE
                                             decomposition table (all 26 types,
 WHICH TYPES EXPLAIN IT? ────────────────►    Δ, %Δ, share, contribution; Σ = total Δ)
                                             + tau-b stability + provisional badge
                                                        │ select a category
 WHERE? ─────────────────────────────────► V2  GEOGRAPHY & CONCENTRATION
                                             portion table (with intersection share),
                                             beat table (in-ward + whole-beat),
                                             concentration curve, persistence class
                                                        │ select a beat or portion
 WHEN? / CIRCUMSTANCES? ─────────────────► V3  PROFILE (beat or portion)
                                             composition · change drivers · settings ·
                                             hour × DOW · arrest share · own baseline
                                                        │ drill to circumstances
 IS IT PERSISTENT? ──────────────────────► V4  CIRCUMSTANCES & PERSISTENCE
                                             setting × time cross-tab (cells <5 suppressed),
                                             repeat-location, k-of-N persistence, seasonality
                                                        │
 RELATED CONDITIONS? ────────────────────► V5  CROSS-DOMAIN & RESPONSE
 WHAT RESPONSE? / WHAT HAPPENED AFTER?       311 / vacancy / lighting / crashes overlay,
                                             documented response register, assessment
                                             (comparison area, displacement check)
                                                        │
                                             ▸ every number links back to METHODS
```

Rules: one control bar, URL-encoded, never reset by navigation · every view states geography,
denominator, period and provisional status · every Overview finding deep-links to the exact
view and anchor with filters applied · no statistical technique gets a view of its own.

Component specifications (F1–F11) are in the companion report, Part 4.

---

# DELIVERABLE 4 — External Operations Integration Matrix

**No new tabs.** All twelve domains land inside the four existing surfaces (Overview, Trends,
Beat Meeting, Civic Accountability) or inside the Neighborhood Issue Tracker.

| Domain | Primary public source | Class | Home in NIP | Note / hard limit |
|---|---|---|---|---|
| **A. Police service demand & emergency response** | 911 calls-for-service are **not** in the public crime dataset | **4** (CFS detail, response times) / **2** (arrest-flag proxy) | Trends ▸ Public Safety, as a stated gap | **Do not** compute a reporting rate as crime ÷ calls — the datasets cannot be linked and the denominator would be invalid. Keep CFS, dispatches, recorded crime, arrest-flagged incidents as **four distinct measures** |
| **B. Neighborhood problem resolution** | 311 `v6vf-nfxy` | **3** | **Issue Tracker** + Beat Meeting | Per-category closure semantics; never pool |
| **C. Traffic & pedestrian safety** | Traffic Crashes (crashes / people / vehicles) | **3** | Trends ▸ new *Safety beyond crime* section | Crash severity coding differs from crime; exposure denominator (VMT) unavailable |
| **D. Domestic violence & victimization** | crime `domestic` + description coding | **1/2** | Trends ▸ Public Safety (F7) | Strictest privacy tier; victim-service outcomes are **4/5** |
| **E. Victim services** | no public dataset identified | **4/5** | Civic Accountability, as a gap | Do not imply service availability |
| **F. Police–community interactions** | Complaints (COPA), use-of-force, stops are separate public datasets | **3** | Civic Accountability | Different universes from crime; never merged into a crime count |
| **G. Neighborhood quality of life** | 311 subsets (lighting, sanitation, graffiti), vacancy | **3** | Issue Tracker | Volume ≠ conditions |
| **H. Large events & service disruption** | permitted-events data; **UNVERIFIED** availability | **3** | Trends ▸ context layer | Needed for the sporting-event question (F11), still deferred |
| **I. Emergency management** | no routine public dataset identified | **5** | out of scope for now | — |
| **J. Service accessibility** | facility locations; GTFS transit | **3** | People & Housing / context | Access ≠ usage |
| **K. Public-facing administrative services** | 311 information-only calls; permits | **3** | Issue Tracker | `311 INFORMATION ONLY CALL` is geocoded to the 311 centre — **must be excluded** from any geography |
| **L. Interagency coordination** | 311 `owner_department` | **3** | Issue Tracker | Departmental routing is observable; coordination quality is not |

## Priority integration 1 — calls for service vs recorded crime

Public data does **not** include 911 calls for service, dispatch records, or response
timestamps; these require restricted access (**class 4**). NIP must therefore:
- present recorded crime and arrest-flagged incidents as the two measures it actually has;
- name calls-for-service and response time as **documented gaps**, not estimate them;
- **never** divide crime by calls to produce a reporting rate.

## Priority integration 2 — Neighborhood Issue Tracker

A single object with an explicit six-stage ladder, where each stage is a separate, evidenced
field — never collapsed into "resolved":

| Stage | Evidence required | Source | Available? |
|---|---|---|---|
| 1 · Reported | a request/incident record exists | 311, crime | after 311 ingestion |
| 2 · Acknowledged | agency/department assignment | 311 `owner_department` | yes, with 311 |
| 3 · Action documented | a published action record | permits, projects, TIF, aldermanic records | partial |
| 4 · System marked complete | `status = Completed`, `closed_date` | 311 | yes — **and this is not stage 5** |
| 5 · Conditions changed | subsequent measurement of the condition | crime, repeat 311, violations | sometimes |
| 6 · Causal effect established | comparison area + pre/post + alternatives | — | rarely; usually **not established** |

The tracker's core discipline: an administrative "Completed" is stage 4 evidence about a
*record*, not stage 5 evidence about a *street*. Recurring requests at the same block after
closure are the observable signal that stages 4 and 5 diverged.

---

# DELIVERABLE 5 — Geographic & Classification Integrity Report

**Beat definition — resolved; full evidence in the companion report, Part 1.** Summary:

- Using CPD's reported `beat` is **defensible, not a governance violation**; I withdrew the
  earlier "defect" classification.
- Mismatch with PIP is **stable 10.4–12.4%** across 2019–2026 (no vintage step); **0 of 885**
  mismatches lack coordinates; **84%** resolve to an adjacent beat in the same district.
- Decisive: **published coordinates are privacy-masked** — 3,438 distinct points for 7,817
  incidents, busiest point 96 incidents, 99.8% of points map to one masked block, and **74 of
  692 blocks carry more than one CPD beat**. CPD's field encodes finer location information
  than the coordinate does, so PIP cannot be more accurate at beat scale.
- Mismatch scales with polygon size: **ward 3.2% · CA 8.7% · beat 11.3%** — exactly as masking
  predicts. **Ward totals are unaffected** (selection is spatial).
- Recommendation: spatial for ward/CA selection; **CPD's field for beat attribution**; beat∩ward
  share from the **polygon**; disclose both; five named tests including a >3-point mismatch-rate
  alert.
- **Genuine bug (D8):** `incidents.py:171` filters on CPD-reported `ward` inside a spatially
  selected set — a `ward=20` filter silently drops **248 of 7,817 rows (3.2%)**.

**Classification integrity (this report):** IUCR codes are stable 2006–2026 for prostitution;
description wording drifts and must never be used as a join key — use IUCR. Broad categories
partition the total; the narrow `categories` block **overlaps** (burglary ⊂ property) and must
never be shown as a breakdown. New requirement: an **enforcement-generated** flag on category
metadata (prostitution, narcotics, gambling, liquor, weapons possession).

**Still open:** 16 of 21 beats straddle Ward 20 (0223 = 28.9% inside) with no disclosure; UI
truncation hides 14 of 26 types and 13 of 21 beats; the 2023 ward map is applied to all years.

---

# DELIVERABLE 6 — Statistical Methods Plan

Full plan in the companion report, Part 9 (period comparability, additive decomposition with
Σ = total-change validation, Kendall tau-b stability classification, Poisson plausible-variation
bands, publication thresholds, change-point as candidate-flagging only, persistence classes,
concentration curves, five sensitivity analyses, validation requirements). Additions from this
investigation:

| Method | Assumption | Validation test | Limitation |
|---|---|---|---|
| **Enforcement-sensitivity check** (new) | a category's arrest share indicates how enforcement-driven it is | compute arrest share per category per year; flag >50% as enforcement-generated | high arrest share can also reflect on-scene arrest for serious crime — the flag prompts a caveat, it does not classify by itself |
| **Discretionary vs victim-reported indexing** (new) | victim-reported series approximate underlying incidence better than discretionary ones | index both groups to a base year and compare shapes (verified: gambling −99% vs battery −47%) | neither group is a clean measure of incidence |
| **Release-to-release lag curve** (3F) | retained releases are comparable snapshots | recompute the same period from `bw-release-20260726` and `bw-release-20260921` (verified difference: 7,813 → 7,817 for Ward 20 2025) | only two releases retained today, so the curve starts coarse |
| Near-repeat (3B) | space-time clustering beyond baseline density | Knox ratio vs permutation null | **block-masked coordinates** make true near-repeat distances unmeasurable; report as exploratory only |
| Harm weighting (3E) | an external published weight set applies to Chicago categories | show counts beside every weighted figure; publish the weight table | weights are normative judgements imported from another jurisdiction |

---

# DELIVERABLE 7 — Data Source & Availability Matrix

The full matrix is in the companion report, Part 8 (crime, circumstances, beats, census,
parcels, permits, 311, jobs/LODES WAC vs RAC, TIF, education, transport). Additions and
corrections from this investigation:

| Item | Class | Detail |
|---|---|---|
| IUCR codes | **1** in production | `iucr` present in Bronze; the stable join key for classification over time |
| Arrest share by category | **2** unexposed | computable today; basis for the enforcement flag |
| Retained releases for lag analysis | **1** | `bw-release-20260726` + `bw-release-20260921` both on the production disk |
| 911 calls for service, dispatch, response times | **4** restricted | not in public data; do not estimate |
| Police complaints / use of force / stops | **3** additional public | separate datasets, separate universes |
| Traffic crashes | **3** | for domain C |
| Permitted large events | **3**, **UNVERIFIED** availability | needed before F11 |
| Victim services, emergency management | **4/5** | no routine public dataset identified |
| TIF 2025 Year-end Report | **3**, now **available** | `TIF_Projection_2025_Yearend_Report.pdf` (owner's local working copy, outside the repository) + text extraction; **not in repo**, not yet analysed; ward-share attribution rules still required |
| Prostitution prevalence | **5 — not feasible, not appropriate** | no dataset can support it; arrest counts must not be used as a proxy |

---

# DELIVERABLE 8 — Overview & Beat Meeting Integration

**Pipeline:** Trends calculation → tested function → YAML finding (`draft`) → review →
`published` → Overview card → deep link back to the exact Trends view → archived brief snapshot.
(Finding model, four-way classification, and the six-step editorial process are in the companion
report, Part 7.)

**Overview** carries only the conclusion, its numbers, its scope, its limits, and its link.
Classification is always visible: VERIFIED FINDING · CHANGE/ALERT · RESEARCH QUESTION · DATA GAP.

**Beat Meeting** is the same evidence re-cut for one beat and one audience:

| Section | Content | Source |
|---|---|---|
| This beat, this period | in-ward **and whole-beat** counts, change, stability class | V2/V3 |
| What is driving it | top category changes with counts first | V1 |
| Circumstances | settings, hour/day patterns, suppressed where thin | V4 |
| Persistence | elevated in k of N periods | V4 |
| Arrest indicator | flagged share, with the "not clearance" note | F2 |
| Questions for officers | generated from the evidence, resident-facing | template + findings |
| Resident observations | local knowledge the data cannot capture | manual |
| Documented follow-up | response register entries, with stage 1–6 status | Issue Tracker |

This preserves what made the original Woodlawn brief useful — a short, specific, resident-facing
document with questions attached — while fixing its geography (whole-CA → ward portion) and its
provenance (ad-hoc CSV → tested calculation).

---

# DELIVERABLE 9 — Phased Implementation Roadmap

| Tier | Content | Depends on | Ship alone? |
|---|---|---|---|
| **0 · Public-information corrections** | beat disclosure + whole-beat column; portion intersection shares + "counts are not a safety ranking"; surface freshness; remove UI truncations (26 types, 21 beats, explicit zeros); fix the frame-mixing filter (D8) | none | **Yes — recommended first** |
| **0b · Honesty quick wins** | **provisional badge** on recent periods (3F) + **enforcement-generated flag** on category metadata | Tier 0 | Yes; both are small, data-free, and prevent misreading |
| **1 · Recovery/exposure** | decide `/overview` endpoint (surface or retire); all-categories view; decomposition with Σ-reconciliation | 0 | Yes |
| **2 · Findings infrastructure** | `findings.yml`, `findings.py`, `/api/v1/findings`, CI validation, brief archive; Overview rebuilt (Public Safety findings only) | 1 | Yes |
| **3 · Crime Trends views** | V1–V4; F2 arrest-by-category (new); F3/F4 profiles; F5 circumstances; F6 burglary 3-way; F7 domestic battery; 3A repeat-location | 1 | Yes |
| **4 · Statistical methods** | tau-b, Poisson bands, thresholds, change-point candidates, 3G persistence, concentration curves, sensitivity panel | 3 | Yes |
| **5 · External ops ingestion** | 311 (V2-005) → Census blocks + ACS → LODES WAC/RAC → parcels/permits → crashes → TIF. One dataset per package | 2 | Sequential |
| **6 · Issue Tracker** | six-stage ladder over crime + 311 + vacancy + violations + responses | 5 (311 minimum) | After 311 |
| **7 · Civic accountability & SARA** | response register, assessment with comparison areas, 3C displacement; then the conditional questions (burglary × housing change; F11 events) | 5, 6 | Last |

**Smallest coherent first implementation: Tier 0 + Tier 0b.** Together they correct every
currently misleading element, add the two labels that prevent the most likely misreadings
(provisional recent data; enforcement-driven categories), touch `index.tsx`, `incidents.py`,
`crime_categories.yml` and one API field, need no new data, and are fully reversible.

---

# DELIVERABLE 10 — CPD Data Scientist Demonstration

**Recommended case study: "Why are reported prostitution incidents almost absent in Ward 20?"**

Selected over the burglary study because the evidence supports a **complete, defensible
conclusion** that a naive reading would get wrong — and because the conclusion is a caution
about a measure, which is the most valuable thing an analyst can contribute to an operational
discussion. No conclusion is forced: the answer is partly "this cannot be known", stated
plainly.

| Demonstrated skill | In this case study | Status |
|---|---|---|
| **Problem definition** | Recast the question from "is there no prostitution in Ward 20?" to "what does this variable measure, and what can it support?" | proposed analysis, verified inputs |
| **Data extraction** | 21 years × Bronze+Silver, joined on `id`, IUCR-level classification, ward/CA/beat geography | **executed this session** |
| **Data validation** | manifest checksums (21/21), per-year id-set equality, `source_removed` exclusion, YTD handling, 2023-ward-map disclosure | **executed** |
| **Statistical analysis** | full series 2006–2026; arrest-share analysis (99% vs 16.1% baseline); discretionary vs victim-reported indexing (gambling −99.0% · prostitution −97.3% · narcotics −86.7% · liquor −82.4% vs battery −47.1%) | **executed** |
| **Geographic analysis** | Ward 20 vs portions vs **whole** community areas vs beats vs citywide; ruled out clipping (whole Woodlawn CA = 0 in 2025); located the residual citywide (CA 56 = 70, CA 25 = 46) | **executed** |
| **Classification forensics** | IUCR stability 1505–1549; candidate absorbers quantified (human trafficking 1 → 18 cannot absorb ~6,800) | **executed** |
| **Visualization** | indexed discretionary-vs-victim-reported panel with an arrest-share underlay; small-multiple IUCR series; citywide-vs-ward index | proposed |
| **Written interpretation** | the series measures enforcement posture, not prevalence; Ward 20's collapse preceded the citywide one; documented policy changes are consistent but not established as causes | proposed, evidence verified |
| **Limitations** | prevalence unknowable from these data; no policy field to test; trafficking counts too small and too enforcement-dependent; 2023 ward map applied historically; 2026 partial | **stated** |
| **Decision support** | an **enforcement-sensitivity flag** applied across every category, so no future NIP finding, brief, or dashboard reads an activity-driven series as a condition measure — reusable, and it prevents a whole class of error | proposed |

**Working vs proposed:** the extraction, validation, statistical and geographic analyses above
were executed against production data in this session and their numbers are verified. The
visualizations, the enforcement flag, and their integration into NIP are proposed designs.

---

## Sources

Prostitution enforcement context:
[CAASE, *Policing & Enforcement of Prostitution Laws in Chicago* (2020)](https://www.caase.org/wp-content/uploads/2020/05/Report-PEOPL-Jan20-v1.3-WithAppx.pdf) ·
[WTTW coverage](https://news.wttw.com/2020/01/27/report-chicago-police-prioritize-arrests-of-sex-sellers-over-buyers-traffickers) ·
[CAASE on city strategy](https://www.caase.org/city-doubles-down-on-failed-efforts-to-end-prostitution/) ·
[Vice, on reduced discretionary enforcement](https://www.vice.com/en/article/what-happened-after-chicago-police-cut-down-on-busting-drug-possession-and-prostitution/)

Crime-intelligence practice (full list in the companion report):
[NYPD CompStat 2.0](https://compstat.nypdonline.org/) ·
[BOCSAR crime mapping guide](https://bocsar.nsw.gov.au/statistics-dashboards/crime-and-policing/guide-for-the-crime-mapping-tool.html) ·
[BOCSAR trend method (Kendall's tau-b)](https://dcj.nsw.gov.au/content/dcj/bocsar/bocsar-home/statistics-dashboards/crime-and-policing/using_crime_statistics.html) ·
[College of Policing SARA](https://www.college.police.uk/guidance/problem-solving-policing/sara-model) ·
[ASU POP Center SARA](https://popcenter.asu.edu/content/sara-model) ·
[Weisburd, law of crime concentration](https://onlinelibrary.wiley.com/doi/abs/10.1111/1745-9125.12070)

---

*Read-only investigation. No source code, configuration, data pointer, scheduler, deployment,
or repository state was changed. Production remains Render `e00665c`, `current` →
`bw-release-20260921`, scheduler OFF.*
