import { describe, expect, it } from "vitest";
import { DRAG_THRESHOLD_PX, shouldStartDrag } from "./pet-drag";

describe("pet-drag 拖拽阈值判定（M6，TC-WIN-01/02）", () => {
  it("按下后未移动 / 移动小于阈值 → 不进入拖拽（保留点击语义）", () => {
    expect(shouldStartDrag(100, 100, 100, 100)).toBe(false);
    expect(shouldStartDrag(100, 100, 103, 103)).toBe(false);
  });

  it("水平或垂直超过阈值 → 进入拖拽", () => {
    expect(shouldStartDrag(100, 100, 100 + DRAG_THRESHOLD_PX, 100)).toBe(true);
    expect(shouldStartDrag(100, 100, 100 - DRAG_THRESHOLD_PX, 100)).toBe(true);
    expect(shouldStartDrag(100, 100, 100, 100 + DRAG_THRESHOLD_PX)).toBe(true);
    expect(shouldStartDrag(100, 100, 100 + 1, 100 + DRAG_THRESHOLD_PX + 2)).toBe(true);
  });

  it("阈值默认 4px（跨轴分量不叠加）", () => {
    // 3px + 3px 各自都小于 4 → 不触发（按轴判定，避免斜向轻移误触发）
    expect(shouldStartDrag(100, 100, 103, 97)).toBe(false);
  });

  it("自定义阈值生效", () => {
    expect(shouldStartDrag(0, 0, 9, 0, 10)).toBe(false);
    expect(shouldStartDrag(0, 0, 10, 0, 10)).toBe(true);
  });
});
