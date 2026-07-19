# Product Requirements

**Product.** Bronzeville–Woodlawn Observatory — a public civic-data site that tells
residents what is actually happening in their neighborhood, who is responsible for it, and
how confident anyone should be in the numbers.

**Status.** Nothing described here is built. The repository is in the data-foundation
phase. This document defines the target, not the present.

## Geographic scope

Bronzeville and Woodlawn, Chicago. Nothing else is published. City-wide figures appear only
as a comparison baseline.

Bronzeville is not one official community area and requires an approved custom boundary —
see [GIS_STRATEGY.md](../architecture/GIS_STRATEGY.md).

## Users

Residents first. Also: small business owners, CAPS and beat-meeting attendees, Nextdoor
community leads, journalists, community organizations, and elected or agency staff. Detailed
in [USER_PERSONAS.md](USER_PERSONAS.md).

The site is built for the resident who has ten minutes and no background in statistics. Every
other user is served by the same pages, not by separate expert tooling.

## Core resident questions

The site exists to answer these:

1. Is crime in my neighborhood going up or down, and over what period?
2. What kind of crime, and where — near me, or somewhere else in the neighborhood?
3. Is what I am seeing on my block a real pattern, or a few loud incidents?
4. Who is responsible for doing something about it?
5. What have they promised, and did they do it?
6. What else was going on at the time — policy changes, events, seasons?
7. How is my neighborhood changing — people, housing, businesses, voting?
8. Can I trust these numbers, and when were they last updated?

## MVP pages

| Page | Answers |
| --- | --- |
| **Neighborhood Overview** | What is happening here, in one screen |
| **Crime Trends** | Direction over time, by category and period |
| **Map** | Where — at block level, never exact addresses |
| **Beat Meeting Brief** | A printable one-page summary to bring to a CAPS meeting |
| **Who Is Responsible** | Which office owns which problem, and what they have committed to |
| **Community Change** | Population, housing, business, and voting context |
| **Data Health** | Freshness, completeness, and known gaps |
| **Methodology** | How every number is produced, in plain language |

## Requirements

**Plain language.** Methodology and page copy must be readable at a fourth-to-sixth-grade
level. If a resident cannot tell what a chart claims without a statistics background, the
chart is wrong for this site.

**Data transparency.** Every published statistic shows its source dataset and refresh date.
Any geography-dependent figure discloses how many records were excluded for missing
coordinates. Data Health is a first-class page, not a footnote.

**Accountability.** Responsibility is presented as a distribution across offices — direct
authority, budget authority, coordination influence, no direct control — not as a single
name to blame. Public commitments are tracked with evidence and may be marked `unclear`.
See [ACCOUNTABILITY_FRAMEWORK.md](../methodology/ACCOUNTABILITY_FRAMEWORK.md).

**Event and policy context.** Trends are shown against dated events and policy changes so
residents can see what else was happening. Timing association is labeled as association,
never as cause. See
[EVENTS_AND_POLICY_CONTEXT.md](../methodology/EVENTS_AND_POLICY_CONTEXT.md).

## Future phases

**Nothing in this section exists.** These are the long-term capabilities the project is
aiming at, recorded so the architecture does not paint itself into a corner. An item
appearing here is a direction, not a commitment or a schedule. The MVP above ships first;
each capability below still needs its own decision, and anything that changes how data is
interpreted needs an ADR.

Sequencing and priorities live in [ROADMAP.md](ROADMAP.md) and [BACKLOG.md](BACKLOG.md).

### Data foundation

| Capability | Status |
| --- | --- |
| Historical crime, 2006 to present | Planned — current critical path |
| Daily automated refresh | Planned |
| Bronzeville and Woodlawn only (scope holds at every phase) | Standing constraint |

### Core views

| Capability | Status |
| --- | --- |
| Interactive map | Planned — blocked on boundaries |
| Crime trends | Planned |
| Resident mode — the default, plain-language view | Planned |
| Beat meeting mode — printable, meeting-oriented view | Planned |

### Accountability

| Capability | Status |
| --- | --- |
| Alderman accountability dashboard | Planned |
| Ward scorecards | Planned |
| Police beat scorecards | Planned |

Scorecards carry a specific hazard: a ward or beat score invites the reader to conclude the
official *caused* the score. Wards and beats are also redrawn over time, so a scorecard
trend can move without anything real changing. Any scorecard must state the authority type
behind each measure ([ACCOUNTABILITY_FRAMEWORK.md](../methodology/ACCOUNTABILITY_FRAMEWORK.md))
and must not be built as a ranking of people.

Note also that ward and beat scorecards report on **ward and beat geography** — they are not
a back door to defining Bronzeville, which still requires its approved boundary
([GIS_STRATEGY.md](../architecture/GIS_STRATEGY.md)).

### Community context overlays

| Capability | Status |
| --- | --- |
| Census overlays | Planned |
| Income overlays | Planned |
| Population changes | Planned |
| Election turnout | Planned |
| Building permits | Planned |
| Vacant buildings | Planned |
| Street lighting | Planned |
| 311 requests | Planned |
| CTA stations | Planned |
| Schools | Planned |
| Parks | Planned |

Every overlay adds a variable a reader will be tempted to read as an explanation. More
context is not automatically more truth. Each arrives with its own guardrails or not at all.

### Analysis

| Capability | Status |
| --- | --- |
| Domestic violence trend analysis | Planned — see caution below |
| Holiday calendar | Planned |
| Sports calendar | Planned |
| COVID timeline | Planned |
| Policy timeline | Planned |
| Federal funding timeline | Planned |

**Domestic violence needs extra care.** Reporting rates for domestic violence are strongly
affected by willingness to report, shelter capacity, and police practice, so a fall in
reports may mean fewer incidents *or* fewer people willing to call. It is also the category
where small counts and household-level detail most risk identifying individuals. Any DV
analysis must state this openly and must not narrow to a granularity that could expose a
household.

The four timelines are **context, not cause**, without exception
([EVENTS_AND_POLICY_CONTEXT.md](../methodology/EVENTS_AND_POLICY_CONTEXT.md)).

### Distribution

| Capability | Status |
| --- | --- |
| Downloadable reports | Planned |
| Public fact sheets | Planned |

Anything downloadable or shareable leaves the site and loses its surrounding context. Every
exported artifact must carry its source, refresh date, boundary version, and exclusion
counts *inside* the artifact, so that a screenshot or a printout is still honest on its own.

## Non-goals

- **Not a crime-alert or real-time-safety app.** Data lags roughly seven days.
- **Not predictive policing.** No forecasting of where or by whom crime will occur.
- **No person-level profiling, suspect identification, or nationality-based risk analysis.**
  Hard constraint — see [SECURITY.md](../architecture/SECURITY.md).
- **No exact addresses.**
- **No causal claims.** The site shows association and context; it does not assert cause.
- **Not a city-wide dashboard.** Two neighborhoods, done properly.
- **Not a replacement for official data.** It is a lens on official data, always cited.
