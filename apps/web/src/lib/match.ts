/**
 * Match phase on the client. The API sends each pick's phase; this re-checks it against the viewer's clock so a card
 * leaves "upcoming" the moment its kick-off passes, without waiting for the next refetch.
 */
import type { MatchPhase, Pick } from "@/lib/schemas";

/** Same fallback as the API (MATCH_LIVE_MINUTES): without a feed a match counts as in play this long. */
const LIVE_MINUTES = 115;

export const HISTORY_PHASES: ReadonlySet<MatchPhase> = new Set(["finished", "awaiting_result", "postponed", "cancelled", "abandoned"]);

export function phaseAt(p: Pick, now: number): MatchPhase {
  if (p.phase !== "upcoming" || !p.kickoff_time) return p.phase;
  const k = Date.parse(p.kickoff_at);
  if (now < k) return "upcoming";
  return now < k + LIVE_MINUTES * 60_000 ? "live" : "awaiting_result";
}

const CALLED_OFF: Partial<Record<MatchPhase, string>> = {
  postponed: "Postponed", cancelled: "Cancelled", abandoned: "Abandoned",
};

/** Short status for a match that has kicked off: 63', HT, FT, Live, Postponed, Result pending. */
export function matchClock(p: Pick, phase: MatchPhase): string {
  if (CALLED_OFF[phase]) return CALLED_OFF[phase]!;
  const s = p.live?.status ?? "";
  if (phase === "finished") return s === "AET" ? "AET" : s === "PEN" ? "Pens" : "FT";
  if (phase === "awaiting_result") return "Result pending";
  if (s === "HT") return "HT";
  if (s === "BT") return "Break";
  if (s === "P") return "Pens";
  if (s === "SUSP" || s === "INT") return "Stopped";
  if (p.live?.elapsed != null) return `${p.live.elapsed}'`;
  return "Live";
}

export function hasScore(p: Pick): boolean {
  return p.live?.home_goals != null && p.live?.away_goals != null;
}

/** Would the pick win if the match ended now? null when there is no score or the pick is locked. */
export function onCourse(p: Pick): boolean | null {
  if (!p.pick || !hasScore(p)) return null;
  const h = p.live!.home_goals!, a = p.live!.away_goals!;
  const side = h > a ? "home" : a > h ? "away" : "draw";
  return side === p.pick;
}
