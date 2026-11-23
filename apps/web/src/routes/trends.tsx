import { createFileRoute } from "@tanstack/react-router";
import { WireShell } from "@/components/WireShell";
import { QuestionHeader } from "@/components/QuestionHeader";
import { PotholeServicePanel } from "@/components/PotholeServicePanel";
import { useYear } from "@/lib/useYear";
import { useGeography } from "@/lib/useGeography";
import {
  ComingSoonNotice,
  PendingControl,
  PendingControls,
  PendingVisual,
} from "@/components/Pending";

export const Route = createFileRoute("/trends")({
  head: () => ({
    meta: [
      { title: "Trends — Ward 20 Neighborhood Intelligence" },
      {
        name: "description",
        content:
          "Is reported crime in Ward 20 getting better or worse? The crime trend views are not yet connected to validated live data. Pothole service requests from Chicago 311 are live.",
      },
    ],
  }),
  component: Trends,
});

function Trends() {
  return (
    <WireShell>
      <section className="mb-6">
        <QuestionHeader question="Is it getting better or worse?">
          <ComingSoonNotice>
            The crime trend views on this page are not yet connected to validated live data. Their
            layouts show what they will contain. No trend, figure, or comparison is shown until the
            data supports one. The City Services section further down is live.
          </ComingSoonNotice>

          {/* No direction is stated. Answering this question needs several enriched years, and
              "rising" or "falling" would be invented until the trend method is built and
              validated against them. */}
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
            Answering this question requires several years of geography-enriched data and a
            validated trend method. Until then, this page says nothing about direction — an
            unsupported claim about whether a neighborhood is getting safer is not a harmless
            placeholder.
          </p>
        </QuestionHeader>
      </section>

      {/* Controls — kept in place, disabled until they filter real data. */}
      <PendingControls label="Trend controls" columns="sm:grid-cols-5">
        {/* Geography will come from the shared selector (Ward 20 overall or an area within
            it), the same context the Overview uses — not a page-local list. */}
        <PendingControl label="Geography" options={["Ward 20 overall", "Area within Ward 20"]} />
        <PendingControl
          label="Crime group"
          options={["All", "Violent", "Property", "Quality of life"]}
        />
        <PendingControl
          label="Period"
          options={["Last 12 months", "Last 5 years", "Last 10 years"]}
        />
        <PendingControl label="Show" options={["Counts", "Rate per 1,000"]} />
        <PendingControl label="Compare with" options={["Prior year", "5-year baseline"]} />
      </PendingControls>

      {/* Primary view */}
      <section aria-labelledby="line" className="mb-8">
        <h2 id="line" className="font-serif text-xl">
          Reported incidents, monthly
        </h2>
        <PendingVisual
          height={260}
          planned="One line of monthly reported incidents, with a shaded band showing the five-year range for the same month."
        />
      </section>

      {/* City Services — the first connected section on this page. Crime trends above are
          still placeholders; this one is live, so it is labelled as such rather than sitting
          among them unmarked. */}
      <CityServicesSection />

      {/* Category change */}
      <section aria-labelledby="cats">
        <h2 id="cats" className="font-serif text-xl">
          Category change vs prior year
        </h2>
        <PendingVisual
          height={220}
          planned="Absolute change in reports per category, as horizontal bars. The count will lead, because small categories look extreme in percentage terms."
        />
      </section>
    </WireShell>
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
