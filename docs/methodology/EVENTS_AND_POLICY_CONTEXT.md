# Events and Policy Context

Residents reasonably ask "what changed?" when a trend moves. This document defines how the
project supplies that context — and the hard limits on what may be claimed from it.

**Not built.** Specification for the `event_calendar` and `policy_event` entities.

## Event categories

| Category | Examples |
| --- | --- |
| **COVID periods** | Stay-at-home orders, phased reopenings, school closures |
| **Federal and local policy changes** | Ordinances, state statutes, federal enforcement actions, CPD policy shifts, bond reform |
| **Sports events** | Home games, playoff runs, large-draw events |
| **Holidays** | Federal and cultural holidays, long weekends |
| **School calendar** | Term start and end, breaks, early-release days |
| **Weather** | Heat waves, cold snaps, major storms, unusually warm stretches |
| **Neighborhood events** | Festivals, parades, large gatherings, construction closures |

## These are contextual variables — nothing more

Every item above is **context**. It is displayed *next to* a trend so a reader can see what
else was happening. It is never presented as the reason the trend moved.

### Timing association does not establish causation

Crime is seasonal. Reporting behavior changes. Policies are enacted *because* of trends as
often as trends follow policies. Multiple events overlap constantly — in any given month
there is a holiday, a weather pattern, a school-calendar change, and usually a policy
change. Something will always line up.

An overlay showing a trend change near a dated event establishes **only** that the two
happened around the same time.

**Prohibited in published copy:** "crime rose *because of*", "*driven by*", "*due to*", "*the
result of*", "X *caused* Y". **Required instead:** "crime rose *during*", "this change
*coincided with*", "*we cannot say from this data whether* X affected Y."

### Claims about groups of people

**Any claim that a group of people — Venezuelans, migrants, or any nationality, ethnicity, or
immigration status — is associated with a change in crime must be labeled explicitly as a
hypothesis, not a finding.**

More fundamentally: **nationality and immigration status cannot be inferred from crime
data.** The Chicago crime dataset contains no such fields. Any analysis purporting to link
them is not measuring what it claims to measure — it is measuring an assumption someone
introduced. The correct response to such a hypothesis is to state plainly that **this data
cannot answer it**, and to say what data would be required and why it is not available here.

This is a hard constraint, not a stylistic preference. See
[SECURITY.md](../architecture/SECURITY.md).

## Before / during / after analysis

Trends may be examined in **before, during, and after** windows around a dated event. When
this is done:

- **Window boundaries are stated** and chosen before looking at results — not tuned until an
  effect appears.
- **Alternative explanations are shown alongside**: seasonality, the ~7-day reporting lag,
  concurrent events, changes in reporting behavior, boundary or grouping changes, and small
  counts producing noisy percentages.
- **Baseline comparison is included** — the same window in prior years, and the citywide
  trend, so a neighborhood change is not mistaken for a local one when the whole city moved.
- **Uncertainty is stated.** In two neighborhoods, counts for a specific crime type in a
  short window are often small, and small numbers swing wildly in percentage terms.

If, after alternatives are shown, the honest answer is "we cannot tell," the site says that.
"We cannot tell from this data" is a legitimate and frequently correct published conclusion.
