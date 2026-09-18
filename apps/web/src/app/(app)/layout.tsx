import type { Metadata } from "next";

import { Prefetched } from "@/lib/prefetch";
import { User } from "@/lib/schemas";

import { AppShell } from "./app-shell";

// Signed-in pages are private: never indexed, never cached by shared caches.
export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function AppLayout({ children }: { children: React.ReactNode }) {
  // the shell waits for /me before showing a page: prefetching it removes that wait from the first paint
  return (
    <Prefetched queries={[{ key: ["me"], path: "/me", schema: User }]}>
      <AppShell>{children}</AppShell>
    </Prefetched>
  );
}
