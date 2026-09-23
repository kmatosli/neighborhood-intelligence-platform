/**
 * The Neighborhood Intelligence Brief — the Overview's published conclusions.
 *
 * This is deliberately not a dashboard. It states what the data establishes, what it does not,
 * and links each conclusion to the analysis behind it. Three rules shape every element here:
 *
 * 1. No figure appears without the context needed to judge it — place, period, what it is
 *    compared against, and its limitations.
 * 2. A domain with no data says so, with what is missing. It never shows a placeholder number.
 * 3. A finding and its evidence are the same numbers: the API computes both from one source, so
 *    the brief cannot drift from the page it links to.
 */

import { Link } from "@tanstack/react-router";
import { classificationLabel, findingHref, type Finding, type FindingsResponse } from "@/lib/api";

const TOPIC_LABELS: Record<string, string> = {
  public_safety: "Public Safety",
  people_and_housing: "People & Housing",
  city_services: "City Services",
  economic_conditions: "Economic Conditions",
  public_investment: "Public Investment & Development",
};

function topicLabel(topic: string): string {
  return TOPIC_LABELS[topic] ?? topic.replace(/_/g, " ");
}

/** Classification badge. Colour carries no judgement — it only distinguishes the kinds. */
function ClassificationBadge({ finding }: { finding: Finding }) {
  const tone =
    finding.classification === "verified_finding"
      ? "border-primary/50"
      : finding.classification === "change_alert"
        ? "border-amber-500/50"
        : finding.classification === "research_question"
          ? "border-sky-500/50"
          : "border-muted-foreground/40";
  return (
    <span className={`rounded border px-1.5 py-0.5 text-sm text-muted-foreground ${tone}`}>
      {classificationLabel(finding.classification)}
    </span>
  );
}

function FindingCard({ finding, lead = false }: { finding: Finding; lead?: boolean }) {
  const href = findingHref(finding);
  return (
    <article className="rounded-lg border bg-card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="wire-label">{topicLabel(finding.topic)}</span>
        <ClassificationBadge finding={finding} />
        {finding.provisional && (
          <span className="rounded border border-amber-500/50 px-1.5 py-0.5 text-sm text-muted-foreground">
            provisional
          </span>
        )}
        {finding.enforcement_sensitive && (
          <span className="rounded border border-sky-500/50 px-1.5 py-0.5 text-sm text-muted-foreground">
            enforcement-led
          </span>
        )}
      </div>

      <h3
        className={
          lead
            ? "mt-2 font-serif text-xl leading-snug sm:text-2xl"
            : "mt-2 font-serif text-lg leading-snug"
        }
      >
        {finding.headline}
      </h3>
      <p className="mt-2 text-base">{finding.observation}</p>

      {finding.evidence.length > 0 && (
        <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-base">
          {finding.evidence.map((item) => (
            <div key={`${finding.id}-${item.label}`} className="flex gap-2">
              <dt className="text-muted-foreground">{item.label}</dt>
              <dd className="font-medium tabular-nums">{item.value}</dd>
            </div>
          ))}
        </dl>
      )}

      {finding.missing.length > 0 && (
        <div className="mt-3 text-base">
          <p className="text-muted-foreground">What this needs:</p>
          <ul className="mt-1 list-disc pl-5">
            {finding.missing.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Scope and period travel with the claim, not in a footnote somewhere else. */}
      <p className="mt-3 text-sm text-muted-foreground">
        {finding.geography_label}
        {finding.geography_area_share_pct != null && (
          <>
            {" "}
            · {Math.round(finding.geography_area_share_pct)}% of the community area is in Ward 20
          </>
        )}
        {finding.reporting_period && <> · {finding.reporting_period}</>}
        {finding.data_through && <> · data through {finding.data_through}</>}
        {finding.source_dataset_id && <> · {finding.source_dataset_id}</>}
      </p>

      {finding.limitations.length > 0 && (
        <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
          {finding.limitations.map((item) => (
            <li key={item}>Limitation: {item}</li>
          ))}
        </ul>
      )}

      {href && (
        <p className="mt-3">
          <Link to={href} className="text-base underline underline-offset-4">
            See the analysis behind this
          </Link>
        </p>
      )}
    </article>
  );
}

export function IntelligenceBrief({ brief }: { brief: FindingsResponse }) {
  const hasAnyFinding =
    brief.lead.length > 0 ||
    brief.by_domain.length > 0 ||
    brief.neighborhood_differences.length > 0;

  return (
    <section aria-labelledby="brief" className="mb-10">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="brief" className="font-serif text-xl">
          What the data establishes
        </h2>
        <p className="text-sm text-muted-foreground">
          {brief.geography_label} · {brief.year} · data through {brief.data_through}
        </p>
      </div>

      {!hasAnyFinding && (
        <p className="mt-3 rounded-lg border bg-card p-4 text-base">
          No finding met the standard for publication for this geography and period. The evidence
          pages below still show the underlying figures.
        </p>
      )}

      {brief.lead.length > 0 && (
        <div className="mt-3 space-y-3">
          {brief.lead.map((finding) => (
            <FindingCard key={finding.id} finding={finding} lead />
          ))}
        </div>
      )}

      {brief.by_domain.length > 0 && (
        <div className="mt-6">
          <h3 className="wire-label">Also found</h3>
          <div className="mt-2 space-y-3">
            {brief.by_domain.map((finding) => (
              <FindingCard key={finding.id} finding={finding} />
            ))}
          </div>
        </div>
      )}

      {brief.neighborhood_differences.length > 0 && (
        <div className="mt-6">
          <h3 className="wire-label">Differences between the areas in Ward 20</h3>
          <div className="mt-2 space-y-3">
            {brief.neighborhood_differences.map((finding) => (
              <FindingCard key={finding.id} finding={finding} />
            ))}
          </div>
        </div>
      )}

      {brief.questions.length > 0 && (
        <div className="mt-6">
          <h3 className="wire-label">Questions the evidence raises</h3>
          <div className="mt-2 space-y-3">
            {brief.questions.map((finding) => (
              <FindingCard key={finding.id} finding={finding} />
            ))}
          </div>
        </div>
      )}

      {brief.data_gaps.length > 0 && (
        <div className="mt-6">
          <h3 className="wire-label">Domains with no data yet</h3>
          <p className="mt-1 text-base text-muted-foreground">
            These are listed so their absence is visible. Nothing is estimated for them.
          </p>
          <div className="mt-2 space-y-3">
            {brief.data_gaps.map((finding) => (
              <FindingCard key={finding.id} finding={finding} />
            ))}
          </div>
        </div>
      )}

      {/* A suppressed finding is a decision, so it is shown as one rather than left as a gap. */}
      {brief.withheld.length > 0 && (
        <details className="mt-6 rounded-lg border bg-card p-4">
          <summary className="cursor-pointer text-base">
            {brief.withheld.length} finding{brief.withheld.length === 1 ? "" : "s"} withheld for
            this selection
          </summary>
          <ul className="mt-2 space-y-1 text-base text-muted-foreground">
            {brief.withheld.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </details>
      )}

      <p className="mt-4 text-sm text-muted-foreground">
        Every figure above is computed from the {brief.data_release ?? "current"} data release and
        re-checked against it automatically. Conclusions are written and reviewed by hand, never
        generated at page load.
      </p>
    </section>
  );
}
