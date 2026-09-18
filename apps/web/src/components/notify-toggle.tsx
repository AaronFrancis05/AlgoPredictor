"use client";

import { Bell, BellOff } from "lucide-react";
import { useState } from "react";

import { notificationsSupported, useNotifySetting } from "@/lib/notify";

/** Turn browser notifications for followed matches on or off (this browser only). */
export function NotifyToggle() {
  const [on, enable, disable] = useNotifySetting();
  const [denied, setDenied] = useState(false);
  if (!notificationsSupported()) return null;
  return (
    <div className="flex flex-col items-end gap-1">
      <button type="button" aria-pressed={on}
              onClick={async () => { if (on) disable(); else setDenied(!(await enable())); }}
              className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs hover:bg-surface-2">
        {on ? <Bell className="h-3.5 w-3.5 text-brand" aria-hidden /> : <BellOff className="h-3.5 w-3.5" aria-hidden />}
        {on ? "Notifying: followed matches" : "Notify me about followed matches"}
      </button>
      {denied ? (
        <p className="text-[11px] text-muted">Notifications are blocked for this site. Allow them in the browser settings.</p>
      ) : null}
    </div>
  );
}
