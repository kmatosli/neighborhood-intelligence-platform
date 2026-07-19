import { createFileRoute } from "@tanstack/react-router";
import { WireShell } from "@/components/WireShell";
import { useBrief } from "@/lib/brief";

export const Route = createFileRoute("/beat-meeting")({
  head: () => ({
    meta: [
      { title: "Beat Meeting Brief — Bronzeville & Woodlawn" },
      {
        name: "description",
        content:
          "One-page brief for the next CAPS beat meeting: recurring patterns, questions to ask, and who has authority to act. Patterns are not yet connected to validated live data.",
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
        </div>
        {/* Disabled: neither export exists yet, and a button that does nothing when pressed
            reads as a broken site rather than an unfinished one. */}
        <div className="flex gap-2">
          <button
            type="button"
            disabled
            aria-describedby="exports-pending"
            className="cursor-not-allowed rounded-md border bg-muted px-3 py-1.5 text-sm text-muted-foreground opacity-70"
          >
            Print
          </button>
          <button
            type="button"
            disabled
            aria-describedby="exports-pending"
            className="cursor-not-allowed rounded-md border bg-muted px-3 py-1.5 text-sm text-muted-foreground opacity-70"
          >
            Download PDF
          </button>
          <span id="exports-pending" className="sr-only">
            Export is unavailable until this page is connected to live data
          </span>
        </div>
      </section>

      <p className="mb-6 rounded-md border bg-caution/20 p-3 text-base" role="note">
        <strong>Live data coming soon.</strong> The automated pattern detection below is not yet
        connected to validated live data. The issues <em>you</em> added from the Overview page,
        however, carry live figures and appear first.
      </p>

      <YourBrief />

      {/* Beat selector — kept in place, disabled until it selects against real data. */}
      <section className="mb-6 grid gap-3 rounded-lg border bg-card p-4 sm:grid-cols-3">
        <p id="controls-pending" className="wire-label sm:col-span-3">
          Controls are disabled until this page is connected to live data
        </p>
        <Control label="Beat" id="beat" options={["0311", "0312", "0313", "0314"]} />
        <Control
          label="Window"
          id="window"
          options={["Last 30 days", "Last 90 days", "Last 365 days"]}
        />
        <Control
          label="Compare with"
          id="cmp"
          options={["Same 90 days, prior year", "Prior 90 days"]}
        />
      </section>

      {/* Snapshot — the tiles stay so the shape of the brief is legible. No values, because
          no value has been computed. A dash is not a zero and is not a guess. */}
      <section aria-label="Snapshot" className="mb-8 grid gap-4 sm:grid-cols-4">
        <PendingStat label="Reports (90d)" />
        <PendingStat label="Violent" />
        <PendingStat label="Property" />
        <PendingStat label="Quality of life" />
      </section>

      {/* Recurring patterns */}
      <section aria-labelledby="patterns" className="mb-8">
        <h2 id="patterns" className="font-serif text-xl">
          Recurring patterns
        </h2>
        <PendingVisual
          height={200}
          planned="Recurring clusters of reported incidents by type, day of week, and time of day, described in plain language. Locations will be general areas, never addresses."
        />
        <p className="mt-2 text-xs text-muted-foreground">
          Pattern detection runs on reported incidents only. A reported incident is not a
          conviction, and a cluster of reports is not proof of a cause.
        </p>
      </section>

      {/* Questions */}
      <section aria-labelledby="qs" className="mb-8">
        <h2 id="qs" className="font-serif text-xl">
          Questions to ask
        </h2>
        <PendingVisual
          height={160}
          planned="Questions generated from the patterns actually found in the selected beat and window, each naming the office that can answer it."
        />
        <p className="mt-2 text-xs text-muted-foreground">
          These questions will follow from the data. Publishing a fixed list before the patterns
          exist would put words in residents&rsquo; mouths about problems no one has measured.
        </p>
      </section>

      {/* Who has authority to act — civic reference, not derived from crime data, so it stands
          on its own and stays live. */}
      <section aria-labelledby="resp">
        <h2 id="resp" className="font-serif text-xl">
          Who has authority to act
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Reference information about which office is responsible for what. This does not depend
          on the crime data and is shown in full.
        </p>
        <div className="mt-3 overflow-x-auto rounded-lg border bg-card">
          <table className="w-full min-w-[32rem] text-left text-sm">
            <thead className="bg-muted/60 text-xs uppercase tracking-wide">
              <tr>
                <th scope="col" className="px-3 py-2">
                  Need
                </th>
                <th scope="col" className="px-3 py-2">
                  Primary responsibility
                </th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {[
                ["Report and evidence intake", "CPD"],
                ["Pattern investigation", "CPD district detectives"],
                ["Charging after arrest", "Cook County State's Attorney"],
                ["Lighting assessment", "CDOT + ward coordination"],
                ["Public meeting response", "District commander / CAPS"],
                ["Budget and citywide priorities", "Mayor & City Council"],
                ["Recorded ward commitments", "Ward Alderman's office"],
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
          No single office controls the whole outcome. Ask each authority for their specific piece.
        </p>
      </section>
    </WireShell>
  );
}

/**
 * The issues a resident collected from other pages (currently the Overview). Each item already
 * carries live figures computed on its source page, so this section shows real numbers even
 * while automated pattern detection is still pending. This is the "Open my brief" destination.
 */
function YourBrief() {
  const brief = useBrief();

  if (brief.items.length === 0) {
    return (
      <section aria-labelledby="your-brief" className="mb-8 rounded-lg border border-dashed bg-card/50 p-4">
        <h2 id="your-brief" className="font-serif text-xl">
          Your brief is empty
        </h2>
        <p className="mt-1 text-base text-muted-foreground">
          On the Overview page, use <strong>Add to brief</strong> on any issue to collect it here
          for your beat meeting. Nothing is added automatically.
        </p>
      </section>
    );
  }

  return (
    <section aria-labelledby="your-brief" className="mb-8">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="your-brief" className="font-serif text-xl">
          Your brief · {brief.items.length} issue{brief.items.length === 1 ? "" : "s"}
        </h2>
        <button
          type="button"
          onClick={() => brief.clear()}
          className="min-h-11 rounded-md border bg-background px-3 py-2 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          Clear brief
        </button>
      </div>
      <ol className="mt-3 space-y-3">
        {brief.items.map((item) => (
          <li key={item.id} className="rounded-lg border bg-card p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <h3 className="font-serif text-lg font-semibold">{item.title}</h3>
              <button
                type="button"
                onClick={() => brief.remove(item.id)}
                aria-label={`Remove ${item.title} from brief`}
                className="min-h-11 rounded-md border bg-background px-3 py-1 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              >
                Remove
              </button>
            </div>
            <dl className="mt-2 space-y-1 text-sm">
              <BriefRow term="Supporting figure" desc={item.supportingStat} />
              <BriefRow term="Comparison" desc={item.comparisonPeriod} />
              {item.beat && <BriefRow term="Beat" desc={item.beat} />}
              <BriefRow term="Responsible authority" desc={item.primaryAuthority} />
              {item.alderpersonRole && <BriefRow term="Alderperson" desc={item.alderpersonRole} />}
              {item.residentQuestion && <BriefRow term="Question to ask" desc={`“${item.residentQuestion}”`} />}
              {item.evidence && <BriefRow term="Evidence" desc={item.evidence} />}
            </dl>
          </li>
        ))}
      </ol>
      <p className="mt-2 text-xs text-muted-foreground">
        Every figure here was computed from live data on the page that produced it. Printing this
        brief will be added in a later milestone.
      </p>
    </section>
  );
}

function BriefRow({ term, desc }: { term: string; desc: string }) {
  return (
    <div className="grid grid-cols-[9rem_1fr] gap-2">
      <dt className="text-muted-foreground">{term}</dt>
      <dd>{desc}</dd>
    </div>
  );
}

/**
 * A visualization with no validated data behind it yet. Renders no marks and no numbers, and
 * names what is planned so the page still communicates its purpose.
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

/** A headline figure whose value has not been computed. The dash never stands in for zero. */
function PendingStat({ label }: { label: string }) {
  return (
    <div className="rounded-lg border bg-card p-3">
      <div className="wire-label">{label}</div>
      <div className="mt-1 font-serif text-3xl text-muted-foreground" aria-hidden="true">
        —
      </div>
      <div className="text-xs text-muted-foreground">Live data coming soon</div>
    </div>
  );
}

function Control({ label, id, options }: { label: string; id: string; options: string[] }) {
  return (
    <div>
      <label htmlFor={id} className="wire-label mb-1 block text-muted-foreground">
        {label}
      </label>
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
