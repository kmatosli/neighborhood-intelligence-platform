import { createFileRoute } from "@tanstack/react-router";
import { WireShell, DisclosureNote, WirePanel } from "@/components/WireShell";

export const Route = createFileRoute("/community-change")({
  head: () => ({
    meta: [
      { title: "Community Change — Bronzeville & Woodlawn" },
      {
        name: "description",
        content:
          "Population, income, housing, and voter turnout in Bronzeville and Woodlawn with tract-level overlays.",
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
        <h1 className="font-serif text-2xl leading-snug sm:text-3xl">
          How is Woodlawn changing?
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Population has been roughly flat since 2015. Median household income
          has risen. Renter share remains high. Voter turnout in the 20th Ward
          rose in the 2024 general election compared to 2020.
        </p>
        <p className="mt-2 max-w-2xl text-xs text-muted-foreground">
          Note: Ward 20 covers most of Woodlawn but they are not the same
          boundary. Census tracts, wards, and community areas are shown
          separately.
        </p>
      </section>

      {/* Metric controls */}
      <section
        aria-label="Metric controls"
        className="mb-6 grid gap-3 rounded-lg border bg-card p-4 sm:grid-cols-3"
      >
        <div>
          <label htmlFor="metric" className="wire-label mb-1 block">Metric</label>
          <select id="metric" className="w-full rounded-md border bg-background px-2 py-1.5 text-sm">
            <option>Median household income</option>
            <option>Population</option>
            <option>Poverty rate</option>
            <option>Unemployment</option>
            <option>Educational attainment</option>
            <option>Housing occupancy</option>
            <option>Median rent</option>
            <option>Homeownership</option>
            <option>Vacancy</option>
            <option>Voter registration</option>
            <option>Voter turnout</option>
          </select>
        </div>
        <div>
          <label htmlFor="geo" className="wire-label mb-1 block">Geography</label>
          <select id="geo" className="w-full rounded-md border bg-background px-2 py-1.5 text-sm">
            <option>Census tract</option>
            <option>Community area</option>
            <option>Ward</option>
          </select>
        </div>
        <div>
          <label htmlFor="year" className="wire-label mb-1 block">Vintage</label>
          <select id="year" className="w-full rounded-md border bg-background px-2 py-1.5 text-sm">
            <option>ACS 2019–2023 5-year</option>
            <option>ACS 2018–2022 5-year</option>
            <option>Decennial 2020</option>
          </select>
        </div>
      </section>

      {/* Trend + map */}
      <section className="grid gap-6 lg:grid-cols-2">
        <div>
          <h2 className="font-serif text-xl">Median household income, Woodlawn</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Single metric over time. Values shown in 2023 dollars.
          </p>
          <div className="mt-3">
            <WirePanel label="Time-series placeholder" height={220}>
              Line chart — median income 2015–2023
            </WirePanel>
          </div>
          <DisclosureNote>
            Source: U.S. Census Bureau, American Community Survey 5-year
            estimates. All dollar figures are inflation-adjusted to the most
            recent vintage using CPI-U.
          </DisclosureNote>
        </div>
        <div>
          <h2 className="font-serif text-xl">Tract-level overlay</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Choropleth of the selected metric by census tract inside Woodlawn.
            Tract boundaries do not follow beats or wards.
          </p>
          <div className="mt-3">
            <WirePanel label="Choropleth placeholder" height={220}>
              Map — census tracts shaded by median income
            </WirePanel>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Legend, source, and vintage will appear here.
          </p>
        </div>
      </section>

      {/* Geography reminder */}
      <section aria-labelledby="geos" className="mt-8">
        <h2 id="geos" className="font-serif text-xl">These geographies are different</h2>
        <div className="mt-3 overflow-hidden rounded-lg border bg-card">
          <table className="w-full text-left text-sm">
            <thead className="bg-muted/60 text-xs uppercase tracking-wide">
              <tr>
                <th className="px-3 py-2">Boundary</th>
                <th className="px-3 py-2">Used for</th>
                <th className="px-3 py-2">Example</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              <tr><td className="px-3 py-2">Community area</td><td className="px-3 py-2 text-muted-foreground">Neighborhood analysis</td><td className="px-3 py-2">Woodlawn (42), Douglas / Grand Boulevard (35, 38)</td></tr>
              <tr><td className="px-3 py-2">Ward</td><td className="px-3 py-2 text-muted-foreground">Voting, alderman accountability</td><td className="px-3 py-2">Ward 3, Ward 20</td></tr>
              <tr><td className="px-3 py-2">Police beat / district</td><td className="px-3 py-2 text-muted-foreground">CPD operations</td><td className="px-3 py-2">District 003, Beat 0313</td></tr>
              <tr><td className="px-3 py-2">Census tract / block group</td><td className="px-3 py-2 text-muted-foreground">Demographic overlays</td><td className="px-3 py-2">Tract 4204</td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </WireShell>
  );
}
