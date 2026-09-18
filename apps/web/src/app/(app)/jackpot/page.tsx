"use client";

import { useQuery } from "@tanstack/react-query";

import { Disclaimer, PickCard } from "@/components/picks";
import { Alert, Card, PageHeader, Spinner } from "@/components/ui";
import { ErrorPanel } from "@/components/upgrade";
import { api } from "@/lib/api";
import { pct, today } from "@/lib/format";
import { useNow } from "@/lib/hooks";
import { Jackpot, type Pick } from "@/lib/schemas";

/** "Won ✓" / "Lost" once the day's legs are decided (either leg losing settles it). */
function DayTally({ legs }: { legs: Pick[] }) {
  if (!legs.length) return null;
  if (legs.some((l) => l.outcome === "lost")) return <span className="mr-2 font-semibold text-danger">Day lost ·</span>;
  if (legs.every((l) => l.outcome === "won")) return <span className="mr-2 font-semibold text-brand">Day won ✓ ·</span>;
  return null;
}

export default function JackpotPage() {
  const now = useNow(30_000);
  const day = today(); // the viewer's date, so the week turns over at their midnight
  const q = useQuery({ queryKey: ["jackpot", day], queryFn: () => api(`/jackpot?week_of=${day}`, Jackpot),
                       refetchInterval: 60_000 });
  const fmt = (d: string) =>
    new Intl.DateTimeFormat(undefined, { weekday: "long", day: "numeric", month: "short", timeZone: "UTC" })
      .format(new Date(`${d}T12:00:00Z`));

  return (
    <>
      <PageHeader title="Weekly jackpot" subtitle="The two highest-confidence picks for every day of this week." />
      {q.isLoading ? <Spinner /> : null}
      {q.error ? <ErrorPanel error={q.error} /> : null}
      {q.data ? (
        <div className="space-y-8">
          <Card className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-xs text-muted">Week starting</p>
              <p className="text-lg font-bold">{fmt(q.data.week_start)}</p>
            </div>
            <div className="text-right">
              <p className="text-xs text-muted">Chance all 14 picks win (model)</p>
              <p className="text-lg font-bold tabular-nums">{pct(q.data.week_combined_probability, 3)}</p>
            </div>
          </Card>
          <Alert>{q.data.note}</Alert>
          {q.data.days.map((d) => (
            <section key={d.date} aria-labelledby={`day-${d.date}`} className="space-y-3">
              <div className="flex items-baseline justify-between">
                <h2 id={`day-${d.date}`} className="text-lg font-semibold">{fmt(d.date)}</h2>
                <p className="text-sm text-muted"><DayTally legs={d.legs} /> Both win: {pct(d.combined_probability)}</p>
              </div>
              {d.legs.length ? (
                <div className="grid gap-4 md:grid-cols-2">
                  {d.legs.map((p) => <PickCard key={p.prediction_id} pick={p} showValue now={now} />)}
                </div>
              ) : (
                <Card className="text-sm text-muted">No picks published for this day yet.</Card>
              )}
            </section>
          ))}
          <Disclaimer />
        </div>
      ) : null}
    </>
  );
}
