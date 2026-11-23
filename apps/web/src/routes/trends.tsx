import { createFileRoute } from "@tanstack/react-router";
import { WireShell } from "@/components/WireShell";
import { QuestionHeader } from "@/components/QuestionHeader";
import { PotholeServicePanel } from "@/components/PotholeServicePanel";
import { ChangeSection } from "@/components/ChangeSection";
import { useYear } from "@/lib/useYear";
import { useGeography } from "@/lib/useGeography";

export const Route = createFileRoute("/trends")({
  head: () => ({
    meta: [
      { title: "Trends — Ward 20 Neighborhood Intelligence" },
      {
        name: "description",
        content:
          "How reported crime in Ward 20 has changed: every crime type, reconciled to the total, with long-run context. Geography, Circumstances and Investigations are not yet built. Pothole service requests from Chicago 311 are live.",
      },
    ],
  }),
  component: Trends,
});

/**
 * Crime Trends in the five approved sections. Only Change is built; the others say so in one
 * sentence and show no controls and no placeholder charts, because a disabled widget implies an
 * analysis that does not exist. Geography and year come from the shared shell (`?geo=`,
 * `?year=`), never from a page-local control.
 */
function Trends() {
  const { year, isLoading: yearLoading } = useYear();
  const { geographyId, isLoading: geoLoading } = useGeography();
  const ready = !yearLoading && !geoLoading && year !== null && geographyId !== null;

  return (
    <WireShell>
      <section className="mb-8">
        <QuestionHeader
          question="Is it getting better or worse?"
          lede="Reported crime only. These pages describe what the records show; they do not say why a number moved, and a count is not a safety ranking."
        />
      </section>

      {ready ? (
        <ChangeSection geographyId={geographyId} year={year} />
      ) : (
        <p className="mb-12 text-base text-muted-foreground">Loading…</p>
      )}

      <NotYetBuilt
        id="geography"
        number={2}
        title="Geography"
        sentence="Where incidents concentrate within the selected area and whether that concentration persists is not yet built."
      />
      <NotYetBuilt
        id="circumstances"
        number={3}
        title="Circumstances"
        sentence="When and in what settings incidents are reported — time of day, day of week, location type — is not yet built."
      />
      <NotYetBuilt
        id="investigations"
        number={4}
        title="Investigations"
        sentence="Focused studies of particular crime types are not yet built."
      />

      <MethodsSection />

      {/* City Services — a separate, live dataset. Unchanged by the crime sections above. */}
      <CityServicesSection />
    </WireShell>
  );
}

function NotYetBuilt({
  id,
  number,
  title,
  sentence,
}: {
  id: string;
  number: number;
  title: string;
  sentence: string;
}) {
  return (
    <section aria-labelledby={id} className="mb-8">
      <p className="wire-label mb-1">Section {number}</p>
      <h2 id={id} className="font-serif text-2xl">
        {title}
      </h2>
      <p className="mt-1 max-w-2xl text-base text-muted-foreground">{sentence}</p>
    </section>
  );
}

/** Methods for what is built today. Static text: no figure here, so none can drift. */
function MethodsSection() {
  return (
    <section aria-labelledby="methods" className="mb-12">
      <p className="wire-label mb-1">Section 5</p>
      <h2 id="methods" className="font-serif text-2xl">
        Definitions &amp; Methods
      </h2>
      <dl className="mt-3 max-w-3xl space-y-3 text-base">
        <div>
          <dt className="font-medium">What is counted</dt>
          <dd className="text-muted-foreground">
            Incidents reported to the Chicago Police Department and published in the City&apos;s
            Crimes dataset — not convictions, and not every crime. Records the City has since
            withdrawn are kept for the record but excluded from every figure.
          </dd>
        </div>
        <div>
          <dt className="font-medium">Where an incident is placed</dt>
          <dd className="text-muted-foreground">
            By the incident&apos;s mapped location against the current (2023) Ward 20 boundary and
            the community-area boundaries — never by the ward or area the record reports. Every year
            is placed with the same map. An area figure is only the part of that community area
            inside Ward 20.
          </dd>
        </div>
        <div>
          <dt className="font-medium">Comparisons</dt>
          <dd className="text-muted-foreground">
            Both periods cover the same calendar span, with inclusive start and end dates, and both
            lie wholly inside the published data; a part-year is never compared with a full year. A
            percentage is withheld when its comparison count is too small to be stable, and the
            counts are always shown.
          </dd>
        </div>
        <div>
          <dt className="font-medium">Groups and overlays</dt>
          <dd className="text-muted-foreground">
            The broad groups divide every report into exactly one group. Overlays —
            enforcement-generated offences, narcotics, motor vehicle theft, and selected FBI/NIBRS
            violent-offense classes — are separate lenses that overlap each other and the groups, so
            they are never added up or drawn as parts of a whole. The violent overlay follows the
            source&apos;s own FBI/NIBRS code and is a plain subset, not a severity or safety
            measure.
          </dd>
        </div>
        <div>
          <dt className="font-medium">Recent and revised data</dt>
          <dd className="text-muted-foreground">
            The City withholds roughly the latest week and keeps revising records. A period ending
            within 60 days of the newest record is marked provisional. The source has no separate
            report date, so revisions are measured by comparing retained data releases incident by
            incident.
          </dd>
        </div>
        <div>
          <dt className="font-medium">Direction over time</dt>
          <dd className="text-muted-foreground">
            Kendall&apos;s tau-b on complete calendar years. It describes whether totals tended to
            rise or fall; it is not a forecast and does not explain a change.
          </dd>
        </div>
        <div>
          <dt className="font-medium">Near-repeat patterns</dt>
          <dd className="text-muted-foreground">
            Published locations are masked to the block, so the true distance between incidents
            cannot be measured. Near-repeat analysis is therefore kept as a research note, not a
            public view.
          </dd>
        </div>
      </dl>
    </section>
  );
}

/**
 * City Services → Potholes. Reads the shared geography and year from the URL, the same context
 * the Overview uses, so moving between pages keeps the selection.
 */
function CityServicesSection() {
  const { year, isLoading: yearLoading } = useYear();
  const { geographyId, isLoading: geoLoading } = useGeography();

  return (
    <section aria-labelledby="city-services" className="mb-10">
      <h2 id="city-services" className="font-serif text-xl">
        City Services — potholes
      </h2>
      <p className="mt-1 text-base text-muted-foreground">
        Reported pothole service requests from the City of Chicago 311 system. These are reports
        residents and staff submitted, not a count of how many potholes exist, and not a measure of
        how well the City performs.
      </p>
      {yearLoading || geoLoading || year === null || geographyId === null ? (
        <p className="mt-3 text-base text-muted-foreground">Loading…</p>
      ) : (
        <PotholeServicePanel geographyId={geographyId} year={year} />
      )}
    </section>
  );
}
