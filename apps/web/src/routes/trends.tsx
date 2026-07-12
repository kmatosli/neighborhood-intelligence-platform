import { createFileRoute } from "@tanstack/react-router";
import { WireShell, DisclosureNote, WirePanel } from "@/components/WireShell";

export const Route = createFileRoute("/trends")({
  head: () => ({
    meta: [
      { title: "Trends — Bronzeville & Woodlawn Neighborhood Brief" },
      {
        name: "description",
        content:
          "Is reported crime in Woodlawn getting better or worse? A single trend line and category changes.",
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
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Reported incidents in Woodlawn have declined gradually over the past
          five years, with a summer 2020 spike. The most recent 12 months are
          slightly below the five-year average.
        </p>
      </section>

      {/* Controls */}
      <section
        aria-label="Trend controls"
        className="mb-6 grid gap-3 rounded-lg border bg-card p-4 sm:grid-cols-5"
      >
        <Control label="Neighborhood" options={["Woodlawn", "Bronzeville", "Compare"]} />
        <Control
          label="Crime group"
          options={["All", "Violent", "Property", "Quality of life"]}
        />
        <Control
          label="Period"
          options={["Last 12 months", "Last 5 years", "Last 10 years"]}
        />
        <Control label="Show" options={["Counts", "Rate per 1,000"]} />
        <Control
          label="Compare with"
          options={["Prior year", "5-year baseline"]}
        />
      </section>

      {/* Primary view */}
      <section aria-labelledby="line" className="mb-8">
        <h2 id="line" className="font-serif text-xl">
          Reported incidents, monthly
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          One line: monthly reported incidents. Shaded band: five-year range for
          the same month.
        </p>
        <div className="mt-3">
          <WirePanel label="Line chart placeholder" height={260}>
            Line chart — monthly incidents with 5-year range band
          </WirePanel>
        </div>
        <DisclosureNote>
          Rate per 1,000 uses ACS 5-year population estimates for Community Area
          42 (Woodlawn). Population changes slowly, so short-term rate
          differences mostly reflect changes in reports, not people.
        </DisclosureNote>
      </section>

      {/* Category change */}
      <section aria-labelledby="cats">
        <h2 id="cats" className="font-serif text-xl">
          Category change vs prior year
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Horizontal bars show the absolute change in reports. Small categories
          can look extreme in percentage terms — the count is shown first.
        </p>
        <div className="mt-3 rounded-lg border bg-card p-4">
          <ul className="space-y-3">
            {[
              { name: "Motor vehicle theft", delta: +84 },
              { name: "Theft from vehicle", delta: +55 },
              { name: "Retail theft", delta: +28 },
              { name: "Criminal damage", delta: +9 },
              { name: "Narcotics", delta: -12 },
              { name: "Residential burglary", delta: -23 },
              { name: "Aggravated assault", delta: -34 },
              { name: "Robbery", delta: -47 },
            ].map((r) => (
              <CategoryBar key={r.name} name={r.name} delta={r.delta} />
            ))}
          </ul>
        </div>
      </section>
    </WireShell>
  );
}

function Control({ label, options }: { label: string; options: string[] }) {
  const id = label.toLowerCase().replace(/\s+/g, "-");
  return (
    <div>
      <label htmlFor={id} className="wire-label mb-1 block">
        {label}
      </label>
      <select
        id={id}
        className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
      >
        {options.map((o) => (
          <option key={o}>{o}</option>
        ))}
      </select>
    </div>
  );
}

function CategoryBar({ name, delta }: { name: string; delta: number }) {
  const max = 100;
  const pct = Math.min(100, (Math.abs(delta) / max) * 100);
  const positive = delta > 0;
  return (
    <li className="grid grid-cols-[minmax(0,10rem)_1fr_auto] items-center gap-3">
      <span className="truncate text-sm">{name}</span>
      <div className="relative h-4 rounded-sm bg-muted">
        <div className="absolute inset-y-0 left-1/2 w-px bg-border" />
        <div
          className={
            "absolute inset-y-0 " +
            (positive
              ? "left-1/2 bg-caution"
              : "right-1/2 bg-primary")
          }
          style={{ width: `${pct / 2}%` }}
          aria-hidden
        />
      </div>
      <span
        className={
          "shrink-0 text-sm font-medium tabular-nums " +
          (positive ? "text-caution-foreground" : "text-primary")
        }
      >
        {positive ? "+" : "−"}
        {Math.abs(delta)}
      </span>
    </li>
  );
}
