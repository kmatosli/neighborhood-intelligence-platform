# NIP Crime Analytics Innovation Catalogue

**For feature-by-feature owner review** · Date 2026-09-22 · **Nothing implemented**  

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

Every feature below is marked **PENDING OWNER REVIEW**. Nothing is approved. Approve, reject, or
defer each line individually.

**Baseline re-verified this session:** Render `e00665c` · `BW_DATA_DIR=/var/data/current` ·
`current` → `bw-release-20260921` · scheduler **OFF** · `data_through 2026-09-06`.

**Companions** (established findings are cited, not repeated): **[A]** `V2_ANALYTICAL_REDESIGN_2026-09-22.md` ·
**[B]** `V2_INTEGRATED_INTELLIGENCE_ARCHITECTURE_2026-09-22.md` · **[C]** `V2_CRIME_ANALYTICS_ADDENDUM_2026-09-22.md` ·
**[D]** `V2_NEIGHBORHOOD_COMPARISON_ADDENDUM_2026-09-22.md`

---

# PART 1 — The prostitution investigation (all ten questions answered)

Counts, date coverage and geography re-verified against the active release. **Ward 20: 1 record
in 2025, 0 in 2026 YTD (through 2026-09-06)** — confirmed.

## Q1–Q4, Q6 · Full series: whole community area / portion inside Ward 20

| Yr | City | Woodlawn | WashPark | Englewood | NewCity | GrandBlvd | GGCross | Ward 20 |
|---|---|---|---|---|---|---|---|---|
| 2006 | 7,034 | 124/121 | 124/68 | 190/4 | 332/167 | 275/0 | 30/8 | **372** |
| 2007 | 6,087 | 67/61 | 161/114 | 203/0 | 396/153 | 175/1 | 32/6 | 337 |
| 2008 | 5,141 | 38/38 | **241/174** | 297/2 | 217/72 | 203/1 | 14/5 | 292 |
| 2010 | 2,484 | 30/19 | 87/59 | 166/1 | 53/24 | 78/0 | 17/2 | 105 |
| 2013 | 1,652 | 31/18 | 28/25 | 93/0 | 24/11 | 34/0 | 8/3 | 57 |
| 2015 | 1,322 | 9/6 | 0/0 | 123/1 | 33/20 | 10/0 | 3/0 | 27 |
| 2017 | 735 | 1/0 | 1/0 | **71/0** | 2/1 | 26/0 | 0/0 | 1 |
| 2020 | 278 | 0/0 | 1/0 | 17/0 | 0/0 | 7/0 | 0/0 | 0 |
| 2023 | 209 | 0/0 | 0/0 | 1/0 | 0/0 | 0/0 | 0/0 | 0 |
| 2025 | 189 | 0/0 | 0/0 | 5/0 | 2/1 | 4/0 | 0/0 | **1** |
| 2026 | 97 | 0/0 | 0/0 | 0/0 | 1/0 | 0/0 | 0/0 | **0** |

*(Fuller Park, Hyde Park, Kenwood are ≤5 in every year and ~0 throughout.)*

**New geographic insight:** Ward 20's decline was driven by **New City, Washington Park and
Woodlawn** collapsing. **Englewood and Grand Boulevard retained records longest — but in their
non-ward portions** (Englewood whole CA 71 in 2017 while the ward portion was 0). This sharpens
explanation #5 from [C]: activity persisted *adjacent to but outside* Ward 20.

## Q5, Q7–Q10 · Established in [B]/[C], summarised

- **Q5 concentrations elsewhere:** 2006 top CAs were 25 Austin (829), 27 E. Garfield Pk (531), 8
  Near North (429). 2025: 56 Garfield Ridge (70), 25 Austin (46). Top wards moved from 28/27/26/16/24/**20**
  to 24/23/14/22/33/9 — **the residual relocated to the west/northwest side**.
- **Q7 classification:** IUCR 1505/1506/1507/1512/1513/1525/1531/1549 stable 2006→2026; only
  description wording drifted (`SOLICIT FOR BUSINESS` → `SOLICITING FOR BUSINESS`). **Use IUCR as
  the join key, never description.**
- **Q8 filters:** nothing excluded. Mapped to `public_order`; `category_drivers` returns all types
  untruncated; the UI's `.slice(0,12)` hides it from display only. Whole-CA cross-check = 0, so
  ward clipping is not implicated.
- **Q9 related but distinct:** HUMAN TRAFFICKING 1 (2006) → 18 (2025); SEX OFFENSE ~1,000–1,600
  stable; PUBLIC INDECENCY ~4–14; OBSCENITY 17→55. Reported separately; **never combined**, and
  trafficking is **not** treated as evidence about prostitution or vice versa.
- **Q10 establishable vs unknowable:** establishable — recorded enforcement fell ~97% citywide and
  to ~zero in Ward 20; the category is **~99% arrest-flagged vs 16.1% for all crime**; all
  discretionary offences fell together (gambling −99.0%, narcotics −86.7%) while victim-reported
  battery fell −47.1%. **Unknowable** — underlying prevalence, displacement indoors/online,
  victimization, and whether any specific policy caused it. (BJS victimization research exists
  nationally but does not reach this geography.)

**Verdict: RESEARCH FINDING about the measure, not the neighbourhood.**

## Proposed visualization — the "rare category" investigation panel

```
┌ Crime Trends ▸ Rare & Unexpected Counts ▸ PROSTITUTION ───────────────┐
│ Ward 20, 2025:  1 recorded incident        ⚠ ENFORCEMENT-GENERATED    │
│ "This category is recorded almost only when police make an arrest      │
│  (99% arrest-flagged, vs 16% of all crime). It measures enforcement    │
│  activity, not how often the behaviour occurs."            ▸ methods   │
├───────────────────────────────────────────────────────────────────────┤
│ 1 · IS THIS NEW?  indexed 2006=100, log scale                         │
│  100┤●─────                                                           │
│     │      ╲●────╲                          ── Ward 20                │
│   10┤            ╲───●──╲                   ── Chicago                │
│    1┤                    ╲●───────●───────●─────●                     │
│     └2006──2010──2014──2018──2022──2026                               │
│  Ward 20: 372 → 105 → 8 → 0 → 0 → 0 (1 in 2025)                       │
├───────────────────────────────────────────────────────────────────────┤
│ 2 · IS IT A CODING CHANGE?   IUCR presence over time                  │
│  1506 ████████████████████████  still in use citywide (141 in 2025)   │
│  1513 ████████████████████████  1505 ███████░░  1549 ░░░░████████     │
│  → codes stable; only wording changed. NOT reclassification.          │
├───────────────────────────────────────────────────────────────────────┤
│ 3 · IS IT JUST OUTSIDE?  whole CA vs Ward 20 portion, small multiples │
│  Englewood  whole ▆▆▅▄▃▂▁  ward ▁▁▁▁▁▁▁   ← persisted OUTSIDE ward    │
│  New City   whole ▇▆▄▂▁▁▁  ward ▆▅▃▁▁▁▁                               │
├───────────────────────────────────────────────────────────────────────┤
│ 4 · IS IT ONLY US?  discretionary vs victim-reported, 2006→2025       │
│  gambling −99.0% │ prostitution −97.3% │ narcotics −86.7%              │
│  ───────────────────────────────────────────────────────              │
│  battery (victim-reported) −47.1%                                     │
│  → the whole discretionary class collapsed, not this category alone.   │
├───────────────────────────────────────────────────────────────────────┤
│ 5 · WHAT THIS CANNOT TELL US                          [DATA GAP]      │
│  prevalence · displacement online/indoors · victimization · causation  │
│  Related-but-distinct: human trafficking 18 citywide (2025) ▸ separate │
└───────────────────────────────────────────────────────────────────────┘
```

---

# PART 6 — APPROVAL CATALOGUE

Readiness: **R1** buildable on current data · **R2** needs a correction/exposure first ·
**R3** needs new public data · **R4** research-stage · **R5** restricted data.
Complexity: **S** small (days) · **M** medium (1–2 wks) · **L** large (3 wks+).

| ID | Feature | Analytical question | Proposed visualization | Data | Readiness | Overlaps existing | Dependencies | Cx | **Approval** |
|---|---|---|---|---|---|---|---|---|---|
| **CA-01** | Rare & Unexpected Counts | Is a surprisingly low count real, filtered, or an artifact? | Investigation panel (Part 1) | production | **R1** | none | enforcement flag | M | **PENDING OWNER REVIEW** |
| **CA-02** | Crime-Category Movement | Which categories move which way, and is coding implicated? | Decomposition table + composition ribbon | production | **R1** | `category_drivers` exists, UI truncates | untruncate (Tier 0) | M | **PENDING OWNER REVIEW** |
| **CA-03** | Near-Repeat Crime | Do burglaries cluster nearby soon after one? | Knox space-time grid vs permutation null | production, **degraded** | **R4** | none | accept block-level floor | L | **PENDING OWNER REVIEW** |
| **CA-04** | Migration & Displacement | Did a local decline coincide with an adjacent rise? | Adjacency flow map + paired series | production | **R1** for description; **R4** for attribution | none | beat adjacency graph | L | **PENDING OWNER REVIEW** |
| **CA-05** | Persistent/Emerging/Shifting Hotspots | Is this concentration longstanding or new? | k-of-N persistence classes on block/beat grid | production | **R1** | "repeat block" issue card only | suppression rules | M | **PENDING OWNER REVIEW** |
| **CA-06** | Repeat Locations | Do incidents recur at the same place/premises type? | Ranked masked-block table + premises cross-tab | production | **R1** | partial (one issue card) | suppression rules | S | **PENDING OWNER REVIEW** |
| **CA-07** | Event-Associated Crime | Do incidents shift around events/holidays/weather? | Event-window vs matched-control comparison | **needs event calendars, weather** | **R3/R4** | none | ingestion + pre-registration | L | **PENDING OWNER REVIEW** |
| **CA-08** | Crime & Built Environment | Do incidents co-locate with vacancy, lighting, violations? | Bivariate map + co-location table | **needs 311, vacancy, violations, parcels** | **R3** | none | Tier 5 ingestion | L | **PENDING OWNER REVIEW** |
| **CA-09** | Severity & Composition | Does a stable total conceal a shift in serious offences? | Composition ribbon + counts always visible | production | **R1** (no weights) / **R4** (harm index) | none | **separate approval for any weight set** | M | **PENDING OWNER REVIEW** |
| **CA-10** | Incident-to-Arrest | What does the arrest flag show by category, place, time? | Paired bars (flagged / not) + share line | production | **R1** | ward-wide summary only | disclosure copy | M | **PENDING OWNER REVIEW** |
| **CA-11** | Reporting Lag & Revision | Does a recent decline shrink as records arrive? | Snapshot-vs-snapshot lag curve + provisional badge | production + **retained releases** | **R1** | none | none | S | **PENDING OWNER REVIEW** |
| **CA-12** | Trend & Anomaly Detection | Is this outside normal variation? | SPC chart + tau-b label + Poisson band | production | **R1** | none | thresholds | M | **PENDING OWNER REVIEW** |
| **CA-13** | Incident Circumstances Explorer | Under what circumstances does this occur? | Setting × hour heatmap + facets, cells <5 suppressed | production | **R1** | none | suppression rules | M | **PENDING OWNER REVIEW** |
| **CA-14** | Documented Response & Outcome | What was done, and what followed? | SARA card + ITS with comparison area | **needs response records** | **R3** | none | response register | L | **PENDING OWNER REVIEW** |
| **CA-15** | Geographic Definition Audit | Which geography is this, and what changes if I switch? | Side-by-side definition matrix + frame toggle | production | **R2** | **corrects D1/D8** | Tier 0 | M | **PENDING OWNER REVIEW** |
| **CA-16** | Risk-Terrain **Diagnostic** *(discovered)* | Which environmental features co-locate with incidents? | Feature co-location table + risk surface | **needs built-environment data** | **R4** | none | CA-08 first | L | **PENDING OWNER REVIEW** |
| **CA-17** | Measurement-Intelligence Panel *(discovered)* | Is this pattern a property of the dataset? | Data-integrity strip on every view | production | **R1** | none | none | S | **PENDING OWNER REVIEW** |
| **CA-18** | Concentration & Inequality *(discovered)* | How concentrated is crime, and is that changing? | Lorenz curve + Gini trend | production | **R1** | none | state spatial unit | S | **PENDING OWNER REVIEW** |
| **CA-19** | Neighborhood Comparison *(discovered)* | How do two areas compare, and does the ordering hold? | Paired table + frame/measure toggles | production (area denominators) | **R1** | none | frame toggle | M | **PENDING OWNER REVIEW** |

---

# PART 4 — Feature proposals

Each: question · illustrative or verified finding · interface · data · method · limitations ·
scope · relationships.

## CA-01 · Rare & Unexpected Counts — **R1, M**
**Question.** Currently a resident seeing "1" learns nothing about why. This distinguishes *zero
recorded reports* / *missing data* / *filtered out* / *suppressed* / *genuinely rare*.
**Finding (VERIFIED).** Prostitution in Ward 20 fell 372 (2006) → ~0 (2016 onward); the category
is 99% arrest-flagged; the whole discretionary class collapsed citywide. Not suppression, not
reclassification.
**Interface.** Part 1 panel: five stacked questions, each answered with a chart.
**Data.** Production only. **Method.** Indexed series (log scale), IUCR presence-over-time,
whole-CA vs portion small multiples, arrest-share comparison.
**Limitations.** Cannot speak to prevalence; a low count may still be under-enforcement,
under-reporting, or genuine rarity — the panel must present all three as live possibilities.
**Scope.** New analysis on current data. **Relationships.** Uses CA-17's integrity strip and
CA-15's geography matrix; feeds Overview as a DATA GAP card.

## CA-02 · Crime-Category Movement — **R1, M**
**Question.** Which categories explain a total change, and could coding explain part of it?
**Finding (VERIFIED, Ward 20).** Total fell 17,483 (2006) → 7,817 (2025), −55%, but discretionary
share fell 16.8% → 5.6% while violent share rose 35.1% → 38.7% and property 41.9% → 47.5%. MVT
rose 4.9% → 13.2% (2023) → 8.4%.
**Interface.** Decomposition table (all 26 types: count, Δ, %Δ, share, **contribution to net
change**, Σ reconciling to the total) + a composition ribbon over time.
**Data.** Production. **Method.** Additive contribution decomposition; IUCR-stability check to
separate coding change from real movement.
**Limitations.** Broad categories partition the total; the narrow `categories` block **overlaps**
and must never be shown as a breakdown. Never a %Δ without counts.
**Scope.** Exposure + new analysis. **Relationships.** Entry point from every Overview
public-safety finding; hands off to CA-13 and CA-09.

## CA-03 · Near-Repeat Crime — **R4, L**
**Question.** After a burglary, is the risk to nearby addresses briefly elevated?
**Finding.** *ILLUSTRATIVE:* "burglaries within 2 blocks and 14 days occur more often than
chance would predict."
**Interface.** Space-time contingency grid (distance bands × day bands) with observed/expected
ratios; a permutation-null band.
**Data.** Production, **degraded**. **Method.** Knox-style test against a permutation baseline.
**Limitations — decisive.** Published coordinates are **block-masked** (3,438 distinct points for
7,817 Ward 20 incidents in 2025; busiest point = 96 incidents). True near-repeat distances are
**unmeasurable**; only block-to-block adjacency is available, which is coarser than the
literature's unit. Must never imply a shared offender.
**Scope.** Research-stage. **Recommendation: approve as a documented research note, not a public
view.**

## CA-04 · Migration & Displacement — **R1 description / R4 attribution, L**
**Question.** When one area falls, do adjacent areas rise?
**Interface.** Adjacency flow map (beats), paired target-vs-neighbour series, type/time shift
panel.
**Method.** Adjacent-unit change vs non-adjacent control; check whether type or timing shifted
rather than location.
**Limitations.** Redistribution is observable; **displacement caused by an intervention is not**,
absent a documented intervention and a comparison area. Regression to the mean will mimic
displacement.
**Scope.** New analysis (descriptive); attribution only inside CA-14.

## CA-05 · Persistent / Emerging / Shifting Hotspots — **R1, M**
**Question.** Is this concentration longstanding, new, receding, or moved?
**Interface.** Block/beat grid coloured by class, with **k of N periods** printed on every unit.
**Method.** Elevated in k of N comparable periods → persistent / emerging / receding / episodic.
**Limitations.** Masked block is the floor; small blocks flip class on 1–2 incidents, so require a
minimum count before classifying. A hotspot describes **reports at a place**, never the people
there.
**Scope.** New analysis. **Relationships.** Shares the spatial unit with CA-06 and CA-18.

## CA-06 · Repeat Locations — **R1, S**
**Question.** Do reports recur at the same block or premises type?
**Finding (VERIFIED).** Ward 20 2025: 692 masked blocks; the busiest carries **221** reports; top
10 blocks hold 15.2%.
**Interface.** Ranked block table (count, category mix, persistence) + premises-type cross-tab.
**Limitations & safeguards.** Blocks only — never an address; suppress per-block category cells
below 5; **exclude domestic, sexual and child-offence detail from any location view**; no
household or victim profile of any kind.
**Scope.** New analysis (partly exists as one issue card).

## CA-07 · Event-Associated Crime — **R3/R4, L**
**Question.** Do incidents change around games, holidays, school terms, heat, or storms?
**Interface.** Event-window vs **matched-control window** (same weekday/hour/season, no event),
with a sensitivity strip.
**Data.** Needs permitted-event calendars (**UNVERIFIED** availability), school calendars, NOAA
weather. **Method.** Matched-control comparison, pre-registered windows.
**Limitations.** Confounded by weekend/holiday effects, alcohol hours, reporting propensity.
**Domestic-related events must be a separate, privacy-protected research question and must never
be published as evidence that sporting events cause domestic violence.**
**Scope.** New ingestion + research-stage. **Recommendation: defer.**

## CA-08 · Crime & Built Environment — **R3, L**
**Question.** Do incidents co-locate with vacancy, poor lighting, violations, corridors, transit?
**Interface.** Bivariate block-group map + co-location table with counts on both axes.
**Data.** 311 `v6vf-nfxy`, vacant buildings `kc9i-wq85`, city-owned land `aksk-kvfp`, violations
`22u3-xenr`, permits `ydr8-5enu`, parcels `pabr-t5kh` — **none ingested**.
**Limitations.** These are **administrative activity**, not condition censuses; 311 volume
reflects reporting propensity (including an *Alderman's Office* origin channel). Co-location is
not causation; both may follow population or land use.
**Scope.** New ingestion. **Relationships.** Prerequisite for CA-16.

## CA-09 · Severity & Composition — **R1 / R4, M**
**Question.** Does a flat total hide a rise in the most serious offences?
**Finding (VERIFIED).** Ward 20 2023 → 2025: total 8,384 → 7,817 while homicide 12 → 13 and
robbery 128 → 87 — the total and its most serious components move differently.
**Interface.** Composition ribbon + a serious-offence small-multiple row; **counts always on
screen**.
**Limitations.** A **harm-weighted index requires separate approval**: weights are normative
judgements, usually imported from another jurisdiction's sentencing, and must be published as a
table beside the counts. No single unexplained score.
**Scope.** New analysis (unweighted) now; weighting is a separate decision.

## CA-10 · Incident-to-Arrest — **R1, M**
**Question.** How does the arrest flag vary by category, place and time?
**Finding (VERIFIED).** Ward 20 2025 arrest-flagged 16.5% overall, but **Englewood portion 20.2%
vs Woodlawn portion 15.7%**; prostitution 91.5%, all crime 16.1% citywide.
**Interface.** Paired bars per category (flagged / not flagged) + share line + geography facets.
**Limitations — mandatory copy.** The flag is *as of the record's last update*; there is **no
arrest date**, so timing cannot be measured; it drifts as old records are updated; it is **not**
clearance, prosecution, conviction, or investigative quality; dispositions are **not available**.
Small-N guard before any share.
**Scope.** New analysis on existing field (previously proposed, never built — **not** a regression).

## CA-11 · Reporting Lag & Revision — **R1, S**
**Question.** Is a recent decline real or just incomplete?
**Finding (VERIFIED).** Ward 20 2025 moved **7,813 → 7,817** between the July and September
releases; both releases are retained on the production disk. Source `updated_on` exists; there is
**no separate report date**, so occurrence-vs-report lag cannot be measured — only revision.
**Interface.** Lag curve (same period across snapshots) + a **provisional badge** on any period
within ~60 days of `data_through`.
**Limitations.** Only two retained snapshots today, so the curve starts coarse; it improves as
releases accumulate.
**Scope.** New analysis. **Recommendation: highest value per effort with CA-17.**

## CA-12 · Trend & Anomaly Detection — **R1, M**
**Question.** Is this month outside normal variation, or ordinary noise?
**Interface.** SPC chart with control limits, a tau-b verdict label (rising / falling / **stable**),
a Poisson plausible-variation band, and change-points marked as **candidates for review**.
**Method.** Kendall tau-b (BOCSAR's approach); SPC; 12-month rolling mean; 5-year same-month band.
**Limitations.** Independence is violated by clustered crime, so limits are indicative;
significance ≠ importance; **reject** automated seasonal adjustment on small series — it fits noise.
**Scope.** New analysis. **Relationships.** Supplies the stability label every finding needs.

## CA-13 · Incident Circumstances Explorer — **R1, M**
**Question.** Under what circumstances does a selected offence occur?
**Finding (VERIFIED).** `location_description` is 99.7% populated with 72 distinct values; hour and
day-of-week parse for 100% of records (4.2% exactly midnight). Ward 20 2025 burglary n=250:
FORCIBLE ENTRY 93, BURGLARY FROM MOTOR VEHICLE 68, UNLAWFUL ENTRY 67; APARTMENT 97, STREET 54.
**Interface.** Setting × hour heatmap with category/geography facets; cells <5 suppressed.
**Residential vs commercial burglary:** only **54% (135/250)** is classifiable from
`location_description` → present a **three-way** residential / commercial / vehicle-or-unclassified
split, never a two-way one.
**Limitations.** No offender or victim detail exists or may be inferred; midnight clustering
signals imprecise timing.
**Scope.** New analysis on existing fields.

## CA-14 · Documented Response & Outcome — **R3, L**
**Question.** What was actually done about a problem, and what followed?
**Interface.** SARA card — problem · analysis · documented response + date · subsequent
observations · **evaluation limitations** — with an ITS chart and a comparison area.
**Data.** Needs published response records (city, aldermanic, project, permit).
**Limitations.** **No intervention may be invented.** Distinguish *no response documented* from
*no response occurred*. Before/after alone establishes nothing; without a comparison area, publish
the numbers and state the effect is **not established**.
**Scope.** New ingestion + design. **Relationships.** The only place a causal claim may ever live.

## CA-15 · Geographic Definition Audit — **R2, M**
**Question.** Which geography am I looking at, and what changes if I switch?
**Findings (VERIFIED).** CPD-reported vs spatial beat disagree for **885 of 7,817 (11.3%)** Ward 20
2025 records, stable 10.4–12.4% across 2019–2026; **16 of 21 beats are <95% inside the ward**
(0223 = 28.9%); mismatch scales with polygon size (ward 3.2% · CA 8.7% · beat 11.3%); **area**
shares are Woodlawn 50.1% / Englewood 23.0% while **incident** shares are 77.0% / 14.7%.
**Interface.** A definition matrix (field, authority, vintage, what it answers) + the frame toggle
+ a permanent "what changes if I switch" note.
**Recommendation (unchanged from [A]).** Spatial for ward/CA selection; **CPD's field for beat
attribution** (published coordinates are masked, so PIP cannot be finer at beat scale); polygon for
beat∩ward share; disclose both. Also fixes **D8**: `incidents.py:171` filtering on CPD-reported
`ward` inside a spatially selected set silently drops 248 of 7,817 rows.
**Scope.** Correction + exposure. **This is analytical foundation — recommend first.**

## CA-16 · Risk-Terrain **Diagnostic** — **R4, L** *(discovered — NIJ / Rutgers)*
**What the source does.** Risk Terrain Modeling diagnoses which **environmental** features
co-locate to create settings where crime concentrates, and has been NIJ-evaluated across multiple
cities, including a published Chicago assault application.
**Adaptation for NIP.** Use the **diagnostic** half only — "which environmental features co-locate
with reported incidents here" — and **not** the forecasting/patrol-targeting half.
**Limitations & safeguards.** Uses land features, **never demographics**. Forecasting place risk
shades into predictive deployment, which NIP does not do; the output must be framed as *diagnosis
of existing conditions*, not prediction. Requires CA-08 data first.
**Scope.** Research-stage. **Recommendation: note now, revisit after CA-08.**

## CA-17 · Measurement-Intelligence Panel — **R1, S** *(discovered)*
**Question.** Is this pattern a property of the neighbourhood or of the dataset?
**Interface.** A compact integrity strip on every analytical view: unplaced records ·
`beat_mismatch` (885 / 11.3%) · ward/CA frame disagreement (248 / 3.2%, 683 / 8.7%) · IUCR
stability · records the City withdrew (210 across 2017–2026) · small-count warnings · provisional
status.
**Data.** Entirely existing fields. **Scope.** New analysis, no new data.
**Recommendation: approve with CA-11 — cheapest genuine differentiator in the catalogue.**

## CA-18 · Concentration & Inequality — **R1, S** *(discovered)*
**Finding (VERIFIED).** Ward 20 concentration is **rising**: blocks holding 50% of reports 16.3%
(2016) → 14.8% (2020) → **13.2%** (2025); **Gini 0.542 → 0.557 → 0.581** while total volume fell.
**Interface.** Lorenz curve with Gini printed and a Gini trend sparkline.
**Limitations.** Must state the spatial unit: NIP's masked block is **much coarser** than the
street segment in the 2–6% concentration literature, so the figures are not directly comparable.
**Scope.** New analysis.

## CA-19 · Neighborhood Comparison — **R1, M** *(discovered, see [D])*
**Finding (VERIFIED).** The ordering **flips with the denominator**: whole-CA counts make Englewood
higher (5,086 vs 3,848), per square mile make Woodlawn higher (1,855 vs 1,656, since Englewood is
48% larger). The Ward 20 Englewood portion records **58 robberies vs Woodlawn's 57 with a quarter
the incidents**.
**Interface.** Paired table with frame toggle (whole CA ↔ portion), measure toggle (count / per
sq mi / per resident — **disabled with a reason**), and a permanent "ordering depends on the
measure" panel.
**Limitations.** **No composite safety score.** Population unavailable (whole-CA obtainable,
portion needs block apportionment). Enforcement shares differ (5.3% vs 7.8%) and must be labelled.
**Scope.** New analysis; two existing `/pulse` calls composed client-side — **no backend change**.

---

# PART 5 — Three complete user journeys

Shared state travels in the URL throughout: `?geo=&frame=&year=&compare=&category=&beat=&setting=`.
No journey resets a filter.

## Journey A — "Why are prostitution reports apparently so rare?"

| # | Screen | What the user sees | State carried |
|---|---|---|---|
| 1 | Overview → **DATA GAP card** | "Recorded prostitution offences in Ward 20 are effectively zero since 2016. This measures enforcement activity, not prevalence." | `geo=ward20` |
| 2 | Trends ▸ **CA-01** panel, Q1 | Indexed log series: Ward 20 372 → ~0; Chicago 7,034 → 189 | + `category=PROSTITUTION` |
| 3 | same, Q2 | **CA-15** IUCR presence bars → codes stable, wording drifted | unchanged |
| 4 | same, Q3 | Whole-CA vs portion small multiples → Englewood/Grand Boulevard persisted **outside** the ward | + `frame` toggle live |
| 5 | same, Q4 | Discretionary vs victim-reported: gambling −99%, narcotics −87% vs battery −47% | unchanged |
| 6 | **CA-17** strip | 99% arrest-flagged; IUCR stable; nothing filtered or suppressed | unchanged |
| 7 | Methods | Distinct classifications (trafficking 18 citywide, kept separate); what is unknowable | — |

**Outcome:** a RESEARCH FINDING about the measure. The user leaves understanding that the number is
about policing, not about their block.

## Journey B — "Are burglaries persistent or shifting?"

| # | Screen | What the user sees | State |
|---|---|---|---|
| 1 | Overview CHANGE/ALERT | "Burglary is running above last year while overall crime falls" — **provisional** badge (CA-11) | `geo=ward20&year=2026` |
| 2 | Trends ▸ **CA-02** | Decomposition: burglary's contribution to net change; Σ reconciles | + `category=BURGLARY` |
| 3 | **CA-13** circumstances | Three-way split (residential / commercial / vehicle-or-unclassified — 54% classifiable); FORCIBLE ENTRY 93 vs BURGLARY FROM MV 68; setting × hour heatmap | + `setting` |
| 4 | **CA-18** concentration | Lorenz + Gini; is burglary more concentrated than crime overall? | unchanged |
| 5 | **CA-05** persistence | Blocks classed persistent / emerging / receding with **k of N** shown | + `beat` on click |
| 6 | **CA-06** repeat locations | Ranked blocks, cells <5 suppressed, no addresses | unchanged |
| 7 | **CA-03** research note | Near-repeat: what it would take, and why masked coordinates prevent it | — |
| 8 | **CA-12** | tau-b verdict: is the rise a trend or noise? | unchanged |
| 9 | **CA-14** | Any documented response? If none: "no response documented in available data" | — |

## Journey C — "Is this apparent increase unusual?"

| # | Screen | What the user sees | State |
|---|---|---|---|
| 1 | A large %Δ on a category card | **CA-02** rule: the count appears before the percentage | `geo=&category=` |
| 2 | **CA-12** SPC chart | Control limits + Poisson band → is the point outside normal variation? | unchanged |
| 3 | **CA-12** seasonality | 5-year same-month band → is this an ordinary summer rise? | unchanged |
| 4 | **CA-11** provisional | Is the period complete? Lag curve from retained snapshots | unchanged |
| 5 | **CA-17** small counts | If prior < 20, the %Δ is withheld and the reason shown | unchanged |
| 6 | **CA-15** sensitivity | Does the change survive switching frame (portion ↔ whole CA) and beat definition? | frame toggle |
| 7 | Verdict | One of: DESCRIPTIVE FINDING · STATISTICAL ASSOCIATION · RESEARCH HYPOTHESIS · *(no causal claim)* | — |

---

# PART 7 — Proposed Crime Trends structure (for later approval)

Five sections, not one per method. Rationale: each maps to a question a user actually asks, and
every feature above lands in exactly one, so no chart is duplicated.

| Section | Holds | Features |
|---|---|---|
| **1 · Change** | what changed and which types explain it | CA-02, CA-09, CA-12, CA-11 badge |
| **2 · Geography** | where it happens, how concentrated, is it persistent | CA-05, CA-06, CA-18, CA-19, CA-04 |
| **3 · Circumstances** | when and under what conditions | CA-13, CA-10, CA-07 *(if approved)* |
| **4 · Investigations** | focused studies | CA-01, burglary, domestic battery, CA-03 note, CA-16 *(later)* |
| **5 · Definitions & Methods** | what the numbers mean and their limits | CA-15, CA-17, methodology, suppression rules |
| *Response & outcomes* | documented actions and assessment | **CA-14 → Civic Accountability**, not a Trends tab |

Navigation boundaries preserved: **Overview** = curated verified findings · **Crime Trends** =
supporting analysis · **Beat Meeting** = beat-scoped evidence + resident follow-up ·
**Civic Accountability** = documented commitments and responses. No navigation redesign is
proposed beyond adding sections inside the existing Trends page.

---

# WHAT I NEED YOU TO REVIEW

1. **Approve/reject each of CA-01 … CA-19 individually.** All are PENDING.
2. **My recommended first three** (all R1, small, no new data, and they correct or prevent
   misreadings): **CA-15** (geography definitions — also fixes the 3.2% row-dropping filter),
   **CA-17** (measurement-intelligence strip), **CA-11** (provisional badge + lag curve).
3. **Three decisions that are yours, not mine:**
   - **CA-09 harm weighting** — do we ever adopt an imported normative weight set? (Default: no.)
   - **CA-03 near-repeat** — research note only, or a public view despite masked coordinates?
     (Recommend: note only.)
   - **CA-07 event analysis** — defer, or start with the domestic-violence research question under
     strict privacy? (Recommend: defer.)
4. **Confirm the Part 7 five-section structure** before any Trends work begins.
5. Note **CA-14 lives in Civic Accountability**, not Crime Trends — confirm that placement.

---

## Sources (new in this catalogue)

[NIJ — Risk Terrain Modeling for Spatial Risk Assessment](https://nij.ojp.gov/library/publications/risk-terrain-modeling-spatial-risk-assessment) ·
[NIJ — From Crime Mapping to Crime Forecasting](https://nij.ojp.gov/topics/articles/crime-mapping-crime-forecasting-evolution-place-based-policing) ·
[NIJ — Police Technologies for Place-Based Crime Prevention](https://nij.ojp.gov/library/publications/police-technologies-place-based-crime-prevention-integrating-risk-terrain) ·
[NIJ — Applying RTM to assault in Chicago](https://nij.ojp.gov/library/publications/vulnerability-and-exposure-crime-applying-risk-terrain-modeling-study-assault)

Earlier sources (CompStat, BOCSAR incl. Kendall tau-b, College of Policing/SARA, POP Center,
Weisburd concentration, Healthy Chicago Survey, CAASE) are listed in [A], [B] and [D].

---

*Read-only. No code, configuration, dependency, data, pointer, scheduler, deployment, or
repository state was changed. Nothing is approved.*
