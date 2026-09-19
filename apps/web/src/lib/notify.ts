"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useSyncExternalStore } from "react";

import type { Pick } from "@/lib/schemas";

const WATCHED = new Set(["live", "picks", "top"]);

/**
 * Device notifications while the site is open (also in a background tab). Two opt-in settings per browser, both
 * needing the browser's permission: followed matches (a goal, full time, a match called off) and account
 * messages (the bell: access codes, plan changes, reminders).
 */
export const notificationsSupported = () => typeof window !== "undefined" && "Notification" in window;

/** A per-browser on/off setting kept in localStorage (in memory when storage is blocked). */
function makeSetting(key: string) {
  const listeners = new Set<() => void>();
  let memory = false;
  const read = (): boolean => {
    const granted = typeof Notification !== "undefined" && Notification.permission === "granted";
    let stored = memory;
    try {
      stored = localStorage.getItem(key) === "on";
    } catch {
      // storage unavailable: keep the in-memory value
    }
    return stored && granted;
  };
  const write = (on: boolean) => {
    memory = on;
    try {
      if (on) localStorage.setItem(key, "on");
      else localStorage.removeItem(key);
    } catch {
      // storage unavailable: the setting lasts until reload
    }
    listeners.forEach((l) => l());
  };
  /** [on, turn on (asks permission), turn off] */
  return function useSetting(): [boolean, () => Promise<boolean>, () => void] {
    const on = useSyncExternalStore(
      (cb) => { listeners.add(cb); return () => { listeners.delete(cb); }; },
      read,
      () => false,
    );
    const enable = async () => {
      if (!notificationsSupported()) return false;
      const perm = Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
      if (perm === "granted") registerServiceWorker();
      write(perm === "granted");
      return perm === "granted";
    };
    return [on, enable, () => write(false)];
  };
}

/** Followed-match notifications (goals, full time). */
export const useNotifySetting = makeSetting("ap.notify");
/** Account notifications from the bell. */
export const useAccountNotifySetting = makeSetting("ap.notify.account");

/** Only site paths may be opened from a notification. */
export const safeLink = (link: string | null | undefined): string | null =>
  link && link.startsWith("/") && !link.startsWith("//") ? link : null;

/** Register /sw.js, which only shows notifications and opens their link (it caches nothing). Android Chrome
 * refuses `new Notification()` and needs this; elsewhere it is a harmless extra. */
export function registerServiceWorker() {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
  navigator.serviceWorker.register("/sw.js").catch(() => {
    // not allowed here (private mode, old browser): the page falls back to new Notification()
  });
}

/** The active service worker registration (registering /sw.js if needed, waiting up to 3 s), or undefined. */
async function activeRegistration(): Promise<ServiceWorkerRegistration | undefined> {
  if (!("serviceWorker" in navigator)) return undefined;
  try {
    const reg = (await navigator.serviceWorker.getRegistration()) ?? (await navigator.serviceWorker.register("/sw.js"));
    if (reg.active) return reg;
    return await Promise.race([
      navigator.serviceWorker.ready,
      new Promise<undefined>((resolve) => setTimeout(() => resolve(undefined), 3000)),
    ]);
  } catch {
    return undefined;
  }
}

/** Show a notification on the device, if the user allowed it. Never throws. */
export async function showDeviceNotification(title: string, opts: { body: string; tag: string; link?: string | null }) {
  if (!notificationsSupported() || Notification.permission !== "granted") return;
  const link = safeLink(opts.link);
  const options = { body: opts.body, tag: opts.tag, icon: "/icon", data: { link } };
  try {
    const reg = await activeRegistration();
    if (reg) {
      await reg.showNotification(title, options);
      return;
    }
  } catch {
    // fall through to the page-level notification
  }
  try {
    const n = new Notification(title, options);
    n.onclick = () => {
      window.focus();
      if (link) window.location.assign(link);
      n.close();
    };
  } catch {
    // some mobile browsers only allow notifications from a service worker
  }
}

/** Unread items not seen before, oldest first. `seen` is updated. Exported for tests. */
export function freshUnread<T extends { id: string; read: boolean }>(seen: Set<string>, items: T[]): T[] {
  const fresh = items.filter((i) => !seen.has(i.id) && !i.read);
  items.forEach((i) => seen.add(i.id));
  return fresh.reverse();
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
        if (msg && follows.current?.(p)) {
          void showDeviceNotification("AlgoPredict", { body: msg, tag: p.prediction_id, link: "/live" });
        }
      }
    });
  }, [enabled, qc]);
}
