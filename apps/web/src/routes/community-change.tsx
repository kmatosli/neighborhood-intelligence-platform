import { createFileRoute } from "@tanstack/react-router";
import { WireShell } from "@/components/WireShell";
import { QuestionHeader } from "@/components/QuestionHeader";
import {
  ComingSoonNotice,
  PendingControl,
  PendingControls,
  PendingVisual,
} from "@/components/Pending";

export const Route = createFileRoute("/community-change")({
  head: () => ({
    meta: [
      { title: "Community Change — Ward 20 Neighborhood Intelligence" },
      {
        name: "description",
        content:
          "Population, income, housing, and voter turnout in Ward 20 and the neighborhoods within it, with tract-level overlays. Not yet connected to validated live data.",
      },
    ],
  }),
  component: CommunityChange,
});

function CommunityChange() {
  return (
    <WireShell>
      <section className="mb-6">
        <QuestionHeader question="How is Ward 20 changing?">
          {/* Census, ACS, and election ingestion are not built, so no claim is made about
              population, income, housing, or turnout. */}
          <ComingSoonNotice>
            This page is not yet connected to validated live data. Census, ACS, and election data
            have not been ingested, so no figure or trend about the neighborhood is shown.
          </ComingSoonNotice>

          <p className="mt-2 max-w-2xl text-xs text-muted-foreground">
            When it is connected, geographies will be kept distinct: Ward 20 crosses parts of nine
            community areas (about half of Woodlawn, most of Washington Park, and parts of
            Englewood, Fuller Park, New City, and others). Census tracts, wards, and community areas
            will be reported separately, never merged into one number.
          </p>
        </QuestionHeader>
      </section>

      {/* Metric controls — kept in place, disabled until they select against real data. */}
      <PendingControls label="Metric controls" columns="sm:grid-cols-3">
        <PendingControl
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
        <PendingControl
          label="Geography"
          id="geo"
          options={["Census tract", "Community area", "Ward"]}
        />
        <PendingControl
          label="Vintage"
          id="vintage"
          options={["ACS 2019–2023 5-year", "ACS 2018–2022 5-year", "Decennial 2020"]}
        />
      </PendingControls>

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
            planned="A choropleth of the selected metric by census tract inside Ward 20, with legend, source, and vintage."
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
                <td className="px-3 py-2">Ward</td>
                <td className="px-3 py-2 text-muted-foreground">
                  This site&rsquo;s analytical universe; voting; alderperson accountability
                </td>
                <td className="px-3 py-2">Ward 20 (2023 map)</td>
              </tr>
              <tr>
                <td className="px-3 py-2">Community area</td>
                <td className="px-3 py-2 text-muted-foreground">
                  Neighborhood analysis — shown only for the part inside Ward 20
                </td>
                <td className="px-3 py-2">Woodlawn (42), New City (61)</td>
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
          Back of the Yards is a neighborhood name, not an official community area; the City
          represents it through New City (61). It is listed as unavailable until a documented
          neighborhood boundary is validated.
        </p>
      </section>
    </WireShell>
  );
}
