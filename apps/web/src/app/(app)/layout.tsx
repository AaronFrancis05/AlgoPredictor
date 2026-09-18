import type { Metadata } from "next";

import { AppShell } from "./app-shell";

// Signed-in pages are private: never indexed, never cached by shared caches.
export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
