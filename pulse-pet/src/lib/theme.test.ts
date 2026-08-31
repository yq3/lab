import { describe, expect, it } from "vitest";
import { parseThemePreference, resolveTheme } from "./theme";

describe("resolveTheme（TC-UI-02-1）", () => {
  it("auto 跟随系统：系统深 → dark；系统浅 → light", () => {
    expect(resolveTheme("auto", true)).toBe("dark");
    expect(resolveTheme("auto", false)).toBe("light");
  });

  it("手动选择 > 系统偏好（light/dark 覆盖系统深浅）", () => {
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("light", false)).toBe("light");
    expect(resolveTheme("dark", true)).toBe("dark");
    expect(resolveTheme("dark", false)).toBe("dark");
  });
});

describe("parseThemePreference", () => {
  it("合法值直通；非法/空 → null（回退 auto）", () => {
    expect(parseThemePreference("auto")).toBe("auto");
    expect(parseThemePreference("light")).toBe("light");
    expect(parseThemePreference("dark")).toBe("dark");
    expect(parseThemePreference("Dark")).toBeNull();
    expect(parseThemePreference("solarized")).toBeNull();
    expect(parseThemePreference("")).toBeNull();
    expect(parseThemePreference(null)).toBeNull();
    expect(parseThemePreference(42)).toBeNull();
  });
});
