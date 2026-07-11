# Documentation Index

Civic-data observatory for Bronzeville and Woodlawn, Chicago. The project is in the
**data-foundation phase**: a verified Chicago crime API client and validation layer exist;
storage, geography, analytics, and the web application do not.

Start with [PROJECT_STATUS.md](PROJECT_STATUS.md) for what is built, and [../TODO.md](../TODO.md)
for what is next.

## Architecture

| Document | Purpose |
| --- | --- |
| [ARCHITECTURE.md](architecture/ARCHITECTURE.md) | System shape, current vs. planned |
| [DATA_FLOW.md](architecture/DATA_FLOW.md) | Step-by-step path from API to publication |
| [DATA_MODEL.md](architecture/DATA_MODEL.md) | Planned entities, keys, and build status |
| [VALIDATION.md](architecture/VALIDATION.md) | The four validation levels |
| [GIS_STRATEGY.md](architecture/GIS_STRATEGY.md) | Neighborhood boundaries and spatial assignment |
| [SECURITY.md](architecture/SECURITY.md) | Secrets, data handling, and analytical limits |

## Architecture decisions

| ADR | Status |
| --- | --- |
| [ADR-0001 — Repository and Python layout](architecture/ADR/ADR-0001-repository-and-python-layout.md) | Accepted |
| [ADR-0002 — Bronze/Silver/Gold data layers](architecture/ADR/ADR-0002-bronze-silver-gold-data-layers.md) | Accepted |
| [ADR-0003 — Validation levels](architecture/ADR/ADR-0003-validation-levels.md) | Accepted |
| [ADR-0004 — Neighborhood boundary strategy](architecture/ADR/ADR-0004-neighborhood-boundary-strategy.md) | Proposed |

## Product

- [PRD.md](product/PRD.md) — what is being built and for whom
- [ROADMAP.md](product/ROADMAP.md) — phases and sequencing
- [USER_PERSONAS.md](product/USER_PERSONAS.md) — the people this serves
- [SUCCESS_METRICS.md](product/SUCCESS_METRICS.md) — how we know it works
- [BACKLOG.md](product/BACKLOG.md) — prioritized epics

## Methodology

- [DATA_GOVERNANCE.md](methodology/DATA_GOVERNANCE.md) — the rules every number must satisfy
- [CRIME.md](methodology/CRIME.md) — how crime data is used and what it does not mean
- [DATA_QUALITY.md](methodology/DATA_QUALITY.md) — the health signals we track
- [ACCOUNTABILITY_FRAMEWORK.md](methodology/ACCOUNTABILITY_FRAMEWORK.md) — who is responsible for what
- [EVENTS_AND_POLICY_CONTEXT.md](methodology/EVENTS_AND_POLICY_CONTEXT.md) — context without causation

## Decisions and limitations

- [ISSUE_LOG.md](decisions/ISSUE_LOG.md) — known open issues
- [KNOWN_LIMITATIONS.md](decisions/KNOWN_LIMITATIONS.md) — what this project cannot currently tell you
- [FUTURE_IDEAS.md](decisions/FUTURE_IDEAS.md) — unapproved ideas, parked

## Sources

- [DATA_SOURCES.md](DATA_SOURCES.md) — official datasets and endpoints
