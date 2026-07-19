import { createFileRoute } from "@tanstack/react-router";
import { WireShell } from "@/components/WireShell";

export const Route = createFileRoute("/community-change")({
  head: () => ({
    meta: [
      { title: "Community Change — Bronzeville & Woodlawn" },
      {
        name: "description",
        content:
          "Population, income, housing, and voter turnout in Bronzeville and Woodlawn with tract-level overlays. Not yet connected to validated live data.",
      },
    ],
  }),
  component: CommunityChange,
});

function CommunityChange() {
  return (
    <WireShell>
      <section className="mb-6">
        <p className="wire-label mb-2">Main question</p>
        <h1 className="font-serif text-2xl leading-snug sm:text-3xl">How is Woodlawn changing?</h1>

        {/* Census, ACS, and election ingestion are not built, so no claim is made about
            population, income, housing, or turnout. */}
        <p className="mt-3 rounded-md border bg-caution/20 p-3 text-base" role="note">
          <strong>Live data coming soon.</strong> This page is not yet connected to validated live
          data. Census, ACS, and election data have not been ingested, so no figure or trend about
          the neighborhood is shown.
        </p>

        <p className="mt-2 max-w-2xl text-xs text-muted-foreground">
          When it is connected, geographies will be kept distinct: Ward 20 covers most of Woodlawn
          but is not the same boundary. Census tracts, wards, and community areas will be reported
          separately, never merged into one number.
        </p>
      </section>

      {/* Metric controls — kept in place, disabled until they select against real data. */}
      <section
        aria-label="Metric controls"
        className="mb-6 grid gap-3 rounded-lg border bg-card p-4 sm:grid-cols-3"
      >
        <p id="controls-pending" className="wire-label sm:col-span-3">
          Controls are disabled until this page is connected to live data
        </p>
        <Control
          label="Metric"
          id="metric"
          options={[
            "Median household income",
            "Population",
            "Poverty rate",
            "Unemployment",
            "Educational attainment",
            "Housing occupancy",
            "Median rent",
            "Homeownership",
            "Vacancy",
            "Voter registration",
            "Voter turnout",
          ]}
        />
        <Control label="Geography" id="geo" options={["Census tract", "Community area", "Ward"]} />
        <Control
          label="Vintage"
          id="year"
          options={["ACS 2019–2023 5-year", "ACS 2018–2022 5-year", "Decennial 2020"]}
        />
      </section>

      {/* Trend + map */}
      <section className="grid gap-6 lg:grid-cols-2">
        <div>
          <h2 className="font-serif text-xl">Selected metric over time</h2>
          <PendingVisual
            height={220}
            planned="One metric over time for the selected geography, with dollar figures inflation-adjusted to the most recent vintage."
          />
          <p className="mt-2 text-xs text-muted-foreground">
            Planned source: U.S. Census Bureau, American Community Survey 5-year estimates. The
            source and vintage will be shown alongside every figure.
          </p>
        </div>
        <div>
          <h2 className="font-serif text-xl">Tract-level overlay</h2>
          <PendingVisual
            height={220}
            planned="A choropleth of the selected metric by census tract inside Woodlawn, with legend, source, and vintage."
          />
          <p className="mt-2 text-xs text-muted-foreground">
            Tract boundaries do not follow beats or wards, and will not be presented as if they do.
          </p>
        </div>
      </section>

      {/* Geography reference — factual, not derived from any dataset, so it stands on its own
          and stays live. */}
      <section aria-labelledby="geos" className="mt-8">
        <h2 id="geos" className="font-serif text-xl">
          These geographies are different
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Reference information. This does not depend on data that is still being ingested.
        </p>
        <div className="mt-3 overflow-x-auto rounded-lg border bg-card">
          <table className="w-full min-w-[40rem] text-left text-sm">
            <thead className="bg-muted/60 text-xs uppercase tracking-wide">
              <tr>
                <th scope="col" className="px-3 py-2">
                  Boundary
                </th>
                <th scope="col" className="px-3 py-2">
                  Used for
                </th>
                <th scope="col" className="px-3 py-2">
                  Example
                </th>
              </tr>
            </thead>
            <tbody className="divide-y">
              <tr>
                <td className="px-3 py-2">Community area</td>
                <td className="px-3 py-2 text-muted-foreground">Neighborhood analysis</td>
                <td className="px-3 py-2">Woodlawn (42)</td>
              </tr>
              <tr>
                <td className="px-3 py-2">Ward</td>
                <td className="px-3 py-2 text-muted-foreground">Voting, alderman accountability</td>
                <td className="px-3 py-2">Ward 3, Ward 20</td>
              </tr>
              <tr>
                <td className="px-3 py-2">Police beat / district</td>
                <td className="px-3 py-2 text-muted-foreground">CPD operations</td>
                <td className="px-3 py-2">District 003, Beat 0313</td>
              </tr>
              <tr>
                <td className="px-3 py-2">Census tract / block group</td>
                <td className="px-3 py-2 text-muted-foreground">Demographic overlays</td>
                <td className="px-3 py-2">Tract 4204</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          Bronzeville is not one official community area, and is not shown here as one.
        </p>
      </section>
    </WireShell>
  );
}

/**
 * A visualization with no validated data behind it yet.
 *
 * It renders no marks, no axis, and no numbers, and says plainly that it is not connected. An
 * empty chart frame would read as "zero"; a populated one would be a fabrication. Naming what
 * is planned keeps the page useful to a reader without asserting anything.
 */
function PendingVisual({ height, planned }: { height: number; planned: string }) {
  return (
    <div
      className="mt-3 flex items-center justify-center rounded-md border border-dashed bg-muted/30 p-4 text-center"
      style={{ minHeight: height }}
      role="note"
    >
      <div className="max-w-md">
        <p className="wire-label">Live data coming soon</p>
        <p className="mt-1 text-base">
          This visualization is not yet connected to validated live data.
        </p>
        <p className="mt-2 text-sm text-muted-foreground">Planned: {planned}</p>
      </div>
    </div>
  );
}

function Control({ label, id, options }: { label: string; id: string; options: string[] }) {
  return (
    <div>
      <label htmlFor={id} className="wire-label mb-1 block text-muted-foreground">
        {label}
      </label>
      {/* Disabled, not removed: the reader can see what this page will let them ask, without a
          control that silently does nothing when used. */}
      <select
        id={id}
        disabled
        aria-describedby="controls-pending"
        className="w-full cursor-not-allowed rounded-md border bg-muted px-2 py-1.5 text-sm text-muted-foreground opacity-70"
      >
        {options.map((o) => (
          <option key={o}>{o}</option>
        ))}
      </select>
    </div>
  );
}
