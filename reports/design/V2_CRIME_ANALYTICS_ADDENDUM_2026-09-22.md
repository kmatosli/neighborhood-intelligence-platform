# NIP V2 — Crime Analytics Addendum (new analysis only)

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

This is an **addendum**, deliberately not a third full report. The assignment says not to repeat
completed work, so this document contains **only analysis and design that the two existing
reports do not already cover**, plus a map showing where each of the twelve deliverables is
answered.

**Existing reports in this folder:**
- **[A]** `V2_ANALYTICAL_REDESIGN_2026-09-22.md` — capability inventory, defect register, beat
  resolution, Crime Trends features F1–F11, external practice, Overview wireframe, finding
  model + editorial process, data matrix, methods plan, roadmap, acceptance criteria,
  demonstration.
- **[B]** `V2_INTEGRATED_INTELLIGENCE_ARCHITECTURE_2026-09-22.md` — prostitution case study,
  innovation matrix 3A–3H, five-view Crime Trends IA, twelve External Operations domains,
  Neighborhood Issue Tracker, integrity report, updated matrices, roadmap tiers.

## Production re-verified (2026-09-22, after the previous audit)

| Item | Verified now |
|---|---|
| Render commit | `e00665c` |
| `BW_DATA_DIR` | `/var/data/current` |
| `current` → | `bw-release-20260921` |
| Scheduler | **OFF** |
| `refresh.lock` | none |
| Freshness | `stale`, `data_through 2026-09-06`, last success 2026-09-15 |

Unchanged. Also newly verified: **the geospatial stack now works on this machine** — geopandas
1.1.4 / pyogrio 0.13.0 read the 277-feature beat layer successfully. The Windows App Control
block recorded on 2026-09-14 has cleared, which unblocks polygon-based work (beat∩ward shares,
spatial joins). `libpysal` is **not** installed, so Moran's I / LISA would need a new dependency
(approval required).

---

# NEW ANALYSIS 1 — Prostitution: explanations #5 and #7 resolved

Report [B] tested explanations 1–4, 6 and 8. This assignment adds two that were **not**
previously tested: whether activity sits *just outside* the ward, and whether a **police
district** rather than a ward would reveal it.

## Explanation #7 — "the ward is the wrong unit; use a police district" → **CONTRADICTED**

PROSTITUTION records by the police districts that overlap Ward 20:

| Year | Citywide | Ward 20 | Dist 2 | Dist 3 | Dist 7 | Dist 9 |
|---|---|---|---|---|---|---|
| 2006 | 7,034 | 372 | 402 | 185 | 442 | **656** |
| 2010 | 2,484 | 105 | 165 | 45 | 166 | 102 |
| 2014 | 1,625 | 8 | 16 | 38 | 92 | 21 |
| 2018 | 718 | 0 | 21 | 0 | 35 | 9 |
| 2022 | 283 | 0 | 0 | 0 | 7 | 1 |
| 2025 | 189 | **1** | 4 | 1 | 4 | 8 |

Widening the geography from ward to district reveals nothing hidden: District 9 fell 656 → 8,
District 7 442 → 4, District 2 402 → 4, District 3 185 → 1. **The collapse is present at every
spatial scale**, so the apparent absence is not an artifact of choosing a ward.

## Explanation #5 — "activity is just outside Ward 20" → **PARTIALLY SUPPORTED, but trivial in magnitude**

Within the nine community areas that intersect Ward 20:

| Year | Records in those 9 CAs | Inside Ward 20 | Outside Ward 20, same CAs |
|---|---|---|---|
| 2006 | 1,084 | 372 (34%) | 712 |
| 2025 | 11 | **1** | **10** |

Proportionally, more of the (tiny) residual sits outside the ward than inside. In absolute terms
**10 records spread across nine community areas is not a concentration** and cannot support any
neighbourhood statement.

## New finding — the residual enforcement relocated

Top wards by PROSTITUTION records:

| 2006 | 2025 |
|---|---|
| 28 (931) · 27 (790) · 26 (457) · 16 (436) · 24 (413) · **20 (372)** | 24 (54) · 23 (41) · 14 (15) · 22 (14) · 33 (11) · 9 (6) |

Ward 20 was 6th in the city in 2006 and is absent from the top today. The residual activity is
recorded on the **west/northwest side**, not the south side. So the pattern is a *volume
collapse plus a geographic relocation of the remaining enforcement* — a stronger statement than
"it declined", and one the data does support.

## Verdict on all eight competing explanations

| # | Explanation | Verdict |
|---|---|---|
| 1 | Genuinely uncommon in the area | **Unresolved — unknowable from these data** |
| 2 | Rarely reported to police | **Unresolved**, and plausible: the offence is almost never victim-reported |
| 3 | Enforcement/reporting practice drives the dataset | **Strongly supported** — 99% arrest-flagged vs 16.1% for all crime; all discretionary offences collapsed together (gambling −99.0%, narcotics −86.7%) while victim-reported battery fell −47.1% |
| 4 | Recorded under another type/IUCR/description | **Contradicted** — IUCR 1505–1549 stable; human trafficking 1→18 is three orders too small |
| 5 | Just outside Ward 20 | **Partially supported, magnitude trivial** (10 records across 9 CAs in 2025) |
| 6 | Historical patterns differ | **Confirmed** — 372 (2006) → ~0 from 2016 |
| 7 | Ward too small; district would show it | **Contradicted** — districts collapsed identically |
| 8 | Revisions/classification/coverage | **Contradicted as an explanation** — checksums verified, ids unique, IUCR stable |

**Classification: RESEARCH FINDING about the measure, not about the neighbourhood.** The
defensible published statement is: *"Recorded prostitution offences in Ward 20 fell from 372 in
2006 to effectively zero from 2016, as part of a citywide collapse in discretionary enforcement.
Because these records are created almost only when police make an arrest, they measure
enforcement activity and cannot establish whether the underlying behaviour changed."*

Distinctions held throughout, as instructed: prostitution/sex work is **not** treated as
evidence of trafficking (separate categories, separate evidence, and trafficking counts are far
too small and enforcement-dependent to support any local claim); no demographic characteristic
was used to infer conduct.

---

# NEW ANALYSIS 2 — Concentration measured (5B): Lorenz/Gini, and it is rising

Reported crime across masked blocks in Ward 20 (the finest honest spatial unit — see [A] Part 1
on coordinate masking):

| Year | Incidents | Blocks | Blocks holding 50% of reports | **Gini** | Busiest block | Top 10 blocks |
|---|---|---|---|---|---|---|
| 2016 | 8,769 | 704 | 115 (16.3%) | **0.542** | 258 | 13.0% |
| 2020 | 6,718 | 683 | 101 (14.8%) | **0.557** | 226 | 13.8% |
| 2025 | 7,817 | 692 | 91 (**13.2%**) | **0.581** | 221 | 15.2% |

**Two findings.** (1) Concentration is **increasing** — Gini 0.542 → 0.581 while total volume
fell, so reports are becoming more spatially concentrated even as they decline. (2) NIP's
measured concentration (13.2% of blocks → 50% of reports) is **much less extreme than the
street-segment literature** (2–6% of segments → 50%), exactly as expected because a masked block
is far coarser than a segment. Publishing our number next to theirs without that caveat would be
a false comparison; publishing it *with* the caveat is a genuine contribution.

**Design:** a Lorenz curve with the Gini printed, a k-of-N persistence class per block, and a
stated floor ("block, not street segment"). Privacy: blocks are already the published masking
unit; suppress any per-block category breakdown below 5.

---

# NEW ANALYSIS 3 — Crime-mix transition measured (5C)

Ward 20, share of reported incidents (total fell 17,483 → 7,817, **−55%**):

| Year | Total | Violent % | Property % | Discretionary % | Motor-vehicle theft % | Narcotics % |
|---|---|---|---|---|---|---|
| 2006 | 17,483 | 35.1 | 41.9 | **16.8** | 4.9 | 12.9 |
| 2012 | 12,311 | 34.5 | 42.0 | 16.9 | 3.8 | 13.6 |
| 2016 | 8,769 | 39.9 | 46.5 | **5.1** | 3.8 | 3.5 |
| 2020 | 6,718 | 41.9 | 42.2 | 7.6 | 4.7 | 2.5 |
| 2023 | 8,384 | 37.6 | 50.1 | 6.6 | **13.2** | 1.3 |
| 2025 | 7,817 | 38.7 | 47.5 | 5.6 | 8.4 | 1.8 |

**This is the "the total conceals different movements" finding the original brief wanted, now
measured.** The composition shifted materially: the discretionary share collapsed between 2012
and 2016 (16.9% → 5.1%), so what remains is proportionally more violent (35.1% → 38.7%) and more
property-focused (41.9% → 47.5%) — *without* violent crime rising in absolute terms. Motor-vehicle
theft tripled as a share into 2023 (3.8% → 13.2%) then eased to 8.4%.

**Required disclosure (5C's own warning):** the 2012→2016 discretionary step is an **enforcement**
change, not a coding change — verified separately, since IUCR codes are stable across the period.
A composition chart must therefore separate the two mechanisms in its note, or a reader will
conclude the neighbourhood became more violent when the measurable change is that police stopped
generating one class of record.

---

# NEW DESIGN — 5J Data-quality & measurement intelligence panel

The assignment asks for a systematic way to say "this may be a property of the dataset". Every
input below already exists in Silver or Bronze:

| Signal | Field available today | Current value (Ward 20 2025) | Surface as |
|---|---|---|---|
| Missing geography | `geography_status`, null coords | quality file per year | "n records could not be placed" |
| Contradictory beat assignment | `beat_mismatch` | **885 (11.3%)** | a footnote wherever a beat appears |
| Ward/CA frame disagreement | `ward_mismatch`, `community_area_mismatch` | 248 (3.2%) / 683 (8.7%) | methodology note |
| Classification change | `iucr` stability over time | stable 2006–2026 for prostitution | alert when a new IUCR appears or one stops |
| Source completeness change | manifest rows + reconciliation log | 210 rows marked `source_removed` (2017–2026) | "records the City has since withdrawn" |
| Small-number instability | count thresholds | Kenwood = 30/yr | suppress + explain |
| Duplicates / revisions | id uniqueness; release-to-release diff | ids unique; **2025 total moved 7,813 → 7,817** between retained releases | provisional badge |
| Missing reporting periods | year-file completeness | 2006–2026 complete, 2026 YTD | YTD flag |
| Abrupt coding-pattern change | share-by-IUCR step detection | discretionary step 2012→2016 | "mechanism: enforcement, not coding" |

This is the cheapest high-value feature in the whole programme: it is assembled entirely from
fields that already exist, and it is what separates an intelligence platform from a dashboard.

---

# PART 6 ASSESSMENT — advanced methods, kept or rejected

| Method | Verdict for NIP | Reason |
|---|---|---|
| **Statistical process-control charts** | **Adopt** for monthly monitoring | Natural fit for "is this outside normal variation"; assumptions (independence, stable variance) must be stated; clustered crime violates independence so limits are indicative |
| **Change-point detection** | **Adopt as candidate-flagging only** | Never auto-publish "crime changed in March"; flag for human review |
| **Time-series decomposition** | **Adopt, simple form** | 5-year monthly seasonal index; **reject** X-13/STL on small neighbourhood series — the adjustment would fit noise |
| **Spatial clustering (Moran's I / LISA)** | **Conditional** | Geometry stack now works, but needs `libpysal` (new dependency, approval). Meaningful at block-group/beat level; **not** at masked-block level where the unit is the privacy artifact |
| **Multivariate analysis / regression** | **Defer** | No denominators or covariates are ingested yet; regression on counts without population would be uninterpretable. Revisit after Census/ACS |
| **Interrupted time-series** | **Adopt only with a documented response + comparison area** | This is the correct tool for SARA Assessment; useless without a real intervention date |
| **Comparison-area analysis** | **Adopt** | Required alongside any ITS; also the displacement check |
| **Sensitivity analysis** | **Adopt, publish it** | Five specified in [A] Part 9.8 |
| **Uncertainty intervals** | **Adopt** | Poisson-style bands with the independence caveat |
| **Anomaly detection** | **Adopt, narrow** | Only as a data-quality signal (5J), never as an enforcement-targeting signal |
| Individual risk scores; demographic/socioeconomic proxies | **Rejected on principle** | Out of scope regardless of data availability |

**Claim-type labels** (mandatory on every view): DESCRIPTIVE FINDING · STATISTICAL ASSOCIATION ·
RESEARCH HYPOTHESIS · CAUSAL CLAIM. Only ITS-with-comparison-area may carry the last, and none
is proposed today.

---

# DELIVERABLE MAP — where each of the twelve is answered

| # | Deliverable | Location |
|---|---|---|
| 1 | Recovered capabilities & defects | **[A]** Parts 2–3 (inventory; D1–D9 defect register) |
| 2 | **Prostitution research design** | **[B]** Deliverable 1 (counts, history, classification, arrest-share, documented context) **+ this addendum, New Analysis 1** (district & just-outside tests; all 8 explanations adjudicated) |
| 3 | **Beat attribution resolution** | **[A]** Part 1 (full evidence) · **[B]** Deliverable 5 (summary). Recommendation unchanged: spatial for ward/CA selection, **CPD's field for beat attribution**, polygon for beat∩ward share, disclose both, 5 named tests |
| 4 | Innovative analytics inventory | **[B]** Deliverable 2 (3A–3H) **+ this addendum** (5B Gini measured, 5C measured, 5J designed, Part 6 verdicts) |
| 5 | Crime Trends IA / user journey | **[B]** Deliverable 3 (five connected views) · **[A]** Part 4 (F1–F11 specs) |
| 6 | Statistical & spatial methods plan | **[A]** Part 9 · **[B]** Deliverable 6 · **+ Part 6 table above** |
| 7 | External practice comparison | **[A]** Part 6 (CompStat, BOCSAR incl. Kendall tau-b, College of Policing/SARA, POP Center, concentration research) |
| 8 | Data availability matrix | **[A]** Part 8 · **[B]** Deliverable 7 · **+ addendum**: geometry stack now usable; `libpysal` missing |
| 9 | Updated product architecture | **[B]** Deliverables 4 & 8 (twelve domains into four surfaces; Overview↔Beat Meeting pipeline) |
| 10 | Prioritized roadmap | **[B]** Deliverable 9 (Tiers 0–7) · **+ addendum revision below** |
| 11 | Acceptance criteria | **[A]** Part 11 · **+ additions below** |
| 12 | CPD demonstration | **[B]** Deliverable 10 (prostitution study — evidence supports it; selected on merit, not novelty) |

## Roadmap revision (supersedes [B] Deliverable 9 only where noted)

**Tier 0b** gains one item, now the highest value-per-effort in the programme:
**the 5J measurement-intelligence panel** — assembled entirely from existing fields
(`beat_mismatch`, `ward_mismatch`, `geography_status`, manifest, reconciliation log,
release-to-release diff), no new data, and it directly prevents dataset artifacts being read as
neighbourhood change.

**Tier 4** gains: Gini/Lorenz concentration with the block-vs-segment caveat; crime-mix
transition with the enforcement-vs-coding note; SPC charts. `libpysal` (for LISA) is deferred to
its own approval.

**Smallest coherent first implementation is unchanged: Tier 0 + Tier 0b.**

## Acceptance criteria additions

- **Enforcement-sensitivity disclosure:** any category with arrest share >50% renders its
  enforcement-generated label; a test asserts the label appears for prostitution, narcotics,
  gambling, liquor.
- **Concentration reporting:** any concentration statistic publishes its spatial unit and states
  that the masked block is coarser than a street segment; a test fails if the unit is absent.
- **Composition changes:** a crime-mix view must carry the mechanism note (enforcement change vs
  coding change) and cite the IUCR-stability check.
- **Claim typing:** every published view carries exactly one of the four claim-type labels; CI
  fails on an unlabelled view.
- **Measurement intelligence:** the 5J panel's values are computed, not hardcoded; a test
  asserts the `beat_mismatch` figure matches a direct recomputation.

---

*Read-only. No code, configuration, data pointer, scheduler, deployment, dependency, or
repository state was changed. Production remains Render `e00665c`, `current` →
`bw-release-20260921`, scheduler OFF.*
