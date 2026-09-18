import type { Metadata } from "next";

import { Logo } from "@/components/site-chrome";

export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main id="main" className="flex min-h-screen flex-col items-center justify-center px-4 py-12">
      <div className="mb-8"><Logo /></div>
      <div className="w-full max-w-md rounded-card border border-border bg-surface p-6 sm:p-8">{children}</div>
      <p className="mt-6 max-w-md text-center text-xs text-muted">
        18+ only. Predictions are probabilities, not guarantees.
      </p>
    </main>
  );
}
