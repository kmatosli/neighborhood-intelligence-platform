# NIP V2 — Neighborhood Comparison Addendum: Englewood vs Woodlawn

**Date:** 2026-09-22 · **Status:** read-only investigation & design — nothing implemented  

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
**Companions:** `V2_ANALYTICAL_REDESIGN_2026-09-22.md` **[A]** ·
`V2_INTEGRATED_INTELLIGENCE_ARCHITECTURE_2026-09-22.md` **[B]** ·
`V2_CRIME_ANALYTICS_ADDENDUM_2026-09-22.md` **[C]**

All figures verified this session against the active release (`bw-release-20260921`,
`data_through 2026-09-06`, Render `e00665c`, scheduler OFF — re-verified).

## Correction to the companion reports

[A] Part 5 and [B] reported "share of the community area inside Ward 20" as **77.0% Woodlawn /
14.7% Englewood**. Those are **incident shares**, not area shares, and were mislabelled as area.
The **geometric** area shares, computed this session from the polygons, are **Woodlawn 50.1%**
and **Englewood 23.0%**. Both quantities are valid and useful, but they answer different
questions and must be labelled distinctly. This is exactly the class of label error the platform
must not ship, so it is corrected here and carried into the acceptance criteria.

---

# DELIVERABLE 1 — What exists vs what is planned

| Capability | Status |
|---|---|
| Per-geography analysis (one area at a time) | **Built** — `/api/v1/pulse/{geo}`, `/overview/{geo}`, `/incidents/{geo}` |
| Geography registry incl. all 9 portions + whole-CA context | **Built** — `/api/v1/geographies` |
| Portion counts and shares within Ward 20 | **Built** (computed), surfaced partially |
| **Two-geography side-by-side comparison** | **Not built and not previously specified.** No endpoint accepts two geographies; no UI compares two areas. [A]'s wireframe listed portions in one table but did not compare a pair |
| **Whole-CA vs portion toggle in the UI** | **Not built** — the registry distinguishes them; the UI does not let a user switch frame |
| Area denominators | **Newly feasible** — the geometry stack works (geopandas 1.1.4 / pyogrio 0.13.0); areas computed below for the first time |
| Population denominators | **Data gap** — no census data ingested |
| Perception data | **Not ingested**; a credible source exists (below) |

So neighborhood comparison is **new functionality**, not a regression, and the frame toggle is
its prerequisite.

---

# DELIVERABLE 2 — Verified comparisons (2025, consistent dates/categories/periods)

## A. Whole community areas · B. Ward 20 portions · D. vs Chicago

| View | n | Violent % | Property % | Discret. % | Arrest % | Homicide | Robbery | Burglary | MVT | Blocks | Blocks=50% | Gini | Night % | Wknd % | Apt/Res % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **A** Whole Woodlawn (CA 42) | 3,848 | 36.4 | **50.5** | 5.6 | 15.9 | 7 | 87 | 144 | 303 | 283 | 51 | 0.516 | 24.6 | 27.2 | 43.7 |
| **A** Whole Englewood (CA 68) | **5,086** | **41.2** | 39.9 | **8.5** | 18.8 | **13** | **172** | 153 | 362 | 504 | 94 | 0.489 | 25.6 | 27.6 | 44.5 |
| **B** Woodlawn in Ward 20 | **2,962** | 35.6 | **51.8** | 5.3 | 15.7 | 5 | 57 | **108** | 243 | 197 | 36 | 0.504 | 24.5 | 27.1 | **46.5** |
| **B** Englewood in Ward 20 | 747 | **43.4** | 37.6 | 7.8 | **20.2** | 2 | **58** | 15 | 57 | 94 | 11 | **0.609** | 24.8 | 26.4 | 24.2 |
| Ward 20 overall | 7,817 | 38.7 | 47.5 | 5.6 | 16.5 | 13 | 225 | 250 | 659 | 692 | 91 | 0.581 | 25.9 | 27.9 | 42.5 |
| **D** Chicago citywide | 238,049 | 32.0 | 54.4 | 5.6 | 16.1 | 438 | 5,817 | 9,740 | 17,256 | 28,352 | 3,505 | 0.586 | 23.8 | 28.6 | 35.0 |

**VERIFIED FINDINGS:**
1. Englewood's whole-CA total is **32% higher** than Woodlawn's (5,086 vs 3,848), and it is more
   **violence-weighted** (41.2% vs 36.4%), with **2× the robberies** (172 vs 87) and nearly
   double the homicides (13 vs 7).
2. Woodlawn is more **property-weighted** (50.5% vs 39.9%). Burglary is nearly identical in
   absolute terms (144 vs 153) despite the total gap.
3. Both areas are more violence-weighted than Chicago overall (32.0%).
4. **The Ward 20 Englewood portion records 58 robberies against the Woodlawn portion's 57 — with
   a quarter of the total incidents** (747 vs 2,962). Composition, not volume, is where the
   difference lives.
5. The Englewood portion is the **most spatially concentrated** unit examined (Gini 0.609) and
   has a very different setting mix (24.2% apartment/residence vs Woodlawn's 46.5%).
6. Time patterns are nearly identical everywhere (night ~25%, weekend ~27%) — **time of day does
   not distinguish these neighborhoods**, which is itself a useful negative finding.

## C. Each area against its own baseline (whole CA)

| Year | Woodlawn total | violent | homicide | robbery | Englewood total | violent | homicide | robbery | Engl/Wood ratio |
|---|---|---|---|---|---|---|---|---|---|
| 2006 | 8,271 | 2,806 | 9 | 364 | 12,402 | 4,725 | 14 | 490 | 1.50 |
| 2012 | 5,697 | 1,951 | 21 | 226 | 9,415 | 3,375 | 16 | 449 | 1.65 |
| 2016 | 3,825 | 1,513 | 11 | 206 | 6,367 | 2,677 | **48** | 318 | 1.66 |
| 2020 | 3,084 | 1,295 | 9 | 109 | 5,231 | 2,230 | 36 | 208 | 1.70 |
| 2023 | 3,915 | 1,350 | 12 | 128 | 5,161 | 2,083 | 23 | 215 | 1.32 |
| 2025 | 3,848 | 1,401 | 7 | 87 | 5,086 | 2,093 | 13 | 172 | **1.32** |

**VERIFIED FINDINGS:** Woodlawn −53% and Englewood −59% since 2006, so **Englewood declined
faster** and the gap between them **narrowed** (ratio 1.70 in 2020 → 1.32 now). Robbery fell
76% in Woodlawn and 65% in Englewood. Englewood's homicide count peaked at **48 in 2016** and is
13 today; Woodlawn peaked at 21 in 2012 and is 7.

---

# DELIVERABLE 3 — Findings that change with category, geography, or denominator

**This is the central result: the direction of the comparison flips depending on the choice.**

| Framing | Woodlawn | Englewood | Who is "higher"? |
|---|---|---|---|
| Whole-CA raw count | 3,848 | **5,086** | **Englewood** |
| Whole-CA **per square mile** | **1,855** | 1,656 | **Woodlawn** ⟵ *reverses* |
| Ward 20 portion raw count | **2,962** | 747 | **Woodlawn** (a geography artifact) |
| Ward 20 portion per square mile | **2,848** | 1,060 | **Woodlawn** |
| Violent share | 36.4% | **41.2%** | **Englewood** |
| Property share | **50.5%** | 39.9% | **Woodlawn** |
| Robbery, whole CA | 87 | **172** | **Englewood** |
| Robbery, ward portion | 57 | **58** | **tied** |
| Concentration (Gini, ward portion) | 0.504 | **0.609** | **Englewood** |

Areas computed from the polygons this session: Woodlawn **2.074 sq mi** (1.040 in Ward 20),
Englewood **3.072 sq mi** (0.705 in Ward 20). **Englewood is 48% larger**, which is why a raw
count overstates it relative to density.

**VERIFIED FINDING:** No single ordering of these two neighborhoods survives a change of
denominator. Any product that presents one number and implies "safer/less safe" is misleading by
construction. This is the evidentiary basis for refusing a composite danger score — which this
design does refuse.

---

# DELIVERABLE 4 — Missing data required for a fair comparison

| Requirement | Status | Note |
|---|---|---|
| **Resident population** | **DATA GAP — decisive** | Without it, no per-capita rate. Both areas lost population over this period, so a count decline partly reflects fewer residents, not only less crime |
| Whole-CA population | **Obtainable, not ingested** | City ACS-by-community-area (`t68z-cikk`) covers whole CAs — enough for comparison **A** only |
| **Portion population** | **Harder gap** | Requires Census **block**-level counts + apportionment; block groups on disk have only 13 of 92 fully inside Ward 20 |
| Area | **NEWLY AVAILABLE** | computed above; the only defensible denominator NIP has today |
| Daytime/ambient population | **Gap** | LODES WAC (jobs located in area) is the nearest public proxy; not ingested |
| Commercial premises count | **Gap** | Business licences would proxy exposure for commercial theft/burglary |
| Housing units / occupancy | **Gap** | Needed for burglary-per-household, the correct burglary denominator |
| Street mileage | **Gap** | Needed for street-based offences; the city layer has no working API export |

**Asymmetry worth designing around:** whole-CA population is reachable now, portion population is
not. So **per-capita comparison is feasible for comparison A and not for comparison B** — the UI
must therefore offer rates only where the denominator exists, and say so where it does not.

---

# DELIVERABLE 5 — Perception data: available source, unverified values

A credible, representative instrument exists: the **Healthy Chicago Survey** (Chicago Department
of Public Health, annual since 2014), published through the **Chicago Health Atlas** with the
indicators *Perceived neighborhood safety* (HCSNS), *Perceived neighborhood safety rate*
(HCSNSP — "percent of adults who report feeling safe in their neighborhood all or most of the
time"), and *Perceived neighborhood violence* (HCSNV). Results are published for Chicago overall
and **each of the 77 community areas**, population-weighted.

| Aspect | Assessment |
|---|---|
| Representative survey? | **Yes** — a weighted population survey, not media or search interest |
| Geography | **Whole community areas only** — cannot describe Ward 20 portions |
| Values for Woodlawn / Englewood | **NOT VERIFIED.** The Atlas indicator pages are JavaScript applications; values were not retrievable this session. I will not state which neighborhood perceives itself as safer |
| Ingested into NIP? | No |
| Uncertainty | Community-area estimates from a city-wide survey carry material sampling error; margins were not retrievable and must be published alongside any value |

**Classification: RESEARCH QUESTION with an identified source** — not a data gap (a source
exists), and not a verified finding (values unconfirmed). The motivating premise — that reported
crime may not align with public perception — is therefore **neither confirmed nor refuted here**.

**Five measures the product must keep distinct** (they are routinely conflated):

| Measure | What it is | NIP status |
|---|---|---|
| Perceived safety | what residents feel | HCS, not ingested |
| Reported crime | incidents recorded by CPD | **in production** |
| Recorded enforcement activity | arrest-generated records (see [B] Deliverable 1) | **in production**, needs the enforcement flag |
| Victimization | crime experienced, incl. unreported | **no source** — a true gap; national surveys do not reach this geography |
| Crime **in** the area vs crime **experienced by** residents | location ≠ residence | **unmeasurable** — the dataset records incident location only |

The last row matters for this comparison: an incident in Woodlawn may involve people from
anywhere, and residents may be victimized elsewhere. NIP measures **places, not populations**,
and must say so.

---

# DELIVERABLE 6 — Neighborhood Comparison wireframe

```
┌ Crime Trends ▸ Neighborhood Comparison ────────────────────────────────┐
│ Compare [ Woodlawn ▾ ]  with  [ Englewood ▾ ]                          │
│ Frame:  ( ) Whole community area   (•) Portion inside Ward 20          │
│ Period: [2025 ▾]  vs [2024 ▾]   Category: [All ▾]                      │
│ Measure: (•) Count  ( ) Per sq mile  ( ) Per resident ⓘ unavailable    │
│          └ "Per resident needs census data NIP has not ingested" ▸why  │
├────────────────────────────────────────────────────────────────────────┤
│ ⚠ FRAME NOTE: you are comparing the parts of these community areas     │
│   inside Ward 20 — 50.1% of Woodlawn's area and 23.0% of Englewood's.  │
│   These are not whole-neighborhood figures.          [switch frame]    │
├────────────────────────────────────────────────────────────────────────┤
│                         Woodlawn(pt)   Englewood(pt)   Ward 20   City  │
│ Reported incidents          2,962            747        7,817  238,049 │
│ Per square mile             2,848          1,060            —       —  │
│ Violent share               35.6%          43.4%        38.7%   32.0%  │
│ Property share              51.8%          37.6%        47.5%   54.4%  │
│ Robbery                        57             58          225   5,817  │
│ Burglary                      108             15          250   9,740  │
│ Arrest-marked share         15.7%          20.2%        16.5%   16.1%  │
│ Concentration (Gini)        0.504          0.609        0.581   0.586  │
│ ⓘ Enforcement-generated categories are 5.3% / 7.8% — these respond to  │
│   police activity, not only to conditions.                     ▸why    │
├────────────────────────────────────────────────────────────────────────┤
│ ORDERING DEPENDS ON THE MEASURE                                        │
│ Whole-CA count → Englewood higher · Whole-CA per sq mi → Woodlawn      │
│ higher · Violent share → Englewood · Property share → Woodlawn         │
│ ▸ open the denominator explainer                                       │
├────────────────────────────────────────────────────────────────────────┤
│ [ Trend ] [ Composition ] [ Concentration & persistence ] [ Methods ]  │
│  each opens the pair side-by-side, filters preserved                   │
├────────────────────────────────────────────────────────────────────────┤
│ NOT SHOWN, AND WHY                                                     │
│ • Per-resident rates — census not ingested (whole CA feasible; portion │
│   needs block-level apportionment)                                     │
│ • Perceived safety — Healthy Chicago Survey exists, whole CA only,     │
│   not ingested                          [RESEARCH QUESTION]            │
│ • No composite safety score — no denominator supports one              │
└────────────────────────────────────────────────────────────────────────┘
```

Deliberate design choices: the **frame toggle is always visible and always annotated**; the
measure selector **shows the unavailable option greyed with its reason** rather than hiding it;
the "ordering depends on the measure" panel is **permanent, not a footnote**; and there is no
single headline number, because no single number is defensible.

---

# DELIVERABLE 7 — Integration into Crime Trends and Overview

**Crime Trends:** Neighborhood Comparison becomes a sixth view alongside the five in [B]
Deliverable 3, reachable from V2 (Geography & Concentration) by selecting a second area. It
inherits the shared control bar and adds one state parameter (`compare_geo`). Every tab in it
opens the existing single-area views in paired mode — no duplicated analytics.

**API:** no endpoint accepts two geographies today. Two options — (a) the client issues two
existing `/pulse/{geo}` calls and composes, or (b) a new `/api/v1/compare?a=&b=&frame=`. **(a) is
recommended first**: zero backend change, zero new contract, and the comparison is provably the
same numbers users already see.

**Overview:** carries at most **one** comparison finding, as a conclusion with its link — e.g.
*"Englewood and Woodlawn differ more in composition than in volume: the Ward 20 portion of
Englewood records as many robberies as Woodlawn's with a quarter the incidents."* That sentence
is supported by the verified table above. Overview must **not** reproduce the comparison
interface, and must never publish an ordering without its denominator.

**Beat Meeting:** the same pair logic serves beat-vs-beat comparison, with the whole-beat vs
ward-clipped columns from [A] Part 1.

---

# DELIVERABLE 8 — Acceptance criteria and dependencies

**Acceptance criteria (additions to [A] Part 11):**
1. **Frame integrity** — a comparison never mixes a whole-CA figure with a portion figure in the
   same row or series; a test asserts both sides of every comparison share one frame.
2. **Area vs incident share labelling** — any "share of the community area in Ward 20" states
   whether it is **area** (Woodlawn 50.1%, Englewood 23.0%) or **incidents** (77.0%, 14.7%); CI
   fails on an unlabelled share. *(Directly from the correction at the top of this report.)*
3. **Denominator disclosure** — every rate names its denominator; an unavailable denominator is
   shown disabled with a reason, never silently omitted or substituted.
4. **No composite score** — a test asserts no endpoint or view emits a single combined
   safety/danger index.
5. **Ordering honesty** — where the ranking of two areas reverses under an available denominator,
   the view must display both orderings.
6. **Enforcement flag surfaced** — discretionary-category shares are labelled in any comparison
   (Woodlawn 5.3% / Englewood 7.8%).
7. **Measure separation** — perceived safety, reported crime, enforcement activity, and
   victimization are never combined into one figure or chart axis.
8. **Reproducibility** — every figure records release id and `data_through`; the numbers in this
   report recompute exactly from `bw-release-20260921`.

**Dependencies, in order:** frame toggle in the geography control → paired-call comparison view
(no backend change) → area denominators (**ready now**, geometry stack verified) → whole-CA
population via `t68z-cikk` (unlocks per-capita for comparison A) → Census blocks + apportionment
(unlocks portion per-capita) → Healthy Chicago Survey ingestion (unlocks the perception question).
The enforcement-generated flag from [C] is a prerequisite for the comparison view, because
discretionary shares differ between these two areas (5.3% vs 7.8%) and would otherwise be read
as a difference in conditions.

**Smallest coherent first implementation:** the **frame toggle plus the paired-count comparison
with area denominators** — no backend change, no new data, and it delivers the one finding that
matters most (the ordering depends on the denominator).

---

## Sources

[Chicago Health Atlas — Perceived neighborhood safety rate (HCSNSP)](https://chicagohealthatlas.org/indicators/HCSNSP) ·
[Perceived neighborhood safety (HCSNS)](https://chicagohealthatlas.org/indicators/HCSNS?topic=perceived-neighborhood-safety) ·
[Perceived neighborhood violence (HCSNV)](https://chicagohealthatlas.org/indicators/HCSNV) ·
[CDPH Healthy Chicago Survey](https://www.chicago.gov/city/en/depts/cdph/supp_info/healthy-communities/healthy-chicago-survey.html) ·
[HCS data & documentation](https://www.chicago.gov/city/en/depts/cdph/supp_info/healthy-communities/hcs-data-and-documentation.html)

---

*Read-only. No code, configuration, dependency, data pointer, scheduler, deployment, or
repository state was changed. Production remains Render `e00665c`, `current` →
`bw-release-20260921`, scheduler OFF.*
