/**
 * The meeting brief: a small, resident-owned collection of issues carried from any page to
 * the Beat Meeting brief. It is the connective tissue between Overview, Services &
 * Accountability, and (later) Promises, Money, and Act.
 *
 * State lives in localStorage — the simplest mechanism that survives navigation and reload
 * without a global store. Changes broadcast a custom event so every mounted `useBrief()`
 * updates in step, including across browser tabs (via the native `storage` event).
 *
 * No numbers are computed here. A brief item only ever holds values that were already
 * derived from live data on the page that produced it.
 */

import { useCallback, useSyncExternalStore } from "react";

const STORAGE_KEY = "bww.brief.v1";
const CHANGE_EVENT = "bww:brief-changed";

/**
 * A shared accountability issue — the common record that lets Overview, Services, Promises,
 * Money, and Act refer to one issue instead of duplicating its facts. Optional fields are
 * present only for the pages that can supply them.
 */
export type BriefItem = {
  /** Stable identifier so the same issue is never added twice. */
  id: string;
  source: "overview" | "services" | "promises" | "money" | "act";
  category: string;
  title: string;
  /** The single statistic that supports the finding, already computed on the source page. */
  supportingStat: string;
  comparisonPeriod: string;
  geography?: string;
  beat?: string | null;
  primaryAuthority: string;
  supportingAuthority?: string | null;
  alderpersonRole?: string;
  residentQuestion?: string;
  evidence?: string;
  addedAt: number;
};

function read(): BriefItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? (parsed as BriefItem[]) : [];
  } catch {
    return [];
  }
}

function write(items: BriefItem[]): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export function getBrief(): BriefItem[] {
  return read();
}

/** Add an issue, ignoring a duplicate id so a reader cannot add the same finding twice. */
export function addToBrief(item: BriefItem): void {
  const items = read();
  if (items.some((existing) => existing.id === item.id)) return;
  write([...items, item]);
}

export function removeFromBrief(id: string): void {
  write(read().filter((item) => item.id !== id));
}

export function clearBrief(): void {
  write([]);
}

export function isInBrief(id: string): boolean {
  return read().some((item) => item.id === id);
}

// -- React binding ---------------------------------------------------------------------

function subscribe(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const onStorage = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY) callback();
  };
  window.addEventListener(CHANGE_EVENT, callback);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(CHANGE_EVENT, callback);
    window.removeEventListener("storage", onStorage);
  };
}

// A stable snapshot reference between changes keeps useSyncExternalStore from looping.
let cache: BriefItem[] = [];
let cacheKey = "";
function getSnapshot(): BriefItem[] {
  if (typeof window === "undefined") return cache;
  const raw = window.localStorage.getItem(STORAGE_KEY) ?? "";
  if (raw !== cacheKey) {
    cacheKey = raw;
    cache = read();
  }
  return cache;
}

export function useBrief(): {
  items: BriefItem[];
  add: (item: BriefItem) => void;
  remove: (id: string) => void;
  clear: () => void;
  has: (id: string) => boolean;
} {
  const items = useSyncExternalStore(subscribe, getSnapshot, () => cache);
  const add = useCallback((item: BriefItem) => addToBrief(item), []);
  const remove = useCallback((id: string) => removeFromBrief(id), []);
  const clear = useCallback(() => clearBrief(), []);
  const has = useCallback((id: string) => items.some((i) => i.id === id), [items]);
  return { items, add, remove, clear, has };
}
