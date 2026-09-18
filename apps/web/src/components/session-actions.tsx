"use client";

import { LayoutDashboard } from "lucide-react";
import type { ReactNode } from "react";
import { useSyncExternalStore } from "react";

import { ButtonLink } from "@/components/ui";

/**
 * Whether this browser holds a session. Reads the non-httpOnly ap_csrf cookie, which the API sets and clears together
 * with the session cookies, so public pages stay static and cost no API call. It is a display hint only: if the
 * session has expired, the dashboard's own API call sends the visitor to sign in.
 * null during server rendering and hydration (the server cannot know), then true/false.
 */
export function useHasSession(): boolean | null {
  return useSyncExternalStore(
    () => () => {},
    () => document.cookie.split("; ").some((c) => c.startsWith("ap_csrf=")),
    () => null,
  );
}

/** Header buttons: Dashboard when signed in, otherwise Sign in + Start free. */
export function HeaderActions() {
  const signedIn = useHasSession();
  if (signedIn === null) return <div className="h-10 w-40" aria-hidden />; // same footprint, no flash of the wrong buttons
  if (signedIn) {
    return (
      <ButtonLink href="/dashboard">
        <LayoutDashboard className="h-4 w-4" aria-hidden /> Dashboard
      </ButtonLink>
    );
  }
  return (
    <div className="flex items-center gap-2">
      <ButtonLink href="/login" variant="ghost">Sign in</ButtonLink>
      <ButtonLink href="/register">Start free</ButtonLink>
    </div>
  );
}

/** A call to action that sends signed-in visitors to the dashboard instead of the sign-up page. */
export function SessionCta({ signedOut, signedOutHref }: { signedOut: ReactNode; signedOutHref: string }) {
  const signedIn = useHasSession();
  return signedIn ? (
    <ButtonLink href="/dashboard">Go to your dashboard</ButtonLink>
  ) : (
    <ButtonLink href={signedOutHref}>{signedOut}</ButtonLink>
  );
}
