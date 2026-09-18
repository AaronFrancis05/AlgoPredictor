"use client";

import { Star } from "lucide-react";

import { cn } from "@/lib/format";
import { useFollows } from "@/lib/follows";
import type { Pick } from "@/lib/schemas";

/** Star to follow one match. Renders nothing outside the signed-in area. */
export function FollowButton({ pick, className }: { pick: Pick; className?: string }) {
  const f = useFollows();
  if (!f) return null;
  const direct = f.matches.has(pick.prediction_id);
  const viaLeague = !direct && f.leagues.has(pick.league_code);
  const label = direct ? `Stop following ${pick.home_team} v ${pick.away_team}`
    : viaLeague ? "Followed through its league" : `Follow ${pick.home_team} v ${pick.away_team}`;
  return (
    <button type="button" aria-pressed={direct} aria-label={label} title={label}
            onClick={() => f.toggle("match", pick.prediction_id)}
            className={cn("grid h-7 w-7 shrink-0 place-items-center rounded-sm text-muted hover:bg-surface-2 hover:text-fg",
                          className)}>
      <Star className={cn("h-4 w-4", (direct || viaLeague) && "text-warn", direct && "fill-current")} aria-hidden />
    </button>
  );
}

/** Follow / unfollow a whole league (shown next to the league filter). */
export function FollowLeagueButton({ code, name }: { code: string; name: string }) {
  const f = useFollows();
  if (!f) return null;
  const on = f.leagues.has(code);
  return (
    <button type="button" aria-pressed={on} onClick={() => f.toggle("league", code)}
            className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs hover:bg-surface-2">
      <Star className={cn("h-3.5 w-3.5", on && "fill-current text-warn")} aria-hidden />
      {on ? `Following ${name}` : `Follow ${name}`}
    </button>
  );
}
