import { describe, expect, it } from "vitest";

import { todayIn } from "./format";
import { liveRefetchDelay } from "./hooks";

describe("todayIn", () => {
  // 00:57 on 19 September in Kampala is still 18 September in UTC (the bug seen on the dashboard)
  const now = new Date("2026-09-18T21:57:00Z");

  it("uses the viewer's time zone", () => {
    expect(todayIn("Africa/Kampala", now)).toBe("2026-09-19");
    expect(todayIn("Europe/London", now)).toBe("2026-09-18");
  });

  it("falls back to UTC for a missing or invalid zone", () => {
    expect(todayIn(undefined, now)).toBe("2026-09-18");
    expect(todayIn("Not/AZone", now)).toBe("2026-09-18");
  });
});

describe("liveRefetchDelay", () => {
  const now = Date.parse("2026-09-19T15:00:00Z");

  it("refetches just after the announced update", () => {
    expect(liveRefetchDelay("2026-09-19T15:04:00Z", now)).toBe(4 * 60_000 + 3_000);
  });

  it("never polls faster than 15 s or slower than 5 min", () => {
    expect(liveRefetchDelay("2026-09-19T14:59:00Z", now)).toBe(15_000);
    expect(liveRefetchDelay("2026-09-19T18:00:00Z", now)).toBe(5 * 60_000);
  });

  it("falls back to two minutes without a usable hint", () => {
    expect(liveRefetchDelay(null, now)).toBe(120_000);
    expect(liveRefetchDelay("not a date", now)).toBe(120_000);
  });
});
