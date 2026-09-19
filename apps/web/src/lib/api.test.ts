import { describe, expect, it, vi } from "vitest";

import { refreshWithRetry, type RefreshOutcome } from "./api";

function attempts(...outcomes: RefreshOutcome[]) {
  const fn = vi.fn<() => Promise<RefreshOutcome>>();
  for (const o of outcomes) fn.mockResolvedValueOnce(o);
  return fn;
}

const noWait = () => Promise.resolve();

describe("refreshWithRetry", () => {
  it("does not retry a success or a refusal", async () => {
    for (const outcome of ["ok", "signed_out"] as const) {
      const attempt = attempts(outcome);
      expect(await refreshWithRetry(attempt, noWait)).toBe(outcome);
      expect(attempt).toHaveBeenCalledTimes(1);
    }
  });

  it("retries once when the server did not answer", async () => {
    const attempt = attempts("unavailable", "ok");
    expect(await refreshWithRetry(attempt, noWait)).toBe("ok");
    expect(attempt).toHaveBeenCalledTimes(2);
  });

  it("reports unavailable, not signed out, when the retry also fails", async () => {
    const attempt = attempts("unavailable", "unavailable");
    expect(await refreshWithRetry(attempt, noWait)).toBe("unavailable");
    expect(attempt).toHaveBeenCalledTimes(2);
  });
});
