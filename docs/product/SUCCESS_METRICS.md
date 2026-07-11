# Success Metrics

What "working" means, stated so it can be checked. None of these are measurable yet — the
public application is not built. They are acceptance criteria for it.

## Comprehension

| Metric | Target | How it is checked |
| --- | --- | --- |
| A resident can identify the trend direction for their neighborhood | **under 1 minute** from landing | Timed task with residents who have not seen the site |
| A resident can name the office responsible for a given problem | **under 2 minutes** | Same, using the work-van break-in scenario |
| Methodology reading level | **4th–6th grade** | Automated readability score on every methodology and page-copy string, checked in CI |
| A resident can state one thing the data *cannot* tell them after reading the Overview | **majority of testers** | Comprehension interview |

## Utility

| Metric | Target |
| --- | --- |
| The Beat Meeting Brief prints to **one page** on standard paper, with source and refresh date visible | Always |
| A shared summary retains its citation and refresh date when screenshotted | Always |
| A user can filter to one crime category and a small area within **3 interactions** | Always |

## Transparency

| Metric | Target |
| --- | --- |
| Published statistics showing source dataset **and** refresh date | **100%** |
| Geography-dependent figures disclosing the count of records excluded for missing coordinates | **100%** |
| Published Bronzeville figures naming the boundary version that produced them | **100%** |
| Causal language in published copy | **Zero** — association only |

## Reliability

| Metric | Target |
| --- | --- |
| A failed scheduled refresh **erases or corrupts valid data** | **Never** — last good data survives |
| A schema break is detected before ingestion, not after | **Always** — metadata validation precedes extraction |
| A refresh returning zero rows, or a latest date moving backward, is treated as failure | **Always** |
| Data Health page is live on the day the first public numbers are | **Yes** |
| Ruff, mypy, and pytest passing on `main` | **Always** |

## Explicit non-metrics

Traffic, engagement time, and return visits are **not** success metrics. A resident who gets
their answer in forty seconds and leaves is a success. Optimizing for attention would
corrupt every other target on this page.
