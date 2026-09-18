import { describe, expect, it } from "vitest";

import { Pick } from "./schemas";
import { candidates, legProblem, slipTotals } from "./slip";

const now = Date.parse("2026-09-19T10:00:00Z");
const mk = (id: string, o: Partial<Record<string, unknown>> = {}) => Pick.parse({
  prediction_id: id, kickoff_date: "2026-09-19", kickoff_time: "15:00", kickoff_at: "2026-09-19T14:00:00Z",
  league_code: "E0", home_team: `H${id}`, away_team: `A${id}`, pick: "home", confidence: 0.6, tier: "Medium",
  tier_hit_rate: 0.57, p_home: 0.6, p_draw: 0.25, p_away: 0.15, fair_odds: 1.67, odds: 1.8, edge: null,
  value_flag: null, locked: false, is_demo: false, model_version: "v", ...o,
});

describe("slip rules", () => {
  it("applies the server's leg rules", () => {
    expect(legProblem(mk("a"), [], now)).toBeNull();
    expect(legProblem(mk("a", { odds: 1.1 }), [], now)).toMatch(/Odds outside/);
    expect(legProblem(mk("a", { odds: 2.6 }), [], now)).toMatch(/Odds outside/);
    expect(legProblem(mk("a", { kickoff_at: "2026-09-19T09:00:00Z" }), [], now)).toBe("Already kicked off");
    expect(legProblem(mk("a", { locked: true, pick: null, confidence: null }), [], now)).toBe("Locked on your plan");
    // a second pick on the same match (same date and teams) is refused
    expect(legProblem(mk("b", { home_team: "Ha", away_team: "Aa" }), [mk("a")], now)).toMatch(/this match/);
    const six = ["1", "2", "3", "4", "5", "6"].map((i) => mk(i));
    expect(legProblem(mk("7"), six, now)).toBe("At most 6 legs");
  });

  it("multiplies odds and probabilities", () => {
    const t = slipTotals([mk("a", { odds: 2, confidence: 0.5 }), mk("b", { odds: 1.5, confidence: 0.8 })]);
    expect(t).toEqual({ odds: 3, probability: 0.4, expectedValue: expect.closeTo(0.2, 10) });
    expect(slipTotals([])).toBeNull();
  });

  it("offers eligible picks, most likely first", () => {
    const pool = [mk("a", { confidence: 0.55 }), mk("b", { confidence: 0.7 }), mk("c", { odds: 3 })];
    expect(candidates(pool, [mk("a")], now).map((p) => p.prediction_id)).toEqual(["b"]);
  });
});
