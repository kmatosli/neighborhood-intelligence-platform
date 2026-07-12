import { createFileRoute } from "@tanstack/react-router";
import { WireShell, DisclosureNote } from "@/components/WireShell";

export const Route = createFileRoute("/beat-meeting")({
  head: () => ({
    meta: [
      { title: "Beat Meeting Brief — Bronzeville & Woodlawn" },
      {
        name: "description",
        content:
          "One-page brief for the next CAPS beat meeting: recurring patterns, questions to ask, and who has authority to act.",
      },
    ],
  }),
  component: BeatMeeting,
});

function BeatMeeting() {
  return (
    <WireShell>
      <section className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="wire-label mb-2">Main question</p>
          <h1 className="font-serif text-2xl leading-snug sm:text-3xl">
            What should residents ask at the next beat meeting?
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
            A one-page brief you can print or bring on your phone. All patterns
            below are from reported incidents in the last 90 days.
          </p>
        </div>
        <div className="flex gap-2">
          <button className="rounded-md border bg-card px-3 py-1.5 text-sm hover:bg-accent">
            Print
          </button>
          <button className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground">
            Download PDF
          </button>
        </div>
      </section>

      {/* Beat selector */}
      <section className="mb-6 grid gap-3 rounded-lg border bg-card p-4 sm:grid-cols-3">
        <div>
          <label htmlFor="beat" className="wire-label mb-1 block">Beat</label>
          <select id="beat" className="w-full rounded-md border bg-background px-2 py-1.5 text-sm" defaultValue="0313">
            <option>0311</option>
            <option>0312</option>
            <option>0313 — East Woodlawn</option>
            <option>0314</option>
          </select>
        </div>
        <div>
          <label htmlFor="window" className="wire-label mb-1 block">Window</label>
          <select id="window" className="w-full rounded-md border bg-background px-2 py-1.5 text-sm">
            <option>Last 30 days</option>
            <option>Last 90 days</option>
            <option>Last 365 days</option>
          </select>
        </div>
        <div>
          <label htmlFor="cmp" className="wire-label mb-1 block">Compare with</label>
          <select id="cmp" className="w-full rounded-md border bg-background px-2 py-1.5 text-sm">
            <option>Same 90 days, prior year</option>
            <option>Prior 90 days</option>
          </select>
        </div>
      </section>

      {/* Snapshot */}
      <section aria-label="Snapshot" className="mb-8 grid gap-4 sm:grid-cols-4">
        <Stat label="Reports (90d)" value="184" delta="−12 vs prior year" tone="down" />
        <Stat label="Violent" value="27" delta="−6" tone="down" />
        <Stat label="Property" value="98" delta="+18" tone="up" />
        <Stat label="Quality of life" value="59" delta="−1" tone="steady" />
      </section>

      {/* Recurring patterns */}
      <section aria-labelledby="patterns" className="mb-8">
        <h2 id="patterns" className="font-serif text-xl">
          Recurring patterns
        </h2>
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          <Pattern
            title="Theft from vehicles, weekday overnights"
            body="Reports cluster Tuesday–Thursday between 10 PM and 4 AM, most often along commercial cross streets. 34 reports in the last 90 days, up from 22."
          />
          <Pattern
            title="Retail theft, Friday afternoons"
            body="Reports concentrate near the 63rd Street commercial strip between 2 PM and 6 PM. 19 reports, similar to prior period."
          />
          <Pattern
            title="Graffiti and criminal damage, alleys"
            body="Recurring in mid-block alleys south of 65th. 28 reports in 90 days, roughly flat."
          />
          <Pattern
            title="Robbery near transit stops, evenings"
            body="Small number of reports (7 in 90 days) near Green Line stops between 6 PM and 10 PM. Below last year."
          />
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          Locations are shown as general areas, not addresses.
        </p>
      </section>

      {/* Questions */}
      <section aria-labelledby="qs" className="mb-8">
        <h2 id="qs" className="font-serif text-xl">Five questions to ask</h2>
        <ol className="mt-3 space-y-2 rounded-lg border bg-card p-4 text-sm">
          <li>1. What is the district's plan for the overnight vehicle-break-in pattern on the commercial cross streets?</li>
          <li>2. Which streetlights along that corridor have been out for more than 30 days, and who is coordinating repair with CDOT?</li>
          <li>3. How many of last quarter's vehicle-break-in reports resulted in an arrest, and how many were charged?</li>
          <li>4. What has the ward office committed to fund for lighting or camera improvements this year?</li>
          <li>5. When is the next problem-solving session for this beat, and how do residents contribute?</li>
        </ol>
      </section>

      {/* Who is responsible */}
      <section aria-labelledby="resp">
        <h2 id="resp" className="font-serif text-xl">Who has authority to act</h2>
        <div className="mt-3 overflow-hidden rounded-lg border bg-card">
          <table className="w-full text-left text-sm">
            <thead className="bg-muted/60 text-xs uppercase tracking-wide">
              <tr>
                <th className="px-3 py-2">Need</th>
                <th className="px-3 py-2">Primary responsibility</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {[
                ["Report and evidence intake", "CPD"],
                ["Pattern investigation", "CPD 003rd District detectives"],
                ["Charging after arrest", "Cook County State's Attorney"],
                ["Lighting assessment", "CDOT + ward coordination"],
                ["Public meeting response", "District commander / CAPS"],
                ["Budget and citywide priorities", "Mayor & City Council"],
                ["Recorded ward commitments", "20th Ward Alderman's office"],
              ].map(([need, who]) => (
                <tr key={need}>
                  <td className="px-3 py-2">{need}</td>
                  <td className="px-3 py-2 text-muted-foreground">{who}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          No single office controls the whole outcome. Ask each authority for
          their specific piece.
        </p>
      </section>

      <DisclosureNote>
        Patterns are computed from reported incidents in the selected beat over
        the selected window. Small counts are noted, and specific addresses are
        withheld to protect residents. Arrest and charging figures come from CPD
        and the Cook County State's Attorney open data.
      </DisclosureNote>
    </WireShell>
  );
}

function Stat({
  label,
  value,
  delta,
  tone,
}: {
  label: string;
  value: string;
  delta: string;
  tone: "up" | "down" | "steady";
}) {
  const cls =
    tone === "down"
      ? "text-primary"
      : tone === "up"
        ? "text-caution-foreground"
        : "text-muted-foreground";
  return (
    <div className="rounded-lg border bg-card p-3">
      <div className="wire-label">{label}</div>
      <div className="mt-1 font-serif text-3xl tabular-nums">{value}</div>
      <div className={"text-xs tabular-nums " + cls}>{delta}</div>
    </div>
  );
}

function Pattern({ title, body }: { title: string; body: string }) {
  return (
    <article className="rounded-lg border bg-card p-4">
      <h3 className="font-medium">{title}</h3>
      <p className="mt-1 text-sm text-muted-foreground">{body}</p>
    </article>
  );
}
