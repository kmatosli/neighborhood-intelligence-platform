import { createFileRoute } from "@tanstack/react-router";
import { WireShell } from "@/components/WireShell";

export const Route = createFileRoute("/trends")({
  head: () => ({
    meta: [
      { title: "Trends — Bronzeville & Woodlawn Neighborhood Brief" },
      {
        name: "description",
        content:
          "Is reported crime in Woodlawn getting better or worse? A single trend line and category changes. Not yet connected to validated live data.",
      },
    ],
  }),
  component: Trends,
});

function Trends() {
  return (
    <WireShell>
      <section className="mb-6">
        <p className="wire-label mb-2">Main question</p>
        <h1 className="font-serif text-2xl leading-snug sm:text-3xl">
          Is it getting better or worse?
        </h1>

        <p className="mt-3 rounded-md border bg-caution/20 p-3 text-base" role="note">
          <strong>Live data coming soon.</strong> This page is not yet connected to validated live
          data. The layout below shows what it will contain. No trend, figure, or comparison is
          shown until the data supports one.
        </p>

        {/* No direction is stated. Answering this question needs several enriched years; only
            2024 and 2026 exist so far, so "rising" or "falling" would be invented. */}
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Answering this question requires several years of geography-enriched data. Until those
          years are complete, this page says nothing about direction — an unsupported claim about
          whether a neighborhood is getting safer is not a harmless placeholder.
        </p>
      </section>

      {/* Controls — kept in place, disabled until they filter real data. */}
      <section
        aria-label="Trend controls"
        className="mb-6 grid gap-3 rounded-lg border bg-card p-4 sm:grid-cols-5"
      >
        <p id="controls-pending" className="wire-label sm:col-span-5">
          Controls are disabled until this page is connected to live data
        </p>
        <Control label="Neighborhood" options={["Woodlawn", "Bronzeville", "Compare"]} />
        <Control label="Crime group" options={["All", "Violent", "Property", "Quality of life"]} />
        <Control label="Period" options={["Last 12 months", "Last 5 years", "Last 10 years"]} />
        <Control label="Show" options={["Counts", "Rate per 1,000"]} />
        <Control label="Compare with" options={["Prior year", "5-year baseline"]} />
      </section>

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

/**
 * A visualization with no validated data behind it yet.
 *
 * It renders no marks, no axis, and no numbers, and says plainly that it is not connected. An
 * empty chart frame would read as "zero incidents"; a populated one would be a fabrication.
 * Naming what is planned keeps the page useful to a reader without asserting anything.
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

function Control({ label, options }: { label: string; options: string[] }) {
  const id = label.toLowerCase().replace(/\s+/g, "-");
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
