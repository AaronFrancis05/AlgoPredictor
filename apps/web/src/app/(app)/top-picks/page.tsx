"use client";

import { useQuery } from "@tanstack/react-query";

import { Disclaimer, MatchList, PickCard } from "@/components/picks";
import { EmptyState, PageHeader, Spinner } from "@/components/ui";
import { ErrorPanel } from "@/components/upgrade";
import { api } from "@/lib/api";
import { isoDate } from "@/lib/format";
import { useMe, useNow } from "@/lib/hooks";
import { phaseAt } from "@/lib/match";
import { PicksDay } from "@/lib/schemas";

export default function TopPicks() {
  const me = useMe();
  const now = useNow(30_000);
  const day = isoDate();
  const q = useQuery({ queryKey: ["top", day], queryFn: () => api(`/picks/top?date=${day}&n=10`, PicksDay),
                       refetchInterval: 60_000 });
  const ranked = (q.data?.picks ?? []).map((p, i) => ({ p, rank: i + 1 }));
  // the day's ten stay fixed; a pick leaves the cards at kick-off and is followed in the list below
  const upcoming = ranked.filter(({ p }) => phaseAt(p, now) === "upcoming");
  const started = ranked.filter(({ p }) => phaseAt(p, now) !== "upcoming");
  return (
    <>
      <PageHeader title="Daily top 10" subtitle="The ten picks the model is most confident about today, highest first." />
      {q.isLoading ? <Spinner /> : null}
      {q.error ? <ErrorPanel error={q.error} /> : null}
      {q.data && q.data.picks.length === 0 ? (
        <EmptyState title="No picks published for today yet" />
      ) : null}
      {q.data && q.data.picks.length > 0 ? (
        <div className="space-y-8">
          {upcoming.length > 0 ? (
            <ol className="grid gap-4 md:grid-cols-2">
              {upcoming.map(({ p, rank }) => (
                <li key={p.prediction_id} className="relative">
                  <span className="absolute -left-2 -top-2 z-10 grid h-7 w-7 place-items-center rounded-sm bg-brand text-xs font-bold text-brand-fg">
                    {rank}
                  </span>
                  <PickCard pick={p} showValue={Boolean(me.data?.entitlements.value_flags)} now={now} />
                </li>
              ))}
            </ol>
          ) : (
            <EmptyState title="All of today's top picks have kicked off">Follow them below, or see tomorrow&apos;s on Today.</EmptyState>
          )}
          {started.length > 0 ? (
            <section className="space-y-3" aria-labelledby="started">
              <h2 id="started" className="text-sm font-semibold">
                Already kicked off <span className="num font-normal text-muted">{started.length}</span>
              </h2>
              <MatchList picks={started.map(({ p }) => p)} now={now} day={day} />
            </section>
          ) : null}
          <p className="text-xs text-muted">
            &quot;Most confident&quot; is not &quot;certain&quot;: in testing, Strong picks won {Math.round((q.data.tier_hit_rates.Strong ?? 0) * 100)}% of the time.
          </p>
          <Disclaimer text={q.data.disclaimer} />
        </div>
      ) : null}
    </>
  );
}
