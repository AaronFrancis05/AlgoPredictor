import { Skeleton } from "@/components/ui";

/**
 * Placeholder shown by the loading.tsx boundaries while a page renders on the server. Every page is dynamic (per
 * request CSP nonce), so without a boundary Next cannot prefetch a route and a click waits for the whole render.
 */
export function PageLoading({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-4" aria-busy aria-live="polite">
      <span className="sr-only">Loading</span>
      <Skeleton className="h-8 w-56" />
      <Skeleton className="h-4 w-80 max-w-full" />
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} className="h-24 w-full" />)}
    </div>
  );
}
