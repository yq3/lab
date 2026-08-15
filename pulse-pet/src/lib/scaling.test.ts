import { describe, expect, it } from "vitest";
import { computeCanvasSize, computeFrameRect, computeScale } from "./scaling";

describe("computeScale：min 比例缩放（TC-SP-02）", () => {
  it("128×128 帧图在 220×220 canvas 内放大", () => {
    // 220/128 = 1.71875
    expect(computeScale(220, 220, 128, 128)).toBeCloseTo(1.71875, 5);
  });

  it("非正方形 canvas 取较小比例，保持比例不裁剪", () => {
    // 宽 100 高 200，帧 100×100 → 受宽度限制 scale=1
    expect(computeScale(100, 200, 100, 100)).toBe(1);
  });
});

describe("computeCanvasSize：HiDPI 内部分辨率（TC-SP-02）", () => {
  it("1× 显示器内部分辨率 = 220", () => {
    expect(computeCanvasSize(220, 1)).toBe(220);
  });

  it("2× 显示器内部分辨率 = 440", () => {
    expect(computeCanvasSize(220, 2)).toBe(440);
  });
});

describe("computeFrameRect：居中绘制、不裁剪", () => {
  it("128 帧在 220 canvas 内居中放大到 220", () => {
    const r = computeFrameRect(220, 220, 128, 128);
    expect(r.dw).toBeCloseTo(220, 5);
    expect(r.dh).toBeCloseTo(220, 5);
    expect(r.dx).toBeCloseTo(0, 5);
    expect(r.dy).toBeCloseTo(0, 5);
  });

  it("HiDPI 2× 下帧图居中且放大到 440", () => {
    const r = computeFrameRect(440, 440, 128, 128);
    expect(r.dw).toBeCloseTo(440, 5);
    expect(r.dx).toBeCloseTo(0, 5);
  });

  it("帧图完整落在 canvas 内（不裁剪）", () => {
    const r = computeFrameRect(220, 220, 128, 128);
    expect(r.dx).toBeGreaterThanOrEqual(0);
    expect(r.dy).toBeGreaterThanOrEqual(0);
    expect(r.dx + r.dw).toBeLessThanOrEqual(220 + 1e-6);
    expect(r.dy + r.dh).toBeLessThanOrEqual(220 + 1e-6);
  });
});
