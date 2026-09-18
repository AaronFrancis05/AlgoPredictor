"use client";

import { type QueryClient, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

/**
 * Pushed change notifications from the API (Server-Sent Events). An event only names what changed; the affected
 * queries are refetched through the normal endpoints, which apply the viewer's plan.
 *
 * NEXT_PUBLIC_EVENTS_URL can point straight at the API (e.g. https://api.example/api/v1/events) when the host in
 * front of the site buffers streamed responses; the default goes through the same-origin /api/v1 rewrite.
 */
const EVENTS_URL = process.env.NEXT_PUBLIC_EVENTS_URL || "/api/v1/events";

export type LiveEventKind = "live" | "picks";

const AFFECTS: Record<LiveEventKind, string[]> = {
  live: ["live", "picks", "top", "jackpot"],
  picks: ["picks", "top", "jackpot", "history", "live"],
};

const listeners = new Set<(kind: LiveEventKind) => void>();

/** Extra reactions to pushed events (e.g. notifications for followed matches). Returns an unsubscribe. */
export function onLiveEvent(fn: (kind: LiveEventKind) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function refresh(qc: QueryClient, kind: LiveEventKind) {
  for (const key of AFFECTS[kind]) void qc.invalidateQueries({ queryKey: [key] });
  listeners.forEach((l) => l(kind));
}

/**
 * Keeps one stream open while the tab is visible (or while `keepInBackground`, used when the viewer asked for
 * notifications). On returning to the tab everything live is refreshed once, since events may have been missed.
 */
export function useLiveEvents(enabled: boolean, keepInBackground = false) {
  const qc = useQueryClient();
  useEffect(() => {
    if (!enabled || typeof EventSource === "undefined") return;
    let source: EventSource | null = null;
    const open = () => {
      if (source) return;
      source = new EventSource(EVENTS_URL);
      source.addEventListener("live", () => refresh(qc, "live"));
      source.addEventListener("picks", () => refresh(qc, "picks"));
    };
    const close = () => {
      source?.close();
      source = null;
    };
    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        if (!source) refresh(qc, "live");
        open();
      } else if (!keepInBackground) {
        close();
      }
    };
    if (document.visibilityState === "visible" || keepInBackground) open();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      close();
    };
  }, [enabled, keepInBackground, qc]);
}
