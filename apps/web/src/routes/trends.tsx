import { createFileRoute } from "@tanstack/react-router";
import { WireShell } from "@/components/WireShell";
import { QuestionHeader } from "@/components/QuestionHeader";
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
          "Is reported crime in Ward 20 getting better or worse? A single trend line and category changes. Not yet connected to validated live data.",
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
            This page is not yet connected to validated live data. The layout below shows what it
            will contain. No trend, figure, or comparison is shown until the data supports one.
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
