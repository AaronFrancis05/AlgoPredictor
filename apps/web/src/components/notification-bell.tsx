"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import { cn } from "@/lib/format";
import {
  freshUnread,
  notificationsSupported,
  registerServiceWorker,
  safeLink,
  showDeviceNotification,
  useAccountNotifySetting,
} from "@/lib/notify";
import { type AppNotification, Notifications } from "@/lib/schemas";

export const NOTIFICATIONS_KEY = ["notifications"] as const;

const when = (iso: string) =>
  new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
    .format(new Date(iso));

/** The inbox, polled every minute (also in a background tab when device notifications are on). New unread
 * items after the first load become device notifications when the user allowed them. */
function useNotifications(device: boolean) {
  const q = useQuery({
    queryKey: NOTIFICATIONS_KEY,
    queryFn: () => api("/me/notifications", Notifications),
    refetchInterval: 60_000,
    refetchIntervalInBackground: device,
    staleTime: 20_000,
  });
  const seen = useRef<Set<string> | null>(null);
  useEffect(() => {
    if (device) registerServiceWorker();
  }, [device]);
  useEffect(() => {
    if (!q.data) return;
    if (seen.current === null) {  // first load: remember what is there, never replay old messages
      seen.current = new Set(q.data.items.map((i) => i.id));
      return;
    }
    const fresh = freshUnread(seen.current, q.data.items);
    if (device) {
      for (const n of fresh) void showDeviceNotification(n.title, { body: n.body, tag: n.id, link: n.link });
    }
  }, [q.data, device]);
  return q;
}

function DeviceToggle() {
  const [on, enable, disable] = useAccountNotifySetting();
  const [blocked, setBlocked] = useState(false);
  if (!notificationsSupported()) {
    return <p className="text-xs text-muted">This browser cannot show device notifications. They still collect here.</p>;
  }
  return (
    <div className="space-y-1">
      <label className="flex cursor-pointer items-center justify-between gap-3 text-xs">
        <span>Show on this device</span>
        <input type="checkbox" className="h-4 w-4 accent-brand" checked={on}
               onChange={async () => { if (on) disable(); else setBlocked(!(await enable())); }} />
      </label>
      {blocked ? (
        <p className="text-[11px] text-muted">Notifications are blocked for this site. Allow them in the browser settings.</p>
      ) : null}
    </div>
  );
}

export function NotificationBell() {
  const qc = useQueryClient();
  const router = useRouter();
  const [device] = useAccountNotifySetting();
  const q = useNotifications(device);
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const unread = q.data?.unread ?? 0;

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function markRead(body: { ids: string[] } | { all: true }) {
    try {
      qc.setQueryData(NOTIFICATIONS_KEY, await api("/me/notifications/read", Notifications, { method: "POST", json: body }));
    } catch {
      // the next poll shows the real state
    }
  }

  function openItem(n: AppNotification) {
    if (!n.read) void markRead({ ids: [n.id] });
    const link = safeLink(n.link);
    setOpen(false);
    if (link) router.push(link);
  }

  return (
    <div ref={root} className="relative">
      <button type="button" aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen((o) => !o)}
              aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
              className={cn("relative grid h-9 w-9 place-items-center rounded-md border border-transparent text-muted hover:border-border hover:text-fg",
                open && "border-border bg-surface text-fg")}>
        <Bell className="h-4 w-4" aria-hidden />
        {unread ? (
          <span aria-hidden className="num absolute -right-1 -top-1 min-w-4 rounded-sm bg-danger px-1 text-center text-[10px] font-bold leading-4 text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        ) : null}
      </button>
      {open ? (
        <div role="dialog" aria-label="Notifications"
             className="fixed inset-x-4 top-16 z-50 overflow-hidden rounded-card border border-border bg-surface text-sm sm:absolute sm:inset-x-auto sm:right-0 sm:top-full sm:mt-2 sm:w-96">
          <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
            <p className="font-semibold">Notifications</p>
            {unread ? (
              <button type="button" className="text-xs font-semibold text-brand hover:underline" onClick={() => void markRead({ all: true })}>
                Mark all read
              </button>
            ) : null}
          </div>
          <div className="max-h-[60vh] overflow-y-auto">
            {q.isLoading ? <p className="px-4 py-6 text-center text-xs text-muted">Loading…</p> : null}
            {q.isError ? <p className="px-4 py-6 text-center text-xs text-muted">Could not load notifications.</p> : null}
            {q.data && q.data.items.length === 0 ? (
              <p className="px-4 py-6 text-center text-xs text-muted">No notifications yet.</p>
            ) : null}
            <ul className="divide-y divide-border">
              {q.data?.items.map((n) => (
                <li key={n.id}>
                  <button type="button" onClick={() => openItem(n)}
                          className={cn("flex w-full gap-3 px-4 py-3 text-left hover:bg-surface-2", !n.read && "bg-brand/5")}>
                    <span aria-hidden className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-sm", n.read ? "bg-transparent" : "bg-brand")} />
                    <span className="min-w-0 space-y-0.5">
                      <span className={cn("block", !n.read && "font-semibold")}>
                        {n.title}{n.read ? null : <span className="sr-only"> (unread)</span>}
                      </span>
                      {n.body ? <span className="block text-xs text-muted">{n.body}</span> : null}
                      <span className="block text-[11px] text-muted">{when(n.created_at)}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
          <div className="border-t border-border px-4 py-2.5">
            <DeviceToggle />
          </div>
        </div>
      ) : null}
    </div>
  );
}
