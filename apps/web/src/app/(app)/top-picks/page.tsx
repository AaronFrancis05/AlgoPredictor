"use client";

import { useQuery } from "@tanstack/react-query";

import { Disclaimer, PickCard } from "@/components/picks";
import { EmptyState, PageHeader, Spinner } from "@/components/ui";
import { ErrorPanel } from "@/components/upgrade";
import { api } from "@/lib/api";
import { isoDate } from "@/lib/format";
import { useMe } from "@/lib/hooks";
import { PicksDay } from "@/lib/schemas";

export default function TopPicks() {
  const me = useMe();
  const q = useQuery({ queryKey: ["top", isoDate()], queryFn: () => api(`/picks/top?date=${isoDate()}&n=10`, PicksDay) });
  return (
    <>
      <PageHeader title="Daily top 10" subtitle="The ten picks the model is most confident about today, highest first." />
      {q.isLoading ? <Spinner /> : null}
      {q.error ? <ErrorPanel error={q.error} /> : null}
      {q.data && q.data.picks.length === 0 ? (
        <EmptyState title="No picks published for today yet" />
      ) : null}
      {q.data && q.data.picks.length > 0 ? (
        <div className="space-y-6">
          <ol className="grid gap-4 md:grid-cols-2">
            {q.data.picks.map((p, i) => (
              <li key={p.prediction_id} className="relative">
                <span className="absolute -left-2 -top-2 z-10 grid h-7 w-7 place-items-center rounded-sm bg-brand text-xs font-bold text-brand-fg">
                  {i + 1}
                </span>
                <PickCard pick={p} showValue={Boolean(me.data?.entitlements.value_flags)} />
              </li>
            ))}
          </ol>
          <p className="text-xs text-muted">
            &quot;Most confident&quot; is not &quot;certain&quot;: in testing, Strong picks won {Math.round((q.data.tier_hit_rates.Strong ?? 0) * 100)}% of the time.
          </p>
          <Disclaimer text={q.data.disclaimer} />
        </div>
      ) : null}
    </>
  );
}
