import { describe, expect, it } from "vitest";

import { matchClock, onCourse, phaseAt } from "./match";
import { Pick } from "./schemas";

const KICKOFF = Date.parse("2026-09-19T14:00:00Z");

// what the API deployed before this change sends: no phase / live / outcome fields
const legacy = {
  prediction_id: "p1", kickoff_date: "2026-09-19", kickoff_time: "15:00", kickoff_at: "2026-09-19T14:00:00+00:00",
  league_code: "E0", home_team: "Arsenal", away_team: "Chelsea", pick: "home", confidence: 0.61, tier: "Medium",
  tier_hit_rate: 0.57, p_home: 0.61, p_draw: 0.22, p_away: 0.17, fair_odds: 1.64, odds: 1.7, edge: null,
  value_flag: null, locked: false, is_demo: false, model_version: "v1", result: null, correct: null,
};

describe("match phases", () => {
  it("parses responses from an API without the new fields", () => {
    const p = Pick.parse(legacy);
    expect(p.phase).toBe("upcoming");
    expect(p.live).toBeNull();
    expect(p.outcome).toBeNull();
  });

  it("moves an upcoming pick to live at kick-off, then to awaiting result", () => {
    const p = Pick.parse(legacy);
    expect(phaseAt(p, KICKOFF - 60_000)).toBe("upcoming");
    expect(phaseAt(p, KICKOFF + 60_000)).toBe("live");
    expect(phaseAt(p, KICKOFF + 3 * 3_600_000)).toBe("awaiting_result");
    // the server's phase wins once it is past upcoming
    expect(phaseAt(Pick.parse({ ...legacy, phase: "finished" }), KICKOFF - 60_000)).toBe("finished");
    // no published kick-off time: left to the server
    expect(phaseAt(Pick.parse({ ...legacy, kickoff_time: "" }), KICKOFF + 60_000)).toBe("upcoming");
  });

  it("shows the minute, HT, FT and whether the pick is winning", () => {
    const live = (status: string, elapsed: number | null, h: number, a: number) =>
      Pick.parse({ ...legacy, phase: "live", live: { status, elapsed, home_goals: h, away_goals: a, updated_at: null } });
    expect(matchClock(live("2H", 63, 1, 0), "live")).toBe("63'");
    expect(matchClock(live("HT", 45, 0, 0), "live")).toBe("HT");
    expect(matchClock(live("FT", 90, 2, 1), "finished")).toBe("FT");
    expect(matchClock(Pick.parse(legacy), "postponed")).toBe("Postponed");
    expect(onCourse(live("2H", 63, 1, 0))).toBe(true);
    expect(onCourse(live("2H", 63, 1, 1))).toBe(false);
    expect(onCourse(Pick.parse(legacy))).toBeNull();
  });
});
