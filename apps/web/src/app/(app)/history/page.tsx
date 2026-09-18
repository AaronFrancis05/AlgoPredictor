"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo } from "react";

import { Disclaimer, leagueName, MatchList } from "@/components/picks";
import { Button, EmptyState, PageHeader, Segmented, Select, Skeleton } from "@/components/ui";
import { ErrorPanel } from "@/components/upgrade";
import { api } from "@/lib/api";
import { cn, isoDate, localDay, pct, today } from "@/lib/format";
import { useNow } from "@/lib/hooks";
import { History, type Pick } from "@/lib/schemas";

const RANGES = [
  { value: "7", label: "7 days" },
  { value: "30", label: "30 days" },
  { value: "90", label: "90 days" },
] as const;
type Outcome = "all" | "won" | "lost" | "pending";
const PAGE_SIZE = 50;

/** n days before the viewer's local today. */
function daysAgo(n: number) {
  const d = new Date(`${today()}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() - n);
  return isoDate(d);
}

function dayHeading(day: string) {
  return new Intl.DateTimeFormat(undefined, { weekday: "long", day: "numeric", month: "long" })
    .format(new Date(`${day}T12:00:00`));
}

function groupByDay(picks: Pick[]): [string, Pick[]][] {
  const groups = new Map<string, Pick[]>();
  for (const p of picks) {
    const d = localDay(p.kickoff_at);
    groups.set(d, [...(groups.get(d) ?? []), p]);
  }
  return [...groups.entries()];
}

function Stats({ data }: { data: History }) {
  const s = data.summary;
  const cells = [
    { label: "Played", value: s.matches },
    { label: "Won", value: s.won, tone: "text-brand" },
    { label: "Lost", value: s.lost, tone: "text-danger" },
    { label: "Hit rate", value: pct(s.hit_rate, 1), hint: "Won ÷ (won + lost)" },
    { label: "Awaiting result", value: s.pending + (s.void ? ` · ${s.void} void` : "") },
  ];
  return (
    <div className="space-y-3">
      <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-card border border-border bg-border sm:grid-cols-5">
        {cells.map((c) => (
          <div key={c.label} title={c.hint} className="bg-surface px-4 py-3 last:col-span-2 sm:last:col-span-1">
            <dt className="text-xs text-muted">{c.label}</dt>
            <dd className={cn("num mt-1 text-xl font-semibold", c.tone)}>{c.value}</dd>
          </div>
        ))}
      </dl>
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted">
        {data.by_tier.map((t) => (
          <span key={t.tier}>
            {t.tier}: <span className="num font-semibold text-fg">{t.won}/{t.settled}</span>
            {t.hit_rate != null ? ` (${pct(t.hit_rate, 0)})` : ""}
          </span>
        ))}
        {s.provisional > 0 ? (
          <span>{s.provisional} result{s.provisional === 1 ? "" : "s"} provisional (live full-time score, not yet graded)</span>
        ) : null}
      </div>
    </div>
  );
}

function HistoryView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const now = useNow(60_000);

  const range = params.get("range") ?? "7";
  const from = params.get("from") ?? daysAgo(Number(range) - 1);
  const to = params.get("to") ?? today();
  const league = params.get("league") ?? "";
  const tier = params.get("tier") ?? "";
  const outcome = (params.get("outcome") ?? "all") as Outcome;
  const page = Math.max(1, Number(params.get("page") ?? "1") || 1);
  const singleDay = params.has("from") && from === to;

  const set = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(changes)) {
      if (v == null || v === "") next.delete(k);
      else next.set(k, v);
    }
    if (!("page" in changes)) next.delete("page");
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  };

  const query = useMemo(() => {
    const qs = new URLSearchParams({ date_from: from, date_to: to, page: String(page), page_size: String(PAGE_SIZE) });
    if (league) qs.set("league", league);
    if (tier) qs.set("tier", tier);
    if (outcome !== "all") qs.set("outcome", outcome);
    return qs.toString();
  }, [from, to, page, league, tier, outcome]);

  const q = useQuery({
    queryKey: ["history", query],
    queryFn: () => api(`/picks/history?${query}`, History),
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });
  const data = q.data;
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <>
      <PageHeader
        title="History"
        subtitle={singleDay
          ? `Played matches on ${dayHeading(from)}.`
          : "Every played match with its score and whether the pick won."}
      />
      <div className="mb-6 flex flex-wrap items-center gap-2 border-b border-border pb-3">
        {singleDay ? (
          <Button variant="secondary" className="px-2.5 py-1.5 text-xs" onClick={() => set({ from: null, to: null })}>
            Show last 7 days
          </Button>
        ) : (
          <Segmented label="Period" value={range as (typeof RANGES)[number]["value"]} options={[...RANGES]}
                     onChange={(v) => set({ range: v === "7" ? null : v, from: null, to: null })} />
        )}
        <label htmlFor="h-league" className="sr-only">League</label>
        <Select id="h-league" value={league} onChange={(e) => set({ league: e.target.value })}>
          <option value="">All leagues</option>
          {(data?.leagues ?? []).map((l) => <option key={l} value={l}>{leagueName(l)}</option>)}
        </Select>
        <label htmlFor="h-tier" className="sr-only">Tier</label>
        <Select id="h-tier" value={tier} onChange={(e) => set({ tier: e.target.value })}>
          <option value="">All tiers</option>
          <option value="Strong">Strong</option>
          <option value="Medium">Medium</option>
          <option value="Lean">Lean</option>
        </Select>
        <Segmented<Outcome> label="Outcome" value={outcome} onChange={(v) => set({ outcome: v === "all" ? null : v })}
                            options={[{ value: "all", label: "All" }, { value: "won", label: "Won" },
                                      { value: "lost", label: "Lost" }, { value: "pending", label: "Pending" }]} />
      </div>

      {q.isLoading ? (
        <div className="space-y-4" aria-busy aria-label="Loading history">
          <Skeleton className="h-[74px] w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : null}
      {q.error && !data ? <ErrorPanel error={q.error} /> : null}
      {data ? (
        <div className={cn("space-y-8 transition-opacity", q.isFetching && q.isPlaceholderData && "opacity-60")}>
          <Stats data={data} />
          {data.picks.length === 0 ? (
            <EmptyState title="No played matches match these filters">
              Matches appear here after kick-off plus about two hours, or as soon as the live feed reports full time.
            </EmptyState>
          ) : (
            groupByDay(data.picks).map(([day, picks]) => (
              <section key={day} className="space-y-3" aria-labelledby={`d-${day}`}>
                <h2 id={`d-${day}`} className="text-sm font-semibold">
                  {dayHeading(day)} <span className="num font-normal text-muted">{picks.length}</span>
                </h2>
                <MatchList picks={picks} now={now} day={day} />
              </section>
            ))
          )}
          {pages > 1 ? (
            <nav aria-label="Pages" className="flex items-center justify-between gap-3">
              <Button variant="secondary" disabled={page <= 1} onClick={() => set({ page: String(page - 1) })}>
                <ChevronLeft className="h-4 w-4" aria-hidden /> Newer
              </Button>
              <span className="num text-xs text-muted">Page {page} of {pages}</span>
              <Button variant="secondary" disabled={page >= pages} onClick={() => set({ page: String(page + 1) })}>
                Older <ChevronRight className="h-4 w-4" aria-hidden />
              </Button>
            </nav>
          ) : null}
          <Disclaimer text={data.disclaimer} />
        </div>
      ) : null}
    </>
  );
}

export default function HistoryPage() {
  return (
    <Suspense fallback={<Skeleton className="h-64 w-full" />}>
      <HistoryView />
    </Suspense>
  );
}
