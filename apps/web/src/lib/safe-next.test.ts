import { describe, expect, it } from "vitest";

import { safeNextPath } from "./safe-next";

describe("safeNextPath", () => {
  it.each([
    ["/dashboard", "/dashboard"],
    ["/history?league=E0&page=2", "/history?league=E0&page=2"],
    ["/account#sign-in", "/account#sign-in"],
    ["/a/../top-picks", "/top-picks"],
  ])("keeps the site path %s", (raw, expected) => {
    expect(safeNextPath(raw)).toBe(expected);
  });

  it.each([
    "//evil.example",
    "/\\evil.example",
    "/\\/evil.example",
    "/\t/evil.example",
    "/\n/evil.example",
    "https://evil.example/dashboard",
    "javascript:alert(1)",
    "dashboard",
    "",
  ])("refuses %j", (raw) => {
    expect(safeNextPath(raw)).toBe("/dashboard");
  });

  it("refuses non-strings and uses the given fallback", () => {
    expect(safeNextPath(["/dashboard"], "/live")).toBe("/live");
    expect(safeNextPath(undefined)).toBe("/dashboard");
  });
});
