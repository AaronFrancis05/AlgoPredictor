import { Check, Lock } from "lucide-react";

import { Badge, Card } from "@/components/ui";
import { cn, kickoff, kickoffTime, localDay, odds, pct, pickLabel, prob } from "@/lib/format";
import type { Pick } from "@/lib/schemas";
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

export function PickCard({ pick, showValue = false, day }: { pick: Pick; showValue?: boolean; day?: string }) {
  const settled = pick.result != null;
  return (
    <Card className="relative flex flex-col overflow-hidden p-0">
      {!pick.locked && tierBar[pick.tier] ? (
        <span aria-hidden className={cn("absolute inset-y-0 left-0 w-[3px]", tierBar[pick.tier])} />
      ) : null}
      <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-2.5 text-xs text-muted">
        <p className="flex min-w-0 items-center gap-2">
          <span className="num font-semibold text-fg"><KickoffTime iso={pick.kickoff_at} day={day} /></span>
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
          <h3 className="truncate text-base font-semibold">
            {pick.home_team} <span className="font-normal text-muted">v</span> {pick.away_team}
          </h3>
          {pick.locked ? (
            <p className="mt-2 flex items-center gap-2 text-sm text-muted">
              <Lock className="h-4 w-4" aria-hidden /> Upgrade or check back closer to kick-off to see this pick.
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
      {(showValue && pick.value_flag) || settled ? (
        <div className="flex flex-wrap items-center gap-2 border-t border-border px-5 py-2.5">
          {showValue && pick.value_flag ? (
            <Badge className="border-brand/50 bg-brand/15 text-brand">
              VALUE · edge {pick.edge != null ? `${(pick.edge * 100).toFixed(1)}%` : "n/a"}
            </Badge>
          ) : null}
          {settled ? <ResultTag pick={pick} /> : null}
        </div>
      ) : null}
    </Card>
  );
}

function ResultTag({ pick }: { pick: Pick }) {
  if (pick.result == null) return null;
  return (
    <span className={cn("text-xs font-semibold", pick.correct ? "text-brand" : pick.correct === false ? "text-danger" : "text-muted")}>
      Result: {pick.result}
      {pick.correct != null ? ` · ${pick.correct ? "correct" : "missed"}` : ""}
    </span>
  );
}

/** Every pick of a day as one table: the densest view, and the easiest to scan by kick-off. */
export function PicksTable({ picks, showValue, day }: { picks: Pick[]; showValue: boolean; day?: string }) {
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
            <th scope="col" className="px-4 py-2.5 font-medium">Result</th>
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
              <td className="px-4 py-2.5"><ResultTag pick={p} /></td>
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
