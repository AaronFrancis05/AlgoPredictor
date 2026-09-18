"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { today } from "@/lib/format";
import { LivePicks, User } from "@/lib/schemas";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => api("/me", User), staleTime: 30_000 });
}

/** The current time, re-read every `everyMs` so views can move matches between phases as the clock passes. */
export function useNow(everyMs = 30_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), everyMs);
    return () => clearInterval(id);
  }, [everyMs]);
  return now;
}

/** The viewer's local date, updated when their clock passes midnight while the page is open. */
export function useToday(): string {
  useNow(60_000);
  return today();
}

const LIVE_MIN_MS = 15_000;
const LIVE_MAX_MS = 5 * 60_000;
const LIVE_FALLBACK_MS = 2 * 60_000;

/**
 * Milliseconds until the live list should be fetched again. The API says when the list is next expected to
 * change (the worker's next score poll or the next kick-off); refetching earlier only returns the same data.
 * Pushed updates (useLiveEvents) refresh sooner when something changes in between.
 */
export function liveRefetchDelay(nextUpdateAt: string | null | undefined, now = Date.now()): number {
  if (!nextUpdateAt) return LIVE_FALLBACK_MS;
  const due = Date.parse(nextUpdateAt) - now + 3_000; // a little after the poll, so its result is in
  if (Number.isNaN(due)) return LIVE_FALLBACK_MS;
  return Math.min(LIVE_MAX_MS, Math.max(LIVE_MIN_MS, due));
}

export const liveQuery = {
  queryKey: ["live"],
  queryFn: () => api("/picks/live", LivePicks),
  staleTime: LIVE_MIN_MS,
};

/** Matches in play. Shared by the nav badge and the Live page (one cache entry, one refetch schedule). */
export function useLive(enabled = true) {
  return useQuery({
    ...liveQuery,
    enabled,
    refetchInterval: (q) => liveRefetchDelay(q.state.data?.next_update_at),
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true, // coming back to the tab shows current scores at once
  });
}
