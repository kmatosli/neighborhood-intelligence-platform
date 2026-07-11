# Future Ideas

**None of these are approved scope.** They are parked here so they are not lost and not
smuggled into the roadmap. Anything moving from this page to
[BACKLOG.md](../product/BACKLOG.md) needs a deliberate decision, and anything that changes
how the data is interpreted needs an ADR.

## Additional data overlays

- **311 service requests** — complaints, lighting outages, abandoned vehicles; the resident's
  side of the same street the crime data describes.
- **Building violations** — code enforcement as a signal of conditions on a block.
- **Vacant properties** — vacancy alongside incident clusters.
- **Street lighting** — outages and coverage. Suggested by the accountability work: lighting
  is often the concrete lever a resident actually has.
- **Weather** — daily temperature and precipitation as a seasonal control.
- **Sports schedules** — home games and large-draw events as context.

## Longitudinal context

- **Policy timelines** — a visual layer of dated federal, state, county, and city changes
  behind any trend chart.
- **Voter turnout** — participation alongside outcomes on the Community Change page.
- **ACS demographic overlays** — population, income, and housing change over time.

## Accountability

- **Public commitment tracking** — extending `public_commitment` into a full record of what
  officials promised, when, and whether it happened, with evidence.

## Distribution

- **Nextdoor share summaries** — short, accurate, citation-carrying summaries designed to
  survive being screenshotted and reposted. Would need care: this is the vector by which the
  project's framing most easily gets stripped, and a summary that loses its "association, not
  cause" framing does more harm than not existing.

## Caution

Every overlay above adds a variable that someone will read as an explanation. More context is
not automatically more truth — an overlay that invites a causal reading it cannot support is
a net loss. Each addition must arrive with its own guardrails, not just its data.
