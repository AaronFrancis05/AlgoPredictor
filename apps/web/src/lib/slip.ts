/**
 * Editing a slip in the browser. Same leg rules as the API's slip builder (apps/api/app/services/products.py):
 * odds 1.20-2.50, not yet kicked off, one leg per match. Combined probability multiplies the model's leg
 * probabilities, which assumes the matches are independent.
 */
import type { Pick } from "@/lib/schemas";

export const ODDS_MIN = 1.2;
export const ODDS_MAX = 2.5;
export const MAX_LEGS = 6;

const matchOf = (p: Pick) => `${p.kickoff_date}|${p.home_team}|${p.away_team}`;

/** Why a pick cannot be added to `legs` (null when it can). */
export function legProblem(p: Pick, legs: Pick[], now: number): string | null {
  if (p.locked || p.pick == null || p.confidence == null) return "Locked on your plan";
  if (p.odds == null || p.odds < ODDS_MIN || p.odds > ODDS_MAX) return `Odds outside ${ODDS_MIN.toFixed(2)}-${ODDS_MAX.toFixed(2)}`;
  if (Date.parse(p.kickoff_at) <= now) return "Already kicked off";
  if (legs.some((l) => l.prediction_id === p.prediction_id)) return "Already on the slip";
  if (legs.some((l) => matchOf(l) === matchOf(p))) return "Another leg is from this match";
  if (legs.length >= MAX_LEGS) return `At most ${MAX_LEGS} legs`;
  return null;
}

export type SlipTotals = { odds: number; probability: number; expectedValue: number } | null;

/** Combined odds, model probability and expected value (null for an empty slip). */
export function slipTotals(legs: Pick[]): SlipTotals {
  if (!legs.length) return null;
  const odds = legs.reduce((a, l) => a * (l.odds ?? 1), 1);
  const probability = legs.reduce((a, l) => a * (l.confidence ?? 0), 1);
  return { odds: Math.round(odds * 100) / 100, probability, expectedValue: probability * odds - 1 };
}

/** Picks that could be added, highest model probability first. */
export function candidates(pool: Pick[], legs: Pick[], now: number): Pick[] {
  return pool.filter((p) => legProblem(p, legs, now) == null)
    .sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0));
}
