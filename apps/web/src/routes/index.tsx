import { createFileRoute, Link } from "@tanstack/react-router";
import { WireShell, DisclosureNote } from "@/components/WireShell";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "What changed? — Bronzeville & Woodlawn Neighborhood Brief" },
      {
        name: "description",
        content:
          "A resident-facing brief on reported crime and neighborhood change in Bronzeville and Woodlawn. Wireframe build.",
      },
      { property: "og:title", content: "Bronzeville & Woodlawn Neighborhood Brief" },
      {
        property: "og:description",
        content: "What changed in your neighborhood? Plain-language findings, then the numbers.",
      },
    ],
  }),
  component: Overview,
});

type Card = {
  label: string;
  current: number;
  prior: number;
  interpretation: string;
  tone: "steady" | "down" | "up";
};

const CARDS: Card[] = [
  {
    label: "Reported crime (all)",
    current: 3842,
    prior: 3961,
    interpretation:
      "Slightly fewer reports than the same period last year. The change is small — treat it as roughly steady.",
    tone: "steady",
  },
  {
    label: "Violent crime",
    current: 612,
    prior: 674,
    interpretation:
      "Reported violent incidents are down from last year. Robbery and aggravated assault drove most of the decrease.",
    tone: "down",
  },
  {
    label: "Property crime",
    current: 1487,
    prior: 1329,
    interpretation:
      "Reported property incidents are up. Motor-vehicle theft and theft-from-vehicle rose the most.",
    tone: "up",
  },
];

const INCREASES = [
  { name: "Motor vehicle theft", from: 214, to: 298 },
  { name: "Theft from vehicle", from: 176, to: 231 },
  { name: "Retail theft", from: 84, to: 112 },
];

const DECREASES = [
  { name: "Robbery", from: 188, to: 141 },
  { name: "Aggravated assault", from: 302, to: 268 },
  { name: "Residential burglary", from: 121, to: 98 },
];

function fmt(n: number) {
  return n.toLocaleString("en-US");
}

function diffText(current: number, prior: number) {
  const delta = current - prior;
  const pct = prior === 0 ? 0 : Math.round((delta / prior) * 100);
  const sign = delta > 0 ? "+" : delta < 0 ? "−" : "";
  return {
    abs: `${sign}${fmt(Math.abs(delta))}`,
    pct: `${sign}${Math.abs(pct)}%`,
    delta,
  };
}

function Overview() {
  return (
    <WireShell neighborhood="Woodlawn">
      {/* Headline finding */}
      <section aria-labelledby="finding" className="mb-8">
        <p className="wire-label mb-2">Headline finding</p>
        <h1 id="finding" className="font-serif text-2xl leading-snug sm:text-3xl">
          Reported violent crime in Woodlawn is <strong>down</strong> from the
          same period last year. <span className="text-muted-foreground">Reports of </span>
          vehicle break-ins and car theft <strong>increased</strong>.
        </h1>
        <p className="mt-3 text-sm text-muted-foreground">
          Compared to Jan–Dec 2023. Counts below are reported incidents, not
          convictions.
        </p>
      </section>

      {/* Three primary cards */}
      <section aria-label="Key figures" className="grid gap-4 sm:grid-cols-3">
        {CARDS.map((c) => {
          const d = diffText(c.current, c.prior);
          const toneClass =
            c.tone === "down"
              ? "text-primary"
              : c.tone === "up"
                ? "text-caution-foreground"
                : "text-muted-foreground";
          return (
            <article
              key={c.label}
              className="rounded-lg border bg-card p-4 shadow-sm"
            >
              <h2 className="wire-label">{c.label}</h2>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="font-serif text-4xl font-semibold tabular-nums">
                  {fmt(c.current)}
                </span>
                <span className="text-sm text-muted-foreground tabular-nums">
                  vs {fmt(c.prior)} last year
                </span>
              </div>
              <div className={"mt-1 text-sm font-medium tabular-nums " + toneClass}>
                {d.abs} reports ({d.pct})
              </div>
              <p className="mt-3 text-sm">{c.interpretation}</p>
            </article>
          );
        })}
      </section>

      {/* Trend wireframe */}
      <section aria-labelledby="trend" className="mt-8">
        <h2 id="trend" className="font-serif text-xl">
          Last 12 months of reported incidents
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          A single monthly line, compared to the prior 12 months. Chart shows a
          gentle overall decrease with a summer bump.
        </p>
        <div className="mt-3">
          <WireLineChart />
        </div>
        <DisclosureNote>
          Monthly counts are pulled from the Chicago Data Portal Crimes dataset,
          filtered to Community Area 42 (Woodlawn). Comparison is the same month
          one year prior. Missing days are not imputed.
        </DisclosureNote>
      </section>

      {/* Top movers */}
      <section aria-label="Top changes" className="mt-8 grid gap-6 sm:grid-cols-2">
        <MoverList
          title="Top three increases"
          items={INCREASES}
          direction="up"
        />
        <MoverList
          title="Top three decreases"
          items={DECREASES}
          direction="down"
        />
      </section>

      {/* Beat meeting CTA */}
      <section
        aria-labelledby="beat-cta"
        className="mt-8 rounded-lg border bg-accent/50 p-5"
      >
        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 sm:flex sm:justify-between">
          <div className="min-w-0">
            <h2 id="beat-cta" className="font-serif text-lg font-semibold">
              Prepare for the next beat meeting
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              A printable one-page brief with recurring patterns, questions to
              ask, and who is responsible.
            </p>
          </div>
          <Link
            to="/beat-meeting"
            className="shrink-0 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-95"
          >
            Open brief
          </Link>
        </div>
      </section>
    </WireShell>
  );
}

function MoverList({
  title,
  items,
  direction,
}: {
  title: string;
  items: { name: string; from: number; to: number }[];
  direction: "up" | "down";
}) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <h3 className="wire-label mb-2">{title}</h3>
      <ul className="divide-y">
        {items.map((it) => {
          const d = diffText(it.to, it.from);
          return (
            <li key={it.name} className="flex items-baseline justify-between gap-3 py-2">
              <span className="min-w-0 truncate text-sm">{it.name}</span>
              <span className="shrink-0 text-sm tabular-nums text-muted-foreground">
                {fmt(it.from)} → <span className="text-foreground">{fmt(it.to)}</span>{" "}
                <span
                  className={
                    direction === "down" ? "text-primary" : "text-caution-foreground"
                  }
                >
                  ({d.pct})
                </span>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function WireLineChart() {
  // Sample monthly series (this year vs last year) - illustrative only
  const curr = [340, 305, 298, 312, 328, 355, 372, 361, 340, 315, 302, 314];
  const prev = [352, 318, 310, 325, 340, 371, 384, 375, 358, 332, 315, 321];
  const labels = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];
  const w = 640;
  const h = 200;
  const pad = { t: 16, r: 12, b: 28, l: 32 };
  const max = Math.max(...curr, ...prev) * 1.05;
  const min = Math.min(...curr, ...prev) * 0.85;
  const x = (i: number) =>
    pad.l + (i * (w - pad.l - pad.r)) / (curr.length - 1);
  const y = (v: number) =>
    pad.t + ((max - v) / (max - min)) * (h - pad.t - pad.b);
  const line = (arr: number[]) =>
    arr.map((v, i) => `${i === 0 ? "M" : "L"} ${x(i)} ${y(v)}`).join(" ");

  return (
    <figure className="rounded-lg border bg-card p-3">
      <svg
        viewBox={`0 0 ${w} ${h}`}
        role="img"
        aria-label="Monthly reported incidents this year compared to last year"
        className="h-auto w-full"
      >
        <g stroke="currentColor" className="text-border" strokeWidth={1}>
          <line x1={pad.l} x2={w - pad.r} y1={h - pad.b} y2={h - pad.b} />
        </g>
        <path
          d={line(prev)}
          fill="none"
          strokeDasharray="4 4"
          className="stroke-muted-foreground"
          strokeWidth={1.5}
        />
        <path
          d={line(curr)}
          fill="none"
          className="stroke-primary"
          strokeWidth={2}
        />
        {labels.map((lb, i) => (
          <text
            key={i}
            x={x(i)}
            y={h - pad.b + 16}
            textAnchor="middle"
            className="fill-muted-foreground"
            fontSize={11}
          >
            {lb}
          </text>
        ))}
      </svg>
      <figcaption className="mt-2 flex flex-wrap gap-4 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-2">
          <span className="inline-block h-0.5 w-6 bg-primary" />
          This year
        </span>
        <span className="inline-flex items-center gap-2">
          <span
            className="inline-block h-0.5 w-6"
            style={{
              backgroundImage:
                "linear-gradient(to right, currentColor 50%, transparent 50%)",
              backgroundSize: "6px 2px",
            }}
          />
          Last year
        </span>
        <span className="ml-auto">
          <a href="#" className="underline">
            View as accessible data table
          </a>
        </span>
      </figcaption>
    </figure>
  );
}
