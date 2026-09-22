import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  createRootRouteWithContext,
  retainSearchParams,
  useRouter,
  HeadContent,
  Scripts,
} from "@tanstack/react-router";
import { useEffect, type ReactNode } from "react";

/**
 * The app's shared search params — the two global analytical contexts: `year` (see useYear)
 * and `geo`, the product geography (see useGeography).
 */
type RootSearch = {
  year?: number;
  geo?: string;
};

/**
 * Validate `?year` and `?geo` once, at the root, so every route sees clean values. A missing
 * or malformed value becomes "not selected" rather than an error; the hooks then resolve it to
 * the default (latest enriched year; Ward 20 overall). Values are shape-checked, not checked
 * against the live lists — those are fetched client-side, and an unknown-but-well-formed
 * geography is reported by useGeography as unsupported rather than silently replaced.
 */
function validateSearch(search: Record<string, unknown>): RootSearch {
  const result: RootSearch = {};

  const rawYear = search.year;
  const year = typeof rawYear === "number" ? rawYear : Number(rawYear);
  if (Number.isInteger(year) && year >= 2000 && year <= 2100) {
    result.year = year;
  }

  const rawGeo = typeof search.geo === "string" ? search.geo.trim().toLowerCase() : "";
  if (/^[a-z0-9-]{1,40}$/.test(rawGeo)) {
    result.geo = rawGeo;
  }

  return result;
}

import appCss from "../styles.css?url";
import { reportLovableError } from "../lib/lovable-error-reporting";

function NotFoundComponent() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-7xl font-bold text-foreground">404</h1>
        <h2 className="mt-4 text-xl font-semibold text-foreground">Page not found</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <div className="mt-6">
          <Link
            to="/"
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Go home
          </Link>
        </div>
      </div>
    </div>
  );
}

function ErrorComponent({ error, reset }: { error: Error; reset: () => void }) {
  console.error(error);
  const router = useRouter();
  useEffect(() => {
    reportLovableError(error, { boundary: "tanstack_root_error_component" });
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="text-xl font-semibold tracking-tight text-foreground">
          This page didn't load
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Something went wrong on our end. You can try refreshing or head back home.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <button
            onClick={() => {
              router.invalidate();
              reset();
            }}
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Try again
          </button>
          <a
            href="/"
            className="inline-flex items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
          >
            Go home
          </a>
        </div>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  validateSearch,
  // Keep `?year` attached as a reader moves between sections, so the selected year survives
  // navigation without any page having to thread it through links by hand.
  search: { middlewares: [retainSearchParams(["year", "geo"])] },
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      // Working public identity until the final product name is chosen. Not a brand.
      { title: "Ward 20 Neighborhood Intelligence" },
      {
        name: "description",
        content:
          "Reported crime and civic data for Chicago's Ward 20 and the neighborhoods within it, from public City of Chicago datasets. Development preview.",
      },
      { property: "og:title", content: "Ward 20 Neighborhood Intelligence" },
      {
        property: "og:description",
        content:
          "Reported crime and civic data for Chicago's Ward 20 and the neighborhoods within it. Development preview.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
    links: [
      {
        rel: "stylesheet",
        href: appCss,
      },
      { rel: "icon", href: "/favicon.svg", type: "image/svg+xml" },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function RootShell({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();

  return (
    <QueryClientProvider client={queryClient}>
      {/* Required: nested routes render here. Removing <Outlet /> breaks all child routes. */}
      <Outlet />
    </QueryClientProvider>
  );
}
