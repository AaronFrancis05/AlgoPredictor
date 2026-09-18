"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useSyncExternalStore } from "react";

import type { Pick } from "@/lib/schemas";

const WATCHED = new Set(["live", "picks", "top"]);

/**
 * Browser notifications for followed matches while the site is open (also in a background tab): a goal, full
 * time, or a match called off. Opt-in per browser; needs the browser's permission.
 */
const PREF_KEY = "ap.notify";
const prefListeners = new Set<() => void>();
let memoryPref = false; // mirror of the stored setting, used when localStorage is unavailable

function readPref(): boolean {
  const granted = typeof Notification !== "undefined" && Notification.permission === "granted";
  let stored = memoryPref;
  try {
    stored = localStorage.getItem(PREF_KEY) === "on";
  } catch {
    // storage unavailable: keep the in-memory value
  }
  return stored && granted;
}

function writePref(on: boolean) {
  memoryPref = on;
  try {
    if (on) localStorage.setItem(PREF_KEY, "on");
    else localStorage.removeItem(PREF_KEY);
  } catch {
    // storage unavailable: the setting lasts until reload
  }
  prefListeners.forEach((l) => l());
}

export const notificationsSupported = () => typeof window !== "undefined" && "Notification" in window;

/** [on, turn on (asks permission), turn off] */
export function useNotifySetting(): [boolean, () => Promise<boolean>, () => void] {
  const on = useSyncExternalStore(
    (cb) => { prefListeners.add(cb); return () => { prefListeners.delete(cb); }; },
    readPref,
    () => false,
  );
  const enable = async () => {
    if (!notificationsSupported()) return false;
    const perm = Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
    writePref(perm === "granted");
    return perm === "granted";
  };
  return [on, enable, () => writePref(false)];
}

/** What a notification is about: score and status of one match. Exported for tests. */
export function matchSignature(p: Pick): string {
  const l = p.live;
  return `${l?.home_goals ?? "-"}:${l?.away_goals ?? "-"}|${l?.status ?? ""}|${p.phase}`;
}

/** The message for a change from `before` to `p`, or null when nothing worth telling happened. */
export function changeMessage(before: string | undefined, p: Pick): string | null {
  const now = matchSignature(p);
  if (before === undefined || before === now) return null;
  const [scoreBefore] = before.split("|");
  const [score] = now.split("|");
  const teams = `${p.home_team} ${p.live?.home_goals ?? ""}-${p.live?.away_goals ?? ""} ${p.away_team}`;
  if (["postponed", "cancelled", "abandoned"].includes(p.phase)) return `${p.home_team} v ${p.away_team}: ${p.phase}`;
  if (p.live && ["FT", "AET", "PEN"].includes(p.live.status) && !before.includes(`|${p.live.status}|`)) {
    return `Full time: ${teams}`;
  }
  const goals = (s: string) => {
    const [h, a] = s.split(":").map(Number);
    return Number.isFinite(h) && Number.isFinite(a) ? h + a : null;
  };
  const [totalBefore, total] = [goals(scoreBefore), goals(score)];
  if (totalBefore !== null && total !== null && total > totalBefore) return `Goal: ${teams}`;
  return null;
}

/**
 * Watches the shared live query and notifies about followed matches. The first sighting of a match only records
 * its state, so opening the page never replays old goals.
 */
export function useMatchNotifications(enabled: boolean, isFollowed: ((p: Pick) => boolean) | null) {
  const qc = useQueryClient();
  const seen = useRef(new Map<string, string>());
  const follows = useRef(isFollowed);
  useEffect(() => {
    follows.current = isFollowed;
  }, [isFollowed]);

  useEffect(() => {
    if (!enabled) return;
    return qc.getQueryCache().subscribe((event) => {
      // the live list drops a match at full time, so the day lists (which keep finished matches) are watched too
      if (event.type !== "updated" || !WATCHED.has(String(event.query.queryKey[0]))) return;
      const data = event.query.state.data as { picks?: Pick[] } | undefined;
      if (!data?.picks) return;
      for (const p of data.picks) {
        const msg = changeMessage(seen.current.get(p.prediction_id), p);
        seen.current.set(p.prediction_id, matchSignature(p));
        if (msg && follows.current?.(p) && Notification.permission === "granted") {
          try {
            new Notification("AlgoPredict", { body: msg, tag: p.prediction_id, icon: "/icon" });
          } catch {
            // some mobile browsers only allow notifications from a service worker
          }
        }
      }
    });
  }, [enabled, qc]);
}
