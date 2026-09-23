"""The Overview's published findings — reviewed wording, computed numbers.

Read-only. Two halves that must stay separate:

* `config/findings.yml` holds the editorial decision — which conclusions are worth publishing,
  in what words, with what limitations, and whether a reviewer has approved them.
* This module holds the arithmetic. Each `calculation` named in that file is a function here
  that returns values from the real Bronze + Silver data. No number is typed into the config,
  and no sentence is generated at request time, so a published figure can always be recomputed
  and checked against what the site said.

A finding is served only when its `status` is `published` AND its calculation succeeds AND any
suppression rule passes. Anything withheld is reported in `withheld` rather than disappearing,
because a reader who is shown four findings should be able to tell that a fifth was suppressed
and why.

Only Public Safety has ingested data. Every other domain is a `data_gap` entry that states what
is missing and shows no figure — never an estimate, never a placeholder.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from bw_observatory.config import Settings
from bw_observatory.presentation.geography import (
    COMMUNITY_AREA_COLUMN,
    ProductGeography,
    load_geography_registry,
)
from bw_observatory.presentation.measurement import measurement_notes
from bw_observatory.presentation.models import Finding, FindingEvidence, FindingsResponse
from bw_observatory.presentation.overview import (
    CRIME_DATASET_ID,
    is_enforcement_generated,
    load_geography_rows,
    resolve_geography,
)
from bw_observatory.presentation.pulse import build_pulse

#: Classifications a finding may carry. Anything else in config is a configuration error.
CLASSIFICATIONS = frozenset({"verified_finding", "change_alert", "research_question", "data_gap"})

#: Topics, in the order the brief presents them. Public safety is first because it is the only
#: one with data; the rest appear as gaps so their absence is visible rather than implied.
TOPIC_ORDER = (
    "public_safety",
    "people_and_housing",
    "city_services",
    "economic_conditions",
    "public_investment",
)

TOPIC_LABELS = {
    "public_safety": "Public Safety",
    "people_and_housing": "People & Housing",
    "city_services": "City Services",
    "economic_conditions": "Economic Conditions",
    "public_investment": "Public Investment & Development",
}

#: Findings that lead the brief, in order. Kept short on purpose: a brief that leads with
#: everything leads with nothing.
LEAD_IDS = ("F-001", "F-002")


class FindingsConfigError(RuntimeError):
    """The findings file is malformed. Raised loudly rather than serving a partial brief."""


@dataclass(frozen=True)
class CalcContext:
    """Everything a calculation may read. Passing the data root explicitly matters: a
    calculation that reached for `Settings()` would read the live release even when a caller
    (a test, a reproduction of an archived brief) asked for a different one."""

    data_dir: Path
    year: int
    pulse: Any
    geography: ProductGeography


@dataclass(frozen=True)
class Computed:
    """What a calculation returns: slot values, evidence rows, and any suppression reason."""

    values: dict[str, Any]
    evidence: list[FindingEvidence] = field(default_factory=list)
    #: "up" | "down" | "flat" | "any" — selects the reviewed headline wording.
    direction: str = "any"
    #: Set when the finding must not publish; the text explains why.
    withhold: str | None = None
    enforcement_sensitive: bool = False


@dataclass(frozen=True)
class FindingSpec:
    """One entry from config/findings.yml, validated."""

    id: str
    topic: str
    classification: str
    headline: dict[str, str]
    observation: str
    subtopic: str | None = None
    calculation: str | None = None
    limitations: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    destination_route: str | None = None
    destination_anchor: str | None = None
    only_geography: str | None = None
    min_prior: int | None = None
    status: str = "draft"
    reviewed_by: str | None = None
    reviewed_at: str | None = None


def _text(value: Any) -> str:
    """Collapse a YAML folded block into one line of prose."""
    return " ".join(str(value).split())


@lru_cache(maxsize=1)
def load_finding_specs(path: Path | None = None) -> tuple[FindingSpec, ...]:
    """Every finding defined in config, validated. Same file in, same findings out."""
    resolved = path or Settings().findings_config
    if not resolved.exists():
        raise FindingsConfigError(f"Findings config not found: {resolved}")

    payload = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    entries = payload.get("findings", [])
    if not isinstance(entries, list):
        raise FindingsConfigError("`findings` must be a list.")

    specs: list[FindingSpec] = []
    seen: set[str] = set()
    for entry in entries:
        identifier = str(entry.get("id", "")).strip()
        if not identifier:
            raise FindingsConfigError("Every finding needs an `id`.")
        if identifier in seen:
            raise FindingsConfigError(f"Duplicate finding id: {identifier}")
        seen.add(identifier)

        classification = str(entry.get("classification", "")).strip()
        if classification not in CLASSIFICATIONS:
            raise FindingsConfigError(
                f"{identifier}: classification `{classification}` is not one of "
                f"{sorted(CLASSIFICATIONS)}."
            )
        headline = entry.get("headline")
        if not isinstance(headline, dict) or not headline:
            raise FindingsConfigError(f"{identifier}: `headline` must be a mapping of wordings.")
        # A finding that states a figure must name the calculation that produced it.
        if classification in {"verified_finding", "change_alert"} and not entry.get("calculation"):
            raise FindingsConfigError(
                f"{identifier}: a {classification} needs a `calculation`, so its number can be "
                "recomputed."
            )

        destination = entry.get("destination") or {}
        specs.append(
            FindingSpec(
                id=identifier,
                topic=str(entry.get("topic", "")).strip(),
                classification=classification,
                headline={str(k): _text(v) for k, v in headline.items()},
                observation=_text(entry.get("observation", "")),
                subtopic=(
                    None if entry.get("subtopic") is None else str(entry["subtopic"]).strip()
                ),
                calculation=(
                    None if entry.get("calculation") is None else str(entry["calculation"]).strip()
                ),
                limitations=tuple(_text(x) for x in entry.get("limitations", [])),
                missing=tuple(_text(x) for x in entry.get("missing", [])),
                destination_route=(
                    None if destination.get("route") is None else str(destination["route"])
                ),
                destination_anchor=(
                    None if destination.get("anchor") is None else str(destination["anchor"])
                ),
                only_geography=(
                    None
                    if entry.get("only_geography") is None
                    else str(entry["only_geography"]).strip()
                ),
                min_prior=(None if entry.get("min_prior") is None else int(entry["min_prior"])),
                status=str(entry.get("status", "draft")).strip(),
                reviewed_by=(
                    None if entry.get("reviewed_by") is None else str(entry["reviewed_by"])
                ),
                reviewed_at=(
                    None if entry.get("reviewed_at") is None else str(entry["reviewed_at"])
                ),
            )
        )
    return tuple(specs)


# -- calculations ------------------------------------------------------------------------
#
# Each takes the already-built Pulse for the selected geography/year (so the brief and the page
# can never disagree about a number) and returns slot values plus evidence.


def _count(value: int) -> str:
    return f"{value:,}"


def _change_phrase(current: int, prior: int) -> tuple[str, str]:
    """A reviewed phrase for the movement, and its direction key."""
    delta = current - prior
    if prior <= 0:
        return "with no comparable figure for the earlier period", "flat"
    pct = abs(delta) / prior * 100
    if delta == 0:
        return "unchanged", "flat"
    word = "up" if delta > 0 else "down"
    return f"{word} {abs(delta):,} reports, {pct:.1f}%", word


def calc_overall_change(context: CalcContext) -> Computed:
    """Total reported incidents against the same period last year."""
    pulse = context.pulse
    current = pulse.incidents.current
    prior = pulse.incidents.prior
    if prior is None:
        return Computed(values={}, withhold="no comparable prior period is available")
    phrase, direction = _change_phrase(current, prior)
    return Computed(
        values={
            "total": _count(current),
            "prior_total": _count(prior),
            "change_phrase": phrase,
            "prior_raw": prior,
        },
        evidence=[
            FindingEvidence(
                label="Reported incidents", value=_count(current), period=pulse.current_period.end
            ),
            FindingEvidence(
                label="Same period last year",
                value=_count(prior),
                period=pulse.prior_period.end if pulse.prior_period else None,
            ),
        ],
        direction=direction,
    )


def calc_largest_contributor(context: CalcContext) -> Computed:
    """The crime type that moved the total most, by absolute change."""
    pulse = context.pulse
    scored = [d for d in pulse.category_drivers if d.absolute_change is not None]
    if not scored:
        return Computed(values={}, withhold="no prior period to attribute the change to")
    top = max(scored, key=lambda d: abs(d.absolute_change or 0))
    if not top.absolute_change:
        return Computed(values={}, withhold="no crime type moved measurably")

    prior = top.prior or 0
    phrase, direction = _change_phrase(top.current, prior)
    overall = pulse.incidents.current - (pulse.incidents.prior or pulse.incidents.current)
    return Computed(
        values={
            "category": top.primary_type.title(),
            "total": _count(top.current),
            "prior_total": _count(prior),
            "change_phrase": phrase,
            "overall_change": f"{overall:+,}",
            "prior_raw": prior,
        },
        evidence=[
            FindingEvidence(label=top.primary_type.title(), value=_count(top.current)),
            FindingEvidence(label="Same period last year", value=_count(prior)),
            FindingEvidence(label="Change", value=f"{top.absolute_change:+,}"),
        ],
        direction=direction,
        enforcement_sensitive=bool(getattr(top, "enforcement_generated", False))
        or is_enforcement_generated(top.primary_type),
    )


def calc_enforcement_share(context: CalcContext) -> Computed:
    """How much of the total sits in categories recorded only where police act."""
    pulse = context.pulse
    total = pulse.incidents.current
    if total <= 0:
        return Computed(values={}, withhold="no incidents in the period")
    flagged = sum(
        d.current for d in pulse.category_drivers if is_enforcement_generated(d.primary_type)
    )
    if flagged == 0:
        return Computed(values={}, withhold="no enforcement-generated categories in the period")
    return Computed(
        values={
            "enforcement_total": _count(flagged),
            "total": _count(total),
            "enforcement_pct": f"{flagged / total * 100:.0f}%",
        },
        evidence=[
            FindingEvidence(label="Enforcement-led reports", value=_count(flagged)),
            FindingEvidence(label="All reported incidents", value=_count(total)),
        ],
        enforcement_sensitive=True,
    )


def calc_portion_distribution(context: CalcContext) -> Computed:
    """How the ward's reported incidents spread across the community-area portions inside it.

    One pass over the year: the ward's records already carry their spatial community area, so
    grouping them is enough. Loading each portion separately would read the same year nine
    times and turn the brief into the slowest request on the site.
    """
    registry = load_geography_registry()
    names = {
        g.community_area: g.display_name
        for g in registry.geographies
        if g.is_available and g.community_area is not None
    }
    if len(names) < 2:
        return Computed(values={}, withhold="fewer than two areas are available to compare")

    rows = load_geography_rows(context.data_dir, context.year, context.geography)
    if rows.empty:
        return Computed(values={}, withhold="no records for the period")

    counts = rows[COMMUNITY_AREA_COLUMN].astype("string").value_counts()
    counted = [
        (names[str(area)], int(count))
        for area, count in counts.items()
        if str(area) in names and count > 0
    ]
    if len(counted) < 2:
        return Computed(values={}, withhold="not enough areas have records in this period")

    counted.sort(key=lambda row: row[1], reverse=True)
    total = sum(count for _, count in counted)
    top_name, top_count = counted[0]
    bottom_name, bottom_count = counted[-1]

    def share(count: int) -> str:
        return f"{count / total * 100:.0f}%" if total else "—"

    return Computed(
        values={
            "total": _count(total),
            "top_name": top_name,
            "top_share": f"{share(top_count)} ({_count(top_count)} reports)",
            "bottom_name": bottom_name,
            "bottom_share": f"{share(bottom_count)} ({_count(bottom_count)} reports)",
        },
        evidence=[
            FindingEvidence(label=name, value=f"{_count(count)} ({share(count)})")
            for name, count in counted
        ],
    )


CALCULATIONS: dict[str, Callable[[CalcContext], Computed]] = {
    "overall_change": calc_overall_change,
    "largest_contributor": calc_largest_contributor,
    "enforcement_share": calc_enforcement_share,
    "portion_distribution": calc_portion_distribution,
}


# -- assembly ----------------------------------------------------------------------------


def _render(template: str, values: dict[str, Any]) -> str:
    """Fill reviewed wording from computed values. A missing slot is a configuration error."""
    try:
        return template.format(**values)
    except KeyError as error:  # pragma: no cover - guarded by tests
        raise FindingsConfigError(
            f"wording needs a value the calculation did not return: {error}"
        ) from error


def _headline_for(spec: FindingSpec, direction: str) -> str:
    wording = spec.headline
    for key in (direction, "any"):
        if key in wording:
            return wording[key]
    raise FindingsConfigError(
        f"{spec.id}: no reviewed headline for direction `{direction}`; add it to config rather "
        "than letting the platform choose its own wording."
    )


def build_findings(data_dir: Path, year: int, geography_id: str | None = None) -> FindingsResponse:
    """The Overview brief for one geography and year.

    Numbers come from the same Pulse the Trends page uses, so the brief and its evidence can
    never disagree. Data gaps and research questions need no data and are always included.
    """
    geography = resolve_geography(geography_id or load_geography_registry().default_id)
    pulse = build_pulse(data_dir, year, geography.geography_id)

    provisional = bool(pulse.measurement and pulse.measurement.provisional_period)
    period = f"{year} to {pulse.data_through}" if pulse.is_year_to_date else str(year)
    comparison = pulse.prior_period.end if pulse.prior_period else None
    comparison_period = f"the same period in {year - 1}" if pulse.is_year_to_date else str(year - 1)
    shared_params = {"geo": geography.geography_id, "year": str(year)}

    lead: list[Finding] = []
    by_domain: list[Finding] = []
    differences: list[Finding] = []
    questions: list[Finding] = []
    gaps: list[Finding] = []
    withheld: list[str] = []

    for spec in load_finding_specs():
        if spec.status != "published":
            withheld.append(f"{spec.id}: not published (status {spec.status})")
            continue
        if spec.only_geography and spec.only_geography != geography.geography_id:
            continue

        computed = Computed(values={})
        if spec.calculation:
            calculation = CALCULATIONS.get(spec.calculation)
            if calculation is None:
                raise FindingsConfigError(f"{spec.id}: unknown calculation `{spec.calculation}`.")
            computed = calculation(
                CalcContext(data_dir=data_dir, year=year, pulse=pulse, geography=geography)
            )
            if computed.withhold:
                withheld.append(f"{spec.id}: {computed.withhold}")
                continue
            # A percentage on a tiny comparison period is not worth publishing.
            prior_raw = computed.values.get("prior_raw")
            if (
                spec.min_prior is not None
                and isinstance(prior_raw, int)
                and prior_raw < spec.min_prior
            ):
                withheld.append(
                    f"{spec.id}: the comparison period has only {prior_raw} reports, below the "
                    f"{spec.min_prior} needed for a stable percentage"
                )
                continue

        values = {
            **computed.values,
            "geography": geography.display_name,
            "period": period,
            "comparison_period": comparison_period,
        }
        finding = Finding(
            id=spec.id,
            topic=spec.topic,
            subtopic=spec.subtopic,
            classification=spec.classification,
            headline=_render(_headline_for(spec, computed.direction), values),
            observation=_render(spec.observation, values),
            evidence=computed.evidence,
            missing=list(spec.missing),
            limitations=list(spec.limitations),
            geography_id=geography.geography_id,
            geography_label=geography.display_name,
            geography_area_share_pct=geography.share_of_area_in_ward_pct,
            reporting_period=period,
            comparison_period=comparison if spec.calculation else None,
            source_dataset_id=CRIME_DATASET_ID if spec.calculation else None,
            data_through=pulse.data_through if spec.calculation else None,
            provisional=provisional if spec.calculation else False,
            enforcement_sensitive=computed.enforcement_sensitive,
            calculation=spec.calculation,
            destination_route=spec.destination_route,
            destination_anchor=spec.destination_anchor,
            destination_params=shared_params if spec.destination_route else {},
            reviewed_by=spec.reviewed_by,
            reviewed_at=spec.reviewed_at,
        )

        if spec.classification == "data_gap":
            gaps.append(finding)
        elif spec.classification == "research_question":
            questions.append(finding)
        elif spec.subtopic == "neighborhood_differences":
            differences.append(finding)
        elif spec.id in LEAD_IDS:
            lead.append(finding)
        else:
            by_domain.append(finding)

    lead.sort(key=lambda f: LEAD_IDS.index(f.id) if f.id in LEAD_IDS else len(LEAD_IDS))
    gaps.sort(key=lambda f: TOPIC_ORDER.index(f.topic) if f.topic in TOPIC_ORDER else 99)

    return FindingsResponse(
        geography_id=geography.geography_id,
        geography_label=geography.display_name,
        year=year,
        data_release=_release_name(data_dir),
        data_through=pulse.data_through,
        freshness_status=_freshness_status(data_dir, year, geography, pulse.data_through),
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        lead=lead,
        by_domain=by_domain,
        neighborhood_differences=differences,
        questions=questions,
        data_gaps=gaps,
        withheld=withheld,
    )


def _release_name(data_dir: Path) -> str | None:
    """The release directory the figures came from, so an archived brief is reproducible."""
    try:
        return data_dir.resolve().name
    except OSError:  # pragma: no cover - defensive
        return None


def _freshness_status(
    data_dir: Path, year: int, geography: ProductGeography, through: str
) -> str | None:
    """`provisional` when records are still arriving for the period, else `settled`."""
    try:
        notes = measurement_notes(data_dir, year, geography, through_iso=through)
    except Exception:  # noqa: BLE001 - a missing flag must not withhold the brief
        return None
    return "provisional" if notes.provisional_period else "settled"
