import { describe, expect, it } from "vitest";
import { BUBBLE_AUTO_HIDE_MS, sanitizeBubbleText } from "./bubble";

describe("sanitizeBubbleText：气泡净化约束（沿用 M2 口径，TC-EV-20/21）", () => {
  it("多行压成单行", () => {
    expect(sanitizeBubbleText("a\nb\r\nc")).toBe("a b c");
  });
  it("超长截断到 140 字符", () => {
    expect(sanitizeBubbleText("x".repeat(200)).length).toBe(140);
  });
  it("空/空白/非字符串 → 空串（丢弃，不出气泡）", () => {
    expect(sanitizeBubbleText("")).toBe("");
    expect(sanitizeBubbleText("   ")).toBe("");
    expect(sanitizeBubbleText(null)).toBe("");
    expect(sanitizeBubbleText(123)).toBe("");
    expect(sanitizeBubbleText(undefined)).toBe("");
  });
  it("合法文本原样保留（token 汇报模板实测）", () => {
    expect(sanitizeBubbleText("本期用了 58.3k input / 910 output / $0.05")).toBe(
      "本期用了 58.3k input / 910 output / $0.05",
    );
  });
  it("自动隐藏时长为正的常量", () => {
    expect(BUBBLE_AUTO_HIDE_MS).toBeGreaterThan(0);
  });
});
