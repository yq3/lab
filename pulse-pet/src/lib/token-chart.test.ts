import { describe, expect, it } from "vitest";
import { computeBars, pieSlices } from "./token-chart";

describe("computeBars：柱状图几何（自画 SVG，TC-TK-09）", () => {
  it("高度与最大值成比例，且落在绘图区内", () => {
    const bars = computeBars([1, 2, 4], { width: 200, height: 100, pad: 10 });
    expect(bars).toHaveLength(3);
    // 最大值占满可用高度
    const maxH = Math.max(...bars.map((b) => b.h));
    expect(maxH).toBe(100 - 2 * 10);
    // 比例 1:2:4
    expect(bars[0].h).toBeCloseTo(maxH / 4, 6);
    expect(bars[1].h).toBeCloseTo(maxH / 2, 6);
    // 条不重叠、都在画布内
    for (const b of bars) {
      expect(b.x).toBeGreaterThanOrEqual(0);
      expect(b.x + b.w).toBeLessThanOrEqual(200);
      expect(b.y).toBeGreaterThanOrEqual(0);
      expect(b.y + b.h).toBeLessThanOrEqual(100);
    }
    expect(bars[0].x + bars[0].w).toBeLessThanOrEqual(bars[1].x);
  });

  it("零值高度 0（贴基线），不产生 NaN", () => {
    const bars = computeBars([0, 5, 0], { width: 90, height: 60, pad: 5 });
    expect(bars[0].h).toBe(0);
    expect(Number.isFinite(bars[0].y)).toBe(true);
    expect(bars[2].h).toBe(0);
  });

  it("全零 / 空输入 → 空/全零条", () => {
    expect(computeBars([], { width: 100, height: 50, pad: 5 })).toEqual([]);
    const bars = computeBars([0, 0], { width: 100, height: 50, pad: 5 });
    expect(bars.every((b) => b.h === 0)).toBe(true);
  });
});

describe("pieSlices：项目占比饼图（TC-TK-09）", () => {
  it("两个等值切片各 50%，path 合法", () => {
    const slices = pieSlices(
      [
        { value: 5, label: "a" },
        { value: 5, label: "b" },
      ],
      50,
    );
    expect(slices).toHaveLength(2);
    expect(slices[0].percent).toBeCloseTo(50, 6);
    expect(slices[1].percent).toBeCloseTo(50, 6);
    for (const s of slices) {
      expect(s.path.startsWith("M")).toBe(true);
      expect(s.path).toMatch(/A\s+50\s+50\s/);
    }
  });

  it("单项 100% 生成完整圆（两段弧）", () => {
    const slices = pieSlices([{ value: 3, label: "only" }], 40);
    expect(slices).toHaveLength(1);
    expect(slices[0].percent).toBeCloseTo(100, 6);
    // 完整圆需两段半圆弧
    expect(slices[0].path.match(/A/g)?.length).toBeGreaterThanOrEqual(2);
  });

  it("空 / 全零 → 无切片", () => {
    expect(pieSlices([], 40)).toEqual([]);
    expect(
      pieSlices(
        [
          { value: 0, label: "a" },
          { value: 0, label: "b" },
        ],
        40,
      ),
    ).toEqual([]);
  });

  it("占比和为 100%", () => {
    const slices = pieSlices(
      [
        { value: 1, label: "a" },
        { value: 2, label: "b" },
        { value: 7, label: "c" },
      ],
      60,
    );
    const total = slices.reduce((acc, s) => acc + s.percent, 0);
    expect(total).toBeCloseTo(100, 6);
  });
});
