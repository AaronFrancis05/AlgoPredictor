"use client";

import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";

import { Disclaimer, LiveDot, MatchList } from "@/components/picks";
import { EmptyState, PageHeader, Skeleton } from "@/components/ui";
import { ErrorPanel } from "@/components/upgrade";
import { api } from "@/lib/api";
import { useNow } from "@/lib/hooks";
import { phaseAt } from "@/lib/match";
import { LivePicks } from "@/lib/schemas";

const REFRESH_MS = 30_000;

export default function LivePage() {
  const now = useNow(15_000);
  const q = useQuery({
    queryKey: ["live"],
    queryFn: () => api("/picks/live", LivePicks),
    refetchInterval: REFRESH_MS,
    refetchIntervalInBackground: false,
  });
  // a match can reach full time between refreshes: keep only what is still in play by the viewer's clock too
  const live = useMemo(() => (q.data?.picks ?? []).filter((p) => phaseAt(p, now) === "live"), [q.data, now]);
  const updated = q.dataUpdatedAt
    ? new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(q.dataUpdatedAt)
    : null;

  return (
    <>
      <PageHeader
        title="Live"
        subtitle="Matches with a published pick that are in play now. Finished matches move to History."
        action={updated ? (
          <p className="inline-flex items-center gap-1.5 text-xs text-muted" role="status" aria-live="polite">
            <RefreshCw className={q.isFetching ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} aria-hidden />
            Updated {updated} · refreshes every 30 s
          </p>
        ) : null}
      />
      {q.isLoading ? (
        <div className="space-y-px" aria-busy aria-label="Loading live matches">
          {Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-14 w-full" />)}
        </div>
      ) : null}
      {q.error && !q.data ? <ErrorPanel error={q.error} /> : null}
      {q.data ? (
        <div className="space-y-8">
          {!q.data.feed ? (
            <p className="rounded-card border border-border bg-surface px-4 py-3 text-xs text-muted">
              Live scores are not switched on yet, so matches show as in play from kick-off until the final whistle
              without a score. Results appear in History once graded.
            </p>
          ) : null}
          {live.length === 0 ? (
            <EmptyState title="No matches in play right now">
              Upcoming picks are on <Link className="underline" href="/dashboard">Today</Link>, and played matches with their
              results are in <Link className="underline" href="/history">History</Link>.
            </EmptyState>
          ) : (
            <section className="space-y-3" aria-labelledby="in-play">
              <h2 id="in-play" className="flex items-center gap-2 text-sm font-semibold">
                <LiveDot /> In play <span className="num font-normal text-muted">{live.length}</span>
              </h2>
              <MatchList picks={live} now={now} />
            </section>
          )}
          <p className="text-xs text-muted">
            Live scores are for information and can lag the match by a minute or two. A pick counts as won or lost only
            on the official result.
          </p>
          <Disclaimer text={q.data.disclaimer} />
        </div>
      ) : null}
    </>
  );
}
