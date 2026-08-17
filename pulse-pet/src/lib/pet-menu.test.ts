import { describe, expect, it } from "vitest";
import { buildPetMenuItems, clampMenuPosition } from "./pet-menu";

describe("buildPetMenuItems 右键菜单项（M6，TC-WIN-03）", () => {
  it("非穿透态：含「设置」与「切换交互模式」入口（TC-WIN-03 规定项）", () => {
    const items = buildPetMenuItems(false);
    const labels = items.map((i) => i.label).join("\n");
    expect(labels).toContain("设置");
    expect(labels).toContain("切换交互模式");
  });

  it("「切换交互模式」标签随穿透状态显示 开/关（双通道状态可见，TC-WIN-05）", () => {
    const off = buildPetMenuItems(false).find((i) => i.id === "toggle-pass-through");
    const on = buildPetMenuItems(true).find((i) => i.id === "toggle-pass-through");
    expect(off?.label).toContain("关");
    expect(on?.label).toContain("开");
  });

  it("菜单项 id 唯一且有对应动作", () => {
    const items = buildPetMenuItems(false);
    const ids = items.map((i) => i.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const need of ["settings", "toggle-pass-through", "hide-pet"] as const) {
      expect(ids).toContain(need);
    }
  });
});

describe("clampMenuPosition 菜单定位（220×220 窗口内，M6）", () => {
  const W = 220;
  const MENU_W = 176;
  const MENU_H = 104;

  it("光标在中上部 → 原位弹出", () => {
    const p = clampMenuPosition(10, 20, W, MENU_W, MENU_H);
    expect(p).toEqual({ x: 10, y: 20 });
  });

  it("光标近右缘 → 左移贴边不越出窗口", () => {
    const p = clampMenuPosition(215, 20, W, MENU_W, MENU_H);
    expect(p.x).toBeLessThanOrEqual(W - MENU_W - 2);
    expect(p.x).toBeGreaterThanOrEqual(2);
  });

  it("光标近底缘 → 上移贴边；两轴同时越界 → 同时 clamp", () => {
    const p = clampMenuPosition(218, 218, W, MENU_W, MENU_H);
    expect(p.y).toBeLessThanOrEqual(W - MENU_H - 2);
    expect(p.x).toBeLessThanOrEqual(W - MENU_W - 2);
  });

  it("菜单比窗口还大 → 退化为安全边距（不 panic）", () => {
    const p = clampMenuPosition(110, 110, W, 300, 300);
    expect(p.x).toBe(2);
    expect(p.y).toBe(2);
  });
});
