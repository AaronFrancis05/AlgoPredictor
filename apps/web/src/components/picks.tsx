import { Check, Lock, X } from "lucide-react";

import { Badge, Card } from "@/components/ui";
import { cn, kickoff, kickoffTime, localDay, odds, pct, pickLabel, prob } from "@/lib/format";
import { hasScore, matchClock, onCourse, phaseAt } from "@/lib/match";
import type { MatchPhase, Pick } from "@/lib/schemas";
import { leagueNames } from "@/lib/site";

const tierStyle: Record<string, string> = {
  Strong: "border-strong/50 bg-strong/15 text-strong",
  Medium: "border-medium/50 bg-medium/15 text-medium",
  Lean: "border-lean/50 bg-lean/15 text-lean",
  locked: "border-border text-muted",
};

const tierBar: Record<string, string> = { Strong: "bg-strong", Medium: "bg-medium", Lean: "bg-lean" };

export const leagueName = (code: string) => leagueNames[code] ?? code;

export function TierBadge({ tier, hitRate }: { tier: string; hitRate?: number | null }) {
  return (
    <Badge
      className={tierStyle[tier] ?? tierStyle.locked}
      title={hitRate != null ? `${tier}: ${pct(hitRate)} of past picks in this tier won` : undefined}
    >
      {tier === "locked" ? "Locked" : tier}
    </Badge>
  );
}

/** Kick-off as a time when it falls on `day` in the viewer's zone, otherwise with its date. */
export function KickoffTime({ iso, day }: { iso: string; day?: string }) {
  return <time dateTime={iso}>{day && localDay(iso) === day ? kickoffTime(iso) : kickoff(iso)}</time>;
}

export function LiveDot({ className }: { className?: string }) {
  return (
    <span aria-hidden className={cn("relative inline-flex h-2 w-2", className)}>
      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-danger opacity-60" />
      <span className="relative inline-flex h-2 w-2 rounded-full bg-danger" />
    </span>
  );
}

/** Clock for a match that has kicked off: pulsing dot + minute while in play, FT / Postponed / pending after. */
export function MatchClock({ pick, phase }: { pick: Pick; phase: MatchPhase }) {
  const text = matchClock(pick, phase);
  if (phase === "live") {
    return (
      <span className="inline-flex items-center gap-1.5 font-semibold text-danger">
        <LiveDot />
        <span className="num">{text}</span>
        <span className="sr-only">in play</span>
      </span>
    );
  }
  return <span className={cn("num font-semibold", phase === "finished" ? "text-fg" : "text-muted")}>{text}</span>;
}

export function Score({ pick, className }: { pick: Pick; className?: string }) {
  if (!hasScore(pick)) return null;
  return (
    <span className={cn("num font-bold tabular-nums", className)} aria-label={`Score ${pick.live!.home_goals} to ${pick.live!.away_goals}`}>
      {pick.live!.home_goals}<span className="px-1 text-muted">-</span>{pick.live!.away_goals}
    </span>
  );
}

/** Won / lost for a played match; "provisional" while the result comes from the live feed, not the grading. */
export function OutcomeBadge({ pick }: { pick: Pick }) {
  if (pick.outcome == null) return null;
  const won = pick.outcome === "won";
  return (
    <span className="inline-flex items-center gap-1.5">
      <Badge className={won ? "border-brand/50 bg-brand/15 text-brand" : "border-danger/50 bg-danger/10 text-danger"}>
        {won ? <Check className="mr-1 h-3 w-3" aria-hidden /> : <X className="mr-1 h-3 w-3" aria-hidden />}
        {won ? "Won" : "Lost"}
      </Badge>
      {!pick.outcome_official ? (
        <span className="text-[11px] text-muted" title="From the live full-time score. Confirmed when the result is graded.">
          provisional
        </span>
      ) : null}
    </span>
  );
}

/** While in play: is the pick currently winning? */
export function CourseTag({ pick }: { pick: Pick }) {
  const c = onCourse(pick);
  if (c == null) return null;
  return (
    <span className={cn("whitespace-nowrap text-xs font-semibold", c ? "text-brand" : "text-warn")}>
      <span className="hidden sm:inline">{c ? "Pick winning now" : "Pick not winning now"}</span>
      <span className="sm:hidden">{c ? "Winning" : "Not winning"}</span>
    </span>
  );
}

/** Home / draw / away probabilities as three labelled rows, the picked outcome highlighted. */
export function OutcomeLadder({ pick }: { pick: Pick }) {
  if (pick.p_home == null || pick.p_draw == null || pick.p_away == null) return null;
  const rows = [
    { key: "home", label: pick.home_team, v: pick.p_home },
    { key: "draw", label: "Draw", v: pick.p_draw },
    { key: "away", label: pick.away_team, v: pick.p_away },
  ] as const;
  return (
    <dl className="space-y-1.5">
      {rows.map((r) => {
        const picked = pick.pick === r.key;
        return (
          <div key={r.key} className="grid grid-cols-[minmax(0,7.5rem)_1fr_3.25rem] items-center gap-3 text-xs">
            <dt className={cn("flex min-w-0 items-center gap-1", picked ? "font-semibold text-fg" : "text-muted")}>
              <span className="truncate">{r.label}</span>
              {picked ? <Check className="h-3.5 w-3.5 shrink-0" aria-label="picked" /> : null}
            </dt>
            <div className="h-1.5 bg-surface-2" aria-hidden>
              <div className={cn("h-full", picked ? tierBar[pick.tier] ?? "bg-accent" : "bg-border")}
                   style={{ width: `${r.v * 100}%` }} />
            </div>
            <dd className={cn("num text-right", picked ? "font-semibold text-fg" : "text-muted")}>{prob(r.v)}</dd>
          </div>
        );
      })}
    </dl>
  );
}

export function PickCard({ pick, showValue = false, day, now }: {
  pick: Pick; showValue?: boolean; day?: string; now?: number;
}) {
  const phase = now != null ? phaseAt(pick, now) : pick.phase;
  const started = phase !== "upcoming";
  return (
    <Card className="relative flex flex-col overflow-hidden p-0">
      {!pick.locked && tierBar[pick.tier] ? (
        <span aria-hidden className={cn("absolute inset-y-0 left-0 w-[3px]", tierBar[pick.tier])} />
      ) : null}
      <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-2.5 text-xs text-muted">
        <p className="flex min-w-0 items-center gap-2">
          {started ? <MatchClock pick={pick} phase={phase} /> : (
            <span className="num font-semibold text-fg"><KickoffTime iso={pick.kickoff_at} day={day} /></span>
          )}
          <span aria-hidden>·</span>
          <span className="truncate">{leagueName(pick.league_code)}</span>
        </p>
        <div className="flex shrink-0 items-center gap-1">
          {pick.is_demo ? <Badge className="border-warn/50 text-warn">Demo data</Badge> : null}
          <TierBadge tier={pick.tier} hitRate={pick.tier_hit_rate} />
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-4 px-5 py-4">
        <div className="min-w-0">
          <div className="flex items-start justify-between gap-3">
            <h3 className="min-w-0 truncate text-base font-semibold">
              {pick.home_team} <span className="font-normal text-muted">v</span> {pick.away_team}
            </h3>
            {started ? <Score pick={pick} className="shrink-0 text-lg leading-6" /> : null}
          </div>
          {pick.locked ? (
            <p className="mt-2 flex items-center gap-2 text-sm text-muted">
              <Lock className="h-4 w-4" aria-hidden />
              {started ? "Locked on your plan. Shown once the result is in." : "Upgrade or check back closer to kick-off to see this pick."}
            </p>
          ) : (
            <p className="mt-1 text-sm">
              <span className="mr-1.5 text-xs uppercase tracking-wide text-muted">Pick</span>
              <strong>{pickLabel(pick.pick, pick.home_team, pick.away_team)}</strong>
            </p>
          )}
        </div>
        {!pick.locked ? <OutcomeLadder pick={pick} /> : null}
      </div>

      {!pick.locked ? (
        <dl className="grid grid-cols-3 divide-x divide-border border-t border-border bg-surface-2/40 text-xs">
          <div className="px-5 py-2.5">
            <dt className="text-muted">Fair odds</dt>
            <dd className="num font-medium">{odds(pick.fair_odds)}</dd>
          </div>
          <div className="px-4 py-2.5">
            <dt className="text-muted">Market odds</dt>
            <dd className="num font-medium">{odds(pick.odds)}</dd>
          </div>
          <div className="px-4 py-2.5">
            <dt className="text-muted">Tier hit rate</dt>
            <dd className="num font-medium">{pct(pick.tier_hit_rate, 0)}</dd>
          </div>
        </dl>
      ) : null}
      {(showValue && pick.value_flag) || pick.outcome || (phase === "live" && onCourse(pick) != null) ? (
        <div className="flex flex-wrap items-center gap-2 border-t border-border px-5 py-2.5">
          {showValue && pick.value_flag ? (
            <Badge className="border-brand/50 bg-brand/15 text-brand">
              VALUE · edge {pick.edge != null ? `${(pick.edge * 100).toFixed(1)}%` : "n/a"}
            </Badge>
          ) : null}
          {pick.outcome ? <OutcomeBadge pick={pick} /> : phase === "live" ? <CourseTag pick={pick} /> : null}
        </div>
      ) : null}
    </Card>
  );
}

/**
 * One match as a dense row: clock or kick-off, teams with the score, the pick, and how it stands. Used for live
 * strips, history and the started part of the top 10.
 */
export function MatchRow({ pick, now, day, showDate = false }: { pick: Pick; now: number; day?: string; showDate?: boolean }) {
  const phase = phaseAt(pick, now);
  const started = phase !== "upcoming";
  return (
    // fixed side columns: each row is its own grid, so auto widths would not line up from row to row
    <li className="grid grid-cols-[4.75rem_minmax(0,1fr)_auto] items-center gap-3 bg-surface px-4 py-3 sm:grid-cols-[5.5rem_minmax(0,1fr)_13rem_10rem]">
      <div className="text-xs">
        {started && !showDate ? <MatchClock pick={pick} phase={phase} /> : (
          <span className="num font-semibold"><KickoffTime iso={pick.kickoff_at} day={showDate ? undefined : day} /></span>
        )}
        {showDate ? <div className="mt-0.5"><MatchClock pick={pick} phase={phase} /></div> : null}
      </div>
      <div className="min-w-0">
        <p className="flex items-center gap-2 text-sm font-medium">
          <span className="truncate">{pick.home_team} <span className="text-muted">v</span> {pick.away_team}</span>
          {started ? <Score pick={pick} className="shrink-0" /> : null}
        </p>
        <p className="truncate text-xs text-muted">
          {leagueName(pick.league_code)}
          <span className="sm:hidden"> · {pick.locked ? "Locked" : pickLabel(pick.pick, pick.home_team, pick.away_team)}</span>
        </p>
      </div>
      <div className="hidden min-w-0 text-sm sm:block">
        {pick.locked ? (
          <span className="inline-flex items-center gap-1.5 text-xs text-muted"><Lock className="h-3.5 w-3.5" aria-hidden /> Locked</span>
        ) : (
          <>
            <p className="truncate font-medium">{pickLabel(pick.pick, pick.home_team, pick.away_team)}</p>
            <p className="num text-xs text-muted">{prob(pick.confidence)} · {pick.tier}</p>
          </>
        )}
      </div>
      <div className="flex justify-end">
        {pick.outcome ? <OutcomeBadge pick={pick} /> : phase === "live" ? <CourseTag pick={pick} /> : pick.locked ? null : <TierBadge tier={pick.tier} />}
      </div>
    </li>
  );
}

export function MatchList({ picks, now, day, showDate }: { picks: Pick[]; now: number; day?: string; showDate?: boolean }) {
  return (
    <ul className="divide-y divide-border overflow-hidden rounded-card border border-border">
      {picks.map((p) => <MatchRow key={p.prediction_id} pick={p} now={now} day={day} showDate={showDate} />)}
    </ul>
  );
}

function ResultCell({ pick, now }: { pick: Pick; now?: number }) {
  const phase = now != null ? phaseAt(pick, now) : pick.phase;
  if (phase === "upcoming") return null;
  return (
    <span className="inline-flex flex-wrap items-center gap-2 text-xs">
      <MatchClock pick={pick} phase={phase} />
      <Score pick={pick} />
      <OutcomeBadge pick={pick} />
    </span>
  );
}

/** Every pick of a day as one table: the densest view, and the easiest to scan by kick-off. */
export function PicksTable({ picks, showValue, day, now }: { picks: Pick[]; showValue: boolean; day?: string; now?: number }) {
  return (
    <div className="overflow-x-auto rounded-card border border-border bg-surface">
      <table className="w-full min-w-[760px] text-sm">
        <thead className="border-b border-border text-left text-xs text-muted">
          <tr>
            <th scope="col" className="px-4 py-2.5 font-medium">Kick-off</th>
            <th scope="col" className="px-4 py-2.5 font-medium">Match</th>
            <th scope="col" className="px-4 py-2.5 font-medium">Pick</th>
            <th scope="col" className="px-4 py-2.5 text-right font-medium">Prob.</th>
            <th scope="col" className="px-4 py-2.5 font-medium">Tier</th>
            <th scope="col" className="px-4 py-2.5 text-right font-medium">Fair</th>
            <th scope="col" className="px-4 py-2.5 text-right font-medium">Market</th>
            {showValue ? <th scope="col" className="px-4 py-2.5 text-right font-medium">Edge</th> : null}
            <th scope="col" className="px-4 py-2.5 font-medium">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {picks.map((p) => (
            <tr key={p.prediction_id} className="hover:bg-surface-2/50">
              <td className="num whitespace-nowrap px-4 py-2.5 text-xs"><KickoffTime iso={p.kickoff_at} day={day} /></td>
              <td className="px-4 py-2.5">
                <p className="font-medium">{p.home_team} <span className="text-muted">v</span> {p.away_team}</p>
                <p className="text-xs text-muted">{leagueName(p.league_code)}</p>
              </td>
              {p.locked ? (
                <td colSpan={showValue ? 6 : 5} className="px-4 py-2.5 text-xs text-muted">
                  <span className="inline-flex items-center gap-1.5"><Lock className="h-3.5 w-3.5" aria-hidden /> Locked on your plan</span>
                </td>
              ) : (
                <>
                  <td className="px-4 py-2.5 font-medium">{pickLabel(p.pick, p.home_team, p.away_team)}</td>
                  <td className="num px-4 py-2.5 text-right font-semibold">{prob(p.confidence)}</td>
                  <td className="px-4 py-2.5"><TierBadge tier={p.tier} hitRate={p.tier_hit_rate} /></td>
                  <td className="num px-4 py-2.5 text-right">{odds(p.fair_odds)}</td>
                  <td className="num px-4 py-2.5 text-right">{odds(p.odds)}</td>
                  {showValue ? (
                    <td className={cn("num px-4 py-2.5 text-right", p.value_flag && "font-semibold text-brand")}>
                      {p.edge != null ? `${(p.edge * 100).toFixed(1)}%` : "n/a"}
                    </td>
                  ) : null}
                </>
              )}
              <td className="px-4 py-2.5"><ResultCell pick={p} now={now} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Locked fixtures as one compact list instead of a wall of identical cards. */
export function LockedList({ picks, day }: { picks: Pick[]; day?: string }) {
  return (
    <ul className="grid gap-px overflow-hidden rounded-card border border-border bg-border lg:grid-cols-2">
      {picks.map((p) => (
        <li key={p.prediction_id}
            className="grid grid-cols-[4.5rem_minmax(0,1fr)_auto] items-center gap-3 bg-surface px-4 py-2.5 lg:last:odd:col-span-2">
          <span className="num text-xs font-semibold"><KickoffTime iso={p.kickoff_at} day={day} /></span>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{p.home_team} <span className="text-muted">v</span> {p.away_team}</p>
            <p className="truncate text-xs text-muted">{leagueName(p.league_code)}</p>
          </div>
          <Lock className="h-4 w-4 text-muted" aria-label="Locked" />
        </li>
      ))}
    </ul>
  );
}

export function Disclaimer({ text }: { text?: string }) {
  return (
    <p className="text-xs leading-relaxed text-muted">
      {text ??
        "Predictions are model probabilities, not certainties. Even the Strong tier loses about one match in four in historical testing. 18+ only."}{" "}
      Please gamble responsibly. If you need support,{" "}
      <a className="underline" href="/responsible-gambling">
        get help
      </a>
      .
    </p>
  );
}
