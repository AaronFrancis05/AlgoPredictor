"use client";

import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, ChevronLeft, ChevronRight, History as HistoryIcon, LayoutGrid, Lock, Rows3 } from "lucide-react";
import Link from "next/link";
import { type ReactNode, useEffect, useMemo, useState, useSyncExternalStore } from "react";

import {
  Disclaimer, KickoffTime, leagueName, LiveDot, LockedList, PickCard, PicksTable,
} from "@/components/picks";
import { Button, ButtonLink, Card, EmptyState, Segmented, Select, Skeleton } from "@/components/ui";
import { ErrorPanel } from "@/components/upgrade";
import { api } from "@/lib/api";
import { cn, isoDate } from "@/lib/format";
import { useMe, useNow } from "@/lib/hooks";
import { phaseAt } from "@/lib/match";
import { type Entitlements, type Pick, PicksDay } from "@/lib/schemas";

type Sort = "kickoff" | "confidence";
type View = "cards" | "table";
const VIEW_KEY = "ap.dashboard.view";

function shift(day: string, n: number) {
  const d = new Date(`${day}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return isoDate(d);
}

const dayDate = (day: string) => new Date(`${day}T12:00:00Z`);

function relativeName(day: string): string {
  const today = isoDate();
  if (day === today) return "Today";
  if (day === shift(today, 1)) return "Tomorrow";
  if (day === shift(today, -1)) return "Yesterday";
  return new Intl.DateTimeFormat(undefined, { weekday: "long", timeZone: "UTC" }).format(dayDate(day));
}

// Cards or table, remembered per browser. Storage can be unavailable (private mode): then it lasts the visit.
let memoryView: View | null = null;
const viewListeners = new Set<() => void>();

function readView(): View {
  if (memoryView) return memoryView;
  try {
    return localStorage.getItem(VIEW_KEY) === "table" ? "table" : "cards";
  } catch {
    return "cards";
  }
}

function useView(): [View, (v: View) => void] {
  const view = useSyncExternalStore(
    (cb) => { viewListeners.add(cb); return () => { viewListeners.delete(cb); }; },
    readView,
    () => "cards" as View,
  );
  const set = (v: View) => {
    memoryView = v;
    try { localStorage.setItem(VIEW_KEY, v); } catch {}
    viewListeners.forEach((l) => l());
  };
  return [view, set];
}

const picksQuery = (day: string) => ({
  queryKey: ["picks", day],
  queryFn: () => api(`/picks?date=${day}`, PicksDay),
  staleTime: 60_000, // matches the API's Cache-Control max-age
});

function DayStrip({ day, onPick }: { day: string; onPick: (d: string) => void }) {
  const today = isoDate();
  const days = Array.from({ length: 7 }, (_, i) => shift(day, i - 3));
  const fmt = (d: string, o: Intl.DateTimeFormatOptions) =>
    new Intl.DateTimeFormat(undefined, { ...o, timeZone: "UTC" }).format(dayDate(d));
  return (
    <div className="flex items-stretch gap-2">
      <Button variant="secondary" className="px-2.5" aria-label="Previous day" onClick={() => onPick(shift(day, -1))}>
        <ChevronLeft className="h-4 w-4" />
      </Button>
      <ol className="grid flex-1 grid-cols-5 overflow-hidden rounded-md border border-border bg-surface sm:grid-cols-7">
        {days.map((d, i) => {
          const selected = d === day;
          const outer = i === 0 || i === days.length - 1; // five days fit a phone, seven from sm up
          return (
            <li key={d} className={cn("border-l border-border", i === 1 && "border-l-0 sm:border-l",
                                      i === 0 && "border-l-0", outer && "hidden sm:block")}>
              <button type="button" onClick={() => onPick(d)} aria-current={selected ? "date" : undefined}
                      className={cn("relative flex h-full w-full flex-col items-center gap-0.5 py-2 text-xs transition-colors",
                        selected ? "bg-surface-2 text-fg" : "text-muted hover:bg-surface-2/60 hover:text-fg")}>
                <span className="uppercase tracking-wide">{fmt(d, { weekday: "short" })}</span>
                <span className={cn("num text-base", selected ? "font-bold" : "font-medium")}>{fmt(d, { day: "numeric" })}</span>
                {d === today ? <span className="text-[10px] font-semibold text-brand">Today</span> : <span className="text-[10px]">&nbsp;</span>}
                {selected ? <span aria-hidden className="absolute inset-x-0 bottom-0 h-0.5 bg-brand" /> : null}
              </button>
            </li>
          );
        })}
      </ol>
      <Button variant="secondary" className="px-2.5" aria-label="Next day" onClick={() => onPick(shift(day, 1))}>
        <ChevronRight className="h-4 w-4" />
      </Button>
    </div>
  );
}

function Summary({ data, day, parts }: { data: PicksDay; day: string; parts: Parts }) {
  const next = [...parts.upcoming].sort((a, b) => a.kickoff_at.localeCompare(b.kickoff_at))[0];
  const cells: { label: string; value: ReactNode; hint?: string }[] = [
    { label: "Published", value: data.total_published },
    { label: "Still to play", value: parts.upcoming.length },
    {
      label: "Live now",
      value: parts.live.length ? (
        <span className="inline-flex items-center gap-2 text-danger"><LiveDot />{parts.live.length}</span>
      ) : 0,
    },
    { label: "Finished", value: parts.done.length, hint: "Played matches move to History" },
    { label: "Next kick-off", value: next ? <KickoffTime iso={next.kickoff_at} day={day} /> : "n/a" },
  ];
  return (
    <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-card border border-border bg-border sm:grid-cols-5">
      {cells.map((c) => (
        <div key={c.label} title={c.hint} className="bg-surface px-4 py-3 last:col-span-2 sm:last:col-span-1">
          <dt className="text-xs text-muted">{c.label}</dt>
          <dd className="num mt-1 text-xl font-semibold">{c.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function planRule(e: Entitlements | undefined): string {
  if (!e || (e.picks_per_day == null && e.reveal_hours_before_kickoff == null)) return "";
  const parts = [];
  if (e.picks_per_day != null) parts.push(`the ${e.picks_per_day} most confident picks of the day`);
  if (e.reveal_hours_before_kickoff != null) parts.push(`each shown ${e.reveal_hours_before_kickoff} hours before kick-off`);
  return `Your plan shows ${parts.join(", ")}.`;
}

function UpgradeStrip({ data, entitlements }: { data: PicksDay; entitlements?: Entitlements }) {
  return (
    <div className="flex flex-col gap-3 rounded-card border border-border bg-surface px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-sm bg-surface-2">
          <Lock className="h-4 w-4 text-muted" aria-hidden />
        </span>
        <div>
          <p className="text-sm font-semibold">
            {data.hidden_count} of {data.total_published} picks are locked on the <span className="capitalize">{data.plan}</span> plan.
          </p>
          <p className="text-xs text-muted">{planRule(entitlements) || "Upgrade to see every pick for the day."}</p>
        </div>
      </div>
      <ButtonLink href="/account/plans" className="shrink-0">Unlock all picks</ButtonLink>
    </div>
  );
}

function LoadingGrid() {
  return (
    <div className="space-y-6" aria-busy aria-label="Loading picks">
      <Skeleton className="h-[74px] w-full" />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-60 w-full" />)}
      </div>
    </div>
  );
}

type Parts = { upcoming: Pick[]; live: Pick[]; done: Pick[] };

function split(picks: Pick[], now: number): Parts {
  const parts: Parts = { upcoming: [], live: [], done: [] };
  for (const p of picks) {
    const ph = phaseAt(p, now);
    (ph === "upcoming" ? parts.upcoming : ph === "live" ? parts.live : parts.done).push(p);
  }
  return parts;
}

function LiveStrip({ picks, now, day, showValue }: { picks: Pick[]; now: number; day: string; showValue: boolean }) {
  return (
    <section className="space-y-3" aria-labelledby="live-now">
      <div className="flex items-center justify-between gap-3">
        <h2 id="live-now" className="flex items-center gap-2 text-sm font-semibold">
          <LiveDot /> Live now <span className="num font-normal text-muted">{picks.length}</span>
        </h2>
        <Link href="/live" className="inline-flex items-center gap-1 text-xs font-semibold text-brand hover:underline">
          Live centre <ArrowRight className="h-3.5 w-3.5" aria-hidden />
        </Link>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {picks.map((p) => <PickCard key={p.prediction_id} pick={p} showValue={showValue} day={day} now={now} />)}
      </div>
    </section>
  );
}

function FinishedNote({ count, day }: { count: number; day: string }) {
  return (
    <div className="flex flex-col gap-3 rounded-card border border-border bg-surface px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-sm bg-surface-2">
          <HistoryIcon className="h-4 w-4 text-muted" aria-hidden />
        </span>
        <div>
          <p className="text-sm font-semibold">
            {count} {count === 1 ? "match" : "matches"} on this day {count === 1 ? "has" : "have"} been played.
          </p>
          <p className="text-xs text-muted">Scores, results and whether each pick won are in History.</p>
        </div>
      </div>
      <ButtonLink href={`/history?from=${day}&to=${day}`} variant="secondary" className="shrink-0">View results</ButtonLink>
    </div>
  );
}

function sortPicks(picks: Pick[], sort: Sort): Pick[] {
  const out = [...picks];
  if (sort === "confidence") out.sort((a, b) => (b.confidence ?? -1) - (a.confidence ?? -1));
  else out.sort((a, b) => a.kickoff_at.localeCompare(b.kickoff_at));
  return out;
}

export default function Dashboard() {
  const [day, setDay] = useState(isoDate());
  const [league, setLeague] = useState("all");
  const [sort, setSort] = useState<Sort>("kickoff");
  const me = useMe();
  const qc = useQueryClient();
  // today's list refreshes each minute so scores and phases stay current while the page is open
  const q = useQuery({ ...picksQuery(day), placeholderData: keepPreviousData,
                       refetchInterval: day === isoDate() ? 60_000 : false });

  const [view, setView] = useView();
  const now = useNow(30_000);

  // warm the neighbouring days so the arrows feel instant
  useEffect(() => {
    if (!q.isSuccess) return;
    void qc.prefetchQuery(picksQuery(shift(day, 1)));
    void qc.prefetchQuery(picksQuery(shift(day, -1)));
  }, [q.isSuccess, day, qc]);

  const selectDay = (d: string) => { setDay(d); setLeague("all"); };
  const data = q.data;
  const showValue = Boolean(me.data?.entitlements.value_flags);
  const leagues = useMemo(
    () => [...new Set((data?.picks ?? []).map((p) => p.league_code))].sort((a, b) => leagueName(a).localeCompare(leagueName(b))),
    [data],
  );
  const parts = useMemo(() => {
    const all = (data?.picks ?? []).filter((p) => league === "all" || p.league_code === league);
    return split(sortPicks(all, sort), now);
  }, [data, league, sort, now]);
  const filtered = parts.upcoming;
  const open = filtered.filter((p) => !p.locked);
  const locked = filtered.filter((p) => p.locked);
  const allParts = useMemo(() => split(data?.picks ?? [], now), [data, now]);
  const fullDate = new Intl.DateTimeFormat(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })
    .format(dayDate(day));
  const updating = q.isFetching && q.isPlaceholderData;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-muted">Daily picks</p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">{relativeName(day)}</h1>
          <p className="mt-1 text-sm text-muted">
            {fullDate}. Kick-off times are in your time zone.
            {updating ? <span className="ml-2 text-xs" role="status">Updating…</span> : null}
          </p>
        </div>
        <div className="flex items-center gap-2 lg:w-[30rem]">
          <div className="flex-1"><DayStrip day={day} onPick={selectDay} /></div>
          {day !== isoDate() ? <Button variant="secondary" onClick={() => selectDay(isoDate())}>Today</Button> : null}
        </div>
      </div>

      {q.isLoading ? <LoadingGrid /> : null}
      {q.error && !data ? <ErrorPanel error={q.error} /> : null}

      {data ? (
        data.picks.length === 0 ? (
          <EmptyState title="No picks published for this day yet">
            Picks are published before kick-off once fixtures and odds are available. Try another day above.
          </EmptyState>
        ) : (
          <div className={cn("space-y-6 transition-opacity", updating && "opacity-60")}>
            <Summary data={data} day={day} parts={allParts} />
            {data.hidden_count > 0 && allParts.upcoming.length > 0 ? (
              <UpgradeStrip data={data} entitlements={me.data?.entitlements} />
            ) : null}
            {parts.live.length > 0 ? <LiveStrip picks={parts.live} now={now} day={day} showValue={showValue} /> : null}

            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-3">
              <div className="flex flex-wrap items-center gap-2">
                <label htmlFor="league" className="sr-only">League</label>
                <Select id="league" value={league} onChange={(e) => setLeague(e.target.value)}>
                  <option value="all">All leagues ({data.picks.length})</option>
                  {leagues.map((l) => (
                    <option key={l} value={l}>
                      {leagueName(l)} ({data.picks.filter((p) => p.league_code === l).length})
                    </option>
                  ))}
                </Select>
                <Segmented<Sort> label="Sort by" value={sort} onChange={setSort}
                                 options={[{ value: "kickoff", label: "Kick-off" }, { value: "confidence", label: "Confidence" }]} />
              </div>
              <Segmented<View> label="View" value={view} onChange={setView} options={[
                { value: "cards", label: <><LayoutGrid className="h-3.5 w-3.5" aria-hidden />Cards</> },
                { value: "table", label: <><Rows3 className="h-3.5 w-3.5" aria-hidden />Table</> },
              ]} />
            </div>

            {filtered.length === 0 ? null : view === "table" ? (
              <PicksTable picks={filtered} showValue={showValue} day={day} now={now} />
            ) : (
              <>
                {open.length > 0 ? (
                  <section className="space-y-3" aria-labelledby="open-picks">
                    <h2 id="open-picks" className="text-sm font-semibold">
                      Still to play <span className="num font-normal text-muted">{open.length}</span>
                    </h2>
                    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                      {open.map((p) => <PickCard key={p.prediction_id} pick={p} showValue={showValue} day={day} now={now} />)}
                    </div>
                  </section>
                ) : null}
                {locked.length > 0 ? (
                  <section className="space-y-3" aria-labelledby="locked-picks">
                    <h2 id="locked-picks" className="text-sm font-semibold">
                      Locked on your plan <span className="num font-normal text-muted">{locked.length}</span>
                    </h2>
                    <LockedList picks={locked} day={day} />
                  </section>
                ) : null}
              </>
            )}
            {filtered.length === 0 ? (
              <Card className="text-sm text-muted">
                {parts.live.length + parts.done.length > 0
                  ? "Every match on this day has kicked off. Nothing left to play."
                  : "No picks in this league for the day."}
              </Card>
            ) : null}
            {parts.done.length > 0 ? <FinishedNote count={parts.done.length} day={day} /> : null}
            <Disclaimer text={data.disclaimer} />
          </div>
        )
      ) : null}
    </div>
  );
}
