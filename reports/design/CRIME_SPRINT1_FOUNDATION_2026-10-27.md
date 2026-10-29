# Crime Sprint 1 foundation — 2026-10-27

**Design record, locked for Sprint 1 (owner decisions 11–17, 2026-10-27).** It fixes the
contracts that Crime Analytics Sprint 1 (Foundation + Change core) builds against. Owner decisions referenced here are recorded in
`NIP_CRIME_ANALYTICS_INNOVATION_CATALOGUE.md` (2026-10-27 decision record). Production sequencing is in
`docs/PRODUCTION_CATCHUP_PLAN_2026-10-27.md`.

Contents: §1 Gold crime aggregate contract · §2 Serious-offense overlay (proposal; needs owner
sign-off) · §3 Retiring the Trends placeholders · §4 Reproducibility register.

---

## 1. Gold crime aggregate contract

Gold is approved (owner, 2026-10-27) as the layer for release-aware, precomputed crime
aggregates. **Silver stays the system of record.** Gold is a derived cache with a proof
attached. It is never edited, never a source for another Gold product, and never read if its
proof fails.

### 1.1 Location and release identity

```
<release_root>/                         e.g. /var/data/bw-release-20261028
  release.json                          APPROVED identity contract: release_id, cut_at,
                                        data_through, source_watermark, source dataset id,
                                        source manifest digest, Silver digest identity,
                                        builder commit, config digest, status
  gold/crime/
    _build.json                         build proof (§1.4)
    daily_counts.parquet                the base aggregate (§1.2)
    coverage.parquet                    which days are covered, per year (§1.3)
    revisions/<prior_id>__<this_id>/events.parquet   incident-level revision events (§1.5)
```

- **`release_id` is written explicitly**, not inferred from the directory name (owner decision
  11). `findings._release_name` returned the resolved directory name, which locally is `data`.
  `release.json` is the authority; a local development root carries a clearly marked
  development id (`dev-…`) and `status: development`.
- Every release root carries its own Gold. **An archived release keeps the Gold it was cut
  with**, so an archived brief or chart is reproducible from that archive alone.
- The API reads Gold only from the root `Settings` pinned for the request (`_pin_data_root`).
  No code path opens a second root, with one exception: the revision table, which is
  precomputed *into* the newer release at cut time.

### 1.2 `daily_counts.parquet`, the single base table

| Column | Type | Notes |
|---|---|---|
| `release_id` | string | repeated on every row, so a stray file cannot be mistaken for another release |
| `geography_id` | string | `ward20` and the nine `community_area_portion` ids from `config/geographies.yml`; **never** `bronzeville`; `back-of-the-yards` absent (unavailable, never zero) |
| `geography_kind` | string | `ward` / `community_area_portion` |
| `date` | date | the incident `date` (occurrence, per source metadata), Chicago local date |
| `year`, `month` | int16 | derived from `date`; stored for partition pruning |
| `primary_type` | string | source value as published (both `CRIM SEXUAL ASSAULT` spellings kept; grouping is config) |
| `fbi_code` | string | the source's NIBRS classification. Needed for the serious-offense overlay (§2); IUCR-level grain is deferred to Sprint 3 |
| `broad_category` | string | from `config/crime_categories.yml` `broad_categories`, **the mutually exclusive partition** |
| `count` | int32 | rows in `current_source_view` (excludes `source_removed`) |
| `count_source_removed` | int32 | rows excluded as `source_removed`, kept so exclusions are visible and reconcilable |

- **Grain:** one row per (`geography_id`, `date`, `primary_type`, `fbi_code`). Sparse: no row
  means zero, **but only inside a covered day** (§1.3).
- **Why daily, not monthly:** like-for-like windows cut on a day. Year-to-date through 09-06
  against the prior year through 09-06, or the trailing 365 days ending 09-06, cannot be built from
  monthly totals without fabricating the partial month. Monthly and annual series are rollups of
  this table at read time.
- **Size (INFERRED):** Ward 20 has ≈ 8k incidents a year, giving under 1M rows over 21 years
  for the ward plus its portions. Small enough that every rollup is runtime arithmetic.
- **Placement:** `spatial_ward_current == "20"` and `spatial_community_area` only; never the
  source `ward`/`community_area`. The 2023 ward map is applied to every year, and this is disclosed.

### 1.3 `coverage.parquet`

One row per (`year`, `date`) that the release covers: `date ≤ data_through`, plus
`month_complete` (bool) and `provisional` (bool, using the existing 60-day rule from
`measurement._is_provisional`, keyed to the actual newest record and never the wall clock).
Coverage stops a missing day being read as a zero, and stops a partial month being compared
with a full one.

### 1.4 `_build.json`, the proof that makes Gold controlled

```json
{
  "release_id": "bw-release-20261028",
  "built_at": "…Z",
  "builder_commit": "<git sha>",
  "config_sha256": {"crime_categories.yml": "…", "geographies.yml": "…"},
  "inputs": {"bronze_manifest_sha256": "…", "silver_partitions_sha256": {"2006": "…", "…": "…"}},
  "data_through": "YYYY-MM-DD",
  "source_watermark": "…",
  "reconciliation": {"2025": {"silver_current_view_ward20": 7817, "gold_sum_ward20": 7817, "pass": true}, "…": {}},
  "status": "PASS"
}
```

**Rules:**

1. The builder **fails** unless, for every year and every geography, Σ`count` equals the count of
   `current_source_view` rows in Silver⋈Bronze, and Σ`count_source_removed` equals the
   `source_removed` rows. The portions' sum must equal the ward's (every ward point lies in
   exactly one community area; this is verified, not assumed).
2. **Runtime integrity is cheap** (owner decision 14). On a request the API compares only small
   identities: `release.json` `release_id` against `_build.json`, the digest of the small
   input-ledger files (Bronze manifest, refresh log, reconciliation log) against the digest
   recorded at build, and `_build.json` `status == PASS`. It never hashes or scans Silver per
   request; full Parquet checksums belong to release build, release verification and
   deployment acceptance. **On any disagreement Gold is STALE:** the endpoint answers
   `aggregates_stale` with no figures, and never silently recomputes or mixes inputs.
3. **Releases are immutable** (owner decision 13). Gold is built once, in the candidate release,
   before it becomes public. Automated publication, when built, is copy-on-write: active →
   candidate copy → refresh → reconcile → rebuild Gold → verify → atomic pointer switch. A
   failed candidate never becomes public. Nothing refreshes `current` in place.
4. A config change (for example a new overlay member) changes `config_sha256` and therefore
   requires a rebuild. Overlays are not stored (§1.6), so this matters only for `broad_category`.

### 1.5 `revisions/<prior>__<this>/events.parquet`, incident-level revision events

Owner decision 15. Built from the prior **archived** release (verified by its `.sha256`) and
the new one. **One row per incident id whose state differs between the releases**, over every
id placed in Ward 20 in either release. An id appears once however many attributes changed.

Columns: `id`, `prior_release_id`, `current_release_id`, `exists_prior`, `exists_current`;
`old_`/`new_` for `date`, `year`, `month`, `primary_type`, `fbi_code`, `arrest`, `domestic`,
`ward` (spatial), `community_area` (spatial) and `source_status`; boolean reason flags `added`,
`removed`, `reclassified`, `date_changed`, `geography_changed`, `arrest_changed`,
`domestic_changed` (several may be true at once).

Every revision summary is derived from this table. For any analytical cell (geography × year ×
month × primary type, current-source view) the build checks
`current_count − prior_count = entries_to_cell − exits_from_cell`, where an entry is an event
whose new state is in the cell and whose old state is not, and an exit is the reverse. Reason
flags are never summed across reasons, because one incident can carry several.

**What CA-11 can and cannot say.** Two retained releases exist today (July 2026-07-26 and
September 2026-09-21, both archived locally). The source has **no separate report-date field**
(`date` = "Date when the incident occurred"; `updated_on` = "last updated", per the dataset's
own metadata), so a reporting-lag curve is approximated by comparing releases, never by a
report date.

### 1.6 What is *not* a separate table

- **Annual totals:** a rollup of `daily_counts`, tested against Silver.
- **Overlays** (enforcement-generated, narcotics, motor-vehicle theft, serious-offense subset):
  computed at read time from `primary_type`/`fbi_code` and config. Storing them would create a
  second definition of each. Every overlay result is labelled "overlay, not additive" and is
  never stacked to 100% (owner decision 9).
- **Geography portions:** already the `geography_id` dimension.

---

## 2. Serious-offense overlay — APPROVED 2026-10-27 as "Selected FBI/NIBRS violent-offense classes"

**Owner decision 12** resolved §2.3 as proposed: follow `fbi_code`; exclude `01B`, `08A`, `08B`;
include officer / protected-employee 04A/04B with an enforcement-contact caveat; sensitive-victim
classes count but are never broken out; attempts stay where coded. The text below is the
analysis that decision rests on.

**This is not a score and not a weight.** It is an auditable subset of records, used as an
overlay, next to the partition and never summed with it. Unweighted composition is approved
(CA-09); harm weighting is rejected.

### 2.1 Source basis (VERIFIED 2026-10-27)

The dataset's own `fbi_code` column: "Indicates the crime classification as outlined in the
FBI's National Incident-Based Reporting System (NIBRS). See the Chicago Police Department
listing of these classifications at https://gis.chicagopolice.org/pages/crime_details"
(portal metadata for `ijzp-q8t2`). The proposal uses the source's classification instead of a
reading of description text.

**Consistency check** (local release, citywide, 2006–2026; the counts are inventory, not
findings): every IUCR code maps to exactly one `fbi_code` across all 21 years. The build must
re-assert this every release and **fail** if an IUCR acquires a second code or an unknown code appears.

### 2.2 Proposed members

| `fbi_code` | Meaning | `primary_type` | IUCR covered | Citywide records 2006–2026 |
|---|---|---|---|---|
| `01A` | Murder and non-negligent manslaughter | HOMICIDE | 0110, 0130 | 11,461 |
| `02` | Criminal sexual assault, incl. attempts and non-aggravated | CRIMINAL SEXUAL ASSAULT / CRIM SEXUAL ASSAULT | 0261–0266, 0271–0275, 0281, 0291 | 32,898 |
| `03` | Robbery, incl. vehicular hijacking and attempts | ROBBERY | 0312, 0313, 031A, 031B, 0320, 0325, 0326, 0330, 0331, 0334, 0337, 033A, 033B, 0340 | 232,607 |
| `04A` | Aggravated assault | ASSAULT | 051A, 051B, 0520, 0530, 0550–0553, 0555–0558 | 124,311 |
| `04B` | Aggravated battery | BATTERY | 041A, 041B, 0420, 0430, 0450–0453, 0461, 0462, 0479–0483, 0485, 0487–0489, 0495–0499 | 173,243 |

**Not every ASSAULT or BATTERY is included.** `08A` (simple assault, 310,498) and `08B` (simple
battery, 953,064) are excluded.

### 2.3 Ambiguities (resolved by owner decision 12, 2026-10-27, as proposed below)

1. **Description says "aggravated", FBI code says simple.** These IUCR codes are FBI `08A`/`08B`:
   - `0440` "AGGRAVATED – HANDS, FISTS, FEET, NO / MINOR INJURY"
   - `0454` "AGGRAVATED P.O. – HANDS … NO / MINOR INJURY"
   - `0554` "AGGRAVATED POLICE OFFICER – HANDS … NO INJURY"
   - and the protected-employee codes `0545`/`0484`

   Illinois statute aggravates them by victim status; the NIBRS code does not.
   **Proposal: follow `fbi_code` (exclude) and say so in Definitions & Methods.**
2. **`01B` involuntary manslaughter / reckless homicide** (87 citywide records) sits under CPD's
   HOMICIDE type but outside NIBRS `01A`. **Proposal: exclude, and disclose that the overlay's
   homicide count can be lower than the HOMICIDE primary type.**
3. **Officer and protected-employee victims** (`0550`–`0558`, `0450`–`0453`, `0461`, `0462`,
   `0480`–`0483`) are partly a product of police contact. **Proposal: include, with the
   enforcement-contact caveat.** The alternative is to report them as a separate disclosed line.
4. **Sensitive victim classes** inside `04B`: domestic (`0488`, `0489`, `0496`–`0499`), child
   (`0485`), unborn child (`0487`), senior (`0495`). **Proposal: include in the counts; never
   break them out below the overlay level** (the CA-06 and CA-13 privacy rules apply).
5. **Not proposed:** KIDNAPPING and HUMAN TRAFFICKING (FBI `26`), SEX OFFENSE (`17`). These are
   outside the NIBRS violent set. Listing them as members would need its own decision.
6. **Attempts** are included wherever the source codes them inside `02`/`03`, as NIBRS does.

### 2.4 Config representation (`config/crime_categories.yml`)

```yaml
# Overlays: labelled subsets, NOT part of the broad_categories partition. A record can be
# in several overlays; overlay counts are never stacked or summed to a total.
overlays:
  selected_fbi_violent:
    label: "Selected FBI/NIBRS violent-offense classes"
    status: approved            # owner, 2026-10-27
    basis: >-
      Source field `fbi_code` (NIBRS classification, per dataset ijzp-q8t2 metadata and the
      CPD crime-details listing). Membership is by code, never by description text.
    fbi_codes: ["01A", "02", "03", "04A", "04B"]
    excluded_note: >-
      Excludes 01B (involuntary manslaughter / reckless homicide) and every 08A/08B record,
      including IUCR 0440, 0454, 0554, 0545 and 0484, whose descriptions say "aggravated" but
      which the source codes as simple assault or battery.
    caveats: [officer_victim_contact, sensitive_victim_no_breakout]
```

The overlay is never described as a severity, harm or safety measure.

---

## 3. Retiring the Trends placeholders

### 3.1 Audit of `apps/web/src/routes/trends.tsx` (2026-10-27, branch `feature/city-services-311`)

| Element | Line | Problem | Action |
|---|---|---|---|
| `PendingControl` "Crime group: All / Violent / Property / **Quality of life**" | 56–59 | "Quality of life" is not a defined category. Violent and property are partition members, but no other groups are offered. | **Remove** |
| `PendingControl` "Show: Counts / **Rate per 1,000**" | 64 | No population denominator is ingested; rates are impossible today | **Remove** |
| `PendingControl` "Compare with: Prior year / **5-year baseline**" | 65 | No baseline method exists | **Remove**; Sprint 1 replaces it with real comparison windows |
| `PendingControl` "Period: Last 12 months / 5 years / 10 years" | 61–63 | Implies a working multi-year trend | **Remove**; Sprint 1 replaces it |
| `PendingControl` "Geography" | 55 | Duplicates the shell selector | **Remove** (the shell owns `?geo=`) |
| `PendingVisual` "monthly line + five-year band" | 73–76 | A fake chart outline | Replace with the Sprint 1 trend-context chart |
| `PendingVisual` "Category change vs prior year" | 89–92 | A fake chart outline | Replace with the Sprint 1 decomposition table |
| `ComingSoonNotice` | 33–37 | Accurate today | Narrow it to the sections still unbuilt once Change is live |

Out of Trends scope, but the same pattern, logged for a later lane (not Sprint 1):

- `beat-meeting.tsx:90`: a "Quality of life" `PendingStat`.
- `beat-meeting.tsx:71`: hardcoded beat options 0311–0314.
- `community-change.tsx:47`: pending metric controls.
- `IncidentsTable.tsx:17-41`: a hardcoded list of 13 crime types, which contradicts
  `crime_categories.yml` ("never duplicated in application code").

### 3.2 The Sprint 1 shell

```
Trends — "Is it getting better or worse?"     (geo + year from the shell; nothing page-local)
├─ 1 · Change                    LIVE in Sprint 1
│     comparison window: YTD vs same YTD · trailing 365 days vs previous 365 days · last full year
│       (API key `t12m`; equal 365-day exposure, owner 2026-10-28)                ← real control
│     decomposition table (all types, counts first, contribution, reconciliation row)
│     long-run composition (partition) + overlays (separately, never stacked to 100%)
│     trend context (monthly, rolling 12 complete calendar months, 3/5/10-year, full history)
│     direction: Kendall tau-b on complete annual totals (tau, p, n, descriptive label)
│       — SPC limits and change points are DEFERRED (separate CA-12 review)
│     same-calendar-span history (prior 5 / 10 years: min, median, max, current)
│     provisional + revision panel (both release ids named)
├─ 2 · Geography                 "Not yet built." + one sentence on what it will answer
├─ 3 · Circumstances             same
├─ 4 · Investigations            same
├─ 5 · Definitions & Methods     static methods text only: geography frame, source vs spatial
│                                fields, source_removed exclusion, provisional rule, no report
│                                date, enforcement-generated overlay, min_prior suppression,
│                                CA-03 research note
└─ City Services — potholes      unchanged, after PR #4 merges
```

Rules: no disabled control anywhere; a not-yet-built section shows a heading plus one plain
sentence, with no skeleton chart; every live figure states its geography, period and release;
the page heading never answers "safer". The placeholder removal is the first commit of the
Sprint 1 PR, so the page does not briefly ship fake controls next to real ones.

---

## 4. Reproducibility register

**Rule:** a figure in a design report is not publishable. Each must be recomputed by
committed, tested analytical code against a named release, and the code's output is what is
published. **No figure below may be typed into config, copy, or code.** "Report" letters refer
to the 2026-09-22 reports in `reports/design/` (Cat = catalogue; A = analytical redesign;
B = integrated architecture; C = crime addendum; D = neighborhood addendum). All originals were
computed ad hoc over SSH against `bw-release-20260921` (A:22, A:30-38), and no script or
notebook for them exists (A:172).

| # | Finding | Original number(s) | Period | Geography | Report | Reproducible code today? | Rebuilt in | Status |
|---|---|---|---|---|---|---|---|---|
| R-01 | Long-run crime mix | 17,483 → 7,817 (−55%); discretionary share 16.8% → 5.6%; violent 35.1% → 38.7%; property 41.9% → 47.5% | 2006 → 2025 | Ward 20 | Cat:174-176; C:156-169 | No | Sprint 1 | **REQUIRES RECOMPUTATION BEFORE PUBLICATION** |
| R-02 | Discretionary collapse | 16.9% → 5.1% | 2012 → 2016 | Ward 20 | C:166-169 | No | Sprint 1 | **REQUIRES RECOMPUTATION BEFORE PUBLICATION** |
| R-03 | Net change | −398 (reports said −4.6%) | 2025 vs 2024, same period | Ward 20 | A:277, 527, 635 | **Yes**: F-001 `calc_overall_change`, tested; corrected to 7,817 vs 8,215, −4.8% | done (on `main`, not deployed) | Reproducible; **the −4.6% is SUPERSEDED** |
| R-04 | Category contribution decomposition | only Σ = −398 reported; no per-type contributions | 2025 vs 2024 | Ward 20 | A:277, 293-298 | Partial: per-type Δ in `category_drivers`; no contribution share or reconciliation | Sprint 1 | **REQUIRES RECOMPUTATION BEFORE PUBLICATION** |
| R-05 | Motor-vehicle-theft historical share | 4.9% → 13.2% (2023) → 8.4% | 2006 → 2023 → 2025 | Ward 20 | Cat:174-176 | No | Sprint 1 (overlay) | **REQUIRES RECOMPUTATION BEFORE PUBLICATION** |
| R-06 | MVT count | 659 | 2025 | Ward 20 | D:65 | Partial (driver row) | Sprint 1 | **REQUIRES RECOMPUTATION BEFORE PUBLICATION** |
| R-07 | Serious-offense composition | total 8,384 → 7,817 (Ward 20); homicide 12 → 13 and robbery 128 → 87 **were not Ward 20** — whole-Woodlawn-community-area counts inserted into a Ward 20 statement (§4.1) | 2023 → 2025 | stated as Ward 20; **mixed frames** | Cat:253-254; D:85-97 | Yes since Sprint 1 (Ward 20 values in §4.1); mapping approved 2026-10-27 (§2) | Sprint 1 | **WITHDRAWN** (geography-mixing transcription error); cite only the code-derived Ward 20 values |
| R-08 | Revision between releases | 7,813 → 7,817 | July → September release, year 2025 | Ward 20 | Cat:275-277 | No release comparison exists | Sprint 1 (§1.5) | **REQUIRES RECOMPUTATION BEFORE PUBLICATION** |
| R-09 | Source withdrawals | 210 `source_removed` (5 in Ward 20) | 2017–2026, reconciliation of 2026-09-15 | citywide / Ward 20 | A:686-688 | **Yes**: the reconciliation log and Silver `source_status`; re-derived 2026-10-27 | done | Reproducible (operational fact, not a finding) |
| R-10 | Concentration / Gini | Gini 0.542 / 0.557 / 0.581; share of blocks holding 50% of reports 16.3% / 14.8% / 13.2% | 2016 / 2020 / 2025 | Ward 20, masked block | Cat:351-352; C:133-137 | No | Sprint 2 | **REQUIRES RECOMPUTATION BEFORE PUBLICATION** |
| R-11 | Gini by portion | Woodlawn 0.504; Englewood 0.609; citywide 0.586 | 2025 | portions; citywide | D:61-66 | No (no citywide geography in the product) | Sprint 2 | **REQUIRES RECOMPUTATION BEFORE PUBLICATION** |
| R-12 | Repeat masked blocks | 692 blocks; busiest 221; top 10 = 15.2%; 74 blocks carry more than one CPD beat | 2025 | Ward 20 | Cat:222-223; A:97 | Partial: the single top block (`pulse.py:711`) | Sprint 2 | **REQUIRES RECOMPUTATION BEFORE PUBLICATION** |
| R-13 | Coordinate masking | 3,438 distinct points for 7,817 incidents; busiest point 96 | 2025 | Ward 20 | Cat:193-195 | No | Sprint 5 (CA-03 note) | **REQUIRES RECOMPUTATION BEFORE PUBLICATION** |
| R-14 | Prostitution investigation | 372 (2006) → ≈ 0–1; arrest-flagged 99.3 / 99.8 / 91.5% | 2006–2026 | as stated in each source table | B:50-66, 117-121; C:63-113; Cat:39-51, 161-163 | Partial: enforcement flag only | Sprint 4 | **REQUIRES RECOMPUTATION BEFORE PUBLICATION** |
| R-15 | Discretionary collapse by type | gambling −99.0%; narcotics −86.7%; battery −47.1% | per B | per B | B:130-137 | No | Sprint 4 | **REQUIRES RECOMPUTATION BEFORE PUBLICATION** |
| R-16 | Burglary circumstances | n = 250: forcible entry 93, from motor vehicle 68, unlawful entry 67; apartment 97, street 54; 54% (135/250) classifiable | 2025 | Ward 20 | Cat:295-301; A:322-329 | No | Sprint 3 / 4 | **REQUIRES RECOMPUTATION BEFORE PUBLICATION** |
| R-17 | Burglary YTD | 262 (2026 YTD) vs 250 | 2026 YTD vs 2025 | Ward 20 | A:278, 527-528 | No; the report marks it DRAFT/ILLUSTRATIVE | Sprint 4 | **REQUIRES RECOMPUTATION BEFORE PUBLICATION** |
| R-18 | Location-description quality | 99.7% populated; 72 values; 4.2% of times exactly midnight | 2025 | Ward 20 | Cat:295-301 | No | Sprint 3 | **REQUIRES RECOMPUTATION BEFORE PUBLICATION** |
| R-19 | Arrest flag, overall | 16.5% | 2025 | Ward 20 | Cat:264-265 | **Yes**: `/pulse` `arrests.percent` 0.1649 (live) | done | Reproducible |
| R-20 | Arrest flag by area / category | Englewood portion 20.2% vs Woodlawn portion 15.7%; prostitution 91.5%; citywide 16.1% | 2025 | portions; citywide | Cat:264-265; D:61-66 | Partial: per-portion overall share via `/pulse?geo=`; nothing by category or citywide | Sprint 3 | **REQUIRES RECOMPUTATION BEFORE PUBLICATION** |
| R-21 | Neighborhood comparison | whole-CA counts Englewood 5,086 vs Woodlawn 3,848; per square mile 1,855 vs 1,656; robbery in the portions 58 vs 57; gap ratio 1.70 → 1.32; areas 2.074 / 3.072 sq mi | 2006–2025 | **whole community areas** and portions | Cat:359-362; D:61-121 | No; whole-CA figures are outside the product frame and must be labelled as such if ever shown | Sprint 2 | **REQUIRES RECOMPUTATION BEFORE PUBLICATION** |
| R-22 | Area vs incident share | area 50.1% / 23.0%; incidents 77.0% / 14.7% | 2025 | Woodlawn / Englewood portions | D:26-33 | **Yes**: area shares in `config/geographies.yml`; incident shares F-010 `calc_portion_distribution` | done (on `main`) | Reproducible |
| R-23 | Geography sensitivity, mismatch counts | beat 885 (11.3%); ward 248 (3.2%); community area 683 (8.7%) | 2025 | Ward 20 | Cat:318-321; A:71-78 | **Yes**: `measurement.measurement_notes`, tested | done (on `main`) | Reproducible |
| R-24 | Geography sensitivity, beat series | beat mismatch 10.4–12.4% by year; beat 0233: 514 by PIP vs 337 by field; 84% adjacent-beat cause | multi-year | Ward 20 | A:71-104 | No | Sprint 5 | **REQUIRES RECOMPUTATION BEFORE PUBLICATION** |
| R-25 | Beats straddling the ward | reports: 16 of 21 beats under 95% inside the ward | 2025 | Ward 20 | Cat:318-321; A:211-212 | **Yes**: whole-beat context; **SUPERSEDED** by 19 of 23 (PROJECT_STATUS V2-006) | done (on `main`) | Reproducible at the corrected value |
| R-26 | Domestic battery | 380 battery; 193 by description; 206 by flag; 50.8%; 69.4% in apartments | 2026-01-01 → 07-02 | **whole Woodlawn community area, pre-V2: not a product geography** | A:179-197, 223-224 | No | Sprint 4 | **REQUIRES RECOMPUTATION BEFORE PUBLICATION**, and the frame itself is invalid |

Theft and criminal-damage investigations have **no** research figure to register (none was computed).

### 4.1 Sprint 1 reproduction check (2026-10-27)

Recomputed by committed code (`gold.crime_aggregates`, `presentation.change`) from scratch
extractions of the retained archives — `bw-release-20260921` (SHA-256 matches its sidecar) and
`bw-release-20260726` — with retroactive `release.json` written into the extractions only. Ward 20
unless stated. **The code-derived value is authoritative; nothing was tuned to agree.**

| # | Finding | Old research value | Reproducible value | Result | Explanation |
|---|---|---|---|---|---|
| R-01 | Total 2006 → 2025 | 17,483 → 7,817 (−55%) | 17,483 → 7,817 (−55.3%) | MATCH | |
| R-01 | Violent share (broad partition) | 35.1% → 38.7% | 35.1% → 38.7% | MATCH | |
| R-01 | Property share | 41.9% → 47.5% | 41.9% → 47.5% | MATCH | |
| R-01 | Discretionary / enforcement-generated share 2006 → 2025 | 16.8% → 5.6% | 16.8% (2,935) → 5.7% (448 of 7,817 = 5.73%) | DIFFER (0.1 pp) | Rounding or a slightly different ad-hoc type list; the configured overlay list is now the definition |
| R-02 | Enforcement-generated share 2012 → 2016 | 16.9% → 5.1% | 16.9% → 5.2% (453) | DIFFER (0.1 pp, 2016) | As above |
| R-05 | Motor vehicle theft share 2006 / 2023 / 2025 | 4.9% / 13.2% / 8.4% | 4.9% (858) / 13.2% (1,104) / 8.4% (659) | MATCH | |
| R-06 | MVT count 2025 | 659 | 659 | MATCH | |
| R-03 | Net change 2025 vs 2024 | −398 (reported −4.6%) | 7,817 vs 8,215: −398, −4.8%; Σ type Δ reconciles | MATCH (net); −4.6% superseded | |
| R-04 | Largest type changes 2025 vs 2024 | not computed | weapons violation −164, battery −130, robbery −111, MVT −68, deceptive practice +51, narcotics +44 | NEW | First reproducible decomposition |
| R-07 | Totals 2023 → 2025 | 8,384 → 7,817 | 8,384 → 7,817 | MATCH | |
| R-07 | Homicide 2023 → 2025 | 12 → 13 | Ward 20: 28 → 13 (`01A` 28 → 13) | INVALID (mixed frames) | 12 is the **whole Woodlawn community area** 2023 count (D:85-97); 13 matches Ward 20 2025 (and whole Englewood 2025). Whole Woodlawn 2025 is 7 |
| R-07 | Robbery 2023 → 2025 | 128 → 87 | Ward 20: 334 → 225 | INVALID (mixed frames) | 128 and 87 are the **whole Woodlawn community area** counts (D:85-97), not Ward 20 |
| R-07 | Selected FBI/NIBRS violent classes 2023 → 2025 | — | 1,149 (13.7%) → 946 (12.1%) | NEW | Approved overlay, first computation |
| R-08 | Revision July → September, year 2025 | 7,813 → 7,817 | 7,813 → 7,817 (+5 entries / −1 exit); 2024: 8,216 → 8,215 | MATCH | 19 incidents touch 2024–2025: 4 added, 2 withdrawn, 1 reclassified, 1 re-placed, 11 arrest-flag changes (reasons not additive) |
| R-09 | Source withdrawals in Ward 20 | 5 | 2024: 1 · 2025: 1 · 2026: 3 | MATCH | |

Publication status after this check: R-01 (total, violent, property), R-05, R-06, R-03, R-08 and R-09
are **reproducible by committed code** against `bw-release-20260921`; R-01/R-02 enforcement shares
are reproducible at the code-derived values; the R-07 homicide/robbery research figures are
**withdrawn and must not be cited as Ward 20** — the code-derived Ward 20 values replace them.
Nothing from this table is typed into the application; the page computes every figure live.

**R-07 cause (VERIFIED, independent review 2026-10-27).** The catalogue's CA-09 statement mixed
geography frames — a research/transcription error, not a data, period, subtype or
reported-ward effect. Recomputed from `bw-release-20260921`, spatial placement, current-source
view:

| Geography | 2023 total / homicide / robbery | 2025 total / homicide / robbery |
|---|---|---|
| Ward 20 | 8,384 / 28 / 334 | 7,817 / 13 / 225 |
| Whole Woodlawn community area | 3,915 / 12 / 128 | 3,848 / 7 / 87 |

The statement took Ward 20's totals and inserted whole-Woodlawn homicide (2023) and robbery
(2023, 2025) counts; its 2025 homicide 13 matches Ward 20 (and, by coincidence, whole
Englewood). Source-reported ward placement gives neither (2023: 29 / 337 of 8,469). Rule
restated: a whole-community-area figure is never presented as a Ward-portion or Ward-wide
value. Other rows from the same addendum were checked: R-20 (portion arrest shares 15.7% /
20.2%) and R-21 (portion robbery 57 / 58) recompute exactly as Ward 20 portions; R-11 (Gini by
portion) draws on the same table and must be checked for the same error when it is rebuilt.
