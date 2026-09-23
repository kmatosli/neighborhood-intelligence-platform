# NIP V2 — Analytical Redesign: Investigation & Design Report

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

**Scope:** read-only investigation of the live V2 release, its history, and its data

Every figure in this report was computed against the active September release during this
session. Claims I could not verify are marked **UNVERIFIED**. Illustrative wording is labelled
**ILLUSTRATIVE**.

---

## 0. Verified production baseline (checked, not assumed)

| Item | Verified value | How |
|---|---|---|
| `BW_DATA_DIR` | `/var/data/current` | SSH env |
| `current` → | `bw-release-20260921` | `readlink` |
| resolves to | `/var/data/bw-release-20260921` | `readlink -f` |
| active-release proof | `current/bronze/crime/2026.parquet` = 13,792,890 bytes (September; July is 8,860,824) | `stat` |
| Render commit | `e00665c` | `RENDER_GIT_COMMIT` on the instance |
| Scheduler | **OFF** | `BW_REFRESH_SCHEDULE` unset |
| Public API | `data_through 2026-09-06`, `status stale` | `/api/v1/freshness` |

The September release is confirmed **active**, not merely staged.

---

# PART 1 — THE BEAT-DEFINITION QUESTION (resolved)

## 1.1 Correction to my earlier classification

In my previous report I called the use of the CPD-reported beat a confirmed governance
defect. **That classification was wrong and I withdraw it.** The evidence below shows the
field choice is defensible; the real defects are non-disclosure, frame inconsistency, and one
genuine filter bug. This matters because it changes what should be built.

## 1.2 The two fields

| | `source_beat` (Bronze `beat`) | `spatial_beat_current` (Silver) |
|---|---|---|
| Definition | The beat CPD publishes on the record | Point-in-polygon of the **published coordinate** against the beat layer |
| Authority | CPD operational/records assignment | Geometry |
| Boundary layer | CPD's own, as of the record | `n9it-hstw`, downloaded 2026-07-12 (`data/reference/chicago/2026-07-12/police_beats.geojson`) |
| Temporal frame | beat at the time of the record | one current boundary set applied to all years |
| Input precision | derived before privacy masking | **inherits the masked coordinate** |

Districts in the repo are *derived* by dissolving the beat layer on its own `district` field
(manifest: "DERIVED, not downloaded"), so beats nest exactly inside districts by construction.

## 1.3 Vintage compatibility

Mismatch rate is **stable across years**, so there is no boundary-change step inside the
window:

| Year | Ward 20 incidents | beat mismatch | rate |
|---|---|---|---|
| 2019 | 8,204 | 925 | 11.3% |
| 2022 | 7,284 | 794 | 10.9% |
| 2023 | 8,384 | 888 | 10.6% |
| 2024 | 8,215 | 1,020 | 12.4% |
| 2025 | 7,817 | 885 | 11.3% |
| 2026 YTD | 5,333 | 556 | 10.4% |

A vintage break would appear as a step change. It does not. **Vintage is not the explanation.**

## 1.4 Cause decomposition (2025 Ward 20, 885 mismatches)

| Candidate cause | Finding |
|---|---|
| Missing coordinates | **Ruled out** — 0 mismatched records lack a spatial beat; all 885 are `geography_status = assigned` |
| Coordinate error / boundary proximity | **Dominant** — 739 of 885 (84%) resolve to a *different beat in the same district*, i.e. adjacent-beat disagreement |
| Cross-district disagreement | 146 (16%) |
| Source-assignment difference | Present, and inseparable from the above with public data |

**The decisive evidence — published coordinates are privacy-masked, not true locations.** For
Ward 20 2025 (7,817 incidents with coordinates):

- only **3,438 distinct coordinate pairs** (mean 2.3 incidents per point); the busiest single
  point carries **96** incidents
- **99.8%** of coordinate pairs map to exactly one masked block
- **74 of 692 blocks carry more than one CPD beat** — CPD's beat field therefore varies
  *within* a masked block, so it encodes finer location information than the published
  coordinate does
- mismatch rate among coordinate-shared records is 13.8%, above the 11.3% overall

Concrete consequence: beat 0233 has **514** incidents by PIP but **337** by CPD's field, and
the largest transfers are 0313→0233 (70), 0231→0233 (55), 0223→0233 (45) — all neighbouring
beats. Beat 0312: 1,129 (PIP) vs 1,087 (CPD).

**Conclusion.** PIP on a block-masked coordinate cannot be more accurate than CPD's own
assignment at beat scale. Substituting it would *lose* information and would silently move
~11% of records between beats.

## 1.5 What the mismatch does and does not affect

| Affected? | What |
|---|---|
| **No** | Ward totals. Selection uses `spatial_ward_current`; both fields agree on the ward for 96.8% of records and selection is unambiguous |
| **No** | Ward-level trend, category decomposition, arrest share — none use beat |
| **Yes** | Beat attribution, beat counts, beat shares, "top beat" headlines, issue cards |
| **Yes** | Any beat-level comparison against CPD's own published beat figures |

Scale of the frame difference by polygon size — exactly as masking error predicts:

| Geography | Mismatch rate (PIP vs CPD-reported), Ward 20 2025 |
|---|---|
| Ward | **3.2%** (248 of 7,817) |
| Community area | **8.7%** (683) |
| Beat | **11.3%** (885) |

Reverse direction: CPD-reported ward 20 has 7,950 records; 329 of them fall outside Ward 20
by PIP.

## 1.6 Recommended field per purpose

| Purpose | Use | Why |
|---|---|---|
| Ward / community-area selection and all ward totals | **`spatial_ward_current`, `spatial_community_area`** (unchanged) | The polygons are large relative to masking error, and the existing rule exists to avoid "ward at time of record" drift as ward maps change |
| Beat attribution, beat concentration, beat profiles | **`source_beat` (CPD-reported)** — i.e. keep today's behaviour | Finer than the masked coordinate; matches what CPD and beat meetings use; reconcilable with CPD's published figures |
| Beat ∩ ward denominators ("how much of this beat is in Ward 20") | **`spatial_beat_current` from the beat polygon**, computed on the geometry, not on incidents | A geometric question deserves a geometric answer |
| Incident-table geography columns | CPD-published fields, **labelled "as published by CPD"** | They are source facts |
| Incident-table geography **filters** | **Defect — see D8** | Mixing frames silently drops rows |

## 1.7 Disclosure and tests

**Disclosure** (new methodology note + on-page footnote wherever a beat appears):
> "Beat figures use the police beat CPD publishes on each record. Ward and neighbourhood
> figures use the published coordinate placed in the 2023 ward map. The two disagree for about
> 11% of Ward 20 records because published coordinates are masked to the block, so a beat
> boundary cannot be resolved from them. Beat counts here will therefore differ slightly from
> a map-based count, and beats extend beyond Ward 20 — see the whole-beat column."

**Tests to add:**
1. `beat_mismatch` rate per year stays within a stated band (alert if it moves >3 points — that would signal a real boundary change).
2. Beat counts sum to the selected geography's total; shares sum to 1.0 ± 0.001.
3. For each displayed beat, publish both in-ward and whole-beat counts; assert in-ward ≤ whole-beat.
4. A regression test asserting the ward total is invariant to the beat field chosen.
5. No filter may mix frames: a test that the row count of a spatially-selected set is unchanged by applying a CPD-field filter for the same geography.

---

# PART 2 — DELIVERABLE 1: EXISTING CAPABILITY INVENTORY

| Capability | Classification | Evidence |
|---|---|---|
| Crime Bronze+Silver 2006–2026, PIP ward/CA/beat/district/tract/block-group | Working | 6,266,664 rows; 21 years; verifier PASS |
| `/years`, `/geographies`, `/overview/{geo}`, `/pulse/{geo}`, `/incidents/{geo}`, `export.csv`, `/freshness` | Working | verified in production |
| Overview (Pulse) page — metrics, monthly chart, beat concentration, driver table, issue cards, data-trust panel | Working — **the only page with live data** | `apps/web/src/routes/index.tsx` |
| Geography + year context in the URL (`?geo=`, `?year=`) | Working | `useGeography.ts`, `useYear.ts` |
| Trends page | **Previously proposed, never implemented** — placeholder in V1 *and* V2 (87 lines, 0 API calls, `planned=` text only) | `trends.tsx`; `git show 502c351:...trends.tsx` |
| Beat Meeting, Community Change, Civic Accountability pages | **Previously proposed, never implemented** — 0 API calls each | `beat-meeting.tsx`, `authority.tsx`, `community-change.tsx` |
| `category_drivers` — every CPD primary type, current vs prior, untruncated | **Present but hard to find** (API complete, UI shows 12 of 26) | `pulse.py:153`; `index.tsx:466` |
| `monthly_categories`, `broad_categories`, `beats` (all), `issues` | Present, partly surfaced | `PulseResponse` |
| `/overview/{geo}` categories endpoint | **Built but unused by the UI** | V2-003 §1 |
| Arrest data | Working, but only as one ward-wide summary (count/total/percent + prior) | `ArrestSummary` |
| Arrest **by category** visualization | **Previously proposed, never implemented** — no such component or notebook in any commit on any branch | `git log --all` (no `.ipynb` ever) |
| Domestic-battery analysis | **Never in the product.** Figures were produced ad hoc from a review CSV | see Part 3 |
| Review tooling (`audit_2026.py`, `review_2026.py`, `find_incident.py`) | Working, local-only, gitignored outputs | `scripts/` |
| `/freshness` surfaced in the UI | **Missing** — no component consumes it | grep found none |
| Findings / intelligence-brief model | Does not exist | — |
| 311, Census/ACS, jobs, TIF, parcels, permits | **No data** — disk holds only crime + boundary geometry | `data/` listing |

## Recovered: the original Woodlawn Beat Meeting Brief calculation

Reproduced **exactly** from `data/review/woodlawn_2026_incidents.csv` (1,919 rows, produced by
`scripts/audit_2026.py`):

| Brief figure | Reproduced | Definition established |
|---|---|---|
| 380 battery reports | **380** | `primary_type == BATTERY` |
| 193 "specifically coded domestic battery" | **193** | **`description` contains "DOMESTIC"** |
| ~51% | **50.8%** | 193/380 |
| ~69% in apartments | **69.4%** (134/193) | `location_description == APARTMENT` |

**The definition was CPD's detailed `description`, not the `domestic` boolean.** The boolean
gives **206**. All 193 description-coded records are also flagged; 13 flagged batteries are
not description-coded. Geography was the **whole Woodlawn community area**, period
**2026-01-01 → 2026-07-02**, on pre-V2 data. These are not Ward 20 figures and must never be
republished as such.

---

# PART 3 — DELIVERABLE 2: VERIFIED DEFECTS AND REGRESSIONS

Ordered by public-information risk. Each is verified; none is speculative.

**D1 — Beat figures are ward-clipped and beat definition is undisclosed. (Confirmed)**
Of 21 beats appearing in Ward 20 2025, **16 are <95% inside the ward**: 0223 **28.9%**, 0711
55.2%, 0321 53.8%, 0935 63.5%, 0233 **66.9%**, 0312 99.6%. Nothing on the page says the counts
are ward-clipped, and nothing says which beat definition is used. A resident taking "Beat 233"
to a CPD beat meeting — which covers the whole beat — is comparing different universes.
*Fix:* disclosure + a whole-beat column. No recomputation needed.

**D2 — Detailed categories and beats truncated in the UI, not the API. (Confirmed)**
`index.tsx:466` `.slice(0, 12)` on a change-sorted list; Ward 20 2025 has **26** primary
types, so 14 are unreachable. `index.tsx:391` `beats.slice(0, 8)` hides 13 of 21.

**D3 — PROSTITUTION is not missing data. (Confirmed — not a defect)**
Mapped at `config/crime_categories.yml:116` → `public_order`; returned untruncated by
`category_drivers`; **Ward 20 has 1 record in 2025 and 0 in 2026**. Invisible because of D2
plus genuine rarity. An All-Categories view must render an explicit **0**, distinct from
"no data".

**D4 — Arrest-by-category is new functionality, not a regression. (Confirmed)**
No implementation ever existed. Data supports building it.

**D5 — The 380/193/51%/69% figures are whole-community-area, 2026-H1, pre-V2. (Confirmed)**
Republishing them as current Ward 20 figures would breach the governance rule.

**D6 — `/overview/{geo}` is built but unused.** Duplicate surface to maintain or retire.

**D7 — Freshness is not visible to the public.** `/freshness` currently reports `stale`
(16 days behind, last successful refresh 2026-09-15) and the page shows only `data_through`.
The UI presents no staleness signal at all.

**D8 — Frame-mixing filter bug in the incidents table. (Confirmed — genuine bug)**
`incidents.py:171` filters on the CPD-reported `ward` inside a set already selected by
`spatial_ward_current`. For Ward 20 2025 a `ward=20` filter **silently drops 248 of 7,817
rows (3.2%)**. Same pattern for `district` and `beat`. Either drop these filters or label them
explicitly as CPD-published-field filters and state the effect.

**D9 — Trends/Beat Meeting/Community Change/Accountability are placeholders.** Not
regressions — never built. But the navigation implies analysis that does not exist.

**Not defects:** the Woodlawn-vs-Englewood contrast (Part 5); `data_through 2025-12-31` on a
2025 view; beat `share` denominators (verified: beat counts sum to 7,817 and shares to 1.000);
the use of CPD-reported beat (Part 1).

---

# PART 4 — DELIVERABLE 3: CRIME TRENDS ARCHITECTURE

## 4.1 Principle

One investigation, ten linked questions — not ten charts. A single control bar persists
across every view, and every view states its geography, denominator, and period.

## 4.2 Persistent controls

| Control | Values | Status |
|---|---|---|
| Geography | Ward 20 · any of 9 CA portions · whole CA (context only, clearly marked) · beat | portions ready; whole-CA ready; beat ready |
| Category | 6 broad · all 26 CPD primary types · detailed `description` | ready |
| Location setting | 72 distinct `location_description` values | ready |
| Domestic | description-coded · flag · either (three separate measures) | ready |
| Arrest | flagged / not flagged | ready |
| Period | YTD-comparable · full year · rolling 12m · custom range · multiyear | ready |
| Comparison | prior period · same period prior year · 5-year baseline | ready |

**Rule:** whole-CA and portion figures may never appear in the same series without an explicit
frame label.

## 4.3 User journey

```
OVERVIEW finding: "Crime fell 4.6% in 2025, unevenly across types"
   │  deep link carries ?geo=ward20&year=2025&compare=2024
   ▼
TRENDS ▸ Public Safety ▸ Composition & Change
   │  decomposition table: every type, count, Δ, %Δ, share, contribution to net change
   │  reconciliation line: Σ contributions = −398 = 7,817 − 8,215   ✓
   ▼  user clicks BURGLARY (+12 in 2025; 250 → 262 in 2026 YTD)
CATEGORY VIEW: burglary over time, by portion, by beat, by setting, by hour/DOW, arrest share
   ▼  user clicks beat 0312 (14.4% of ward incidents)
BEAT PROFILE: composition, Δ drivers, settings, temporal, arrest, persistence,
   │           in-ward vs whole-beat columns side by side
   ▼
CIRCUMSTANCES EXPLORER: cross-tab setting × hour × category, small cells suppressed
   ▼
METHODS & LIMITATIONS  →  DOCUMENTED RESPONSE (if any)  →  ASSESSMENT
```

## 4.4 Feature specifications

Each entry: analytical question · data required · method · limitation · journey position.

**F1 Category change decomposition** — *Which types explain the movement?* Crime Silver+Bronze
(have). For each type: current, prior, Δ, %Δ, share of current, **contribution to net change**
(Δ_type / Δ_total). Σ contributions must equal the total change. Limitation: broad categories
overlap in the narrow `categories` block and do **not** sum — only `broad_categories` partition
the total. Never show %Δ without counts (1 → 3 is +200%). Entry point from every Overview
public-safety finding.

**F2 Arrest-indicator analysis** *(new build)* — *What does the arrest flag show?* `arrest`
bool (have). Per category and geography: total, flagged, not flagged, flagged share, prior
comparison. Limitations, stated on the view: the flag is **as of the record's last update**,
there is **no arrest date**, so timing cannot be measured; it drifts as old records are
updated; it is **not** a clearance, charge, conviction, or investigative-quality measure; case
dispositions are **not available** in this dataset. Small-N guard before publishing a share.

**F3 Beat profile** — *Why is this beat large?* Composition, change drivers, settings,
temporal, arrest, persistence, own historical baseline. **Two columns throughout: in-ward and
whole-beat.** Uses CPD-reported beat (Part 1.6) with the geometric in-ward share computed from
the polygon. Limitation: 16 of 21 beats straddle the ward.

**F4 Neighborhood-portion profile** — same structure per portion, always with intersection
share. **Never rank portions by raw count as "safety"** (Part 5).

**F5 Incident-circumstances explorer** (BOCSAR-informed) — category × setting × hour × DOW ×
month × beat × portion × arrest × domestic. All fields present: `location_description` 99.7%
populated, 72 distinct values; hour and day-of-week parse for 100% of records, 24 distinct
hours, 7 days, only 4.2% exactly midnight (so time-of-day is usable, with that caveat noted).
Limitation: no offender/victim detail exists and none may be inferred.

**F6 Burglary investigation** — *Residential vs commercial distinguishable?* **Partly.**
Verified on Ward 20 2025 (n=250): `description` separates `FORCIBLE ENTRY` 93, `BURGLARY FROM
MOTOR VEHICLE` 68, `UNLAWFUL ENTRY` 67, `HOME INVASION` 15, `ATTEMPT FORCIBLE ENTRY` 7;
`location_description` gives APARTMENT 97, STREET 54, RESIDENCE 18, RESIDENCE-GARAGE 17,
COMMERCIAL/BUSINESS OFFICE 4. A residential-ish classifier over `location_description`
captures **135 of 250 (54%)**, leaving 115 unclassifiable — including 54 "STREET" which are
largely vehicle burglaries. **Recommendation:** publish a three-way split — residential /
commercial / vehicle-or-unclassified — and never a two-way residential-vs-commercial split,
which would force 46% of records into a wrong bucket.

**F7 Domestic-battery investigation** — recover and re-run on the September release for
matching current and prior periods, reporting the **description-coded** and **flag** measures
as two separate series wherever they differ (193 vs 206 in the original window). Views:
domestic vs other battery, setting, hour, DOW, monthly, beat, portion. Privacy: block-level
minimum aggregation, small-count suppression, no setting × time × beat cross-tabs thin enough
to single out an address or household.

**F8 Time-series and seasonality** — see Deliverable 7.

**F9 Hotspot persistence** — see Deliverable 7.

**F10 SARA workflow and documented response** — see Deliverable 4.6 and Part 8.

**F11 Sporting-event exploratory question** — **recommend deferring.** Requires event
schedules with start/end times (Bears/Bulls/Sox/Cubs/Fire; not ingested), a matched-control
design (same weekday/hour/season without events), and pre-registration of the comparison.
Confounders: weekend/holiday effects, weather, alcohol-service hours, reporting-propensity
shifts. It must be framed as a question and must never be published as evidence that events
cause domestic violence. Keep it as a documented research question until 311 and housing work
land.

---

# PART 5 — NEIGHBORHOOD COMPOSITION (resolves the Woodlawn/Englewood puzzle)

Ward 20 2025, total **7,817** — portion counts sum exactly to the ward total:

| Portion | In-ward incidents | % of ward | Whole CA citywide | Share of CA inside Ward 20 |
|---|---|---|---|---|
| Woodlawn | 2,962 | 37.9% | 3,848 | **77.0%** |
| Washington Park | 1,843 | 23.6% | 2,459 | 74.9% |
| New City | 1,010 | 12.9% | — | — |
| Englewood | 747 | 9.6% | 5,086 | **14.7%** |
| Fuller Park | 429 | 5.5% | — | — |
| Greater Grand Crossing | 299 | 3.8% | — | — |
| Grand Boulevard | 270 | 3.5% | — | — |
| Hyde Park | 227 | 2.9% | — | — |
| Kenwood | 30 | 0.4% | — | — |

**There is no defect.** Englewood has *more* citywide incidents than Woodlawn (5,086 vs
3,848), but only 14.7% of Englewood lies inside Ward 20 versus 77.0% of Woodlawn. The
apparent disparity is the intersection share, and the UI must show that share next to every
portion. Kenwood (30) is below any reasonable publication threshold for category slices.

**Denominator guidance:** raw counts answer "where did reported incidents occur in this ward",
nothing more. Per-capita rates require Census block-level population (**not ingested**;
block groups on disk have only 13 of 92 fully inside the ward, so apportionment is mandatory).
Per-area rates are computable today from the polygons but answer a different question. Until a
population denominator exists, publish counts and shares only, and say why.

---

# PART 6 — DELIVERABLE 4: EXTERNAL PRACTICE COMPARISON

## 6.1 NYPD CompStat / CompStat 2.0

*What it does:* recurring (weekly) management reporting on seven major crime categories at
city, borough and precinct level, with historical comparison, and a public interactive portal
that added date, time and specific crime type detail that earlier reporting lacked; organised
around geographic accountability and follow-up.
*Problem addressed:* making change visible on a fixed cadence and attaching it to a
geographic unit someone is answerable for.
*NIP today:* one-off page load, no cadence, no archive.
*Buildable on current public data:* a **recurring Ward 20 / portion / beat brief** on a fixed
cadence, with category-level change, prior-period comparison, and an **archive of past briefs**
so a finding's evidence is preserved. This is the single most transferable idea.
*Needs more data:* none for the reporting itself.
*Needs restricted CPD access:* deployment, staffing, response follow-up — NIP has none of
this and must not imply otherwise.
*Safeguards:* no ranking of commanders or neighbourhoods; a fixed cadence must not turn into
pressure to show declines.

## 6.2 NSW BOCSAR

*What it does:* a crime mapping tool with Rate Map / Table / Trend / Charts / Hotspot views
from 1995; seven filters including **premises type**, alcohol-related, domestic-violence-related,
day type and time; LGA tables covering 60+ offence types with premises type, month and time of
day; and an explicit trend method — **Kendall's tau-b rank-order correlation (p<.05)** to
classify a series as rising, falling, or **stable**.
*Problem addressed:* letting the public interrogate circumstances, and refusing to call noise
a trend.
*NIP today:* no circumstances explorer; no trend test; percentage changes presented without a
stability judgement.
*Buildable now:* the circumstances explorer (F5) — `location_description` is 99.7% populated
with 72 values and time-of-day parses for 100% of records; and **adopting a tau-b-style
stability test** so NIP can say "stable" instead of reporting every wiggle.
*Needs more data:* population denominators for true rate maps.
*Safeguards:* premises detail for domestic and sexual offences needs stricter aggregation than
BOCSAR applies at LGA scale, because Ward 20 portions are far smaller than an LGA.

## 6.3 UK College of Policing — POP and SARA

*What it does:* SARA — Scanning, Analysis, Response, Assessment — as the standard
problem-solving model; guidance informed by a 2019 national Problem Solving and Demand
Reduction Programme study plus a rapid evidence assessment and a systematic review. Assessment
is identified as the most demanding stage, and evidence-based practice is built in precisely
through requiring that the response be tracked and its effect reliably determined.
*Problem addressed:* stopping analysis from ending at description.
*NIP today:* describes; does not structure problems or assess responses.
*Buildable now:* Scanning and Analysis in full from crime data; a **Response register** of
documented public actions; Assessment only where a comparison area and pre-period exist.
*Needs more data:* the response records themselves (city/aldermanic/CPD publications).
*Safeguards:* a documented response must be distinguished from an inferred one, and a decline
after an action must never be presented as caused by it.

## 6.4 ASU Center for Problem-Oriented Policing

*What it does:* problem definition, analysis of incident circumstances, response selection and
evaluation, with the SARA model as its spine.
*Transferable:* the discipline of defining a problem narrowly enough to be actionable —
"burglary" is not a problem, "forcible-entry apartment burglary in beat 0312 on weekday
afternoons" is.
*NIP today:* no problem-definition object.
*Buildable now:* a problem record with category, geography, setting, time window, persistence
evidence, and the questions it raises.

## 6.5 Crime concentration and persistence research

Weisburd's law of crime concentration finds roughly **2–6% of street segments produce 50% of
crime**, with a bandwidth near 4% at 50% concentration; concentration is stable over time but
sensitive to strategy, some hot spots persist for over a decade (~5% of block-long segments)
while others disappear or move. Near-repeat victimisation is well established for residential
burglary.
*Transferable:* concentration should be **measured and reported as a statistic** (what share
of blocks accounts for half of reports), and hotspots should be classified by **persistence**,
not just current level.
*NIP today:* a single "repeat block" issue card threshold.
*Buildable now:* concentration curves and persistence classification at masked-block and beat
level — 692 distinct blocks in Ward 20 2025, which is enough to compute a concentration curve.
*Limitation:* true street-segment analysis is **not possible** — coordinates are block-masked
(3,438 distinct points for 7,817 incidents), so NIP's finest honest unit is the masked block,
which is coarser than the segment unit in that literature. This must be stated rather than
papered over.

## 6.6 What NIP must not claim

No access to internal CPD systems — no dispatch, no calls for service, no investigative
records, no case dispositions, no deployment or staffing. Every capability above is built on
published data only. And no feature should be adopted merely because another agency uses it.

---

# PART 7 — DELIVERABLE 5: OVERVIEW INTELLIGENCE-BRIEF WIREFRAME

```
┌ Ward 20 Neighborhood Intelligence ──────── [Ward 20 ▾] [2025 ▾] ─────┐
│ Brief of 2026-09-22 · crime data through Sep 6, 2026                  │
│ ⚠ Refresh stale: 16 days since last successful update  ▸ why          │
├───────────────────────────────────────────────────────────────────────┤
│ LEAD FINDINGS                                                         │
│ ┌───────────────────────────────────────────────────────────────────┐ │
│ │ F-001 · PUBLIC SAFETY · VERIFIED FINDING                          │ │
│ │ Reported crime fell 4.6% in 2025, but the decline is uneven        │ │
│ │ across crime types.                                               │ │
│ │ 7,817 reports in 2025 vs 8,215 in 2024 (−398)                      │ │
│ │ Ward 20 · CPD ijzp-q8t2 · full-year 2025 vs full-year 2024         │ │
│ │ Limits: reports, not convictions; city revises records             │ │
│ │ ▸ See which types explain the change (26 types, reconciled)        │ │
│ └───────────────────────────────────────────────────────────────────┘ │
│ ┌ F-002 · PUBLIC SAFETY · CHANGE / ALERT ──────────────────────────┐  │
│ │ Burglary is running above last year while overall crime falls.    │  │
│ │ 262 reports in 2026 YTD vs 250 in full-year 2025  ⚠ periods not   │  │
│ │ comparable — needs YTD-vs-YTD before publication  [DRAFT]         │  │
│ └──────────────────────────────────────────────────────────────────┘  │
├───────────────────────────────────────────────────────────────────────┤
│ FINDINGS BY DOMAIN                                                    │
│ Public Safety ................ 2 findings      ▸ Trends              │
│ People & Housing ............. DATA GAP — no census/parcel data  ▸why│
│ City Services ................ DATA GAP — 311 not ingested       ▸why│
│ Economic Conditions .......... DATA GAP                          ▸why│
│   └ Jobs & Unemployment ...... DATA GAP — LODES/ACS not ingested ▸why│
│ Public Investment ............ DATA GAP — TIF not ingested       ▸why│
│ Education & Youth ............ not assessed                          │
│ Transportation & Access ...... not assessed                          │
├───────────────────────────────────────────────────────────────────────┤
│ NEIGHBORHOOD DIFFERENCES   (Ward 20 portions — not whole CAs)         │
│ Woodlawn ............. 2,962  37.9% of ward   (77% of the CA is here) │
│ Washington Park ...... 1,843  23.6%           (75% of the CA)         │
│ New City .............. 1,010  12.9%                                  │
│ Englewood .............. 747   9.6%  (only 15% of the CA is in ward)  │
│ … Kenwood ............... 30   0.4%  ⚠ too few to break down further  │
│ Counts are not a safety ranking — no population denominator yet ▸why  │
├───────────────────────────────────────────────────────────────────────┤
│ QUESTIONS RAISED BY THE EVIDENCE            [RESEARCH QUESTION]       │
│ Q-01 Are burglaries concentrated where housing-market change is       │
│      greatest?   Needs: parcels, permits, values   ▸ what's required  │
│ Q-02 Does beat 0233's concentration persist, or is it this year only? │
│      Computable today                          ▸ open the analysis    │
├───────────────────────────────────────────────────────────────────────┤
│ DOCUMENTED PUBLIC RESPONSE                                            │
│ No responses documented in the available data.                        │
│ (NIP records only published actions; absence here means not           │
│  documented, not that nothing happened.)                              │
└───────────────────────────────────────────────────────────────────────┘
```

**Verified in F-001:** 7,817 / 8,215 / −4.6% / −398. **F-002 is DRAFT and ILLUSTRATIVE** — the
250-vs-262 comparison mixes a full year with a YTD period and must not publish in that form.

## 7.1 Finding model

Proposed: stored in `config/findings.yml` (not yet created), version-controlled and reviewed:

```yaml
- id: F-001
  topic: public_safety
  subtopic: overall_trend
  classification: verified_finding      # verified_finding | change_alert | research_question | data_gap
  headline: "Reported crime fell 4.6% in 2025, but the decline is uneven across crime types."
  observation: "..."                    # plain language, no jargon
  evidence:
    - {label: "2025 reports", value: 7817, period: "2025-01-01..2025-12-31"}
    - {label: "2024 reports", value: 8215, period: "2024-01-01..2024-12-31"}
    - {label: "change", value: -398, unit: reports}
  baseline: prior_full_year             # and/or five_year_same_period
  source: {dataset: ijzp-q8t2, release: bw-release-20260921, data_through: 2026-09-06}
  geography: {scope: ward20, kind: ward, intersection_share: null}
  reporting_period: "2025 full year"
  comparison_period: "2024 full year"
  calculation_ref: findings.overall_change
  freshness: {status: stale, last_successful_refresh: "2026-09-15T03:10:39Z"}
  limitations: ["reports not convictions", "city revises records after publication"]
  destination: {route: /trends, anchor: composition, params: {geo: ward20, year: 2025, compare: 2024}}
  status: published                     # draft | in_review | published | retired
  reviewed_by: "<name>"
  reviewed_at: "2026-09-22"
```

## 7.2 Editorial review process

1. **Calculate** — the number comes from a function in `presentation/findings.py` with a unit
   test asserting the exact published value. No number reaches a finding except through code.
2. **Draft** — finding authored in YAML as `draft`; not served publicly.
3. **Review** — a second pass re-runs the calculation independently and checks geography
   label, period comparability, baseline choice, limitations, and classification. A YTD-vs-full-year
   comparison (F-002) fails review.
4. **Publish** — status flipped in a commit, so publication is attributable and reversible.
5. **Continuous validation** — CI recomputes every published finding against the current
   release; a mismatch fails the build and the finding is auto-demoted to `in_review` rather
   than silently drifting.
6. **Archive** — each brief is snapshotted (findings + numbers + release id + data_through) so
   a historical finding stays reproducible after the data moves. This is what makes a recurring
   brief honest.

No public-facing conclusion is ever generated dynamically by an LLM.

---

# PART 8 — DELIVERABLE 6: DATA AVAILABILITY MATRIX

Classification: **PROD** in production · **UNEXPOSED** built but not surfaced · **MISSING-PUBLIC**
public data not ingested · **RESTRICTED** needs internal CPD access.

| Capability | Data status | Source / coverage | Geographic resolution | Limitations |
|---|---|---|---|---|
| Crime counts, trends, categories | **PROD** | `ijzp-q8t2`, 2006→2026-09-06 | point→ward/CA/beat/district/tract/BG | reports not convictions; city revises; recent weeks incomplete |
| All 26 primary types, monthly categories | **UNEXPOSED** | same | same | UI truncates to 12 |
| Arrest flag | **PROD** (summary) / **UNEXPOSED** (by category) | same | same | flag at last update; **no arrest date**; not clearance/conviction |
| Case dispositions, clearance | **RESTRICTED** / separate source | — | — | absent from this dataset; must be stated |
| Calls for service, dispatch, deployment | **RESTRICTED** | — | — | NIP has no access; never imply otherwise |
| Incident circumstances (setting, hour, DOW) | **PROD** | `location_description` 99.7% populated, 72 values; 24 hours; 7 days | masked block | 4.2% exactly midnight; no offender/victim detail |
| Domestic (coded vs flagged) | **PROD** | `description`, `domestic` | masked block | two different measures — report separately |
| Burglary residential/commercial/vehicle | **PROD, partial** | `description` + `location_description` | masked block | only 54% classifiable as residential-ish; use a 3-way split |
| Beat analysis | **PROD** | CPD `beat` + beat polygon | beat; beat∩ward geometric | 11% PIP/CPD disagreement; 16/21 beats straddle ward |
| Street-segment concentration | **not possible** | — | masked block is the floor | coordinates block-snapped (3,438 points / 7,817 incidents) |
| Population, households, tenure, vacancy | **MISSING-PUBLIC** | Census 2020 blocks; ACS 5-yr | block nests well; **BG: only 13 of 92 fully inside → apportionment required** | needs `CENSUS_API_KEY`; ACS uses 2020 tracts, disk has 2010 |
| Income, poverty | **MISSING-PUBLIC** | ACS 5-yr | BG/tract | margins of error must be published |
| Property values / change, parcels | **MISSING-PUBLIC** | Cook County Assessor `pabr-t5kh` (1.86 M, lat/lon, class) | point→portion | assessment ≠ market value |
| Permits / demolitions / violations | **MISSING-PUBLIC** | `ydr8-5enu` (847 k), `22u3-xenr` (2.0 M) | point | administrative activity, not conditions |
| Vacant land / buildings | **MISSING-PUBLIC** | `aksk-kvfp` (20,770), `kc9i-wq85` (5,012) | point | city-owned only / complaint-based |
| 311 service requests | **MISSING-PUBLIC** | `v6vf-nfxy`, 14.6 M rows, 2018-07→2026-09; Ward 20 144,808 | lat/lon→PIP (**never** the dataset's own `ward`) | post-2018 taxonomy only; exclude `311 INFORMATION ONLY CALL`; `closed_date` semantics differ per department — never pool; no reopen field |
| Streetlight outages, vacant-building complaints | **MISSING-PUBLIC** | 311 subsets | point | volume ≠ service quality |
| **Unemployment, labor force, EPOP** | **MISSING-PUBLIC** | ACS S2301 (BG/tract); BLS LAUS (county/metro only) | ACS: BG w/ apportionment | **never substitute citywide/county rates for Ward 20**; large MOEs at BG |
| **Jobs located in Ward 20** | **MISSING-PUBLIC** | LEHD **LODES WAC** | 2020 census block — **best fit for portions** | imputation noise at block level; excludes some self-employed/federal |
| **Jobs held by Ward 20 residents** | **MISSING-PUBLIC** | LEHD **LODES RAC** | same | distinct from WAC — must never be conflated |
| Industry, earnings bands | **MISSING-PUBLIC** | LODES segments; ACS | block / BG | broad bands only |
| Commuting, transit access to jobs | **MISSING-PUBLIC** | LODES OD; ACS journey-to-work; GTFS | block / BG | access ≠ usage |
| Youth employment | **MISSING-PUBLIC** | ACS by age | tract | small samples, wide MOEs |
| Training / apprenticeship, local hiring outcomes | **MISSING-PUBLIC**, likely unavailable | IDES, program records | program | hiring outcomes rarely published at this geography — likely a permanent gap |
| TIF districts / balances / projects | **MISSING-PUBLIC** | TIF district boundaries + reports; 2025 Year-end Report PDF **not in repo** (**UNVERIFIED** — owner's Downloads, 189 pp) | districts ≠ ward; projects address-level | **never attribute a district balance to the ward** |
| Development projects, RDA/IGA, SBIF | **MISSING-PUBLIC** | portal datasets | address→portion | commitments ≠ expenditures |
| Education: enrollment, absenteeism, graduation | **MISSING-PUBLIC** | CPS school-level | **school ≠ residence** — attendance boundaries only partly align | a school in the ward serves pupils outside it; do not present as a ward measure without stating this |
| Transportation: transit service, travel time | **MISSING-PUBLIC** | GTFS, ACS | stop/route | service ≠ access ≠ usage |

**Education & Transportation recommendation:** do **not** create tabs. Education data is
school-based and does not map cleanly to a ward of residence; transit data measures service,
not opportunity. Both can contribute a single contextual finding later if a defensible measure
emerges. Adding tabs now would violate "do not create tabs merely because datasets exist".

---

# PART 9 — DELIVERABLE 7: STATISTICAL AND GEOSPATIAL METHODS PLAN

## 9.1 Period comparability (prerequisite for everything)

Only compare like with like: YTD-to-the-same-day-of-year, or full year to full year. The
current data stops 2026-09-06, so any 2026 comparison must be 2026-01-01→09-06 against
2025-01-01→09-06. **F-002 in the wireframe fails this test and is marked DRAFT for that
reason.** Assumption: reporting propensity is stable across the compared windows — which the
platform must flag as an assumption, not a fact.

## 9.2 Change decomposition

Additive contribution: for each type, Δ_type = current − prior, contribution = Δ_type /
Δ_total. **Validation: Σ Δ_type ≡ Δ_total** (for 2025 vs 2024, Σ must equal −398). Use
`broad_categories` when a partition is required; the narrow `categories` block overlaps
(burglary ⊂ property) and must never be presented as a breakdown of the total.

## 9.3 Trend classification, not wiggle reporting

Adopt a **Kendall tau-b rank-order test** on the monthly series (BOCSAR's approach) to
classify a series as rising, falling, or **stable** at p<.05, reported alongside the counts.
Supplement with a 12-month rolling mean for presentation and a 5-year same-month range band
for context. Assumptions: monotonic trend detection only — tau-b will not find a turning
point. Limitation: significance is not importance; a statistically clear 2% drift may be
operationally irrelevant, and the platform must never substitute one for the other.

## 9.4 Uncertainty and small counts

Counts are not a sample, but they are realisations of a variable process, so present a
**Poisson-based interval** (e.g. ±1.96√n) as a plausible-variation band, with the explicit
caveat that it assumes independence, which clustered crime violates. Publication thresholds:
no %Δ where prior < 20; no category slice below 10; suppress cells below 5 in any cross-tab.
Kenwood (30 incidents for the whole year) cannot support any category breakdown.

## 9.5 Seasonality

Compare same-month-prior-year and same-quarter; compute a simple monthly seasonal index from
a 5-year baseline. Do **not** apply automated seasonal adjustment (X-13/STL) to small
neighbourhood series — the adjustment would be dominated by noise. State that summer peaks in
violent crime are expected, so a July rise is not news unless it exceeds the seasonal band.

## 9.6 Change-point and persistence

Change-point: a simple, explainable method (CUSUM or binary segmentation on the monthly
series) with a minimum segment length, used only to *flag candidates for human review* — never
to auto-publish "crime changed in March". Persistence: classify a unit (beat or masked block)
across the last N comparable periods as **persistent** (elevated in ≥k of N), **emerging**
(elevated now, not historically), **receding** (elevated historically, not now), or
**episodic**. Report the count of periods, not a single label, so the evidence is visible.

## 9.7 Geographic concentration

Compute the concentration curve: what share of masked blocks accounts for 50% of reports
(Ward 20 2025 has 692 blocks, 3,438 distinct coordinate points, 7,817 incidents). Report the
observed share against the 2–6%-of-segments finding in the literature **with the explicit
caveat that NIP's unit is the masked block, not the street segment**, so the numbers are not
directly comparable. Sensitivity: recompute at beat level and check the ordering is stable.

## 9.8 Sensitivity analyses to publish, not hide

1. **Geographic definition** — portion vs whole CA; PIP beat vs CPD beat (an 11% swing in
   beat attribution); ward-clipped vs whole-beat.
2. **Reporting window** — YTD cut date moved ±2 weeks; the 7-day source lag; late-reported
   records (the 2025 total moved 7,813 → 7,817 between the July and September releases).
3. **Category definition** — broad bucket vs primary type vs description.
4. **Domestic definition** — description-coded vs flag (193 vs 206).
5. **Source revision** — `source_removed` reconciliation removed 210 rows across 2017–2026.

Any finding whose direction flips under a sensitivity test must not be published as a finding.

## 9.9 Outcome assessment (SARA Assessment)

Where a documented response exists: pre/post comparison with (a) a stated pre-period, (b) a
**comparison area** not subject to the response, (c) a check for **displacement** into
adjacent beats, and (d) enumerated alternative explanations. Where no comparison area exists,
publish the before/after numbers and state explicitly that the effect of the response is
**not established**. Never infer causation from an association in time or space.

## 9.10 Validation requirements

Every method ships with: a unit test on a fixed fixture; a reconciliation assertion
(decomposition sums, shares sum to 1, portions sum to the ward); a documented assumption list;
and a recorded failure mode ("what would make this misleading").

---

# PART 10 — DELIVERABLE 8: IMPLEMENTATION ROADMAP

**Tier 0 — corrections to misleading public information** *(smallest coherent first step;
ship alone, no new data, no new pages)*
1. Beat disclosure: state the beat definition, add the **whole-beat vs in-ward** column, note
   that 16 of 21 beats extend beyond the ward. *(D1)*
2. Show each portion's **intersection share** and add "counts are not a safety ranking".
   *(Part 5)*
3. Surface **freshness** — the site currently gives no staleness signal while `/freshness`
   says `stale`. *(D7)*
4. Remove the UI truncations: all 26 types, all 21 beats, explicit zeros. *(D2/D3)*
5. Fix or label the incidents **frame-mixing filters** — silently dropping 3.2% of rows is a
   bug. *(D8)*

*Files: `index.tsx`, `incidents.py` (+ one API field for intersection share). Independently
shippable, reversible, no data dependency.*

**Tier 1 — recovery of previously built-but-hidden functionality**
`/overview` endpoint decision (surface or retire, D6); all-categories view; category
decomposition with the reconciliation assertion.

**Tier 2 — findings infrastructure and the Overview brief**
`config/findings.yml`, `presentation/findings.py`, `/api/v1/findings`, CI validation, brief
archive; Overview rebuilt with Public Safety findings only. Deep links carry geography, year
and filters.

**Tier 3 — Crime Trends build-out**
F1 decomposition → F2 arrest-by-category *(new)* → F3 beat profile → F4 portion profile →
F5 circumstances explorer → F6 burglary 3-way → F7 domestic battery → F8/F9 time-series and
persistence.

**Tier 4 — new statistical analysis**
tau-b trend classification, Poisson bands, publication thresholds, change-point candidates,
persistence classification, concentration curves, the sensitivity panel.

**Tier 5 — cross-domain integration, one dataset per package**
311 (V2-005) → Census blocks + ACS (unblocks every denominator) → LODES WAC/RAC (jobs in vs
held by) → parcels/permits → TIF. Each package: ingest, PIP clip, publish availability, then
findings.

**Tier 6 — SARA and accountability**
Problem records, response register, assessment with comparison areas; the conditional
questions (burglary vs housing change; sporting events) only after Tier 5.

**Recommended first implementation: Tier 0 only.** It corrects everything currently
misleading, needs no new data, touches two files, and is fully reversible.

---

# PART 11 — DELIVERABLE 9: ACCEPTANCE CRITERIA

**Geographic correctness** — every figure names its geography and, for a portion, its
intersection share · no whole-CA figure is labelled as Ward 20 · `bronzeville` remains 404 ·
every beat figure states in-ward or whole-beat · the beat definition is disclosed wherever a
beat appears.

**Reconciliation** — portion counts sum to the ward total (2025: 2,962+1,843+1,010+747+429+299
+270+227+30 = 7,817) · beat shares sum to 1.000 ± 0.001 · Σ category contributions = total
change (−398 for 2025 vs 2024) · `source_removed` rows excluded everywhere · a published
finding's number equals the API's, asserted in CI.

**Category completeness** — all primary types present in the selection are reachable · a type
with zero records renders an explicit 0, never an omission · no top-N truncation without a
"show all (n)" control · overlapping narrow categories are never presented as a partition.

**Arrest definitions** — labelled "share of reported incidents carrying an arrest flag at last
update" · never clearance, conviction, or investigative quality · absence of dispositions
stated on the view · no share published below the small-N threshold.

**Comparable periods** — YTD compares to the same day-of-year · a mixed full-year/YTD
comparison fails review and cannot publish · the 7-day source lag and late-reporting effect
disclosed.

**Statistical calculations** — every trend statement carries a stability classification, not
just a percentage · no %Δ where prior < 20 · uncertainty bands stated with their assumption ·
sensitivity results published with the finding.

**Privacy** — nothing below masked-block level · no domestic/sexual/child offence location
detail · cross-tab cells below 5 suppressed · Kenwood-scale geographies get no category
breakdown · suppression rules documented publicly.

**Deep links** — every finding link lands on the specific chart anchor with geography, year and
filters preserved; no link resolves to a page top; a broken destination fails CI.

**Historical reproducibility** — each archived brief records release id, `data_through`, and
every published number, and can be recomputed from that release.

**Classification clarity** — every Overview item is visibly one of VERIFIED FINDING /
CHANGE-ALERT / RESEARCH QUESTION / DATA GAP · a data gap explains what is missing and what it
would take · "no documented response" is distinguished from "no response occurred".

---

# PART 12 — DELIVERABLE 10: CPD DATA SCIENTIST DEMONSTRATION

## One case study, end to end: *Forcible-entry apartment burglary in Ward 20*

Chosen because it exercises every skill on real, verified, public data, and because the
honest answer includes a limitation — which is itself the point.

**1. Operational problem definition (POP-style, narrow enough to act on)**
Not "burglary" but: *forcible-entry and unlawful-entry burglary in residential settings within
Ward 20 — is it concentrated, is the concentration persistent, and what circumstances
characterise it?* Verified starting facts: Ward 20 2025 burglary n=250 — FORCIBLE ENTRY 93,
UNLAWFUL ENTRY 67, BURGLARY FROM MOTOR VEHICLE 68, HOME INVASION 15; by setting APARTMENT 97,
STREET 54, RESIDENCE 18, RESIDENCE-GARAGE 17.

**2. Data engineering and validation** *(working today)*
Medallion pipeline: Bronze per-year Parquet with a SHA-256 manifest; Silver point-in-polygon
enrichment; join on `id`. Streaming partition I/O in 20,000-row batches; atomic temp-sibling
publish; per-partition invariants (unique ids, identical id sets, manifest row+checksum) proved
after every write; `O_EXCL` single-writer lock; source-truth reconciliation marking
`source_removed` rather than deleting; incremental refresh on the source `updated_on`
watermark; `/api/v1/freshness` health. Verified release integrity: 21 years, 6,266,664 rows,
all 21 manifest checksums matching, per-year Bronze/Silver id sets identical.

**3. Statistical analysis** — YTD-comparable periods; additive change decomposition
reconciling to the total; tau-b trend classification; Poisson plausible-variation bands;
publication thresholds; documented sensitivity to geography, window, and category definition.

**4. Crime-category decomposition** — the full 26-type table with counts, Δ, %Δ, share and
contribution to net change, Σ reconciling to −398 for 2025 vs 2024.

**5. Beat-level investigation** — beat 0312 (1,087 CPD-reported / 1,129 PIP; 14.4% of ward
incidents): composition, change drivers, settings, hour/day, arrest share, persistence across
comparable periods, in-ward vs whole-beat (0312 is 99.6% inside the ward, so it is a clean
case, unlike 0223 at 28.9%).

**6. Geospatial analysis** — concentration curve over 692 masked blocks; persistence
classification; explicit statement that the masked block is the analytical floor because
coordinates are block-snapped (3,438 distinct points for 7,817 incidents), so street-segment
methods from the literature do not transfer.

**7. Visualization** — decomposition bars led by counts; small-multiple monthly series with a
5-year band; setting × hour heatmap with suppressed cells; in-ward vs whole-beat paired bars.

**8. Written findings** — one page: what changed, which types explain it, where it
concentrates, whether the concentration persists, what the arrest flag shows, what it does not
establish.

**9. Methodological limitations** *(stated, not buried)* — reports not convictions; arrest flag
is not clearance and has no date; coordinates masked to the block; 11% beat-attribution
disagreement between CPD's field and geometry; 16 of 21 beats straddle the ward; **no
population denominator exists**, so counts are not rates; city revisions move history (the
2025 total moved 7,813 → 7,817 between releases); no access to calls for service, dispatch,
deployment or dispositions.

**10. Decision-support application** — a recurring, archived Ward 20 brief (CompStat's cadence
idea, not its interface) that flags candidate problems with persistence evidence and the
questions each raises, structured so a documented response can later be assessed against a
comparison area — while stating plainly that a decline after an action does not establish that
the action caused it.

**Working vs proposed:** items 2 and the underlying data are working in production today.
Items 1, 3–10 are proposed designs in this report; the burglary counts, beat figures,
concentration inputs and integrity results quoted in them are verified, but the analyses
themselves are not yet built.

---

## Sources (external practice research)

- [NYPD CompStat 2.0 portal](https://compstat.nypdonline.org/) · [NYPD CompStat page](https://www.nyc.gov/site/nypd/stats/crime-statistics/compstat.page)
- [BOCSAR Crime Mapping Tool guide](https://bocsar.nsw.gov.au/statistics-dashboards/crime-and-policing/guide-for-the-crime-mapping-tool.html) · [Using crime statistics (trend method, Kendall's tau-b)](https://dcj.nsw.gov.au/content/dcj/bocsar/bocsar-home/statistics-dashboards/crime-and-policing/using_crime_statistics.html) · [LGA crime tables](https://bocsar.nsw.gov.au/statistics-dashboards/crime-and-policing/lga-excel-crime-tables.html)
- [College of Policing — SARA model](https://www.college.police.uk/guidance/problem-solving-policing/sara-model) · [Problem-oriented policing toolkit](https://www.college.police.uk/research/crime-reduction-toolkit/problem-oriented-policing) · [Implementing POP](https://www.college.police.uk/guidance/effective-implementation-problem-oriented-policing/introduction)
- [ASU Center for Problem-Oriented Policing — SARA](https://popcenter.asu.edu/content/sara-model)
- [Weisburd, The Law of Crime Concentration and the Criminology of Place (Criminology, 2015)](https://onlinelibrary.wiley.com/doi/abs/10.1111/1745-9125.12070) · [JQC editors' introduction](https://link.springer.com/article/10.1007/s10940-017-9342-0) · [Gill et al., testing crime concentration](https://cebcp.org/wp-content/halloffame/Gill-etal-Testing-Concentration-Crime.pdf)

---

*Read-only investigation. No code, configuration, data pointer, scheduler, deployment, or
repository state was changed. Production remains: Render `e00665c`, `current` →
`bw-release-20260921`, scheduler OFF.*
