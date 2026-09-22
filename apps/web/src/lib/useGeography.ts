/**
 * The one place geography lives.
 *
 * Geography is the other primary analytical context beside year, so it lives in the URL too:
 * `/?geo=woodlawn&year=2024` is shareable, bookmarkable, and survives back/forward and a
 * refresh. The root route validates `?geo` and `retainSearchParams` keeps it attached while a
 * reader moves between sections, so this hook never needs its own store — the URL is the
 * single source of truth, exactly as with useYear.
 *
 * The list of geographies is never hardcoded: it comes from `/api/v1/geographies`. When no
 * valid geography is in the URL, the effective geography is the catalog's default — Ward 20
 * overall. A `?geo` naming an unknown or pending geography is NOT silently swapped for
 * something else: it is reported as `unsupported` so the page can say so.
 */

import { useCallback } from "react";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";

import {
  fetchGeographies,
  type GeographyCatalog,
  type GeographyKind,
  type NeighborhoodAvailability,
} from "@/lib/api";

export type GeographyState = {
  /** The effective geography id, or null while the catalog is still loading. */
  geographyId: string | null;
  /** The effective geography, or null while loading. */
  geography: NeighborhoodAvailability | null;
  /** Update the URL's `?geo`, staying on the current page. */
  setGeography: (geographyId: string) => void;
  /** Every geography from the API, in catalog order (the ward first). */
  geographies: NeighborhoodAvailability[];
  catalog: GeographyCatalog | null;
  /**
   * The `?geo` that was requested but cannot be shown (unknown, or pending a boundary), or
   * null when the URL is fine. The page must say so rather than show the default's figures
   * under the wrong name.
   */
  unsupported: NeighborhoodAvailability | { neighborhood_id: string; display_name: null } | null;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
};

export function useGeography(): GeographyState {
  const search = useSearch({ strict: false }) as { geo?: string };
  const navigate = useNavigate();

  const query = useQuery({
    queryKey: ["geographies"],
    queryFn: ({ signal }) => fetchGeographies(signal),
    retry: false,
    staleTime: Infinity,
  });

  const catalog = query.data ?? null;
  const geographies = catalog?.geographies ?? [];

  const requested = search.geo?.trim().toLowerCase() || null;
  const match = requested
    ? (geographies.find((g) => g.neighborhood_id === requested) ?? null)
    : null;

  let geography: NeighborhoodAvailability | null = null;
  let unsupported: GeographyState["unsupported"] = null;
  if (catalog) {
    if (match?.available) {
      geography = match;
    } else {
      geography =
        geographies.find((g) => g.neighborhood_id === catalog.default_geography_id) ?? null;
      if (requested) {
        unsupported = match ?? { neighborhood_id: requested, display_name: null };
      }
    }
  }

  const setGeography = useCallback(
    (next: string) => {
      // Same typed-search rough edge as useYear: this hook runs on several routes, so the
      // reducer's return is typed `never`. The update is a plain merge onto the validated root
      // search, so cast to navigate's own parameter type.
      navigate({
        search: (prev: Record<string, unknown>) => ({ ...prev, geo: next }),
      } as Parameters<typeof navigate>[0]);
    },
    [navigate],
  );

  return {
    geographyId: geography?.neighborhood_id ?? null,
    geography,
    setGeography,
    geographies,
    catalog,
    unsupported,
    isLoading: query.isLoading,
    isError: query.isError,
    error: (query.error as Error | null) ?? null,
  };
}

/**
 * The label a selector shows for a geography. The ward reads "Ward 20 overall"; a community
 * area reads "Woodlawn (part in Ward 20)" so it can never be read as the whole community area.
 */
export function geographyOptionLabel(geography: NeighborhoodAvailability): string {
  if (geography.kind === "ward") return `${geography.display_name} overall`;
  if (geography.kind === "community_area_portion") {
    return `${geography.display_name} (part in Ward 20)`;
  }
  return geography.display_name;
}

/** How a page names the place in its own headline. */
export function geographyHeadingName(name: string, kind: GeographyKind | string): string {
  return kind === "community_area_portion" ? `the Ward 20 part of ${name}` : name;
}
