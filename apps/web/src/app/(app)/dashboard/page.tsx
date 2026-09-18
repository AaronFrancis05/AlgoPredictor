"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";

import { Disclaimer, PickCard } from "@/components/picks";
import { Button, ButtonLink, EmptyState, PageHeader, Spinner } from "@/components/ui";
import { ErrorPanel } from "@/components/upgrade";
import { api } from "@/lib/api";
import { isoDate } from "@/lib/format";
import { useMe } from "@/lib/hooks";
import { PicksDay } from "@/lib/schemas";

function shift(day: string, n: number) {
  const d = new Date(`${day}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return isoDate(d);
}

export default function Dashboard() {
  const [day, setDay] = useState(isoDate());
  const me = useMe();
  const q = useQuery({ queryKey: ["picks", day], queryFn: () => api(`/picks?date=${day}`, PicksDay) });
  const label = new Intl.DateTimeFormat(undefined, { weekday: "long", day: "numeric", month: "long" }).format(
    new Date(`${day}T12:00:00Z`),
  );

  return (
    <>
      <PageHeader
        title="Today's picks"
        subtitle={label}
        action={
          <div className="flex gap-2">
            <Button variant="secondary" aria-label="Previous day" onClick={() => setDay((d) => shift(d, -1))}><ChevronLeft className="h-4 w-4" /></Button>
            <Button variant="secondary" onClick={() => setDay(isoDate())}>Today</Button>
            <Button variant="secondary" aria-label="Next day" onClick={() => setDay((d) => shift(d, 1))}><ChevronRight className="h-4 w-4" /></Button>
          </div>
        }
      />
      {q.isLoading ? <Spinner label="Loading picks" /> : null}
      {q.error ? <ErrorPanel error={q.error} /> : null}
      {q.data ? (
        q.data.picks.length === 0 ? (
          <EmptyState title="No picks published for this day yet">
            Picks are published before kick-off once fixtures and odds are available.
          </EmptyState>
        ) : (
          <div className="space-y-6">
            {q.data.hidden_count > 0 ? (
              <div className="flex flex-col items-start justify-between gap-3 rounded-card border border-border bg-surface p-4 sm:flex-row sm:items-center">
                <p className="text-sm">
                  {q.data.hidden_count} of {q.data.total_published} picks are locked on the {q.data.plan} plan.
                </p>
                <ButtonLink href="/pricing">Unlock all picks</ButtonLink>
              </div>
            ) : null}
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {q.data.picks.map((p) => (
                <PickCard key={p.prediction_id} pick={p} showValue={Boolean(me.data?.entitlements.value_flags)} />
              ))}
            </div>
            <Disclaimer text={q.data.disclaimer} />
          </div>
        )
      ) : null}
    </>
  );
}
