import { describe, expect, it } from "vitest";

import { changeMessage, freshUnread, matchSignature, safeLink } from "./notify";
import { Pick } from "./schemas";

const base = Pick.parse({
  prediction_id: "p1", kickoff_date: "2026-09-19", kickoff_time: "15:00", kickoff_at: "2026-09-19T14:00:00Z",
  league_code: "E0", home_team: "Arsenal", away_team: "Chelsea", pick: "home", confidence: 0.6, tier: "Medium",
  tier_hit_rate: 0.57, p_home: 0.6, p_draw: 0.25, p_away: 0.15, fair_odds: 1.67, odds: 1.8, edge: null,
  value_flag: null, locked: false, is_demo: false, model_version: "v", phase: "live",
  live: { status: "1H", elapsed: 10, home_goals: 0, away_goals: 0, updated_at: null },
});
const at = (status: string, h: number, a: number, phase = "live") =>
  Pick.parse({ ...base, phase, live: { status, elapsed: 50, home_goals: h, away_goals: a, updated_at: null } });

describe("freshUnread", () => {
  it("returns each new unread item once, oldest first", () => {
    const seen = new Set(["a"]);
    const items = [{ id: "c", read: false }, { id: "b", read: false }, { id: "x", read: true }, { id: "a", read: false }];
    expect(freshUnread(seen, items).map((i) => i.id)).toEqual(["b", "c"]);
    expect(freshUnread(seen, items)).toEqual([]);
  });
});

describe("safeLink", () => {
  it("only allows paths on this site", () => {
    expect(safeLink("/account/plans")).toBe("/account/plans");
    expect(safeLink("//evil.example")).toBeNull();
    expect(safeLink("https://evil.example")).toBeNull();
    expect(safeLink(null)).toBeNull();
  });
});

describe("changeMessage", () => {
  it("stays quiet on first sight and when nothing changed", () => {
    expect(changeMessage(undefined, base)).toBeNull();
    expect(changeMessage(matchSignature(base), base)).toBeNull();
    expect(changeMessage(matchSignature(base), at("HT", 0, 0))).toBeNull();
  });

  it("announces goals and full time", () => {
    expect(changeMessage(matchSignature(base), at("1H", 1, 0))).toBe("Goal: Arsenal 1-0 Chelsea");
    expect(changeMessage(matchSignature(at("2H", 1, 0)), at("FT", 1, 0, "finished"))).toBe("Full time: Arsenal 1-0 Chelsea");
  });

  it("announces a match called off", () => {
    expect(changeMessage(matchSignature(base), at("PST", 0, 0, "postponed"))).toBe("Arsenal v Chelsea: postponed");
  });
});
