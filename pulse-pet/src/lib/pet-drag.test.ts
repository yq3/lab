import { describe, expect, it } from "vitest";
import { DRAG_THRESHOLD_PX, shouldStartDrag, DragClickGuard } from "./pet-drag";

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

describe("DragClickGuard 拖拽尾巴 click 抑制（M6 R2，用户反馈：拖拽后附加一次单击）", () => {
  it("拖拽序列（down→超阈值 move→up→click）：click 被抑制一次（不轮换）", () => {
    const g = new DragClickGuard();
    g.onPointerDown(100, 100);
    expect(g.onPointerMove(100 + DRAG_THRESHOLD_PX, 100)).toBe(true); // 启动拖拽
    g.onPointerUp();
    // OS drag loop 结束后 WKWebView 补发的 click：吞掉
    expect(g.shouldSuppressClick()).toBe(true);
    // 只吞一次：后续（不存在的）重复询问不再抑制
    expect(g.shouldSuppressClick()).toBe(false);
  });

  it("普通单击（down→up→click，无位移）：不抑制（保留 M1 状态轮换）", () => {
    const g = new DragClickGuard();
    g.onPointerDown(100, 100);
    expect(g.onPointerMove(101, 102)).toBe(false); // 未达阈值
    g.onPointerUp();
    expect(g.shouldSuppressClick()).toBe(false);
  });

  it("无 move 的纯点击（down→up→click）：不抑制", () => {
    const g = new DragClickGuard();
    g.onPointerDown(0, 0);
    g.onPointerUp();
    expect(g.shouldSuppressClick()).toBe(false);
  });

  it("超阈值后连续 move 只启动一次拖拽（drag loop 接管后多余的 move 不重复触发）", () => {
    const g = new DragClickGuard();
    g.onPointerDown(0, 0);
    expect(g.onPointerMove(DRAG_THRESHOLD_PX, 0)).toBe(true);
    expect(g.onPointerMove(DRAG_THRESHOLD_PX * 5, 20)).toBe(false);
    expect(g.onPointerMove(0, 0)).toBe(false);
  });

  it("平台差异兜底：拖拽结束若平台不补发 click，下一次按下重置（真实单击不被误吞）", () => {
    const g = new DragClickGuard();
    g.onPointerDown(0, 0);
    g.onPointerMove(DRAG_THRESHOLD_PX, 0); // 拖拽
    g.onPointerUp();
    // 假设该平台没有补发 click —— 标志残留；用户随后真实单击：
    g.onPointerDown(50, 50); // 新一轮按下 → 重置抑制标志
    g.onPointerUp();
    expect(g.shouldSuppressClick()).toBe(false);
  });

  it("非主键/穿透路径不记录起点：无 down 的 move 序列不触发拖拽也不抑制", () => {
    const g = new DragClickGuard();
    expect(g.onPointerMove(1000, 1000)).toBe(false); // 悬停滑动（无按键）
    expect(g.shouldSuppressClick()).toBe(false);
  });
});
