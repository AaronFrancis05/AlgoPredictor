import { describe, expect, it } from "vitest";

import { formatPrice, pickLabel } from "./format";
import { LoginForm, Pick, RegisterForm, SlipForm } from "./schemas";

describe("form schemas", () => {
  it("rejects weak passwords and missing age confirmation", () => {
    const r = RegisterForm.safeParse({ email: "a@b.co", password: "weakpassword", confirm_age_18: false, accept_terms: true });
    expect(r.success).toBe(false);
    const paths = r.success ? [] : r.error.issues.map((i) => i.path[0]);
    expect(paths).toContain("password");
    expect(paths).toContain("confirm_age_18");
  });

  it("accepts a valid registration", () => {
    const r = RegisterForm.safeParse({ email: " a@b.co ", password: "Str0ng-password!", confirm_age_18: true, accept_terms: true });
    expect(r.success).toBe(true);
    expect(r.success && r.data.email).toBe("a@b.co");
  });

  it("coerces and bounds slip inputs", () => {
    expect(SlipForm.safeParse({ target_odds: "10", min_legs: "2", max_legs: "5", days_ahead: "3" }).success).toBe(true);
    expect(SlipForm.safeParse({ target_odds: "1.1", min_legs: 2, max_legs: 5, days_ahead: 3 }).success).toBe(false);
    expect(SlipForm.safeParse({ target_odds: 10, min_legs: 5, max_legs: 3, days_ahead: 3 }).success).toBe(false);
  });

  it("requires email and password to sign in", () => {
    expect(LoginForm.safeParse({ email: "nope", password: "" }).success).toBe(false);
  });
});

describe("API response schemas", () => {
  it("parses a locked pick and rejects a malformed one", () => {
    const locked = {
      prediction_id: "x1", kickoff_date: "2026-09-19", kickoff_time: "15:00", kickoff_at: "2026-09-19T14:00:00Z",
      league_code: "E0", home_team: "A", away_team: "B", pick: null, confidence: null, tier: "locked",
      tier_hit_rate: null, p_home: null, p_draw: null, p_away: null, fair_odds: null, odds: null, edge: null,
      value_flag: null, locked: true, is_demo: false, model_version: "v1",
    };
    expect(Pick.safeParse(locked).success).toBe(true);
    expect(Pick.safeParse({ ...locked, pick: "win" }).success).toBe(false);
  });
});

describe("formatting", () => {
  it("formats zero-decimal and cent currencies", () => {
    expect(formatPrice(37000, "UGX", "en-US")).toContain("37,000");
    expect(formatPrice(999, "USD", "en-US")).toBe("$9.99");
  });

  it("labels picks", () => {
    expect(pickLabel("home", "Arsenal", "Everton")).toBe("Arsenal to win");
    expect(pickLabel("draw", "A", "B")).toBe("Draw");
  });
});
